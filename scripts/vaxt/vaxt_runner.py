#!/usr/bin/env python3
"""VAXT pipeline runner — fetch, load, and validate heritage-grain sources.

Reads sources.toml for source declarations and orchestrates:
  1. Fetch  — (ETL only) run ETL script as subprocess
  2. Load   — CREATE TABLE AS SELECT * FROM read_csv_auto(path) into DuckDB
  3. Validate — script validator + inline rules (row count, unique key, etc.)

Usage:
    vaxt_runner.py                     # Run all enabled sources
    vaxt_runner.py --source markers    # Run one source
    vaxt_runner.py --validate-only     # Validate without re-fetching/loading
    vaxt_runner.py --dry-run           # Show plan; pass --dry-run to ETL scripts
    vaxt_runner.py --list              # List all sources with status
    vaxt_runner.py --fetch-only        # Run ETL fetch only (no load/validate)
"""

import argparse
import csv
import subprocess
import sys
import tomllib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
MANIFEST = SCRIPT_DIR / "sources.toml"

# Result statuses
PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"


def load_manifest() -> dict:
    with open(MANIFEST, "rb") as f:
        return tomllib.load(f)


def resolve_path(rel: str) -> Path:
    return WORKSPACE / rel


def csv_headers(path: Path) -> list[str]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        return next(reader)


def check_columns(path: Path, required: list[str]) -> list[str]:
    """Gate 1: check CSV headers contain all required columns."""
    headers = csv_headers(path)
    missing = [c for c in required if c not in headers]
    return missing


def run_script_validator(script_path: Path) -> tuple[bool, str]:
    """Gate 2: run external validator script, check exit code."""
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        cwd=str(WORKSPACE),
        timeout=60,
    )
    ok = result.returncode == 0
    output = (result.stdout.strip() + "\n" + result.stderr.strip()).strip()
    return ok, output


def run_inline_validation(conn, table: str, rules: dict) -> list[str]:
    """Gate 3: run inline validation rules against loaded DuckDB table."""
    errors = []

    # min_rows
    if "min_rows" in rules:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if count < rules["min_rows"]:
            errors.append(f"row count {count} < min_rows {rules['min_rows']}")

    # max_rows
    if "max_rows" in rules:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if count > rules["max_rows"]:
            errors.append(f"row count {count} > max_rows {rules['max_rows']}")

    # unique_key
    if "unique_key" in rules:
        col = rules["unique_key"]
        dupes = conn.execute(
            f'SELECT "{col}", COUNT(*) AS n FROM {table} GROUP BY "{col}" HAVING n > 1 LIMIT 5'
        ).fetchall()
        if dupes:
            dupe_vals = ", ".join(str(d[0]) for d in dupes[:3])
            errors.append(f"unique_key '{col}' has duplicates: {dupe_vals}")

    # numeric_bounds
    if "numeric_bounds" in rules:
        for col, bounds in rules["numeric_bounds"].items():
            lo, hi = bounds
            violations = conn.execute(
                f'SELECT COUNT(*) FROM {table} WHERE "{col}" IS NOT NULL AND (CAST("{col}" AS DOUBLE) < {lo} OR CAST("{col}" AS DOUBLE) > {hi})'
            ).fetchone()[0]
            if violations > 0:
                errors.append(f"numeric_bounds '{col}' [{lo}, {hi}]: {violations} violations")

    # required_values
    if "required_values" in rules:
        for col, values in rules["required_values"].items():
            actual = {
                r[0]
                for r in conn.execute(
                    f'SELECT DISTINCT "{col}" FROM {table} WHERE "{col}" IS NOT NULL'
                ).fetchall()
            }
            missing = [v for v in values if v not in actual]
            if missing:
                errors.append(f"required_values '{col}' missing: {missing}")

    return errors


def fetch_source(src_key: str, src: dict, dry_run: bool) -> tuple[str, str]:
    """Run ETL fetch for an ETL source. Returns (status, message)."""
    etl = src.get("etl", {})
    script = etl.get("script")
    if not script:
        return SKIP, "no etl.script defined"

    # Skip fetch if this source is produced by a parent
    if src.get("parent_source"):
        return SKIP, f"produced by parent '{src['parent_source']}'"

    script_path = resolve_path(script)
    if not script_path.exists():
        return FAIL, f"ETL script not found: {script}"

    cmd = [sys.executable, str(script_path)]
    delay = etl.get("delay_sec")
    if delay is not None:
        cmd.extend(["--delay", str(delay)])
    if dry_run:
        dry_flag = etl.get("dry_run_flag", "--dry-run")
        cmd.append(dry_flag)

    timeout = etl.get("timeout_sec", 300)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(WORKSPACE), timeout=timeout
        )
        if result.returncode != 0:
            return FAIL, f"ETL exited {result.returncode}: {result.stderr.strip()[:200]}"
        return PASS, f"ETL complete ({script_path.name})"
    except subprocess.TimeoutExpired:
        return FAIL, f"ETL timed out after {timeout}s"


def load_source(conn, src: dict) -> tuple[str, str]:
    """Load CSV into DuckDB. Returns (status, message)."""
    csv_path = resolve_path(src["path"])
    table = src["table_name"]

    if not csv_path.exists():
        return FAIL, f"CSV not found: {csv_path}"

    # Gate 1: column check
    required = src.get("columns", {}).get("required", [])
    if required:
        missing = check_columns(csv_path, required)
        if missing:
            return FAIL, f"missing columns: {missing}"

    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(
        f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto(?, delim=',', header=true)",
        [str(csv_path)],
    )
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return PASS, f"{count} rows loaded"


