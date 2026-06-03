# VAXT — Heritage Grain Data Scripts

Scripts for VAXT data products: cold-tolerance marker registry, Nordic variety index, phenotype schema, GRIN germplasm, climate zones, and crop wild relatives.

**Layout:**

| What | Path |
|------|------|
| Scripts & ETL | `scripts/vaxt/` |
| Static source CSVs | `scripts/vaxt/*.csv` (committed) |
| Runtime data (DuckDB + ETL outputs) | `data/datasets/heritage-grain/` (gitignored) |
| MCP server | `packages/vaxt/` |

**Data products:**

| File | Description |
|------|-------------|
| `cold_tolerance_markers.csv` | ~141 markers (wheat, barley, rye, oat, triticale, apple, cherry, peach, grape, haskap, blueberry, black currant, strawberry, raspberry, timothy, meadow fescue, perennial ryegrass, lingonberry, cloudberry, sea buckthorn) |
| `nordic_variety_trait_index.csv` | ~200 varieties (cereals, forage grasses, berries, fruit trees, grapes, pear, plum, saskatoon, currant, gooseberry) |
| `phenotype_template.csv` | ~53 records (LT50, electrolyte leakage, ice encasement, snow mold, winter survival, DTA, dehardening, crown moisture, multi-site/multi-year) |
| `grin_accessions.csv` | ~70 USDA GRIN germplasm accessions with cold tolerance traits |
| `climate_zones.csv` | 16 USDA hardiness zones (1a–8b) with temperature ranges |
| `crop_wild_relatives.csv` | ~41 wild progenitor species with extreme cold tolerance |
| `breeding_programs.csv` | ~50 breeding programs worldwide (Nordic, Canadian, US, Russian, Baltic, Asian) |
| `rootstock_compatibility.csv` | ~60 rootstock entries (apple, pear, cherry, plum, grape, apricot) |
| `disease_resistance.csv` | ~50 snow mold/winter disease resistance entries (M. nivale, Typhula, Sclerotinia) |
| `field_trial_sites.csv` | ~40 field trial sites worldwide (Norway, Finland, Sweden, Canada, USA, Iceland, Russia) |
| `sourdough_starters.csv` | ~35 heritage sourdough cultures (San Francisco, Finnish ruis, Icelandic rúgbrauð, Arctic cultures) |
| `phenotype_schema.json` | JSON Schema for phenotype records (71 fields, 11 required) |

**Pipeline runner (sources.toml):**
```bash
python3 scripts/vaxt/vaxt_runner.py --list           # List all sources with status
python3 scripts/vaxt/vaxt_runner.py --dry-run        # Show plan; pass --dry-run to ETL scripts
python3 scripts/vaxt/vaxt_runner.py                  # Run all enabled sources (fetch + load + validate)
python3 scripts/vaxt/vaxt_runner.py --source markers # Run one source
python3 scripts/vaxt/vaxt_runner.py --validate-only  # Validate existing DuckDB without re-loading
python3 scripts/vaxt/vaxt_runner.py --fetch-only     # Run ETL fetch only (no load/validate)
```

All source declarations (paths, table names, column requirements, validation rules) live in `sources.toml`.

**Validate (standalone):**
```bash
python3 scripts/vaxt/validate_markers.py
python3 scripts/vaxt/validate_variety_index.py
python3 scripts/vaxt/validate_phenotype.py
```

**ETL — GrainGenes (standalone):**
```bash
python3 scripts/vaxt/etl_graingenes.py              # Full run (scrapes GrainGenes, ~60s)
python3 scripts/vaxt/etl_graingenes.py --dry-run     # List QTLs without fetching
python3 scripts/vaxt/etl_graingenes.py --delay 2.0   # Slower rate limit
```
Output: `data/datasets/heritage-grain/graingenes_qtl.csv` (59 QTLs: frost tolerance, winter survival, snow mold)

**ETL — T3 Triticeae Toolbox (standalone, BrAPI v2):**
```bash
python3 scripts/vaxt/etl_t3_brapi.py                # Full run (wheat + barley + oat, ~20min)
python3 scripts/vaxt/etl_t3_brapi.py --dry-run       # List variables/trials only
python3 scripts/vaxt/etl_t3_brapi.py --crop wheat    # Single crop
python3 scripts/vaxt/etl_t3_brapi.py --max-trials 5  # Limit trials per variable
python3 scripts/vaxt/etl_t3_brapi.py --delay 1.5     # Slower rate limit
```
Output:
- `data/datasets/heritage-grain/t3_observations.csv` — winterhardiness phenotype observations
- `data/datasets/heritage-grain/t3_germplasm.csv` — germplasm metadata (genus, species, pedigree)

T3 winterhardiness variables:

