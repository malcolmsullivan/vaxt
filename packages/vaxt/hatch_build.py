"""Hatchling build hook — stage the warehouse into the wheel so `pip`/`uvx` is turnkey.

The canonical DuckDB warehouse lives at the REPO ROOT
(``data/datasets/heritage-grain/heritage-grain.duckdb``), which is *above* this
package's build root (``packages/vaxt``). No static package-data mechanism can reach
above its own project root, so this hook copies it into the wheel at build time as
``vaxt_mcp/data/heritage-grain.duckdb`` and writes a ``WAREHOUSE.json`` fingerprint
(schema version, sha256, byte size, table + row counts) beside it.

``pip install "git+https://…#subdirectory=packages/vaxt"`` clones the whole repo to a
temp dir before building the subdirectory, so the parent ``data/`` path is present
there too — the same reason this works for a local ``python -m build``.

Editable installs are skipped: a source checkout already resolves the warehouse via
``VAXT_DUCKDB_PATH`` / ``$WORKSPACE_ROOT`` / cwd, and must not carry a frozen copy.
"""

import hashlib
import json
import shutil
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# Canonical warehouse, relative to the repo root (two levels above packages/vaxt).
_CANONICAL_REL = "data/datasets/heritage-grain/heritage-grain.duckdb"
# Destination inside the built wheel (relative to site-packages).
_WHEEL_DB_DEST = "vaxt_mcp/data/heritage-grain.duckdb"
_WHEEL_FP_DEST = "vaxt_mcp/data/WAREHOUSE.json"
_FINGERPRINT_SCHEMA = 1


class VaxtBundleWarehouse(BuildHookInterface):
    """Copies the warehouse + fingerprint into non-editable wheels."""

    PLUGIN_NAME = "custom"

    def initialize(self, version, build_data):
        # Editable installs resolve the DB from the repo; never bundle a frozen copy.
        if version == "editable":
            return

        canonical = Path(self.root).parents[1] / _CANONICAL_REL
        if not canonical.exists():
            raise FileNotFoundError(
                f"Cannot build a turnkey vaxt-mcp wheel: canonical warehouse not "
                f"found at {canonical}. Build from a full repo checkout (or a "
                f"git+https #subdirectory install, which clones the whole repo)."
            )

        # Stage the fingerprint into a hook-owned, gitignored dir (no src pollution).
        staged = Path(self.root) / ".hatch-build" / "data"
        staged.mkdir(parents=True, exist_ok=True)
        fingerprint_path = staged / "WAREHOUSE.json"
        fingerprint_path.write_text(
            json.dumps(_fingerprint(canonical), indent=2, default=str),
            encoding="utf-8",
        )

        # force_include guarantees both files land in the wheel regardless of the
        # package's default file matching.
        force = build_data.setdefault("force_include", {})
        force[str(canonical)] = _WHEEL_DB_DEST
        force[str(fingerprint_path)] = _WHEEL_FP_DEST

    def finalize(self, version, build_data, artifact_path):
        # Best-effort cleanup of the staging dir; harmless if it remains (gitignored).
        staged = Path(self.root) / ".hatch-build"
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)


def _fingerprint(db_path: Path) -> dict:
    """Content-addressed snapshot fingerprint: makes a stale wheel self-evident.

    sha256 + byte size uniquely identify the frozen warehouse; table/row counts are
    the same figures CLAIMS.md tracks. No build timestamp, so the wheel stays
    reproducible.
    """
    data = db_path.read_bytes()
    fp = {
        "schema_version": _FINGERPRINT_SCHEMA,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
    # Row/table counts are best-effort: the hook declares duckdb as a build
    # dependency, but never fail a build over the fingerprint's richness.
    try:
        import duckdb  # noqa: PLC0415 — build-time only

        con = duckdb.connect(str(db_path), read_only=True)
        try:
            tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
            counts = {
                t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                for t in tables
            }
        finally:
            con.close()
        fp["tables"] = len(counts)
        fp["table_counts"] = counts
        fp["total_rows"] = sum(counts.values())
    except Exception as e:  # noqa: BLE001 — fingerprint richness is optional
        fp["counts_error"] = str(e)
    return fp
