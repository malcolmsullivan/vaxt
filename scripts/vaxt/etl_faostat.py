#!/usr/bin/env python3
"""ETL: Download FAOSTAT crop production data for cold-climate cereals.

Downloads the bulk Production_Crops_Livestock normalized CSV from FAO,
filters to target crops and countries, and outputs a clean CSV.

Usage:
    python3 scripts/vaxt/etl_faostat.py                    # Full run
    python3 scripts/vaxt/etl_faostat.py --dry-run           # Show filter plan only
    python3 scripts/vaxt/etl_faostat.py --year-min 1990     # Start from 1990
    python3 scripts/vaxt/etl_faostat.py --skip-download     # Reuse cached ZIP

Source: https://bulks-faostat.fao.org/production/
License: FAO open data, attribution required.
"""

import argparse
import csv
import io
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_DIR = WORKSPACE / "data" / "datasets" / "heritage-grain"
OUTPUT_CSV = OUTPUT_DIR / "faostat_production.csv"
CACHE_ZIP = OUTPUT_DIR / "faostat_bulk.zip"

BULK_URL = "https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip"
USER_AGENT = "VAV-OS/1.0 (malcolm@vav-os.com) heritage-grain-ETL"

# Target crops (FAOSTAT item names)
TARGET_ITEMS = {
    "Wheat",
    "Barley",
    "Rye",
    "Oats",
    "Triticale",
}

# Target countries (FAOSTAT area names)
TARGET_AREAS = {
    # Nordic
    "Sweden",
    "Finland",
    "Norway",
    "Denmark",
    "Iceland",
    # Baltic
    "Estonia",
    "Latvia",
    "Lithuania",
    # Major cold-climate producers
    "Canada",
    "Russian Federation",
    "United States of America",
    # Other Nordic-adjacent
    "Poland",
    "Germany",
    "United Kingdom of Great Britain and Northern Ireland",
}

# Target elements (metric codes)
TARGET_ELEMENTS = {
    "5312": "Area harvested",       # hectares
    "5510": "Production",           # tonnes
    "5412": "Yield",                # kg/ha
}

# Output columns
OUTPUT_COLUMNS = [
    "area",
    "area_code",
    "item",
    "item_code",
    "element",
    "element_code",
    "year",
    "value",
    "unit",
    "flag",
]


def download_bulk(cache_path: Path) -> Path:
    """Download FAOSTAT bulk ZIP if not cached."""
    if cache_path.exists():
        size_mb = cache_path.stat().st_size / (1024 * 1024)
        print(f"Using cached ZIP: {cache_path.name} ({size_mb:.1f} MB)")
        return cache_path

    print(f"Downloading FAOSTAT bulk data (~33 MB)...")
    req = Request(BULK_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=120) as resp:
            data = resp.read()
    except (HTTPError, URLError) as exc:
        print(f"ERROR: Download failed: {exc}", file=sys.stderr)
        sys.exit(1)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(data)
    size_mb = len(data) / (1024 * 1024)
    print(f"Downloaded {size_mb:.1f} MB -> {cache_path.name}")
    return cache_path


