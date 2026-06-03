"""Unit tests for VAXT DuckDB client."""

import os
import pytest

# Skip all tests if DuckDB not available
pytestmark = pytest.mark.skipif(
    not os.path.exists("data/datasets/heritage-grain/heritage-grain.duckdb"),
    reason="DuckDB not available",
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
        results = client.search_varieties(zone="3")
        assert len(results) > 0

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
