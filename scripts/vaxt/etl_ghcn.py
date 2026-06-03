#!/usr/bin/env python3
"""ETL: Download NOAA GHCN-Daily station metadata and TMIN observations.

Downloads station/inventory metadata (fixed-width text), then streams
by_year CSV.GZ files to extract daily minimum temperature (TMIN) at
Nordic/Baltic stations.

Outputs:
    data/datasets/heritage-grain/ghcn_stations.csv
    data/datasets/heritage-grain/ghcn_climate_observations.csv

Usage:
    python3 scripts/vaxt/etl_ghcn.py                      # Full run (2020-2025)
    python3 scripts/vaxt/etl_ghcn.py --dry-run             # Show station counts only
    python3 scripts/vaxt/etl_ghcn.py --year-min 2015       # Extend range
    python3 scripts/vaxt/etl_ghcn.py --year-max 2024       # Trim range
    python3 scripts/vaxt/etl_ghcn.py --skip-download       # Reuse cached files
    python3 scripts/vaxt/etl_ghcn.py --delay 0.5           # Rate limit between downloads

Source: https://www.ncei.noaa.gov/pub/data/ghcn/daily
License: NOAA public domain, attribution appreciated.
"""

import argparse
import csv
import gzip
import io
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_DIR = WORKSPACE / "data" / "datasets" / "heritage-grain"
CACHE_DIR = OUTPUT_DIR / "cache"
STATIONS_CSV = OUTPUT_DIR / "ghcn_stations.csv"
OBS_CSV = OUTPUT_DIR / "ghcn_climate_observations.csv"

BULK_BASE = "https://www.ncei.noaa.gov/pub/data/ghcn/daily"
STATIONS_URL = f"{BULK_BASE}/ghcnd-stations.txt"
INVENTORY_URL = f"{BULK_BASE}/ghcnd-inventory.txt"
BY_YEAR_URL = BULK_BASE + "/by_year/{year}.csv.gz"

USER_AGENT = "VAV-OS/1.0 (malcolm@vav-os.com) heritage-grain-ETL"

# GHCN uses FIPS country codes (NOT ISO)
NORDIC_FIPS = {
    "NO": "Norway",
    "SW": "Sweden",
    "FI": "Finland",
    "DA": "Denmark",
    "IC": "Iceland",
    "EN": "Estonia",
    "LG": "Latvia",
    "LH": "Lithuania",
    "GL": "Greenland",
}

STATION_COLUMNS = [
    "station_id",
    "name",
    "latitude",
    "longitude",
    "elevation_m",
    "country_fips",
    "country_name",
    "wmo_id",
    "tmin_first_year",
    "tmin_last_year",
]

OBS_COLUMNS = [
    "station_id",
    "date",
    "year",
    "month",
    "tmin_c",
    "quality_flag",
    "source_flag",
]


def download_file(url: str, dest: Path, label: str) -> Path:
    """Download a file if not already cached."""
    if dest.exists():
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  Cached: {dest.name} ({size_mb:.1f} MB)")
        return dest

    print(f"  Downloading {label}...")
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=300) as resp:
            data = resp.read()
    except (HTTPError, URLError) as exc:
        print(f"ERROR: Download failed: {exc}", file=sys.stderr)
        sys.exit(1)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    size_mb = len(data) / (1024 * 1024)
    print(f"  Downloaded {size_mb:.1f} MB -> {dest.name}")
    return dest


def parse_stations(path: Path) -> dict[str, dict]:
    """Parse ghcnd-stations.txt (fixed-width).

    Format (per NOAA readme):
        ID            1-11   Character
        LATITUDE     13-20   Real
        LONGITUDE    22-30   Real
        ELEVATION    32-37   Real
        STATE        39-40   Character
        NAME         42-71   Character
        GSN FLAG     73-75   Character
        HCN/CRN FLAG 77-79   Character
        WMO ID       81-85   Character
    """
    stations = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if len(line) < 71:
            continue
        sid = line[0:11].strip()
        fips = sid[:2]
        if fips not in NORDIC_FIPS:
            continue

        lat = line[12:20].strip()
        lon = line[21:30].strip()
        elev = line[31:37].strip()
        name = line[41:71].strip()
        wmo = line[80:85].strip() if len(line) >= 85 else ""

        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except ValueError:
            continue

        try:
            elev_f = float(elev)
            if elev_f == -999.9:
                elev_f = None
        except ValueError:
            elev_f = None

        stations[sid] = {
            "station_id": sid,
            "name": name,
            "latitude": lat_f,
            "longitude": lon_f,
            "elevation_m": elev_f if elev_f is not None else "",
            "country_fips": fips,
            "country_name": NORDIC_FIPS[fips],
            "wmo_id": wmo if wmo != "     " else "",
        }
    return stations


