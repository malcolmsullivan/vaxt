"""VAXT MCP Server — heritage grain research tools over DuckDB.

Run: python -m vaxt_mcp
Register: claude mcp add vaxt -- python -m vaxt_mcp.server
"""

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

from vaxt_mcp.client import VaxtClient

mcp = FastMCP("VAXT")
_client: VaxtClient | None = None


def _get_client() -> VaxtClient:
    global _client
    if _client is None:
        _client = VaxtClient()
    return _client


def _json(data) -> str:
    return json.dumps(data, indent=2, default=str)


def _error(e: Exception) -> str:
    return json.dumps({"error": True, "message": str(e)}, indent=2)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_health_check() -> str:
    """Check VAXT DuckDB status — table counts, data freshness, total rows."""
    try:
        return _json(_get_client().health_check())
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Variety Intelligence
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_search_varieties(
    crop: str = "",
    zone: str = "",
    country: str = "",
    traits: Optional[str] = None,
    limit: int = 25,
) -> str:
    """Search heritage grain varieties by crop, USDA zone, country, and/or traits.

    Args:
        crop: Filter by crop type (wheat, rye, barley, oat, apple, grape, etc.)
        zone: USDA hardiness zone (1-7)
        country: Country of origin (Norway, Sweden, Finland, Canada, USA, etc.)
        traits: Comma-separated traits (winterhardiness, drought tolerance, bread quality, etc.)
        limit: Max results (default 25)
    """
    try:
        trait_list = [t.strip() for t in traits.split(",") if t.strip()] if traits else None
        results = _get_client().search_varieties(
            crop=crop, zone=zone, country=country, traits=trait_list, limit=limit
        )
        return _json({"count": len(results), "varieties": results})
    except Exception as e:
        return _error(e)


@mcp.tool()
async def vaxt_get_variety(name: str) -> str:
    """Get full profile for a heritage variety — traits, growing data, disease resistance, cold markers.

    Args:
        name: Variety name (e.g. "Norstar", "Ölandsvete", "Dalarna")
    """
    try:
        result = _get_client().get_variety(name)
        if result is None:
            return _json({"error": True, "message": f"Variety '{name}' not found"})
        return _json(result)
    except Exception as e:
        return _error(e)


@mcp.tool()
async def vaxt_match_varieties(
    zone: str = "",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    crop: str = "",
    limit: int = 10,
) -> str:
    """Recommend varieties for a location/zone with planting windows.

    Args:
        zone: USDA hardiness zone (1-7). If empty, estimated from lat/lon.
        lat: Latitude (optional, used if zone not provided)
        lon: Longitude (optional, used if zone not provided)
        crop: Filter by crop type (optional)
        limit: Max variety results (default 10)
    """
    try:
        result = _get_client().match_varieties(
            zone=zone, lat=lat, lon=lon, crop=crop, limit=limit
        )
        return _json(result)
    except Exception as e:
        return _error(e)


@mcp.tool()
async def vaxt_compare_varieties(names: str) -> str:
    """Side-by-side comparison of 2-5 heritage varieties.

    Args:
        names: Comma-separated variety names (e.g. "Norstar,Dalarna,Ölandsvete")
    """
    try:
        name_list = [n.strip() for n in names.split(",") if n.strip()]
        if len(name_list) < 2 or len(name_list) > 5:
            return _json({"error": True, "message": "Provide 2-5 variety names"})
        results = _get_client().compare_varieties(name_list)
        return _json({"count": len(results), "varieties": results})
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Climate & Growing
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_get_growing_season(
    station: str = "",
    country: str = "",
    limit: int = 20,
) -> str:
    """Get frost-free days, frost dates, and minimum temperatures for weather stations.

    Args:
        station: Filter by station name (partial match)
        country: Filter by country name (Norway, Finland, Sweden, Canada, etc.)
        limit: Max results (default 20)
    """
    try:
        results = _get_client().get_growing_season(
            station=station, country=country, limit=limit
        )
        return _json({"count": len(results), "stations": results})
    except Exception as e:
        return _error(e)


