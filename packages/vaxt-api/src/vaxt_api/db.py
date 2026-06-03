"""Read-only DuckDB access for the VAXT BrAPI server.

A new read-only connection is opened per query. DuckDB allows concurrent
read-only readers, and the heritage-grain DB is small, so this keeps the
server stateless and simple. Point it at a DB with VAXT_DUCKDB_PATH.
"""
from __future__ import annotations

import os

import duckdb

_DEFAULT_PATH = "data/datasets/heritage-grain/heritage-grain.duckdb"


def db_path() -> str:
    return os.environ.get("VAXT_DUCKDB_PATH", _DEFAULT_PATH)


def query(sql: str, params: list | None = None) -> list[dict]:
    """Run a read-only query and return a list of dict rows."""
    con = duckdb.connect(db_path(), read_only=True)
    try:
        cur = con.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        con.close()


def scalar(sql: str, params: list | None = None):
    """Run a query that returns a single value (e.g. count(*))."""
    rows = query(sql, params)
    if not rows:
        return None
    return next(iter(rows[0].values()))
