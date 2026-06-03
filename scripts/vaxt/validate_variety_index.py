#!/usr/bin/env python3
"""Validate nordic_variety_trait_index.csv. Run from workspace root."""

import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INDEX_CSV = SCRIPT_DIR / "nordic_variety_trait_index.csv"

REQUIRED_COLUMNS = [
    "variety",
    "crop",
    "program",
    "country",
    "traits",
    "cold_tolerance_notes",
    "usda_zone",
    "source",
]


def main() -> None:
    if not INDEX_CSV.exists():
        print(f"Missing: {INDEX_CSV}")
        return
    with open(INDEX_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        if headers != REQUIRED_COLUMNS:
            print(f"Expected columns: {REQUIRED_COLUMNS}")
            print(f"Got: {headers}")
            return
        rows = list(reader)
    print(f"OK: {len(rows)} varieties in {INDEX_CSV.name}")
    crops = set(r["crop"] for r in rows if r.get("crop"))
    print(f"Crops: {', '.join(sorted(crops))}")
    programs = set(r["program"] for r in rows if r.get("program"))
    print(f"Programs: {len(programs)} ({', '.join(sorted(programs)[:5])}...)")


if __name__ == "__main__":
    main()
