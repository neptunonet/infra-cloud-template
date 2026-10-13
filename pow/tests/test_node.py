import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    already_imported = "node" in sys.modules
    import node as node_module

    if already_imported:
        importlib.reload(node_module)
    with TestClient(node_module.app) as test_client:
        yield test_client


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_chain_starts_with_genesis(client):
    chain = client.get("/chain").json()
    assert len(chain) == 1
    assert chain[0]["index"] == 0


def test_tx_and_mine(client):
    r = client.post("/tx", json={"sender": "ana", "to": "beto", "amount": 1})
    assert r.status_code == 201
    assert len(client.get("/tx").json()) == 1

    body = client.post("/mine").json()
    assert body["mined"]["index"] == 1
    assert body["mined"]["transactions"][0]["sender"] == "ana"
    assert client.get("/tx").json() == []
    assert len(client.get("/chain").json()) == 2


def test_chain_survives_a_restart(client, tmp_path):
    client.post("/mine")
    assert (tmp_path / "chain.json").exists()
    import node

    assert len(node.load_chain()) == 2


def test_metrics_reports_block_height(client):
    client.post("/mine")
    assert "pow_block_height 1.0" in client.get("/metrics").text


@pytest.mark.skip(reason="TODO(TF): add POST /peers/sync and enable this test")
def test_peers_sync_exists(client):
    assert client.post("/peers/sync").status_code == 200
