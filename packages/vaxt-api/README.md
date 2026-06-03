# vaxt-api — VAXT BrAPI v2.1 server

A thin, **read-only [BrAPI v2.1](https://brapi.org)** (Breeding API) over the VAXT heritage-grain DuckDB,
so the data is consumable by standard breeding tools (BMS, Breedbase, Field Book) — not just the MCP
server and the website. FastAPI + DuckDB, stateless (a read-only connection per request).

## Run
```bash
pip install -e "packages/vaxt-api[dev]"
export VAXT_DUCKDB_PATH=data/datasets/heritage-grain/heritage-grain.duckdb   # default
uvicorn vaxt_api.app:app --reload
# → http://127.0.0.1:8000/brapi/v2/serverinfo   (interactive docs at /docs)
```

## Endpoints (core v2.1 subset)
| Call | Backed by | Notes |
|---|---|---|
| `GET /brapi/v2/serverinfo` | — | server + implemented calls |
| `GET /brapi/v2/germplasm` | `t3_germplasm` (200) | filters: `germplasmName`, `commonCropName` |
| `GET /brapi/v2/germplasm/{germplasmDbId}` | `t3_germplasm` | 404 if missing |
| `GET /brapi/v2/studies` | distinct `t3_observations.study_db_id` (82) | filter: `studyName` |
| `GET /brapi/v2/studies/{studyDbId}` | `t3_observations` | + observation variables |
| `GET /brapi/v2/observationunits` | `t3_observations` | filters: `studyDbId`, `germplasmName` |
| `GET /brapi/v2/observations` | `t3_observations` (6202) | filters: `studyDbId`, `germplasmName` |

All list endpoints page with `page` / `pageSize` and return the standard BrAPI envelope
(`metadata.pagination` + `result.data`).

## Test
```bash
pip install -e "packages/vaxt-api[dev]"
VAXT_DUCKDB_PATH=data/datasets/heritage-grain/heritage-grain.duckdb pytest tests/vaxt-api/ -v
```
Tests assert against the committed DB snapshot (200 germplasm · 82 studies · 6202 observations).
