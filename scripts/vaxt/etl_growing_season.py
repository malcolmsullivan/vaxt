#!/usr/bin/env python3
"""ETL: Derive growing-season metrics from existing GHCN-Daily TMIN data.

Reads ghcn_climate_observations.csv and computes per-station, per-year:
  - Last spring frost date (last TMIN <= 0C in Jan-Jun)
  - First fall frost date (first TMIN <= 0C in Aug-Dec)
  - Frost-free days (gap between the two)
  - Hard-freeze days (days with TMIN <= -20C, relevant for hardening)
  - Annual minimum TMIN (coldest reading)

No network calls required -- pure derivation from existing data.

Outputs:
    data/datasets/heritage-grain/growing_season.csv

Usage:
    python3 scripts/vaxt/etl_growing_season.py                # Full run
    python3 scripts/vaxt/etl_growing_season.py --dry-run       # Show station/year counts only
    python3 scripts/vaxt/etl_growing_season.py --frost-threshold -2  # Custom frost cutoff

Source: Derived from NOAA GHCN-Daily TMIN (etl_ghcn.py output)
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_DIR = WORKSPACE / "data" / "datasets" / "heritage-grain"
OBS_CSV = OUTPUT_DIR / "ghcn_climate_observations.csv"
STATIONS_CSV = OUTPUT_DIR / "ghcn_stations.csv"
OUTPUT_CSV = OUTPUT_DIR / "growing_season.csv"

OUTPUT_COLUMNS = [
    "station_id",
    "station_name",
    "country_name",
    "latitude",
    "longitude",
    "year",
    "last_spring_frost",
    "first_fall_frost",
    "frost_free_days",
    "hard_freeze_days",
    "annual_min_tmin_c",
    "obs_count",
]


def load_stations(path: Path) -> dict[str, dict]:
    """Load station metadata for name/country/coords."""
    stations = {}
    if not path.exists():
        return stations
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            stations[row["station_id"]] = {
                "station_name": row.get("name", ""),
                "country_name": row.get("country_name", ""),
                "latitude": row.get("latitude", ""),
                "longitude": row.get("longitude", ""),
            }
    return stations


def load_observations(path: Path) -> dict[tuple[str, int], list[tuple[str, float]]]:
    """Load TMIN observations grouped by (station_id, year).

    Returns: {(station_id, year): [(date_str, tmin_c), ...]}
    """
    groups: dict[tuple[str, int], list[tuple[str, float]]] = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                sid = row["station_id"]
                year = int(row["year"])
                tmin = float(row["tmin_c"])
                date = row["date"]
            except (KeyError, ValueError):
                continue
            groups[(sid, year)].append((date, tmin))
    return groups


def compute_growing_season(
    obs: list[tuple[str, float]],
    frost_threshold: float,
) -> dict:
    """Compute growing-season metrics for a single station-year.

    Args:
        obs: sorted list of (date_str, tmin_c)
        frost_threshold: temperature at or below which counts as frost (default 0)
    """
    obs.sort(key=lambda x: x[0])

    # Spring: last frost date in Jan-Jun (month <= 6)
    last_spring_frost = None
    for date, tmin in obs:
        month = int(date[5:7])
        if month > 6:
            break
        if tmin <= frost_threshold:
            last_spring_frost = date

    # Fall: first frost date in Aug-Dec (month >= 8)
    first_fall_frost = None
    for date, tmin in obs:
        month = int(date[5:7])
        if month < 8:
            continue
        if tmin <= frost_threshold:
            first_fall_frost = date
            break

    # Frost-free days
    frost_free_days = ""
    if last_spring_frost and first_fall_frost:
        # Parse dates manually (avoid datetime import for stdlib-only pattern)
        sy, sm, sd = (int(x) for x in last_spring_frost.split("-"))
        fy, fm, fd = (int(x) for x in first_fall_frost.split("-"))
        spring_doy = _day_of_year(sy, sm, sd)
        fall_doy = _day_of_year(fy, fm, fd)
        frost_free_days = max(0, fall_doy - spring_doy)

    # Hard-freeze days (TMIN <= -20C)
    hard_freeze_days = sum(1 for _, tmin in obs if tmin <= -20.0)

    # Annual minimum
    annual_min = min(tmin for _, tmin in obs)

    return {
        "last_spring_frost": last_spring_frost or "",
        "first_fall_frost": first_fall_frost or "",
        "frost_free_days": frost_free_days,
        "hard_freeze_days": hard_freeze_days,
        "annual_min_tmin_c": round(annual_min, 1),
        "obs_count": len(obs),
    }


def _day_of_year(year: int, month: int, day: int) -> int:
    """Day of year (1-366) without datetime."""
    days_in_month = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        days_in_month[2] = 29
    return sum(days_in_month[:month]) + day


def main():
    parser = argparse.ArgumentParser(
        description="ETL: Derive growing-season metrics from GHCN TMIN"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show station/year counts only"
    )
    parser.add_argument(
        "--frost-threshold",
        type=float,
        default=0.0,
        help="Frost threshold in C (default: 0.0)",
    )
    args = parser.parse_args()

    if not OBS_CSV.exists():
        print(f"ERROR: {OBS_CSV.name} not found. Run etl_ghcn.py first.", file=sys.stderr)
        sys.exit(1)

    # Load data
    print("=== Growing Season Derivation ===")
    print(f"Frost threshold: {args.frost_threshold}C")

    print("  Loading station metadata...", end=" ", flush=True)
    stations = load_stations(STATIONS_CSV)
    print(f"{len(stations)} stations")

    print("  Loading TMIN observations...", end=" ", flush=True)
    groups = load_observations(OBS_CSV)
    unique_stations = len(set(sid for sid, _ in groups))
    unique_years = sorted(set(yr for _, yr in groups))
    print(f"{len(groups)} station-years ({unique_stations} stations, {len(unique_years)} years)")

    if args.dry_run:
        print(f"\n=== Dry Run ===")
        print(f"Stations with TMIN data: {unique_stations}")
        print(f"Years: {min(unique_years)}–{max(unique_years)}")
        print(f"Station-years to process: {len(groups)}")
        print(f"Frost threshold: {args.frost_threshold}C")
        print(f"Output would be: {OUTPUT_CSV.name}")
        return

    # Compute growing season for each station-year
    print("  Computing growing season metrics...")
    rows = []
    for (sid, year), obs in sorted(groups.items()):
        if len(obs) < 30:
            # Skip station-years with sparse data
            continue
        metrics = compute_growing_season(obs, args.frost_threshold)
        meta = stations.get(sid, {})
        rows.append({
            "station_id": sid,
            "station_name": meta.get("station_name", ""),
            "country_name": meta.get("country_name", ""),
            "latitude": meta.get("latitude", ""),
            "longitude": meta.get("longitude", ""),
            "year": year,
            **metrics,
        })

    if not rows:
        print("No station-years with sufficient data.")
        sys.exit(1)

    # Write CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Wrote {len(rows)} station-years -> {OUTPUT_CSV.name}")

    # Summary
    print(f"\n=== Summary ===")
    print(f"Station-years: {len(rows)}")
    years_out = sorted(set(r["year"] for r in rows))
    print(f"Years: {min(years_out)}–{max(years_out)}")

    # By country
    by_country: dict[str, int] = {}
    for r in rows:
        cc = r["country_name"] or "Unknown"
        by_country[cc] = by_country.get(cc, 0) + 1
    print("Station-years by country:")
    for country, count in sorted(by_country.items(), key=lambda x: -x[1]):
        print(f"  {country}: {count}")

    # Frost-free day stats
    ff_days = [r["frost_free_days"] for r in rows if r["frost_free_days"] != ""]
    if ff_days:
        ff_int = [int(d) for d in ff_days]
        avg_ff = sum(ff_int) / len(ff_int)
        print(f"\nFrost-free days: avg {avg_ff:.0f}, min {min(ff_int)}, max {max(ff_int)}")

    # Coldest station-year
    coldest = min(rows, key=lambda r: r["annual_min_tmin_c"])
    print(f"Coldest: {coldest['station_name']} ({coldest['station_id']}) in {coldest['year']}: {coldest['annual_min_tmin_c']}C")

    # Most hard-freeze days
    hardest = max(rows, key=lambda r: r["hard_freeze_days"])
    print(f"Most hard-freeze days: {hardest['station_name']} ({hardest['station_id']}) in {hardest['year']}: {hardest['hard_freeze_days']} days <= -20C")


if __name__ == "__main__":
    main()
