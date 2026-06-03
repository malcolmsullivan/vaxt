#!/usr/bin/env python3
"""
Establish Airtable cross-links between VAXT tables.

Relationships:
  1. Varieties → Breeding Programs  (match on program/institution name)
  2. Sourdough Starters → Recipes   (match on Starter ID)
  3. Community Grain Projects → Varieties  (match on varieties_grown names)

Usage:
    python3 scripts/vaxt/link_airtable_records.py [--dry-run]

Env:
    VAXT_AIRTABLE_PAT       Personal Access Token
    VAXT_AIRTABLE_BASE_ID   Base ID (default: appgv7zVxZnT2q9BX)
"""

import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BASE_ID = os.environ.get("VAXT_AIRTABLE_BASE_ID", "appgv7zVxZnT2q9BX")
PAT = os.environ.get("VAXT_AIRTABLE_PAT", "")
RATE_DELAY = 0.25
BATCH_SIZE = 10
DRY_RUN = "--dry-run" in sys.argv

# Load from .env if PAT not in environment
if not PAT and (SCRIPT_DIR / ".env").exists():
    for line in (SCRIPT_DIR / ".env").read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "VAXT_AIRTABLE_PAT":
            PAT = v.strip()

if not PAT:
    print("ERROR: VAXT_AIRTABLE_PAT not set. See scripts/vaxt/.env.example")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Content-Type": "application/json",
}


# ---------------------------------------------------------------------------
# HTTP helpers (same as sync script)
# ---------------------------------------------------------------------------
def api_request(url: str, method: str = "GET", payload: dict | None = None,
                retries: int = 3) -> dict:
    time.sleep(RATE_DELAY)
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            if e.code == 429 or e.code >= 500:
                wait = 2 ** (attempt + 1)
                print(f"  Retry {attempt+1}/{retries} after {wait}s ({e.code})")
                time.sleep(wait)
                continue
            print(f"  HTTP {e.code}: {body[:300]}")
            raise
    raise RuntimeError(f"Failed after {retries} retries: {url}")


def get_tables() -> dict:
    """Return {table_name: {id, fields: {name: field_info}}}."""
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"
    data = api_request(url)
    result = {}
    for t in data["tables"]:
        fields = {f["name"]: f for f in t.get("fields", [])}
        result[t["name"]] = {"id": t["id"], "fields": fields}
    return result


def get_all_records(table_id: str, fields: list[str] | None = None) -> list[dict]:
    """Fetch all records from a table, handling pagination."""
    records = []
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}?pageSize=100"
    if fields:
        from urllib.parse import quote
        for f in fields:
            url += f"&fields[]={quote(f)}"
    offset = None
    while True:
        page_url = url + (f"&offset={offset}" if offset else "")
        data = api_request(page_url)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def add_field(table_id: str, field_def: dict) -> None:
    """Add a field to an existing table."""
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{table_id}/fields"
    if DRY_RUN:
        print(f"  [DRY RUN] Would add field '{field_def['name']}'")
        return
    api_request(url, method="POST", payload=field_def)
    print(f"  Added field '{field_def['name']}'")


def update_records_batch(table_id: str, updates: list[dict]) -> int:
    """Update records in batches of 10. Returns total updated."""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    total = 0
    for i in range(0, len(updates), BATCH_SIZE):
        batch = updates[i:i + BATCH_SIZE]
        payload = {
            "records": batch,
            "typecast": True,
        }
        if DRY_RUN:
            print(f"  [DRY RUN] Would update batch {i//BATCH_SIZE + 1} ({len(batch)} records)")
            total += len(batch)
            continue
        api_request(url, method="PATCH", payload=payload)
        total += len(batch)
        print(f"  Updated batch {i//BATCH_SIZE + 1}: {len(batch)} records")
    return total


