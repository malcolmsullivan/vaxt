"""Ask VAXT web service — SSE /chat over the M1-M2 agent core (unchanged).

Run locally:
    pip install -e "packages/vaxt-agent[web]"
    export VAXT_DUCKDB_PATH=data/datasets/heritage-grain/heritage-grain.duckdb
    uvicorn vaxt_agent.web:app          # or: vaxt-web
    # -> http://127.0.0.1:8000/  (UI)   /health   /ready

Failure contract (two channels, because an SSE stream cannot change its HTTP
status once bytes flow):
  * pre-stream, knowable up front:  HTTP 503 JSON — {"code": "no_key"} when
    ANTHROPIC_API_KEY is unset (the honest keyless state, never a fake answer).
  * mid-stream: a terminal `error` SSE event — {"code": "upstream_unavailable"}
    when the model API fails after the SDK's retries, {"code": "internal_error"}
    for anything else. Never a fabricated answer.

Model calls retry (SDK max_retries) with a per-call timeout; tool calls never
retry — they are local deterministic reads whose failures already degrade to
error envelopes in ToolCore. Every DuckDB path here is read_only=True.
"""

import json
import logging
import os
import queue
import threading
import time
from itertools import count
from pathlib import Path

import duckdb
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from vaxt_agent import obs
from vaxt_agent.agent import DEFAULT_MODEL, run_agent
from vaxt_agent.provenance import TABLE_KEY, fetch_citation_row
from vaxt_agent.tools import ToolCore

log = logging.getLogger("vaxt_agent.web")

MODEL_MAX_RETRIES = 3
MODEL_TIMEOUT_S = 60.0
EXPECTED_TABLE_COUNT = 27
_DEFAULT_DB = "data/datasets/heritage-grain/heritage-grain.duckdb"
_INDEX_HTML = Path(__file__).resolve().parents[2] / "web" / "index.html"
_SENTINEL = object()

obs.setup_json_logging()
app = FastAPI(
    title="Ask VAXT",
    description="Grounded, cited Q&A over the VAXT heritage-grain warehouse.",
)


def db_path() -> str:
    return os.environ.get("VAXT_DUCKDB_PATH", _DEFAULT_DB)


# ── observability wrappers (agent core stays untouched) ─────────────────────
class _ObservedToolCore(ToolCore):
    """Times each tool call and logs it with redacted args. No retries."""

    def call(self, tool_name: str, args: dict) -> dict:
        t0 = time.perf_counter()
        env = super().call(tool_name, args)
        obs.log_tool_call(
            tool_name, args, int(env.get("count", 0)),
            (time.perf_counter() - t0) * 1000, env.get("error"),
        )
        return env


class _ObservedMessages:
    def __init__(self, inner):
        self._inner = inner

    def create(self, **kw):
        t0 = time.perf_counter()
        resp = self._inner.create(**kw)
        u = getattr(resp, "usage", None)
        usage = u if isinstance(u, dict) else {
            "input_tokens": getattr(u, "input_tokens", 0) or 0,
            "output_tokens": getattr(u, "output_tokens", 0) or 0,
        }
        obs.log_model_call(kw.get("model", ""), usage, (time.perf_counter() - t0) * 1000)
        return resp


class _ObservedClient:
    def __init__(self, inner):
        self.messages = _ObservedMessages(inner.messages)


def _make_resilient_client():
    import anthropic
    return anthropic.Anthropic(max_retries=MODEL_MAX_RETRIES, timeout=MODEL_TIMEOUT_S)


# ── dependency seams (tests override these; see tests/vaxt-agent/test_web.py) ──
def get_api_key_present() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def get_agent_runner():
    def _run(question: str, model: str | None, on_event):
        core = _ObservedToolCore()
        try:
            return run_agent(
                question,
                anthropic_client=_ObservedClient(_make_resilient_client()),
                toolcore=core,
                model=model,
                on_event=on_event,
            )
        finally:
            core.close()  # run_agent only closes cores it created

    return _run


