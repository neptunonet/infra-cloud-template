import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

MODEL_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def trained_model(tmp_path_factory, monkeypatch_session=None):
    # Train into a throwaway dir so we never touch a committed model file.
    tmp_dir = tmp_path_factory.mktemp("model")
    model_path = tmp_dir / "model.joblib"
    subprocess.run(
        [sys.executable, str(MODEL_DIR / "train.py")],
        cwd=tmp_dir,
        check=True,
    )
    return model_path


@pytest.fixture()
def client(trained_model, monkeypatch):
    monkeypatch.setenv("MODEL_PATH", str(trained_model))
    import importlib
    import sys

    already_imported = "serve" in sys.modules
    import serve as serve_module

    if already_imported:
        importlib.reload(serve_module)
    with TestClient(serve_module.app) as test_client:  # runs the startup hook
        yield test_client


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_healthz_is_503_without_a_model(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "missing.joblib"))
    import importlib

    import serve as serve_module

    importlib.reload(serve_module)
    with TestClient(serve_module.app) as c:
        assert c.get("/healthz").status_code == 503
        r = c.post("/predict", json={"features": [5.1, 3.5, 1.4, 0.2]})
        assert r.status_code == 503


def test_index_lists_endpoints(client):
    assert "POST /predict" in client.get("/").json()["endpoints"]


def test_predict_returns_class_and_confidence(client):
    r = client.post("/predict", json={"features": [5.1, 3.5, 1.4, 0.2]})
    assert r.status_code == 200
    body = r.json()
    assert body["class"] in {"setosa", "versicolor", "virginica"}
    assert 0.0 <= body["confidence"] <= 1.0


def test_predict_validates_feature_count(client):
    r = client.post("/predict", json={"features": [1.0]})
    assert r.status_code == 400


def test_metrics(client):
    client.post("/predict", json={"features": [5.1, 3.5, 1.4, 0.2]})
    r = client.get("/metrics")
    assert b"model_predictions_total" in r.content
