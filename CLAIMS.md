# CLAIMS — every VAXT claim mapped to verified reality

This repo is used as engineering evidence. This file exists so that every
quantitative or capability claim in the README (and in any résumé/portfolio
description of VAXT) can be checked against the code and data on demand, with
zero gap between what is said and what is true.

**Verification method (2026-07-05, plugin surface added):** read the source
directly; ran read-only DuckDB queries against the committed warehouse
(`data/datasets/heritage-grain/heritage-grain.duckdb`); ran the full test suite
(`pytest tests/` → **135 passed** with the warehouse present, after the plugin
surface); ran the keyless eval both locally and in the container
(`eval/run_eval.py --mode replay` and `docker compose run --rm eval` → **17/17**);
built the `vaxt-mcp` wheel and confirmed the warehouse is bundled inside it; and ran
the **clean-environment turnkey test on Windows** — a fresh venv with only the wheel
(no repo checkout, no env vars) resolved `db_source=bundled` (27 tables) and
`VAXT_REQUIRE_DB=1` refused the bundled fallback (see §9). `claude plugin validate ./`
passes and the Stop hook flags a fabricated `[table:key]` on a synthetic transcript.
Figures below are from that snapshot.

Legend: ✅ true · ➖ true but imprecise / worth restating · 🔧 was wrong, fixed in this pass.

---

## 1. Platform figures

| Claim | Verified reality | Status |
|---|---|---|
| MCP server exposes **21 read-only data tools** (+ a grounding tool) | `server.py` registers **21** data-read `@mcp.tool()` functions **plus `vaxt_verify_citation`** (a deterministic citation check), so `mcp.list_tools()` returns **22**. The agent still runs over the **21** data tools (`vaxt_verify_citation` is filtered out of `all_tool_schemas`); asserted by `tests/vaxt-mcp/unit/test_server.py`. | ✅ (21 data + 1 grounding) |
| Warehouse has **27 tables** | `information_schema.tables` (main schema, base tables) = **27**. | ✅ |
| **62 tests** | Was 62 originally. **86** after the M0 truth pass, **93** after M1 (agent + provenance), **123** after M3 (web-service tests), **135** after the plugin surface (2 server provenance/verify tests + 5 bundled-resolution tests + 5 plugin/hook tests). | ✅ (superseded upward) |
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
| Provenance lives in the data tier | `enrich`/`resolve_citation`/`fetch_citation_row`/`TABLE_KEY` are in `vaxt_mcp.provenance`; the server's data tools emit `(table, key)` records and the agent/eval/web import the same module — one definition, so no consumer can disagree. A conformance test asserts the two agent transports still agree. | ✅ |

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

## 4. Claim discipline (what is and isn't claimed)

- **"Full-stack" — now claimed truthfully, as of M3–M5.** Through M2 there was no
  front-end, so the README made no full-stack claim. M3–M5 add an HTTP `/chat`
  service, a thin web UI, and a container (see §8) — so a front-end, an endpoint,
  and a deployment artifact now exist. The claim is made only because all three
  are real and verified, not as aspiration.
- No "9-API" claim (the ETL touches 7 external APIs/downloads + 2 derived sources).
- No "CI builds a real database" claim — the README states the DB is *committed*.
- **The plugin (§9) is claimed as an install/distribution surface over the existing
  MCP capability, not a new data capability.** Its "grounded, cited" claim is honest
  because the plugin ships the deterministic verifier (`vaxt_verify_citation` + the
  Stop hook), not just a citation *format* — a fabricated `[table:key]` is flagged in
  code the plugin owns. The claim was written only after the clean-environment
  turnkey test was executed and observed (§9), not as aspiration.
- **`uv`/Python are a stated prerequisite, not bootstrapped.** Claude Code does not
  install `uv`; the plugin's MCP server and Stop hook both require `uv` on PATH.
  "Turnkey" means zero *data/config* setup, not zero runtime.

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

---

## 8. Ask VAXT web service (M3–M5)

