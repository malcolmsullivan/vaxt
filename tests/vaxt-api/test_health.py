"""Health + readiness for the BrAPI server. Keyless, runs against the committed DB."""
import os

import pytest

from vaxt_api.db import db_path

pytestmark = pytest.mark.skipif(not os.path.exists(db_path()), reason="DuckDB not available")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from vaxt_api.app import app
    return TestClient(app)


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_counts_full_warehouse(client):
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["tables"] >= 27
