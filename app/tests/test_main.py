"""Tests for the servicio patron. Uses a temp dir as DATA_DIR so nothing
touches the real /data path."""

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    already_imported = "main" in sys.modules
    import main as app_module

    if already_imported:
        importlib.reload(app_module)  # pick up the patched DATA_DIR
    return TestClient(app_module.app)


def test_root_persists_counter(client):
    r1 = client.get("/")
    assert r1.status_code == 200
    assert "Visitas persistidas" in r1.text

    r2 = client.get("/")
    assert "2" in r2.text  # second hit, counter must have persisted


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_metrics_exposes_prometheus_format(client):
    client.get("/")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert b"servicio_patron_hits_total" in r.content


def test_items_roundtrip(client):
    payload = {"name": "gpu", "value": "t4"}
    r = client.post("/items", json=payload)
    assert r.status_code == 201
    assert r.json()["name"] == "gpu"

    r2 = client.get("/items")
    assert len(r2.json()) == 1
    assert r2.json()[0]["name"] == "gpu"
