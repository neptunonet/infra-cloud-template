import sys
from pathlib import Path

import prometheus_client
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    for collector in list(prometheus_client.REGISTRY._collector_to_names):
        prometheus_client.REGISTRY.unregister(collector)
    yield
