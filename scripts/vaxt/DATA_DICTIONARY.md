# VAXT Data Dictionary

CSV datasets for the VAXT Heritage Grain Knowledge Base.

**License**: CC BY 4.0 — Attribution required.
**Attribution**: VAXT Heritage Grain Project (Sauce Technologies)
**Contact**: malcolm@vav-os.com

---

## Varieties Index

**File**: `nordic_variety_trait_index.csv`
**Records**: ~280
**Description**: Master index of heritage grain, fruit, and berry varieties with cold tolerance data.

| Column | Type | Description |
|--------|------|-------------|
| variety | text | Variety name (primary key) |
| crop | text | Crop type with qualifier (e.g. "wheat (winter)", "apple", "haskap") |
| program | text | Breeding program or institution of origin |
| country | text | Country of origin |
| traits | text | Semicolon-separated traits (winterhardiness, bread quality, etc.) |
| cold_tolerance_notes | text | Detailed cold tolerance characteristics |
| usda_zone | text | USDA hardiness zone (1-7) |
| source | text | Data source reference |

---

## Cold Tolerance Markers

**File**: `cold_tolerance_markers.csv`
**Records**: ~140
**Description**: Genomic markers for cold/frost tolerance in cereals.

| Column | Type | Description |
|--------|------|-------------|
| species | text | Species (wheat, rye, barley, oat) |
| locus | text | Genetic locus name (e.g. Fr-A1, Fr-A2) |
| chromosome | text | Chromosome location (e.g. 5A, 5B) |
| gene | text | Gene name (e.g. VRN1, TaCBF cluster) |
| marker | text | Marker name or type |
| marker_type | text | Type: operational, co-localized, functional, flanking, QTL |
| frost_tolerance_pct | text | Frost tolerance percentage range |
| notes | text | Mechanism and research notes |
| source | text | Publication or data source |

---

## Climate Zones

**File**: `climate_zones.csv`
**Records**: 16
**Description**: USDA hardiness zones with temperature ranges and example locations.

| Column | Type | Description |
|--------|------|-------------|
| zone | integer | USDA zone number (1-13) |
| subzone | text | Subzone (a or b) |
| min_temp_c | float | Minimum temperature (°C) |
| max_temp_c | float | Maximum temperature (°C) |
| example_locations | text | Example locations in this zone |
| relevance | text | Relevance to heritage grain growing |

---

## Breeding Programs

**File**: `breeding_programs.csv`
**Records**: ~83
**Description**: Global cold-climate plant breeding institutions (Nordic, Baltic, UK, Russia, Asia).

| Column | Type | Description |
|--------|------|-------------|
| program_id | text | Unique program ID (e.g. PROG-001) |
| institution | text | Institution name |
| country | text | Country |
| city | text | City |
| crops | text | Crop species covered |
| focus_areas | text | Research focus areas |
| notable_releases | text | Notable variety releases |
| established_year | integer | Year established |
| latitude | float | Latitude |
| longitude | float | Longitude |
| website | text | Institution website URL |
| source | text | Data source |

---

## Field Trial Sites

**File**: `field_trial_sites.csv`
**Records**: ~39
**Description**: Cold-climate field trial locations with climate data.

| Column | Type | Description |
|--------|------|-------------|
| site_id | text | Unique site ID (e.g. SITE-001) |
| name | text | Site name |
| institution | text | Managing institution |
| country | text | Country |
| latitude | float | Latitude |
| longitude | float | Longitude |
| elevation_m | integer | Elevation in meters |
| usda_zone | text | USDA hardiness zone |
| mean_jan_temp_c | float | Mean January temperature (°C) |
| record_low_c | float | Record low temperature (°C) |
| snow_cover_days | integer | Average annual snow cover days |
| trial_types | text | Types of trials conducted |
| crops_tested | text | Crops tested at this site |
| active | text | Whether site is currently active |
| source | text | Data source |

---

## GRIN Accessions

**File**: `grin_accessions.csv`
**Records**: ~68
**Description**: USDA GRIN germplasm bank accession references.

| Column | Type | Description |
|--------|------|-------------|
| pi_number | text | Plant Introduction number (e.g. PI 172382) |
| species | text | Botanical species name |
| common_name | text | Common name |
| crop_group | text | Crop group (cereal, fruit, forage) |
| origin_country | text | Country of origin |
| improvement_status | text | Status: landrace, cultivar, wild, breeding material |
| cold_hardiness_zone | text | Cold hardiness zone |
| collection_site | text | Original collection site |
| latitude | float | Latitude of collection site |
| longitude | float | Longitude of collection site |
| traits | text | Semicolon-separated key traits |
| notes | text | Historical and research notes |
| source | text | Data source (GRIN-Global NPGS) |

---

## Disease Resistance