def extract_and_filter(
    zip_path: Path, year_min: int, year_max: int
) -> list[dict]:
    """Extract CSV from ZIP and filter to target crops/countries/years."""
    with zipfile.ZipFile(zip_path) as zf:
        # Find the CSV inside the ZIP
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not csv_names:
            print("ERROR: No CSV found in ZIP", file=sys.stderr)
            sys.exit(1)

        csv_name = csv_names[0]
        print(f"Reading: {csv_name}")

        with zf.open(csv_name) as f:
            # Handle BOM and encoding
            text = io.TextIOWrapper(f, encoding="utf-8-sig")
            reader = csv.DictReader(text)

            rows = []
            total = 0
            for row in reader:
                total += 1

                # Filter: item
                item = row.get("Item", "")
                if item not in TARGET_ITEMS:
                    continue

                # Filter: area
                area = row.get("Area", "")
                if area not in TARGET_AREAS:
                    continue

                # Filter: element
                element_code = row.get("Element Code", "")
                if element_code not in TARGET_ELEMENTS:
                    continue

                # Filter: year
                try:
                    year = int(row.get("Year", "0"))
                except ValueError:
                    continue
                if year < year_min or year > year_max:
                    continue

                # Filter: value must exist
                value = row.get("Value", "").strip()
                if not value:
                    continue

                rows.append({
                    "area": area,
                    "area_code": row.get("Area Code (M49)", row.get("Area Code", "")),
                    "item": item,
                    "item_code": row.get("Item Code", ""),
                    "element": row.get("Element", ""),
                    "element_code": element_code,
                    "year": year,
                    "value": value,
                    "unit": row.get("Unit", ""),
                    "flag": row.get("Flag", ""),
                })

    print(f"Scanned {total:,} rows, matched {len(rows):,}")
    return rows


def main():
    parser = argparse.ArgumentParser(
        description="ETL: FAOSTAT crop production for cold-climate cereals"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show filter plan only"
    )
    parser.add_argument(
        "--skip-download", action="store_true", help="Reuse cached ZIP"
    )
    parser.add_argument(
        "--year-min", type=int, default=1961, help="Start year (default: 1961)"
    )
    parser.add_argument(
        "--year-max", type=int, default=2025, help="End year (default: 2025)"
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print("=== FAOSTAT ETL Dry Run ===")
        print(f"Crops: {', '.join(sorted(TARGET_ITEMS))}")
        print(f"Countries: {', '.join(sorted(TARGET_AREAS))}")
        print(f"Elements: {', '.join(f'{k} ({v})' for k, v in sorted(TARGET_ELEMENTS.items()))}")
        print(f"Years: {args.year_min}–{args.year_max}")
        est = len(TARGET_ITEMS) * len(TARGET_AREAS) * len(TARGET_ELEMENTS) * (args.year_max - args.year_min + 1)
        print(f"Max possible rows: {est:,}")
        print(f"\nSource: {BULK_URL}")
        return

    # Phase 1: Download
    if args.skip_download and CACHE_ZIP.exists():
        zip_path = CACHE_ZIP
        print(f"Using cached ZIP: {zip_path.name}")
    else:
        zip_path = download_bulk(CACHE_ZIP)

    # Phase 2: Extract and filter
    print(f"\nFiltering: {len(TARGET_ITEMS)} crops x {len(TARGET_AREAS)} countries, {args.year_min}–{args.year_max}")
    rows = extract_and_filter(zip_path, args.year_min, args.year_max)

    if not rows:
        print("No matching records found.")
        sys.exit(1)

    # Phase 3: Write CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows):,} rows -> {OUTPUT_CSV.name}")

    # Summary
    items = sorted(set(r["item"] for r in rows))
    areas = sorted(set(r["area"] for r in rows))
    years = sorted(set(r["year"] for r in rows))
    elements = sorted(set(r["element"] for r in rows))

    print(f"\nCrops ({len(items)}): {', '.join(items)}")
    print(f"Countries ({len(areas)}): {', '.join(areas)}")
    print(f"Years: {min(years)}–{max(years)} ({len(years)} years)")
    print(f"Metrics ({len(elements)}): {', '.join(elements)}")

    # Top producers (latest year with data)
    latest_year = max(years)
    print(f"\nTop producers ({latest_year}, production in tonnes):")
    production = [
        r for r in rows
        if r["year"] == latest_year and r["element"] == "Production"
    ]
    production.sort(key=lambda r: float(r["value"]), reverse=True)
    for r in production[:10]:
        val = float(r["value"])
        print(f"  {r['area']}: {r['item']} — {val:,.0f} t")


if __name__ == "__main__":
    main()
