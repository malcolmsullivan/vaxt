"""Live-MCP transport — the agent's tools routed through the real MCP server.

This calls the actual registered `@mcp.tool()` wrappers via `mcp.call_tool`
(arg handling, JSON envelope, and graceful error envelope all exercised), then
feeds the result through the SAME `provenance.enrich` that ToolCore uses. So the
"the agent calls the real MCP server" story is faithful, and the demo path and
the direct/eval path emit identical provenance — asserted by the conformance
test in tests/vaxt-agent/.

It runs the server in-process (`mcp.call_tool`), which exercises the true tool
layer with no subprocess/stdio flakiness. For the literal over-stdio deployment,
the server is registered with `claude mcp add vaxt -- python -m vaxt_mcp.server`.
"""

import asyncio
import json

from vaxt_mcp.server import mcp

from vaxt_agent import provenance

_TOOL_PREFIX = "vaxt_"

# The key under which each list-returning wrapper nests its rows (mirrors
# server.py). Tools not listed here return a whole dict that already matches the
# VaxtClient result shape.
_ENVELOPE_KEY = {
    "vaxt_search_varieties": "varieties",
    "vaxt_compare_varieties": "varieties",
    "vaxt_get_growing_season": "stations",
    "vaxt_get_planting_calendar": "calendars",
    "vaxt_search_markers": "markers",
    "vaxt_search_qtl": "qtl",
    "vaxt_search_sourdough": "starters",
    "vaxt_search_seed_sources": "sources",
    "vaxt_get_disease_resistance": "records",
    "vaxt_get_distillery_grain_sources": "distilleries",
    "vaxt_get_rootstock_compatibility": "rootstocks",
    "vaxt_get_crop_wild_relatives": "species",
    "vaxt_search_community_projects": "projects",
    "vaxt_search_eppo_pathogens": "pathogens",
    "vaxt_get_journal_entries": "entries",
}


class MCPTransport:
    """Same interface as ToolCore, backed by the live MCP tool layer."""

    def close(self) -> None:  # symmetry with ToolCore
        pass

    def call(self, tool_name: str, args: dict) -> dict:
        try:
            out = asyncio.run(mcp.call_tool(tool_name, dict(args or {})))
        except Exception as e:
            return {"tool": tool_name, "error": str(e), "records": [], "count": 0}

        content = out[0] if isinstance(out, tuple) else out
        try:
            parsed = json.loads(content[0].text)
        except (AttributeError, IndexError, ValueError, TypeError) as e:
            return {"tool": tool_name, "error": f"bad tool output: {e}", "records": [], "count": 0}

        if isinstance(parsed, dict) and parsed.get("error"):
            return {"tool": tool_name, "error": parsed.get("message", "error"), "records": [], "count": 0}

        if tool_name == "vaxt_health_check":
            return {"tool": tool_name, "info": parsed, "records": [], "count": 0}

        method = tool_name[len(_TOOL_PREFIX):] if tool_name.startswith(_TOOL_PREFIX) else tool_name
        raw = self._raw_from_envelope(tool_name, parsed)
        records = provenance.enrich(method, raw)
        return {"tool": tool_name, "count": len(records), "records": records}

    @staticmethod
    def _raw_from_envelope(tool_name: str, parsed):
        key = _ENVELOPE_KEY.get(tool_name)
        if key is None:
            return parsed  # whole-dict tools already match the client shape
        if isinstance(parsed, dict):
            return parsed.get(key, [])
        return parsed  # e.g. match_varieties returned [] when nothing to match
