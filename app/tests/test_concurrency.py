"""Concurrent writes must not lose hits or corrupt items.json."""

import importlib
import sys
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient


def test_concurrent_writes_keep_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    if "main" in sys.modules:
        app_module = importlib.reload(sys.modules["main"])
    else:
        import main as app_module
    client = TestClient(app_module.app)

    def post(i):
        return client.post("/items", json={"name": f"demo-{i}"}).status_code

    def hit(_):
        return client.get("/").status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        posts = list(pool.map(post, range(200)))
        hits = list(pool.map(hit, range(200)))

    assert set(posts) == {201}
    assert set(hits) == {200}
    assert len(client.get("/items").json()) == 200
    assert (tmp_path / "counter.txt").read_text() == "200"
    assert not list(tmp_path.glob(".*"))  # no temp files left behind
