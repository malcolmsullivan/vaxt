"""Anti-"green-CI-while-testing-nothing" guard.

The DB-backed tests skip themselves when the ~8.76 MiB heritage-grain DuckDB is
absent — reasonable on a laptop that hasn't checked out the data. But CI commits
the warehouse and MUST actually exercise it. If a path/cwd regression ever made
the suite skip in CI, every test would go green while asserting nothing.

This guard closes that hole: CI sets ``VAXT_REQUIRE_DB=1``, which turns a missing
or under-populated warehouse into a hard failure instead of a silent skip. It
resolves the path through the client's own logic, so it fails for the same reason
the real tools would.
"""

import os

import duckdb
import pytest

from vaxt_mcp.client import _resolve_db_path

REQUIRE_DB = os.environ.get("VAXT_REQUIRE_DB") == "1"
EXPECTED_MIN_TABLES = 27


@pytest.mark.skipif(
    not REQUIRE_DB,
    reason="VAXT_REQUIRE_DB != 1 (CI sets it to enforce the warehouse is present)",
)
def test_warehouse_present_and_populated():
    path = _resolve_db_path()
    assert os.path.exists(path), f"heritage-grain warehouse missing at {path!r}"
    con = duckdb.connect(path, read_only=True)
    try:
        n = con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_type = 'BASE TABLE'"
        ).fetchone()[0]
    finally:
        con.close()
    assert n >= EXPECTED_MIN_TABLES, (
        f"expected >= {EXPECTED_MIN_TABLES} base tables, found {n} at {path}"
    )
