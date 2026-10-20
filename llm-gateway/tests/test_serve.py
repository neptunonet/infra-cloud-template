"""Tests del gateway con Ollama simulado (httpx.MockTransport).

En CI no hay Ollama ni pesos: cada test arma la respuesta que daría Ollama y
verifica qué le manda el gateway y qué devuelve.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

import serve


def _ollama_down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


@pytest.fixture()
def client():
    return TestClient(serve.app)


def use_ollama(monkeypatch, handler):
    monkeypatch.setattr(serve, "transport", httpx.MockTransport(handler))


def test_healthz_does_not_need_ollama(client, monkeypatch):
    use_ollama(monkeypatch, _ollama_down)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_ok_when_model_is_loaded(client, monkeypatch):
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": serve.MODEL}]})

    use_ollama(monkeypatch, handler)
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "model": serve.MODEL}


def test_readyz_503_when_model_is_missing(client, monkeypatch):
    use_ollama(monkeypatch, lambda req: httpx.Response(200, json={"models": []}))
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["status"] == "model missing"


def test_readyz_503_when_ollama_is_down(client, monkeypatch):
    use_ollama(monkeypatch, _ollama_down)
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["status"] == "ollama unreachable"


def test_generate_forwards_prompt_and_reports_tokens_per_s(client, monkeypatch):
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": serve.MODEL,
                "response": "Hola.",
                "eval_count": 20,
                "eval_duration": 2_000_000_000,  # 2 s en nanosegundos
            },
        )

    use_ollama(monkeypatch, handler)
    r = client.post("/generate", json={"prompt": "Decí hola", "max_tokens": 32})
    assert r.status_code == 200
    assert seen["path"] == "/api/generate"
    assert seen["body"] == {
        "model": serve.MODEL,
        "prompt": "Decí hola",
        "stream": False,
        "options": {"num_predict": 32},
    }
    body = r.json()
    assert body["response"] == "Hola."
    assert body["tokens"] == 20
    assert body["tokens_per_s"] == 10.0


def test_generate_502_when_ollama_is_down(client, monkeypatch):
    use_ollama(monkeypatch, _ollama_down)
    r = client.post("/generate", json={"prompt": "hola"})
    assert r.status_code == 502


def test_generate_rejects_empty_prompt(client):
    r = client.post("/generate", json={"prompt": ""})
    assert r.status_code == 422