# ---------------------------------------------------------------------------
# Link 1: Varieties → Breeding Programs
# ---------------------------------------------------------------------------
def link_varieties_to_programs(tables: dict) -> None:
    """Link Varieties to Breeding Programs.

    Strategy: Read the variety CSV's 'program' column. Match to Breeding Programs
    table on Institution name. Create linked record field on Varieties.
    """
    print("\n== Link 1: Varieties → Breeding Programs ==")

    var_table = tables.get("Varieties")
    prog_table = tables.get("Breeding Programs")
    if not var_table:
        print("  ERROR: Varieties table not found")
        return
    if not prog_table:
        print("  ERROR: Breeding Programs table not found")
        return

    # Ensure Varieties has a linked record field to Breeding Programs
    if "Breeding Program" not in var_table["fields"]:
        print("  Adding 'Breeding Program' linked record field to Varieties...")
        add_field(var_table["id"], {
            "name": "Breeding Program",
            "type": "multipleRecordLinks",
            "options": {
                "linkedTableId": prog_table["id"],
            },
        })
    else:
        print("  'Breeding Program' field already exists on Varieties")

    # Fetch all breeding programs → build lookup by institution name
    print("  Fetching Breeding Programs...")
    prog_records = get_all_records(prog_table["id"], fields=["Institution", "Program ID"])
    prog_by_institution = {}
    prog_by_id = {}
    for rec in prog_records:
        f = rec.get("fields", {})
        inst = f.get("Institution", "").strip().lower()
        pid = f.get("Program ID", "").strip().lower()
        if inst:
            prog_by_institution[inst] = rec["id"]
        if pid:
            prog_by_id[pid] = rec["id"]
    print(f"  {len(prog_by_institution)} programs indexed by institution")

    # Read CSV for program column
    csv_path = SCRIPT_DIR / "nordic_variety_trait_index.csv"
    if not csv_path.exists():
        print("  ERROR: nordic_variety_trait_index.csv not found")
        return

    with open(csv_path, newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))

    # Build variety_name → program mapping from CSV
    csv_program_map = {}
    for row in csv_rows:
        name = row.get("variety", "").strip()
        program = row.get("program", "").strip()
        if name and program:
            csv_program_map[name] = program

    # Fetch all varieties
    print("  Fetching Varieties...")
    var_records = get_all_records(var_table["id"], fields=["Name", "Breeding Program"])
    print(f"  {len(var_records)} varieties fetched")

    # Build updates: match variety's program to breeding program record ID
    updates = []
    matched = 0
    already_linked = 0
    no_match = 0

    for rec in var_records:
        f = rec.get("fields", {})
        name = f.get("Name", "").strip()
        existing_links = f.get("Breeding Program", [])

        if existing_links:
            already_linked += 1
            continue

        csv_program = csv_program_map.get(name, "")
        if not csv_program:
            continue

        # Try matching: program name → institution, or direct program_id match
        program_lower = csv_program.lower()
        prog_rec_id = (
            prog_by_institution.get(program_lower)
            or prog_by_id.get(program_lower)
        )

        # Try partial match — institution contains program name or vice versa
        if not prog_rec_id:
            for inst, rid in prog_by_institution.items():
                if program_lower in inst or inst in program_lower:
                    prog_rec_id = rid
                    break

        if prog_rec_id:
            updates.append({
                "id": rec["id"],
                "fields": {"Breeding Program": [prog_rec_id]},
            })
            matched += 1
        else:
            no_match += 1

    print(f"  Matched: {matched}, Already linked: {already_linked}, No match: {no_match}")

    if updates:
        total = update_records_batch(var_table["id"], updates)
        print(f"  Total: {total} variety-program links created")
    else:
        print("  No new links to create")


# ---------------------------------------------------------------------------
# Link 2: Sourdough Starters → Recipes
# ---------------------------------------------------------------------------
def link_starters_to_recipes(tables: dict) -> None:
    """Link Sourdough Starters to Sourdough Recipes on Starter ID."""
    print("\n== Link 2: Sourdough Starters → Recipes ==")

    starter_table = tables.get("Sourdough Starters")
    recipe_table = tables.get("Sourdough Recipes")
    if not starter_table:
        print("  ERROR: Sourdough Starters table not found")
        return
    if not recipe_table:
        print("  ERROR: Sourdough Recipes table not found")
        return

    # Ensure Starters has a linked record field to Recipes
    if "Recipes" not in starter_table["fields"]:
        print("  Adding 'Recipes' linked record field to Sourdough Starters...")
        add_field(starter_table["id"], {
            "name": "Recipes",
            "type": "multipleRecordLinks",
            "options": {
                "linkedTableId": recipe_table["id"],
            },
        })
    else:
        print("  'Recipes' field already exists on Sourdough Starters")

    # Fetch all recipes → build lookup by Starter ID
    print("  Fetching Sourdough Recipes...")
    recipe_records = get_all_records(recipe_table["id"], fields=["Starter ID"])
    recipes_by_starter = {}
    for rec in recipe_records:
        f = rec.get("fields", {})
        sid = f.get("Starter ID", "").strip()
        if sid:
            recipes_by_starter.setdefault(sid, []).append(rec["id"])
    print(f"  {len(recipes_by_starter)} starters have recipes")

    # Fetch all starters
    print("  Fetching Sourdough Starters...")
    starter_records = get_all_records(starter_table["id"], fields=["Starter ID", "Recipes"])
    print(f"  {len(starter_records)} starters fetched")

    # Build updates
    updates = []
    matched = 0
    already_linked = 0

    for rec in starter_records:
        f = rec.get("fields", {})
        sid = f.get("Starter ID", "").strip()
        existing_links = f.get("Recipes", [])

        if existing_links:
            already_linked += 1
            continue

        recipe_ids = recipes_by_starter.get(sid, [])
        if recipe_ids:
            updates.append({
                "id": rec["id"],
                "fields": {"Recipes": recipe_ids},
            })
            matched += 1

    print(f"  Matched: {matched}, Already linked: {already_linked}")

    if updates:
        total = update_records_batch(starter_table["id"], updates)
        print(f"  Total: {total} starter-recipe links created")
    else:
        print("  No new links to create")


