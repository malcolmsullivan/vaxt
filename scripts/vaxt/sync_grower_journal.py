#!/usr/bin/env python3
"""
Sync Grower's Journal from Notion → DuckDB.

Reads the Grower's Journal Notion database and exports entries
to a CSV + DuckDB table for MCP querying.

Usage:
    python3 scripts/vaxt/sync_grower_journal.py [--dry-run]

Env:
    NOTION_API_KEY          Notion integration token
    VAXT_GROWER_JOURNAL_DB  Notion database ID (default: eb7c936f8b2b4e309be08b0ec8e43ef2)
"""

import csv
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_CSV = SCRIPT_DIR / "grower_journal.csv"
DUCKDB_PATH = WORKSPACE / "data" / "datasets" / "heritage-grain" / "heritage-grain.duckdb"

NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
DB_ID = os.environ.get("VAXT_GROWER_JOURNAL_DB", "eb7c936f8b2b4e309be08b0ec8e43ef2")
DRY_RUN = "--dry-run" in sys.argv

# Load from .env if not set
if not NOTION_API_KEY and (SCRIPT_DIR / ".env").exists():
    for line in (SCRIPT_DIR / ".env").read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "NOTION_API_KEY":
            NOTION_API_KEY = v.strip()


def notion_request(url: str, method: str = "GET", body: dict | None = None) -> dict:
    """Make a Notion API request."""
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=headers, method=method)
    time.sleep(0.35)  # Rate limit
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())


def extract_text(prop: dict) -> str:
    """Extract text from a Notion property."""
    ptype = prop.get("type", "")
    if ptype == "title":
        return "".join(t.get("plain_text", "") for t in prop.get("title", []))
    elif ptype == "rich_text":
        return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
    elif ptype == "select":
        sel = prop.get("select")
        return sel.get("name", "") if sel else ""
    elif ptype == "multi_select":
        return ";".join(s.get("name", "") for s in prop.get("multi_select", []))
    elif ptype == "number":
        val = prop.get("number")
        return str(val) if val is not None else ""
    elif ptype == "date":
        d = prop.get("date")
        return d.get("start", "") if d else ""
    elif ptype == "checkbox":
        return str(prop.get("checkbox", False)).lower()
    return ""


def fetch_journal_entries() -> list[dict]:
    """Fetch all entries from the Grower's Journal Notion DB."""
    entries = []
    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    has_more = True
    start_cursor = None

    while has_more:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor

        data = notion_request(url, method="POST", body=body)
        for page in data.get("results", []):
            props = page.get("properties", {})
            entry = {
                "page_id": page["id"],
                "created": page.get("created_time", ""),
            }
            # Extract all properties dynamically
            for name, prop in props.items():
                key = name.lower().replace(" ", "_").replace("(", "").replace(")", "")
                entry[key] = extract_text(prop)
            entries.append(entry)

        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return entries


def write_csv(entries: list[dict]) -> None:
    """Write entries to CSV."""
    if not entries:
        print("  No entries to write")
        return

    # Collect all keys across all entries
    all_keys = []
    seen = set()
    for entry in entries:
        for k in entry:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry)

    print(f"  Written {len(entries)} entries to {OUTPUT_CSV}")


def load_to_duckdb(entries: list[dict]) -> None:
    """Load entries into DuckDB grower_journal table."""
    try:
        import duckdb
    except ImportError:
        print("  WARNING: duckdb not installed, skipping DuckDB load")
        return

    if not DUCKDB_PATH.exists():
        print(f"  WARNING: DuckDB not found at {DUCKDB_PATH}, skipping")
        return

    conn = duckdb.connect(str(DUCKDB_PATH))

    # Create table from CSV
    conn.execute("DROP TABLE IF EXISTS grower_journal")
    conn.execute(f"""
        CREATE TABLE grower_journal AS
        SELECT * FROM read_csv_auto('{OUTPUT_CSV}', header=true)
    """)

    count = conn.execute("SELECT COUNT(*) FROM grower_journal").fetchone()[0]
    print(f"  Loaded {count} rows into DuckDB grower_journal table")
    conn.close()


def main():
    print("VAXT Grower's Journal Sync")
    print(f"  Notion DB: {DB_ID}")
    print(f"  Output CSV: {OUTPUT_CSV}")
    print(f"  DuckDB: {DUCKDB_PATH}")

    if not NOTION_API_KEY:
        print("\nERROR: NOTION_API_KEY not set")
        print("  Set in environment or scripts/vaxt/.env")
        sys.exit(1)

    if DRY_RUN:
        print("\n[DRY RUN] Would fetch from Notion and export to CSV + DuckDB")
        return

    print("\nFetching journal entries from Notion...")
    entries = fetch_journal_entries()
    print(f"  Found {len(entries)} entries")

    if entries:
        write_csv(entries)
        load_to_duckdb(entries)

    print("\nDone.")


if __name__ == "__main__":
    main()
