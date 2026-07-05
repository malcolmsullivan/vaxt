"""ToolCore — the single execution path the agent's tools run through.

Schemas are lifted from the canonical FastMCP server (so the model sees exactly
the documented 21-tool surface), but execution is in-process against VaxtClient
and every result is enriched with provenance. The live-MCP transport
(mcp_transport.py) reuses this same ToolCore, so the demo path and the eval path
can never diverge in what a tool returns.
"""

import asyncio
import functools

from vaxt_mcp import provenance
from vaxt_mcp.client import VaxtClient
from vaxt_mcp.server import mcp

_TOOL_PREFIX = "vaxt_"

# Tools registered on the MCP server that are NOT part of the agent's data-read
# surface. `vaxt_verify_citation` is a grounding primitive for plain MCP/plugin
# sessions (self-checking a [table:key]); the agent's answers are graded by the
# deterministic grader instead, so it keeps its unchanged 21 data tools.
_NON_DATA_TOOLS = frozenset({"vaxt_verify_citation"})


@functools.lru_cache(maxsize=1)
def data_tool_schemas() -> tuple:
    """The 21 VAXT data-tool schemas, lifted from the FastMCP server (cached).

    Excludes non-data tools (see _NON_DATA_TOOLS) so the agent's surface stays the
    documented 21 read tools.
    """
    tools = asyncio.run(mcp.list_tools())
    return tuple(
        {
            "name": t.name,
            "description": (t.description or "").strip(),
            "input_schema": t.inputSchema,
        }
        for t in tools
        if t.name not in _NON_DATA_TOOLS
    )


def all_tool_schemas() -> list:
    """The 21 VAXT data tools (the agent answers in prose with inline citations)."""
    return [dict(s) for s in data_tool_schemas()]


class ToolCore:
    """Runs VAXT tools in-process and returns provenance-tagged envelopes."""

    def __init__(self, client: VaxtClient | None = None):
        self._client = client or VaxtClient()

    def close(self) -> None:
        self._client.close()

    def call(self, tool_name: str, args: dict) -> dict:
        """Execute one tool call. Returns an envelope, never raises."""
        method = self._method_for(tool_name)
        if method is None or not hasattr(self._client, method):
            return {"tool": tool_name, "error": f"unknown tool {tool_name!r}", "records": [], "count": 0}
        try:
            kwargs = self._coerce_args(method, args or {})
            raw = getattr(self._client, method)(**kwargs)
        except Exception as e:  # tool failures degrade to an error envelope
            return {"tool": tool_name, "error": str(e), "records": [], "count": 0}

        if method == "health_check":
            return {"tool": tool_name, "info": raw, "records": [], "count": 0}

        records = provenance.enrich(method, raw)
        return {"tool": tool_name, "count": len(records), "records": records}

    @staticmethod
    def _method_for(tool_name: str) -> str | None:
        if not tool_name.startswith(_TOOL_PREFIX):
            return None
        return tool_name[len(_TOOL_PREFIX):]

    @staticmethod
    def _coerce_args(method: str, args: dict) -> dict:
        """Mirror the MCP wrappers' comma-separated-string -> list handling."""
        args = dict(args)
        if method == "search_varieties" and isinstance(args.get("traits"), str):
            args["traits"] = [t.strip() for t in args["traits"].split(",") if t.strip()] or None
        if method == "compare_varieties" and isinstance(args.get("names"), str):
            args["names"] = [n.strip() for n in args["names"].split(",") if n.strip()]
        return args
