#!/usr/bin/env python3
"""ETL: Download Eurostat crop production data for cold-climate cereals.

Uses the Eurostat JSON-stat API (anonymous, no auth required).
Filters to target crops and Nordic/Baltic countries.

Usage:
    python3 scripts/vaxt/etl_eurostat.py                    # Full run
    python3 scripts/vaxt/etl_eurostat.py --dry-run           # Show filter plan only
    python3 scripts/vaxt/etl_eurostat.py --year-min 2000     # Start from 2000

Source: https://ec.europa.eu/eurostat/databrowser/product/view/apro_cpsh1
License: Eurostat open data, attribution to Eurostat required.

Complements faostat_production with:
  - EU standard humidity normalization
  - Triticale and rye as distinct crops (FAOSTAT lumps some)
  - Often more current for European data
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_DIR = WORKSPACE / "data" / "datasets" / "heritage-grain"
OUTPUT_CSV = OUTPUT_DIR / "eurostat_production.csv"

USER_AGENT = "VAV-OS/1.0 (malcolm@vav-os.com) heritage-grain-ETL"

API_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_cpsh1"

# Target crops (Eurostat crop codes)
TARGET_CROPS = {
    "C1100": "Wheat and spelt",
    "C1210": "Rye",
    "C1300": "Barley",
    "C1400": "Oats",
    "C1600": "Triticale",
}

# Target countries (Eurostat geo codes)
TARGET_GEO = {
    # Nordic
    "SE": "Sweden",
    "FI": "Finland",
    "NO": "Norway",
    "DK": "Denmark",
    "IS": "Iceland",
    # Baltic
    "EE": "Estonia",
    "LV": "Latvia",
    "LT": "Lithuania",
    # Other cold-climate
    "PL": "Poland",
    "DE": "Germany",
}

# Target metrics (strucpro codes)
TARGET_METRICS = {
    "AR": "Area harvested",           # 1000 ha
    "PR_HU_EU": "Production",         # 1000 t (EU humidity)
    "YI_HU_EU": "Yield",              # t/ha (EU humidity)
}

# Units per metric
METRIC_UNITS = {
    "AR": "1000 ha",
    "PR_HU_EU": "1000 t",
    "YI_HU_EU": "t/ha",
}

OUTPUT_COLUMNS = [
    "geo",
    "geo_label",
    "crop_code",
    "crop_label",
    "metric_code",
    "metric_label",
    "year",
    "value",
    "unit",
]


def build_api_url(year_min: int) -> str:
    """Build Eurostat API URL with query parameters."""
    params = [
        ("format", "JSON"),
        ("sinceTimePeriod", str(year_min)),
        ("lang", "en"),
    ]
    for code in TARGET_CROPS:
        params.append(("crops", code))
    for code in TARGET_METRICS:
        params.append(("strucpro", code))
    for code in TARGET_GEO:
        params.append(("geo", code))

    return f"{API_BASE}?{urlencode(params)}"


def fetch_jsonstat(url: str) -> dict:
    """Fetch JSON-stat data from Eurostat API."""
    print(f"Fetching Eurostat API...")
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except (HTTPError, URLError) as exc:
        print(f"ERROR: API request failed: {exc}", file=sys.stderr)
        sys.exit(1)


def parse_jsonstat(data: dict) -> list[dict]:
    """Parse JSON-stat format into flat rows.

    JSON-stat uses positional indexing: the value at position P maps to
    dimension indices computed from the sizes array (row-major order).
    """
    dim_ids = data["id"]       # e.g. ["freq", "crops", "strucpro", "geo", "time"]
    sizes = data["size"]       # e.g. [1, 5, 3, 10, 30]
    values = data.get("value", {})
    dimensions = data.get("dimension", {})

    # Build category label lookups for each dimension
    dim_categories: list[list[tuple[str, str]]] = []
    for dim_name in dim_ids:
        dim = dimensions[dim_name]
        cat_index = dim["category"]["index"]
        cat_label = dim["category"].get("label", {})

        # index can be dict {code: position} or list [code, ...]
        if isinstance(cat_index, dict):
            ordered = sorted(cat_index.items(), key=lambda x: x[1])
            cats = [(code, cat_label.get(code, code)) for code, _ in ordered]
        else:
            cats = [(code, cat_label.get(code, code)) for code in cat_index]

        dim_categories.append(cats)

    # Compute strides for positional decoding
    strides = []
    stride = 1
    for s in reversed(sizes):
        strides.append(stride)
        stride *= s
    strides.reverse()

    rows = []
    for pos_str, val in values.items():
        if val is None:
            continue

        pos = int(pos_str)

        # Decode position into dimension indices
        indices = []
        remaining = pos
        for i, s in enumerate(strides):
            idx = remaining // s
            remaining %= s
            indices.append(idx)

        # Look up category codes/labels
        cats = {}
        for i, dim_name in enumerate(dim_ids):
            code, label = dim_categories[i][indices[i]]
            cats[dim_name] = (code, label)

        # Filter: only target dimensions
        crop_code, crop_label = cats.get("crops", ("", ""))
        metric_code, metric_label_raw = cats.get("strucpro", ("", ""))
        geo_code, geo_label = cats.get("geo", ("", ""))
        time_code, _ = cats.get("time", ("", ""))

        if crop_code not in TARGET_CROPS:
            continue
        if metric_code not in TARGET_METRICS:
            continue
        if geo_code not in TARGET_GEO:
            continue

        try:
            year = int(time_code)
        except ValueError:
            continue

        rows.append({
            "geo": geo_code,
            "geo_label": geo_label,
            "crop_code": crop_code,
            "crop_label": TARGET_CROPS[crop_code],
            "metric_code": metric_code,
            "metric_label": TARGET_METRICS[metric_code],
            "year": year,
            "value": val,
            "unit": METRIC_UNITS.get(metric_code, ""),
        })

    return rows


def main():
    parser = argparse.ArgumentParser(
        description="ETL: Eurostat crop production for cold-climate cereals"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show filter plan only"
    )
    parser.add_argument(
        "--year-min", type=int, default=1990, help="Start year (default: 1990)"
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print("=== Eurostat ETL Dry Run ===")
        print(f"Dataset: apro_cpsh1 (Crop production in EU standard humidity)")
        print(f"Crops: {', '.join(f'{k} ({v})' for k, v in sorted(TARGET_CROPS.items()))}")
        print(f"Countries: {', '.join(f'{k} ({v})' for k, v in sorted(TARGET_GEO.items()))}")
        print(f"Metrics: {', '.join(f'{k} ({v})' for k, v in sorted(TARGET_METRICS.items()))}")
        print(f"Years: {args.year_min}–present")
        est = len(TARGET_CROPS) * len(TARGET_GEO) * len(TARGET_METRICS) * (2025 - args.year_min + 1)
        print(f"Max possible rows: {est:,}")
        print(f"\nAPI: {API_BASE}")
        return

    # Phase 1: Fetch
    url = build_api_url(args.year_min)
    data = fetch_jsonstat(url)

    # Phase 2: Parse
    print("Parsing JSON-stat response...")
    rows = parse_jsonstat(data)

    if not rows:
        print("No matching records found.")
        sys.exit(1)

    # Sort by geo, crop, metric, year
    rows.sort(key=lambda r: (r["geo"], r["crop_code"], r["metric_code"], r["year"]))

    # Phase 3: Write CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows):,} rows -> {OUTPUT_CSV.name}")

    # Summary
    crops = sorted(set(r["crop_label"] for r in rows))
    geos = sorted(set(r["geo_label"] for r in rows))
    years = sorted(set(r["year"] for r in rows))
    metrics = sorted(set(r["metric_label"] for r in rows))

    print(f"\nCrops ({len(crops)}): {', '.join(crops)}")
    print(f"Countries ({len(geos)}): {', '.join(geos)}")
    print(f"Years: {min(years)}–{max(years)} ({len(years)} years)")
    print(f"Metrics ({len(metrics)}): {', '.join(metrics)}")

    # Top producers (latest year with data)
    latest_year = max(years)
    print(f"\nTop producers ({latest_year}, production in 1000 t):")
    production = [
        r for r in rows
        if r["year"] == latest_year and r["metric_code"] == "PR_HU_EU"
    ]
    production.sort(key=lambda r: float(r["value"]), reverse=True)
    for r in production[:10]:
        val = float(r["value"])
        print(f"  {r['geo_label']}: {r['crop_label']} — {val:,.1f} kt")


if __name__ == "__main__":
    main()
