#!/usr/bin/env python3
"""ETL: Compute photoperiod (day length) for field trial sites.

Uses spherical geometry to compute day length at each site latitude for
key dates in the growing season. Nordic cereals are long-day sensitive
(16h+), so moving varieties across latitudes fails without this data.

No network calls required -- pure computation from field_trial_sites.csv.

Outputs:
    data/datasets/heritage-grain/photoperiod_zones.csv

Usage:
    python3 scripts/vaxt/etl_photoperiod.py              # Full run
    python3 scripts/vaxt/etl_photoperiod.py --dry-run     # Show site counts only

Source: Computed from latitude using solar declination geometry.
"""

import argparse
import csv
import math
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_DIR = WORKSPACE / "data" / "datasets" / "heritage-grain"
SITES_CSV = SCRIPT_DIR / "field_trial_sites.csv"
OUTPUT_CSV = OUTPUT_DIR / "photoperiod_zones.csv"

OUTPUT_COLUMNS = [
    "site_id",
    "name",
    "country",
    "latitude",
    "longitude",
    "daylength_summer_solstice_h",
    "daylength_winter_solstice_h",
    "daylength_spring_equinox_h",
    "daylength_jun1_h",
    "daylength_aug1_h",
    "photoperiod_class",
    "polar_day",
    "polar_night",
    "annual_daylength_range_h",
]

# Key dates as day-of-year
DOY_SPRING_EQUINOX = 80   # ~March 21
DOY_SUMMER_SOLSTICE = 172  # ~June 21
DOY_WINTER_SOLSTICE = 355  # ~Dec 21
DOY_JUN1 = 152             # June 1 (start of Nordic growing)
DOY_AUG1 = 213             # Aug 1 (grain fill period)

# Earth's axial tilt (degrees)
AXIAL_TILT = 23.4397


def solar_declination(doy: int) -> float:
    """Solar declination angle in degrees for a given day of year.

    Uses the simplified equation:
        delta = -23.44 * cos(360/365 * (doy + 10))
    """
    return -AXIAL_TILT * math.cos(math.radians(360.0 / 365.0 * (doy + 10)))


def day_length(latitude: float, doy: int) -> float:
    """Compute astronomical day length in hours.

    Args:
        latitude: degrees north (negative for south)
        doy: day of year (1-366)

    Returns:
        Day length in decimal hours. Returns 24.0 for polar day,
        0.0 for polar night.
    """
    decl = solar_declination(doy)
    lat_rad = math.radians(latitude)
    decl_rad = math.radians(decl)

    # Hour angle at sunrise/sunset
    cos_ha = -math.tan(lat_rad) * math.tan(decl_rad)

    if cos_ha < -1.0:
        return 24.0  # Polar day (midnight sun)
    if cos_ha > 1.0:
        return 0.0   # Polar night

    hour_angle = math.acos(cos_ha)
    return 2.0 * math.degrees(hour_angle) / 15.0


def classify_photoperiod(summer_daylength: float) -> str:
    """Classify photoperiod sensitivity based on summer solstice day length.

    Nordic/boreal classification:
        ultra-long-day:  >= 20h (polar/sub-polar, midnight sun zone)
        long-day:        >= 16h (typical Nordic cereal zone)
        intermediate:    14-16h (temperate, shorter summers)
        neutral:         < 14h  (day-neutral or short-day zone)
    """
    if summer_daylength >= 20.0:
        return "ultra-long-day"
    if summer_daylength >= 16.0:
        return "long-day"
    if summer_daylength >= 14.0:
        return "intermediate"
    return "neutral"


def main():
    parser = argparse.ArgumentParser(
        description="ETL: Compute photoperiod zones for field trial sites"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show site counts only"
    )
    args = parser.parse_args()

    if not SITES_CSV.exists():
        print(f"ERROR: {SITES_CSV.name} not found.", file=sys.stderr)
        sys.exit(1)

    # Load field trial sites
    print("=== Photoperiod Zone Computation ===")
    sites = []
    with open(SITES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except (KeyError, ValueError):
                continue
            sites.append({
                "site_id": row["site_id"],
                "name": row["name"],
                "country": row["country"],
                "latitude": lat,
                "longitude": lon,
            })

    print(f"  Field trial sites: {len(sites)}")

    if args.dry_run:
        print(f"\n=== Dry Run ===")
        print(f"Sites to process: {len(sites)}")
        lats = [s["latitude"] for s in sites]
        print(f"Latitude range: {min(lats):.2f}N to {max(lats):.2f}N")
        countries = sorted(set(s["country"] for s in sites))
        print(f"Countries: {', '.join(countries)}")
        print(f"Output would be: {OUTPUT_CSV.name}")
        return

    # Compute photoperiod for each site
    print("  Computing day lengths...")
    rows = []
    for site in sites:
        lat = site["latitude"]

        dl_summer = round(day_length(lat, DOY_SUMMER_SOLSTICE), 2)
        dl_winter = round(day_length(lat, DOY_WINTER_SOLSTICE), 2)
        dl_equinox = round(day_length(lat, DOY_SPRING_EQUINOX), 2)
        dl_jun1 = round(day_length(lat, DOY_JUN1), 2)
        dl_aug1 = round(day_length(lat, DOY_AUG1), 2)

        rows.append({
            "site_id": site["site_id"],
            "name": site["name"],
            "country": site["country"],
            "latitude": lat,
            "longitude": site["longitude"],
            "daylength_summer_solstice_h": dl_summer,
            "daylength_winter_solstice_h": dl_winter,
            "daylength_spring_equinox_h": dl_equinox,
            "daylength_jun1_h": dl_jun1,
            "daylength_aug1_h": dl_aug1,
            "photoperiod_class": classify_photoperiod(dl_summer),
            "polar_day": "yes" if dl_summer >= 24.0 else "no",
            "polar_night": "yes" if dl_winter <= 0.0 else "no",
            "annual_daylength_range_h": round(dl_summer - dl_winter, 2),
        })

    # Write CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Wrote {len(rows)} sites -> {OUTPUT_CSV.name}")

    # Summary
    print(f"\n=== Summary ===")

    # By photoperiod class
    by_class: dict[str, int] = {}
    for r in rows:
        cls = r["photoperiod_class"]
        by_class[cls] = by_class.get(cls, 0) + 1
    print("Sites by photoperiod class:")
    for cls in ["ultra-long-day", "long-day", "intermediate", "neutral"]:
        if cls in by_class:
            print(f"  {cls}: {by_class[cls]}")

    # Extremes
    longest = max(rows, key=lambda r: r["daylength_summer_solstice_h"])
    shortest = min(rows, key=lambda r: r["daylength_summer_solstice_h"])
    print(f"\nLongest summer day: {longest['name']} ({longest['country']}) at {longest['latitude']}N: {longest['daylength_summer_solstice_h']}h")
    print(f"Shortest summer day: {shortest['name']} ({shortest['country']}) at {shortest['latitude']}N: {shortest['daylength_summer_solstice_h']}h")

    # Polar sites
    polar = [r for r in rows if r["polar_day"] == "yes"]
    if polar:
        print(f"\nPolar day sites ({len(polar)}):")
        for r in polar:
            print(f"  {r['name']} ({r['country']}): {r['latitude']}N")

    # Annual range
    widest = max(rows, key=lambda r: r["annual_daylength_range_h"])
    print(f"\nWidest annual range: {widest['name']} ({widest['country']}): {widest['annual_daylength_range_h']}h swing")


if __name__ == "__main__":
    main()