| Crop | Variable | Trials |
|------|----------|--------|
| Wheat | Winter kill damage - % | 111 |
| Wheat | Winter kill damage - 0-9 DAMAGE scale | 74 |
| Wheat | Spring regrowth - 1-10 scale | 143 |
| Wheat | Frost damage - % | 15 |
| Wheat | Frost damage - 0-3 injury scale | 2 |
| Barley | Winter hardiness - % | 254 |
| Oat | Winter survival - percent | 103 |
| Oat | Winter stress severity - 0-9 Rating | 45 |
| Oat | Freeze damage severity - 0-9 Rating | 15 |

**ETL — GBIF Occurrences (standalone):**
```bash
python3 scripts/vaxt/etl_gbif.py                # Full run (14 taxa × 11 countries, ~5min)
python3 scripts/vaxt/etl_gbif.py --dry-run       # List species/country counts only
python3 scripts/vaxt/etl_gbif.py --delay 1.5     # Slower rate limit
python3 scripts/vaxt/etl_gbif.py --limit 500     # Max records per species per country
```
Output: `data/datasets/heritage-grain/gbif_occurrences.csv` (cold-hardy crop wild relative occurrences in Nordic/Arctic regions)

GBIF target taxa (14 genera):

| Group | Genera |
|-------|--------|
| Cereal wild relatives | Aegilops, Triticum (wild), Hordeum, Secale, Avena |
| Forage grasses | Phleum (timothy), Festuca (fescue), Lolium (ryegrass) |
| Berry wild relatives | Rubus, Vaccinium, Ribes, Hippophae (sea buckthorn) |
| Fruit wild relatives | Malus (wild apple), Prunus |

Countries: NO, SE, FI, IS, DK, GL, RU, CA, EE, LV, LT

**ETL — FAOSTAT Crop Production (standalone):**
```bash
python3 scripts/vaxt/etl_faostat.py                # Full run (downloads 33MB bulk ZIP, ~30s)
python3 scripts/vaxt/etl_faostat.py --dry-run       # Show filter plan only
python3 scripts/vaxt/etl_faostat.py --skip-download  # Reuse cached ZIP
python3 scripts/vaxt/etl_faostat.py --year-min 2000  # Start from 2000
```
Output: `data/datasets/heritage-grain/faostat_production.csv` (area harvested, production, yield for 5 cereals × 14 countries × 64 years)

FAOSTAT coverage:

| Dimension | Values |
|-----------|--------|
| Crops | Wheat, Barley, Rye, Oats, Triticale |
| Countries | Sweden, Finland, Norway, Denmark, Iceland, Estonia, Latvia, Lithuania, Canada, Russia, USA, Poland, Germany, UK |
| Metrics | Area harvested (ha), Production (tonnes), Yield (kg/ha) |
| Years | 1961–2024 |

**ETL — Eurostat Crop Production (standalone):**
```bash
python3 scripts/vaxt/etl_eurostat.py                # Full run (JSON-stat API, ~5s)
python3 scripts/vaxt/etl_eurostat.py --dry-run       # Show filter plan only
python3 scripts/vaxt/etl_eurostat.py --year-min 2000  # Start from 2000
```
Output: `data/datasets/heritage-grain/eurostat_production.csv` (area, production in EU humidity, yield for 5 cereals × 10 countries × 25+ years)

Eurostat coverage:

| Dimension | Values |
|-----------|--------|
| Crops | Wheat and spelt, Barley, Rye, Oats, Triticale |
| Countries | Sweden, Finland, Norway, Denmark, Iceland, Estonia, Latvia, Lithuania, Poland, Germany |
| Metrics | Area harvested (1000 ha), Production in EU humidity (1000 t), Yield in EU humidity (t/ha) |
| Years | 2000–2025 |

**ETL — Growing Season (standalone, derived from GHCN):**
```bash
python3 scripts/vaxt/etl_growing_season.py                # Full run (derived from GHCN TMIN, no network)
python3 scripts/vaxt/etl_growing_season.py --dry-run       # Show station/year counts only
python3 scripts/vaxt/etl_growing_season.py --frost-threshold -2  # Custom frost cutoff
```
Output: `data/datasets/heritage-grain/growing_season.csv` (3,700+ station-years: last spring frost, first fall frost, frost-free days, hard-freeze days, annual min)

Requires GHCN data (`etl_ghcn.py`) to have run first.

**ETL — Photoperiod Zones (standalone, pure computation):**
```bash
python3 scripts/vaxt/etl_photoperiod.py                # Full run (instant, no network)
python3 scripts/vaxt/etl_photoperiod.py --dry-run       # Show site list only
```
Output: `data/datasets/heritage-grain/photoperiod_zones.csv` (40 sites: day length at solstice/equinox, photoperiod class, polar day/night flags)