# ── /chat ────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str
    model: str | None = None


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@app.post("/chat")
def chat(
    req: ChatRequest,
    runner=Depends(get_agent_runner),
    has_key: bool = Depends(get_api_key_present),
):
    # The key check must precede any client construction: a bare Anthropic()
    # raises at construction without a key, which would surface as a mid-stream
    # error instead of this honest pre-stream state.
    if not has_key:
        return JSONResponse(
            status_code=503,
            content={
                "code": "no_key",
                "message": "Set ANTHROPIC_API_KEY to enable answers. "
                           "Tools, BrAPI, and health are unaffected.",
            },
        )

    trace_id = obs.new_trace_id()
    log.info("chat_request", extra={
        "event": "chat_request", "trace_id": trace_id,
        "question_len": len(req.question),  # never the text — may carry a location
        "model": req.model or DEFAULT_MODEL,
    })
    q: queue.Queue = queue.Queue()
    seq = count(1)

    def on_event(tc, env):
        q.put(("status", {
            "tool": tc.tool, "row_count": tc.record_count,
            **({"error": tc.error} if tc.error else {}),
            "trace_id": trace_id, "seq": next(seq),
        }))

    def worker():
        import anthropic
        obs.trace_id_var.set(trace_id)
        try:
            transcript = runner(req.question, req.model, on_event)
            q.put(("answer", transcript.model_dump()))
        except (anthropic.APITimeoutError, anthropic.APIError) as e:
            log.error("model_api_failure", extra={"trace_id": trace_id, "error": str(e)})
            q.put(("error", {
                "code": "upstream_unavailable",
                "message": "the model API is unavailable; no answer was produced",
                "trace_id": trace_id,
            }))
        except Exception as e:
            log.exception("chat_worker_failure", extra={"trace_id": trace_id})
            q.put(("error", {
                "code": "internal_error",
                "message": f"internal error; no answer was produced: {e}",
                "trace_id": trace_id,
            }))
        finally:
            q.put(_SENTINEL)

    threading.Thread(target=worker, daemon=True, name=f"chat-{trace_id}").start()

    def gen():
        # If the client disconnects, the worker still runs to completion and
        # exits via the sentinel — one bounded run, no leak (see ARCHITECTURE).
        while True:
            item = q.get()
            if item is _SENTINEL:
                break
            event, payload = item
            yield _sse(event, payload)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Trace-Id": trace_id},
    )


# ── health / readiness ───────────────────────────────────────────────────────
@app.get("/health")
def health():
    """Process up + DB path resolves + SELECT 1. No model calls."""
    try:
        con = duckdb.connect(db_path(), read_only=True)
        try:
            con.execute("SELECT 1").fetchone()
        finally:
            con.close()
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})
    return {"status": "ok", "db": db_path()}


@app.get("/ready")
def ready():
    """Health + full warehouse present (>= 27 tables). Never pings the model —
    readiness polling must not burn tokens; reachability is a boot-time log."""
    try:
        con = duckdb.connect(db_path(), read_only=True)
        try:
            tables = len(con.execute("SHOW TABLES").fetchall())
        finally:
            con.close()
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not_ready", "error": str(e)})
    if tables < EXPECTED_TABLE_COUNT:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "tables": tables,
                     "expected": EXPECTED_TABLE_COUNT},
        )
    return {"status": "ready", "tables": tables}


# ── citation expansion ───────────────────────────────────────────────────────
@app.get("/citation")
def citation(table: str | None = None, key: str | None = None):
    """The row behind a [table:key] citation chip. Table/keycol come from the
    TABLE_KEY registry only; key is always a bound parameter."""
    if not table or not key:
        raise HTTPException(status_code=400, detail="both 'table' and 'key' are required")
    if table not in TABLE_KEY:
        raise HTTPException(status_code=404, detail=f"unknown table {table!r}")
    con = duckdb.connect(db_path(), read_only=True)
    try:
        row = fetch_citation_row(con, table, key)
    finally:
        con.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no row in {table!r} with key {key!r}")
    return {"table": table, "key": key, "key_column": TABLE_KEY[table], "row": row}


# ── UI ───────────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    if _INDEX_HTML.is_file():
        return FileResponse(_INDEX_HTML, media_type="text/html")
    return JSONResponse({"message": "Ask VAXT API. UI not present; see /docs."})


@app.on_event("startup")
def _boot_check():
    """One-time, logged. Never fatal, never a token spent on /ready."""
    key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    log.info("boot", extra={
        "event": "boot", "db": db_path(), "api_key_present": key,
        "default_model": DEFAULT_MODEL,
        "mode": "live answers enabled" if key else "keyless (tools/health only)",
    })


def main() -> None:
    """Console entry point: `vaxt-web`."""
    import uvicorn
    uvicorn.run(
        "vaxt_agent.web:app",
        host=os.environ.get("VAXT_WEB_HOST", "127.0.0.1"),
        port=int(os.environ.get("VAXT_WEB_PORT", "8000")),
    )
