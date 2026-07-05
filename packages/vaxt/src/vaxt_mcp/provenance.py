"""Provenance enrichment — the grounding layer, owned by the data tier.

VaxtClient returns bare row dicts (its `source` column is real-world data lineage,
not a citation key). Grounding needs a machine-checkable `(table, key)` per row, so
this module wraps each tool result into records tagged with their table and key
value. `enrich()` is the single place that decides provenance; `resolve_citation()`
is the single place that checks it against the warehouse.

This lives in `vaxt_mcp` (the data/MCP tier), not in the agent, so that EVERY
consumer — the MCP server's tools, the agent, the eval grader, the web `/citation`
endpoint, and the plugin's Stop hook — shares one provenance definition and can
never disagree about what a citation means. The server enriches its tool results
here, so a plain MCP client sees the same `(table, key)` the agent does.

Citation resolution is defined as "**>= 1 row** in `table` where the key column
matches (case-insensitively)". Exactly-one would be nicer, but the real data has a
few duplicate natural keys (`varieties` "Aurora"; two `eppo_code`s; `markers` has
no unique key), so >= 1 is the honest invariant. It still makes a fabricated key —
the thing that matters — a hard, deterministic failure.
"""

import duckdb

# Designated key column per table. The column must be present in the output of
# every tool that reads the table (verified against client.py's SELECTs).
TABLE_KEY: dict[str, str] = {
    "varieties": "variety",
    "variety_growing_enrichment": "variety",
    "disease_resistance": "variety_or_gene",
    "markers": "marker",
    "growing_season": "station_name",
    "climate_zones": "zone",
    "photoperiod_zones": "site_id",
    "soilgrids": "site_id",
    "field_trial_sites": "site_id",
    "planting_calendars": "calendar_id",
    "graingenes_qtl": "qtl_name",
    "breeding_programs": "program_id",
    "sourdough_starters": "starter_id",
    "seed_sources": "source_id",
    "distillery_profiles": "distillery_id",
    "rootstock_compatibility": "rootstock",
    "crop_wild_relatives": "species",
    "community_grain_projects": "project_id",
    "eppo_pathogens": "eppo_code",
    "grin_accessions": "pi_number",
}

# Tools whose result is a flat list[dict] from a single table (client method -> table).
_FLAT: dict[str, str] = {
    "search_varieties": "varieties",
    "compare_varieties": "varieties",
    "get_growing_season": "growing_season",
    "get_planting_calendar": "planting_calendars",
    "search_markers": "markers",
    "search_qtl": "graingenes_qtl",
    "search_sourdough": "sourdough_starters",
    "search_seed_sources": "seed_sources",
    "get_disease_resistance": "disease_resistance",
    "get_distillery_grain_sources": "distillery_profiles",
    "get_rootstock_compatibility": "rootstock_compatibility",
    "get_crop_wild_relatives": "crop_wild_relatives",
    "search_community_projects": "community_grain_projects",
    "search_eppo_pathogens": "eppo_pathogens",
}

# Composite sub-keys that are nested inside get_variety / cross_reference results,
# mapped to the table each one comes from.
_NESTED_TABLE = {
    "growing_data": "variety_growing_enrichment",
    "disease_resistance": "disease_resistance",
    "cold_tolerance_markers": "markers",
    "grin_accessions": "grin_accessions",
    "seed_sources": "seed_sources",
}
# grin_accessions has no unique key in TABLE_KEY; cite it by pi_number when present.
TABLE_KEY.setdefault("grin_accessions", "pi_number")


def _record(table: str, row: dict) -> dict:
    """Tag one row dict with its (table, key)."""
    keycol = TABLE_KEY.get(table)
    key = None
    if keycol and isinstance(row, dict) and row.get(keycol) is not None:
        key = str(row[keycol])
    return {"table": table, "key": key, "key_column": keycol, "fields": row}


def _records_from_list(table: str, rows) -> list[dict]:
    return [_record(table, r) for r in rows if isinstance(r, dict)]


