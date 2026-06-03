#!/usr/bin/env python3
"""Load VAXT CSVs + ETL outputs into heritage-grain.duckdb (DuckDB).

Usage:
    python3 scripts/vaxt/load_heritage_grain.py [--validate]

Tables created:
    markers              — cold_tolerance_markers.csv
    varieties            — nordic_variety_trait_index.csv
    phenotype_records    — phenotype_template.csv
    graingenes_qtl       — data/datasets/heritage-grain/graingenes_qtl.csv
    grin_accessions      — grin_accessions.csv
    climate_zones        — climate_zones.csv
    crop_wild_relatives  — crop_wild_relatives.csv
    breeding_programs    — breeding_programs.csv
    rootstock_compatibility — rootstock_compatibility.csv
    disease_resistance   — disease_resistance.csv
    field_trial_sites    — field_trial_sites.csv
    t3_observations      — data/datasets/heritage-grain/t3_observations.csv (T3 BrAPI ETL)
    t3_germplasm         — data/datasets/heritage-grain/t3_germplasm.csv (T3 BrAPI ETL)
    gbif_occurrences     — data/datasets/heritage-grain/gbif_occurrences.csv (GBIF ETL)
    sourdough_starters   — sourdough_starters.csv
    sourdough_recipes    — sourdough_recipes.csv
    seed_sources         — seed_sources.csv
    planting_calendars   — planting_calendars.csv
    variety_growing_enrichment — variety_growing_enrichment.csv
    distillery_profiles  — distillery_profiles.csv
    community_grain_projects — community_grain_projects.csv
    eppo_pathogens       — eppo_pathogens.csv
    faostat_production   — data/datasets/heritage-grain/faostat_production.csv (FAOSTAT ETL)
    eurostat_production  — data/datasets/heritage-grain/eurostat_production.csv (Eurostat ETL)
    growing_season       — data/datasets/heritage-grain/growing_season.csv (derived from GHCN)
    photoperiod_zones    — data/datasets/heritage-grain/photoperiod_zones.csv (computed)
    soilgrids            — data/datasets/heritage-grain/soilgrids.csv (SoilGrids API)

Output: data/datasets/heritage-grain/heritage-grain.duckdb
"""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent
OUTPUT_DIR = WORKSPACE / "data" / "datasets" / "heritage-grain"
DB_PATH = OUTPUT_DIR / "heritage-grain.duckdb"

# Source files
MARKERS_CSV = SCRIPT_DIR / "cold_tolerance_markers.csv"
VARIETIES_CSV = SCRIPT_DIR / "nordic_variety_trait_index.csv"
PHENOTYPE_CSV = SCRIPT_DIR / "phenotype_template.csv"
GRAINGENES_CSV = OUTPUT_DIR / "graingenes_qtl.csv"
GRIN_CSV = SCRIPT_DIR / "grin_accessions.csv"
CLIMATE_CSV = SCRIPT_DIR / "climate_zones.csv"
WILD_RELATIVES_CSV = SCRIPT_DIR / "crop_wild_relatives.csv"
BREEDING_PROGRAMS_CSV = SCRIPT_DIR / "breeding_programs.csv"
ROOTSTOCK_CSV = SCRIPT_DIR / "rootstock_compatibility.csv"
DISEASE_RESISTANCE_CSV = SCRIPT_DIR / "disease_resistance.csv"
FIELD_TRIAL_SITES_CSV = SCRIPT_DIR / "field_trial_sites.csv"
T3_OBS_CSV = OUTPUT_DIR / "t3_observations.csv"
T3_GERM_CSV = OUTPUT_DIR / "t3_germplasm.csv"
GBIF_CSV = OUTPUT_DIR / "gbif_occurrences.csv"
SOURDOUGH_CSV = SCRIPT_DIR / "sourdough_starters.csv"
SOURDOUGH_RECIPES_CSV = SCRIPT_DIR / "sourdough_recipes.csv"
SEED_SOURCES_CSV = SCRIPT_DIR / "seed_sources.csv"
PLANTING_CALENDARS_CSV = SCRIPT_DIR / "planting_calendars.csv"
VARIETY_GROWING_CSV = SCRIPT_DIR / "variety_growing_enrichment.csv"
DISTILLERY_PROFILES_CSV = SCRIPT_DIR / "distillery_profiles.csv"
COMMUNITY_GRAIN_CSV = SCRIPT_DIR / "community_grain_projects.csv"
EPPO_PATHOGENS_CSV = SCRIPT_DIR / "eppo_pathogens.csv"
FAOSTAT_CSV = OUTPUT_DIR / "faostat_production.csv"
EUROSTAT_CSV = OUTPUT_DIR / "eurostat_production.csv"
GROWING_SEASON_CSV = OUTPUT_DIR / "growing_season.csv"
PHOTOPERIOD_CSV = OUTPUT_DIR / "photoperiod_zones.csv"
SOILGRIDS_CSV = OUTPUT_DIR / "soilgrids.csv"


