"""The Ask VAXT agent loop.

A manual tool-use loop (not the SDK's beta tool_runner) so every tool call and
token count is observable, and so the loop can be driven by a stub client in
tests with no API. The model runs data tools until it calls `submit_answer`,
whose validated input becomes the Transcript.
"""

import json
import logging
import os

from vaxt_agent.prompt import SYSTEM_PROMPT
from vaxt_agent.schemas import Citation, Claim, ToolCall, Transcript
from vaxt_agent.tools import ToolCore, all_tool_schemas

DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 4096
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
                text = _text_of(blocks)
                log.info("agent finished without submit_answer (unstructured)")
                return Transcript(
                    question=question, answer=text, unstructured=True,
                    tool_calls=tool_calls, model=model, usage=usage,
                )

            submit = next((b for b in tool_uses if b.name == "submit_answer"), None)
            if submit is not None:
                return _finalize(question, submit.input, tool_calls, model, usage)

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

        log.warning("agent hit max_iters=%d without submit_answer", max_iters)
        return Transcript(
            question=question, answer="(agent did not converge on an answer)",
            unstructured=True, tool_calls=tool_calls, model=model, usage=usage,
        )
    finally:
        if owns_core:
            core.close()


def _finalize(question, submit_input, tool_calls, model, usage) -> Transcript:
    data = submit_input if isinstance(submit_input, dict) else {}
    claims = []
    for c in data.get("claims", []) or []:
        cites = [
            Citation(table=str(cit.get("table", "")), key=str(cit.get("key", "")))
            for cit in (c.get("citations") or [])
            if isinstance(cit, dict)
        ]
        claims.append(Claim(text=str(c.get("text", "")), citations=cites))
    return Transcript(
        question=question,
        answer=str(data.get("answer", "")),
        claims=claims,
        refused=bool(data.get("refused", False)),
        refusal_reason=str(data.get("refusal_reason", "")),
        tool_calls=tool_calls,
        model=model,
        usage=usage,
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