def enrich(method: str, raw) -> list[dict]:
    """Turn a VaxtClient method's raw result into a flat list of tagged records.

    The agent sees one uniform record shape regardless of which tool ran, so it can
    cite `(table, key)` for any fact it uses.
    """
    if raw is None:
        return []

    if method in _FLAT:
        return _records_from_list(_FLAT[method], raw if isinstance(raw, list) else [])

    if method == "get_breeding_program":
        return _records_from_list("breeding_programs", [raw] if isinstance(raw, dict) else [])

    if method == "get_variety":
        return _variety_records(raw)

    if method == "cross_reference":
        return _cross_reference_records(raw)

    if method == "match_varieties":
        if not isinstance(raw, dict):
            return []
        recs = _records_from_list("varieties", raw.get("varieties", []))
        recs += _records_from_list("planting_calendars", raw.get("planting_calendars", []))
        return recs

    if method == "get_climate_profile":
        if not isinstance(raw, dict):
            return []
        recs = _records_from_list("climate_zones", raw.get("climate_zones", []))
        recs += _records_from_list("photoperiod_zones", raw.get("photoperiod_zones", []))
        recs += _records_from_list("soilgrids", raw.get("soil_profiles", []))
        recs += _records_from_list("field_trial_sites", raw.get("nearest_trial_sites", []))
        return recs

    if method == "get_journal_entries":
        # grower_journal is dynamic and usually empty; tag rows if any exist.
        return [
            {"table": "grower_journal", "key": None, "key_column": None, "fields": r}
            for r in (raw if isinstance(raw, list) else [])
            if isinstance(r, dict)
        ]

    # health_check and anything else: no citable records.
    return []


def _variety_records(raw: dict) -> list[dict]:
    if not isinstance(raw, dict):
        return []
    nested_keys = set(_NESTED_TABLE)
    base = {k: v for k, v in raw.items() if k not in nested_keys}
    recs = [_record("varieties", base)]
    if isinstance(raw.get("growing_data"), dict):
        recs.append(_record("variety_growing_enrichment", raw["growing_data"]))
    recs += _records_from_list("disease_resistance", raw.get("disease_resistance", []))
    recs += _records_from_list("markers", raw.get("cold_tolerance_markers", []))
    return recs


def _cross_reference_records(raw: dict) -> list[dict]:
    if not isinstance(raw, dict):
        return []
    recs: list[dict] = []
    if isinstance(raw.get("profile"), dict):
        recs.append(_record("varieties", raw["profile"]))
    if isinstance(raw.get("growing_data"), dict):
        recs.append(_record("variety_growing_enrichment", raw["growing_data"]))
    recs += _records_from_list("disease_resistance", raw.get("disease_resistance", []))
    recs += _records_from_list("markers", raw.get("cold_tolerance_markers", []))
    recs += _records_from_list("grin_accessions", raw.get("grin_accessions", []))
    recs += _records_from_list("seed_sources", raw.get("seed_sources", []))
    return recs


def resolve_citation(con: duckdb.DuckDBPyConnection, table: str, key: str) -> bool:
    """True iff >= 1 row in `table` has the key column == key (case-insensitive).

    Unknown table or key column -> False (a citation naming a table we don't track
    cannot be trusted). Uses a read-only connection supplied by the caller.
    """
    keycol = TABLE_KEY.get(table)
    if keycol is None:
        return False
    sql = (
        f'SELECT 1 FROM "{table}" '  # table/keycol are from our own registry, never user input
        f'WHERE LOWER(CAST("{keycol}" AS VARCHAR)) = LOWER(?) LIMIT 1'
    )
    try:
        return con.execute(sql, [str(key)]).fetchone() is not None
    except duckdb.Error:
        return False


def fetch_citation_row(con: duckdb.DuckDBPyConnection, table: str, key: str) -> dict | None:
    """The cited row itself, for display — same registry and match rule as
    resolve_citation, so the two can never disagree about what a citation means.

    Returns *a* matching row (LIMIT 1): the grounding invariant is >= 1 row, and
    a few natural keys are legitimately non-unique. Unknown table, unknown key
    column, or no match -> None. Uses a read-only connection from the caller.
    """
    keycol = TABLE_KEY.get(table)
    if keycol is None:
        return None
    sql = (
        f'SELECT * FROM "{table}" '  # table/keycol are from our own registry, never user input
        f'WHERE LOWER(CAST("{keycol}" AS VARCHAR)) = LOWER(?) LIMIT 1'
    )
    try:
        cur = con.execute(sql, [str(key)])
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))
    except duckdb.Error:
        return None
