"""ToolCore — the single execution path the agent's tools run through.

Schemas are lifted from the canonical FastMCP server (so the model sees exactly
the documented 21-tool surface), but execution is in-process against VaxtClient
and every result is enriched with provenance. The live-MCP transport
(mcp_transport.py) reuses this same ToolCore, so the demo path and the eval path
can never diverge in what a tool returns.
"""

import asyncio
import functools

from vaxt_mcp.client import VaxtClient
from vaxt_mcp.server import mcp

from vaxt_agent import provenance

_TOOL_PREFIX = "vaxt_"

# The final-answer tool. Making the answer a tool call with a strict schema means
# "every claim carries a citation" is enforced structurally, not hoped for.
SUBMIT_ANSWER_TOOL = {
    "name": "submit_answer",
    "description": (
        "Submit your final answer. Call this exactly once, at the end. Every "
        "factual sentence must be a claim with at least one citation drawn from a "
        "record you actually retrieved. If the warehouse cannot answer the "
        "question, set refused=true, give a short refusal_reason, and provide no "
        "citations and no invented facts."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "The prose answer for the user.",
            },
            "claims": {
                "type": "array",
                "description": "One entry per factual sentence in the answer.",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "citations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "table": {"type": "string"},
                                    "key": {"type": "string"},
                                },
                                "required": ["table", "key"],
                            },
                        },
                    },
                    "required": ["text", "citations"],
                },
            },
            "refused": {"type": "boolean"},
            "refusal_reason": {"type": "string"},
        },
        "required": ["answer", "claims", "refused"],
    },
}


@functools.lru_cache(maxsize=1)
def data_tool_schemas() -> tuple:
    """The 21 VAXT tool schemas, lifted from the FastMCP server (cached)."""
    tools = asyncio.run(mcp.list_tools())
    return tuple(
        {
            "name": t.name,
            "description": (t.description or "").strip(),
            "input_schema": t.inputSchema,
        }
        for t in tools
    )


def all_tool_schemas() -> list:
    """Data tools + the submit_answer contract tool."""
    return [dict(s) for s in data_tool_schemas()] + [SUBMIT_ANSWER_TOOL]


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