Nordic cereals are long-day sensitive (16h+). Computes day length from latitude using solar declination geometry.

| Class | Summer solstice | Sites |
|-------|----------------|-------|
| ultra-long-day | >= 20h (polar/sub-polar) | 6 |
| long-day | 16–20h (typical Nordic) | 22 |
| intermediate | 14–16h (temperate) | 12 |

**ETL — SoilGrids (standalone, REST API):**
```bash
python3 scripts/vaxt/etl_soilgrids.py                # Full run (40 API calls, ~40s)
python3 scripts/vaxt/etl_soilgrids.py --dry-run       # Show site list only
python3 scripts/vaxt/etl_soilgrids.py --delay 2.0     # Slower rate limit
```
Output: `data/datasets/heritage-grain/soilgrids.csv` (40 sites: pH, clay/sand/silt %, organic carbon, nitrogen, CEC, soil texture class)

Source: rest.soilgrids.org (ISRIC, CC-BY 4.0, free, no auth)

**DuckDB database (standalone):**
```bash
python3 scripts/vaxt/load_heritage_grain.py              # Load all CSVs into DuckDB
python3 scripts/vaxt/load_heritage_grain.py --validate   # Load + run validation queries
```
Output: `data/datasets/heritage-grain/heritage-grain.duckdb` (20 tables)

| Table | Source |
|-------|--------|
| `markers` | `cold_tolerance_markers.csv` |
| `varieties` | `nordic_variety_trait_index.csv` |
| `phenotype_records` | `phenotype_template.csv` |
| `graingenes_qtl` | GrainGenes ETL output |
| `grin_accessions` | `grin_accessions.csv` |
| `climate_zones` | `climate_zones.csv` |
| `crop_wild_relatives` | `crop_wild_relatives.csv` |
| `breeding_programs` | `breeding_programs.csv` |
| `rootstock_compatibility` | `rootstock_compatibility.csv` |
| `disease_resistance` | `disease_resistance.csv` |
| `field_trial_sites` | `field_trial_sites.csv` |
| `t3_observations` | T3 BrAPI ETL (winterhardiness phenotypes) |
| `t3_germplasm` | T3 BrAPI ETL (germplasm metadata) |
| `gbif_occurrences` | GBIF ETL (Nordic/Arctic crop wild relative occurrences) |
| `sourdough_starters` | `sourdough_starters.csv` |
| `faostat_production` | FAOSTAT ETL (crop production statistics) |
| `eurostat_production` | Eurostat ETL (EU crop production, humidity-normalized) |
| `growing_season` | Derived from GHCN TMIN (frost dates, frost-free days, hard-freeze) |
| `photoperiod_zones` | Computed from latitude (day length, photoperiod class) |
| `soilgrids` | SoilGrids API (pH, clay, sand, silt, SOC, texture class) |

**Species coverage (25+):** wheat, barley, rye, oat, triticale, timothy, meadow fescue, perennial ryegrass, festulolium, apple, cherry, peach, plum, apricot, pear, grape, haskap, blueberry, black currant, red currant, gooseberry, strawberry, raspberry, lingonberry, cloudberry, saskatoon berry, sea buckthorn, arctic kiwi, red clover, alfalfa

**New in v2 expansion:**
- Forage grasses (timothy, meadow fescue, perennial ryegrass, festulolium: 20 varieties, 12 markers)
- Russian/Soviet cereal varieties (Bezostaya 1, Chulpan, Mironovskaya 808, etc.)
- Iceland/Faroe cultivars (Skalinn, Hrafn, Visir, etc.)
- Scottish/UK winter cereals (Glasgow, Belenus, KWS Lili, Optic)
- Stone fruits (plum: Toka, Waneta, Superior; apricot: Scout, Harlayne)
- Currants/gooseberry (Consort, Ben Tirran, Ojebyn, Hinnomaki Red, Pixwell)
- Saskatoon berry (Thiessen, Smoky, Northline, Martin, JB30)
- Cold-climate grapes (Frontenac Gris, Brianna, Louise Swenson, St. Croix, Mars)
- Baltic cultivars (Estonian, Latvian, Lithuanian varieties)
- AFP/IRI antifreeze protein genes (TaAFP, ScAFP, LpAFP, DcAFP)
- ICE/MYB transcription factor regulators (TaICE1, HvICE1, VvMYB44, etc.)
- 50 breeding programs worldwide
- 60 rootstock compatibility entries
- 50 snow mold/disease resistance entries
- 40 field trial sites (Norway to Japan)

**Source:** [Horticulture_Open-Source_Genomics.md](../../docs/Horticulture_Open-Source_Genomics.md)
