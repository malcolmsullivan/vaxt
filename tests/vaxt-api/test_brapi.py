"""Tests for the VAXT BrAPI v2.1 server.

Run against the committed heritage-grain DuckDB. Totals are asserted against that
fixed snapshot (200 germplasm, 82 studies, 6202 observations). Skips if the DB is
absent (same convention as the MCP tests).
"""
import os

import pytest

from vaxt_api.db import db_path

pytestmark = pytest.mark.skipif(not os.path.exists(db_path()), reason="DuckDB not available")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from vaxt_api.app import app
    return TestClient(app)


def test_serverinfo(client):
    r = client.get("/brapi/v2/serverinfo")
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["serverName"] == "VAXT BrAPI"
    services = {c["service"] for c in result["calls"]}
    assert {"germplasm", "studies", "observations"} <= services


def test_germplasm_envelope(client):
    r = client.get("/brapi/v2/germplasm", params={"pageSize": 5})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"metadata", "result"}
    pag = body["metadata"]["pagination"]
    assert pag["pageSize"] == 5
    assert pag["totalCount"] == 200          # committed-DB snapshot
    assert pag["totalPages"] == 40
    data = body["result"]["data"]
    assert len(data) == 5
    assert {"germplasmDbId", "germplasmName", "commonCropName"} <= set(data[0])


def test_germplasm_filter_by_crop(client):
    r = client.get("/brapi/v2/germplasm", params={"commonCropName": "wheat", "pageSize": 1000})
    assert r.status_code == 200
    data = r.json()["result"]["data"]
    assert len(data) > 0
    assert all("wheat" in (g["commonCropName"] or "").lower() for g in data)


def test_germplasm_by_id_and_404(client):
    first = client.get("/brapi/v2/germplasm", params={"pageSize": 1}).json()["result"]["data"][0]
    gid = first["germplasmDbId"]
    ok = client.get(f"/brapi/v2/germplasm/{gid}")
    assert ok.status_code == 200
    assert ok.json()["result"]["germplasmDbId"] == gid
    missing = client.get("/brapi/v2/germplasm/__does_not_exist__")
    assert missing.status_code == 404


def test_studies(client):
    r = client.get("/brapi/v2/studies", params={"pageSize": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["pagination"]["totalCount"] == 82   # committed-DB snapshot
    data = body["result"]["data"]
    assert len(data) == 5
    s = data[0]
    assert "studyDbId" in s and "studyName" in s
    assert isinstance(s["seasons"], list)


def test_observations(client):
    r = client.get("/brapi/v2/observations", params={"pageSize": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["pagination"]["totalCount"] == 6202  # committed-DB snapshot
    data = body["result"]["data"]
    assert len(data) == 3
    assert {"observationDbId", "observationVariableName", "value"} <= set(data[0])


def test_observations_filter_by_study(client):
    study = client.get("/brapi/v2/studies", params={"pageSize": 1}).json()["result"]["data"][0]
    sid = study["studyDbId"]
    r = client.get("/brapi/v2/observations", params={"studyDbId": sid, "pageSize": 1000})
    assert r.status_code == 200
    data = r.json()["result"]["data"]
    assert len(data) > 0
    assert all(o["studyDbId"] == sid for o in data)


def test_observationunits(client):
    r = client.get("/brapi/v2/observationunits", params={"pageSize": 2})
    assert r.status_code == 200
    data = r.json()["result"]["data"]
    assert len(data) == 2
    assert {"observationUnitDbId", "observationUnitName"} <= set(data[0])