@mcp.tool()
async def vaxt_get_climate_profile(
    zone: str = "",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> str:
    """Get climate zone, photoperiod, soil data, and nearest trial sites for a location.

    Args:
        zone: USDA hardiness zone (1-13)
        lat: Latitude (for photoperiod, soil, and nearest trial sites)
        lon: Longitude (for photoperiod, soil, and nearest trial sites)
    """
    try:
        result = _get_client().get_climate_profile(zone=zone, lat=lat, lon=lon)
        return _json(result)
    except Exception as e:
        return _error(e)


@mcp.tool()
async def vaxt_get_planting_calendar(zone: str = "", crop: str = "") -> str:
    """Get sowing windows by USDA zone and crop type.

    Args:
        zone: USDA hardiness zone (1-7)
        crop: Crop type (wheat, rye, barley, oat, etc.)
    """
    try:
        results = _get_client().get_planting_calendar(zone=zone, crop=crop)
        return _json({"count": len(results), "calendars": results})
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Genomics & Breeding
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_search_markers(
    species: str = "",
    chromosome: str = "",
    gene: str = "",
    limit: int = 50,
) -> str:
    """Search cold tolerance markers by species, chromosome, or gene.

    Args:
        species: Species (wheat, rye, barley, oat)
        chromosome: Chromosome name (e.g. "5A", "5B")
        gene: Gene name (partial match, e.g. "CBF", "VRN1")
        limit: Max results (default 50)
    """
    try:
        results = _get_client().search_markers(
            species=species, chromosome=chromosome, gene=gene, limit=limit
        )
        return _json({"count": len(results), "markers": results})
    except Exception as e:
        return _error(e)


@mcp.tool()
async def vaxt_search_qtl(
    species: str = "",
    trait: str = "",
    limit: int = 50,
) -> str:
    """Search GrainGenes QTL (Quantitative Trait Loci) by species and trait.

    Args:
        species: Species (wheat, barley, rye, oat)
        trait: Trait keyword (e.g. "frost", "cold", "vernalization")
        limit: Max results (default 50)
    """
    try:
        results = _get_client().search_qtl(species=species, trait=trait, limit=limit)
        return _json({"count": len(results), "qtl": results})
    except Exception as e:
        return _error(e)


@mcp.tool()
async def vaxt_get_breeding_program(
    program_id: str = "",
    institution: str = "",
) -> str:
    """Get breeding program details — institution, crops, focus areas, notable releases.

    Args:
        program_id: Program ID (e.g. "PROG-001")
        institution: Institution name (partial match, e.g. "Graminor", "NIBIO")
    """
    try:
        result = _get_client().get_breeding_program(
            program_id=program_id, institution=institution
        )
        if result is None:
            return _json({"error": True, "message": "Breeding program not found"})
        return _json(result)
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Culture & Sources
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_search_sourdough(
    grain_base: str = "",
    origin: str = "",
    culture_type: str = "",
    limit: int = 25,
) -> str:
    """Search sourdough starters with linked recipes — by grain base, origin, or culture type.

    Args:
        grain_base: Grain base (wheat, rye, rice, etc.)
        origin: Country of origin (Italy, USA, Finland, etc.)
        culture_type: Culture type (e.g. "mixed", "wild", "commercial")
        limit: Max results (default 25)
    """
    try:
        results = _get_client().search_sourdough(
            grain_base=grain_base, origin=origin, culture_type=culture_type, limit=limit
        )
        return _json({"count": len(results), "starters": results})
    except Exception as e:
        return _error(e)


@mcp.tool()
async def vaxt_search_seed_sources(
    crop: str = "",
    country: str = "",
    access_type: str = "",
    limit: int = 25,
) -> str:
    """Search seed sources — gene banks, heritage companies, community exchanges.

    Args:
        crop: Filter by crop/specialty (wheat, rye, apple, etc.)
        country: Filter by country (Sweden, Norway, USA, etc.)
        access_type: Filter by type (gene_bank, heritage_seed_company, community, etc.)
        limit: Max results (default 25)
    """
    try:
        results = _get_client().search_seed_sources(
            crop=crop, country=country, access_type=access_type, limit=limit
        )
        return _json({"count": len(results), "sources": results})
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Disease Resistance
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_get_disease_resistance(
    variety: str = "",
    pathogen: str = "",
    crop: str = "",
    resistance_level: str = "",
    limit: int = 50,
) -> str:
    """Search disease resistance records by variety/gene, pathogen, crop, or resistance level.

    Args:
        variety: Variety or gene name (e.g. "Norstar", "TaCBF14")
        pathogen: Pathogen species (e.g. "Microdochium nivale", "Typhula")
        crop: Host crop (e.g. "winter wheat", "rye", "timothy")
        resistance_level: Filter by level (e.g. "high", "moderate", "low")
        limit: Max results (default 50)
    """
    try:
        results = _get_client().get_disease_resistance(
            variety=variety, pathogen=pathogen, crop=crop,
            resistance_level=resistance_level, limit=limit,
        )
        return _json({"count": len(results), "records": results})
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Distillery Grain Sources
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_get_distillery_grain_sources(
    country: str = "",
    spirit_type: str = "",
    heritage_only: bool = False,
    limit: int = 25,
) -> str:
    """Search distilleries and their grain sources — by country, spirit type, or heritage focus.

    Args:
        country: Filter by country (Sweden, Finland, Norway, Denmark, Scotland, etc.)
        spirit_type: Filter by spirit (single malt, rye whiskey, gin, aquavit, etc.)
        heritage_only: If true, only return distilleries with heritage grain focus
        limit: Max results (default 25)
    """
    try:
        results = _get_client().get_distillery_grain_sources(
            country=country, spirit_type=spirit_type,
            heritage_only=heritage_only, limit=limit,
        )
        return _json({"count": len(results), "distilleries": results})
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Rootstock Compatibility
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_get_rootstock_compatibility(
    crop_group: str = "",
    scion: str = "",
    max_zone: Optional[int] = None,
    limit: int = 50,
) -> str:
    """Search rootstock compatibility — by crop group, scion cultivar, or cold hardiness zone.

    Args:
        crop_group: Crop group (apple, pear, cherry, plum)
        scion: Scion cultivar name (e.g. "Honeycrisp", "Gala", "Bartlett")
        max_zone: Maximum USDA zone (e.g. 3 returns zone 1-3 rootstocks)
        limit: Max results (default 50)
    """
    try:
        results = _get_client().get_rootstock_compatibility(
            crop_group=crop_group, scion=scion,
            max_zone=max_zone, limit=limit,
        )
        return _json({"count": len(results), "rootstocks": results})
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Crop Wild Relatives
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_get_crop_wild_relatives(
    crop_group: str = "",
    family: str = "",
    max_zone: Optional[int] = None,
    grin_only: bool = False,
    limit: int = 50,
) -> str:
    """Search crop wild relatives — wild species used in breeding for cold tolerance.

    Args:
        crop_group: Crop group (fruit, vine, berry, cereal, forage)
        family: Botanical family (Rosaceae, Vitaceae, Poaceae, etc.)
        max_zone: Maximum USDA zone (e.g. 2 returns zone 1-2 species)
        grin_only: If true, only return species available from USDA GRIN
        limit: Max results (default 50)
    """
    try:
        results = _get_client().get_crop_wild_relatives(
            crop_group=crop_group, family=family,
            max_zone=max_zone, grin_only=grin_only, limit=limit,
        )
        return _json({"count": len(results), "species": results})
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Community Grain Projects
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_search_community_projects(
    country: str | None = None,
    crop: str | None = None,
    model: str | None = None,
    min_members: int | None = None,
    limit: int = 25,
) -> str:
    """Search community grain projects — co-ops, seed commons, CSAs, community mills.

    Args:
        country: Filter by country (e.g. "Sweden", "UK")
        crop: Filter by crop grown (e.g. "wheat", "rye") — matches within semicolon-delimited list
        model: Filter by project model — co-op, seed_commons, csa, guild, community_garden, community_mill, grain_csa, seed_library, research_network
        min_members: Minimum member count
        limit: Max results (default 25)
    """
    try:
        results = _get_client().search_community_projects(
            country=country, crop=crop, model=model,
            min_members=min_members, limit=limit,
        )
        return _json({"count": len(results), "projects": results})
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# EPPO Pathogens
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_search_eppo_pathogens(
    host_crop: str | None = None,
    pathogen_type: str | None = None,
    severity: str | None = None,
    quarantine_eu: bool | None = None,
    limit: int = 25,
) -> str:
    """Search EPPO plant pathogens relevant to heritage grain and cold-climate crops.

    Args:
        host_crop: Filter by host crop (e.g. "wheat", "cherry") — matches within semicolon-delimited list
        pathogen_type: Filter by type — fungus, bacteria, virus, nematode, oomycete, phytoplasma
        severity: Filter by severity — low, moderate, high, very_high
        quarantine_eu: Filter by EU quarantine status (true/false)
        limit: Max results (default 25)
    """
    try:
        results = _get_client().search_eppo_pathogens(
            host_crop=host_crop, pathogen_type=pathogen_type,
            severity=severity, quarantine_eu=quarantine_eu, limit=limit,
        )
        return _json({"count": len(results), "pathogens": results})
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Grower's Journal
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_get_journal_entries(
    variety: str = "",
    location: str = "",
    season: str = "",
    limit: int = 25,
) -> str:
    """Search the Grower's Journal — crowdsourced field observations from Notion.

    Returns empty if journal has not been synced yet (run sync_grower_journal.py first).

    Args:
        variety: Filter by variety/cultivar name (partial match)
        location: Filter by location/site/garden (partial match)
        season: Filter by season/year (e.g. "2025", "spring")
        limit: Max results (default 25)
    """
    try:
        results = _get_client().get_journal_entries(
            variety=variety, location=location, season=season, limit=limit,
        )
        if not results:
            return _json({
                "count": 0,
                "entries": [],
                "note": "No entries found. Journal may not be synced yet — run: python3 scripts/vaxt/sync_grower_journal.py",
            })
        return _json({"count": len(results), "entries": results})
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Cross Reference
# ---------------------------------------------------------------------------
@mcp.tool()
async def vaxt_cross_reference(variety: str) -> str:
    """Cross-reference a variety across all VAXT tables — profile, markers, disease resistance, GRIN accessions, seed sources, and growing data.

    Args:
        variety: Variety name (e.g. "Norstar", "Ölandsvete", "Dalarna")
    """
    try:
        result = _get_client().cross_reference(variety)
        return _json(result)
    except Exception as e:
        return _error(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    mcp.run()