| Claim | Verified reality | Status |
|---|---|---|
| There is an HTTP `/chat` service | `packages/vaxt-agent/src/vaxt_agent/web.py` (FastAPI). `POST /chat` streams SSE — `status` events per tool call (from the agent's `on_event` hook, run in a worker thread) then a final `answer` event carrying the serialized `Transcript`. Reuses the M1–M2 `run_agent` core unchanged. | ✅ |
| There is a web front-end | `packages/vaxt-agent/web/index.html` — one self-contained file (vanilla JS, inline CSS/JS, no build step, no external assets), served by `web.py`. Streams `/chat` and renders the answer with citation chips. Verified in a browser. | ✅ |
| Citation chips resolve to real rows | Clicking a chip calls `GET /citation?table=&key=`, which uses `provenance.fetch_citation_row` (same `TABLE_KEY` registry and `≥1-row` match as `resolve_citation`) and renders the row. Verified live against `varieties:Norstar`. | ✅ |
| Keyless state is honest, never fabricated | With no `ANTHROPIC_API_KEY`, `/chat` returns a pre-stream **503 `{"code":"no_key"}`** and the UI shows tools/health/citations live plus a "set the key" message. No path emits a fabricated answer (an `answer` event only carries a real `Transcript`). Verified in browser and via `curl`. | ✅ |
| Model failure degrades honestly | Model API failure after SDK retries → a terminal SSE `error` event (`upstream_unavailable`), never an answer. Covered by `test_chat_model_failure_becomes_error_event`. | ✅ |
| `/health` and `/ready` exist on both servers | `web.py` and `vaxt-api/app.py` both expose `/health` (process + DB + `SELECT 1`) and `/ready` (`SHOW TABLES` ≥ 27, no model call). Covered by `test_web.py` and `test_health.py`. | ✅ |
| Observability | `obs.py`: JSON logging, per-request `trace_id`, tool-call logs with location-bearing args (`lat`/`lon`/`location`/`station`) redacted, model-call logs with token counts and an **estimated** `est_cost_usd` (static price table; unknown model → `null` + warning). The question is logged by length only, never as text. | ✅ |
| Container + keyless proof | `Dockerfile` (python:3.11-slim, DuckDB baked in read-only) + `compose.yaml`. `docker compose run --rm eval` runs the keyless replay eval (17/17) with no API key; `docker compose up` serves the UI + health. | ✅ |

**Honest caveats:** `est_cost_usd` is an estimate from a static list-price table
(currently sonnet-5's introductory rate, which reverts 2026-09-01), explicitly
labeled as an estimate — not billing truth. The service is a single-user demo:
each `/chat` stream holds one thread, so concurrency is bounded by the ASGI
threadpool (documented in `ARCHITECTURE.md`, not hidden). The live agent still has
normal run-to-run model variance; the deterministic keyless eval, not the live
answer, is the reproducible proof.

---

## 9. Installable Claude Code plugin (the sixth surface)

| Claim | Verified reality | Status |
|---|---|---|
| VAXT installs as a Claude Code plugin | `.claude-plugin/marketplace.json` + `plugin.json` (plugin source `"./"`); `claude plugin validate ./` passes. Install flow: `/plugin marketplace add malcolmsullivan/vaxt` → `/plugin install vaxt@vaxt`. | ✅ |
| It is a **distribution surface over the existing MCP capability**, not new data | The plugin declares the same 22-tool MCP server via `uvx --from ${CLAUDE_PLUGIN_ROOT}/packages/vaxt vaxt-mcp` (pinned to the installed plugin, never a floating remote). Verified: `uvx` builds the local package (bundling the DB) and the server speaks MCP. | ✅ |
| The server is turnkey off-repo | The `vaxt-mcp` wheel bundles the 8.76 MiB warehouse (build hook + `WAREHOUSE.json` fingerprint: sha256, 27 tables, real row counts). **Clean-environment test (Windows):** fresh venv, only the wheel, no repo checkout, no env vars → `db_source=bundled`, 27 tables; `VAXT_REQUIRE_DB=1` refuses the bundled fallback (fail-loud). Also proven in CI (`wheel-build` job: build + assert DB inside + clean-env smoke). | ✅ |
| Grounding is **enforced**, not just formatted | The `vaxt-grounding` skill carries the cite-`[table:key]` / `[[REFUSED]]` contract (derived from the canonical `SYSTEM_PROMPT`; a test guards drift), AND the plugin ships the verifier: `vaxt_verify_citation` (an MCP tool) + a **Stop hook** (`hooks/verify_citations.py`) that resolves every `[table:key]` in the final answer against DuckDB via the same `resolve_citation` — surfacing `VAXT grounding ✓ N/N` or flagging a fabricated key. So the plugin carries VAXT's guarantee, not just its citation style. | ✅ |
| The hook is safe and honest | Flag-and-surface only: it always exits 0 (never blocks/loops), stays silent on non-VAXT turns, and **fails soft-to-neutral** — a raw-tail fallback handles transcript-format drift, and it never prints a ✓ it did not earn. Verified against synthetic transcripts (real + fabricated citations, refusal, non-VAXT) by `tests/plugin/test_plugin.py`. | ✅ |

**Honest caveats:** the plugin's MCP server and Stop hook both require **`uv` and
Python 3.11+ on PATH** — Claude Code does not bootstrap them; "turnkey" is about
data/config, not runtime. The bundled warehouse is a **frozen snapshot** (identified
by the `WAREHOUSE.json` sha256), not a live feed — the fingerprint makes a stale
wheel self-evident, and `VAXT_REQUIRE_DB=1` refuses it. The Stop hook reads the
Claude Code transcript, whose format is internal and can change between versions; on
any parse failure it degrades to a neutral message (never a false ✓) rather than a
verified verdict.
