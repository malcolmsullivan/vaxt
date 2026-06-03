#!/usr/bin/env python3
"""Validate cold_tolerance_markers.csv. Run from workspace root."""

import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MARKERS_CSV = SCRIPT_DIR / "cold_tolerance_markers.csv"

REQUIRED_COLUMNS = [
    "species",
    "locus",
    "chromosome",
    "gene",
    "marker",
    "marker_type",
    "frost_tolerance_pct",
    "notes",
    "source",
]


def main() -> None:
    if not MARKERS_CSV.exists():
        print(f"Missing: {MARKERS_CSV}")
        return
    with open(MARKERS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        if headers != REQUIRED_COLUMNS:
            print(f"Expected columns: {REQUIRED_COLUMNS}")
            print(f"Got: {headers}")
            return
        rows = list(reader)
    print(f"OK: {len(rows)} markers in {MARKERS_CSV.name}")
    species = set(r["species"] for r in rows if r.get("species"))
    print(f"Species: {', '.join(sorted(species))}")


if __name__ == "__main__":
    main()
