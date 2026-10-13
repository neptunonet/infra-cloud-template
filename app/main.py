"""Servicio patron: the reference stateful HTTP service used in every class.

Contract (the class-1 Moodle lab builds a minimal hand-written version of the
same idea; this is the one used from class 2 on):
  - GET  /          -> plain-text hit counter, persisted on disk
  - GET  /healthz   -> liveness probe, always 200 if the process is up
  - GET  /metrics   -> Prometheus exposition format
  - POST /items     -> append a small JSON item to the persisted list
  - GET  /items     -> list the persisted items

State lives under DATA_DIR (default /data), which in every class is a
mounted persistent disk / PVC. Kill the container, keep the disk: the state
survives. That is the whole point of the class-1 demo.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

# --- configuration (env vars, no hardcoded paths/ports) --------------------
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
COUNTER_FILE = DATA_DIR / "counter.txt"
ITEMS_FILE = DATA_DIR / "items.json"
PORT = int(os.environ.get("PORT", "8080"))

app = FastAPI(title="servicio-patron", version="1.0.0")

# --- metrics -----------------------------------------------------------
HITS = Counter("servicio_patron_hits_total", "Total requests received on /")
ITEMS_CREATED = Counter(
    "servicio_patron_items_created_total", "Items persisted via POST /items"
)
REQUEST_LATENCY = Histogram(
    "servicio_patron_request_seconds", "Request latency in seconds", ["path"]
)


# One lock for every read-modify-write of the state files. FastAPI runs sync
# endpoints in a thread pool, so concurrent requests would otherwise lose
# counter hits or leave items.json half-written (and GET /items in 500).
_STATE_LOCK = threading.Lock()


def _atomic_write(path: Path, text: str) -> None:
    """Write to a temp file in the same dir, then rename over the target.

    os.replace is atomic on POSIX: a reader (or a crash) sees the old file or
    the new one, never a truncated mix.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=f".{path.name}.")
    try:
        os.chmod(tmp, 0o644)  # mkstemp creates 0600; keep the old file mode
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class Item(BaseModel):
    name: str
    value: str | None = None


def _read_counter() -> int:
    if COUNTER_FILE.exists():
        return int(COUNTER_FILE.read_text().strip() or 0)
    return 0


def _write_counter(value: int) -> None:
    _atomic_write(COUNTER_FILE, str(value))


def _read_items() -> list[dict[str, Any]]:
    if ITEMS_FILE.exists():
        return json.loads(ITEMS_FILE.read_text() or "[]")
    return []


def _write_items(items: list[dict[str, Any]]) -> None:
    _atomic_write(ITEMS_FILE, json.dumps(items))


@app.get("/")
def root() -> Response:
    start = time.time()
    HITS.inc()
    with _STATE_LOCK:
        contador = _read_counter() + 1
        _write_counter(contador)
    body = f"Servicio patron activo. Visitas persistidas en disco: {contador}\n"
    REQUEST_LATENCY.labels(path="/").observe(time.time() - start)
    return Response(content=body, media_type="text/plain; charset=utf-8")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    HITS.inc(0)  # make sure the metric exists even before anyone hits "/"
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/items", status_code=201)
def create_item(item: Item) -> dict[str, Any]:
    start = time.time()
    stored = item.model_dump()
    stored["created_at"] = time.time()
    with _STATE_LOCK:
        items = _read_items()
        items.append(stored)
        _write_items(items)
    ITEMS_CREATED.inc()
    REQUEST_LATENCY.labels(path="/items").observe(time.time() - start)
    return stored


@app.get("/items")
def list_items() -> list[dict[str, Any]]:
    with _STATE_LOCK:
        return _read_items()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
