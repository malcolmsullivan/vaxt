# VAXT — Heritage Grain Genomics Data Platform

[![CI](https://github.com/malcolmsullivan/vaxt/actions/workflows/ci.yml/badge.svg)](https://github.com/malcolmsullivan/vaxt/actions/workflows/ci.yml)
[![Code: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE)
[![Data: CC BY 4.0](https://img.shields.io/badge/Data-CC%20BY%204.0-green.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Live: vaxt.bio](https://img.shields.io/badge/Live-vaxt.bio-FF6B35.svg)](https://vaxt.bio)

VAXT turns fragmented public agricultural, climate, and genomics data into a single, queryable
knowledge base for **cold-climate heritage grain breeding** — and exposes it through many surfaces: a
public website, a **Claude-callable MCP server**, a grounded/cited agent + chat service, a BrAPI v2.1
endpoint, a Notion knowledge base, and an **[installable Claude Code plugin](#install-as-a-claude-code-plugin)**.
It pairs a manifest-driven ETL pipeline (9 public data sources → DuckDB) with a curated, original data
layer (a cold-tolerance marker registry and a 69-field phenotype schema with no public equivalent).

> **Why it exists:** the data needed to breed cold-hardy grain is scattered across a dozen
> incompatible public sources (FAO, Eurostat, USDA, GBIF, ISRIC, GrainGenes, T3/BrAPI…). VAXT unifies
> them under one typed schema so a breeder — or an AI agent — can actually ask questions across them.

---

## Ask VAXT — a grounded, cited agent

`packages/vaxt-agent/` is a production Claude agent that answers breeder/grower
questions over the 21 tools and the 27-table warehouse, with a hard grounding
contract: **every factual sentence must cite the warehouse row it came from, and
if the warehouse can't answer, the agent refuses instead of guessing.**

```bash
pip install -e "packages/vaxt" -e "packages/vaxt-agent[dev]"
export ANTHROPIC_API_KEY=...        # or: ant auth login
export VAXT_DUCKDB_PATH=data/datasets/heritage-grain/heritage-grain.duckdb

ask-vaxt "What can you tell me about the wheat variety Norstar?"
ask-vaxt "What is the current price of wheat futures?"   # -> refuses; out of scope
ask-vaxt --transport mcp "Compare Norstar and Goodland"  # route via the live MCP tool layer
```

A citation is a `(table, key)` pair, so it is **checkable against DuckDB with no
model call** — a fabricated key resolves to zero rows and fails. That turns
hallucination into a deterministic, testable event, which is what the eval gate
is built on:

```bash
python eval/run_eval.py --mode replay     # no API key needed; runs in CI on every PR
```

`--mode replay` grades committed transcripts (`eval/transcripts/`) against a
citation-anchored golden set (`eval/golden.jsonl`): every citation must resolve,
every answer must be anchored to the known-correct row, and out-of-scope
questions must be refused. It **fails loudly** if a transcript is missing or a
check fails — it cannot report success while checking nothing. `--mode live`
(re)generates the transcripts against the model and adds an independent semantic
judge (Opus 4.8). See [`CLAIMS.md`](CLAIMS.md) for how each claim maps to
verified reality.

### Run it as a service (chat UI + HTTP API)

`packages/vaxt-agent/web.py` serves Ask VAXT over HTTP with a thin, no-build chat
UI. It streams tool activity live and renders **citation chips that expand to the
real warehouse row on click** — grounding you can see. The DuckDB is baked into
the container, so it runs from a clean clone with zero setup:

```bash
docker compose run --rm eval    # the <2-min keyless proof: grounding holds, no API key
docker compose up               # serve the chat UI + /health + /ready on http://localhost:8000
```

With no `ANTHROPIC_API_KEY`, the UI still serves the tools, health, and citation
lookups and shows an honest "set the key to enable answers" state — **never a
fabricated answer**. Set `ANTHROPIC_API_KEY` in the environment to enable live
answers. Without Docker: `pip install -e "packages/vaxt" -e
"packages/vaxt-agent[web]"` then `uvicorn vaxt_agent.web:app` (or `vaxt-web`).

Endpoints: `POST /chat` (SSE — streams `status` events then the answer),
`GET /health` (process + DB + `SELECT 1`), `GET /ready` (warehouse ≥ 27 tables,
no model call), `GET /citation?table=&key=` (the row behind a citation). The BrAPI
server has matching `/health` and `/ready`. See [`ARCHITECTURE.md`](ARCHITECTURE.md)
for the data flow and failure model, and [`WALKTHROUGH.md`](WALKTHROUGH.md) for the
end-to-end story.

---

## Architecture

```
  DATA SOURCES (9)                ETL (manifest-driven)          STORE            SURFACES
  ───────────────                ─────────────────────          ─────            ────────
  FAOSTAT  Eurostat  GHCN   ─┐    sources.toml registry      ┌─► DuckDB   ──┬──► MCP server (21 tools + verify_citation)
  GrainGenes  T3/BrAPI      ─┤──► per-source validation      │   27 tables  ├──► Claude Code plugin (grounded, hook-verified)
  GBIF  SoilGrids           ─┤    (row bounds, unique keys,   │              ├──► BrAPI v2.1 endpoint · Website (vaxt.bio)
  + growing-season (derived) ┤     numeric ranges)            │              └──► Agent + chat service · Notion KB
  + photoperiod (computed)  ─┘    dry-run / fetch / validate ─┘
                                  via vaxt_runner.py
```

Every source declares its tables, required columns, and validation rules in `scripts/vaxt/sources.toml`.
The runner supports `--dry-run`, `--fetch-only`, `--validate-only`, and `--source <name>` so a failed
or partial load is caught at a gate instead of corrupting the store.

---

## Run it in 5 minutes

```bash
# 1. Install the MCP server (Python 3.11+)
pip install -e "packages/vaxt[dev]"

# 2. Build the DuckDB from the committed data
python scripts/vaxt/load_heritage_grain.py        # → data/datasets/heritage-grain/heritage-grain.duckdb

# 3. Point the server at the DB (this is also the default path)
export VAXT_DUCKDB_PATH=data/datasets/heritage-grain/heritage-grain.duckdb
#   PowerShell:  $env:VAXT_DUCKDB_PATH = "data/datasets/heritage-grain/heritage-grain.duckdb"

# 4. Run it, or register it with Claude
python -m vaxt_mcp                                  # run the MCP server directly
claude mcp add vaxt -- python -m vaxt_mcp.server    # register with Claude Code
```

Then ask Claude things like *"search VAXT for zone-3 winter wheat with snow-mold resistance"* or
*"cross-reference Norstar across markers, disease resistance, and seed sources."*

### Off-repo install (turnkey — the warehouse ships in the wheel)

The 8.76 MiB DuckDB is bundled inside the `vaxt-mcp` wheel (a build hook stages it +
a `WAREHOUSE.json` fingerprint), so the server resolves its data with **zero setup**
on any machine that has Python 3.11+ and [`uv`](https://docs.astral.sh/uv/):

```bash
# From the public repo, pinned to a tag (drift-proof: the installed server is
# byte-identical to the warehouse CLAIMS.md is verified against):
uvx --from "git+https://github.com/malcolmsullivan/vaxt@v0.1.0#subdirectory=packages/vaxt" vaxt-mcp
#   or:  pip install "git+https://github.com/malcolmsullivan/vaxt@v0.1.0#subdirectory=packages/vaxt" && python -m vaxt_mcp
```

`_resolve_db_path()` falls back env → workspace → cwd → **bundled package copy**,
logging which source it used; `VAXT_REQUIRE_DB=1` refuses the bundled snapshot so a
stale wheel can never silently answer in place of a live warehouse.

---

## Install as a Claude Code plugin

The sixth surface — a **distribution/install surface over the existing MCP capability**,
with grounding **enforced by the plugin's own Stop hook** (not a new data capability).
In a fresh Claude Code session:

```bash
/plugin marketplace add malcolmsullivan/vaxt
/plugin install vaxt@vaxt
# then, in the session:
/vaxt Which heritage varieties suit a USDA zone 3 winter-wheat grower?
```

You get a grounded, cited answer — and a **machine-verified** one: a `Stop` hook
(`hooks/verify_citations.py`) resolves every `[table:key]` in the answer against
DuckDB with no model call and surfaces a verdict (`VAXT grounding ✓ 3/3 citations
resolve`), flagging any fabricated citation. The plugin bundles:

- the **MCP server** (21 read-only tools) + **`vaxt_verify_citation`**, a
  deterministic citation-check tool;
- the **`vaxt-grounding` skill** — the answer-in-prose, cite-`[table:key]`,
  refuse-with-`[[REFUSED]]` contract (derived from the agent's canonical prompt);
- the **`/vaxt`** command and the enforcing **Stop hook** above.

Requires `uv` on PATH (Claude Code does not bootstrap it). See
[`INTERVIEW-DEMO.md`](INTERVIEW-DEMO.md) for the pre-warmed live-demo runbook.

---

## MCP tools (21 read-only + a citation verifier)

| Group | Tools |
|---|---|
| Diagnostics | `vaxt_health_check` |
| Variety intelligence | `vaxt_search_varieties` · `vaxt_get_variety` · `vaxt_match_varieties` · `vaxt_compare_varieties` |
| Climate & growing | `vaxt_get_growing_season` · `vaxt_get_climate_profile` · `vaxt_get_planting_calendar` |
| Genomics & breeding | `vaxt_search_markers` · `vaxt_search_qtl` · `vaxt_get_breeding_program` |
| Culture & sources | `vaxt_search_sourdough` · `vaxt_search_seed_sources` |
| Disease & pathogens | `vaxt_get_disease_resistance` · `vaxt_search_eppo_pathogens` |
| Horticulture | `vaxt_get_rootstock_compatibility` · `vaxt_get_crop_wild_relatives` |
| Distillery | `vaxt_get_distillery_grain_sources` |
| Community | `vaxt_search_community_projects` |
| Grower's journal | `vaxt_get_journal_entries` |
| Cross-reference | `vaxt_cross_reference` |
| Grounding | `vaxt_verify_citation` *(the 22nd registered tool; not counted among the 21 data-read tools)* |

Each data tool returns structured JSON with a **`records`** array — every record
tagged with its `(table, key)` — so a plain MCP client can cite `[table:key]` and
check it. Tools degrade gracefully (clear `{"error": ...}` payloads, empty-result
notes that tell you which pipeline to run). `vaxt_verify_citation(table, key)`
resolves a citation against DuckDB with no model call — the grounding primitive the
plugin's Stop hook and any self-checking session use.

---

## BrAPI v2.1 endpoint

A fourth surface: a read-only **[BrAPI v2.1](https://brapi.org)** server (`packages/vaxt-api/`, FastAPI)
makes VAXT consumable by standard breeding tools (BMS, Breedbase, Field Book), not just Claude and the
website.

```bash
pip install -e "packages/vaxt-api[dev]"
uvicorn vaxt_api.app:app --reload          # interactive docs at /docs
curl "localhost:8000/brapi/v2/germplasm?commonCropName=wheat&pageSize=5"
```

| Call | Backed by |
|---|---|
| `GET /brapi/v2/serverinfo` | — |
| `GET /brapi/v2/germplasm[/{id}]` | `t3_germplasm` (200) |
| `GET /brapi/v2/studies[/{id}]` | distinct T3 studies (82) |
| `GET /brapi/v2/observationunits` | `t3_observations` |
| `GET /brapi/v2/observations` | `t3_observations` (6 202) |

All list calls page with `page`/`pageSize` and return the standard BrAPI envelope
(`metadata.pagination` + `result.data`). Details in `packages/vaxt-api/README.md`.

---

## The data pipeline

`vaxt_runner.py` orchestrates 9 sources into DuckDB (27 tables). All are public/open-licensed:

| Source | What | Cadence |
|---|---|---|
| FAOSTAT | Crop production 1961–2024 (5 cereals × 14 countries) | bulk download |
| Eurostat | EU crop production (humidity-normalized) | JSON-stat API |
| GHCN | Global daily climate (TMIN/TMAX) | download |
| GrainGenes (USDA) | Cold/frost/winter-survival QTL | scrape |
| T3 / BrAPI | Triticeae Toolbox winterhardiness phenotypes | BrAPI v2 |
| GBIF | Crop-wild-relative occurrences (Nordic/Arctic) | API |
| SoilGrids (ISRIC) | Soil pH/texture/SOC for trial sites | REST |
| growing-season | Frost dates & frost-free days (derived from GHCN) | computed |
| photoperiod | Day length / photoperiod class (from latitude) | computed |

```bash
python scripts/vaxt/vaxt_runner.py --list          # all sources + status
python scripts/vaxt/vaxt_runner.py --dry-run       # plan only
python scripts/vaxt/vaxt_runner.py                 # fetch + load + validate
python scripts/vaxt/vaxt_runner.py --validate-only # gate the existing DB
```

### Original data contributions (no public equivalent)
- **Cold-tolerance marker registry** (`cold_tolerance_markers.csv`) — ~140 molecular markers across 11+
  species (CBF/DREB1, dehydrins, LEA proteins, VRN1-linked frost loci, AFP/ICE regulators).
- **Phenotype schema** (`phenotype_schema.json`) — a 69-field typed JSON Schema standardizing every
  cold-tolerance measurement protocol (LT50, ice encasement, snow mold, DTA, dehardening…).
- **Nordic variety-trait index** (`nordic_variety_trait_index.csv`) — ~200 varieties bridging NordGen /
  GRIN / GrainGenes identifiers.

---

## Testing & CI

```bash
pip install -e "packages/vaxt[dev]" -e "packages/vaxt-api[dev]"
pytest tests/ -v          # MCP + BrAPI, against the committed DuckDB
```

CI (`.github/workflows/ci.yml`) installs both packages and runs both suites (MCP client + BrAPI) against
the **committed** `heritage-grain.duckdb` on Python 3.11. The tests `skip` (rather than error) only if the
DB is ever removed, so a green run means they actually executed.

---

## What broke and how I fixed it

*(Engineering notes — the real value of reading this repo.)*

- **Tests passed by silently skipping.** The MCP client tests `skip` when the DuckDB isn't present. In CI
  that read as "green" while testing nothing. Fix: committed a prebuilt `heritage-grain.duckdb` so the
  suite runs against real data in CI, with `health_check` asserting `tables >= 20` + core tables present —
  a missing or incomplete DB now fails loudly instead of skipping quietly.
- **A 9-source pipeline can't reach a clean state online in CI.** T3/BrAPI alone is a ~20-minute,
  rate-limited crawl, and remote APIs flake. Fix: split *derived/computed* sources (growing-season,
  photoperiod) from *network* sources, committed the curated + derived CSVs so the DB builds offline and
  reproducibly, and kept network ETL behind explicit `--fetch` runs with `--delay` rate-limit controls.
- **Partial loads silently corrupted analytics.** A source that fetched half its rows still "loaded."
  Fix: per-source validation gates in `sources.toml` (row-count bounds, unique-key enforcement, numeric
  range checks) run on every load; `--validate-only` re-gates the DB without re-fetching.

---

## License
Code: **MIT** (`LICENSE`). Data & docs: **CC BY 4.0**. Built under the OpenSauce research program.

## Links
- Live: https://vaxt.bio
- Field guide (CC BY 4.0): *Horticulture Open-Source Genomics* — DOI: `[add Zenodo DOI]`