**File**: `disease_resistance.csv`
**Records**: ~60
**Description**: Disease resistance profiles for cold-climate pathogens.

| Column | Type | Description |
|--------|------|-------------|
| variety_or_gene | text | Variety name or resistance gene |
| crop | text | Crop species |
| pathogen | text | Pathogen name (e.g. Microdochium nivale) |
| resistance_level | text | Level: high, moderate, low, susceptible |
| mechanism | text | Resistance mechanism |
| test_method | text | Testing methodology |
| region | text | Geographic region of testing |
| source | text | Research source |

---

## Planting Calendars

**File**: `planting_calendars.csv`
**Records**: ~79
**Description**: Sowing and harvest windows by hardiness zone and crop.

| Column | Type | Description |
|--------|------|-------------|
| calendar_id | text | Unique calendar ID |
| zone | text | USDA zone range (e.g. "3-4") |
| crop | text | Crop type |
| type | text | Winter or spring type |
| sow_start | text | Sowing window start (month) |
| sow_end | text | Sowing window end (month) |
| vernalization_weeks | text | Required vernalization period |
| expected_harvest | text | Expected harvest period |
| notes | text | Growing notes |

---

## Seed Sources

**File**: `seed_sources.csv`
**Records**: ~37
**Description**: Gene banks, heritage seed companies, and community exchanges.

| Column | Type | Description |
|--------|------|-------------|
| source_id | text | Unique source ID |
| name | text | Organization name |
| type | text | Type: gene_bank, heritage_seed_company, commercial_nordic, community |
| country | text | Country |
| website | text | Website URL |
| ships_to | text | Shipping regions |
| specialties | text | Specialty crops/varieties |
| access | text | Access requirements |
| notes | text | Additional notes |
| source | text | Data source |

---

## Sourdough Starters

**File**: `sourdough_starters.csv`
**Records**: ~35
**Description**: Historic and heritage sourdough cultures.

| Column | Type | Description |
|--------|------|-------------|
| starter_id | text | Unique starter ID (e.g. SS-001) |
| name | text | Starter name |
| origin_country | text | Country of origin |
| origin_city | text | City of origin |
| grain_base | text | Primary grain (wheat, rye, rice) |
| estimated_age_years | integer | Estimated age in years |
| culture_type | text | Culture type (mixed, wild, commercial) |
| flavor_profile | text | Flavor characteristics |
| preservation_method | text | How the culture is maintained |
| notes | text | Historical and cultural notes |
| source_bakery | text | Source bakery or reference |

---

## Sourdough Recipes

**File**: `sourdough_recipes.csv`
**Records**: ~10
**Description**: Recipes paired with specific sourdough starters.

| Column | Type | Description |
|--------|------|-------------|
| starter_id | text | Linked starter ID (matches sourdough_starters.csv) |
| recipe | text | Recipe name |
| hydration_pct | integer | Hydration percentage |
| flour_type | text | Flour type used |
| fermentation_schedule | text | Fermentation schedule details |
| serving_notes | text | Serving and pairing notes |
| source | text | Recipe source |

---

## Crop Wild Relatives

**File**: `crop_wild_relatives.csv`
**Records**: ~49
**Description**: Wild species with extreme cold tolerance for breeding use.

| Column | Type | Description |
|--------|------|-------------|
| species | text | Botanical species name |
| common_name | text | Common name |
| family | text | Plant family |
| crop_group | text | Crop group |
| domesticated_relative | text | Closest domesticated relative |
| min_survival_temp_c | float | Minimum survival temperature (°C) |
| native_range | text | Native geographic range |
| usda_zone | text | USDA hardiness zone |
| notes | text | Breeding potential and notes |
| source | text | Data source |

---

## Rootstock Compatibility

**File**: `rootstock_compatibility.csv`
**Records**: ~68
**Description**: Cold-hardy rootstocks for fruit trees and vines.

| Column | Type | Description |
|--------|------|-------------|
| rootstock | text | Rootstock name |
| rootstock_species | text | Botanical species |
| crop_group | text | Crop group (apple, cherry, grape) |
| compatible_scions | text | Compatible scion varieties |
| cold_hardiness_zone | text | USDA cold hardiness zone |
| trunk_hardiness_c | float | Trunk hardiness temperature (°C) |
| root_hardiness_c | float | Root hardiness temperature (°C) |
| dwarfing | text | Dwarfing effect |
| disease_notes | text | Disease resistance notes |
| source | text | Data source |

---

## Distillery Profiles

**File**: `distillery_profiles.csv`
**Records**: ~15
**Description**: Nordic and heritage grain distilleries.

