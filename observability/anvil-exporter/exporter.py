"""Tiny JSON-RPC -> Prometheus exporter for Anvil (class 6, Anvil dashboard).

Anvil speaks Ethereum JSON-RPC, not Prometheus. Rather than pull in a big
generic Ethereum exporter, this polls the one method the class dashboard
needs (eth_blockNumber) and republishes it as a gauge. ~40 lines on purpose:
read it once, then extend it if your dashboard needs another RPC method.
"""

from __future__ import annotations

import os

import httpx
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from starlette.responses import Response

RPC_URL = os.environ.get("RPC_URL", "http://localhost:8545")
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "5"))
PORT = int(os.environ.get("PORT", "9090"))

app = FastAPI(title="anvil-exporter")
BLOCK_NUMBER = Gauge(
    "anvil_block_number", "Latest block number reported by eth_blockNumber"
)


def _poll_once() -> None:
    resp = httpx.post(
        RPC_URL,
        json={"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
        timeout=5.0,
    )
    resp.raise_for_status()
    hex_block = resp.json()["result"]
    BLOCK_NUMBER.set(int(hex_block, 16))


@app.get("/metrics")
def metrics() -> Response:
    try:
        _poll_once()
    except Exception:
        pass  # keep serving the last known value if Anvil is briefly unreachable
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
