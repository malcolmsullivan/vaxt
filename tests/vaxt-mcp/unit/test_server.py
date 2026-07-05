"""Smoke tests for the MCP server layer (the async @mcp.tool wrappers).

The client tests exercise VaxtClient directly; these drive the 21 registered
FastMCP tools end to end — argument handling, the JSON envelope, and the
graceful error envelope — which the client tests never touch.
"""

import asyncio
import json
import os

import pytest

from vaxt_mcp.client import _resolve_db_path
from vaxt_mcp.server import mcp

pytestmark = pytest.mark.skipif(
    not os.path.exists(_resolve_db_path()),
    reason=f"DuckDB not available at {_resolve_db_path()}",
)

# 21 read-only data tools + 1 grounding tool (vaxt_verify_citation).
EXPECTED_DATA_TOOL_COUNT = 21
EXPECTED_TOOL_COUNT = 22
_NON_DATA_TOOLS = {"vaxt_verify_citation"}


def _call_tool(name: str, args: dict) -> str:
    """Invoke a registered FastMCP tool and return its text (JSON) payload."""
    out = asyncio.run(mcp.call_tool(name, args))
    content = out[0] if isinstance(out, tuple) else out
    return content[0].text


def test_all_tools_registered():
    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == EXPECTED_TOOL_COUNT
    names = {t.name for t in tools}
    assert all(n.startswith("vaxt_") for n in names)
    # Exactly 21 data-read tools; the verifier is the one non-data tool.
    assert len(names - _NON_DATA_TOOLS) == EXPECTED_DATA_TOOL_COUNT
    assert "vaxt_verify_citation" in names
    # A representative slice, including the two tools whose latent crashes the
    # client tests surfaced.
    assert {"vaxt_health_check", "vaxt_search_varieties", "vaxt_search_qtl",
            "vaxt_match_varieties", "vaxt_cross_reference"} <= names


def test_health_check_wrapper():
    payload = json.loads(_call_tool("vaxt_health_check", {}))
    assert payload["status"] == "ok"
    assert payload["tables"] >= 27


def test_search_varieties_wrapper_envelope():
    payload = json.loads(_call_tool("vaxt_search_varieties", {"crop": "wheat", "limit": 5}))
    assert payload["count"] > 0
    assert len(payload["varieties"]) <= 5
    assert all("wheat" in v["crop"].lower() for v in payload["varieties"])


def test_search_qtl_wrapper_does_not_crash():
    # Regression guard: search_qtl referenced a nonexistent column and always threw.
    payload = json.loads(_call_tool("vaxt_search_qtl", {"species": "Hordeum", "limit": 5}))
    assert payload["count"] > 0
    assert len(payload["qtl"]) <= 5


def test_missing_variety_returns_error_envelope():
    # Wrapper must degrade to a structured envelope, never raise.
    payload = json.loads(_call_tool("vaxt_get_variety", {"name": "DoesNotExist12345"}))
    assert payload.get("error") is True
    assert "message" in payload


def test_data_tool_emits_provenance_records():
    # The server attaches machine-checkable (table, key) records so a plain MCP
    # client can cite [table:key] without inferring it.
    payload = json.loads(_call_tool("vaxt_search_varieties", {"crop": "wheat", "limit": 5}))
    assert "records" in payload
    assert payload["records"], "expected at least one provenance record"
    for rec in payload["records"]:
        assert rec["table"] == "varieties"
        assert set(rec) >= {"table", "key", "key_column", "fields"}


def test_verify_citation_resolves_real_and_rejects_fabricated():
    real = json.loads(_call_tool("vaxt_verify_citation", {"table": "varieties", "key": "Norstar"}))
    assert real["resolved"] is True
    assert real["row"] is not None

    fake = json.loads(_call_tool("vaxt_verify_citation", {"table": "varieties", "key": "NoSuchVariety_XYZ"}))
    assert fake["resolved"] is False
    assert fake["row"] is None

    untracked = json.loads(_call_tool("vaxt_verify_citation", {"table": "not_a_table", "key": "x"}))
    assert untracked["resolved"] is False