def main():
    try:
        import duckdb
    except ImportError:
        print("Install duckdb: pip install duckdb", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Load VAXT data into heritage-grain.duckdb")
    parser.add_argument("--validate", action="store_true", help="Run validation queries after load")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Removed existing {DB_PATH.name}")

    conn = duckdb.connect(str(DB_PATH))
    print(f"Database: {DB_PATH}")

    total = 0
    sources = [
        ("markers", MARKERS_CSV),
        ("varieties", VARIETIES_CSV),
        ("phenotype_records", PHENOTYPE_CSV),
        ("graingenes_qtl", GRAINGENES_CSV),
        ("grin_accessions", GRIN_CSV),
        ("climate_zones", CLIMATE_CSV),
        ("crop_wild_relatives", WILD_RELATIVES_CSV),
        ("breeding_programs", BREEDING_PROGRAMS_CSV),
        ("rootstock_compatibility", ROOTSTOCK_CSV),
        ("disease_resistance", DISEASE_RESISTANCE_CSV),
        ("field_trial_sites", FIELD_TRIAL_SITES_CSV),
        ("t3_observations", T3_OBS_CSV),
        ("t3_germplasm", T3_GERM_CSV),
        ("gbif_occurrences", GBIF_CSV),
        ("sourdough_starters", SOURDOUGH_CSV),
        ("sourdough_recipes", SOURDOUGH_RECIPES_CSV),
        ("seed_sources", SEED_SOURCES_CSV),
        ("planting_calendars", PLANTING_CALENDARS_CSV),
        ("variety_growing_enrichment", VARIETY_GROWING_CSV),
        ("distillery_profiles", DISTILLERY_PROFILES_CSV),
        ("community_grain_projects", COMMUNITY_GRAIN_CSV),
        ("eppo_pathogens", EPPO_PATHOGENS_CSV),
        ("faostat_production", FAOSTAT_CSV),
        ("eurostat_production", EUROSTAT_CSV),
        ("growing_season", GROWING_SEASON_CSV),
        ("photoperiod_zones", PHOTOPERIOD_CSV),
        ("soilgrids", SOILGRIDS_CSV),
    ]

    for table, csv_path in sources:
        if not csv_path.exists():
            print(f"  SKIP: {table} — {csv_path.name} not found")
            continue
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute(f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto(?, delim=',', header=true)", [str(csv_path)])
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} rows from {csv_path.name}")
        total += count

    print(f"\nTotal: {total} rows across {len(sources)} tables")
    print(f"Size: {DB_PATH.stat().st_size / 1024:.1f} KB")

    if args.validate:
        validate(conn)

    conn.close()


def validate(conn) -> None:
    """Run sample queries to verify the database."""
    print("\n--- Validation Queries ---")

    # 1. Wheat markers on chromosome 5A
    r = conn.execute("SELECT COUNT(*) FROM markers WHERE species = 'wheat' AND chromosome = '5A'").fetchone()
    print(f"Wheat markers on chr 5A: {r[0]}")

    # 2. Varieties by country
    rows = conn.execute(
        "SELECT country, COUNT(*) as n FROM varieties GROUP BY country ORDER BY n DESC LIMIT 5"
    ).fetchall()
    print("Top 5 countries by variety count:")
    for row in rows:
        print(f"  {row[0] or '(unknown)'}: {row[1]}")

    # 3. Phenotype records with LT50 data
    rows = conn.execute(
        "SELECT genotype_name, lt50_su_c FROM phenotype_records WHERE lt50_su_c IS NOT NULL"
    ).fetchall()
    print("Genotypes with LT50 (survival):")
    for row in rows:
        print(f"  {row[0]}: {row[1]}°C")

    # 4. GrainGenes QTLs by species
    try:
        rows = conn.execute(
            "SELECT species, COUNT(*) as n FROM graingenes_qtl GROUP BY species ORDER BY n DESC"
        ).fetchall()
        print("GrainGenes QTLs by species:")
        for row in rows:
            print(f"  {row[0] or '(unknown)'}: {row[1]}")
    except Exception:
        print("GrainGenes QTLs: (table empty or missing)")

    # 5. Cross-table: markers + GrainGenes QTLs on same chromosome
    try:
        rows = conn.execute("""
            SELECT m.species, m.chromosome, COUNT(DISTINCT m.gene) AS marker_genes, COUNT(DISTINCT g.qtl_name) AS gg_qtls
            FROM markers m
            JOIN graingenes_qtl g ON m.chromosome = g.chromosome
            WHERE m.chromosome IS NOT NULL AND m.chromosome != ''
            GROUP BY m.species, m.chromosome
            ORDER BY gg_qtls DESC
            LIMIT 5
        """).fetchall()
        print("Marker/QTL overlap by chromosome:")
        for row in rows:
            print(f"  {row[0]} chr {row[1]}: {row[2]} marker genes, {row[3]} GrainGenes QTLs")
    except Exception:
        print("Marker/QTL overlap: (graingenes_qtl empty or missing)")

    # 6. GRIN accessions by crop group
    try:
        rows = conn.execute(
            "SELECT crop_group, COUNT(*) as n FROM grin_accessions GROUP BY crop_group ORDER BY n DESC"
        ).fetchall()
        print("GRIN accessions by crop group:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")
    except Exception:
        print("GRIN accessions: (table empty or missing)")

    # 7. Climate zones summary
    try:
        r = conn.execute("SELECT COUNT(*) FROM climate_zones").fetchone()
        coldest = conn.execute(
            "SELECT zone, subzone, min_temp_c FROM climate_zones ORDER BY min_temp_c ASC LIMIT 1"
        ).fetchone()
        print(f"Climate zones: {r[0]} entries (coldest: zone {coldest[0]}{coldest[1]} at {coldest[2]}°C)")
    except Exception:
        print("Climate zones: (table empty or missing)")

    # 8. Crop wild relatives — hardiest species
    try:
        rows = conn.execute(
            "SELECT common_name, min_survival_temp_c FROM crop_wild_relatives ORDER BY min_survival_temp_c ASC LIMIT 5"
        ).fetchall()
        print("Hardiest wild relatives:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}°C")
    except Exception:
        print("Crop wild relatives: (table empty or missing)")

    # 9. Breeding programs by country
    try:
        rows = conn.execute(
            "SELECT country, COUNT(*) as n FROM breeding_programs GROUP BY country ORDER BY n DESC LIMIT 5"
        ).fetchall()
        print("Breeding programs by country:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")
    except Exception:
        print("Breeding programs: (table empty or missing)")

    # 10. Rootstock compatibility — hardiest rootstocks
    try:
        rows = conn.execute(
            "SELECT rootstock, crop_group, cold_hardiness_zone, root_hardiness_c FROM rootstock_compatibility ORDER BY root_hardiness_c ASC LIMIT 5"
        ).fetchall()
        print("Hardiest rootstocks (by root hardiness):")
        for row in rows:
            print(f"  {row[0]} ({row[1]}): zone {row[2]}, roots survive {row[3]}°C")
    except Exception:
        print("Rootstock compatibility: (table empty or missing)")

    # 11. Disease resistance — pathogens tested
    try:
        rows = conn.execute(
            "SELECT pathogen, COUNT(*) as n FROM disease_resistance GROUP BY pathogen ORDER BY n DESC"
        ).fetchall()
        print("Disease resistance entries by pathogen:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")
    except Exception:
        print("Disease resistance: (table empty or missing)")

    # 12. Field trial sites by country
    try:
        rows = conn.execute(
            "SELECT country, COUNT(*) as n FROM field_trial_sites GROUP BY country ORDER BY n DESC LIMIT 5"
        ).fetchall()
        print("Field trial sites by country:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")
    except Exception:
        print("Field trial sites: (table empty or missing)")

    # T3 observations by crop and variable
    try:
        rows = conn.execute("""
            SELECT crop, variable_name, COUNT(*) as n
            FROM t3_observations
            GROUP BY crop, variable_name
            ORDER BY crop, n DESC
        """).fetchall()
        print("T3 observations by crop/variable:")
        for row in rows:
            print(f"  {row[0]}: {row[1]} ({row[2]})")
    except Exception:
        print("T3 observations: (table empty or missing)")

    # 10. T3 germplasm by genus
    try:
        rows = conn.execute("""
            SELECT genus, COUNT(*) as n
            FROM t3_germplasm
            GROUP BY genus
            ORDER BY n DESC
        """).fetchall()
        print("T3 germplasm by genus:")
        for row in rows:
            print(f"  {row[0] or '(unknown)'}: {row[1]}")
    except Exception:
        print("T3 germplasm: (table empty or missing)")

    # 11. T3 cross-table: germplasm with observations and pedigree
    try:
        rows = conn.execute("""
            SELECT g.germplasm_name, g.species, g.pedigree, COUNT(*) as obs_count
            FROM t3_observations o
            JOIN t3_germplasm g ON o.germplasm_db_id = CAST(g.germplasm_db_id AS VARCHAR) AND o.crop = g.crop
            WHERE g.pedigree IS NOT NULL AND g.pedigree != '' AND g.pedigree != 'NA/NA'
            GROUP BY g.germplasm_name, g.species, g.pedigree
            ORDER BY obs_count DESC
            LIMIT 5
        """).fetchall()
        print("T3 germplasm with most observations (and pedigree):")
        for row in rows:
            print(f"  {row[0]} ({row[1]}): {row[3]} obs, pedigree: {row[2][:60]}")
    except Exception:
        print("T3 germplasm/observations cross: (join failed or data missing)")

    # 12. Varieties matched to climate zones
    try:
        rows = conn.execute("""
            SELECT v.variety, v.crop, v.usda_zone, cz.min_temp_c
            FROM varieties v
            JOIN climate_zones cz ON CAST(SPLIT_PART(v.usda_zone, '-', 1) AS INTEGER) = cz.zone
                AND cz.subzone = 'a'
            WHERE v.usda_zone IS NOT NULL AND v.usda_zone != ''
            ORDER BY cz.min_temp_c ASC
            LIMIT 5
        """).fetchall()
        print("Hardiest cultivars (by zone min temp):")
        for row in rows:
            print(f"  {row[0]} ({row[1]}): zone {row[2]}, survives {row[3]}°C")
    except Exception:
        print("Variety/zone cross: (join failed or data missing)")

    # 13. GBIF occurrences by genus and country
    try:
        rows = conn.execute("""
            SELECT genus, country_code, COUNT(*) as n
            FROM gbif_occurrences
            GROUP BY genus, country_code
            ORDER BY n DESC
            LIMIT 10
        """).fetchall()
        print("GBIF occurrences by genus/country (top 10):")
        for row in rows:
            print(f"  {row[0]} in {row[1]}: {row[2]}")
    except Exception:
        print("GBIF occurrences: (table empty or missing)")

    # 14. GBIF northernmost occurrences (cold adaptation evidence)
    try:
        rows = conn.execute("""
            SELECT species, decimal_latitude, country_code, genus
            FROM gbif_occurrences
            WHERE decimal_latitude IS NOT NULL
            ORDER BY decimal_latitude DESC
            LIMIT 5
        """).fetchall()
        print("GBIF northernmost occurrences:")
        for row in rows:
            print(f"  {row[0]} at {row[1]:.2f}N ({row[2]})")
    except Exception:
        print("GBIF northernmost: (table empty or missing)")

    # 15. GBIF cross: wild relatives matched to crop_wild_relatives table
    try:
        rows = conn.execute("""
            SELECT g.genus, cwr.common_name, cwr.min_survival_temp_c, COUNT(*) as gbif_records
            FROM gbif_occurrences g
            JOIN crop_wild_relatives cwr ON g.genus = SPLIT_PART(cwr.species, ' ', 1)
            GROUP BY g.genus, cwr.common_name, cwr.min_survival_temp_c
            ORDER BY gbif_records DESC
            LIMIT 5
        """).fetchall()
        print("GBIF genus matched to crop wild relatives:")
        for row in rows:
            print(f"  {row[0]} ({row[1]}): {row[3]} GBIF records, survives {row[2]}C")
    except Exception:
        print("GBIF/CWR cross: (join failed or data missing)")

    # 16. Sourdough starters by grain base
    try:
        rows = conn.execute("""
            SELECT grain_base, COUNT(*) as n
            FROM sourdough_starters
            GROUP BY grain_base
            ORDER BY n DESC
        """).fetchall()
        print("Sourdough starters by grain base:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")
    except Exception:
        print("Sourdough starters: (table empty or missing)")

    # 17. Oldest sourdough cultures
    try:
        rows = conn.execute("""
            SELECT name, origin_country, estimated_age_years, grain_base, culture_type
            FROM sourdough_starters
            ORDER BY estimated_age_years DESC
            LIMIT 5
        """).fetchall()
        print("Oldest sourdough cultures:")
        for row in rows:
            print(f"  {row[0]} ({row[1]}): ~{row[2]} years, {row[3]} {row[4]}")
    except Exception:
        print("Sourdough oldest: (table empty or missing)")

    # Community grain projects by country
    try:
        rows = conn.execute("""
            SELECT country, COUNT(*) as n
            FROM community_grain_projects
            GROUP BY country
            ORDER BY n DESC
            LIMIT 5
        """).fetchall()
        print("Community grain projects by country:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")
    except Exception:
        print("Community grain projects: (table empty or missing)")

    # Community grain projects × varieties cross-join
    try:
        rows = conn.execute("""
            SELECT cgp.name, cgp.country, cgp.varieties_grown
            FROM community_grain_projects cgp
            WHERE cgp.varieties_grown IS NOT NULL AND cgp.varieties_grown != ''
            LIMIT 5
        """).fetchall()
        print("Community projects with named varieties:")
        for row in rows:
            print(f"  {row[0]} ({row[1]}): {row[2][:60]}")
    except Exception:
        print("Community grain projects varieties: (table empty or missing)")

    # EPPO pathogens by type
    try:
        rows = conn.execute("""
            SELECT pathogen_type, COUNT(*) as n
            FROM eppo_pathogens
            GROUP BY pathogen_type
            ORDER BY n DESC
        """).fetchall()
        print("EPPO pathogens by type:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")
    except Exception:
        print("EPPO pathogens: (table empty or missing)")

    # EPPO × disease_resistance cross-join
    try:
        rows = conn.execute("""
            SELECT e.common_name, e.severity, COUNT(DISTINCT dr.variety_or_gene) as resistant_varieties
            FROM eppo_pathogens e
            JOIN disease_resistance dr ON LOWER(e.pathogen_name) = LOWER(dr.pathogen)
            GROUP BY e.common_name, e.severity
            ORDER BY resistant_varieties DESC
            LIMIT 5
        """).fetchall()
        print("EPPO pathogens with most resistance records:")
        for row in rows:
            print(f"  {row[0]} (severity: {row[1]}): {row[2]} resistant varieties/genes")
    except Exception:
        print("EPPO/disease_resistance cross: (join failed or data missing)")

    # FAOSTAT: production by country/crop (latest year)
    try:
        latest = conn.execute("SELECT MAX(year) FROM faostat_production").fetchone()[0]
        rows = conn.execute(f"""
            SELECT area, item, value FROM faostat_production
            WHERE year = {latest} AND element = 'Production'
            ORDER BY CAST(value AS DOUBLE) DESC
            LIMIT 5
        """).fetchall()
        print(f"FAOSTAT top producers ({latest}, tonnes):")
        for row in rows:
            print(f"  {row[0]}: {row[1]} — {float(row[2]):,.0f} t")
    except Exception:
        print("FAOSTAT production: (table empty or missing)")

    # FAOSTAT: Nordic cereal trends (Sweden wheat over time)
    try:
        rows = conn.execute("""
            SELECT year, value FROM faostat_production
            WHERE area = 'Sweden' AND item = 'Wheat' AND element = 'Production'
            ORDER BY year DESC
            LIMIT 5
        """).fetchall()
        print("Sweden wheat production (recent years):")
        for row in rows:
            print(f"  {row[0]}: {float(row[1]):,.0f} t")
    except Exception:
        print("FAOSTAT Sweden wheat: (table empty or missing)")

    # FAOSTAT: cross-table with varieties (countries that grow our crop types)
    try:
        rows = conn.execute(f"""
            SELECT f.area, COUNT(DISTINCT v.variety) as varieties, SUM(CAST(f.value AS DOUBLE)) as total_prod
            FROM faostat_production f
            JOIN varieties v ON LOWER(f.item) = LOWER(SPLIT_PART(v.crop, ' ', 1))
                AND f.area IN (
                    SELECT CASE v2.country
                        WHEN 'Finland' THEN 'Finland'
                        WHEN 'Sweden' THEN 'Sweden'
                        WHEN 'Norway' THEN 'Norway'
                        WHEN 'Canada' THEN 'Canada'
                        WHEN 'USA' THEN 'United States of America'
                        ELSE v2.country
                    END FROM varieties v2 WHERE v2.country = v.country
                )
            WHERE f.year = (SELECT MAX(year) FROM faostat_production) AND f.element = 'Production'
            GROUP BY f.area
            ORDER BY varieties DESC
            LIMIT 5
        """).fetchall()
        print("Countries with both VAXT varieties and FAOSTAT production:")
        for row in rows:
            print(f"  {row[0]}: {row[1]} varieties, {row[2]:,.0f} t total")
    except Exception:
        print("FAOSTAT/varieties cross: (join failed or data missing)")

    # Eurostat: top producers (latest year with data)
    try:
        latest = conn.execute("""
            SELECT MAX(year) FROM eurostat_production
            WHERE metric_code = 'PR_HU_EU' AND value IS NOT NULL
        """).fetchone()[0]
        rows = conn.execute(f"""
            SELECT geo_label, crop_label, value FROM eurostat_production
            WHERE year = {latest} AND metric_code = 'PR_HU_EU'
            ORDER BY value DESC
            LIMIT 5
        """).fetchall()
        print(f"Eurostat top producers ({latest}, 1000 t EU humidity):")
        for row in rows:
            print(f"  {row[0]}: {row[1]} — {row[2]:,.1f} kt")
    except Exception:
        print("Eurostat production: (table empty or missing)")

    # Eurostat: Nordic barley yield trends
    try:
        rows = conn.execute("""
            SELECT year, value FROM eurostat_production
            WHERE geo = 'FI' AND crop_code = 'C1300' AND metric_code = 'YI_HU_EU'
            ORDER BY year DESC
            LIMIT 5
        """).fetchall()
        print("Finland barley yield (recent years, t/ha):")
        for row in rows:
            print(f"  {row[0]}: {row[1]:.2f} t/ha")
    except Exception:
        print("Eurostat Finland barley: (table empty or missing)")

    # Eurostat vs FAOSTAT cross-check (Sweden wheat)
    try:
        rows = conn.execute("""
            SELECT e.year,
                   e.value AS eurostat_kt,
                   CAST(f.value AS DOUBLE) / 1000 AS faostat_kt
            FROM eurostat_production e
            JOIN faostat_production f ON e.year = f.year
            WHERE e.geo = 'SE' AND e.crop_code = 'C1100' AND e.metric_code = 'PR_HU_EU'
              AND f.area = 'Sweden' AND f.item = 'Wheat' AND f.element = 'Production'
            ORDER BY e.year DESC
            LIMIT 5
        """).fetchall()
        print("Sweden wheat: Eurostat vs FAOSTAT (1000 t):")
        for row in rows:
            diff_pct = ((row[1] - row[2]) / row[2] * 100) if row[2] else 0
            print(f"  {row[0]}: Eurostat {row[1]:,.1f} / FAOSTAT {row[2]:,.1f} ({diff_pct:+.1f}%)")
    except Exception:
        print("Eurostat/FAOSTAT cross: (join failed or data missing)")

    # Growing season: frost-free days by country
    try:
        rows = conn.execute("""
            SELECT country_name, COUNT(*) as n,
                   ROUND(AVG(frost_free_days), 0) as avg_ff,
                   MIN(annual_min_tmin_c) as coldest
            FROM growing_season
            WHERE frost_free_days IS NOT NULL
            GROUP BY country_name
            ORDER BY avg_ff ASC
            LIMIT 5
        """).fetchall()
        print("Growing season by country (shortest frost-free):")
        for row in rows:
            print(f"  {row[0]}: {row[1]} station-years, avg {row[2]:.0f} frost-free days, coldest {row[3]}C")
    except Exception:
        print("Growing season: (table empty or missing)")

    # Growing season × field trial sites cross-join
    try:
        rows = conn.execute("""
            SELECT f.name, f.country, g.year,
                   g.frost_free_days, g.annual_min_tmin_c
            FROM field_trial_sites f
            JOIN growing_season g ON ABS(f.latitude - g.latitude) < 0.5
                AND ABS(f.longitude - g.longitude) < 0.5
            WHERE g.frost_free_days IS NOT NULL
            ORDER BY g.frost_free_days ASC
            LIMIT 5
        """).fetchall()
        print("Trial sites matched to nearest GHCN station (shortest seasons):")
        for row in rows:
            print(f"  {row[0]} ({row[1]}) {row[2]}: {row[3]} frost-free days, min {row[4]}C")
    except Exception:
        print("Growing season/sites cross: (join failed or data missing)")

    # Photoperiod zones summary
    try:
        rows = conn.execute("""
            SELECT photoperiod_class, COUNT(*) as n,
                   ROUND(AVG(daylength_summer_solstice_h), 1) as avg_summer
            FROM photoperiod_zones
            GROUP BY photoperiod_class
            ORDER BY avg_summer DESC
        """).fetchall()
        print("Photoperiod classes:")
        for row in rows:
            print(f"  {row[0]}: {row[1]} sites, avg {row[2]}h at summer solstice")
    except Exception:
        print("Photoperiod zones: (table empty or missing)")

    # Photoperiod × varieties cross (long-day cereal zones)
    try:
        rows = conn.execute("""
            SELECT p.name, p.country, p.daylength_summer_solstice_h,
                   p.photoperiod_class
            FROM photoperiod_zones p
            WHERE p.polar_day = 'yes'
            ORDER BY p.latitude DESC
        """).fetchall()
        print("Polar day sites (midnight sun):")
        for row in rows:
            print(f"  {row[0]} ({row[1]}): {row[2]}h, {row[3]}")
    except Exception:
        print("Photoperiod polar: (table empty or missing)")

    # SoilGrids summary
    try:
        rows = conn.execute("""
            SELECT soil_texture_class, COUNT(*) as n,
                   ROUND(AVG(ph_h2o), 1) as avg_ph
            FROM soilgrids
            WHERE soil_texture_class != ''
            GROUP BY soil_texture_class
            ORDER BY n DESC
            LIMIT 5
        """).fetchall()
        print("Soil texture classes at trial sites:")
        for row in rows:
            print(f"  {row[0]}: {row[1]} sites, avg pH {row[2]}")
    except Exception:
        print("SoilGrids: (table empty or missing)")

    # SoilGrids × field trial sites (most acidic soils)
    try:
        rows = conn.execute("""
            SELECT s.name, s.country, s.ph_h2o, s.clay_pct,
                   s.soc_g_per_kg, s.soil_texture_class
            FROM soilgrids s
            WHERE s.ph_h2o != '' AND s.ph_h2o IS NOT NULL
            ORDER BY s.ph_h2o ASC
            LIMIT 5
        """).fetchall()
        print("Most acidic trial sites:")
        for row in rows:
            print(f"  {row[0]} ({row[1]}): pH {row[2]}, clay {row[3]}%, SOC {row[4]} g/kg, {row[5]}")
    except Exception:
        print("SoilGrids acidic: (table empty or missing)")

    # Seed sources by type
    try:
        rows = conn.execute("""
            SELECT type, COUNT(*) as n
            FROM seed_sources
            GROUP BY type
            ORDER BY n DESC
        """).fetchall()
        print("Seed sources by type:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")
    except Exception:
        print("Seed sources: (table empty or missing)")

    # Planting calendars by crop
    try:
        rows = conn.execute("""
            SELECT crop, type, COUNT(*) as n
            FROM planting_calendars
            GROUP BY crop, type
            ORDER BY crop, type
        """).fetchall()
        print("Planting calendars by crop/type:")
        for row in rows:
            print(f"  {row[0]} ({row[1]}): {row[2]} zone entries")
    except Exception:
        print("Planting calendars: (table empty or missing)")

    # Variety growing enrichment × varieties cross-join
    try:
        rows = conn.execute("""
            SELECT vge.variety, v.crop, vge.days_to_maturity, vge.seeding_rate
            FROM variety_growing_enrichment vge
            JOIN varieties v ON vge.variety = v.variety
            ORDER BY v.crop, vge.variety
            LIMIT 10
        """).fetchall()
        print("Enriched varieties matched to trait index:")
        for row in rows:
            print(f"  {row[0]} ({row[1]}): {row[2]} days, {row[3]}")
    except Exception:
        print("Variety growing enrichment: (table empty or cross-join failed)")

    # 18. Sourdough starters with cold/arctic preservation
    try:
        rows = conn.execute("""
            SELECT name, origin_country, preservation_method, grain_base
            FROM sourdough_starters
            WHERE preservation_method ILIKE '%freeze%'
               OR preservation_method ILIKE '%lyophil%'
               OR origin_country IN ('Iceland', 'Greenland', 'Faroe Islands')
               OR notes ILIKE '%arctic%' OR notes ILIKE '%cold%' OR notes ILIKE '%-40%'
        """).fetchall()
        print("Cold-adapted/arctic sourdough cultures:")
        for row in rows:
            print(f"  {row[0]} ({row[1]}): {row[2]}, {row[3]}")
    except Exception:
        print("Sourdough cold-adapted: (table empty or missing)")


if __name__ == "__main__":
    main()
