"""Resolution order + fail-loud guards for the DuckDB path.

These are hermetic (no warehouse, no wheel needed): they drive `_resolve_db`
directly with an injected bundled path and controlled env/cwd, so they assert the
env -> workspace -> cwd -> bundled order, the resolved `source`, and — critically —
that the bundled fallback is *refused* when VAXT_REQUIRE_DB is set (a stale wheel
must never silently answer in place of a missing external warehouse).
"""

from pathlib import Path

from vaxt_mcp.client import _DEFAULT_DB_PATH, _resolve_db


def _clear_env(monkeypatch):
    monkeypatch.delenv("VAXT_DUCKDB_PATH", raising=False)
    monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("VAXT_REQUIRE_DB", raising=False)


def test_env_wins(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_env(monkeypatch)
    monkeypatch.setenv("VAXT_DUCKDB_PATH", "/some/explicit.duckdb")
    path, source = _resolve_db(bundled="/irrelevant/bundled.duckdb")
    assert (path, source) == ("/some/explicit.duckdb", "env")


def test_cwd_relative(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    db = tmp_path / _DEFAULT_DB_PATH
    db.parent.mkdir(parents=True)
    db.write_bytes(b"")  # existence is all _resolve_db checks
    monkeypatch.chdir(tmp_path)
    path, source = _resolve_db(bundled=None)
    assert source == "cwd"
    assert Path(path) == Path(_DEFAULT_DB_PATH)


def test_bundled_fallback(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)  # no cwd DB here
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "nope"))  # no workspace DB
    bundled = tmp_path / "bundled.duckdb"
    bundled.write_bytes(b"")
    path, source = _resolve_db(bundled=str(bundled))
    assert (path, source) == (str(bundled), "bundled")


def test_require_db_refuses_bundled(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "nope"))
    monkeypatch.setenv("VAXT_REQUIRE_DB", "1")
    bundled = tmp_path / "bundled.duckdb"
    bundled.write_bytes(b"")
    import pytest

    with pytest.raises(FileNotFoundError):
        _resolve_db(bundled=str(bundled))


def test_missing_returns_failloud_candidate(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "nope"))
    path, source = _resolve_db(bundled=None)
    # Nothing resolved and nothing bundled -> nonexistent candidate so duckdb.connect
    # fails loud at open, exactly as before the bundled fallback existed.
    assert source == "missing"
    assert not Path(path).exists()
