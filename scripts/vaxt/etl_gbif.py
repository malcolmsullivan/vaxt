#!/usr/bin/env python3
"""ETL: Fetch cold-hardy crop wild relative occurrences from GBIF.

Uses GBIF REST API v1 to pull occurrence records for cereal and fruit
wild relatives observed in Nordic, Arctic, and boreal regions — evidence
of natural cold adaptation.

Outputs:
    data/datasets/heritage-grain/gbif_occurrences.csv

Usage:
    python3 scripts/vaxt/etl_gbif.py                    # Full run
    python3 scripts/vaxt/etl_gbif.py --dry-run           # List species/counts only
    python3 scripts/vaxt/etl_gbif.py --delay 1.5         # Slower rate limit
    python3 scripts/vaxt/etl_gbif.py --limit 500         # Max records per species

GBIF API:
    https://api.gbif.org/v1/occurrence/search
    Free, no API key required.  Rate-limited to 1 req/s by default.
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_DIR = WORKSPACE / "data" / "datasets" / "heritage-grain"
OUTPUT_CSV = OUTPUT_DIR / "gbif_occurrences.csv"

USER_AGENT = "VAV-OS/1.0 (malcolm@vav-os.com) heritage-grain-ETL"
API_BASE = "https://api.gbif.org/v1"

# Target species — cold-hardy crop wild relatives and landraces.
# taxonKey = GBIF backbone taxonomy key for the genus or species.
# We search at genus level for wild species, filtered to Nordic/Arctic countries.
TAXA = [
    # Cereals — wild relatives (GBIF backbone genus keys)
    {"taxon_key": 2703501, "name": "Aegilops", "group": "wheat_wild_relative"},
    {"taxon_key": 2706388, "name": "Triticum (wild)", "group": "wheat_wild_relative",
     "species_filter": ["Triticum monococcum", "Triticum dicoccoides", "Triticum boeoticum"]},
    {"taxon_key": 2706050, "name": "Hordeum (wild)", "group": "barley_wild_relative"},
    {"taxon_key": 2705965, "name": "Secale (wild)", "group": "rye_wild_relative"},
    {"taxon_key": 2705282, "name": "Avena (wild)", "group": "oat_wild_relative"},
    # Forage grasses
    {"taxon_key": 2706001, "name": "Phleum (timothy)", "group": "forage_grass"},
    {"taxon_key": 2704913, "name": "Festuca (fescue)", "group": "forage_grass"},
    {"taxon_key": 2706217, "name": "Lolium (ryegrass)", "group": "forage_grass"},
    # Berry wild relatives
    {"taxon_key": 2988638, "name": "Rubus (wild)", "group": "berry_wild_relative"},
    {"taxon_key": 2882813, "name": "Vaccinium (wild)", "group": "berry_wild_relative"},
    {"taxon_key": 2986095, "name": "Ribes (wild)", "group": "berry_wild_relative"},
    {"taxon_key": 3039284, "name": "Hippophae (sea buckthorn)", "group": "berry_wild_relative"},
    # Fruit tree wild relatives
    {"taxon_key": 3001068, "name": "Malus (wild apple)", "group": "fruit_wild_relative"},
    {"taxon_key": 3020559, "name": "Prunus (wild)", "group": "fruit_wild_relative"},
]

# Nordic + Arctic + Boreal countries
COUNTRIES = ["NO", "SE", "FI", "IS", "DK", "GL", "RU", "CA", "EE", "LV", "LT"]

CSV_COLUMNS = [
    "gbif_id",
    "species",
    "genus",
    "family",
    "group",
    "taxon_key",
    "decimal_latitude",
    "decimal_longitude",
    "country",
    "country_code",
    "locality",
    "event_date",
    "year",
    "month",
    "basis_of_record",
    "institution_code",
    "collection_code",
    "catalog_number",
    "recorded_by",
    "dataset_name",
    "occurrence_status",
    "coordinate_uncertainty_m",
    "elevation_m",
]


def fetch_json(url: str, delay: float = 1.0, retries: int = 3) -> dict | None:
    """Fetch URL and parse JSON. Retries with exponential backoff."""
    for attempt in range(retries):
        req = Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        try:
            with urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            if attempt < retries - 1:
                wait = delay * (2 ** (attempt + 1))
                print(f"  RETRY {attempt + 1}/{retries}: {exc} (waiting {wait:.0f}s)",
                      file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"  WARN: {url} -> {exc}", file=sys.stderr)
                return None
        finally:
            time.sleep(delay)


def search_occurrences(
    taxon_key: int,
    country: str,
    limit: int = 300,
    delay: float = 1.0,
) -> list[dict]:
    """Search GBIF occurrences for a taxon in a country, handling pagination."""
    all_results = []
    offset = 0
    page_size = min(limit, 300)  # GBIF max page size is 300

    while offset < limit:
        params = {
            "taxonKey": taxon_key,
            "country": country,
            "hasCoordinate": "true",
            "occurrenceStatus": "PRESENT",
            "limit": min(page_size, limit - offset),
            "offset": offset,
        }
        url = f"{API_BASE}/occurrence/search?{urlencode(params)}"
        data = fetch_json(url, delay)
        if not data:
            break

        results = data.get("results", [])
        if not results:
            break

        all_results.extend(results)

        if data.get("endOfRecords", True):
            break
        offset += len(results)

    return all_results


def occurrence_to_row(occ: dict, group: str) -> dict:
    """Map a GBIF occurrence record to our CSV schema."""
    return {
        "gbif_id": occ.get("gbifID", occ.get("key", "")),
        "species": occ.get("species", ""),
        "genus": occ.get("genus", ""),
        "family": occ.get("family", ""),
        "group": group,
        "taxon_key": occ.get("taxonKey", ""),
        "decimal_latitude": occ.get("decimalLatitude", ""),
        "decimal_longitude": occ.get("decimalLongitude", ""),
        "country": occ.get("country", ""),
        "country_code": occ.get("countryCode", ""),
        "locality": occ.get("locality", ""),
        "event_date": occ.get("eventDate", ""),
        "year": occ.get("year", ""),
        "month": occ.get("month", ""),
        "basis_of_record": occ.get("basisOfRecord", ""),
        "institution_code": occ.get("institutionCode", ""),
        "collection_code": occ.get("collectionCode", ""),
        "catalog_number": occ.get("catalogNumber", ""),
        "recorded_by": occ.get("recordedBy", ""),
        "dataset_name": occ.get("datasetName", ""),
        "occurrence_status": occ.get("occurrenceStatus", ""),
        "coordinate_uncertainty_m": occ.get("coordinateUncertaintyInMeters", ""),
        "elevation_m": occ.get("elevation", ""),
    }


def main():
    parser = argparse.ArgumentParser(
        description="ETL: GBIF cold-hardy crop wild relative occurrences"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show species/country counts without downloading",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds between requests (default: 1.0)",
    )
    parser.add_argument(
        "--limit", type=int, default=300,
        help="Max records per species per country (default: 300)",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Phase 1: Survey available data
    print("=== Phase 1: Surveying GBIF occurrences ===")
    plan: list[dict] = []

    for taxon in TAXA:
        tk = taxon["taxon_key"]
        name = taxon["name"]
        group = taxon["group"]

        for cc in COUNTRIES:
            # Quick count query (limit=0 just to get count)
            params = {
                "taxonKey": tk,
                "country": cc,
                "hasCoordinate": "true",
                "occurrenceStatus": "PRESENT",
                "limit": 0,
            }
            url = f"{API_BASE}/occurrence/search?{urlencode(params)}"
            data = fetch_json(url, args.delay)
            count = data.get("count", 0) if data else 0

            if count > 0:
                plan.append({
                    "taxon_key": tk,
                    "name": name,
                    "group": group,
                    "country": cc,
                    "count": count,
                    "species_filter": taxon.get("species_filter"),
                })
                print(f"  {name} in {cc}: {count:,} occurrences")

    total_available = sum(p["count"] for p in plan)
    print(f"\nTotal: {len(plan)} taxon-country pairs, {total_available:,} occurrences available")

    if args.dry_run:
        print(f"\nDry run — pass without --dry-run to fetch records (limit={args.limit}/species/country).")
        return

    if not plan:
        print("No occurrences found. Check network connectivity.")
        sys.exit(1)

    # Phase 2: Fetch occurrence records
    print(f"\n=== Phase 2: Fetching occurrences (limit={args.limit}/species/country) ===")
    all_rows: list[dict] = []
    seen_ids: set[str] = set()

    for i, p in enumerate(plan, 1):
        occs = search_occurrences(
            taxon_key=p["taxon_key"],
            country=p["country"],
            limit=args.limit,
            delay=args.delay,
        )

        # Apply species filter if specified
        species_filter = p.get("species_filter")
        if species_filter:
            occs = [o for o in occs if o.get("species", "") in species_filter]

        for occ in occs:
            gid = str(occ.get("gbifID", occ.get("key", "")))
            if gid and gid not in seen_ids:
                seen_ids.add(gid)
                all_rows.append(occurrence_to_row(occ, p["group"]))

        print(f"  [{i}/{len(plan)}] {p['name']} in {p['country']}: "
              f"{len(occs)} fetched ({len(all_rows)} total unique)")

    if not all_rows:
        print("No records retrieved.")
        sys.exit(1)

    # Phase 3: Write CSV
    print(f"\n=== Phase 3: Writing CSV ===")
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Wrote {len(all_rows)} records to {OUTPUT_CSV.name}")

    # Summary
    print(f"\n=== Summary ===")
    by_group: dict[str, int] = {}
    by_country: dict[str, int] = {}
    by_genus: dict[str, int] = {}
    for r in all_rows:
        by_group[r["group"]] = by_group.get(r["group"], 0) + 1
        by_country[r["country_code"]] = by_country.get(r["country_code"], 0) + 1
        by_genus[r["genus"]] = by_genus.get(r["genus"], 0) + 1

    print("By group:")
    for g, n in sorted(by_group.items(), key=lambda x: -x[1]):
        print(f"  {g}: {n:,}")

    print("By country:")
    for c, n in sorted(by_country.items(), key=lambda x: -x[1]):
        print(f"  {c}: {n:,}")

    print("By genus (top 10):")
    for g, n in sorted(by_genus.items(), key=lambda x: -x[1])[:10]:
        print(f"  {g}: {n:,}")


if __name__ == "__main__":
    main()
