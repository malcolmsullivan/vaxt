"""Semantic judge — API-gated secondary check (runs only in live eval).

The deterministic grader already proves grounding without a model. This adds a
second, independent signal — "does the answer text actually address the
question" — judged by a DIFFERENT model (Opus 4.8) than the agent (Sonnet 5), to
avoid correlated blind spots. Forced through a `verdict` tool so the output is
structured on any SDK version.
"""

JUDGE_MODEL = "claude-opus-4-8"

_VERDICT_TOOL = {
    "name": "verdict",
    "description": "Record whether the answer addresses the question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "correct": {
                "type": "boolean",
                "description": "True if the answer specifically and correctly addresses the question.",
            },
            "reason": {"type": "string"},
        },
        "required": ["correct", "reason"],
    },
}

_SYSTEM = (
    "You are a strict grader for a heritage-grain question-answering system. Judge "
    "ONLY whether the answer specifically and correctly addresses the question. Do "
    "not judge citations or formatting. A vague, evasive, or off-topic answer is "
    "incorrect; a correct refusal for an out-of-scope question is not being graded "
    "here."
)


def judge(question: str, answer: str, *, model: str = JUDGE_MODEL, client=None) -> dict:
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=512,
        system=_SYSTEM,
        tools=[_VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "verdict"},
        messages=[{
            "role": "user",
            "content": f"Question:\n{question}\n\nAnswer:\n{answer}",
        }],
    )
    for b in resp.content:
        if getattr(b, "type", None) == "tool_use" and b.name == "verdict":
            return {"correct": bool(b.input.get("correct")), "reason": str(b.input.get("reason", ""))}
    return {"correct": False, "reason": "no verdict returned"}
