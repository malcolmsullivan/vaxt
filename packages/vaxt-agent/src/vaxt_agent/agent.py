"""The Ask VAXT agent loop.

A manual tool-use loop (not the SDK's beta tool_runner) so every tool call and
token count is observable, and so the loop can be driven by a stub client in
tests with no API. The model calls data tools until it answers in prose; the
answer's inline [table:key] citations are then parsed and verified.
"""

import json
import logging
import os

from vaxt_agent import citations as C
from vaxt_agent.prompt import SYSTEM_PROMPT
from vaxt_agent.schemas import ToolCall, Transcript
from vaxt_agent.tools import ToolCore, all_tool_schemas

DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 8192
MAX_ITERS = 8

log = logging.getLogger("vaxt_agent")


def run_agent(
    question: str,
    *,
    anthropic_client=None,
    toolcore: ToolCore | None = None,
    model: str | None = None,
    max_iters: int = MAX_ITERS,
    on_event=None,
) -> Transcript:
    """Answer `question`, grounded and cited. Never raises for tool failures.

    `anthropic_client` and `toolcore` are injectable for testing.
    """
    client = anthropic_client or _default_client()
    core = toolcore or ToolCore()
    owns_core = toolcore is None
    model = model or os.environ.get("VAXT_AGENT_MODEL", DEFAULT_MODEL)
    tools = all_tool_schemas()

    messages: list[dict] = [{"role": "user", "content": question}]
    tool_calls: list[ToolCall] = []
    usage: dict = {}

    try:
        for _ in range(max_iters):
            resp = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
            usage = _merge_usage(usage, getattr(resp, "usage", None))
            blocks = list(resp.content)
            messages.append({"role": "assistant", "content": resp.content})

            tool_uses = [b for b in blocks if getattr(b, "type", None) == "tool_use"]
            if not tool_uses:
                # The model answered in prose. Parse and verify its citations.
                return _finalize(question, _text_of(blocks), tool_calls, model, usage)

            results = []
            for b in tool_uses:
                env = core.call(b.name, dict(b.input or {}))
                tc = ToolCall(
                    tool=b.name, arguments=dict(b.input or {}),
                    record_count=int(env.get("count", 0)), error=env.get("error"),
                )
                tool_calls.append(tc)
                log.info("tool %s -> %d records%s", b.name, tc.record_count,
                         f" (error: {tc.error})" if tc.error else "")
                if on_event:
                    on_event(tc, env)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": json.dumps(env, default=str),
                })
            messages.append({"role": "user", "content": results})

        log.warning("agent hit max_iters=%d without a final answer", max_iters)
        return Transcript(
            question=question, answer="(agent did not converge on an answer)",
            unstructured=True, tool_calls=tool_calls, model=model, usage=usage,
        )
    finally:
        if owns_core:
            core.close()


def _finalize(question, answer_text, tool_calls, model, usage) -> Transcript:
    refused = C.is_refusal(answer_text)
    cites = [] if refused else C.parse_citations(answer_text)
    claims = [] if refused else C.build_claims(answer_text)
    display = C.strip_tags(answer_text)
    return Transcript(
        question=question,
        answer=display,
        citations=cites,
        claims=claims,
        refused=refused,
        refusal_reason=display if refused else "",
        tool_calls=tool_calls,
        model=model,
        usage=usage,
        unstructured=bool(answer_text.strip()) is False,
    )


def _text_of(blocks) -> str:
    return "\n".join(
        getattr(b, "text", "") for b in blocks if getattr(b, "type", None) == "text"
    ).strip()


def _merge_usage(acc: dict, u) -> dict:
    if u is None:
        return acc
    d = u if isinstance(u, dict) else {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
    }
    out = dict(acc)
    for k, v in d.items():
        if isinstance(v, int):
            out[k] = out.get(k, 0) + v
    return out


def _default_client():
    import anthropic
    return anthropic.Anthropic()