def validate_source(conn, src_key: str, src: dict) -> tuple[str, list[str]]:
    """Run validation gates 2+3. Returns (status, messages)."""
    messages = []
    validation = src.get("validation", {})
    table = src["table_name"]
    status = PASS

    # Gate 2: script validator
    script = validation.get("script")
    if script:
        script_path = resolve_path(script)
        if script_path.exists():
            ok, output = run_script_validator(script_path)
            if not ok:
                status = FAIL
                messages.append(f"validator FAIL: {output[:200]}")
            else:
                messages.append(f"validator PASS")
        else:
            status = WARN
            messages.append(f"validator script not found: {script}")

    # Gate 3: inline rules
    inline_errors = run_inline_validation(conn, table, validation)
    if inline_errors:
        status = FAIL
        messages.extend(inline_errors)
    elif validation:
        messages.append("inline rules PASS")

    return status, messages


def list_sources(manifest: dict) -> None:
    """Print a table of all declared sources."""
    global_cfg = manifest.get("global", {})
    print(f"DuckDB: {global_cfg.get('duckdb_path', '(not set)')}")
    print()
    fmt = "  {:<22} {:<8} {:<8} {:<40} {}"
    print(fmt.format("SOURCE", "TYPE", "ENABLED", "TABLE", "PATH"))
    print(fmt.format("-" * 22, "-" * 8, "-" * 8, "-" * 40, "-" * 30))
    for key, src in manifest.get("source", {}).items():
        src_type = src.get("type", "?")
        enabled = "yes" if src.get("enabled", True) else "no"
        table = src.get("table_name", "?")
        path = src.get("path", "?")
        csv_path = resolve_path(path)
        exists = "ok" if csv_path.exists() else "MISSING"
        print(fmt.format(key, src_type, enabled, table, f"{path} [{exists}]"))


def run_pipeline(manifest: dict, args: argparse.Namespace) -> int:
    """Run the full pipeline. Returns exit code."""
    try:
        import duckdb
    except ImportError:
        print("ERROR: Install duckdb: pip install duckdb", file=sys.stderr)
        return 1

    global_cfg = manifest.get("global", {})
    db_path = resolve_path(global_cfg["duckdb_path"])
    sources = manifest.get("source", {})

    # Filter to single source if requested
    if args.source:
        if args.source not in sources:
            print(f"ERROR: unknown source '{args.source}'", file=sys.stderr)
            print(f"  Available: {', '.join(sources.keys())}", file=sys.stderr)
            return 1
        sources = {args.source: sources[args.source]}

    # Ensure output dir exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    results: dict[str, str] = {}

    # Phase 1: Fetch (ETL sources only)
    if not args.validate_only:
        for key, src in sources.items():
            if not src.get("enabled", True):
                results[key] = SKIP
                continue
            if src.get("type") == "etl":
                print(f"[fetch] {key} ...", flush=True)
                status, msg = fetch_source(key, src, args.dry_run)
                print(f"  {status}: {msg}")
                if status == FAIL:
                    results[key] = FAIL

    if args.fetch_only:
        _print_summary(results)
        return 1 if FAIL in results.values() else 0

    if args.dry_run:
        print("\n[dry-run] Skipping load and validate.")
        _print_summary(results)
        return 0

    # Phase 2: Load into DuckDB
    conn = duckdb.connect(str(db_path))

    if not args.validate_only:
        for key, src in sources.items():
            if not src.get("enabled", True):
                results[key] = SKIP
                print(f"[load]  {key}: SKIP (disabled)")
                continue
            if results.get(key) == FAIL:
                print(f"[load]  {key}: SKIP (fetch failed)")
                continue
            print(f"[load]  {key} ...", flush=True)
            status, msg = load_source(conn, src)
            print(f"  {status}: {msg}")
            if status == FAIL:
                results[key] = FAIL

    # Phase 3: Validate
    for key, src in sources.items():
        if not src.get("enabled", True):
            continue
        if results.get(key) == FAIL:
            print(f"[valid] {key}: SKIP (prior failure)")
            continue

        # For validate-only, check the table exists
        if args.validate_only:
            table = src["table_name"]
            try:
                conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
            except Exception:
                print(f"[valid] {key}: SKIP (table '{table}' not found)")
                results[key] = SKIP
                continue

        print(f"[valid] {key} ...", flush=True)
        status, messages = validate_source(conn, key, src)
        for m in messages:
            print(f"  {m}")
        print(f"  => {status}")
        if status == FAIL:
            results[key] = FAIL
        elif key not in results:
            results[key] = status

    conn.close()

    _print_summary(results)
    return 1 if FAIL in results.values() else 0


def _print_summary(results: dict[str, str]) -> None:
    print("\n=== Summary ===")
    for key, status in results.items():
        print(f"  {key}: {status}")
    counts = {}
    for v in results.values():
        counts[v] = counts.get(v, 0) + 1
    parts = [f"{v}={n}" for v, n in sorted(counts.items())]
    print(f"  ({', '.join(parts)})" if parts else "  (no sources processed)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="VAXT pipeline runner — fetch, load, validate heritage-grain sources"
    )
    parser.add_argument("--source", help="Run a single source by key")
    parser.add_argument("--validate-only", action="store_true", help="Validate existing DuckDB (no fetch/load)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan; pass --dry-run to ETL scripts")
    parser.add_argument("--list", action="store_true", help="List all sources with status")
    parser.add_argument("--fetch-only", action="store_true", help="Run ETL fetch only (no load/validate)")

    args = parser.parse_args()
    manifest = load_manifest()

    if args.list:
        list_sources(manifest)
        return 0

    return run_pipeline(manifest, args)


if __name__ == "__main__":
    sys.exit(main())
