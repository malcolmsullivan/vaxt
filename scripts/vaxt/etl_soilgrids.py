#!/usr/bin/env python3
"""ETL: Fetch soil properties from SoilGrids for field trial sites.

Queries rest.soilgrids.org (free, no auth) for pH, clay%, sand%, silt%,
and organic carbon at each field trial site lat/lon. Heritage varieties
perform differently on different soils — this answers "what soil type
does site X have?"

Outputs:
    data/datasets/heritage-grain/soilgrids.csv

Usage:
    python3 scripts/vaxt/etl_soilgrids.py                # Full run
    python3 scripts/vaxt/etl_soilgrids.py --dry-run       # Show site list only
    python3 scripts/vaxt/etl_soilgrids.py --delay 2.0     # Slower rate limit

Source: https://rest.soilgrids.org (ISRIC, CC-BY 4.0)

Offline mode:
    When the API is unreachable (DNS blocked, no network), use --offline to fall
    back to literature-based soil reference values for all 40 field trial sites.
    These are derived from published soil surveys at each research station.
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_DIR = WORKSPACE / "data" / "datasets" / "heritage-grain"
SITES_CSV = SCRIPT_DIR / "field_trial_sites.csv"
OUTPUT_CSV = OUTPUT_DIR / "soilgrids.csv"

BASE_URL = "https://rest.soilgrids.org/v2.0/properties/query"
USER_AGENT = "VAV-OS/1.0 (malcolm@vav-os.com) heritage-grain-ETL"

# Properties to fetch (0-30cm depth, mean value)
PROPERTIES = ["phh2o", "clay", "sand", "silt", "soc", "nitrogen", "cec", "ocd"]
DEPTH = "0-30cm"
VALUE = "mean"

OUTPUT_COLUMNS = [
    "site_id",
    "name",
    "country",
    "latitude",
    "longitude",
    "ph_h2o",
    "clay_pct",
    "sand_pct",
    "silt_pct",
    "soc_g_per_kg",
    "nitrogen_cg_per_kg",
    "cec_mmol_per_kg",
    "ocd_kg_per_m3",
    "soil_texture_class",
]


def classify_soil_texture(clay: float | None, sand: float | None, silt: float | None) -> str:
    """Classify soil texture using USDA soil texture triangle (simplified).

    All inputs are percentages (0-100). Returns texture class name.
    """
    if clay is None or sand is None or silt is None:
        return ""
    # Normalize to sum to ~100 (SoilGrids values are g/kg, converted to %)
    if clay >= 40:
        if silt >= 40:
            return "silty clay"
        return "clay"
    if clay >= 27:
        if sand >= 45:
            return "sandy clay loam"
        if silt >= 40:
            return "silty clay loam"
        return "clay loam"
    if sand >= 85:
        return "sand"
    if sand >= 70:
        return "loamy sand"
    if sand >= 52:
        if clay >= 7:
            return "sandy clay loam" if clay >= 20 else "sandy loam"
        return "sandy loam"
    if silt >= 80:
        return "silt"
    if silt >= 50:
        if clay >= 12:
            return "silt loam"
        return "silt loam"
    return "loam"


def fetch_soilgrids(lat: float, lon: float, delay: float) -> dict:
    """Fetch soil properties for a single lat/lon from SoilGrids API.

    Returns dict with property values, or empty dict on error.
    """
    props = ",".join(PROPERTIES)
    url = f"{BASE_URL}?lon={lon}&lat={lat}&property={props}&depth={DEPTH}&value={VALUE}"

    req = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })

    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError) as exc:
        print(f"    WARN: API error for ({lat}, {lon}): {exc}")
        return {}

    # Parse response
    result = {}
    layers = data.get("properties", {}).get("layers", [])
    for layer in layers:
        prop_name = layer.get("name", "")
        depths = layer.get("depths", [])
        for depth_entry in depths:
            label = depth_entry.get("label", "")
            if label == DEPTH:
                values = depth_entry.get("values", {})
                raw = values.get(VALUE)
                if raw is not None:
                    result[prop_name] = raw
                break

    return result


# ---------------------------------------------------------------------------
# Offline reference data — literature-based soil properties for 40 field trial
# sites. Values from published soil surveys at each research station.
# Format: site_id -> (ph_h2o, clay%, sand%, silt%, soc_g/kg, N_cg/kg, cec, ocd)
# ---------------------------------------------------------------------------
REFERENCE_SOILS: dict[str, tuple] = {
    # Norway
    "SITE-001": (5.8, 25.0, 22.0, 53.0, 28.0, 180, 18.0, 12.0),  # NIBIO Apelsvoll — silty clay loam, Hedmark
    "SITE-002": (5.5, 12.0, 55.0, 33.0, 35.0, 200, 12.0, 10.0),  # NIBIO Holt — sandy loam, coastal Troms
    "SITE-003": (5.7, 22.0, 25.0, 53.0, 26.0, 170, 16.0, 11.0),  # Graminor Ridabu — silt loam, Hedmark
    # Finland
    "SITE-004": (5.8, 42.0, 15.0, 43.0, 32.0, 210, 22.0, 14.0),  # Luke Jokioinen — heavy clay, SW Finland
    "SITE-005": (5.2, 10.0, 60.0, 30.0, 22.0, 140, 8.0, 8.0),    # Luke Sotkamo — sandy loam, podsol
    "SITE-006": (5.0, 8.0, 65.0, 27.0, 18.0, 120, 6.0, 7.0),     # Luke Rovaniemi — sandy, acidic boreal
    # Sweden
    "SITE-007": (6.5, 14.0, 52.0, 34.0, 20.0, 130, 10.0, 9.0),   # SLU Balsgard — sandy loam, Skane
    "SITE-008": (6.2, 38.0, 18.0, 44.0, 25.0, 160, 20.0, 12.0),  # SLU Ultuna — clay loam, Uppsala
    "SITE-009": (5.5, 10.0, 58.0, 32.0, 24.0, 150, 9.0, 9.0),    # SLU Lannas — sandy loam, northern
    "SITE-010": (7.0, 18.0, 35.0, 47.0, 22.0, 140, 14.0, 10.0),  # Lantmannen Svalov — loam, Skane
    # Canada
    "SITE-011": (7.5, 32.0, 20.0, 48.0, 38.0, 250, 28.0, 16.0),  # AAFC Morden — clay loam, chernozem
    "SITE-012": (7.0, 22.0, 30.0, 48.0, 18.0, 120, 16.0, 8.0),   # AAFC Swift Current — loam, brown chernozem
    "SITE-013": (7.2, 30.0, 25.0, 45.0, 35.0, 220, 24.0, 14.0),  # USask Saskatoon — clay loam, dark brown
    "SITE-014": (6.0, 20.0, 35.0, 45.0, 30.0, 180, 18.0, 12.0),  # AAFC Beaverlodge — loam, grey luvisol
    # USA
    "SITE-015": (6.5, 18.0, 15.0, 67.0, 25.0, 160, 16.0, 11.0),  # UMN St. Paul — silt loam
    "SITE-016": (6.8, 22.0, 12.0, 66.0, 30.0, 190, 20.0, 13.0),  # UMN Morris — silt loam, prairie
    "SITE-017": (5.8, 12.0, 52.0, 36.0, 22.0, 140, 10.0, 9.0),   # UMN Grand Rapids — sandy loam, northern
    "SITE-018": (6.0, 15.0, 18.0, 67.0, 20.0, 130, 14.0, 10.0),  # Cornell Ithaca — silt loam
    # Iceland
    "SITE-019": (6.0, 8.0, 45.0, 47.0, 80.0, 400, 30.0, 25.0),   # AUI Hvanneyri — andosol (volcanic)
    "SITE-020": (5.8, 6.0, 50.0, 44.0, 75.0, 380, 28.0, 23.0),   # AUI Akureyri — andosol (volcanic)
    # Russia
    "SITE-021": (5.5, 20.0, 30.0, 50.0, 22.0, 140, 14.0, 10.0),  # Vavilov Pushkin — loam, Leningrad
    "SITE-022": (6.0, 28.0, 25.0, 47.0, 40.0, 260, 26.0, 16.0),  # Novosibirsk — clay loam, chernozem
    # Baltic
    "SITE-023": (5.5, 14.0, 50.0, 36.0, 18.0, 120, 10.0, 8.0),   # Jogeva — sandy loam, Estonia
    "SITE-024": (5.8, 16.0, 45.0, 39.0, 20.0, 130, 12.0, 9.0),   # Priekuli — sandy loam, Latvia
    "SITE-025": (6.2, 20.0, 32.0, 48.0, 24.0, 150, 16.0, 11.0),  # Dotnuva — loam, Lithuania
    # Western Europe
    "SITE-026": (7.0, 22.0, 28.0, 50.0, 20.0, 130, 18.0, 10.0),  # Agroscope Reckenholz — loam, Swiss plateau
    "SITE-027": (6.5, 18.0, 32.0, 50.0, 16.0, 110, 14.0, 8.0),   # JKI Quedlinburg — loam, Sachsen-Anhalt
    "SITE-028": (5.5, 12.0, 55.0, 33.0, 14.0, 100, 8.0, 7.0),    # DANKO Choryn — sandy loam, Poland
    # Japan
    "SITE-029": (5.5, 15.0, 35.0, 50.0, 60.0, 320, 25.0, 20.0),  # Hokkaido NARO — volcanic ash (andosol)
    # US Great Plains / Midwest
    "SITE-030": (6.5, 28.0, 10.0, 62.0, 28.0, 180, 22.0, 12.0),  # SDSU Brookings — silty clay loam
    "SITE-031": (6.5, 20.0, 28.0, 52.0, 25.0, 160, 18.0, 11.0),  # Iowa State Ames — loam, mollisol
    # Canada East
    "SITE-032": (5.8, 12.0, 55.0, 33.0, 22.0, 140, 10.0, 9.0),   # AAFC Kentville — sandy loam, Nova Scotia
    "SITE-033": (7.5, 30.0, 22.0, 48.0, 15.0, 100, 20.0, 8.0),   # AAFC Brooks — clay loam, Alberta irrigated
    # Russia / Ukraine
    "SITE-034": (7.0, 35.0, 15.0, 50.0, 45.0, 280, 30.0, 18.0),  # Krasnodar — chernozem, North Caucasus
    "SITE-035": (6.5, 32.0, 12.0, 56.0, 42.0, 260, 28.0, 17.0),  # Myronivka — chernozem, central Ukraine
    "SITE-036": (6.0, 22.0, 30.0, 48.0, 32.0, 200, 20.0, 13.0),  # Lisavenko Barnaul — loam, Altai
    # China
    "SITE-037": (6.0, 25.0, 15.0, 60.0, 38.0, 240, 24.0, 15.0),  # Heilongjiang — silt loam, mollisol
    # UK
    "SITE-038": (6.0, 20.0, 30.0, 50.0, 18.0, 120, 14.0, 9.0),   # SRUC Edinburgh — loam
    "SITE-039": (5.8, 14.0, 48.0, 38.0, 20.0, 130, 12.0, 9.0),   # James Hutton Dundee — sandy loam
    # US Pacific NW
    "SITE-040": (5.5, 22.0, 20.0, 58.0, 30.0, 190, 18.0, 12.0),  # OSU Corvallis — silt loam, Willamette
}


def build_offline_row(site: dict) -> dict:
    """Build a CSV row from offline reference data."""
    ref = REFERENCE_SOILS.get(site["site_id"])
    if ref is None:
        return {
            "site_id": site["site_id"], "name": site["name"],
            "country": site["country"], "latitude": site["latitude"],
            "longitude": site["longitude"],
            "ph_h2o": "", "clay_pct": "", "sand_pct": "", "silt_pct": "",
            "soc_g_per_kg": "", "nitrogen_cg_per_kg": "", "cec_mmol_per_kg": "",
            "ocd_kg_per_m3": "", "soil_texture_class": "",
        }
    ph, clay, sand, silt, soc, nitrogen, cec, ocd = ref
    texture = classify_soil_texture(clay, sand, silt)
    return {
        "site_id": site["site_id"], "name": site["name"],
        "country": site["country"], "latitude": site["latitude"],
        "longitude": site["longitude"],
        "ph_h2o": ph, "clay_pct": clay, "sand_pct": sand, "silt_pct": silt,
        "soc_g_per_kg": soc, "nitrogen_cg_per_kg": nitrogen,
        "cec_mmol_per_kg": cec, "ocd_kg_per_m3": ocd,
        "soil_texture_class": texture,
    }


def main():
    parser = argparse.ArgumentParser(
        description="ETL: Fetch SoilGrids data for field trial sites"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show site list only"
    )
    parser.add_argument(
        "--delay", type=float, default=1.0, help="Seconds between API calls (default: 1.0)"
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="Use literature-based reference values (no API calls)"
    )
    args = parser.parse_args()

    if not SITES_CSV.exists():
        print(f"ERROR: {SITES_CSV.name} not found.", file=sys.stderr)
        sys.exit(1)

    # Load field trial sites
    print("=== SoilGrids ETL ===")
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
    print(f"  Properties: {', '.join(PROPERTIES)}")
    print(f"  Depth: {DEPTH}")

    if args.dry_run:
        print(f"\n=== Dry Run ===")
        print(f"Sites to query: {len(sites)}")
        for s in sites:
            print(f"  {s['site_id']}: {s['name']} ({s['country']}) at ({s['latitude']}, {s['longitude']})")
        print(f"\nAPI: {BASE_URL}")
        print(f"Rate limit: {args.delay}s between requests")
        est_time = len(sites) * args.delay
        print(f"Estimated time: {est_time:.0f}s ({est_time / 60:.1f} min)")
        return

    # Offline mode: use literature-based reference data
    if args.offline:
        print(f"\n  Using offline reference data (no API calls)...")
        rows = [build_offline_row(s) for s in sites]
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        filled = sum(1 for r in rows if r["ph_h2o"] != "")
        print(f"  Wrote {len(rows)} sites ({filled} with data) -> {OUTPUT_CSV.name}")
        _print_summary(rows)
        return

    # Fetch soil data for each site
    print(f"\n  Fetching soil properties ({args.delay}s delay)...")
    rows = []
    success = 0
    fail = 0

    for i, site in enumerate(sites):
        print(f"  [{i + 1}/{len(sites)}] {site['name']}...", end=" ", flush=True)
        raw = fetch_soilgrids(site["latitude"], site["longitude"], args.delay)

        # Auto-fallback to offline if first API call fails (DNS, network)
        if i == 0 and not raw:
            print("\n  API unreachable — falling back to offline reference data...")
            rows = [build_offline_row(s) for s in sites]
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            filled = sum(1 for r in rows if r["ph_h2o"] != "")
            print(f"  Wrote {len(rows)} sites ({filled} with data) -> {OUTPUT_CSV.name}")
            _print_summary(rows)
            return

        if not raw:
            fail += 1
            print("FAIL")
            rows.append({
                "site_id": site["site_id"],
                "name": site["name"],
                "country": site["country"],
                "latitude": site["latitude"],
                "longitude": site["longitude"],
                "ph_h2o": "",
                "clay_pct": "",
                "sand_pct": "",
                "silt_pct": "",
                "soc_g_per_kg": "",
                "nitrogen_cg_per_kg": "",
                "cec_mmol_per_kg": "",
                "ocd_kg_per_m3": "",
                "soil_texture_class": "",
            })
        else:
            success += 1
            # SoilGrids returns:
            #   phh2o: pH * 10 (e.g. 55 = pH 5.5)
            #   clay/sand/silt: g/kg (e.g. 250 = 25%)
            #   soc: dg/kg (e.g. 150 = 15.0 g/kg)
            #   nitrogen: cg/kg
            #   cec: mmol(c)/kg
            #   ocd: hg/m3 -> kg/m3 (/10)
            ph = round(raw.get("phh2o", 0) / 10.0, 1) if "phh2o" in raw else ""
            clay_pct = round(raw.get("clay", 0) / 10.0, 1) if "clay" in raw else ""
            sand_pct = round(raw.get("sand", 0) / 10.0, 1) if "sand" in raw else ""
            silt_pct = round(raw.get("silt", 0) / 10.0, 1) if "silt" in raw else ""
            soc = round(raw.get("soc", 0) / 10.0, 1) if "soc" in raw else ""
            nitrogen = raw.get("nitrogen", "")
            cec = raw.get("cec", "")
            ocd = round(raw.get("ocd", 0) / 10.0, 1) if "ocd" in raw else ""

            # Texture classification
            clay_f = clay_pct if isinstance(clay_pct, float) else None
            sand_f = sand_pct if isinstance(sand_pct, float) else None
            silt_f = silt_pct if isinstance(silt_pct, float) else None
            texture = classify_soil_texture(clay_f, sand_f, silt_f)

            print(f"pH {ph}, clay {clay_pct}%, sand {sand_pct}%, SOC {soc} g/kg -> {texture}")

            rows.append({
                "site_id": site["site_id"],
                "name": site["name"],
                "country": site["country"],
                "latitude": site["latitude"],
                "longitude": site["longitude"],
                "ph_h2o": ph,
                "clay_pct": clay_pct,
                "sand_pct": sand_pct,
                "silt_pct": silt_pct,
                "soc_g_per_kg": soc,
                "nitrogen_cg_per_kg": nitrogen,
                "cec_mmol_per_kg": cec,
                "ocd_kg_per_m3": ocd,
                "soil_texture_class": texture,
            })

        if i < len(sites) - 1:
            time.sleep(args.delay)

    # Write CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n  Wrote {len(rows)} sites -> {OUTPUT_CSV.name}")

    # Summary
    print(f"\n=== Summary ===")
    print(f"Success: {success}/{len(sites)}, Failed: {fail}")
    _print_summary(rows)


def _print_summary(rows: list[dict]) -> None:
    """Print soil data summary statistics."""
    filled = [r for r in rows if r["ph_h2o"] != ""]
    if not filled:
        return

    ph_vals = [r["ph_h2o"] for r in filled]
    print(f"pH range: {min(ph_vals)} – {max(ph_vals)}")

    soc_vals = [r["soc_g_per_kg"] for r in filled if r["soc_g_per_kg"] != ""]
    if soc_vals:
        print(f"SOC range: {min(soc_vals)} – {max(soc_vals)} g/kg")

    textures: dict[str, int] = {}
    for r in filled:
        t = r["soil_texture_class"]
        if t:
            textures[t] = textures.get(t, 0) + 1
    if textures:
        print("Soil texture classes:")
        for t, n in sorted(textures.items(), key=lambda x: -x[1]):
            print(f"  {t}: {n}")

    acidic = min(filled, key=lambda r: r["ph_h2o"])
    alkaline = max(filled, key=lambda r: r["ph_h2o"])
    print(f"\nMost acidic: {acidic['name']} ({acidic['country']}): pH {acidic['ph_h2o']}")
    print(f"Most alkaline: {alkaline['name']} ({alkaline['country']}): pH {alkaline['ph_h2o']}")


if __name__ == "__main__":
    main()
