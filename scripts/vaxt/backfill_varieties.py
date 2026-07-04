#!/usr/bin/env python3
"""
VAXT Varieties Backfill — sync nordic_variety_trait_index.csv → Airtable.

Reads all 194 varieties from CSV, diffs against existing Airtable records,
and creates the missing ones via REST API.

Usage:
  python3 scripts/vaxt/backfill_varieties.py              # Dry run (default)
  python3 scripts/vaxt/backfill_varieties.py --commit      # Actually create records

Env vars (from scripts/vaxt/.env):
  VAXT_AIRTABLE_PAT      — Personal Access Token
  VAXT_AIRTABLE_BASE_ID  — Base ID (default: appgv7zVxZnT2q9BX)
"""

import csv
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).parent
WORKSPACE = SCRIPT_DIR.parent.parent

# Load .env
env_path = SCRIPT_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

PAT = os.environ.get("VAXT_AIRTABLE_PAT", "")
BASE_ID = os.environ.get("VAXT_AIRTABLE_BASE_ID", "appgv7zVxZnT2q9BX")
API_BASE = "https://api.airtable.com/v0"
CSV_PATH = SCRIPT_DIR / "nordic_variety_trait_index.csv"

# --- Crop normalization (CSV crop → Airtable single select) ---
CROP_MAP = {
    "wheat": "wheat", "wheat (spring)": "wheat", "wheat (winter)": "wheat",
    "rye": "rye", "rye (winter)": "rye",
    "barley": "barley", "barley (spring 6-row)": "barley",
    "barley (spring 2-row)": "barley", "barley (winter 2-row)": "barley",
    "barley (winter 6-row)": "barley",
    "oat": "oat", "oat (spring)": "oat",
    "apple": "apple", "grape": "grape",
    "grape (red wine)": "grape", "grape (white wine)": "grape",
    "grape (table/wine)": "grape", "grape (table)": "grape",
    "grape (table/juice)": "grape", "grape (seedless table)": "grape",
    "haskap": "haskap", "sea buckthorn": "sea buckthorn",
    "arctic bramble": "arctic bramble",
    "spelt": "spelt", "emmer": "emmer", "einkorn": "einkorn",
    # Forage grasses
    "timothy": "forage grass", "meadow fescue": "forage grass",
    "festulolium": "forage grass", "perennial ryegrass": "forage grass",
    "red clover": "forage grass", "white clover": "forage grass",
    "reed canary grass": "forage grass", "tall fescue": "forage grass",
    "smooth bromegrass": "forage grass", "orchardgrass": "forage grass",
    "kentucky bluegrass": "forage grass", "alsike clover": "forage grass",
    "birdsfoot trefoil": "forage grass",
    # Berries
    "blueberry (half-high)": "berry", "blueberry (highbush)": "berry",
    "black currant": "berry", "red currant": "berry",
    "gooseberry": "berry", "saskatoon berry": "berry",
    "cloudberry (female)": "berry", "cloudberry (hermaphrodite)": "berry",
    "cloudberry (male)": "berry", "raspberry": "berry",
    "honeyberry": "berry", "arctic raspberry": "berry",
    "crowberry": "berry", "lingonberry": "berry",
    # Stone fruits
    "sour cherry (bush)": "cherry", "sour cherry (tree)": "cherry",
    "cherry": "cherry", "plum": "plum", "cherry-plum": "plum",
    "apricot": "apricot", "peach": "peach",
    # Legumes
    "pea": "pea", "pea (field)": "pea", "pea (garden)": "pea",
    "faba bean": "faba bean", "lentil": "lentil",
    "lupin": "lupin", "chickpea": "chickpea",
    # Other
    "pear": "pear", "pear (Asian)": "pear",
    "triticale (winter)": "triticale",
}

# --- Trait normalization (CSV trait → Airtable multi-select option) ---
TRAIT_MAP = {
    "winterhardiness": "winterhardiness",
    "exceptional winterhardiness": "winterhardiness",
    "extreme winterhardiness": "winterhardiness",
    "winter hardy": "winterhardiness",
    "winter wheat": "winterhardiness",
    "winter rye": "winterhardiness",
    "cold hardiness": "cold hardy",
    "cold hardy": "cold hardy",
    "extremely hardy": "cold hardy",
    "bread-making quality": "bread quality",
    "bread quality": "bread quality",
    "bread wheat": "bread quality",
    "bread": "bread quality",
    "milling wheat": "bread quality",
    "disease resistance": "disease resistant",
    "disease resistant": "disease resistant",
    "mildew resistant": "disease resistant",
    "drought tolerant": "drought tolerant",
    "drought": "drought tolerant",
    "tall straw": "tall straw",
    "tall": "tall straw",
    "heritage landrace": "heritage landrace",
    "historic": "heritage landrace",
    "hulled grain": "hulled grain",
    "ancient grain": "ancient grain",
    "deep roots": "deep roots",
    "erosion control": "erosion control",
    "low input": "low input",
}

