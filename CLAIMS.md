# CLAIMS — every VAXT claim mapped to verified reality

This repo is used as engineering evidence. This file exists so that every
quantitative or capability claim in the README (and in any résumé/portfolio
description of VAXT) can be checked against the code and data on demand, with
zero gap between what is said and what is true.

**Verification method (2026-07-04):** read the source directly; ran read-only
DuckDB queries against the committed warehouse
(`data/datasets/heritage-grain/heritage-grain.duckdb`); ran the full test suite
(`pytest tests/` → **86 passed** with the warehouse present). Figures below are
from that snapshot.

Legend: ✅ true · ➖ true but imprecise / worth restating · 🔧 was wrong, fixed in this pass.

---

## 1. Platform figures

| Claim | Verified reality | Status |
|---|---|---|
| MCP server exposes **21 tools** | `packages/vaxt/src/vaxt_mcp/server.py` registers exactly 21 `@mcp.tool()` functions; `mcp.list_tools()` returns 21. | ✅ |
| Warehouse has **27 tables** | `information_schema.tables` (main schema, base tables) = **27**. | ✅ |
| **62 tests** | Was 62 before this pass. Now **86** (added 18 tests for 6 previously-untested tools, 5 MCP-server smoke tests, 1 warehouse guard). | ✅ (superseded upward) |
| **3 validation gates** in the ETL | `scripts/vaxt/vaxt_runner.py`: (1) required columns, (2) external validator subprocess, (3) inline `min/max_rows` + `unique_key` + `numeric_bounds` + `required_values`. | ✅ |
| CI runs against a **real** DuckDB | `.github/workflows/ci.yml` runs `pytest` against the **committed** warehouse. It does **not** build the DB in CI (and does not claim to). | ✅ |
| BrAPI: **200 germplasm / 82 studies / 6202 observations** | `t3_germplasm` = 200; distinct `study_db_id` in `t3_observations` = 82; `t3_observations` = 6202. Asserted in `tests/vaxt-api/test_brapi.py`. | ✅ |
| **"9 public data sources → DuckDB"** | `scripts/vaxt/sources.toml` declares **29 sources** (18 bundled static CSVs + 11 ETL sources). The 11 ETL sources are driven by **9 scripts** (7 hit external APIs/downloads + 2 are derived: `growing_season`, `photoperiod`). The committed warehouse holds 27 tables — the 2 GHCN network tables are not committed; the derived `growing_season` is. So "9 sources" is the **ETL-script count** and *under*-states the 29 declared sources. | ➖ restate as "29-source manifest; 9 ETL scripts (7 external + 2 derived)" |
| **"~200 varieties"** | `varieties` = **280 rows**. Undercount, not overcount. | ➖ say ~280 |
| **"~140 molecular markers across 11+ species"** | `markers` = **140 rows**, **22** distinct `species` values (≥11 holds). | ✅ (species count conservative) |
| **"69-field phenotype schema"** | `phenotype_records` has **71 columns**; excluding `record_id` and `notes` leaves 69 phenotype fields — consistent with a 69-field count. Within tolerance, not a material over-claim. | ➖ |
| README: *"health_check asserting tables >= 20"* | The `tables >= 20` assertion lives in the **test** (`tests/vaxt-mcp/unit/test_client.py`), not inside `health_check()` — the function only returns counts. | ➖ phrasing |

---

## 2. Capability / architecture claims

| Claim | Verified reality | Status |
|---|---|---|
| Read-only over DuckDB | Every connection is `duckdb.connect(..., read_only=True)` (`client.py`, `vaxt_api/db.py`). No write/DDL/DML path exists. | ✅ |
| Parameterized SQL | All user input is bound via `?` placeholders; WHERE/LIMIT templates are code-controlled, no user value is f-string-interpolated into SQL. | ✅ |
| Official MCP FastMCP SDK | `from mcp.server.fastmcp import FastMCP` (`mcp[cli]>=1.0`). | ✅ |
| Graceful error envelopes | Each tool wrapper returns a structured `{"error": true, "message": ...}` on failure rather than raising (now covered by `tests/vaxt-mcp/unit/test_server.py`). | ✅ |

---

## 3. Bugs found and fixed while covering the 6 untested tools (this pass)

Writing tests for the previously-untested tools surfaced two advertised tools
that **crashed on their documented usage** — invisible precisely because they
had no test.

