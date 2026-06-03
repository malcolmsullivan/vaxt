#!/usr/bin/env python3
"""
VAXT Airtable → varieties.json export script.

Reads the VAXT Airtable base via REST API and exports:
  1. varieties.json — Website-featured varieties for the VAXT site
  2. stats.json    — Table row counts for Notion sync

Usage:
  python3 scripts/vaxt/export_airtable_varieties.py
  python3 scripts/vaxt/export_airtable_varieties.py --dry-run
  python3 scripts/vaxt/export_airtable_varieties.py --all  # Export all varieties, not just featured

Env vars (from scripts/vaxt/.env):
  VAXT_AIRTABLE_PAT      — Personal Access Token
  VAXT_AIRTABLE_BASE_ID  — Base ID (default: appgv7zVxZnT2q9BX)
  VAXT_OUTPUT_DIR         — Output directory (default: data/datasets/heritage-grain)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SCRIPT_DIR = Path(__file__).parent
WORKSPACE = SCRIPT_DIR.parent.parent

# Load .env if present
env_path = SCRIPT_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

PAT = os.environ.get("VAXT_AIRTABLE_PAT", "")
BASE_ID = os.environ.get("VAXT_AIRTABLE_BASE_ID", "appgv7zVxZnT2q9BX")
OUTPUT_DIR = Path(os.environ.get("VAXT_OUTPUT_DIR", WORKSPACE / "data" / "datasets" / "heritage-grain"))

API_BASE = "https://api.airtable.com/v0"
RATE_LIMIT_DELAY = 0.25  # 5 req/s max → 200ms buffer


class AirtableError(Exception):
    """Raised when an Airtable API call fails."""
    def __init__(self, code: int, body: str):
        self.code = code
        self.body = body
        super().__init__(f"Airtable API {code}: {body}")


def api_get(url: str) -> dict:
    """GET from Airtable API with auth and rate limiting."""
    if not PAT:
        print("ERROR: VAXT_AIRTABLE_PAT not set. See scripts/vaxt/.env.example", file=sys.stderr)
        sys.exit(1)
    req = Request(url, headers={
        "Authorization": f"Bearer {PAT}",
        "Content-Type": "application/json",
    })
    time.sleep(RATE_LIMIT_DELAY)
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise AirtableError(e.code, body)
    except URLError as e:
        print(f"ERROR: Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def get_tables() -> list[dict] | None:
    """List all tables in the base via Metadata API.

    Returns None if the PAT lacks schema.bases:read scope.
    """
    url = f"{API_BASE}/meta/bases/{BASE_ID}/tables"
    try:
        data = api_get(url)
        return data.get("tables", [])
    except AirtableError as e:
        print(f"  Metadata API failed ({e.code}): PAT may lack schema.bases:read scope", file=sys.stderr)
        return None


def get_records(table_ref: str, filter_formula: str = "", fields: list[str] | None = None) -> list[dict]:
    """Fetch all records from a table, handling pagination.

    table_ref can be a table name ('Varieties') or table ID ('tblXxx...').
    Table names are URL-encoded automatically.
    """
    from urllib.parse import quote
    records = []
    params = []
    if filter_formula:
        params.append(f"filterByFormula={quote(filter_formula)}")
    if fields:
        for f in fields:
            params.append(f"fields[]={quote(f)}")

    base_url = f"{API_BASE}/{BASE_ID}/{quote(table_ref)}"
    base_params = list(params)  # preserve original params for pagination

    url = base_url
    if base_params:
        url += "?" + "&".join(base_params)

    while url:
        data = api_get(url)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if offset:
            # Rebuild URL cleanly each time with original params + offset
            page_params = base_params + [f"offset={offset}"]
            url = base_url + "?" + "&".join(page_params)
        else:
            url = None
    return records


def export_varieties(tables: list[dict] | None, all_varieties: bool = False) -> list[dict]:
    """Export varieties from the Varieties table.

    Uses table name ('Varieties') directly for the records API. The tables
    parameter is optional — if metadata is unavailable (PAT lacks
    schema.bases:read), the function falls back to the known table name.
    """
    table_ref = "Varieties"  # Use table name (works regardless of PAT scope)
    if tables:
        for t in tables:
            if t["name"].lower() in ("varieties", "variety"):
                table_ref = t["name"]
                print(f"  Varieties table: {t['name']} ({t['id']})")
                break
    else:
        print(f"  Using table name: {table_ref} (metadata unavailable)")

    # Fetch records
    filter_formula = "" if all_varieties else "{Website Featured}"
    records = get_records(table_ref, filter_formula=filter_formula)
    print(f"  Records fetched: {len(records)}")

    # Transform to clean JSON for website
    varieties = []
    for rec in records:
        f = rec.get("fields", {})
        variety = {
            "id": rec["id"],
            "name": f.get("Name", ""),
            "species": f.get("Species", ""),
            "crop": f.get("Crop", ""),
            "country": f.get("Country", ""),
            "traits": f.get("Traits", []),
            "cold_tolerance_notes": f.get("Cold Tolerance Notes", ""),
            "usda_zone": f.get("USDA Zone", ""),
            "protein": f.get("Protein", ""),
            "sourdough_notes": f.get("Sourdough Notes", ""),
            "bread_notes": f.get("Bread Notes", ""),
            "malt_profile": f.get("Malt Profile", ""),
            "end_use": f.get("End Use", []),
            "falling_number": f.get("Falling Number", ""),
            "test_weight": f.get("Test Weight", ""),
            "origin": f.get("Origin", ""),
            "source": f.get("Source", ""),
            "featured": bool(f.get("Website Featured", False)),
            "status": f.get("Status", "draft"),
            # Applied growing fields
            "seeding_rate": f.get("Seeding Rate", ""),
            "seeding_depth": f.get("Seeding Depth", ""),
            "seeding_window": f.get("Seeding Window", ""),
            "days_to_maturity": f.get("Days to Maturity", ""),
            "row_spacing": f.get("Row Spacing", ""),
            "harvest_notes": f.get("Harvest Notes", ""),
            "seed_sources": f.get("Seed Sources", ""),
            "grower_tips": f.get("Grower Tips", ""),
        }
        varieties.append(variety)

    # Sort: featured first, then by name
    varieties.sort(key=lambda v: (not v["featured"], v["name"]))
    return varieties


def export_stats(tables: list[dict]) -> dict:
    """Export table counts for Notion sync."""
    stats = {
        "base_id": BASE_ID,
        "base_url": f"https://airtable.com/{BASE_ID}",
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tables": {},
    }

    for t in tables:
        # Get record count (use table name — some PATs only allow name-based access)
        try:
            records = get_records(t["name"])
            count = len(records)
        except AirtableError as e:
            print(f"  {t['name']}: SKIPPED ({e.code} — no read access)")
            count = -1
        stats["tables"][t["name"]] = {
            "id": t["id"],
            "url": f"https://airtable.com/{BASE_ID}/{t['id']}",
            "fields": len(t.get("fields", [])),
            "records": count,
        }
        if count >= 0:
            print(f"  {t['name']}: {count} records, {len(t.get('fields', []))} fields")

    stats["total_records"] = sum(t["records"] for t in stats["tables"].values() if t["records"] >= 0)
    stats["total_tables"] = len(stats["tables"])
    return stats


def main():
    parser = argparse.ArgumentParser(description="Export VAXT Airtable → varieties.json + stats.json")
    parser.add_argument("--dry-run", action="store_true", help="List tables and counts without full export")
    parser.add_argument("--all", action="store_true", help="Export all varieties, not just Website Featured")
    parser.add_argument("--stats-only", action="store_true", help="Export stats.json only (no varieties)")
    args = parser.parse_args()

    print(f"VAXT Airtable Export")
    print(f"  Base: {BASE_ID}")
    print(f"  Output: {OUTPUT_DIR}")
    print()

    # Discover tables (optional — PAT may lack schema.bases:read)
    print("Fetching table metadata...")
    tables = get_tables()
    if tables:
        print(f"  Found {len(tables)} tables:")
        for t in tables:
            print(f"    - {t['name']} ({t['id']}, {len(t.get('fields', []))} fields)")
    else:
        print("  Falling back to direct table name access")
    print()

    if args.dry_run:
        print("[DRY RUN] Would export varieties.json and stats.json")
        print(f"  Output dir: {OUTPUT_DIR}")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Stats-only mode
    if args.stats_only:
        if not tables:
            print("ERROR: --stats-only requires metadata access (schema.bases:read scope)", file=sys.stderr)
            sys.exit(1)
        print("Exporting stats...")
        stats = export_stats(tables)
        stats_path = OUTPUT_DIR / "airtable_stats.json"
        stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False))
        print(f"  → {stats_path}")
        print("Done (stats only).")
        return

    # Export varieties FIRST (the important part — works with or without metadata)
    print("Exporting varieties...")
    mode = "all" if args.all else "featured"
    varieties = export_varieties(tables, all_varieties=args.all)
    varieties_path = OUTPUT_DIR / "varieties.json"
    varieties_path.write_text(json.dumps(varieties, indent=2, ensure_ascii=False))
    featured_count = sum(1 for v in varieties if v["featured"])
    print(f"  → {varieties_path} ({len(varieties)} varieties, {featured_count} featured)")
    print()

    # Export stats (optional — runs after varieties so it doesn't block on failure)
    if tables:
        print("Exporting stats...")
        stats = export_stats(tables)
        stats_path = OUTPUT_DIR / "airtable_stats.json"
        stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False))
        print(f"  → {stats_path} ({stats['total_tables']} tables, {stats['total_records']} total records)")
        print()

    print(f"Done. {len(varieties)} varieties exported ({mode}).")


if __name__ == "__main__":
    main()
