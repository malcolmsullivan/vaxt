"""Provenance conformance against the real warehouse (no API key needed).

If any of these fail, a citation could silently point at a column that no longer
exists, or the two transports could disagree — either of which would quietly
break grounding. These run in CI on every PR.
"""

import os

import duckdb
import pytest

from vaxt_mcp.client import _resolve_db_path
from vaxt_agent import provenance
from vaxt_agent.mcp_transport import MCPTransport
from vaxt_agent.tools import ToolCore

pytestmark = pytest.mark.skipif(
    not os.path.exists(_resolve_db_path()),
    reason=f"DuckDB not available at {_resolve_db_path()}",
)

# Queries spanning flat, single, and composite tool shapes.
SAMPLE_CALLS = [
    ("vaxt_search_varieties", {"crop": "wheat", "limit": 5}),
    ("vaxt_get_variety", {"name": "Norstar"}),
    ("vaxt_match_varieties", {"zone": "3"}),
    ("vaxt_compare_varieties", {"names": "Norstar,Goodland"}),
    ("vaxt_get_growing_season", {"country": "Sweden", "limit": 5}),
    ("vaxt_get_climate_profile", {"zone": "3"}),
    ("vaxt_search_markers", {"species": "wheat", "limit": 5}),
    ("vaxt_search_qtl", {"species": "Hordeum", "limit": 5}),
    ("vaxt_get_breeding_program", {"program_id": "BP001"}),
    ("vaxt_search_eppo_pathogens", {"limit": 5}),
    ("vaxt_cross_reference", {"variety": "Norstar"}),
]


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(_resolve_db_path(), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def core():
    c = ToolCore()
    yield c
    c.close()


def test_registry_columns_exist(con):
    """Every TABLE_KEY column exists in its table — the registry can't drift."""
    for table, keycol in provenance.TABLE_KEY.items():
        cols = [r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='main' AND table_name=?", [table],
        ).fetchall()]
        assert cols, f"table {table!r} missing from warehouse"
        assert keycol in cols, f"{table}.{keycol} (registry key) not in columns {cols}"


def test_resolve_real_vs_fabricated(con):
    assert provenance.resolve_citation(con, "varieties", "Norstar") is True
    assert provenance.resolve_citation(con, "varieties", "NoSuchVariety_XYZ") is False
    assert provenance.resolve_citation(con, "breeding_programs", "BP001") is True
    assert provenance.resolve_citation(con, "not_a_table", "x") is False


def test_real_tool_output_is_fully_resolvable(con, core):
    """Every keyed record a real query returns must resolve — no phantom keys."""
    for tool, args in SAMPLE_CALLS:
        env = core.call(tool, args)
        assert not env.get("error"), f"{tool} errored: {env.get('error')}"
        for rec in env["records"]:
            if rec["key"] is None:
                continue
            assert provenance.resolve_citation(con, rec["table"], rec["key"]), (
                f"{tool}: citation [{rec['table']}:{rec['key']}] did not resolve"
            )


def test_two_transports_agree_on_provenance(core):
    """Direct and live-MCP transports must emit identical (table, key) sequences."""
    mt = MCPTransport()
    try:
        for tool, args in SAMPLE_CALLS:
            direct = [(r["table"], r["key"]) for r in core.call(tool, args)["records"]]
            mcp = [(r["table"], r["key"]) for r in mt.call(tool, args)["records"]]
            assert direct == mcp, f"{tool}: transport provenance mismatch"
    finally:
        mt.close()