# ---------------------------------------------------------------------------
# Link 3: Community Grain Projects → Varieties
# ---------------------------------------------------------------------------
def link_projects_to_varieties(tables: dict) -> None:
    """Link Community Grain Projects to Varieties on varieties_grown names."""
    print("\n== Link 3: Community Grain Projects → Varieties ==")

    proj_table = tables.get("Community Grain Projects")
    var_table = tables.get("Varieties")
    if not proj_table:
        print("  ERROR: Community Grain Projects table not found")
        return
    if not var_table:
        print("  ERROR: Varieties table not found")
        return

    # Ensure Community Grain Projects has a linked record field to Varieties
    if "Linked Varieties" not in proj_table["fields"]:
        print("  Adding 'Linked Varieties' linked record field to Community Grain Projects...")
        add_field(proj_table["id"], {
            "name": "Linked Varieties",
            "type": "multipleRecordLinks",
            "options": {
                "linkedTableId": var_table["id"],
            },
        })
    else:
        print("  'Linked Varieties' field already exists")

    # Fetch all varieties → build name → record ID lookup
    print("  Fetching Varieties...")
    var_records = get_all_records(var_table["id"], fields=["Name"])
    var_by_name = {}
    for rec in var_records:
        name = rec.get("fields", {}).get("Name", "").strip()
        if name:
            var_by_name[name.lower()] = rec["id"]
    print(f"  {len(var_by_name)} varieties indexed")

    # Fetch all community projects
    print("  Fetching Community Grain Projects...")
    proj_records = get_all_records(
        proj_table["id"], fields=["Name", "Varieties Grown", "Linked Varieties"]
    )
    print(f"  {len(proj_records)} projects fetched")

    # Build updates
    updates = []
    matched = 0
    already_linked = 0

    for rec in proj_records:
        f = rec.get("fields", {})
        existing_links = f.get("Linked Varieties", [])
        if existing_links:
            already_linked += 1
            continue

        varieties_str = f.get("Varieties Grown", "")
        if not varieties_str:
            continue

        # Parse semicolon-separated variety names
        variety_names = [v.strip() for v in varieties_str.split(";") if v.strip()]
        linked_ids = []
        for vname in variety_names:
            rid = var_by_name.get(vname.lower())
            if rid:
                linked_ids.append(rid)

        if linked_ids:
            updates.append({
                "id": rec["id"],
                "fields": {"Linked Varieties": linked_ids},
            })
            matched += 1

    print(f"  Matched: {matched}, Already linked: {already_linked}")

    if updates:
        total = update_records_batch(proj_table["id"], updates)
        print(f"  Total: {total} project-variety links created")
    else:
        print("  No new links to create")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(f"VAXT Airtable Cross-Links — Base: {BASE_ID}")
    if DRY_RUN:
        print("[DRY RUN MODE — no changes will be made]\n")

    tables = get_tables()
    print(f"Found {len(tables)} tables: {list(tables.keys())}\n")

    link_varieties_to_programs(tables)

    # Refresh tables after schema changes (new linked fields)
    tables = get_tables()

    link_starters_to_recipes(tables)

    # Refresh tables again for project links
    tables = get_tables()

    link_projects_to_varieties(tables)

    print("\nDone.")


if __name__ == "__main__":
    main()
