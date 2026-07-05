"""Unit tests for VAXT DuckDB client."""

import os

import pytest

from vaxt_mcp.client import _resolve_db_path

# Skip all tests only if the warehouse the client would actually open is absent.
# Resolve via the client's own logic (honors VAXT_DUCKDB_PATH / WORKSPACE_ROOT / cwd)
# rather than a hardcoded relative path — a hardcoded path silently skipped the whole
# suite whenever pytest ran from a different cwd, so CI could be green while testing
# nothing. See tests/test_warehouse_guard.py for the CI fail-loud counterpart.
pytestmark = pytest.mark.skipif(
    not os.path.exists(_resolve_db_path()),
    reason=f"DuckDB not available at {_resolve_db_path()}",
)


@pytest.fixture
def client():
    from vaxt_mcp.client import VaxtClient
    c = VaxtClient()
    yield c
    c.close()


class TestHealthCheck:
    def test_returns_ok(self, client):
        result = client.health_check()
        assert result["status"] == "ok"
        assert result["tables"] >= 20

    def test_has_core_tables(self, client):
        result = client.health_check()
        counts = result["table_counts"]
        assert "varieties" in counts
        assert "markers" in counts
        assert "breeding_programs" in counts
        assert "sourdough_starters" in counts


class TestSearchVarieties:
    def test_search_by_crop(self, client):
        results = client.search_varieties(crop="wheat")
        assert len(results) > 0
        for v in results:
            assert "wheat" in v["crop"].lower()

    def test_search_by_zone(self, client):
        # Zones are range-encoded; a zone-3 query must return every variety whose
        # range contains 3 (e.g. "2-3", "3-5"), not only the bare-"3" rows.
        results = client.search_varieties(zone="3")
        assert len(results) > 0
        for v in results:
            lo, _, hi = v["usda_zone"].partition("-")
            assert int(lo) <= 3 <= (int(hi) if hi else int(lo))
        # Regression guard against a relapse to exact-string matching.
        assert any("-" in v["usda_zone"] for v in results)

    def test_search_by_country(self, client):
        results = client.search_varieties(country="Norway")
        assert len(results) > 0

    def test_search_by_traits(self, client):
        results = client.search_varieties(traits=["winterhardiness"])
        assert len(results) > 0

    def test_limit_works(self, client):
        results = client.search_varieties(limit=5)
        assert len(results) <= 5


class TestGetVariety:
    def test_existing_variety(self, client):
        result = client.get_variety("Norstar")
        assert result is not None
        assert result["variety"] == "Norstar"

    def test_nonexistent_variety(self, client):
        result = client.get_variety("DoesNotExist12345")
        assert result is None


class TestSourdough:
    def test_search_all(self, client):
        results = client.search_sourdough()
        assert len(results) > 0

    def test_search_by_grain(self, client):
        results = client.search_sourdough(grain_base="rye")
        assert len(results) > 0


class TestSeedSources:
    def test_search_all(self, client):
        results = client.search_seed_sources()
        assert len(results) > 0


class TestMarkers:
    def test_search_wheat_markers(self, client):
        results = client.search_markers(species="wheat")
        assert len(results) > 0

    def test_search_by_chromosome(self, client):
        results = client.search_markers(species="wheat", chromosome="5A")
        assert len(results) > 0


class TestPlantingCalendar:
    def test_search_by_zone(self, client):
        # Zones are stored as ranges like "3-4", "2-3"
        results = client.get_planting_calendar(zone="3-4")
        assert len(results) > 0

    def test_search_by_crop(self, client):
        results = client.get_planting_calendar(crop="wheat")
        assert len(results) > 0


class TestDiseaseResistance:
    def test_search_all(self, client):
        results = client.get_disease_resistance()
        assert len(results) > 0

    def test_search_by_variety(self, client):
        results = client.get_disease_resistance(variety="Norstar")
        assert len(results) > 0
        for r in results:
            assert "norstar" in r["variety_or_gene"].lower()

    def test_search_by_pathogen(self, client):
        results = client.get_disease_resistance(pathogen="Microdochium")
        assert len(results) > 0
        for r in results:
            assert "microdochium" in r["pathogen"].lower()

    def test_search_by_crop(self, client):
        results = client.get_disease_resistance(crop="winter wheat")
        assert len(results) > 0

    def test_search_by_resistance_level(self, client):
        results = client.get_disease_resistance(resistance_level="high")
        assert len(results) > 0

    def test_limit_works(self, client):
        results = client.get_disease_resistance(limit=3)
        assert len(results) <= 3


