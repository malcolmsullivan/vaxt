# Architecture — Ask VAXT

Ask VAXT answers breeder/grower questions over the 27-table heritage-grain
warehouse with a hard grounding contract: every factual sentence cites the
warehouse row it came from, and if the warehouse can't answer, the agent refuses
instead of guessing. This document covers the runtime data flow, the failure
model, and the deliberate limits.

## Data flow

```
  Browser (static index.html)          vaxt_agent.web  (FastAPI)
  ─────────────────────────            ────────────────────────
  fetch POST /chat  ──HTTP/SSE──▶  POST /chat
    renders tool activity live         ├─ no ANTHROPIC_API_KEY → 503 {"code":"no_key"}   (pre-stream)
    then the answer + citation chips   └─ else: spawn worker thread ─┐
  chip click → GET /citation                                        │  status/answer/error
    → expands the cited row            GET /health  GET /ready       │  events over queue.Queue
                                       GET /citation                 ▼
                                                          run_agent(on_event=push)   ← M1-M2 core, unchanged
                                                                     │
                                                                     ▼
                                                       ToolCore → VaxtClient → DuckDB (27 tables, read-only)
```

- **`POST /chat` (SSE).** Body `{question, model?}`. The synchronous, blocking
  `run_agent` runs in a **worker thread**; its per-tool-call `on_event` hook
  pushes `status` events onto a `queue.Queue`, and the final `Transcript` is
  pushed as an `answer` event. The endpoint is a sync generator that drains the
  queue and yields SSE frames until a sentinel closes the stream. This is the
  simplest bridge from a blocking producer to a streaming HTTP response — a
  stall shows up as a paused stream, not a frozen spinner.
  - `event: status` → `{tool, row_count, seq, trace_id}` — one per tool call.
  - `event: answer` → the serialized `Transcript` (answer, citations, tool_calls,
    usage, model, refused).
  - `event: error` → `{code, message, trace_id}` — a terminal failure (see below).
- **`GET /health`** = process up + DB path resolves + `SELECT 1`.
  **`GET /ready`** = health + `SHOW TABLES` count ≥ 27. Neither pings the model —
  readiness polling must not burn tokens; model reachability is a one-time boot
  check, logged.
- **`GET /citation?table=&key=`** resolves a `[table:key]` citation to its row via
  `provenance.fetch_citation_row`, which shares the `TABLE_KEY` registry and the
  case-insensitive `≥1-row` match with `resolve_citation` — so what the UI shows
  can never disagree with what the grader checks. Table and key column come from
  the registry only; the key is always a bound parameter.
- **The agent core is untouched.** `web.py` injects a configured Anthropic client
  and an observability-wrapping `ToolCore` into the same `run_agent` the CLI and
  eval use. The demo path and the eval path cannot diverge in how a tool behaves.

## Failure model — never a fabricated answer

The grounding contract extends to failures. There are exactly two honest failure
channels, because an SSE stream cannot change its HTTP status once bytes flow:

| When | Channel | Shape |
|---|---|---|
| No API key (known up front) | pre-stream **HTTP 503** | `{"code": "no_key"}` — tools/health/citations stay live |
| Model API fails after retries | in-stream terminal **`error` event** | `{"code": "upstream_unavailable"}` |
| Any other worker exception | in-stream terminal **`error` event** | `{"code": "internal_error"}` |

No path emits a fabricated answer: an `answer` event only ever carries a real
`Transcript`. Model calls retry (the SDK's `max_retries`) with a per-call timeout;
**tool calls never retry** — they are local, deterministic reads whose failures
already degrade to an error envelope inside `ToolCore`, so a retry would only
repeat a deterministic failure.

## Observability

Stdlib `logging` with a JSON formatter (no logging dependency). Each request
carries a `trace_id`. Per tool call: `{tool, args_redacted, row_count,
latency_ms}`. Per model call: `{model, input_tokens, output_tokens, latency_ms,
est_cost_usd}`. Location-bearing tool args (`lat`, `lon`, `location`, `station`)
are redacted — a grower's question can carry their farm's coordinates — and the
question itself is logged by length only, never as text. `est_cost_usd` is an
estimate from a static price table (an unknown model logs a warning and reports
`null` rather than guessing); it is not billing truth.

`vaxt-api` (the BrAPI server) gets the same `/health`, `/ready`, and JSON request
logging, via its own ~40-line formatter. It deliberately does **not** depend on
`vaxt-agent` — inverting that dependency would drag the whole agent stack
(`anthropic`, `mcp`) into the BrAPI server's install for the sake of a logging
formatter. A ~40-line duplication is cheaper than a wrong dependency edge.

## Deliberate limits (chosen, not overlooked)

- **Concurrency ceiling.** Each in-flight `/chat` holds one thread while it
  streams, so concurrent streams are bounded by the ASGI threadpool (~40 by
  default). Right for a single-user demo; a high-concurrency deployment would
  move to an async agent loop or a worker pool.
- **Client disconnect.** If the browser drops mid-answer, the worker still runs
  `run_agent` to completion and exits via the sentinel — one bounded run, no
  leak. A production build would pass a cancellation signal into the loop.
- **DuckDB is read-only everywhere.** Every connection — `/chat`'s `ToolCore`,
  `/citation`, `/health`, `/ready`, and the BrAPI server — opens
  `read_only=True`. Multiple read-only readers are safe; no path opens a
  writable connection, which would break the others.
- **The DuckDB is baked into the container** (read-only, 8.76 MiB) rather than
  mounted, so a clean clone starts with no volume wiring.

## Packaging

`fastapi` + `uvicorn[standard]` are a `[web]` extra on `vaxt-agent`, not base
dependencies. The keyless eval — the reproducible, no-API-key proof that runs in
CI on every PR and in `docker compose run eval` — installs base only and must
stay lean. The container and the `[dev]` test extra pull `[web]`; the eval path
never touches an HTTP library.
