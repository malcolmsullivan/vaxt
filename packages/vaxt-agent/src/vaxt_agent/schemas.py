"""Typed shapes for Ask VAXT answers.

A `Citation` is the load-bearing object: `(table, key)` where `key` is the value
of that table's designated key column. Because every citation is a `(table, key)`
pair, the deterministic grader can resolve it against DuckDB with no model call —
a fabricated key returns zero rows and fails. That is what makes hallucination a
detectable event rather than a judgment call.
"""

from pydantic import BaseModel, Field


class Citation(BaseModel):
    table: str = Field(description="Warehouse table the fact came from.")
    key: str = Field(description="Value of that table's key column for the cited row.")


class Claim(BaseModel):
    text: str = Field(description="One factual sentence from the answer.")
    citations: list[Citation] = Field(
        default_factory=list,
        description="The record(s) that back this claim.",
    )


class ToolCall(BaseModel):
    tool: str
    arguments: dict = Field(default_factory=dict)
    record_count: int = 0
    error: str | None = None


class Transcript(BaseModel):
    question: str
    answer: str = ""
    # Authoritative flat list of citations parsed from the answer.
    citations: list[Citation] = Field(default_factory=list)
    # Cited sentences, for display/structure (each carries its own citations).
    claims: list[Claim] = Field(default_factory=list)
    refused: bool = False
    refusal_reason: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str = ""
    usage: dict = Field(default_factory=dict)
    # True when the model produced no usable answer at all.
    unstructured: bool = False

    def all_citations(self) -> list[Citation]:
        return list(self.citations)