# --- Country normalization ---
COUNTRY_MAP = {
    "Norway": "Norway", "Finland": "Finland", "Sweden": "Sweden",
    "Denmark": "Denmark", "Iceland": "Iceland", "Canada": "Canada",
    "USA": "USA", "Latvia": "Latvia", "Estonia": "Estonia",
    "Lithuania": "Lithuania", "Germany": "Germany", "Poland": "Poland",
    "Ukraine": "Ukraine", "Russia": "Russia",
    "United Kingdom": "United Kingdom", "UK": "United Kingdom",
    "Scotland": "United Kingdom",
    "Faroe Islands": "Faroe Islands",
    "China": "China", "Japan": "Japan",
    "France": "France", "Hungary": "Hungary",
    "Czech Republic": "Czech Republic", "Netherlands": "Netherlands",
    "Italy": "Italy", "Austria": "Austria", "Switzerland": "Switzerland",
    "Germany/UK": "Germany", "": "other",
}


def api_request(method: str, url: str, body: dict | None = None) -> dict:
    """Make an Airtable API request."""
    if not PAT:
        print("ERROR: VAXT_AIRTABLE_PAT not set.", file=sys.stderr)
        sys.exit(1)
    headers = {
        "Authorization": f"Bearer {PAT}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=headers, method=method)
    time.sleep(0.22)  # Rate limit: 5 req/s
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())


def get_all_records(table_id: str, fields: list[str]) -> list[dict]:
    """Fetch all records from a table, handling pagination."""
    records = []
    field_params = "&".join(f"fields[]={quote(f)}" for f in fields)
    url = f"{API_BASE}/{BASE_ID}/{table_id}?{field_params}"
    while url:
        data = api_request("GET", url)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if offset:
            base_url = url.split("&offset=")[0]
            url = f"{base_url}&offset={offset}"
        else:
            url = None
    return records


def create_records(table_id: str, records: list[dict]) -> int:
    """Create records in batches of 10 (Airtable limit)."""
    created = 0
    for i in range(0, len(records), 10):
        batch = records[i:i + 10]
        body = {"records": [{"fields": r} for r in batch]}
        try:
            result = api_request("POST", f"{API_BASE}/{BASE_ID}/{table_id}", body)
            created += len(result.get("records", []))
            print(f"  Batch {i // 10 + 1}: created {len(result.get('records', []))} records")
        except HTTPError as e:
            err = e.read().decode() if e.fp else ""
            print(f"  ERROR batch {i // 10 + 1}: {e.code} — {err}", file=sys.stderr)
    return created


def normalize_traits(raw: str) -> list[str]:
    """Parse semicolon-separated traits and normalize to Airtable options."""
    if not raw:
        return []
    seen = set()
    result = []
    for t in raw.split(";"):
        t = t.strip().lower()
        mapped = TRAIT_MAP.get(t)
        if mapped and mapped not in seen:
            seen.add(mapped)
            result.append(mapped)
    return result


