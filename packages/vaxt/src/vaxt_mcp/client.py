"""VAXT DuckDB client — read-only queries over the heritage grain database."""

import importlib.resources
import json
import logging
import os
from pathlib import Path

import duckdb

log = logging.getLogger("vaxt_mcp.client")

_DEFAULT_DB_PATH = "data/datasets/heritage-grain/heritage-grain.duckdb"
# Where the build hook stages the DB inside the installed package (see hatch_build.py).
_BUNDLED_REL = ("data", "heritage-grain.duckdb")


def _require_db() -> bool:
    """Whether the fail-loud warehouse gate is active (VAXT_REQUIRE_DB truthy)."""
    return os.environ.get("VAXT_REQUIRE_DB", "").strip().lower() in ("1", "true", "yes", "on")


def _bundled_db_path() -> str | None:
    """Absolute path to the DB bundled inside the installed wheel, or None.

    Present only in a real (non-editable) wheel install where hatch_build.py staged
    it; absent for editable/source checkouts (which resolve via env/workspace/cwd).
    """
    try:
        p = importlib.resources.files("vaxt_mcp").joinpath(*_BUNDLED_REL)
        fs = os.fspath(p)  # real on-disk path for a normally-installed (unzipped) wheel
    except (ModuleNotFoundError, FileNotFoundError, TypeError, NotADirectoryError):
        return None
    return fs if os.path.exists(fs) else None


def _resolve_db(require: bool | None = None, bundled: str | None = None) -> tuple[str, str]:
    """Resolve the DuckDB path and its source.

    Order: ``VAXT_DUCKDB_PATH`` env -> ``$WORKSPACE_ROOT``-relative -> cwd-relative
    -> DB bundled in the package. Returns ``(path, source)`` where source is one of
    ``env`` | ``workspace`` | ``cwd`` | ``bundled`` | ``missing``.

    Fail-loud (the repo's warehouse-guard ethos): the bundled copy is a frozen
    snapshot baked into the wheel. When the gate is active (``VAXT_REQUIRE_DB``),
    the bundled fallback is *refused* so a stale wheel can never silently answer in
    place of a missing external warehouse. Falling back to bundled always logs a
    WARNING naming the source. ``require``/``bundled`` are injectable for testing.
    """
    if require is None:
        require = _require_db()

    path = os.environ.get("VAXT_DUCKDB_PATH", "")
    if path:
        return path, "env"

    workspace = os.environ.get("WORKSPACE_ROOT", "/workspace")
    candidate = Path(workspace) / _DEFAULT_DB_PATH
    if candidate.exists():
        return str(candidate), "workspace"

    if Path(_DEFAULT_DB_PATH).exists():
        return _DEFAULT_DB_PATH, "cwd"

    if bundled is None:
        bundled = _bundled_db_path()
    if bundled is not None:
        if require:
            raise FileNotFoundError(
                "VAXT_REQUIRE_DB is set but no external warehouse was found "
                "(VAXT_DUCKDB_PATH / WORKSPACE_ROOT / cwd). Refusing the DB bundled "
                "in the vaxt-mcp package so a stale wheel cannot silently answer. "
                "Set VAXT_DUCKDB_PATH to a live warehouse, or unset VAXT_REQUIRE_DB "
                "to accept the frozen bundled snapshot."
            )
        log.warning(
            "vaxt: no external warehouse found; using the DB bundled in the "
            "vaxt-mcp package (%s). This is a FROZEN snapshot — set VAXT_DUCKDB_PATH "
            "to query a live warehouse.",
            bundled,
        )
        return bundled, "bundled"

    # Nothing resolved and nothing bundled: return the (nonexistent) workspace
    # candidate so duckdb.connect fails loud at open, exactly as before.
    return str(candidate), "missing"


def _resolve_db_path() -> str:
    """Back-compat shim: the resolved path only (see ``_resolve_db`` for source)."""
    return _resolve_db()[0]


def _fingerprint_beside(db_path: str) -> dict | None:
    """The WAREHOUSE.json snapshot fingerprint next to a bundled DB, if present."""
    fp = Path(db_path).with_name("WAREHOUSE.json")
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
    return None


