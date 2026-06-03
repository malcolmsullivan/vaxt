#!/usr/bin/env python3
"""
Create VÄXT variety profile pages in Notion from Airtable data.

Creates 6-12 featured variety pages under the VÄXT KB as children
of the Field Guides page, each with: growing profile, characteristics,
baking/sourdough notes, seed sources, and related guides.

Usage:
    python3 scripts/vaxt/create_notion_variety_profiles.py [--dry-run]
    python3 scripts/vaxt/create_notion_variety_profiles.py --from-file  # Use cached varieties.json

Env:
    VAXT_NOTION_TOKEN         — Notion Internal Integration Token
    VAXT_AIRTABLE_PAT         — Airtable PAT (for live fetch)
    VAXT_AIRTABLE_BASE_ID     — Base ID
"""

import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SCRIPT_DIR = Path(__file__).parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_DIR = WORKSPACE / "data" / "datasets" / "heritage-grain"

# Load .env
if (SCRIPT_DIR / ".env").exists():
    for line in (SCRIPT_DIR / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

NOTION_TOKEN = os.environ.get("VAXT_NOTION_TOKEN", "")
AIRTABLE_PAT = os.environ.get("VAXT_AIRTABLE_PAT", "")
BASE_ID = os.environ.get("VAXT_AIRTABLE_BASE_ID", "appgv7zVxZnT2q9BX")
DRY_RUN = "--dry-run" in sys.argv
FROM_FILE = "--from-file" in sys.argv
LINK_BACK = "--no-link-back" not in sys.argv  # Write Notion URLs back to Airtable

# Notion page IDs
FIELD_GUIDES_PAGE_ID = "318c2b5ee82f818eb883d6906aea9750"
NOTION_API = "https://api.notion.com/v1"


def notion_request(url: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    })
    time.sleep(0.35)
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        print(f"  Notion API {e.code}: {body_text[:300]}")
        raise


def airtable_get(url: str) -> dict:
    req = Request(url, headers={
        "Authorization": f"Bearer {AIRTABLE_PAT}",
        "Content-Type": "application/json",
    })
    time.sleep(0.25)
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())


def airtable_patch(url: str, payload: dict) -> dict:
    """PATCH an Airtable record."""
    data = json.dumps(payload).encode()
    req = Request(url, data=data, method="PATCH", headers={
        "Authorization": f"Bearer {AIRTABLE_PAT}",
        "Content-Type": "application/json",
    })
    time.sleep(0.25)
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())


def ensure_notion_link_field(table_id: str) -> None:
    """Add 'Notion Link' URL field to Varieties table if missing."""
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"
    tables = airtable_get(url)
    for t in tables.get("tables", []):
        if t["id"] == table_id:
            existing = {f["name"] for f in t.get("fields", [])}
            if "Notion Link" not in existing:
                field_url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{table_id}/fields"
                field_def = {"name": "Notion Link", "type": "url"}
                data = json.dumps(field_def).encode()
                req = Request(field_url, data=data, method="POST", headers={
                    "Authorization": f"Bearer {AIRTABLE_PAT}",
                    "Content-Type": "application/json",
                })
                time.sleep(0.25)
                with urlopen(req) as resp:
                    json.loads(resp.read().decode())
                print("  Added 'Notion Link' field to Varieties table")
            else:
                print("  'Notion Link' field already exists")
            break


def update_airtable_notion_link(table_id: str, variety_name: str, notion_url: str) -> bool:
    """Write Notion page URL back to the matching Airtable record."""
    # Find record by Name
    from urllib.parse import quote
    formula = quote(f"{{Name}}='{variety_name}'")
    search_url = (
        f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
        f"?filterByFormula={formula}&maxRecords=1"
    )
    data = airtable_get(search_url)
    records = data.get("records", [])
    if not records:
        return False

    record_id = records[0]["id"]
    patch_url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}/{record_id}"
    airtable_patch(patch_url, {"fields": {"Notion Link": notion_url}})
    return True


