#!/usr/bin/env python3
"""ETL: Pull winterhardiness/cold tolerance phenotype data from T3 Triticeae Toolbox.

Uses BrAPI v2 endpoints across wheat, barley, and oat T3 instances.

Outputs:
    data/datasets/heritage-grain/t3_observations.csv
    data/datasets/heritage-grain/t3_germplasm.csv

Usage:
    python3 scripts/vaxt/etl_t3_brapi.py                    # Full run
    python3 scripts/vaxt/etl_t3_brapi.py --dry-run           # List variables/trials only
    python3 scripts/vaxt/etl_t3_brapi.py --crop wheat        # Single crop
    python3 scripts/vaxt/etl_t3_brapi.py --max-trials 10     # Limit trials per variable
    python3 scripts/vaxt/etl_t3_brapi.py --delay 1.5         # Slower rate limit

T3 instances:
    wheat.triticeaetoolbox.org  — 11K+ observation variables
    barley.triticeaetoolbox.org — 202 observation variables
    oat.triticeaetoolbox.org    — 288 observation variables

BrAPI endpoints used:
    GET /brapi/v2/variables/{id}              — variable metadata
    GET /brapi/v2/observations?studyDbId={id} — observations per trial
    GET /brapi/v2/studies/{id}                — study metadata
    GET /cvterm/{id}/datatables/direct_trials  — trial list (T3 internal)
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_DIR = WORKSPACE / "data" / "datasets" / "heritage-grain"
OBS_CSV = OUTPUT_DIR / "t3_observations.csv"
GERM_CSV = OUTPUT_DIR / "t3_germplasm.csv"

USER_AGENT = "VAV-OS/1.0 (malcolm@vav-os.com) heritage-grain-ETL"

# T3 instances and their winterhardiness variable IDs
# Found via /brapi/v2/variables searching for winter/frost/freeze keywords
INSTANCES = {
    "wheat": {
        "base": "https://wheat.triticeaetoolbox.org",
        "variables": {
            83993: "Winter kill damage - %",
            84233: "Winter kill damage - 0-9 DAMAGE scale",
            90796: "Spring regrowth - 1-10 scale",
            84170: "Frost damage - %",
            84889: "Frost damage - 0-3 injury scale",
        },
    },
    "barley": {
        "base": "https://barley.triticeaetoolbox.org",
        "variables": {
            77385: "Winter hardiness - %",
        },
    },
    "oat": {
        "base": "https://oat.triticeaetoolbox.org",
        "variables": {
            77312: "Winter survival - percent",
            77207: "Winter stress severity - 0-9 Rating",
            77220: "Freeze damage severity - 0-9 Rating",
        },
    },
}

OBS_COLUMNS = [
    "crop",
    "observation_id",
    "germplasm_name",
    "germplasm_db_id",
    "variable_name",
    "variable_db_id",
    "value",
    "study_db_id",
    "study_name",
    "season",
    "location",
    "collector",
    "observation_unit_name",
]

GERM_COLUMNS = [
    "crop",
    "germplasm_db_id",
    "germplasm_name",
    "genus",
    "species",
    "subtaxa",
    "pedigree",
    "institute_code",
    "accession_number",
    "country_of_origin",
]


def fetch_json(url: str, delay: float = 1.0, retries: int = 3) -> dict | list | None:
    """Fetch URL and parse JSON response. Retries on connection errors."""
    for attempt in range(retries):
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urlopen(req, timeout=60) as resp:
                content_type = resp.headers.get("Content-Type", "")
                body = resp.read().decode("utf-8", errors="replace")
                if "html" in content_type and not body.strip().startswith("{"):
                    return None
                return json.loads(body)
        except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            if attempt < retries - 1:
                wait = delay * (2 ** (attempt + 1))  # exponential backoff
                print(f"  RETRY {attempt + 1}/{retries}: {exc} (waiting {wait:.0f}s)", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"  WARN: {url} -> {exc}", file=sys.stderr)
                return None
        finally:
            if attempt == 0 or attempt == retries - 1:
                time.sleep(delay)


def get_trials_for_variable(base_url: str, var_id: int, delay: float) -> list[dict]:
    """Get trial list for a variable using T3 internal endpoint."""
    url = f"{base_url}/cvterm/{var_id}/datatables/direct_trials"
    data = fetch_json(url, delay)
    if not data:
        return []

    # T3 returns {"data": [["<a href='/breeders/trial/ID'>NAME</a>", desc], ...]}
    trials = []
    rows = data.get("data", [])
    for row in rows:
        if not row:
            continue
        cell = str(row[0])
        # Extract numeric ID and name from HTML link
        m = re.search(r'href="[^"]*?/(\d+)"[^>]*>([^<]+)<', cell)
        if m:
            trials.append({"id": m.group(1), "name": m.group(2).strip()})
        else:
            # Fallback: plain text
            clean = re.sub(r"<[^>]+>", "", cell).strip()
            if clean:
                trials.append({"id": clean, "name": clean})
    return trials


def get_observations_for_study(
    base_url: str, study_id: str, delay: float
) -> list[dict]:
    """Fetch all observations for a study via BrAPI v2, handling pagination."""
    all_obs = []
    page = 0
    page_size = 1000

    while True:
        url = (
            f"{base_url}/brapi/v2/observations"
            f"?studyDbId={study_id}&pageSize={page_size}&page={page}"
        )
        data = fetch_json(url, delay)
        if not data:
            break

        result = data.get("result", {})
        obs_list = result.get("data", [])
        if not obs_list:
            break

        all_obs.extend(obs_list)

        # Check pagination
        metadata = data.get("metadata", {})
        pagination = metadata.get("pagination", {})
        total_pages = pagination.get("totalPages", 1)
        if page + 1 >= total_pages:
            break
        page += 1

    return all_obs


def get_study_metadata(base_url: str, study_id: str, delay: float) -> dict:
    """Fetch study metadata (location, season, trial program)."""
    url = f"{base_url}/brapi/v2/studies/{study_id}"
    data = fetch_json(url, delay)
    if not data:
        return {}
    return data.get("result", {})


def get_germplasm_detail(base_url: str, germ_id: str, delay: float) -> dict:
    """Fetch germplasm details via BrAPI v2."""
    url = f"{base_url}/brapi/v2/germplasm/{germ_id}"
    data = fetch_json(url, delay)
    if not data:
        return {}
    return data.get("result", {})


def main():
    parser = argparse.ArgumentParser(
        description="ETL: T3 Triticeae Toolbox winterhardiness data"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List variables/trials without fetching"
    )
    parser.add_argument(
        "--crop",
        choices=["wheat", "barley", "oat"],
        help="Single crop (default: all)",
    )
    parser.add_argument(
        "--max-trials",
        type=int,
        default=0,
        help="Max trials per variable (0 = all)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between requests (default: 1.0)",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    crops = [args.crop] if args.crop else list(INSTANCES.keys())

    # Phase 1: Discover trials for each variable
    print("=== Phase 1: Discovering trials ===")
    plan: list[dict] = []  # [{crop, var_id, var_name, trial_id, trial_name}]

    for crop in crops:
        inst = INSTANCES[crop]
        base = inst["base"]
        print(f"\n{crop.upper()} ({base})")

        for var_id, var_name in inst["variables"].items():
            trials = get_trials_for_variable(base, var_id, args.delay)
            print(f"  {var_name} (id={var_id}): {len(trials)} trials")

            if args.max_trials > 0:
                trials = trials[: args.max_trials]

            for t in trials:
                plan.append(
                    {
                        "crop": crop,
                        "var_id": var_id,
                        "var_name": var_name,
                        "trial_id": t["id"],
                        "trial_name": t["name"],
                        "base": base,
                    }
                )

    print(f"\nTotal: {len(plan)} trial-variable combinations to fetch")

    if args.dry_run:
        for p in plan[:20]:
            print(f"  {p['crop']}: {p['var_name']} / {p['trial_name']}")
        if len(plan) > 20:
            print(f"  ... and {len(plan) - 20} more")
        print(f"\nDry run — pass without --dry-run to fetch observations.")
        return

    # Phase 2: Fetch observations per trial
    print("\n=== Phase 2: Fetching observations ===")
    all_observations: list[dict] = []
    germplasm_ids: dict[tuple[str, str], str] = {}  # (crop, db_id) -> name
    study_cache: dict[tuple[str, str], dict] = {}  # (base, study_id) -> metadata

    for i, p in enumerate(plan, 1):
        crop = p["crop"]
        base = p["base"]
        study_id = p["trial_id"]
        var_name = p["var_name"]
        var_id = p["var_id"]

        # Get study metadata (cached)
        cache_key = (base, study_id)
        if cache_key not in study_cache:
            study_meta = get_study_metadata(base, study_id, args.delay)
            study_cache[cache_key] = study_meta
        else:
            study_meta = study_cache[cache_key]

        location = study_meta.get("locationName", "")
        study_name = study_meta.get("studyName", p["trial_name"])
        seasons = study_meta.get("seasons", [])
        season = seasons[0] if seasons else ""

        # Get observations
        obs_list = get_observations_for_study(base, study_id, args.delay)

        # Filter to our target variable
        matched = [
            o for o in obs_list if str(o.get("observationVariableDbId")) == str(var_id)
        ]

        if matched:
            for o in matched:
                germ_name = o.get("germplasmName", "")
                germ_id = str(o.get("germplasmDbId", ""))
                if germ_id and germ_name:
                    germplasm_ids[(crop, germ_id)] = germ_name

                all_observations.append(
                    {
                        "crop": crop,
                        "observation_id": o.get("observationDbId", ""),
                        "germplasm_name": germ_name,
                        "germplasm_db_id": germ_id,
                        "variable_name": var_name,
                        "variable_db_id": str(var_id),
                        "value": o.get("value", ""),
                        "study_db_id": study_id,
                        "study_name": study_name,
                        "season": season,
                        "location": location,
                        "collector": o.get("collector", ""),
                        "observation_unit_name": o.get("observationUnitName", ""),
                    }
                )

        progress = f"[{i}/{len(plan)}]"
        print(f"  {progress} {crop}/{study_name}: {len(matched)} obs ({len(all_observations)} total)")

    if not all_observations:
        print("No observations found.")
        sys.exit(1)

    # Phase 3: Write observations CSV
    print(f"\n=== Phase 3: Writing CSVs ===")
    with open(OBS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OBS_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_observations)
    print(f"Observations: {len(all_observations)} rows -> {OBS_CSV.name}")

    # Phase 4: Fetch germplasm details (sample — top 200 unique germplasm)
    print(f"\n=== Phase 4: Fetching germplasm details ===")
    germ_sample = list(germplasm_ids.items())[:200]
    germ_rows: list[dict] = []

    for j, ((crop, germ_id), germ_name) in enumerate(germ_sample, 1):
        base = INSTANCES[crop]["base"]
        detail = get_germplasm_detail(base, germ_id, args.delay)
        if detail:
            germ_rows.append(
                {
                    "crop": crop,
                    "germplasm_db_id": germ_id,
                    "germplasm_name": detail.get("germplasmName", germ_name),
                    "genus": detail.get("genus", ""),
                    "species": detail.get("species", ""),
                    "subtaxa": detail.get("subtaxa", ""),
                    "pedigree": detail.get("pedigree", ""),
                    "institute_code": detail.get("instituteCode", ""),
                    "accession_number": detail.get("accessionNumber", ""),
                    "country_of_origin": detail.get("countryOfOriginCode", ""),
                }
            )
        if j % 50 == 0:
            print(f"  [{j}/{len(germ_sample)}] germplasm fetched")

    with open(GERM_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=GERM_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(germ_rows)
    print(f"Germplasm: {len(germ_rows)} rows -> {GERM_CSV.name}")

    # Summary
    print(f"\n=== Summary ===")
    for crop in crops:
        crop_obs = [o for o in all_observations if o["crop"] == crop]
        crop_germ = [g for g in germ_rows if g["crop"] == crop]
        variables = sorted(set(o["variable_name"] for o in crop_obs))
        studies = sorted(set(o["study_db_id"] for o in crop_obs))
        print(f"{crop.upper()}: {len(crop_obs)} obs, {len(studies)} studies, {len(crop_germ)} germplasm")
        for v in variables:
            v_count = sum(1 for o in crop_obs if o["variable_name"] == v)
            print(f"  {v}: {v_count}")


if __name__ == "__main__":
    main()
