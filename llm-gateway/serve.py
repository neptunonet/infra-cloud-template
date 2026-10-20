"""Gateway HTTP delante de Ollama (Lab Clase 4, entregable 3.3).

Endpoints:
  - GET  /healthz   -> 200 si el proceso está vivo (liveness). No depende de
                       Ollama: así el smoke test de CI pasa sin modelo.
  - GET  /readyz    -> 200 si Ollama responde y tiene cargado MODEL; 503 si no
                       (readiness: no mandar tráfico hasta que esté listo).
  - POST /generate  -> {"prompt": "...", "max_tokens": 128}; reenvía a Ollama y
                       devuelve el texto, los tokens y los tokens/s.

La imagen no trae pesos. Qué modelo usar lo dice MODEL (por defecto el mismo
llama3.2:1b de la Clase 1) y dónde está Ollama lo dice OLLAMA_URL. Los pesos
viven en el volumen /models del contenedor de Ollama (entregable 3.2).
"""

import os
import time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("MODEL", "llama3.2:1b")
PORT = int(os.environ.get("PORT", "8082"))
TIMEOUT_S = float(os.environ.get("OLLAMA_TIMEOUT_S", "120"))

# Los tests lo reemplazan por un httpx.MockTransport: no hace falta Ollama real.
transport: httpx.BaseTransport | None = None


def _ollama() -> httpx.Client:
    return httpx.Client(base_url=OLLAMA_URL, timeout=TIMEOUT_S, transport=transport)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    max_tokens: int = Field(default=128, ge=1, le=1024)


app = FastAPI(title="llm-gateway", version="1.0.0")


@app.get("/")
def index() -> dict[str, object]:
    return {
        "service": "llm-gateway",
        "model": MODEL,
        "ollama_url": OLLAMA_URL,
        "endpoints": ["POST /generate", "GET /healthz", "GET /readyz", "GET /docs"],
        "example": {"prompt": "Decí hola en una frase", "max_tokens": 32},
    }


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> JSONResponse:
    try:
        with _ollama() as client:
            r = client.get("/api/tags")
            r.raise_for_status()
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"status": "ollama unreachable", "detail": str(exc)}, status_code=503
        )
    names = [m.get("name") for m in r.json().get("models", [])]
    if MODEL not in names:
        return JSONResponse(
            {"status": "model missing", "model": MODEL, "available": names},
            status_code=503,
        )
    return JSONResponse({"status": "ready", "model": MODEL})


@app.post("/generate")
def generate(req: GenerateRequest) -> dict[str, object]:
    payload = {
        "model": MODEL,
        "prompt": req.prompt,
        "stream": False,
        "options": {"num_predict": req.max_tokens},
    }
    start = time.time()
    try:
        with _ollama() as client:
            r = client.post("/api/generate", json=payload)
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"ollama error: {exc}") from exc
    body = r.json()

    tokens = int(body.get("eval_count", 0))
    eval_s = body.get("eval_duration", 0) / 1e9
    return {
        "model": body.get("model", MODEL),
        "response": body.get("response", ""),
        "tokens": tokens,
        "tokens_per_s": round(tokens / eval_s, 2) if eval_s else None,
        "latency_s": round(time.time() - start, 3),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