def fetch_featured_varieties() -> list[dict]:
    """Fetch featured varieties from Airtable."""
    if FROM_FILE:
        path = OUTPUT_DIR / "varieties.json"
        if not path.exists():
            print(f"ERROR: {path} not found. Run export_airtable_varieties.py first.")
            sys.exit(1)
        all_vars = json.loads(path.read_text())
        return [v for v in all_vars if v.get("featured")]

    # Fetch from Airtable API
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"
    tables = airtable_get(url)
    var_table = None
    for t in tables.get("tables", []):
        if t["name"] == "Varieties":
            var_table = t
            break
    if not var_table:
        print("ERROR: Varieties table not found")
        sys.exit(1)

    # Store table_id for link-back
    fetch_featured_varieties._table_id = var_table["id"]

    records = []
    page_url = f"https://api.airtable.com/v0/{BASE_ID}/{var_table['id']}?pageSize=100"
    while page_url:
        data = airtable_get(page_url)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        page_url = f"{page_url.split('&offset=')[0]}&offset={offset}" if offset else None

    featured = []
    for rec in records:
        f = rec.get("fields", {})
        if f.get("Website Featured"):
            featured.append({
                "name": f.get("Name", ""),
                "species": f.get("Species", ""),
                "crop": f.get("Crop", ""),
                "country": f.get("Country", ""),
                "origin": f.get("Origin", ""),
                "traits": f.get("Traits", []),
                "cold_tolerance_notes": f.get("Cold Tolerance Notes", ""),
                "usda_zone": f.get("USDA Zone", ""),
                "protein": f.get("Protein", ""),
                "sourdough_notes": f.get("Sourdough Notes", ""),
                "bread_notes": f.get("Bread Notes", ""),
                "malt_profile": f.get("Malt Profile", ""),
                "end_use": f.get("End Use", []),
                "seeding_rate": f.get("Seeding Rate", ""),
                "seeding_depth": f.get("Seeding Depth", ""),
                "seeding_window": f.get("Seeding Window", ""),
                "days_to_maturity": f.get("Days to Maturity", ""),
                "row_spacing": f.get("Row Spacing", ""),
                "harvest_notes": f.get("Harvest Notes", ""),
                "seed_sources": f.get("Seed Sources", ""),
                "grower_tips": f.get("Grower Tips", ""),
                "source": f.get("Source", ""),
            })
    return featured


def build_variety_blocks(v: dict) -> list[dict]:
    """Build Notion block children for a variety profile page."""
    blocks = []

    def heading(level: int, text: str):
        types = {2: "heading_2", 3: "heading_3"}
        blocks.append({
            "object": "block",
            "type": types[level],
            types[level]: {
                "rich_text": [{"type": "text", "text": {"content": text}}],
            },
        })

    def paragraph(text: str, bold: bool = False):
        if not text:
            return
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": text},
                    "annotations": {"bold": bold} if bold else {},
                }],
            },
        })

    def bullet(text: str):
        blocks.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
            },
        })

    def divider():
        blocks.append({"object": "block", "type": "divider", "divider": {}})

    # Header info
    if v.get("species"):
        paragraph(v["species"])

    # Quick facts
    heading(2, "Quick Facts")
    if v.get("crop"):
        bullet(f"Crop: {v['crop']}")
    if v.get("country"):
        bullet(f"Country: {v['country']}")
    if v.get("origin"):
        bullet(f"Origin: {v['origin']}")
    if v.get("usda_zone"):
        bullet(f"USDA Zone: {v['usda_zone']}")
    if v.get("protein"):
        bullet(f"Protein: {v['protein']}")
    if v.get("traits"):
        traits_str = ", ".join(v["traits"]) if isinstance(v["traits"], list) else v["traits"]
        bullet(f"Traits: {traits_str}")
    if v.get("end_use"):
        uses = ", ".join(v["end_use"]) if isinstance(v["end_use"], list) else v["end_use"]
        bullet(f"End Use: {uses}")
    if v.get("source"):
        bullet(f"Source: {v['source']}")

    divider()

    # Cold tolerance
    if v.get("cold_tolerance_notes"):
        heading(2, "Cold Tolerance")
        paragraph(v["cold_tolerance_notes"])
        divider()

    # Growing profile
    growing_fields = [
        ("Seeding Rate", v.get("seeding_rate")),
        ("Seeding Depth", v.get("seeding_depth")),
        ("Seeding Window", v.get("seeding_window")),
        ("Days to Maturity", v.get("days_to_maturity")),
        ("Row Spacing", v.get("row_spacing")),
    ]
    has_growing = any(val for _, val in growing_fields)
    if has_growing:
        heading(2, "Growing Profile")
        for label, val in growing_fields:
            if val:
                bullet(f"{label}: {val}")
        if v.get("harvest_notes"):
            paragraph(f"Harvest: {v['harvest_notes']}")
        if v.get("grower_tips"):
            paragraph(f"Tips: {v['grower_tips']}")
        divider()

    # Baking & sourdough
    if v.get("sourdough_notes") or v.get("bread_notes"):
        heading(2, "Baking & Sourdough")
        if v.get("sourdough_notes"):
            paragraph(v["sourdough_notes"])
        if v.get("bread_notes"):
            paragraph(v["bread_notes"])
        divider()

    # Malt profile
    if v.get("malt_profile"):
        heading(2, "Malt Profile")
        paragraph(v["malt_profile"])
        divider()

    # Seed sources
    if v.get("seed_sources"):
        heading(2, "Where to Find Seed")
        paragraph(v["seed_sources"])

    return blocks


