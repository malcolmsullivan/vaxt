"""Web-service tests — no API key, no tokens spent.

/chat is exercised through an injected fake runner (FastAPI dependency_overrides),
so the SSE event shape is asserted without ever calling the model. /health, /ready,
and /citation run against the committed DuckDB.
"""
import json
import os

import pytest

from vaxt_agent.schemas import Citation, ToolCall, Transcript
from vaxt_agent.web import (
    app,
    db_path,
    get_agent_runner,
    get_api_key_present,
)

pytestmark = pytest.mark.skipif(not os.path.exists(db_path()), reason="DuckDB not available")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _parse_sse(text: str):
    """Return [(event, data_dict), ...] from an SSE response body."""
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
        events.append((event, data))
    return events


# ── health / ready ───────────────────────────────────────────────────────────
def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_counts_tables(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["tables"] >= 27


# ── /citation ─────────────────────────────────────────────────────────────────
def test_citation_resolves_real_row(client):
    r = client.get("/citation", params={"table": "varieties", "key": "Norstar"})
    assert r.status_code == 200
    body = r.json()
    assert body["table"] == "varieties"
    assert body["key_column"] == "variety"
    assert isinstance(body["row"], dict) and body["row"]


def test_citation_missing_params_is_400(client):
    assert client.get("/citation", params={"table": "varieties"}).status_code == 400


def test_citation_unknown_table_is_404(client):
    r = client.get("/citation", params={"table": "not_a_table", "key": "x"})
    assert r.status_code == 404


def test_citation_no_row_is_404(client):
    r = client.get("/citation", params={"table": "varieties", "key": "no-such-variety-zzz"})
    assert r.status_code == 404


# ── /chat: keyless 503 ────────────────────────────────────────────────────────
def test_chat_no_key_returns_503(client):
    app.dependency_overrides[get_api_key_present] = lambda: False
    r = client.post("/chat", json={"question": "anything"})
    assert r.status_code == 503
    assert r.json()["code"] == "no_key"


# ── /chat: SSE shape via a fake runner (no tokens) ────────────────────────────
def test_chat_streams_status_then_answer(client):
    def fake_runner(question, model, on_event):
        on_event(ToolCall(tool="vaxt_search_varieties", arguments={}, record_count=3), {})
        on_event(ToolCall(tool="vaxt_get_variety", arguments={}, record_count=1), {})
        return Transcript(
            question=question,
            answer="Norstar is a winter wheat.",
            citations=[Citation(table="varieties", key="Norstar")],
            tool_calls=[ToolCall(tool="vaxt_get_variety", record_count=1)],
            model="stub-model",
            usage={"input_tokens": 10, "output_tokens": 5},
        )

    app.dependency_overrides[get_api_key_present] = lambda: True
    app.dependency_overrides[get_agent_runner] = lambda: fake_runner

    r = client.post("/chat", json={"question": "about Norstar"})
    assert r.status_code == 200
    events = _parse_sse(r.text)

    kinds = [e for e, _ in events]
    assert kinds == ["status", "status", "answer"]

    (_, s1), (_, s2), (_, ans) = events
    assert s1["tool"] == "vaxt_search_varieties" and s1["row_count"] == 3
    assert s1["seq"] == 1 and s2["seq"] == 2
    assert ans["answer"] == "Norstar is a winter wheat."
    assert ans["citations"] == [{"table": "varieties", "key": "Norstar"}]


def test_chat_model_failure_becomes_error_event(client):
    def failing_runner(question, model, on_event):
        import anthropic
        raise anthropic.APIError("boom", request=None, body=None)

    app.dependency_overrides[get_api_key_present] = lambda: True
    app.dependency_overrides[get_agent_runner] = lambda: failing_runner

    r = client.post("/chat", json={"question": "x"})
    assert r.status_code == 200  # stream opened before the failure
    events = _parse_sse(r.text)
    assert [e for e, _ in events] == ["error"]
    assert events[0][1]["code"] == "upstream_unavailable"