class TestDistilleryGrainSources:
    def test_search_all(self, client):
        results = client.get_distillery_grain_sources()
        assert len(results) > 0

    def test_search_by_country(self, client):
        results = client.get_distillery_grain_sources(country="Sweden")
        assert len(results) > 0
        for d in results:
            assert "sweden" in d["country"].lower()

    def test_search_by_spirit_type(self, client):
        results = client.get_distillery_grain_sources(spirit_type="rye")
        assert len(results) > 0

    def test_heritage_only(self, client):
        results = client.get_distillery_grain_sources(heritage_only=True)
        assert len(results) > 0
        for d in results:
            assert d["heritage_focus"] is True

    def test_limit_works(self, client):
        results = client.get_distillery_grain_sources(limit=2)
        assert len(results) <= 2


class TestRootstockCompatibility:
    def test_search_all(self, client):
        results = client.get_rootstock_compatibility()
        assert len(results) > 0

    def test_search_by_crop_group(self, client):
        results = client.get_rootstock_compatibility(crop_group="apple")
        assert len(results) > 0
        for r in results:
            assert "apple" in r["crop_group"].lower()

    def test_search_by_scion(self, client):
        results = client.get_rootstock_compatibility(scion="Honeycrisp")
        assert len(results) > 0

    def test_search_by_max_zone(self, client):
        results = client.get_rootstock_compatibility(max_zone=3)
        assert len(results) > 0
        for r in results:
            assert int(r["cold_hardiness_zone"]) <= 3

    def test_limit_works(self, client):
        results = client.get_rootstock_compatibility(limit=3)
        assert len(results) <= 3


class TestCropWildRelatives:
    def test_search_all(self, client):
        results = client.get_crop_wild_relatives()
        assert len(results) > 0

    def test_search_by_crop_group(self, client):
        results = client.get_crop_wild_relatives(crop_group="fruit")
        assert len(results) > 0
        for r in results:
            assert "fruit" in r["crop_group"].lower()

    def test_search_by_family(self, client):
        results = client.get_crop_wild_relatives(family="Rosaceae")
        assert len(results) > 0

    def test_search_by_max_zone(self, client):
        results = client.get_crop_wild_relatives(max_zone=2)
        assert len(results) > 0
        for r in results:
            assert int(r["usda_zone"]) <= 2

    def test_grin_only(self, client):
        results = client.get_crop_wild_relatives(grin_only=True)
        assert len(results) > 0
        for r in results:
            assert r["grin_available"].lower() == "yes"

    def test_limit_works(self, client):
        results = client.get_crop_wild_relatives(limit=3)
        assert len(results) <= 3


class TestCommunityProjects:
    def test_search_all(self, client):
        results = client.search_community_projects()
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_search_by_country(self, client):
        results = client.search_community_projects(country="Sweden")
        assert isinstance(results, list)
        for r in results:
            assert r["country"].lower() == "sweden"

    def test_search_by_crop(self, client):
        results = client.search_community_projects(crop="wheat")
        assert isinstance(results, list)
        for r in results:
            assert "wheat" in r["crops"].lower()

    def test_search_by_model(self, client):
        results = client.search_community_projects(model="co-op")
        assert isinstance(results, list)
        for r in results:
            assert r["model"].lower() == "co-op"

    def test_limit(self, client):
        results = client.search_community_projects(limit=3)
        assert len(results) <= 3


class TestEppoPathogens:
    def test_search_all(self, client):
        results = client.search_eppo_pathogens()
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_search_by_host_crop(self, client):
        results = client.search_eppo_pathogens(host_crop="wheat")
        assert isinstance(results, list)
        for r in results:
            assert "wheat" in r["host_crops"].lower()

    def test_search_by_type(self, client):
        results = client.search_eppo_pathogens(pathogen_type="fungus")
        assert isinstance(results, list)
        for r in results:
            assert r["pathogen_type"].lower() == "fungus"

    def test_search_by_severity(self, client):
        results = client.search_eppo_pathogens(severity="high")
        assert isinstance(results, list)
        for r in results:
            assert r["severity"].lower() == "high"

    def test_limit(self, client):
        results = client.search_eppo_pathogens(limit=5)
        assert len(results) <= 5


class TestJournalEntries:
    def test_returns_list_when_no_table(self, client):
        """Journal returns empty list gracefully when table doesn't exist."""
        results = client.get_journal_entries()
        assert isinstance(results, list)

    def test_variety_filter_no_crash(self, client):
        """Variety filter doesn't crash even without table."""
        results = client.get_journal_entries(variety="Norstar")
        assert isinstance(results, list)

    def test_location_filter_no_crash(self, client):
        results = client.get_journal_entries(location="Stockholm")
        assert isinstance(results, list)

    def test_season_filter_no_crash(self, client):
        results = client.get_journal_entries(season="2025")
        assert isinstance(results, list)


