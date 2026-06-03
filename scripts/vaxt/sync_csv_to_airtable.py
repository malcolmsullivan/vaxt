#!/usr/bin/env python3
"""
Sync VAXT CSV data → Airtable.

Creates missing tables, adds missing fields to Varieties,
and upserts records from committed CSVs.

Usage:
    python3 scripts/vaxt/sync_csv_to_airtable.py [--dry-run]

Env:
    VAXT_AIRTABLE_PAT   Personal Access Token (scopes: data.records:read/write, schema.bases:read)
    VAXT_AIRTABLE_BASE_ID  Base ID (default: appgv7zVxZnT2q9BX)
"""

import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
BASE_ID = os.environ.get("VAXT_AIRTABLE_BASE_ID", "appgv7zVxZnT2q9BX")
PAT = os.environ.get("VAXT_AIRTABLE_PAT", "")
RATE_DELAY = 0.25  # seconds between API calls
BATCH_SIZE = 10    # Airtable max per upsert request
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
# HTTP helpers
# ---------------------------------------------------------------------------
def api_request(url: str, method: str = "GET", payload: dict | None = None,
                retries: int = 3) -> dict:
    """Make an Airtable API request with retry and rate limiting."""
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


def create_table(name: str, fields: list[dict]) -> str:
    """Create a new table. Returns table ID."""
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"
    payload = {"name": name, "fields": fields}
    if DRY_RUN:
        print(f"  [DRY RUN] Would create table '{name}' with {len(fields)} fields")
        return "dry_run_id"
    data = api_request(url, method="POST", payload=payload)
    print(f"  Created table '{name}' → {data['id']}")
    return data["id"]


def add_field(table_id: str, field_def: dict) -> None:
    """Add a field to an existing table."""
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{table_id}/fields"
    if DRY_RUN:
        print(f"  [DRY RUN] Would add field '{field_def['name']}'")
        return
    api_request(url, method="POST", payload=field_def)
    print(f"  Added field '{field_def['name']}'")


def upsert_records(table_id: str, table_name: str, records: list[dict],
                   merge_field: str) -> int:
    """Upsert records in batches of 10. Returns total upserted.

    If a batch fails with a duplicate-merge error, retries records
    individually so one bad record doesn't block the rest.
    """
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    total = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        payload = {
            "records": [{"fields": rec} for rec in batch],
            "typecast": True,
            "performUpsert": {"fieldsToMergeOn": [merge_field]},
        }
        if DRY_RUN:
            print(f"  [DRY RUN] Would upsert batch {i//BATCH_SIZE + 1} "
                  f"({len(batch)} records) to '{table_name}'")
            total += len(batch)
            continue
        try:
            result = api_request(url, method="PATCH", payload=payload)
            created = sum(1 for r in result.get("createdRecords", []))
            updated = len(batch) - created
            total += len(batch)
            print(f"  Batch {i//BATCH_SIZE + 1}: {created} created, {updated} updated")
        except urllib.error.HTTPError as e:
            body = e.read().decode() if hasattr(e, "read") else ""
            if "Cannot update more than one record" in body or e.code == 422:
                print(f"  Batch {i//BATCH_SIZE + 1}: duplicate-merge error, retrying individually...")
                for rec in batch:
                    single_payload = {
                        "records": [{"fields": rec}],
                        "typecast": True,
                        "performUpsert": {"fieldsToMergeOn": [merge_field]},
                    }
                    try:
                        api_request(url, method="PATCH", payload=single_payload)
                        total += 1
                    except urllib.error.HTTPError as e2:
                        name_val = rec.get(merge_field, "?")
                        print(f"    SKIP '{name_val}': {e2.code} (duplicate in Airtable)")
            else:
                raise
    return total


