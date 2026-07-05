"""Live-MCP transport — the agent's tools routed through the real MCP server.

This calls the actual registered `@mcp.tool()` wrappers via `mcp.call_tool`
(arg handling, JSON envelope, and graceful error envelope all exercised) and reads
the `records` provenance array the SERVER now attaches (via vaxt_mcp.provenance).
So the "the agent calls the real MCP server" story is faithful, and the demo path
and the direct/eval path emit identical provenance — asserted by the conformance
test in tests/vaxt-agent/. Provenance is enriched once, at the data tier; this
transport no longer re-enriches (the server and ToolCore share one definition).

It runs the server in-process (`mcp.call_tool`), which exercises the true tool
layer with no subprocess/stdio flakiness. For the literal over-stdio deployment,
the server is registered with `claude mcp add vaxt -- python -m vaxt_mcp.server`.
"""

import asyncio
import json


from vaxt_mcp.server import mcp


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

        # The server attaches provenance at the data tier; read it, don't re-derive.
        records = parsed.get("records", []) if isinstance(parsed, dict) else []
        return {"tool": tool_name, "count": len(records), "records": records}
