"""Tiny inference server used in class 7 (Vertex AI / Ollama / vast.ai
alternatives) and in the class-8 integrator case.

Endpoints:
  - POST /predict  -> {"features": [sepal_len, sepal_wid, petal_len, petal_wid]}
                      returns {"class": "...", "confidence": 0.9x, "model_version": "v1.2"}
  - GET  /metrics   -> Prometheus exposition format
  - GET  /healthz   -> 200 once the model is loaded, 503 before (readiness)
  - GET  /          -> short help text

Loads model.joblib produced by train.py at image build time -- no training
happens on the request path. The file is loaded ONCE at startup: until it is
loaded /healthz answers 503, so Kubernetes does not send traffic to a pod
whose weights are missing or still loading, and the first /predict is not
slower than the rest.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

MODEL_PATH = Path(os.environ.get("MODEL_PATH", "model.joblib"))
PORT = int(os.environ.get("PORT", "8081"))
# Class 8: observable change that travels commit -> CI -> image -> Helm.
# v1.1 is already taken in the registry (class-6 image with the confidence metric).
MODEL_VERSION = "v1.2"

PREDICTIONS = Counter("model_predictions_total", "Total predictions served")
PREDICT_LATENCY = Histogram("model_predict_seconds", "Prediction latency in seconds")
# Class 6: drift proxy. In-distribution inputs score ~0.98; ambiguous or
# out-of-distribution inputs pull the confidence of the winning class down.
PREDICT_CONFIDENCE = Histogram(
    "predict_confidence_score",
    "Probability of the predicted class",
    buckets=(0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0),
)

_bundle = None


def _load_bundle():
    global _bundle
    if _bundle is None:
        if not MODEL_PATH.exists():
            raise RuntimeError(
                f"model file not found at {MODEL_PATH}; run train.py first"
            )
        _bundle = joblib.load(MODEL_PATH)
    return _bundle


class PredictRequest(BaseModel):
    features: list[float]


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        _load_bundle()
    except Exception as exc:  # keep serving /healthz=503 so the cause is visible
        print(f"model not loaded: {exc}", flush=True)
    yield


app = FastAPI(title="model-server", version="1.0.0", lifespan=lifespan)


@app.get("/")
def index() -> dict[str, object]:
    return {
        "service": "model-server",
        "endpoints": ["POST /predict", "GET /healthz", "GET /metrics", "GET /docs"],
        "example": {"features": [5.1, 3.5, 1.4, 0.2]},
    }


@app.get("/healthz")
def healthz() -> Response:
    if _bundle is None:
        return Response(
            content='{"status":"loading"}',
            status_code=503,
            media_type="application/json",
        )
    return Response(content='{"status":"ok"}', media_type="application/json")


@app.get("/metrics")
def metrics() -> Response:
    PREDICTIONS.inc(0)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict")
def predict(req: PredictRequest) -> dict[str, object]:
    if len(req.features) != 4:
        raise HTTPException(
            400,
            "expected 4 features (iris: sepal_len, sepal_wid, petal_len, petal_wid)",
        )

    if _bundle is None:
        raise HTTPException(503, "model not loaded yet, check /healthz and the logs")

    start = time.time()
    bundle = _bundle
    model = bundle["model"]
    proba = model.predict_proba([req.features])[0]
    idx = int(proba.argmax())
    PREDICTIONS.inc()
    PREDICT_LATENCY.observe(time.time() - start)
    PREDICT_CONFIDENCE.observe(float(proba[idx]))
    return {
        "class": bundle["target_names"][idx],
        "confidence": float(proba[idx]),
        "model_version": MODEL_VERSION,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