| Column | Type | Description |
|--------|------|-------------|
| distillery_id | text | Unique distillery ID |
| name | text | Distillery name |
| country | text | Country |
| city | text | City |
| founded | integer | Year founded |
| spirit_type | text | Spirit type (whisky, aquavit, etc.) |
| heritage_focus | boolean | Whether they focus on heritage grains |
| malting | text | Malting method (floor malted, external, etc.) |
| latitude | float | Latitude |
| longitude | float | Longitude |
| website | text | Website URL |
| notes | text | Notes on heritage grain usage |
| source | text | Data source |

---

## Variety Growing Enrichment

**File**: `variety_growing_enrichment.csv`
**Records**: ~216
**Description**: Supplementary agronomic, malting, and milling data for varieties.

| Column | Type | Description |
|--------|------|-------------|
| variety | text | Variety name (matches varieties index) |
| seeding_rate | text | Recommended seeding rate |
| seeding_depth | text | Recommended seeding depth |
| seeding_window | text | Optimal sowing period |
| days_to_maturity | text | Days from sowing to harvest |
| row_spacing | text | Recommended row spacing |
| harvest_notes | text | Harvest timing and method notes |
| seed_sources | text | Where to obtain seed |
| grower_tips | text | Practical growing advice |
| bread_notes | text | Bread-making characteristics |
| malt_profile | text | Malting profile notes |
| falling_number | text | Falling number (seconds) |
| test_weight | text | Test weight (kg/hl) |
| sourdough_notes | text | Sourdough suitability notes |
| end_use | text | Semicolon-separated end uses |
| species | text | Botanical species name |
| malt_type | text | Malt type: base, specialty, crystal, roasted, distilling |
| modification | text | Modification level: low, medium, high, very_high |
| diastatic_power | text | Diastatic power range (°Lintner) |
| color_lovibond | text | Color range (°Lovibond) |
| extract_potential_pct | text | Extract potential percentage |
| kilning_notes | text | Kilning and malting process notes |
| flour_extraction_pct | text | Flour extraction percentage |
| ash_content_pct | text | Ash content percentage |
| gluten_strength | text | Gluten strength: weak, medium, strong, very_strong |
| water_absorption_pct | text | Water absorption percentage |
| ideal_stone_type | text | Recommended stone mill type |
| milling_notes | text | Milling characteristics and notes |

---

## Community Grain Projects

**File**: `community_grain_projects.csv`
**Records**: ~38
**Description**: Co-ops, seed commons, community mills, and grain CSAs focused on heritage grains.

| Column | Type | Description |
|--------|------|-------------|
| project_id | text | Unique project ID (e.g. CGP-001) |
| name | text | Project name |
| country | text | Country |
| city | text | City or town |
| latitude | float | Latitude |
| longitude | float | Longitude |
| crops | text | Semicolon-separated crop list |
| founded_year | integer | Year founded |
| members | integer | Number of members |
| hectares | float | Area under cultivation |
| model | text | Project model: co-op, seed_commons, csa, guild, community_garden, community_mill, grain_csa, seed_library, research_network |
| focus | text | Semicolon-separated focus areas: seed_saving, grain_growing, milling, baking, education, breeding, marketing, heritage_conservation |
| varieties_grown | text | Semicolon-separated variety names (cross-links to varieties index) |
| website | text | Website URL |
| notes | text | Project description and notes |
| source | text | Data source |

---

## EPPO Pathogens

**File**: `eppo_pathogens.csv`
**Records**: ~51
**Description**: Plant pathogens from the EPPO Global Database relevant to heritage grain and cold-climate crops.

| Column | Type | Description |
|--------|------|-------------|
| eppo_code | text | EPPO code (e.g. PUCCRT) |
| pathogen_name | text | Scientific name (e.g. Puccinia triticina) |
| common_name | text | Common disease name |
| host_crops | text | Semicolon-separated host crop list |
| pathogen_type | text | Type: fungus, bacteria, virus, oomycete, nematode, phytoplasma |
| geographic_range | text | Geographic distribution |
| severity | text | Severity: low, moderate, high, very_high |
| cold_climate_risk | text | Risk level in cold climates |
| management | text | Semicolon-separated management strategies |
| quarantine_eu | boolean | EU quarantine organism (true/false) |
| notes | text | Cold-climate and heritage grain relevance notes |
| source | text | Data source (gd.eppo.int) |

---

## Phenotype Template

**File**: `phenotype_template.csv`
**Records**: ~53
**Description**: Controlled-environment cold hardiness phenotype data.

| Column | Type | Description |
|--------|------|-------------|
| record_id | text | Unique record ID |
| trial_id | text | Trial identifier |
| genotype_name | text | Genotype/variety name |
| lt50_su_c | float | LT50 survival temperature (°C) |
| frost_test_min_temp_c | float | Minimum test temperature (°C) |
| additional columns | various | Trial-specific measurements |