def create_notion_page(parent_id: str, title: str, blocks: list[dict]) -> dict | None:
    """Create a Notion page with given blocks."""
    body = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": [{"text": {"content": title}}],
        },
        "children": blocks[:100],  # Notion API limit: 100 blocks per create
    }
    return notion_request(f"{NOTION_API}/pages", method="POST", body=body)


def main():
    print("VAXT Notion Variety Profiles")
    if DRY_RUN:
        print("[DRY RUN MODE]")
    if LINK_BACK:
        print("Notion Link write-back: ENABLED")
    print()

    # Fetch featured varieties
    print("Fetching featured varieties...")
    varieties = fetch_featured_varieties()
    print(f"  {len(varieties)} featured varieties found\n")

    if not varieties:
        print("No featured varieties to create pages for.")
        return

    # Ensure Notion Link field exists on Varieties table (for write-back)
    table_id = getattr(fetch_featured_varieties, "_table_id", None)
    if LINK_BACK and AIRTABLE_PAT and table_id and not DRY_RUN:
        print("Ensuring 'Notion Link' field exists on Varieties table...")
        ensure_notion_link_field(table_id)

    # Generate and optionally create pages
    linked = 0
    for i, v in enumerate(varieties):
        name = v["name"]
        print(f"  [{i+1}/{len(varieties)}] {name}")

        blocks = build_variety_blocks(v)
        print(f"    {len(blocks)} blocks generated")

        if DRY_RUN:
            print(f"    [DRY RUN] Would create page under Field Guides")
            if LINK_BACK:
                print(f"    [DRY RUN] Would write Notion URL back to Airtable")
            continue

        if not NOTION_TOKEN:
            # Save as markdown for manual creation
            content_dir = OUTPUT_DIR / "notion_variety_profiles"
            content_dir.mkdir(parents=True, exist_ok=True)
            safe_name = name.replace("/", "-").replace(" ", "_")
            path = content_dir / f"{safe_name}.json"
            path.write_text(json.dumps({"title": name, "blocks": blocks}, indent=2))
            print(f"    Saved to {path}")
            continue

        try:
            result = create_notion_page(FIELD_GUIDES_PAGE_ID, name, blocks)
            page_url = result.get("url", "unknown")
            print(f"    Created: {page_url}")

            # Write Notion URL back to Airtable
            if LINK_BACK and AIRTABLE_PAT and table_id and page_url != "unknown":
                if update_airtable_notion_link(table_id, name, page_url):
                    print(f"    Linked back to Airtable")
                    linked += 1
                else:
                    print(f"    WARNING: Could not find '{name}' in Airtable for link-back")
        except Exception as e:
            print(f"    ERROR: {e}")

    if linked:
        print(f"\n  {linked} varieties linked (Notion → Airtable)")
    print("\nDone.")


if __name__ == "__main__":
    main()