class TestCrossReference:
    def test_existing_variety(self, client):
        result = client.cross_reference("Norstar")
        assert result["variety"] == "Norstar"
        assert result["profile"] is not None
        assert isinstance(result["disease_resistance"], list)
        assert isinstance(result["cold_tolerance_markers"], list)
        assert isinstance(result["grin_accessions"], list)
        assert isinstance(result["seed_sources"], list)

    def test_nonexistent_variety(self, client):
        result = client.cross_reference("DoesNotExist12345")
        assert result["variety"] == "DoesNotExist12345"
        assert result["profile"] is None


class TestMatchVarieties:
    def test_by_zone_returns_recommendation_bundle(self, client):
        # usda_zone is range-encoded ('2-3', '3-5', …); a zone-3 grower should match
        # every variety whose range CONTAINS 3, not only the bare-"3" rows.
        result = client.match_varieties(zone="3")
        assert isinstance(result, dict)
        assert result["zone"] == "3"
        assert isinstance(result["varieties"], list)
        assert len(result["varieties"]) > 0
        assert isinstance(result["planting_calendars"], list)
        for v in result["varieties"]:
            lo, _, hi = v["usda_zone"].partition("-")
            assert int(lo) <= 3 <= (int(hi) if hi else int(lo)), \
                f"{v['variety']} zone {v['usda_zone']} does not contain 3"
        # Regression guard: the fix must surface ranged rows, not just bare "3".
        assert any("-" in v["usda_zone"] for v in result["varieties"])
        # And range-encoded planting calendars ('2-3', '3-4') must resolve too.
        assert len(result["planting_calendars"]) > 0

    def test_no_zone_and_no_coords_returns_empty(self, client):
        # Documented edge: with nothing to match on, match_varieties returns [].
        result = client.match_varieties()
        assert result == []

    def test_by_coords_estimates_zone(self, client):
        # Stockholm-ish; zone is estimated from nearest growing_season station.
        result = client.match_varieties(lat=59.3, lon=18.0)
        assert isinstance(result, dict)
        assert result["zone"]  # a non-empty estimated zone string
        assert isinstance(result["varieties"], list)

    def test_crop_filter(self, client):
        result = client.match_varieties(zone="3", crop="apple")
        assert isinstance(result, dict)
        for v in result["varieties"]:
            assert "apple" in v["crop"].lower()


class TestCompareVarieties:
    def test_two_varieties(self, client):
        results = client.compare_varieties(["Norstar", "Goodland"])
        assert isinstance(results, list)
        assert len(results) == 2
        names = {r["variety"] for r in results}
        assert names == {"Norstar", "Goodland"}

    def test_too_few_returns_empty(self, client):
        assert client.compare_varieties(["Norstar"]) == []

    def test_too_many_returns_empty(self, client):
        assert client.compare_varieties(["a", "b", "c", "d", "e", "f"]) == []


class TestGetGrowingSeason:
    def test_by_country(self, client):
        results = client.get_growing_season(country="Sweden")
        assert len(results) > 0
        for r in results:
            assert "sweden" in r["country_name"].lower()

    def test_by_station(self, client):
        results = client.get_growing_season(station="ABISKO")
        assert len(results) > 0
        for r in results:
            assert "abisko" in r["station_name"].lower()

    def test_limit_works(self, client):
        results = client.get_growing_season(limit=5)
        assert len(results) <= 5


class TestGetClimateProfile:
    def test_by_zone(self, client):
        result = client.get_climate_profile(zone="3")
        assert isinstance(result, dict)
        assert len(result["climate_zones"]) > 0
        for z in result["climate_zones"]:
            assert str(z["zone"]) == "3"

    def test_by_coords_adds_photoperiod_soil_sites(self, client):
        result = client.get_climate_profile(lat=59.3, lon=18.0)
        assert isinstance(result, dict)
        assert len(result["photoperiod_zones"]) > 0
        assert len(result["soil_profiles"]) > 0
        assert len(result["nearest_trial_sites"]) > 0

    def test_empty_when_no_args(self, client):
        assert client.get_climate_profile() == {}


class TestSearchQtl:
    def test_by_species_binomial(self, client):
        # graingenes_qtl.species holds binomials ("Hordeum vulgare"), not common
        # names — so "Hordeum" matches but "barley" would not.
        results = client.search_qtl(species="Hordeum")
        assert len(results) > 0
        for r in results:
            assert "hordeum" in r["species"].lower()

    def test_limit_works(self, client):
        results = client.search_qtl(limit=5)
        assert len(results) <= 5


class TestGetBreedingProgram:
    def test_by_program_id(self, client):
        result = client.get_breeding_program(program_id="BP001")
        assert result is not None
        assert result["program_id"] == "BP001"

    def test_by_institution(self, client):
        result = client.get_breeding_program(institution="CIMMYT")
        assert result is not None
        assert "cimmyt" in result["institution"].lower()

    def test_nonexistent(self, client):
        assert client.get_breeding_program(program_id="ZZZ999") is None
