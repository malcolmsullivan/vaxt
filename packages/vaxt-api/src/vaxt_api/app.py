"""VAXT BrAPI v2.1 server.

A thin, read-only Breeding API (https://brapi.org) over the VAXT heritage-grain
DuckDB. Implements the core germplasm + study + observation calls so VAXT data is
consumable by standard breeding tools (BMS, Breedbase, Field Book).

Run locally:
    pip install -e "packages/vaxt-api[dev]"
    export VAXT_DUCKDB_PATH=data/datasets/heritage-grain/heritage-grain.duckdb
    uvicorn vaxt_api.app:app --reload
    # → http://127.0.0.1:8000/brapi/v2/serverinfo
"""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from vaxt_api import brapi, obs
from vaxt_api.db import db_path, query, scalar

EXPECTED_TABLE_COUNT = 27

obs.setup_json_logging()
log = logging.getLogger("vaxt_api")

app = FastAPI(
    title="VAXT BrAPI",
    version="2.1",
    description="Read-only BrAPI v2.1 over the VAXT heritage-grain DuckDB.",
)


@app.middleware("http")
async def _log_requests(request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    log.info(
        "request", extra={
            "event": "request", "method": request.method,
            "path": request.url.path, "status": response.status_code,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        },
    )
    return response


# ── health / readiness ──────────────────────────────────────────────────────
@app.get("/health")
def health():
    """Process up + DB path resolves + SELECT 1."""
    try:
        scalar("SELECT 1")
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})
    return {"status": "ok", "db": db_path()}


@app.get("/ready")
def ready():
    """Health + full warehouse present (>= 27 tables)."""
    try:
        tables = len(query("SHOW TABLES"))
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not_ready", "error": str(e)})
    if tables < EXPECTED_TABLE_COUNT:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "tables": tables, "expected": EXPECTED_TABLE_COUNT},
        )
    return {"status": "ready", "tables": tables}

_CALLS = [
    {"service": s, "methods": ["GET"], "versions": ["2.1"], "dataTypes": ["application/json"]}
    for s in (
        "serverinfo", "germplasm", "germplasm/{germplasmDbId}",
        "studies", "studies/{studyDbId}", "observationunits", "observations",
    )
]


# ── serverinfo ──────────────────────────────────────────────────────────────
@app.get("/brapi/v2/serverinfo")
def serverinfo() -> dict:
    return brapi.single({
        "serverName": "VAXT BrAPI",
        "serverDescription": "Read-only BrAPI v2.1 over the VAXT heritage-grain DuckDB",
        "organizationName": "VAXT / OpenSauce",
        "organizationURL": "https://vaxt.bio",
        "documentationURL": "https://brapi.org",
        "contactEmail": "",
        "location": "",
        "calls": _CALLS,
    })


# ── germplasm ───────────────────────────────────────────────────────────────
def _germplasm(r: dict) -> dict:
    return {
        "germplasmDbId": str(r["germplasm_db_id"]),
        "germplasmName": r["germplasm_name"],
        "accessionNumber": r.get("accession_number"),
        "commonCropName": r.get("crop"),
        "genus": r.get("genus"),
        "species": r.get("species"),
        "subtaxa": r.get("subtaxa"),
        "pedigree": r.get("pedigree"),
        "instituteCode": r.get("institute_code"),
        "countryOfOriginCode": r.get("country_of_origin"),
    }


@app.get("/brapi/v2/germplasm")
def germplasm(
    germplasmName: str | None = None,
    commonCropName: str | None = None,
    page: int = Query(0, ge=0),
    pageSize: int = Query(100, ge=1, le=1000),
) -> dict:
    where, params = [], []
    if germplasmName:
        where.append("germplasm_name ILIKE ?")
        params.append(f"%{germplasmName}%")
    if commonCropName:
        where.append("crop ILIKE ?")
        params.append(f"%{commonCropName}%")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = scalar(f"SELECT count(*) FROM t3_germplasm{clause}", params) or 0
    rows = query(
        f"SELECT * FROM t3_germplasm{clause} ORDER BY germplasm_name LIMIT ? OFFSET ?",
        params + [pageSize, page * pageSize],
    )
    return brapi.page([_germplasm(r) for r in rows], page, pageSize, total)


@app.get("/brapi/v2/germplasm/{germplasmDbId}")
def germplasm_by_id(germplasmDbId: str) -> dict:
    rows = query(
        "SELECT * FROM t3_germplasm WHERE CAST(germplasm_db_id AS VARCHAR) = ?",
        [germplasmDbId],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"germplasmDbId '{germplasmDbId}' not found")
    return brapi.single(_germplasm(rows[0]))


# ── studies ─────────────────────────────────────────────────────────────────
def _seasons(value) -> list[str]:
    return [str(s) for s in (value or []) if s is not None]