def parse_inventory(path: Path, stations: dict[str, dict]) -> dict[str, dict]:
    """Parse ghcnd-inventory.txt and filter for TMIN at target stations.

    Format:
        ID            1-11   Character
        LATITUDE     13-20   Real
        LONGITUDE    22-30   Real
        ELEMENT      32-35   Character
        FIRSTYEAR    37-40   Integer
        LASTYEAR     42-45   Integer
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if len(line) < 45:
            continue
        sid = line[0:11].strip()
        if sid not in stations:
            continue
        element = line[31:35].strip()
        if element != "TMIN":
            continue
        try:
            first_year = int(line[36:40].strip())
            last_year = int(line[41:45].strip())
        except ValueError:
            continue
        stations[sid]["tmin_first_year"] = first_year
        stations[sid]["tmin_last_year"] = last_year

    # Keep only stations that have TMIN inventory
    return {
        sid: s for sid, s in stations.items()
        if "tmin_first_year" in s
    }


def stream_by_year(
    gz_path: Path, target_ids: set[str]
) -> list[dict]:
    """Stream-decompress a by_year CSV.GZ and filter for TMIN at target stations.

    by_year CSV columns: ID, DATE, ELEMENT, VALUE, M-FLAG, Q-FLAG, S-FLAG, OBS-TIME
    """
    rows = []
    with gzip.open(gz_path, "rt", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for record in reader:
            if len(record) < 7:
                continue
            sid = record[0]
            if sid not in target_ids:
                continue
            element = record[2]
            if element != "TMIN":
                continue
            # Q-FLAG (index 5): blank = passed all QC
            qflag = record[5].strip()
            if qflag:
                continue
            # VALUE (index 3): tenths of degrees C; -9999 = missing
            try:
                raw_val = int(record[3])
            except ValueError:
                continue
            if raw_val == -9999:
                continue

            date_str = record[1]  # YYYYMMDD
            try:
                year = int(date_str[:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])
                iso_date = f"{year:04d}-{month:02d}-{day:02d}"
            except (ValueError, IndexError):
                continue

            rows.append({
                "station_id": sid,
                "date": iso_date,
                "year": year,
                "month": month,
                "tmin_c": round(raw_val / 10.0, 1),
                "quality_flag": "",
                "source_flag": record[6].strip() if len(record) > 6 else "",
            })
    return rows


def main():
    parser = argparse.ArgumentParser(
        description="ETL: NOAA GHCN-Daily TMIN for Nordic/Baltic stations"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show station counts only"
    )
    parser.add_argument(
        "--skip-download", action="store_true", help="Reuse cached files"
    )
    parser.add_argument(
        "--year-min", type=int, default=2020, help="Start year (default: 2020)"
    )
    parser.add_argument(
        "--year-max", type=int, default=2025, help="End year (default: 2025)"
    )
    parser.add_argument(
        "--delay", type=float, default=0.5, help="Seconds between downloads (default: 0.5)"
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # --- Phase 1: Download and parse metadata ---
    print("=== Phase 1: Station metadata ===")

    stations_file = CACHE_DIR / "ghcnd-stations.txt"
    inventory_file = CACHE_DIR / "ghcnd-inventory.txt"

    if not args.skip_download:
        download_file(STATIONS_URL, stations_file, "stations metadata (~11 MB)")
        time.sleep(args.delay)
        download_file(INVENTORY_URL, inventory_file, "inventory (~35 MB)")
    else:
        if not stations_file.exists() or not inventory_file.exists():
            print("ERROR: --skip-download but cached files not found", file=sys.stderr)
            sys.exit(1)
        print("  Using cached metadata files")

    print("  Parsing stations...")
    all_stations = parse_stations(stations_file)
    print(f"  Nordic/Baltic stations: {len(all_stations)}")

    print("  Parsing TMIN inventory...")
    tmin_stations = parse_inventory(inventory_file, all_stations)
    print(f"  Stations with TMIN data: {len(tmin_stations)}")

    # Summary by country
    print("\n  Stations by country:")
    by_country: dict[str, int] = {}
    for s in tmin_stations.values():
        cc = s["country_name"]
        by_country[cc] = by_country.get(cc, 0) + 1
    for country, count in sorted(by_country.items(), key=lambda x: -x[1]):
        print(f"    {country}: {count}")

    if args.dry_run:
        print(f"\n=== Dry Run ===")
        print(f"Target countries: {', '.join(sorted(NORDIC_FIPS.values()))}")
        print(f"Year range: {args.year_min}–{args.year_max}")
        print(f"Stations with TMIN: {len(tmin_stations)}")
        years_to_fetch = list(range(args.year_min, args.year_max + 1))
        print(f"Years to download: {len(years_to_fetch)} ({years_to_fetch[0]}–{years_to_fetch[-1]})")
        print(f"\nSource: {BULK_BASE}")
        return

    # Write stations CSV
    with open(STATIONS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=STATION_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for s in sorted(tmin_stations.values(), key=lambda x: x["station_id"]):
            writer.writerow(s)
    print(f"\n  Wrote {len(tmin_stations)} stations -> {STATIONS_CSV.name}")

    # --- Phase 2: Download and filter by_year files ---
    print(f"\n=== Phase 2: TMIN observations ({args.year_min}–{args.year_max}) ===")
    target_ids = set(tmin_stations.keys())
    all_obs: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (station_id, date) dedup

    for year in range(args.year_min, args.year_max + 1):
        gz_name = f"{year}.csv.gz"
        gz_path = CACHE_DIR / gz_name
        url = BY_YEAR_URL.format(year=year)

        if not args.skip_download or not gz_path.exists():
            download_file(url, gz_path, f"{year} daily data")
            time.sleep(args.delay)
        else:
            print(f"  Cached: {gz_name}")

        print(f"  Filtering {year}...", end=" ", flush=True)
        year_rows = stream_by_year(gz_path, target_ids)

        # Deduplicate
        new_rows = []
        for r in year_rows:
            key = (r["station_id"], r["date"])
            if key not in seen:
                seen.add(key)
                new_rows.append(r)

        all_obs.extend(new_rows)
        print(f"{len(new_rows):,} obs ({len(all_obs):,} total)")

    if not all_obs:
        print("No observations found.")
        sys.exit(1)

    # Sort by station_id, date
    all_obs.sort(key=lambda r: (r["station_id"], r["date"]))

    # Write observations CSV
    with open(OBS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OBS_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_obs)
    print(f"\n  Wrote {len(all_obs):,} observations -> {OBS_CSV.name}")

    # --- Phase 3: Summary ---
    print(f"\n=== Summary ===")

    # By country
    obs_by_country: dict[str, int] = {}
    for r in all_obs:
        fips = r["station_id"][:2]
        country = NORDIC_FIPS.get(fips, fips)
        obs_by_country[country] = obs_by_country.get(country, 0) + 1
    print("Observations by country:")
    for country, count in sorted(obs_by_country.items(), key=lambda x: -x[1]):
        print(f"  {country}: {count:,}")

    # By year
    obs_by_year: dict[int, int] = {}
    for r in all_obs:
        obs_by_year[r["year"]] = obs_by_year.get(r["year"], 0) + 1
    print("\nObservations by year:")
    for year in sorted(obs_by_year):
        print(f"  {year}: {obs_by_year[year]:,}")

    # Extremes
    coldest = min(all_obs, key=lambda r: r["tmin_c"])
    coldest_name = tmin_stations.get(coldest["station_id"], {}).get("name", "?")
    print(f"\nColdest observation: {coldest['tmin_c']}°C at {coldest_name} ({coldest['station_id']}) on {coldest['date']}")

    unique_stations = len(set(r["station_id"] for r in all_obs))
    print(f"Unique stations with data: {unique_stations}")
    print(f"Date range: {all_obs[0]['date']} to {all_obs[-1]['date']}")


if __name__ == "__main__":
    main()
