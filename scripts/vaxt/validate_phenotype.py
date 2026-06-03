#!/usr/bin/env python3
"""Validate phenotype_template.csv against phenotype_schema.json."""

import csv
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PHENO_CSV = SCRIPT_DIR / "phenotype_template.csv"
SCHEMA_JSON = SCRIPT_DIR / "phenotype_schema.json"

# Fields that must be non-empty on every row
REQUIRED_FIELDS: list[str] = []  # populated from schema

# Enum fields: column -> allowed values
ENUM_FIELDS: dict[str, list[str]] = {}

# Numeric fields: column -> (min, max) or None
NUMERIC_FIELDS: dict[str, tuple[float | None, float | None]] = {}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEASON_RE = re.compile(r"^\d{4}(-\d{4})?$")


def load_schema() -> dict:
    with open(SCHEMA_JSON, encoding="utf-8") as f:
        return json.load(f)


def build_validators(schema: dict) -> None:
    global REQUIRED_FIELDS
    REQUIRED_FIELDS = schema.get("required", [])

    props = schema.get("properties", {})
    for col, spec in props.items():
        if "enum" in spec:
            ENUM_FIELDS[col] = spec["enum"]
        if spec.get("type") in ("number", "integer"):
            lo = spec.get("minimum")
            hi = spec.get("maximum")
            NUMERIC_FIELDS[col] = (lo, hi)


def validate_row(row: dict, idx: int) -> list[str]:
    errors: list[str] = []

    def _get(field: str) -> str:
        v = row.get(field)
        return v.strip() if v else ""

    # Required fields
    for field in REQUIRED_FIELDS:
        if not _get(field):
            errors.append(f"Row {idx}: required field '{field}' is empty")

    # Enum fields
    for field, allowed in ENUM_FIELDS.items():
        val = _get(field)
        if val and val not in allowed:
            errors.append(f"Row {idx}: '{field}' value '{val}' not in {allowed}")

    # Numeric fields
    for field, (lo, hi) in NUMERIC_FIELDS.items():
        val = _get(field)
        if not val:
            continue
        try:
            num = float(val)
        except ValueError:
            errors.append(f"Row {idx}: '{field}' value '{val}' is not numeric")
            continue
        if lo is not None and num < lo:
            errors.append(f"Row {idx}: '{field}' value {num} < min {lo}")
        if hi is not None and num > hi:
            errors.append(f"Row {idx}: '{field}' value {num} > max {hi}")

    # Date fields
    for field in ("observation_date", "autumn_stand_date", "spring_stand_date"):
        val = _get(field)
        if val and not DATE_RE.match(val):
            errors.append(f"Row {idx}: '{field}' value '{val}' is not YYYY-MM-DD")

    # Season field
    val = _get("season")
    if val and not SEASON_RE.match(val):
        errors.append(f"Row {idx}: 'season' value '{val}' does not match YYYY or YYYY-YYYY")

    return errors


def main() -> None:
    if not PHENO_CSV.exists():
        print(f"Missing: {PHENO_CSV}")
        sys.exit(1)
    if not SCHEMA_JSON.exists():
        print(f"Missing: {SCHEMA_JSON}")
        sys.exit(1)

    schema = load_schema()
    build_validators(schema)

    expected_columns = list(schema["properties"].keys())

    with open(PHENO_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        if headers != expected_columns:
            missing = set(expected_columns) - set(headers)
            extra = set(headers) - set(expected_columns)
            if missing:
                print(f"Missing columns: {sorted(missing)}")
            if extra:
                print(f"Extra columns: {sorted(extra)}")
            if not missing and not extra:
                print("Column order mismatch:")
                print(f"  Expected: {expected_columns[:5]}...")
                print(f"  Got:      {list(headers)[:5]}...")
            sys.exit(1)

        rows = list(reader)

    all_errors: list[str] = []
    for i, row in enumerate(rows, start=2):  # CSV row 2 = first data row
        all_errors.extend(validate_row(row, i))

    if all_errors:
        print(f"FAIL: {len(all_errors)} error(s) in {PHENO_CSV.name}")
        for err in all_errors[:20]:
            print(f"  {err}")
        if len(all_errors) > 20:
            print(f"  ... and {len(all_errors) - 20} more")
        sys.exit(1)

    print(f"OK: {len(rows)} records in {PHENO_CSV.name}")
    crop_types = sorted(set(r["crop_type"] for r in rows if r.get("crop_type")))
    print(f"Crop types: {', '.join(crop_types)}")
    species = sorted(set(r["species"] for r in rows if r.get("species")))
    print(f"Species: {', '.join(species)}")
    trials = sorted(set(r["trial_id"] for r in rows if r.get("trial_id")))
    print(f"Trials: {len(trials)} ({', '.join(trials[:5])})")

    # Trait coverage summary
    trait_groups = {
        "LT50": ["lt50_su_c", "lt50_el_c"],
        "Ice encasement": ["ice_encasement_ld50_days", "ice_encasement_survival_pct"],
        "Snow mold": ["snow_mold_field_score", "snow_mold_ari", "snow_mold_pct_damage"],
        "Winter survival": ["winter_survival_pct", "winter_survival_score"],
        "Crown regrowth": ["crown_regrowth_score", "crown_regrowth_pct"],
        "DTA (fruit)": ["dta_lte_c", "dta_hte_c"],
        "Tissue browning": ["tissue_browning_score"],
    }
    print("Trait coverage:")
    for group, cols in trait_groups.items():
        count = sum(1 for r in rows if any(r.get(c, "").strip() for c in cols))
        print(f"  {group}: {count}/{len(rows)} records")


if __name__ == "__main__":
    main()