| Tool | Defect | Fix |
|---|---|---|
| `search_qtl` | `ORDER BY species, trait_name` (and a `trait_name` filter) referenced a column that does not exist — the real column is `trait`. **Every call threw `BinderException`.** | 🔧 `trait_name` → `trait` (`client.py`). Now covered by `TestSearchQtl` + a server smoke test. |
| `match_varieties` (lat/lon path) | The nearest-station query used `AVG(...)` alongside non-aggregated columns with no `GROUP BY`; DuckDB rejects it, so **coordinate-based matching always threw.** | 🔧 rewrote to select the nearest single station's `annual_min_tmin_c` (`client.py`). Now covered by `TestMatchVarieties::test_by_coords_estimates_zone`. |
| `match_varieties` return type | Annotated `-> list[dict]` but returns a `dict` (or `[]` when nothing to match on). | 🔧 annotation → `-> dict | list`, with a docstring stating both shapes. |

---

## 4. Over-claims the code does NOT make (verified absent — a positive)

An earlier audit flagged these as things to check for. They are **not present**
in the README, so there is nothing to retract:

- No "full-stack" claim (there is no front-end in this repo — and none is claimed).
- No "9-API" claim (the ETL touches 7 external APIs/downloads + 2 derived sources).
- No "CI builds a real database" claim — the README states the DB is *committed*.

---

## 5. Known data-quality and usability notes (honest caveats)

- **Non-unique natural keys:** `varieties` has one duplicate name (**"Aurora"**, 2 rows; `(variety, crop)` is unique). `eppo_pathogens` has two duplicated codes (**CLAVPU**, **GIBBZE**). `markers` has no single unique key. Downstream grounding ("Ask VAXT", M1+) therefore treats a citation as valid when it resolves to **≥1** matching row, which still makes a fabricated key a hard failure.
- **`search_qtl(species=...)` expects a binomial**, not a common name — `graingenes_qtl.species` holds e.g. `"Hordeum vulgare"`, `"Triticum aestivum"`, so `species="barley"` returns 0 while `species="Hordeum"` returns rows. The tool docstring's "wheat, barley, rye, oat" examples are misleading.
- **`get_breeding_program` IDs are `BP001`…`BP083`**, and institutions are global (IRRI, CIMMYT, ICRISAT, …). The server docstring example (`"PROG-001"`, `"Graminor"`) does not match the data.

---

## 6. Git history and identity

- Author on all recent commits is `Malcolm Sullivan <malcolmjsullivan2000@gmail.com>`. No `Co-Authored-By` trailers.
- One commit **subject** (`608cc65`) still references an internal codename, "Ralph" ("remove … Ralph-loop orchestration script"). "Ralph"/"Ralph loop" is a **public agentic-coding technique name**, not a private project codename, and the script itself was removed. Per policy, commit history is **not** rewritten to erase it; it is documented here as historical and low-risk.

---

## 7. Ask VAXT (agent + eval)

| Claim | Verified reality | Status |
|---|---|---|
| Ask VAXT is a real Claude agent over the 21 tools | `packages/vaxt-agent/` runs a manual tool-use loop (Anthropic SDK) over the 21 tools, default model `claude-sonnet-5` (env `VAXT_AGENT_MODEL`). Validated live: grounded answers + refusals. | ✅ |
| Answers are grounded and cited | The agent answers in prose with inline `[table:key]` citations; each is a real warehouse row. | ✅ |
| Every citation is checkable | A citation is `(table, key)`, resolved against DuckDB with **no model call** — a fabricated key returns 0 rows and fails. Resolution = ≥1 matching row (see §5 on non-unique keys). | ✅ |
| It refuses when it can't answer | Out-of-scope questions get an explicit `[[REFUSED]]` with zero citations (5/5 refusal cases pass). | ✅ |
| Two transports agree | The agent's tools run either in-process (`ToolCore`) or through the live MCP server (`mcp.call_tool`); a conformance test asserts both emit identical provenance. | ✅ |
| The eval gate is real and keyless | `eval/run_eval.py --mode replay` grades **17 committed transcripts** (12 answerable + 5 refusal) against the warehouse with **no API key**; it fails loud on any missing transcript or failed check. Runs in CI (`eval-replay`) on every PR. Currently **17/17**. | ✅ |
| Live eval | `--mode live` re-runs the agent and adds a semantic judge on `claude-opus-4-8` (a different model than the agent). CI job `eval-live` is manual (`workflow_dispatch`), API-gated, and asserts the key is present. | ✅ |

**Honest caveat:** the committed transcripts are verified, passing reference
outputs. The *live* agent is not 100% contract-perfect run to run (normal model
variance — e.g. occasionally answering in prose without a citation); `eval-replay`
is the deterministic gate over frozen outputs, and `eval-live` measures the live
agent when you choose to run it.

**Full-stack is still NOT claimed:** there is no web front-end, HTTP endpoint, or
container in this repo (milestones M3–M5). "Ask VAXT" is a CLI + library + eval —
a frontier-model, grounded, tested system, not a full-stack app.
