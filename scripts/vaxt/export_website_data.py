#!/usr/bin/env python3
"""
Export VAXT Airtable data → JSON files for website.

Produces 9 JSON files in website/public/data/:
  varieties.json          — All varieties (full fields)
  seed_sources.json       — Seed sources directory
  planting_calendars.json — Planting windows by zone/crop
  sourdough.json          — Starters + linked recipes
  breeding_programs.json  — Breeding programs
  climate_zones.json      — USDA hardiness zones
  distilleries.json       — Heritage distillery profiles
  community_projects.json — Community grain co-ops, mills, seed commons
  stats.json              — Table counts summary

Usage:
    python3 scripts/vaxt/export_website_data.py [--dry-run]

Env:
    VAXT_AIRTABLE_PAT       Personal Access Token
    VAXT_AIRTABLE_BASE_ID   Base ID (default: appgv7zVxZnT2q9BX)
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
OUTPUT_DIR = WORKSPACE / "website" / "public" / "data"

BASE_ID = os.environ.get("VAXT_AIRTABLE_BASE_ID", "appgv7zVxZnT2q9BX")
PAT = os.environ.get("VAXT_AIRTABLE_PAT", "")
RATE_DELAY = 0.25
DRY_RUN = "--dry-run" in sys.argv

# Load .env
if not PAT and (SCRIPT_DIR / ".env").exists():
    for line in (SCRIPT_DIR / ".env").read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "VAXT_AIRTABLE_PAT":
            PAT = v.strip()

if not PAT:
    print("ERROR: VAXT_AIRTABLE_PAT not set")
    sys.exit(1)


def api_get(url: str) -> dict:
    req = Request(url, headers={
        "Authorization": f"Bearer {PAT}",
        "Content-Type": "application/json",
    })
    time.sleep(RATE_DELAY)
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())


def get_all_records(table_id: str) -> list[dict]:
    records = []
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}?pageSize=100"
    offset = None
    while True:
        page_url = url + (f"&offset={offset}" if offset else "")
        data = api_get(page_url)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def get_tables() -> dict:
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"
    data = api_get(url)
    return {t["name"]: t for t in data["tables"]}


def export_varieties(table_id: str) -> list[dict]:
    """Export all varieties with full field set."""
    records = get_all_records(table_id)
    varieties = []
    for rec in records:
        f = rec.get("fields", {})
        varieties.append({
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
            "seeding_rate": f.get("Seeding Rate", ""),
            "seeding_depth": f.get("Seeding Depth", ""),
            "seeding_window": f.get("Seeding Window", ""),
            "days_to_maturity": f.get("Days to Maturity", ""),
            "row_spacing": f.get("Row Spacing", ""),
            "harvest_notes": f.get("Harvest Notes", ""),
            "seed_sources": f.get("Seed Sources", ""),
            "grower_tips": f.get("Grower Tips", ""),
        })
    varieties.sort(key=lambda v: (not v["featured"], v["name"]))
    return varieties


def export_seed_sources(table_id: str) -> list[dict]:
    records = get_all_records(table_id)
    sources = []
    for rec in records:
        f = rec.get("fields", {})
        sources.append({
            "id": rec["id"],
            "source_id": f.get("Source ID", ""),
            "name": f.get("Name", ""),
            "type": f.get("Type", ""),
            "country": f.get("Country", ""),
            "website": f.get("Website", ""),
            "ships_to": f.get("Ships To", ""),
            "specialties": f.get("Specialties", ""),
            "access": f.get("Access", ""),
            "notes": f.get("Notes", ""),
        })
    sources.sort(key=lambda s: s["name"])
    return sources


def export_planting_calendars(table_id: str) -> list[dict]:
    records = get_all_records(table_id)
    calendars = []
    for rec in records:
        f = rec.get("fields", {})
        calendars.append({
            "id": rec["id"],
            "calendar_id": f.get("Calendar ID", ""),
            "zone": f.get("Zone", ""),
            "crop": f.get("Crop", ""),
            "type": f.get("Type", ""),
            "sow_start": f.get("Sow Start", ""),
            "sow_end": f.get("Sow End", ""),
            "vernalization_weeks": f.get("Vernalization Weeks", ""),
            "expected_harvest": f.get("Expected Harvest", ""),
            "notes": f.get("Notes", ""),
        })
    calendars.sort(key=lambda c: (c["zone"], c["crop"]))
    return calendars


def export_sourdough(starter_table_id: str, recipe_table_id: str) -> dict:
    starters = []
    for rec in get_all_records(starter_table_id):
        f = rec.get("fields", {})
        starters.append({
            "id": rec["id"],
            "starter_id": f.get("Starter ID", ""),
            "name": f.get("Name", ""),
            "origin_country": f.get("Origin Country", ""),
            "origin_city": f.get("Origin City", ""),
            "grain_base": f.get("Grain Base", ""),
            "estimated_age_years": f.get("Estimated Age (years)", None),
            "culture_type": f.get("Culture Type", ""),
            "flavor_profile": f.get("Flavor Profile", ""),
            "preservation_method": f.get("Preservation Method", ""),
            "notes": f.get("Notes", ""),
        })

    recipes = []
    for rec in get_all_records(recipe_table_id):
        f = rec.get("fields", {})
        recipes.append({
            "id": rec["id"],
            "starter_id": f.get("Starter ID", ""),
            "recipe": f.get("Recipe", ""),
            "hydration_pct": f.get("Hydration %", None),
            "flour_type": f.get("Flour Type", ""),
            "fermentation_schedule": f.get("Fermentation Schedule", ""),
            "serving_notes": f.get("Serving Notes", ""),
        })

    starters.sort(key=lambda s: s["name"])
    return {"starters": starters, "recipes": recipes}


def export_breeding_programs(table_id: str) -> list[dict]:
    records = get_all_records(table_id)
    programs = []
    for rec in records:
        f = rec.get("fields", {})
        programs.append({
            "id": rec["id"],
            "program_id": f.get("Program ID", ""),
            "institution": f.get("Institution", ""),
            "country": f.get("Country", ""),
            "city": f.get("City", ""),
            "crops": f.get("Crops", ""),
            "focus_areas": f.get("Focus Areas", ""),
            "notable_releases": f.get("Notable Releases", ""),
            "established_year": f.get("Established Year", None),
            "latitude": f.get("Latitude", None),
            "longitude": f.get("Longitude", None),
            "website": f.get("Website", ""),
        })
    programs.sort(key=lambda p: p["institution"])
    return programs


def export_climate_zones(table_id: str) -> list[dict]:
    records = get_all_records(table_id)
    zones = []
    for rec in records:
        f = rec.get("fields", {})
        zones.append({
            "id": rec["id"],
            "zone": f.get("Zone", None),
            "subzone": f.get("Subzone", ""),
            "min_temp_c": f.get("Min Temp (°C)", None),
            "max_temp_c": f.get("Max Temp (°C)", None),
            "example_locations": f.get("Example Locations", ""),
            "relevance": f.get("Relevance", ""),
        })
    zones.sort(key=lambda z: (z["zone"] or 0, z["subzone"]))
    return zones


def export_distilleries(table_id: str) -> list[dict]:
    """Export distillery profiles."""
    records = get_all_records(table_id)
    distilleries = []
    for rec in records:
        f = rec.get("fields", {})
        founded = f.get("Founded", None)
        if founded is not None:
            try:
                founded = int(founded)
            except (ValueError, TypeError):
                founded = None
        lat = f.get("Latitude", None)
        lon = f.get("Longitude", None)
        if lat is not None:
            try:
                lat = float(lat)
            except (ValueError, TypeError):
                lat = None
        if lon is not None:
            try:
                lon = float(lon)
            except (ValueError, TypeError):
                lon = None
        distilleries.append({
            "id": rec["id"],
            "distillery_id": f.get("Distillery ID", ""),
            "name": f.get("Name", ""),
            "country": f.get("Country", ""),
            "city": f.get("City", ""),
            "founded": founded,
            "spirit_type": f.get("Spirit Type", ""),
            "heritage_focus": bool(f.get("Heritage Focus", False)),
            "malting": f.get("Malting", ""),
            "latitude": lat,
            "longitude": lon,
            "website": f.get("Website", ""),
            "notes": f.get("Notes", ""),
        })
    distilleries.sort(key=lambda d: d["name"])
    return distilleries


def export_community_projects(table_id: str) -> list[dict]:
    """Export community grain projects."""
    records = get_all_records(table_id)
    projects = []
    for rec in records:
        f = rec.get("fields", {})
        lat = f.get("Latitude", None)
        lon = f.get("Longitude", None)
        if lat is not None:
            try:
                lat = float(lat)
            except (ValueError, TypeError):
                lat = None
        if lon is not None:
            try:
                lon = float(lon)
            except (ValueError, TypeError):
                lon = None
        founded = f.get("Founded Year", None)
        if founded is not None:
            try:
                founded = int(founded)
            except (ValueError, TypeError):
                founded = None
        members = f.get("Members", None)
        if members is not None:
            try:
                members = int(members)
            except (ValueError, TypeError):
                members = None
        hectares = f.get("Hectares", None)
        if hectares is not None:
            try:
                hectares = float(hectares)
            except (ValueError, TypeError):
                hectares = None
        projects.append({
            "id": rec["id"],
            "project_id": f.get("Project ID", ""),
            "name": f.get("Name", ""),
            "country": f.get("Country", ""),
            "city": f.get("City", ""),
            "latitude": lat,
            "longitude": lon,
            "crops": f.get("Crops", []),
            "founded_year": founded,
            "members": members,
            "hectares": hectares,
            "model": f.get("Model", ""),
            "focus": f.get("Focus", []),
            "varieties_grown": f.get("Varieties Grown", []),
            "website": f.get("Website", ""),
            "notes": f.get("Notes", ""),
        })
    projects.sort(key=lambda p: p["name"])
    return projects


def write_json(path: Path, data, label: str):
    if DRY_RUN:
        count = len(data) if isinstance(data, list) else sum(len(v) for v in data.values() if isinstance(v, list))
        print(f"  [DRY RUN] Would write {path.name} ({count} items)")
        return
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    size = path.stat().st_size
    print(f"  {path.name:30s} {size:>8,} bytes  {label}")


def main():
    print("VAXT Website Data Export")
    print(f"  Output: {OUTPUT_DIR}\n")

    tables = get_tables()
    print(f"Found {len(tables)} Airtable tables\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Table name → ID lookup
    def tid(name: str) -> str:
        t = tables.get(name)
        if not t:
            print(f"  WARNING: Table '{name}' not found, skipping")
            return ""
        return t["id"]

    # 1. Varieties
    vid = tid("Varieties")
    if vid:
        print("Exporting varieties...")
        varieties = export_varieties(vid)
        write_json(OUTPUT_DIR / "varieties.json", varieties, f"{len(varieties)} varieties")

    # 2. Seed Sources
    sid = tid("Seed Sources")
    if sid:
        print("Exporting seed sources...")
        sources = export_seed_sources(sid)
        write_json(OUTPUT_DIR / "seed_sources.json", sources, f"{len(sources)} sources")

    # 3. Planting Calendars
    pid = tid("Planting Calendars")
    if pid:
        print("Exporting planting calendars...")
        calendars = export_planting_calendars(pid)
        write_json(OUTPUT_DIR / "planting_calendars.json", calendars, f"{len(calendars)} calendars")

    # 4. Sourdough
    st_id = tid("Sourdough Starters")
    sr_id = tid("Sourdough Recipes")
    if st_id and sr_id:
        print("Exporting sourdough...")
        sourdough = export_sourdough(st_id, sr_id)
        write_json(OUTPUT_DIR / "sourdough.json", sourdough, f"{len(sourdough['starters'])} starters, {len(sourdough['recipes'])} recipes")

    # 5. Breeding Programs
    bp_id = tid("Breeding Programs")
    if bp_id:
        print("Exporting breeding programs...")
        programs = export_breeding_programs(bp_id)
        write_json(OUTPUT_DIR / "breeding_programs.json", programs, f"{len(programs)} programs")

    # 6. Climate Zones
    cz_id = tid("Climate Zones")
    if cz_id:
        print("Exporting climate zones...")
        zones = export_climate_zones(cz_id)
        write_json(OUTPUT_DIR / "climate_zones.json", zones, f"{len(zones)} zones")

    # 7. Distilleries
    dist_id = tid("Distillery Profiles")
    if dist_id:
        print("Exporting distilleries...")
        distilleries = export_distilleries(dist_id)
        write_json(OUTPUT_DIR / "distilleries.json", distilleries, f"{len(distilleries)} distilleries")

    # 8. Community Projects
    cp_id = tid("Community Grain Projects")
    if cp_id:
        print("Exporting community projects...")
        projects = export_community_projects(cp_id)
        write_json(OUTPUT_DIR / "community_projects.json", projects, f"{len(projects)} projects")

    # 9. Stats
    print("Exporting stats...")
    stats = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tables": {},
    }
    for name, t in sorted(tables.items()):
        count = len(get_all_records(t["id"]))
        stats["tables"][name] = {"records": count, "fields": len(t.get("fields", []))}
    stats["total_records"] = sum(t["records"] for t in stats["tables"].values())
    stats["total_tables"] = len(stats["tables"])
    write_json(OUTPUT_DIR / "stats.json", stats, f"{stats['total_tables']} tables, {stats['total_records']} records")

    print("\nDone.")


if __name__ == "__main__":
    main()