def read_csv() -> list[dict]:
    """Read the CSV and normalize fields for Airtable."""
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["variety"].strip()
            raw_crop = row["crop"].strip().lower()
            crop = CROP_MAP.get(raw_crop, "other")
            raw_country = row["country"].strip()
            country = COUNTRY_MAP.get(raw_country, "other")
            traits = normalize_traits(row["traits"])
            cold_notes = row["cold_tolerance_notes"].strip()
            zone = row["usda_zone"].strip()
            source = row["source"].strip()

            # Build the Species field from the raw crop info
            species = ""
            if "wheat" in raw_crop:
                species = "Triticum aestivum"
            elif "rye" in raw_crop:
                species = "Secale cereale"
            elif "barley" in raw_crop:
                species = "Hordeum vulgare"
            elif "oat" in raw_crop:
                species = "Avena sativa"
            elif raw_crop == "apple":
                species = "Malus domestica"
            elif "grape" in raw_crop:
                species = "Vitis hybrid"
            elif raw_crop == "haskap":
                species = "Lonicera caerulea"
            elif raw_crop == "sea buckthorn":
                species = "Hippophae rhamnoides"
            elif raw_crop == "lingonberry":
                species = "Vaccinium vitis-idaea"
            elif raw_crop == "arctic bramble":
                species = "Rubus arcticus"
            elif "triticale" in raw_crop:
                species = "x Triticosecale"
            elif raw_crop == "timothy":
                species = "Phleum pratense"
            elif "fescue" in raw_crop:
                species = "Festuca pratensis"
            elif raw_crop == "festulolium":
                species = "x Festulolium"
            elif "ryegrass" in raw_crop:
                species = "Lolium perenne"
            elif "red clover" in raw_crop:
                species = "Trifolium pratense"
            elif "white clover" in raw_crop:
                species = "Trifolium repens"
            elif "alsike clover" in raw_crop:
                species = "Trifolium hybridum"
            elif raw_crop == "reed canary grass":
                species = "Phalaris arundinacea"
            elif raw_crop == "smooth bromegrass":
                species = "Bromus inermis"
            elif raw_crop == "orchardgrass":
                species = "Dactylis glomerata"
            elif raw_crop == "kentucky bluegrass":
                species = "Poa pratensis"
            elif raw_crop == "tall fescue":
                species = "Festuca arundinacea"
            elif "cherry" in raw_crop:
                species = "Prunus cerasus"
            elif raw_crop == "plum" or raw_crop == "cherry-plum":
                species = "Prunus domestica"
            elif raw_crop == "apricot":
                species = "Prunus armeniaca"
            elif raw_crop == "peach":
                species = "Prunus persica"
            elif "pear" in raw_crop:
                species = "Pyrus communis"
            elif "blueberry" in raw_crop:
                species = "Vaccinium corymbosum"
            elif raw_crop == "black currant":
                species = "Ribes nigrum"
            elif raw_crop == "red currant":
                species = "Ribes rubrum"
            elif raw_crop == "gooseberry":
                species = "Ribes uva-crispa"
            elif "saskatoon" in raw_crop:
                species = "Amelanchier alnifolia"
            elif "cloudberry" in raw_crop:
                species = "Rubus chamaemorus"
            elif raw_crop == "raspberry":
                species = "Rubus idaeus"
            elif raw_crop == "honeyberry":
                species = "Lonicera caerulea"
            elif raw_crop == "crowberry":
                species = "Empetrum nigrum"
            elif "pea" in raw_crop:
                species = "Pisum sativum"
            elif raw_crop == "faba bean":
                species = "Vicia faba"
            elif raw_crop == "lentil":
                species = "Lens culinaris"
            elif raw_crop == "lupin":
                species = "Lupinus angustifolius"
            elif raw_crop == "chickpea":
                species = "Cicer arietinum"
            elif raw_crop == "birdsfoot trefoil":
                species = "Lotus corniculatus"

            fields = {
                "Name": name,
                "Species": species,
                "Crop": crop,
                "Country": country,
                "Cold Tolerance Notes": cold_notes,
                "USDA Zone": zone,
                "Source": source,
                "Status": "draft",
            }
            if traits:
                fields["Traits"] = traits

            rows.append(fields)
    return rows


def find_varieties_table() -> str:
    """Find the Varieties table ID via metadata API."""
    url = f"{API_BASE}/meta/bases/{BASE_ID}/tables"
    data = api_request("GET", url)
    for t in data.get("tables", []):
        if t["name"].lower() in ("varieties", "variety"):
            return t["id"]
    print("ERROR: Varieties table not found", file=sys.stderr)
    sys.exit(1)


def main():
    commit = "--commit" in sys.argv

    print("VAXT Varieties Backfill")
    print(f"  Base: {BASE_ID}")
    print(f"  CSV: {CSV_PATH}")
    print(f"  Mode: {'COMMIT' if commit else 'DRY RUN'}")
    print()

    # Step 1: Read CSV
    csv_rows = read_csv()
    csv_names = {r["Name"] for r in csv_rows}
    print(f"CSV: {len(csv_rows)} rows, {len(csv_names)} unique names")

    # Step 2: Get existing Airtable varieties
    print("Fetching existing Airtable varieties...")
    table_id = find_varieties_table()
    print(f"  Table ID: {table_id}")
    existing = get_all_records(table_id, ["Name"])
    existing_names = {r["fields"].get("Name", "").strip() for r in existing}
    print(f"  Existing: {len(existing_names)} varieties")

    # Step 3: Compute diff
    missing_names = csv_names - existing_names
    already_present = csv_names & existing_names
    print(f"\n  Already in Airtable: {len(already_present)}")
    print(f"  Missing (to create): {len(missing_names)}")

    if not missing_names:
        print("\nAll varieties already in Airtable. Nothing to do.")
        return

    # Filter CSV rows to just the missing ones
    to_create = [r for r in csv_rows if r["Name"] in missing_names]

    # Show crop breakdown
    crop_counts = {}
    for r in to_create:
        c = r["Crop"]
        crop_counts[c] = crop_counts.get(c, 0) + 1
    print(f"\n  Crop breakdown of missing varieties:")
    for crop, count in sorted(crop_counts.items(), key=lambda x: -x[1]):
        print(f"    {crop}: {count}")

    if not commit:
        print(f"\n[DRY RUN] Would create {len(to_create)} records.")
        print("  Run with --commit to create them.")
        print(f"\n  Sample (first 5):")
        for r in to_create[:5]:
            print(f"    {r['Name']} ({r['Crop']}, {r['Country']}, zone {r.get('USDA Zone', '?')})")
        return

    # Step 4: Create records
    print(f"\nCreating {len(to_create)} varieties...")
    created = create_records(table_id, to_create)
    print(f"\nDone. Created {created} of {len(to_create)} varieties.")

    # Step 5: Verify
    print("\nVerifying...")
    final = get_all_records(table_id, ["Name"])
    print(f"  Final count: {len(final)} varieties in Airtable")


if __name__ == "__main__":
    main()
