"""`ask-vaxt "<question>"` — grounded, cited answers from the VAXT warehouse."""

import argparse
import logging
import sys

from vaxt_agent.agent import DEFAULT_MODEL, run_agent
from vaxt_agent.schemas import Transcript


def _build_toolcore(transport: str):
    if transport == "mcp":
        from vaxt_agent.mcp_transport import MCPTransport
        return MCPTransport()
    from vaxt_agent.tools import ToolCore
    return ToolCore()


def _render(t: Transcript) -> str:
    lines = [t.answer.strip() or "(no answer)"]
    if t.refused:
        lines.append(f"\n[refused] {t.refusal_reason}")
    cites = []
    seen = set()
    for c in t.all_citations():
        tag = f"[{c.table}:{c.key}]"
        if tag not in seen:
            seen.add(tag)
            cites.append(tag)
    if cites:
        lines.append("\nCitations:")
        lines.extend(f"  {c}" for c in cites)
    if t.tool_calls:
        used = ", ".join(f"{tc.tool}({tc.record_count})" for tc in t.tool_calls)
        lines.append(f"\nTools used: {used}")
    tok = t.usage
    if tok:
        lines.append(
            f"Model: {t.model} | tokens in/out: "
            f"{tok.get('input_tokens', 0)}/{tok.get('output_tokens', 0)}"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ask-vaxt", description="Ask VAXT a heritage-grain question.")
    p.add_argument("question", help="Natural-language question.")
    p.add_argument("--model", default=None, help=f"Claude model (default {DEFAULT_MODEL} or $VAXT_AGENT_MODEL).")
    p.add_argument("--transport", choices=["direct", "mcp"], default="direct",
                   help="How tools reach the data: direct (in-process VaxtClient) or mcp (live MCP tool layer).")
    p.add_argument("--json", action="store_true", help="Print the full Transcript as JSON.")
    p.add_argument("-v", "--verbose", action="store_true", help="Log tool calls to stderr.")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    core = _build_toolcore(args.transport)
    try:
        transcript = run_agent(args.question, toolcore=core, model=args.model)
    except Exception as e:  # most likely auth/connection on the model call
        name = type(e).__name__
        if "Authentication" in name or "PermissionDenied" in name:
            print("Error: the model call was rejected. Set ANTHROPIC_API_KEY (or run "
                  "`ant auth login`) and try again.", file=sys.stderr)
            return 2
        if "Connection" in name:
            print(f"Error: could not reach the model API ({e}).", file=sys.stderr)
            return 2
        print(f"Error: {name}: {e}", file=sys.stderr)
        return 1
    finally:
        core.close()

    if args.json:
        print(transcript.model_dump_json(indent=2))
    else:
        print(_render(transcript))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
