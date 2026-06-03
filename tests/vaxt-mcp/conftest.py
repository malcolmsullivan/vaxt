"""VAXT MCP test configuration."""

import os
import pytest


@pytest.fixture
def duckdb_path():
    """Path to heritage grain DuckDB for integration tests."""
    path = os.environ.get(
        "VAXT_DUCKDB_PATH",
        "data/datasets/heritage-grain/heritage-grain.duckdb",
    )
    if not os.path.exists(path):
        pytest.skip(f"DuckDB not found at {path}")
    return path