class VaxtClient:
    """Read-only DuckDB client for VAXT heritage grain data."""

    def __init__(self, db_path: str | None = None):
        if db_path:
            self._db_path, self._db_source = db_path, "explicit"
        else:
            self._db_path, self._db_source = _resolve_db()
        self._conn: duckdb.DuckDBPyConnection | None = None

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(self._db_path, read_only=True)
        return self._conn

    def _query(self, sql: str, params: list | None = None) -> list[dict]:
        """Execute a parameterized query and return list of dicts."""
        conn = self._get_conn()
        if params:
            result = conn.execute(sql, params)
        else:
            result = conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def _query_one(self, sql: str, params: list | None = None) -> dict | None:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Health ---

    def health_check(self) -> dict:
        """Check DuckDB status and return table counts."""
        try:
            conn = self._get_conn()
            tables = conn.execute("SHOW TABLES").fetchall()
            counts = {}
            for (name,) in tables:
                count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                counts[name] = count
            result = {
                "status": "ok",
                "db_path": self._db_path,
                "db_source": self._db_source,
                "tables": len(counts),
                "table_counts": counts,
                "total_rows": sum(counts.values()),
            }
            fingerprint = _fingerprint_beside(self._db_path)
            if fingerprint is not None:
                # Present for a bundled wheel: identifies the frozen snapshot so a
                # stale wheel is self-evident instead of silent.
                result["warehouse_fingerprint"] = fingerprint
            return result
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "db_path": self._db_path,
                "db_source": self._db_source,
            }

    # --- Variety Intelligence ---

    def search_varieties(self, crop: str = "", zone: str = "",
                         country: str = "", traits: list[str] | None = None,
                         limit: int = 25) -> list[dict]:
        """Search varieties by crop, zone, country, and/or traits."""
        conditions = []
        params = []

        if crop:
            conditions.append("LOWER(crop) LIKE '%' || ? || '%'")
            params.append(crop.lower())
        if zone:
            conditions.append("usda_zone = ?")
            params.append(zone)
        if country:
            conditions.append("LOWER(country) LIKE '%' || ? || '%'")
            params.append(country.lower())
        if traits:
            for trait in traits:
                conditions.append("LOWER(traits) LIKE '%' || ? || '%'")
                params.append(trait.lower())

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT variety, crop, country, usda_zone, traits,
                   cold_tolerance_notes, source
            FROM varieties
            WHERE {where}
            ORDER BY variety
            LIMIT ?
        """
        params.append(limit)
        return self._query(sql, params)

    def get_variety(self, name: str) -> dict | None:
        """Get full variety profile with growing data, disease resistance, and markers."""
        variety = self._query_one(
            "SELECT * FROM varieties WHERE LOWER(variety) = LOWER(?)", [name]
        )
        if not variety:
            return None

        # Enrich with growing data
        growing = self._query_one(
            "SELECT * FROM variety_growing_enrichment WHERE LOWER(variety) = LOWER(?)",
            [name],
        )
        if growing:
            variety["growing_data"] = growing

        # Disease resistance
        diseases = self._query(
            "SELECT * FROM disease_resistance WHERE LOWER(variety_or_gene) = LOWER(?)",
            [name],
        )
        if diseases:
            variety["disease_resistance"] = diseases

        # Cold tolerance markers for this crop's species
        crop = variety.get("crop", "")
        species_map = {
            "wheat": "wheat", "rye": "rye", "barley": "barley", "oat": "oat",
        }
        base_crop = crop.split("(")[0].strip().lower() if crop else ""
        species = species_map.get(base_crop, "")
        if species:
            markers = self._query(
                "SELECT * FROM markers WHERE LOWER(species) = LOWER(?)",
                [species],
            )
            if markers:
                variety["cold_tolerance_markers"] = markers

        return variety

    def match_varieties(self, zone: str = "", lat: float | None = None,
                        lon: float | None = None, crop: str = "",
                        limit: int = 10) -> dict | list:
        """Recommend varieties for a zone/location with planting windows.

        Returns a dict {zone, varieties, planting_calendars} when a zone is given
        or can be estimated from lat/lon; returns [] when there is nothing to
        match on (no zone and no coordinates).
        """
        # If lat/lon provided but no zone, estimate zone from the nearest station's
        # annual minimum temperature.
        if lat is not None and lon is not None and not zone:
            nearest = self._query_one("""
                SELECT gs.station_name, gs.country_name,
                       ROUND(gs.annual_min_tmin_c, 1) as avg_min
                FROM growing_season gs
                WHERE gs.annual_min_tmin_c IS NOT NULL
                ORDER BY ABS(gs.latitude - ?) + ABS(gs.longitude - ?)
                LIMIT 1
            """, [lat, lon])
            if nearest and nearest.get("avg_min") is not None:
                avg_min = nearest["avg_min"]
                # Approximate USDA zone from annual minimum temperature
                if avg_min <= -45:
                    zone = "1"
                elif avg_min <= -40:
                    zone = "2"
                elif avg_min <= -34:
                    zone = "3"
                elif avg_min <= -29:
                    zone = "4"
                elif avg_min <= -23:
                    zone = "5"
                elif avg_min <= -18:
                    zone = "6"
                else:
                    zone = "7"

        if not zone:
            return []

        conditions = ["usda_zone = ?"]
        params: list = [zone]

        if crop:
            conditions.append("LOWER(crop) LIKE '%' || ? || '%'")
            params.append(crop.lower())

        where = " AND ".join(conditions)
        varieties = self._query(f"""
            SELECT v.variety, v.crop, v.country, v.usda_zone, v.traits,
                   v.cold_tolerance_notes,
                   ve.seeding_rate, ve.seeding_depth, ve.days_to_maturity,
                   ve.seeding_window
            FROM varieties v
            LEFT JOIN variety_growing_enrichment ve
                ON LOWER(v.variety) = LOWER(ve.variety)
            WHERE {where}
            ORDER BY v.variety
            LIMIT ?
        """, params + [limit])

        # Add planting calendar data for the zone
        calendars = self._query(
            "SELECT * FROM planting_calendars WHERE zone = ?", [zone]
        )

        return {
            "zone": zone,
            "varieties": varieties,
            "planting_calendars": calendars,
        }

    def compare_varieties(self, names: list[str]) -> list[dict]:
        """Side-by-side comparison of 2-5 varieties."""
        if len(names) < 2 or len(names) > 5:
            return []
        placeholders = ", ".join(["?" for _ in names])
        results = self._query(f"""
            SELECT v.*, ve.seeding_rate, ve.seeding_depth,
                   ve.days_to_maturity, ve.seeding_window, ve.row_spacing
            FROM varieties v
            LEFT JOIN variety_growing_enrichment ve
                ON LOWER(v.variety) = LOWER(ve.variety)
            WHERE LOWER(v.variety) IN ({placeholders})
        """, [n.lower() for n in names])
        return results

    # --- Climate & Growing ---

    def get_growing_season(self, station: str = "", country: str = "",
                           limit: int = 20) -> list[dict]:
        """Get frost-free days, frost dates for stations/regions."""
        conditions = []
        params = []
        if station:
            conditions.append("LOWER(station_name) LIKE '%' || ? || '%'")
            params.append(station.lower())
        if country:
            conditions.append("LOWER(country_name) LIKE '%' || ? || '%'")
            params.append(country.lower())

        where = " AND ".join(conditions) if conditions else "1=1"
        return self._query(f"""
            SELECT station_name, country_name, latitude, longitude,
                   year, last_spring_frost, first_fall_frost,
                   frost_free_days, hard_freeze_days, annual_min_tmin_c
            FROM growing_season
            WHERE {where}
            ORDER BY year DESC, station_name
            LIMIT ?
        """, params + [limit])

    def get_climate_profile(self, zone: str = "", lat: float | None = None,
                            lon: float | None = None) -> dict:
        """Get zone, photoperiod, and soil data for a location."""
        result = {}

        if zone:
            zones = self._query(
                "SELECT * FROM climate_zones WHERE CAST(zone AS VARCHAR) = ?",
                [zone],
            )
            result["climate_zones"] = zones

        if lat is not None and lon is not None:
            # Nearest photoperiod zone
            photo = self._query("""
                SELECT * FROM photoperiod_zones
                ORDER BY ABS(latitude - ?) + ABS(longitude - ?)
                LIMIT 3
            """, [lat, lon])
            result["photoperiod_zones"] = photo

            # Nearest soil data
            soil = self._query("""
                SELECT * FROM soilgrids
                ORDER BY ABS(latitude - ?) + ABS(longitude - ?)
                LIMIT 3
            """, [lat, lon])
            result["soil_profiles"] = soil

            # Nearest trial sites
            sites = self._query("""
                SELECT * FROM field_trial_sites
                ORDER BY ABS(latitude - ?) + ABS(longitude - ?)
                LIMIT 3
            """, [lat, lon])
            result["nearest_trial_sites"] = sites

        return result

    def get_planting_calendar(self, zone: str = "", crop: str = "") -> list[dict]:
        """Get sowing windows by zone and crop."""
        conditions = []
        params = []
        if zone:
            # Zones are stored as ranges like "3-4", "2-3" — match if zone appears
            conditions.append("zone LIKE '%' || ? || '%'")
            params.append(zone)
        if crop:
            conditions.append("LOWER(crop) LIKE '%' || ? || '%'")
            params.append(crop.lower())

        where = " AND ".join(conditions) if conditions else "1=1"
        return self._query(f"""
            SELECT * FROM planting_calendars
            WHERE {where}
            ORDER BY zone, crop
        """, params)

    # --- Genomics & Breeding ---

    def search_markers(self, species: str = "", chromosome: str = "",
                       gene: str = "", limit: int = 50) -> list[dict]:
        """Search cold tolerance markers."""
        conditions = []
        params = []
        if species:
            conditions.append("LOWER(species) = LOWER(?)")
            params.append(species)
        if chromosome:
            conditions.append("LOWER(chromosome) = LOWER(?)")
            params.append(chromosome)
        if gene:
            conditions.append("LOWER(gene) LIKE '%' || ? || '%'")
            params.append(gene.lower())

        where = " AND ".join(conditions) if conditions else "1=1"
        return self._query(f"""
            SELECT * FROM markers WHERE {where}
            ORDER BY species, chromosome, locus
            LIMIT ?
        """, params + [limit])

    def search_qtl(self, species: str = "", trait: str = "",
                   limit: int = 50) -> list[dict]:
        """Search GrainGenes QTL by species and trait."""
        conditions = []
        params = []
        if species:
            conditions.append("LOWER(species) LIKE '%' || ? || '%'")
            params.append(species.lower())
        if trait:
            conditions.append("LOWER(trait) LIKE '%' || ? || '%'")
            params.append(trait.lower())

        where = " AND ".join(conditions) if conditions else "1=1"
        return self._query(f"""
            SELECT * FROM graingenes_qtl WHERE {where}
            ORDER BY species, trait
            LIMIT ?
        """, params + [limit])

    def get_breeding_program(self, program_id: str = "",
                             institution: str = "") -> dict | None:
        """Get breeding program details."""
        if program_id:
            return self._query_one(
                "SELECT * FROM breeding_programs WHERE LOWER(program_id) = LOWER(?)",
                [program_id],
            )
        if institution:
            return self._query_one(
                "SELECT * FROM breeding_programs WHERE LOWER(institution) LIKE '%' || ? || '%'",
                [institution.lower()],
            )
        return None

    # --- Culture & Sources ---

    def search_sourdough(self, grain_base: str = "", origin: str = "",
                         culture_type: str = "",
                         limit: int = 25) -> list[dict]:
        """Search sourdough starters with linked recipes."""
        conditions = []
        params = []
        if grain_base:
            conditions.append("LOWER(s.grain_base) LIKE '%' || ? || '%'")
            params.append(grain_base.lower())
        if origin:
            conditions.append("LOWER(s.origin_country) LIKE '%' || ? || '%'")
            params.append(origin.lower())
        if culture_type:
            conditions.append("LOWER(s.culture_type) LIKE '%' || ? || '%'")
            params.append(culture_type.lower())

        where = " AND ".join(conditions) if conditions else "1=1"
        starters = self._query(f"""
            SELECT s.*, r.recipe, r.hydration_pct, r.flour_type,
                   r.fermentation_schedule
            FROM sourdough_starters s
            LEFT JOIN sourdough_recipes r ON s.starter_id = r.starter_id
            WHERE {where}
            ORDER BY s.name
            LIMIT ?
        """, params + [limit])
        return starters

    def search_seed_sources(self, crop: str = "", country: str = "",
                            access_type: str = "",
                            limit: int = 25) -> list[dict]:
        """Search seed sources by crop, country, or access type."""
        conditions = []
        params = []
        if crop:
            conditions.append("LOWER(specialties) LIKE '%' || ? || '%'")
            params.append(crop.lower())
        if country:
            conditions.append("LOWER(country) LIKE '%' || ? || '%'")
            params.append(country.lower())
        if access_type:
            conditions.append("LOWER(type) LIKE '%' || ? || '%'")
            params.append(access_type.lower())

        where = " AND ".join(conditions) if conditions else "1=1"
        return self._query(f"""
            SELECT * FROM seed_sources
            WHERE {where}
            ORDER BY name
            LIMIT ?
        """, params + [limit])

    # --- Disease Resistance ---

    def get_disease_resistance(self, variety: str = "", pathogen: str = "",
                               crop: str = "", resistance_level: str = "",
                               limit: int = 50) -> list[dict]:
        """Search disease resistance records by variety, pathogen, crop, or resistance level."""
        conditions = []
        params = []
        if variety:
            conditions.append("LOWER(variety_or_gene) LIKE '%' || ? || '%'")
            params.append(variety.lower())
        if pathogen:
            conditions.append("LOWER(pathogen) LIKE '%' || ? || '%'")
            params.append(pathogen.lower())
        if crop:
            conditions.append("LOWER(crop) LIKE '%' || ? || '%'")
            params.append(crop.lower())
        if resistance_level:
            conditions.append("LOWER(resistance_level) LIKE '%' || ? || '%'")
            params.append(resistance_level.lower())

        where = " AND ".join(conditions) if conditions else "1=1"
        return self._query(f"""
            SELECT variety_or_gene, crop, pathogen, resistance_level,
                   mechanism, test_method, region, qtl_or_gene, source
            FROM disease_resistance
            WHERE {where}
            ORDER BY variety_or_gene, pathogen
            LIMIT ?
        """, params + [limit])

    # --- Distillery Grain Sources ---

    def get_distillery_grain_sources(self, country: str = "",
                                     spirit_type: str = "",
                                     heritage_only: bool = False,
                                     limit: int = 25) -> list[dict]:
        """Search distilleries by country, spirit type, or heritage focus."""
        conditions = []
        params = []
        if country:
            conditions.append("LOWER(country) LIKE '%' || ? || '%'")
            params.append(country.lower())
        if spirit_type:
            conditions.append("LOWER(spirit_type) LIKE '%' || ? || '%'")
            params.append(spirit_type.lower())
        if heritage_only:
            conditions.append("heritage_focus = TRUE")

        where = " AND ".join(conditions) if conditions else "1=1"
        return self._query(f"""
            SELECT distillery_id, name, country, city, founded,
                   spirit_type, heritage_focus, malting,
                   latitude, longitude, website, notes, source
            FROM distillery_profiles
            WHERE {where}
            ORDER BY country, name
            LIMIT ?
        """, params + [limit])

    # --- Rootstock Compatibility ---

    def get_rootstock_compatibility(self, crop_group: str = "",
                                    scion: str = "",
                                    max_zone: int | None = None,
                                    limit: int = 50) -> list[dict]:
        """Search rootstocks by crop group, scion compatibility, or cold hardiness zone."""
        conditions = []
        params = []
        if crop_group:
            conditions.append("LOWER(crop_group) LIKE '%' || ? || '%'")
            params.append(crop_group.lower())
        if scion:
            conditions.append("LOWER(compatible_scions) LIKE '%' || ? || '%'")
            params.append(scion.lower())
        if max_zone is not None:
            conditions.append("CAST(cold_hardiness_zone AS INTEGER) <= ?")
            params.append(max_zone)

        where = " AND ".join(conditions) if conditions else "1=1"
        return self._query(f"""
            SELECT rootstock, rootstock_species, crop_group,
                   compatible_scions, cold_hardiness_zone,
                   trunk_hardiness_c, root_hardiness_c, dwarfing,
                   disease_notes, origin, source
            FROM rootstock_compatibility
            WHERE {where}
            ORDER BY cold_hardiness_zone, rootstock
            LIMIT ?
        """, params + [limit])

    # --- Crop Wild Relatives ---

    def get_crop_wild_relatives(self, crop_group: str = "",
                                family: str = "",
                                max_zone: int | None = None,
                                grin_only: bool = False,
                                limit: int = 50) -> list[dict]:
        """Search crop wild relatives by crop group, family, zone, or GRIN availability."""
        conditions = []
        params = []
        if crop_group:
            conditions.append("LOWER(crop_group) LIKE '%' || ? || '%'")
            params.append(crop_group.lower())
        if family:
            conditions.append("LOWER(family) LIKE '%' || ? || '%'")
            params.append(family.lower())
        if max_zone is not None:
            conditions.append("CAST(usda_zone AS INTEGER) <= ?")
            params.append(max_zone)
        if grin_only:
            conditions.append("LOWER(grin_available) = 'yes'")

        where = " AND ".join(conditions) if conditions else "1=1"
        return self._query(f"""
            SELECT species, common_name, family, crop_group,
                   domesticated_relative, native_range,
                   min_survival_temp_c, cold_mechanism, usda_zone,
                   conservation_status, grin_available,
                   breeding_use, notes, source
            FROM crop_wild_relatives
            WHERE {where}
            ORDER BY crop_group, species
            LIMIT ?
        """, params + [limit])

    # --- Community Grain Projects ---

    def search_community_projects(
        self, country: str | None = None, crop: str | None = None,
        model: str | None = None, min_members: int | None = None,
        limit: int = 25,
    ) -> list[dict]:
        """Search community grain projects by country, crop, model, or minimum members."""
        where_parts = ["1=1"]
        params: list = []
        if country:
            where_parts.append("LOWER(country) = LOWER(?)")
            params.append(country)
        if crop:
            where_parts.append("LOWER(crops) LIKE '%' || LOWER(?) || '%'")
            params.append(crop)
        if model:
            where_parts.append("LOWER(model) = LOWER(?)")
            params.append(model)
        if min_members is not None:
            where_parts.append("CAST(members AS INTEGER) >= ?")
            params.append(min_members)
        where = " AND ".join(where_parts)
        return self._query(f"""
            SELECT project_id, name, country, city, latitude, longitude,
                   crops, founded_year, members, hectares, model, focus,
                   varieties_grown, website, notes, source
            FROM community_grain_projects
            WHERE {where}
            ORDER BY name
            LIMIT ?
        """, params + [limit])

    # --- EPPO Pathogens ---

    def search_eppo_pathogens(
        self, host_crop: str | None = None, pathogen_type: str | None = None,
        severity: str | None = None, quarantine_eu: bool | None = None,
        limit: int = 25,
    ) -> list[dict]:
        """Search EPPO pathogens by host crop, type, severity, or EU quarantine status."""
        where_parts = ["1=1"]
        params: list = []
        if host_crop:
            where_parts.append("LOWER(host_crops) LIKE '%' || LOWER(?) || '%'")
            params.append(host_crop)
        if pathogen_type:
            where_parts.append("LOWER(pathogen_type) = LOWER(?)")
            params.append(pathogen_type)
        if severity:
            where_parts.append("LOWER(severity) = LOWER(?)")
            params.append(severity)
        if quarantine_eu is not None:
            where_parts.append("LOWER(quarantine_eu) = LOWER(?)")
            params.append(str(quarantine_eu).lower())
        where = " AND ".join(where_parts)
        return self._query(f"""
            SELECT eppo_code, pathogen_name, common_name, host_crops,
                   pathogen_type, geographic_range, severity,
                   cold_climate_risk, management, quarantine_eu, notes, source
            FROM eppo_pathogens
            WHERE {where}
            ORDER BY pathogen_name
            LIMIT ?
        """, params + [limit])

    # --- Grower's Journal ---

    def get_journal_entries(
        self, variety: str = "", location: str = "",
        season: str = "", limit: int = 25,
    ) -> list[dict]:
        """Search grower's journal entries. Returns empty if table not yet synced."""
        conn = self._get_conn()
        # Check if table exists (populated by sync_grower_journal.py)
        tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
        if "grower_journal" not in tables:
            return []

        # Get column names to build flexible query
        cols = [c[0] for c in conn.execute("DESCRIBE grower_journal").fetchall()]

        where_parts = ["1=1"]
        params: list = []
        if variety:
            # Match any column that might contain variety info
            variety_cols = [c for c in cols if "variety" in c.lower() or "cultivar" in c.lower()]
            if variety_cols:
                clauses = [f"LOWER(CAST(\"{c}\" AS VARCHAR)) LIKE '%' || LOWER(?) || '%'" for c in variety_cols]
                where_parts.append(f"({' OR '.join(clauses)})")
                params.extend([variety] * len(variety_cols))
        if location:
            location_cols = [c for c in cols if "location" in c.lower() or "site" in c.lower() or "garden" in c.lower()]
            if location_cols:
                clauses = [f"LOWER(CAST(\"{c}\" AS VARCHAR)) LIKE '%' || LOWER(?) || '%'" for c in location_cols]
                where_parts.append(f"({' OR '.join(clauses)})")
                params.extend([location] * len(location_cols))
        if season:
            season_cols = [c for c in cols if "season" in c.lower() or "year" in c.lower() or "date" in c.lower()]
            if season_cols:
                clauses = [f"CAST(\"{c}\" AS VARCHAR) LIKE '%' || ? || '%'" for c in season_cols]
                where_parts.append(f"({' OR '.join(clauses)})")
                params.extend([season] * len(season_cols))

        where = " AND ".join(where_parts)
        return self._query(f"""
            SELECT * FROM grower_journal
            WHERE {where}
            ORDER BY created DESC
            LIMIT ?
        """, params + [limit])

    # --- Cross Reference ---

    def cross_reference(self, variety: str) -> dict:
        """Cross-reference a variety across all tables: markers, disease resistance,
        GRIN accessions, seed sources, and growing data."""
        result = {"variety": variety}

        # Base variety info
        base = self._query_one(
            "SELECT * FROM varieties WHERE LOWER(variety) = LOWER(?)", [variety]
        )
        if base:
            result["profile"] = base
        else:
            result["profile"] = None

        # Growing enrichment
        growing = self._query_one(
            "SELECT * FROM variety_growing_enrichment WHERE LOWER(variety) = LOWER(?)",
            [variety],
        )
        result["growing_data"] = growing

        # Disease resistance
        result["disease_resistance"] = self._query(
            "SELECT * FROM disease_resistance WHERE LOWER(variety_or_gene) = LOWER(?)",
            [variety],
        )

        # Cold tolerance markers (match on species from variety's crop)
        markers = []
        if base:
            crop = base.get("crop", "")
            species_map = {
                "wheat": "wheat", "rye": "rye", "barley": "barley", "oat": "oat",
            }
            base_crop = crop.split("(")[0].strip().lower() if crop else ""
            species = species_map.get(base_crop, "")
            if species:
                markers = self._query(
                    "SELECT * FROM markers WHERE LOWER(species) = LOWER(?)",
                    [species],
                )
        result["cold_tolerance_markers"] = markers

        # GRIN accessions (match on variety name in common_name or species)
        result["grin_accessions"] = self._query(
            """SELECT * FROM grin_accessions
               WHERE LOWER(common_name) LIKE '%' || ? || '%'
                  OR LOWER(species) LIKE '%' || ? || '%'""",
            [variety.lower(), variety.lower()],
        )

        # Seed sources (match on variety name in specialties)
        result["seed_sources"] = self._query(
            "SELECT * FROM seed_sources WHERE LOWER(specialties) LIKE '%' || ? || '%'",
            [variety.lower()],
        )

        return result
