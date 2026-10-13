import exporter as exporter_module
import httpx
from fastapi.testclient import TestClient


class _FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"jsonrpc": "2.0", "id": 1, "result": "0x2a"}  # block 42


def test_metrics_reports_block_number(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse())
    client = TestClient(exporter_module.app)

    r = client.get("/metrics")
    assert r.status_code == 200
    assert "anvil_block_number 42.0" in r.text


def test_metrics_survives_unreachable_rpc(monkeypatch):
    def _boom(*a, **k):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(httpx, "post", _boom)
    client = TestClient(exporter_module.app)
    r = client.get("/metrics")
    assert r.status_code == 200  # degrades gracefully, keeps serving


def test_healthz():
    client = TestClient(exporter_module.app)
    assert client.get("/healthz").json() == {"status": "ok"}