def count_records(table_id: str) -> int:
    """Count all records in a table (paginated)."""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}?pageSize=100"
    count = 0
    offset = None
    while True:
        page_url = url + (f"&offset={offset}" if offset else "")
        data = api_request(page_url)
        count += len(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return count


def create_records(table_id: str, table_name: str, records: list[dict]) -> int:
    """Create records in batches of 10 (no upsert — for tables without unique key).
    Returns total created."""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    total = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        payload = {
            "records": [{"fields": rec} for rec in batch],
            "typecast": True,
        }
        if DRY_RUN:
            print(f"  [DRY RUN] Would create batch {i//BATCH_SIZE + 1} "
                  f"({len(batch)} records) in '{table_name}'")
            total += len(batch)
            continue
        result = api_request(url, method="POST", payload=payload)
        total += len(result.get("records", []))
        print(f"  Batch {i//BATCH_SIZE + 1}: {len(batch)} records created")
    return total


def delete_all_records(table_id: str, table_name: str) -> int:
    """Delete all records in a table. Returns count deleted."""
    url_base = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    total = 0

    # Collect all record IDs first
    record_ids = []
    offset = None
    while True:
        page_url = url_base + "?pageSize=100"
        if offset:
            page_url += f"&offset={offset}"
        data = api_request(page_url)
        record_ids.extend(r["id"] for r in data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    if not record_ids:
        return 0

    # Delete in batches of 10
    for i in range(0, len(record_ids), BATCH_SIZE):
        batch = record_ids[i:i + BATCH_SIZE]
        params = "&".join(f"records[]={rid}" for rid in batch)
        delete_url = f"{url_base}?{params}"
        if DRY_RUN:
            print(f"  [DRY RUN] Would delete batch {i//BATCH_SIZE + 1} "
                  f"({len(batch)} records) from '{table_name}'")
            total += len(batch)
            continue
        api_request(delete_url, method="DELETE")
        total += len(batch)
        print(f"  Deleted batch {i//BATCH_SIZE + 1}: {len(batch)} records")

    return total


# ---------------------------------------------------------------------------
# CSV readers
# ---------------------------------------------------------------------------
def read_csv(filename: str) -> list[dict]:
    """Read a CSV from scripts/vaxt/."""
    path = SCRIPT_DIR / filename
    if not path.exists():
        print(f"  WARNING: {path} not found, skipping")
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Step 1: Add enrichment fields to Varieties
# ---------------------------------------------------------------------------
def add_varieties_enrichment_fields(tables: dict) -> None:
    """Add growing enrichment fields to Varieties if missing."""
    print("\n== Step 1: Varieties enrichment fields ==")
    var_table = tables.get("Varieties")
    if not var_table:
        print("  ERROR: Varieties table not found!")
        return

    enrichment_fields = [
        {"name": "Seeding Rate", "type": "singleLineText"},
        {"name": "Seeding Depth", "type": "singleLineText"},
        {"name": "Seeding Window", "type": "singleLineText"},
        {"name": "Days to Maturity", "type": "singleLineText"},
        {"name": "Row Spacing", "type": "singleLineText"},
        {"name": "Harvest Notes", "type": "multilineText"},
        {"name": "Seed Sources", "type": "singleLineText"},
        {"name": "Grower Tips", "type": "multilineText"},
        {"name": "End Use", "type": "multipleSelects",
         "options": {"choices": [
             {"name": "bread"}, {"name": "sourdough"}, {"name": "pastry"},
             {"name": "malt"}, {"name": "distilling"}, {"name": "feed"},
             {"name": "forage"}, {"name": "fresh eating"}, {"name": "juice/wine"},
             {"name": "dual-purpose"},
         ]}},
        {"name": "Bread Notes", "type": "multilineText"},
        {"name": "Malt Profile", "type": "multilineText"},
        {"name": "Falling Number", "type": "singleLineText"},
        {"name": "Test Weight", "type": "singleLineText"},
        # Malting fields
        {"name": "Malt Type", "type": "singleSelect", "options": {"choices": [
            {"name": "base"}, {"name": "specialty"}, {"name": "crystal"},
            {"name": "roasted"}, {"name": "distilling"},
        ]}},
        {"name": "Modification", "type": "singleSelect", "options": {"choices": [
            {"name": "low"}, {"name": "medium"}, {"name": "high"}, {"name": "very_high"},
        ]}},
        {"name": "Diastatic Power", "type": "singleLineText"},
        {"name": "Color Lovibond", "type": "singleLineText"},
        {"name": "Extract Potential %", "type": "singleLineText"},
        {"name": "Kilning Notes", "type": "multilineText"},
        # Milling fields
        {"name": "Flour Extraction %", "type": "singleLineText"},
        {"name": "Ash Content %", "type": "singleLineText"},
        {"name": "Gluten Strength", "type": "singleSelect", "options": {"choices": [
            {"name": "weak"}, {"name": "medium"}, {"name": "strong"}, {"name": "very_strong"},
        ]}},
        {"name": "Water Absorption %", "type": "singleLineText"},
        {"name": "Ideal Stone Type", "type": "singleLineText"},
        {"name": "Milling Notes", "type": "multilineText"},
    ]

    existing = var_table["fields"]
    added = 0
    for fdef in enrichment_fields:
        if fdef["name"] not in existing:
            add_field(var_table["id"], fdef)
            added += 1
        else:
            print(f"  Field '{fdef['name']}' already exists, skipping")

    print(f"  Total: {added} fields added to Varieties")


# ---------------------------------------------------------------------------
# Step 2: Upsert variety growing enrichment data
# ---------------------------------------------------------------------------
def upsert_variety_enrichment(tables: dict) -> None:
    """Upsert variety_growing_enrichment.csv into Varieties."""
    print("\n== Step 2: Variety growing enrichment ==")
    var_table = tables.get("Varieties")
    if not var_table:
        return

    rows = read_csv("variety_growing_enrichment.csv")
    if not rows:
        return

    records = []
    for row in rows:
        rec = {"Name": row["variety"]}
        if row.get("seeding_rate"):
            rec["Seeding Rate"] = row["seeding_rate"]
        if row.get("seeding_depth"):
            rec["Seeding Depth"] = row["seeding_depth"]
        if row.get("seeding_window"):
            rec["Seeding Window"] = row["seeding_window"]
        if row.get("days_to_maturity"):
            rec["Days to Maturity"] = row["days_to_maturity"]
        if row.get("row_spacing"):
            rec["Row Spacing"] = row["row_spacing"]
        if row.get("harvest_notes"):
            rec["Harvest Notes"] = row["harvest_notes"]
        if row.get("seed_sources"):
            rec["Seed Sources"] = row["seed_sources"]
        if row.get("grower_tips"):
            rec["Grower Tips"] = row["grower_tips"]
        if row.get("bread_notes"):
            rec["Bread Notes"] = row["bread_notes"]
        if row.get("malt_profile"):
            rec["Malt Profile"] = row["malt_profile"]
        if row.get("falling_number"):
            rec["Falling Number"] = row["falling_number"]
        if row.get("test_weight"):
            rec["Test Weight"] = row["test_weight"]
        if row.get("sourdough_notes"):
            rec["Sourdough Notes"] = row["sourdough_notes"]
        if row.get("end_use"):
            rec["End Use"] = [u.strip() for u in row["end_use"].split(";") if u.strip()]
        if row.get("species"):
            rec["Species"] = row["species"]
        # Malting fields
        if row.get("malt_type"):
            rec["Malt Type"] = row["malt_type"]
        if row.get("modification"):
            rec["Modification"] = row["modification"]
        if row.get("diastatic_power"):
            rec["Diastatic Power"] = row["diastatic_power"]
        if row.get("color_lovibond"):
            rec["Color Lovibond"] = row["color_lovibond"]
        if row.get("extract_potential_pct"):
            rec["Extract Potential %"] = row["extract_potential_pct"]
        if row.get("kilning_notes"):
            rec["Kilning Notes"] = row["kilning_notes"]
        # Milling fields
        if row.get("flour_extraction_pct"):
            rec["Flour Extraction %"] = row["flour_extraction_pct"]
        if row.get("ash_content_pct"):
            rec["Ash Content %"] = row["ash_content_pct"]
        if row.get("gluten_strength"):
            rec["Gluten Strength"] = row["gluten_strength"]
        if row.get("water_absorption_pct"):
            rec["Water Absorption %"] = row["water_absorption_pct"]
        if row.get("ideal_stone_type"):
            rec["Ideal Stone Type"] = row["ideal_stone_type"]
        if row.get("milling_notes"):
            rec["Milling Notes"] = row["milling_notes"]
        records.append(rec)

    total = upsert_records(var_table["id"], "Varieties", records, "Name")
    print(f"  Total: {total} varieties enriched")


# ---------------------------------------------------------------------------
# Step 3: Create & populate Distillery Profiles
# ---------------------------------------------------------------------------
def sync_distillery_profiles(tables: dict) -> str:
    """Create Distillery Profiles table if missing, upsert CSV data."""
    print("\n== Step 3: Distillery Profiles ==")
    table_name = "Distillery Profiles"

    if table_name not in tables:
        fields = [
            {"name": "Distillery ID", "type": "singleLineText"},
            {"name": "Name", "type": "singleLineText"},
            {"name": "Country", "type": "singleSelect", "options": {"choices": [
                {"name": "Sweden"}, {"name": "Denmark"}, {"name": "Finland"},
                {"name": "Norway"}, {"name": "Iceland"}, {"name": "Scotland"},
                {"name": "Ireland"}, {"name": "USA"}, {"name": "Canada"},
            ]}},
            {"name": "City", "type": "singleLineText"},
            {"name": "Founded", "type": "number", "options": {"precision": 0}},
            {"name": "Spirit Type", "type": "singleLineText"},
            {"name": "Heritage Focus", "type": "checkbox", "options": {"color": "greenBright", "icon": "check"}},
            {"name": "Malting", "type": "singleSelect", "options": {"choices": [
                {"name": "floor malted"}, {"name": "external maltster"},
                {"name": "mixed"}, {"name": "drum malted"},
            ]}},
            {"name": "Latitude", "type": "number", "options": {"precision": 4}},
            {"name": "Longitude", "type": "number", "options": {"precision": 4}},
            {"name": "Website", "type": "url"},
            {"name": "Notes", "type": "multilineText"},
            {"name": "Source", "type": "singleLineText"},
        ]
        table_id = create_table(table_name, fields)
    else:
        table_id = tables[table_name]["id"]
        print(f"  Table already exists: {table_id}")

    rows = read_csv("distillery_profiles.csv")
    if not rows:
        return table_id

    records = []
    for row in rows:
        rec = {
            "Distillery ID": row["distillery_id"],
            "Name": row["name"],
            "Country": row["country"],
            "City": row["city"],
            "Spirit Type": row["spirit_type"],
            "Malting": row["malting"] if row["malting"] not in ("TRUE", "FALSE") else "",
            "Heritage Focus": row.get("heritage_focus", "").upper() == "TRUE",
            "Notes": row.get("notes", ""),
            "Source": row.get("source", ""),
        }
        # Fix malting field — CSV has mixed (TRUE/FALSE for heritage_focus, text for malting)
        malting_val = row.get("malting", "")
        if malting_val and malting_val not in ("TRUE", "FALSE"):
            rec["Malting"] = malting_val

        if row.get("founded"):
            try:
                rec["Founded"] = int(row["founded"])
            except ValueError:
                pass
        if row.get("latitude"):
            try:
                rec["Latitude"] = float(row["latitude"])
            except ValueError:
                pass
        if row.get("longitude"):
            try:
                rec["Longitude"] = float(row["longitude"])
            except ValueError:
                pass
        if row.get("website"):
            rec["Website"] = row["website"]

        records.append(rec)

    total = upsert_records(table_id, table_name, records, "Distillery ID")
    print(f"  Total: {total} distillery profiles synced")
    return table_id


# ---------------------------------------------------------------------------
# Step 4: Create & populate Seed Sources
# ---------------------------------------------------------------------------
def sync_seed_sources(tables: dict) -> str:
    """Create Seed Sources table if missing, upsert CSV data."""
    print("\n== Step 4: Seed Sources ==")
    table_name = "Seed Sources"

    if table_name not in tables:
        fields = [
            {"name": "Source ID", "type": "singleLineText"},
            {"name": "Name", "type": "singleLineText"},
            {"name": "Type", "type": "singleSelect", "options": {"choices": [
                {"name": "gene_bank"}, {"name": "heritage_seed_company"},
                {"name": "commercial_nordic"}, {"name": "community"},
                {"name": "sourdough"}, {"name": "specialty"},
            ]}},
            {"name": "Country", "type": "singleSelect", "options": {"choices": [
                {"name": "Sweden"}, {"name": "Finland"}, {"name": "Norway"},
                {"name": "Denmark"}, {"name": "USA"}, {"name": "UK"},
                {"name": "Germany"}, {"name": "France"}, {"name": "Switzerland"},
                {"name": "Austria"}, {"name": "Lebanon"}, {"name": "Russia"},
                {"name": "other"},
            ]}},
            {"name": "Website", "type": "url"},
            {"name": "Ships To", "type": "singleLineText"},
            {"name": "Specialties", "type": "multilineText"},
            {"name": "Access", "type": "singleLineText"},
            {"name": "Notes", "type": "multilineText"},
            {"name": "Source", "type": "singleLineText"},
        ]
        table_id = create_table(table_name, fields)
    else:
        table_id = tables[table_name]["id"]
        print(f"  Table already exists: {table_id}")

    rows = read_csv("seed_sources.csv")
    if not rows:
        return table_id

    records = []
    for row in rows:
        rec = {}
        field_map = {
            "source_id": "Source ID", "name": "Name", "type": "Type",
            "country": "Country", "website": "Website", "ships_to": "Ships To",
            "specialties": "Specialties", "access": "Access",
            "notes": "Notes", "source": "Source",
        }
        for csv_key, at_key in field_map.items():
            if row.get(csv_key):
                rec[at_key] = row[csv_key]
        records.append(rec)

    total = upsert_records(table_id, table_name, records, "Source ID")
    print(f"  Total: {total} seed sources synced")
    return table_id


# ---------------------------------------------------------------------------
# Step 5: Create & populate Planting Calendars
# ---------------------------------------------------------------------------
def sync_planting_calendars(tables: dict) -> str:
    """Create Planting Calendars table if missing, upsert CSV data."""
    print("\n== Step 5: Planting Calendars ==")
    table_name = "Planting Calendars"

    if table_name not in tables:
        fields = [
            {"name": "Calendar ID", "type": "singleLineText"},
            {"name": "Zone", "type": "singleLineText"},
            {"name": "Crop", "type": "singleSelect", "options": {"choices": [
                {"name": "wheat"}, {"name": "rye"}, {"name": "barley"},
                {"name": "oat"}, {"name": "spelt"}, {"name": "emmer"},
                {"name": "einkorn"},
            ]}},
            {"name": "Type", "type": "singleSelect", "options": {"choices": [
                {"name": "winter"}, {"name": "spring"},
            ]}},
            {"name": "Sow Start", "type": "singleLineText"},
            {"name": "Sow End", "type": "singleLineText"},
            {"name": "Vernalization Weeks", "type": "singleLineText"},
            {"name": "Expected Harvest", "type": "singleLineText"},
            {"name": "Notes", "type": "multilineText"},
        ]
        table_id = create_table(table_name, fields)
    else:
        table_id = tables[table_name]["id"]
        print(f"  Table already exists: {table_id}")

    rows = read_csv("planting_calendars.csv")
    if not rows:
        return table_id

    records = []
    for row in rows:
        rec = {}
        field_map = {
            "calendar_id": "Calendar ID", "zone": "Zone", "crop": "Crop",
            "type": "Type", "sow_start": "Sow Start", "sow_end": "Sow End",
            "vernalization_weeks": "Vernalization Weeks",
            "expected_harvest": "Expected Harvest", "notes": "Notes",
        }
        for csv_key, at_key in field_map.items():
            if row.get(csv_key):
                rec[at_key] = row[csv_key]
        records.append(rec)

    total = upsert_records(table_id, table_name, records, "Calendar ID")
    print(f"  Total: {total} planting calendars synced")
    return table_id


# ---------------------------------------------------------------------------
# Step 6: Create & populate Sourdough Recipes
# ---------------------------------------------------------------------------
def sync_sourdough_recipes(tables: dict) -> str:
    """Create Sourdough Recipes table if missing, upsert CSV data."""
    print("\n== Step 6: Sourdough Recipes ==")
    table_name = "Sourdough Recipes"

    if table_name not in tables:
        fields = [
            {"name": "Starter ID", "type": "singleLineText"},
            {"name": "Recipe", "type": "singleLineText"},
            {"name": "Hydration %", "type": "number", "options": {"precision": 0}},
            {"name": "Flour Type", "type": "singleLineText"},
            {"name": "Fermentation Schedule", "type": "multilineText"},
            {"name": "Serving Notes", "type": "multilineText"},
            {"name": "Source", "type": "singleLineText"},
        ]
        table_id = create_table(table_name, fields)
    else:
        table_id = tables[table_name]["id"]
        print(f"  Table already exists: {table_id}")

    rows = read_csv("sourdough_recipes.csv")
    if not rows:
        return table_id

    records = []
    for row in rows:
        rec = {
            "Starter ID": row["starter_id"],
            "Recipe": row["recipe"],
            "Flour Type": row.get("flour_type", ""),
            "Fermentation Schedule": row.get("fermentation_schedule", ""),
            "Serving Notes": row.get("serving_notes", ""),
            "Source": row.get("source", ""),
        }
        if row.get("hydration_pct"):
            try:
                rec["Hydration %"] = int(row["hydration_pct"])
            except ValueError:
                pass
        records.append(rec)

    total = upsert_records(table_id, table_name, records, "Starter ID")
    print(f"  Total: {total} sourdough recipes synced")
    return table_id


# ---------------------------------------------------------------------------
# Step 6b: Create & populate Community Grain Projects
# ---------------------------------------------------------------------------
def sync_community_grain_projects(tables: dict) -> str:
    """Create Community Grain Projects table if missing, upsert CSV data."""
    print("\n== Step 6b: Community Grain Projects ==")
    table_name = "Community Grain Projects"

    if table_name not in tables:
        fields = [
            {"name": "Project ID", "type": "singleLineText"},
            {"name": "Name", "type": "singleLineText"},
            {"name": "Country", "type": "singleSelect", "options": {"choices": [
                {"name": "Sweden"}, {"name": "Norway"}, {"name": "Finland"},
                {"name": "Denmark"}, {"name": "Iceland"}, {"name": "Faroe Islands"},
                {"name": "United Kingdom"}, {"name": "France"}, {"name": "Germany"},
                {"name": "Austria"}, {"name": "Switzerland"}, {"name": "Latvia"},
                {"name": "Estonia"}, {"name": "Lithuania"}, {"name": "Russia"},
                {"name": "USA"}, {"name": "Canada"},
            ]}},
            {"name": "City", "type": "singleLineText"},
            {"name": "Latitude", "type": "number", "options": {"precision": 4}},
            {"name": "Longitude", "type": "number", "options": {"precision": 4}},
            {"name": "Crops", "type": "multipleSelects", "options": {"choices": [
                {"name": "wheat"}, {"name": "rye"}, {"name": "barley"}, {"name": "oat"},
                {"name": "spelt"}, {"name": "einkorn"}, {"name": "emmer"},
                {"name": "triticale"}, {"name": "pea"}, {"name": "faba bean"},
            ]}},
            {"name": "Founded Year", "type": "number", "options": {"precision": 0}},
            {"name": "Members", "type": "number", "options": {"precision": 0}},
            {"name": "Hectares", "type": "number", "options": {"precision": 1}},
            {"name": "Model", "type": "singleSelect", "options": {"choices": [
                {"name": "co-op"}, {"name": "seed_commons"}, {"name": "csa"},
                {"name": "guild"}, {"name": "community_garden"},
                {"name": "community_mill"}, {"name": "grain_csa"},
                {"name": "seed_library"}, {"name": "research_network"},
            ]}},
            {"name": "Focus", "type": "multipleSelects", "options": {"choices": [
                {"name": "seed_saving"}, {"name": "grain_growing"},
                {"name": "milling"}, {"name": "baking"}, {"name": "education"},
                {"name": "breeding"}, {"name": "marketing"},
                {"name": "heritage_conservation"},
            ]}},
            {"name": "Varieties Grown", "type": "singleLineText"},
            {"name": "Website", "type": "url"},
            {"name": "Notes", "type": "multilineText"},
            {"name": "Source", "type": "singleLineText"},
        ]
        table_id = create_table(table_name, fields)
    else:
        table_id = tables[table_name]["id"]
        print(f"  Table already exists: {table_id}")

    rows = read_csv("community_grain_projects.csv")
    if not rows:
        return table_id

    records = []
    for row in rows:
        rec = {
            "Project ID": row["project_id"],
            "Name": row["name"],
            "Country": row["country"],
            "City": row.get("city", ""),
            "Model": row.get("model", ""),
            "Varieties Grown": row.get("varieties_grown", ""),
            "Notes": row.get("notes", ""),
            "Source": row.get("source", ""),
        }
        if row.get("latitude"):
            try:
                rec["Latitude"] = float(row["latitude"])
            except ValueError:
                pass
        if row.get("longitude"):
            try:
                rec["Longitude"] = float(row["longitude"])
            except ValueError:
                pass
        if row.get("crops"):
            rec["Crops"] = [c.strip() for c in row["crops"].split(";") if c.strip()]
        if row.get("founded_year"):
            try:
                rec["Founded Year"] = int(row["founded_year"])
            except ValueError:
                pass
        if row.get("members"):
            try:
                rec["Members"] = int(row["members"])
            except ValueError:
                pass
        if row.get("hectares"):
            try:
                rec["Hectares"] = float(row["hectares"])
            except ValueError:
                pass
        if row.get("focus"):
            rec["Focus"] = [f.strip() for f in row["focus"].split(";") if f.strip()]
        if row.get("website"):
            rec["Website"] = row["website"]
        records.append(rec)

    total = upsert_records(table_id, table_name, records, "Project ID")
    print(f"  Total: {total} community grain projects synced")
    return table_id


# ---------------------------------------------------------------------------
# Step 7: Backfill Disease Resistance
# ---------------------------------------------------------------------------
def backfill_disease_resistance(tables: dict) -> None:
    """Backfill Disease Resistance from CSV.

    The primary field 'Variety or Gene' has duplicates (same variety tested
    against different pathogens). Since upsert requires a unique merge key,
    we use batch create: clear existing records and re-create from CSV.
    Skips if count already matches.
    """
    print("\n== Step 7: Disease Resistance (backfill) ==")
    table_name = "Disease Resistance"
    if table_name not in tables:
        print("  ERROR: Disease Resistance table not found!")
        return

    table_id = tables[table_name]["id"]
    csv_rows = read_csv("disease_resistance.csv")
    if not csv_rows:
        return

    db_count = count_records(table_id)
    csv_count = len(csv_rows)

    print(f"  Airtable: {db_count} records")
    print(f"  CSV:      {csv_count} records")

    if db_count >= csv_count:
        print(f"  OK — Airtable already has >= CSV count, skipping")
        return

    # Clear stale records (partial data from previous runs)
    if db_count > 0:
        print(f"  Clearing {db_count} existing records before full reload...")
        delete_all_records(table_id, table_name)

    records = []
    for row in csv_rows:
        rec = {
            "Variety or Gene": row["variety_or_gene"],
            "Crop": row.get("crop", ""),
            "Pathogen": row.get("pathogen", ""),
            "Resistance Level": row.get("resistance_level", ""),
            "Mechanism": row.get("mechanism", ""),
            "Test Method": row.get("test_method", ""),
            "Region": row.get("region", ""),
            "Source": row.get("source", ""),
        }
        records.append(rec)

    total = create_records(table_id, table_name, records)
    print(f"  Total: {total} disease resistance records created")


# ---------------------------------------------------------------------------
# Step 8: Backfill Sourdough Starters
# ---------------------------------------------------------------------------
def backfill_sourdough_starters(tables: dict) -> None:
    """Backfill Sourdough Starters from CSV (table exists but sparse)."""
    print("\n== Step 8: Sourdough Starters (backfill) ==")
    table_name = "Sourdough Starters"
    if table_name not in tables:
        print("  ERROR: Sourdough Starters table not found!")
        return

    table_id = tables[table_name]["id"]
    csv_rows = read_csv("sourdough_starters.csv")
    if not csv_rows:
        return

    db_count = count_records(table_id)
    print(f"  Airtable: {db_count} records")
    print(f"  CSV:      {len(csv_rows)} records")

    records = []
    for row in csv_rows:
        rec = {
            "Starter ID": row["starter_id"],
            "Name": row.get("name", ""),
            "Origin Country": row.get("origin_country", ""),
            "Origin City": row.get("origin_city", ""),
            "Grain Base": row.get("grain_base", ""),
            "Flavor Profile": row.get("flavor_profile", ""),
            "Preservation Method": row.get("preservation_method", ""),
            "Culture Type": row.get("culture_type", ""),
            "Notes": row.get("notes", ""),
            "Source": row.get("source_bakery", ""),
        }
        if row.get("estimated_age_years"):
            try:
                rec["Estimated Age (years)"] = int(row["estimated_age_years"])
            except ValueError:
                pass
        records.append(rec)

    total = upsert_records(table_id, table_name, records, "Starter ID")
    print(f"  Total: {total} sourdough starters synced")


# ---------------------------------------------------------------------------
# Step 9: Backfill Crop Wild Relatives
# ---------------------------------------------------------------------------
def backfill_crop_wild_relatives(tables: dict) -> None:
    """Backfill Crop Wild Relatives from CSV (table exists but sparse)."""
    print("\n== Step 9: Crop Wild Relatives (backfill) ==")
    table_name = "Crop Wild Relatives"
    if table_name not in tables:
        print("  ERROR: Crop Wild Relatives table not found!")
        return

    table_id = tables[table_name]["id"]
    csv_rows = read_csv("crop_wild_relatives.csv")
    if not csv_rows:
        return

    db_count = count_records(table_id)
    print(f"  Airtable: {db_count} records")
    print(f"  CSV:      {len(csv_rows)} records")

    records = []
    for row in csv_rows:
        rec = {
            "Species": row["species"],
            "Common Name": row.get("common_name", ""),
            "Family": row.get("family", ""),
            "Crop Group": row.get("crop_group", ""),
            "Domesticated Relative": row.get("domesticated_relative", ""),
            "Native Range": row.get("native_range", ""),
            "USDA Zone": row.get("usda_zone", ""),
            "Notes": row.get("notes", ""),
            "Source": row.get("source", ""),
        }
        if row.get("min_survival_temp_c"):
            try:
                rec["Min Survival Temp (°C)"] = float(row["min_survival_temp_c"])
            except ValueError:
                pass
        records.append(rec)

    total = upsert_records(table_id, table_name, records, "Species")
    print(f"  Total: {total} crop wild relatives synced")


# ---------------------------------------------------------------------------
# Step 10: Backfill Rootstock Compatibility
# ---------------------------------------------------------------------------
def backfill_rootstock_compatibility(tables: dict) -> None:
    """Backfill Rootstock Compatibility from CSV (table exists but sparse)."""
    print("\n== Step 10: Rootstock Compatibility (backfill) ==")
    table_name = "Rootstock Compatibility"
    if table_name not in tables:
        print("  ERROR: Rootstock Compatibility table not found!")
        return

    table_id = tables[table_name]["id"]
    csv_rows = read_csv("rootstock_compatibility.csv")
    if not csv_rows:
        return

    db_count = count_records(table_id)
    print(f"  Airtable: {db_count} records")
    print(f"  CSV:      {len(csv_rows)} records")

    records = []
    for row in csv_rows:
        rec = {
            "Rootstock": row["rootstock"],
            "Rootstock Species": row.get("rootstock_species", ""),
            "Crop Group": row.get("crop_group", ""),
            "Compatible Scions": row.get("compatible_scions", ""),
            "Cold Hardiness Zone": row.get("cold_hardiness_zone", ""),
            "Dwarfing": row.get("dwarfing", ""),
            "Disease Notes": row.get("disease_notes", ""),
            "Source": row.get("source", ""),
        }
        if row.get("trunk_hardiness_c"):
            try:
                rec["Trunk Hardiness (°C)"] = float(row["trunk_hardiness_c"])
            except ValueError:
                pass
        if row.get("root_hardiness_c"):
            try:
                rec["Root Hardiness (°C)"] = float(row["root_hardiness_c"])
            except ValueError:
                pass
        records.append(rec)

    total = upsert_records(table_id, table_name, records, "Rootstock")
    print(f"  Total: {total} rootstock compatibility records synced")


# ---------------------------------------------------------------------------
# Step 11: Backfill Climate Zones
# ---------------------------------------------------------------------------
def backfill_climate_zones(tables: dict) -> None:
    """Backfill Climate Zones from CSV (table exists but sparse).

    Zone is a number field and each zone has a/b subzones, so the primary
    field isn't unique. We use batch create (not upsert) and skip if the
    table already has >= CSV row count.
    """
    print("\n== Step 11: Climate Zones (backfill) ==")
    table_name = "Climate Zones"
    if table_name not in tables:
        print("  ERROR: Climate Zones table not found!")
        return

    table_id = tables[table_name]["id"]
    csv_rows = read_csv("climate_zones.csv")
    if not csv_rows:
        return

    db_count = count_records(table_id)
    csv_count = len(csv_rows)
    print(f"  Airtable: {db_count} records")
    print(f"  CSV:      {csv_count} records")

    if db_count >= csv_count:
        print(f"  OK — Airtable already has >= CSV count, skipping")
        return

    # Clear stale records (sparse placeholder data)
    if db_count > 0:
        print(f"  Clearing {db_count} existing records before full reload...")
        delete_all_records(table_id, table_name)

    print(f"  Creating {csv_count} records (batch create, no upsert — Zone is non-unique)...")

    records = []
    for row in csv_rows:
        rec = {
            "Subzone": row.get("subzone", ""),
            "Example Locations": row.get("example_locations", ""),
            "Relevance": row.get("relevance", ""),
        }
        if row.get("zone"):
            try:
                rec["Zone"] = int(row["zone"])
            except ValueError:
                pass
        if row.get("min_temp_c"):
            try:
                rec["Min Temp (°C)"] = float(row["min_temp_c"])
            except ValueError:
                pass
        if row.get("max_temp_c"):
            try:
                rec["Max Temp (°C)"] = float(row["max_temp_c"])
            except ValueError:
                pass
        records.append(rec)

    total = create_records(table_id, table_name, records)
    print(f"  Total: {total} climate zones created")


# ---------------------------------------------------------------------------
# Step 12: Backfill Breeding Programs
# ---------------------------------------------------------------------------
def backfill_breeding_programs(tables: dict) -> None:
    """Backfill Breeding Programs from CSV (table may have partial data)."""
    print("\n== Step 12: Breeding Programs (backfill) ==")
    table_name = "Breeding Programs"
    if table_name not in tables:
        print("  ERROR: Breeding Programs table not found!")
        return

    table_id = tables[table_name]["id"]
    csv_rows = read_csv("breeding_programs.csv")
    if not csv_rows:
        return

    db_count = count_records(table_id)
    print(f"  Airtable: {db_count} records")
    print(f"  CSV:      {len(csv_rows)} records")

    records = []
    for row in csv_rows:
        rec = {
            "Program ID": row["program_id"],
            "Institution": row.get("institution", ""),
            "Country": row.get("country", ""),
            "City": row.get("city", ""),
            "Crops": row.get("crops", ""),
            "Focus Areas": row.get("focus_areas", ""),
            "Notable Releases": row.get("notable_releases", ""),
            "Source": row.get("source", ""),
        }
        if row.get("latitude"):
            try:
                rec["Latitude"] = float(row["latitude"])
            except ValueError:
                pass
        if row.get("longitude"):
            try:
                rec["Longitude"] = float(row["longitude"])
            except ValueError:
                pass
        if row.get("established_year"):
            try:
                rec["Established Year"] = int(row["established_year"])
            except ValueError:
                pass
        if row.get("website"):
            rec["Website"] = row["website"]
        records.append(rec)

    total = upsert_records(table_id, table_name, records, "Program ID")
    print(f"  Total: {total} breeding programs synced")


# ---------------------------------------------------------------------------
# Step 14: Backfill Cold Tolerance Markers
# ---------------------------------------------------------------------------
def backfill_cold_tolerance_markers(tables: dict) -> None:
    """Backfill Cold Tolerance Markers from CSV.

    The primary field 'species' has duplicates (same species has many markers).
    Use delete+recreate pattern (like Disease Resistance). Skips if count matches.
    """
    print("\n== Step 14: Cold Tolerance Markers (backfill) ==")
    table_name = "Cold Tolerance Markers"
    if table_name not in tables:
        # Create the table if it doesn't exist
        fields = [
            {"name": "Species", "type": "singleLineText"},
            {"name": "Locus", "type": "singleLineText"},
            {"name": "Chromosome", "type": "singleLineText"},
            {"name": "Gene", "type": "singleLineText"},
            {"name": "Marker", "type": "singleLineText"},
            {"name": "Marker Type", "type": "singleSelect", "options": {"choices": [
                {"name": "operational"}, {"name": "co-localized"},
                {"name": "functional"}, {"name": "flanking"},
                {"name": "QTL"}, {"name": "meta-QTL"},
                {"name": "candidate"}, {"name": "haplotype"},
            ]}},
            {"name": "Frost Tolerance %", "type": "singleLineText"},
            {"name": "Notes", "type": "multilineText"},
            {"name": "Source", "type": "singleLineText"},
        ]
        table_id = create_table(table_name, fields)
        if DRY_RUN:
            table_id = "dry_run_id"
    else:
        table_id = tables[table_name]["id"]

    csv_rows = read_csv("cold_tolerance_markers.csv")
    if not csv_rows:
        return

    db_count = count_records(table_id) if not DRY_RUN or table_name in tables else 0
    csv_count = len(csv_rows)
    print(f"  Airtable: {db_count} records")
    print(f"  CSV:      {csv_count} records")

    if db_count >= csv_count:
        print(f"  OK — Airtable already has >= CSV count, skipping")
        return

    # Clear stale records before full reload
    if db_count > 0:
        print(f"  Clearing {db_count} existing records before full reload...")
        delete_all_records(table_id, table_name)

    records = []
    for row in csv_rows:
        rec = {
            "Species": row.get("species", ""),
            "Locus": row.get("locus", ""),
            "Chromosome": row.get("chromosome", ""),
            "Gene": row.get("gene", ""),
            "Marker": row.get("marker", ""),
            "Notes": row.get("notes", ""),
            "Source": row.get("source", ""),
        }
        if row.get("marker_type"):
            rec["Marker Type"] = row["marker_type"]
        if row.get("frost_tolerance_pct"):
            rec["Frost Tolerance %"] = row["frost_tolerance_pct"]
        records.append(rec)

    total = create_records(table_id, table_name, records)
    print(f"  Total: {total} cold tolerance markers created")


# ---------------------------------------------------------------------------
# Step 15: Backfill Field Trial Sites
# ---------------------------------------------------------------------------
def backfill_field_trial_sites(tables: dict) -> None:
    """Backfill Field Trial Sites from CSV. site_id is unique → upsert."""
    print("\n== Step 15: Field Trial Sites (backfill) ==")
    table_name = "Field Trial Sites"
    if table_name not in tables:
        fields = [
            {"name": "Site ID", "type": "singleLineText"},
            {"name": "Name", "type": "singleLineText"},
            {"name": "Institution", "type": "singleLineText"},
            {"name": "Country", "type": "singleSelect", "options": {"choices": [
                {"name": "Norway"}, {"name": "Finland"}, {"name": "Sweden"},
                {"name": "Denmark"}, {"name": "Iceland"}, {"name": "Canada"},
                {"name": "USA"}, {"name": "other"},
            ]}},
            {"name": "Latitude", "type": "number", "options": {"precision": 4}},
            {"name": "Longitude", "type": "number", "options": {"precision": 4}},
            {"name": "Elevation (m)", "type": "number", "options": {"precision": 0}},
            {"name": "USDA Zone", "type": "singleLineText"},
            {"name": "Mean Jan Temp (°C)", "type": "number", "options": {"precision": 1}},
            {"name": "Record Low (°C)", "type": "number", "options": {"precision": 1}},
            {"name": "Snow Cover Days", "type": "number", "options": {"precision": 0}},
            {"name": "Trial Types", "type": "singleLineText"},
            {"name": "Crops Tested", "type": "singleLineText"},
            {"name": "Active", "type": "checkbox", "options": {"color": "greenBright", "icon": "check"}},
            {"name": "Source", "type": "singleLineText"},
        ]
        table_id = create_table(table_name, fields)
        if DRY_RUN:
            table_id = "dry_run_id"
    else:
        table_id = tables[table_name]["id"]
        # Ensure all expected fields exist (table may predate newer columns)
        expected_fields = [
            {"name": "Institution", "type": "singleLineText"},
            {"name": "Mean Jan Temp (°C)", "type": "number", "options": {"precision": 1}},
            {"name": "Record Low (°C)", "type": "number", "options": {"precision": 1}},
            {"name": "Snow Cover Days", "type": "number", "options": {"precision": 0}},
            {"name": "Elevation (m)", "type": "number", "options": {"precision": 0}},
        ]
        existing = tables[table_name].get("fields", {})
        for fdef in expected_fields:
            if fdef["name"] not in existing:
                add_field(table_id, fdef)

    csv_rows = read_csv("field_trial_sites.csv")
    if not csv_rows:
        return

    db_count = count_records(table_id) if not DRY_RUN or table_name in tables else 0
    print(f"  Airtable: {db_count} records")
    print(f"  CSV:      {len(csv_rows)} records")

    records = []
    for row in csv_rows:
        rec = {
            "Site ID": row["site_id"],
            "Name": row.get("name", ""),
            "Institution": row.get("institution", ""),
            "USDA Zone": row.get("usda_zone", ""),
            "Trial Types": row.get("trial_types", ""),
            "Crops Tested": row.get("crops_tested", ""),
            "Active": row.get("active", "").lower() == "yes",
            "Source": row.get("source", ""),
        }
        if row.get("country"):
            rec["Country"] = row["country"]
        for csv_key, at_key in [("latitude", "Latitude"), ("longitude", "Longitude")]:
            if row.get(csv_key):
                try:
                    rec[at_key] = float(row[csv_key])
                except ValueError:
                    pass
        if row.get("elevation_m"):
            try:
                rec["Elevation (m)"] = int(float(row["elevation_m"]))
            except ValueError:
                pass
        if row.get("mean_jan_temp_c"):
            try:
                rec["Mean Jan Temp (°C)"] = float(row["mean_jan_temp_c"])
            except ValueError:
                pass
        if row.get("record_low_c"):
            try:
                rec["Record Low (°C)"] = float(row["record_low_c"])
            except ValueError:
                pass
        if row.get("snow_cover_days"):
            try:
                rec["Snow Cover Days"] = int(row["snow_cover_days"])
            except ValueError:
                pass
        records.append(rec)

    total = upsert_records(table_id, table_name, records, "Site ID")
    print(f"  Total: {total} field trial sites synced")


# ---------------------------------------------------------------------------
# Step 16: Backfill GRIN Accessions
# ---------------------------------------------------------------------------
def backfill_grin_accessions(tables: dict) -> None:
    """Backfill GRIN Accessions from CSV. pi_number is unique → upsert."""
    print("\n== Step 16: GRIN Accessions (backfill) ==")
    table_name = "GRIN Accessions"
    if table_name not in tables:
        fields = [
            {"name": "PI Number", "type": "singleLineText"},
            {"name": "Species", "type": "singleLineText"},
            {"name": "Common Name", "type": "singleLineText"},
            {"name": "Crop Group", "type": "singleSelect", "options": {"choices": [
                {"name": "cereal"}, {"name": "fruit"}, {"name": "forage"},
                {"name": "other"},
            ]}},
            {"name": "Origin Country", "type": "singleLineText"},
            {"name": "Improvement Status", "type": "singleSelect", "options": {"choices": [
                {"name": "landrace"}, {"name": "cultivar"}, {"name": "wild"},
                {"name": "breeding material"}, {"name": "other"},
            ]}},
            {"name": "Cold Hardiness Zone", "type": "singleLineText"},
            {"name": "Collection Site", "type": "singleLineText"},
            {"name": "Latitude", "type": "number", "options": {"precision": 2}},
            {"name": "Longitude", "type": "number", "options": {"precision": 2}},
            {"name": "Traits", "type": "singleLineText"},
            {"name": "Notes", "type": "multilineText"},
            {"name": "Source", "type": "singleLineText"},
        ]
        table_id = create_table(table_name, fields)
        if DRY_RUN:
            table_id = "dry_run_id"
    else:
        table_id = tables[table_name]["id"]
        # Ensure all expected fields exist (table may predate newer columns)
        expected_fields = [
            {"name": "Collection Site", "type": "singleLineText"},
            {"name": "Latitude", "type": "number", "options": {"precision": 2}},
            {"name": "Longitude", "type": "number", "options": {"precision": 2}},
        ]
        existing = tables[table_name].get("fields", {})
        for fdef in expected_fields:
            if fdef["name"] not in existing:
                add_field(table_id, fdef)

    csv_rows = read_csv("grin_accessions.csv")
    if not csv_rows:
        return

    db_count = count_records(table_id) if not DRY_RUN or table_name in tables else 0
    print(f"  Airtable: {db_count} records")
    print(f"  CSV:      {len(csv_rows)} records")

    records = []
    for row in csv_rows:
        rec = {
            "PI Number": row["pi_number"],
            "Species": row.get("species", ""),
            "Common Name": row.get("common_name", ""),
            "Origin Country": row.get("origin_country", ""),
            "Cold Hardiness Zone": row.get("cold_hardiness_zone", ""),
            "Collection Site": row.get("collection_site", ""),
            "Traits": row.get("traits", ""),
            "Notes": row.get("notes", ""),
            "Source": row.get("source", ""),
        }
        if row.get("crop_group"):
            rec["Crop Group"] = row["crop_group"]
        if row.get("improvement_status"):
            rec["Improvement Status"] = row["improvement_status"]
        for csv_key, at_key in [("latitude", "Latitude"), ("longitude", "Longitude")]:
            if row.get(csv_key):
                try:
                    rec[at_key] = float(row[csv_key])
                except ValueError:
                    pass
        records.append(rec)

    total = upsert_records(table_id, table_name, records, "PI Number")
    print(f"  Total: {total} GRIN accessions synced")


# ---------------------------------------------------------------------------
# Step 13: Full Varieties Backfill from nordic_variety_trait_index.csv
# ---------------------------------------------------------------------------

# Normalize granular CSV crop values to Airtable Crop single-select options.
# Detail (winter/spring, row type) is preserved in Cold Tolerance Notes.
CROP_NORMALIZE = {
    "wheat": "wheat",
    "wheat (winter)": "wheat",
    "wheat (spring)": "wheat",
    "rye": "rye",
    "rye (winter)": "rye",
    "barley (spring 6-row)": "barley",
    "barley (spring 2-row)": "barley",
    "barley (winter 2-row)": "barley",
    "barley (winter 6-row)": "barley",
    "oat (spring)": "oat",
    "triticale (winter)": "other",
    "apple": "apple",
    "grape": "grape",
    "grape (white wine)": "grape",
    "grape (red wine)": "grape",
    "grape (table)": "grape",
    "grape (table/wine)": "grape",
    "grape (table/juice)": "grape",
    "grape (seedless table)": "grape",
    "haskap": "haskap",
    "sea buckthorn": "sea buckthorn",
    "lingonberry": "lingonberry",
    "arctic bramble": "arctic bramble",
    "black currant": "other",
    "red currant": "other",
    "gooseberry": "other",
    "raspberry": "other",
    "blueberry (half-high)": "other",
    "blueberry (highbush)": "other",
    "saskatoon berry": "other",
    "cloudberry (female)": "other",
    "cloudberry (male)": "other",
    "cloudberry (hermaphrodite)": "other",
    "plum": "other",
    "sour cherry (bush)": "other",
    "sour cherry (tree)": "other",
    "cherry-plum": "other",
    "pear": "other",
    "pear (Asian)": "other",
    "apricot": "other",
    "timothy": "forage grass",
    "meadow fescue": "forage grass",
    "perennial ryegrass": "forage grass",
    "red clover": "forage grass",
    "white clover": "forage grass",
    "festulolium": "forage grass",
}

# Country normalization — handle multi-country and non-standard entries
COUNTRY_NORMALIZE = {
    "Germany/UK": "Germany",
    "Czech Republic": "other",
    "China": "other",
    "Japan": "other",
    "Netherlands": "other",
    "UK": "other",
    "Italy": "other",
}


def backfill_all_varieties(tables: dict) -> None:
    """Backfill all ~194 varieties from nordic_variety_trait_index.csv.

    Uses upsert on Name — existing records are updated (empty fields filled),
    new records are created. Does NOT overwrite enrichment fields (seeding rate
    etc.) since we only send base fields from this CSV.
    """
    print("\n== Step 13: Varieties full backfill ==")
    var_table = tables.get("Varieties")
    if not var_table:
        print("  ERROR: Varieties table not found!")
        return

    table_id = var_table["id"]
    csv_rows = read_csv("nordic_variety_trait_index.csv")
    if not csv_rows:
        return

    db_count = count_records(table_id)
    print(f"  Airtable: {db_count} records")
    print(f"  CSV:      {len(csv_rows)} records")

    records = []
    for row in csv_rows:
        raw_crop = row.get("crop", "").strip()
        crop = CROP_NORMALIZE.get(raw_crop, "other")

        # Build cold tolerance notes — prepend crop qualifier if normalized away
        notes = row.get("cold_tolerance_notes", "").strip()
        if raw_crop != crop and raw_crop:
            qualifier = f"[{raw_crop}]"
            if notes:
                notes = f"{qualifier} {notes}"
            else:
                notes = qualifier

        # Normalize country
        raw_country = row.get("country", "").strip()
        country = COUNTRY_NORMALIZE.get(raw_country, raw_country)

        # Parse traits — semicolon-separated → list for Multiple Select
        raw_traits = row.get("traits", "").strip()
        traits = [t.strip() for t in raw_traits.split(";") if t.strip()] if raw_traits else []

        rec = {"Name": row["variety"].strip()}

        if crop:
            rec["Crop"] = crop
        if country:
            rec["Country"] = country
        if notes:
            rec["Cold Tolerance Notes"] = notes
        if row.get("usda_zone", "").strip():
            rec["USDA Zone"] = row["usda_zone"].strip()
        if row.get("source", "").strip():
            rec["Source"] = row["source"].strip()
        if traits:
            rec["Traits"] = traits

        records.append(rec)

    total = upsert_records(table_id, "Varieties", records, "Name")
    print(f"  Total: {total} varieties upserted ({len(csv_rows)} from CSV, "
          f"~{len(csv_rows) - db_count} new)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Step 14: Crop field hygiene — patch empty Crop values
# ---------------------------------------------------------------------------
CROP_OVERRIDES = {
    "Antonovka": "apple",
    "Frankenkorn": "spelt",
    "Oberkulmer Rotkorn": "spelt",
}

# Varieties that must have Website Featured = True
FEATURED_OVERRIDES = [
    "Dala Lantvete", "Einkorn", "Emmer", "Glenn", "Jagger",
    "Kungs-Rye", "Marquis", "Oberkulmer Rotkorn", "Red Fife",
    "Rouge de Bordeaux", "Turkey Red", "Ölandsvete",
]


def patch_empty_crop_fields(tables: dict) -> None:
    """Patch varieties that have an empty Crop field based on known overrides."""
    print("\n== Step 14: Crop field hygiene ==")
    var_table = tables.get("Varieties")
    if not var_table:
        return

    records = []
    for name, crop in CROP_OVERRIDES.items():
        records.append({"Name": name, "Crop": crop})

    if DRY_RUN:
        print(f"  [DRY RUN] Would patch {len(records)} empty-crop varieties")
        return

    total = upsert_records(var_table["id"], "Varieties", records, "Name")
    print(f"  Total: {total} varieties patched with Crop field")

    # Ensure featured flag is set
    featured_records = [{"Name": n, "Website Featured": True} for n in FEATURED_OVERRIDES]
    ft = upsert_records(var_table["id"], "Varieties", featured_records, "Name")
    print(f"  Total: {ft} varieties ensured Website Featured")


def main():
    print(f"VAXT Airtable Sync — Base: {BASE_ID}")
    if DRY_RUN:
        print("[DRY RUN MODE — no changes will be made]\n")

    # Discover existing tables
    tables = get_tables()
    print(f"Found {len(tables)} existing tables: {list(tables.keys())}")

    # Execute steps
    add_varieties_enrichment_fields(tables)

    # Refresh table metadata after field additions
    tables = get_tables()

    upsert_variety_enrichment(tables)
    sync_distillery_profiles(tables)
    sync_seed_sources(tables)
    sync_planting_calendars(tables)
    sync_sourdough_recipes(tables)
    sync_community_grain_projects(tables)
    backfill_disease_resistance(tables)

    # Phase 5: Backfill sparse original tables from CSVs
    backfill_sourdough_starters(tables)
    backfill_crop_wild_relatives(tables)
    backfill_rootstock_compatibility(tables)
    backfill_climate_zones(tables)
    backfill_breeding_programs(tables)

    # Phase 0A: Backfill sparse tables (Cold Tolerance Markers, Field Trial Sites, GRIN Accessions)
    backfill_cold_tolerance_markers(tables)
    backfill_field_trial_sites(tables)
    backfill_grin_accessions(tables)

    # Step 13: Full varieties backfill from nordic_variety_trait_index.csv
    backfill_all_varieties(tables)

    # Step 14: Crop field hygiene — patch varieties with empty Crop field
    patch_empty_crop_fields(tables)

    # Final counts
    print("\n== Final Table Counts ==")
    tables = get_tables()
    for name, info in sorted(tables.items()):
        n = count_records(info["id"])
        print(f"  {name:40s}  {n:>4} records")

    print("\nDone.")


if __name__ == "__main__":
    main()