@app.get("/brapi/v2/studies")
def studies(
    studyName: str | None = None,
    page: int = Query(0, ge=0),
    pageSize: int = Query(100, ge=1, le=1000),
) -> dict:
    where, params = ["study_db_id IS NOT NULL"], []
    if studyName:
        where.append("study_name ILIKE ?")
        params.append(f"%{studyName}%")
    clause = " WHERE " + " AND ".join(where)
    total = scalar(f"SELECT count(DISTINCT study_db_id) FROM t3_observations{clause}", params) or 0
    rows = query(
        f"""
        SELECT study_db_id,
               any_value(study_name)            AS study_name,
               any_value(location)              AS location,
               list_distinct(list(season))      AS seasons,
               count(*)                         AS n_obs
        FROM t3_observations{clause}
        GROUP BY study_db_id
        ORDER BY study_name
        LIMIT ? OFFSET ?
        """,
        params + [pageSize, page * pageSize],
    )
    data = [{
        "studyDbId": str(r["study_db_id"]),
        "studyName": r["study_name"],
        "locationName": r.get("location"),
        "seasons": _seasons(r.get("seasons")),
        "active": True,
        "additionalInfo": {"observationCount": r["n_obs"]},
    } for r in rows]
    return brapi.page(data, page, pageSize, total)


@app.get("/brapi/v2/studies/{studyDbId}")
def study_by_id(studyDbId: str) -> dict:
    rows = query(
        """
        SELECT study_db_id,
               any_value(study_name)       AS study_name,
               any_value(location)         AS location,
               list_distinct(list(season)) AS seasons,
               list_distinct(list(variable_name)) AS variables,
               count(*)                    AS n_obs
        FROM t3_observations
        WHERE CAST(study_db_id AS VARCHAR) = ?
        GROUP BY study_db_id
        """,
        [studyDbId],
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"studyDbId '{studyDbId}' not found")
    r = rows[0]
    return brapi.single({
        "studyDbId": str(r["study_db_id"]),
        "studyName": r["study_name"],
        "locationName": r.get("location"),
        "seasons": _seasons(r.get("seasons")),
        "observationVariableDbIds": [str(v) for v in (r.get("variables") or [])],
        "active": True,
        "additionalInfo": {"observationCount": r["n_obs"]},
    })


# ── observation units ───────────────────────────────────────────────────────
@app.get("/brapi/v2/observationunits")
def observationunits(
    studyDbId: str | None = None,
    germplasmName: str | None = None,
    page: int = Query(0, ge=0),
    pageSize: int = Query(100, ge=1, le=1000),
) -> dict:
    where, params = ["observation_unit_name IS NOT NULL"], []
    if studyDbId:
        where.append("CAST(study_db_id AS VARCHAR) = ?")
        params.append(studyDbId)
    if germplasmName:
        where.append("germplasm_name ILIKE ?")
        params.append(f"%{germplasmName}%")
    clause = " WHERE " + " AND ".join(where)
    total = scalar(f"SELECT count(DISTINCT observation_unit_name) FROM t3_observations{clause}", params) or 0
    rows = query(
        f"""
        SELECT observation_unit_name,
               any_value(study_db_id)      AS study_db_id,
               any_value(study_name)       AS study_name,
               any_value(germplasm_db_id)  AS germplasm_db_id,
               any_value(germplasm_name)   AS germplasm_name
        FROM t3_observations{clause}
        GROUP BY observation_unit_name
        ORDER BY observation_unit_name
        LIMIT ? OFFSET ?
        """,
        params + [pageSize, page * pageSize],
    )
    data = [{
        "observationUnitDbId": r["observation_unit_name"],
        "observationUnitName": r["observation_unit_name"],
        "studyDbId": str(r["study_db_id"]) if r.get("study_db_id") is not None else None,
        "studyName": r.get("study_name"),
        "germplasmDbId": str(r["germplasm_db_id"]) if r.get("germplasm_db_id") is not None else None,
        "germplasmName": r.get("germplasm_name"),
    } for r in rows]
    return brapi.page(data, page, pageSize, total)


# ── observations ────────────────────────────────────────────────────────────
@app.get("/brapi/v2/observations")
def observations(
    studyDbId: str | None = None,
    germplasmName: str | None = None,
    page: int = Query(0, ge=0),
    pageSize: int = Query(100, ge=1, le=1000),
) -> dict:
    where, params = ["1 = 1"], []
    if studyDbId:
        where.append("CAST(study_db_id AS VARCHAR) = ?")
        params.append(studyDbId)
    if germplasmName:
        where.append("germplasm_name ILIKE ?")
        params.append(f"%{germplasmName}%")
    clause = " WHERE " + " AND ".join(where)
    total = scalar(f"SELECT count(*) FROM t3_observations{clause}", params) or 0
    rows = query(
        f"""
        SELECT observation_id, observation_unit_name, germplasm_db_id, germplasm_name,
               study_db_id, study_name, variable_name, value, season
        FROM t3_observations{clause}
        ORDER BY observation_id
        LIMIT ? OFFSET ?
        """,
        params + [pageSize, page * pageSize],
    )
    data = [{
        "observationDbId": str(r["observation_id"]),
        "observationUnitName": r.get("observation_unit_name"),
        "germplasmDbId": str(r["germplasm_db_id"]) if r.get("germplasm_db_id") is not None else None,
        "germplasmName": r.get("germplasm_name"),
        "studyDbId": str(r["study_db_id"]) if r.get("study_db_id") is not None else None,
        "studyName": r.get("study_name"),
        "observationVariableName": r.get("variable_name"),
        "value": r.get("value"),
        "season": str(r["season"]) if r.get("season") is not None else None,
    } for r in rows]
    return brapi.page(data, page, pageSize, total)
