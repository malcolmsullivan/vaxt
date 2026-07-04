"""Parse inline citations out of a grounded answer.

The agent answers in prose and cites its sources inline as ``[table:key]`` right
after each factual statement. Parsing those (rather than forcing a structured
tool call) works with the model's natural output and is far more reliable. The
grounding guarantee is unchanged: every parsed ``[table:key]`` is resolved
against DuckDB, so a fabricated one still fails deterministically.
"""

import re

from vaxt_agent.schemas import Citation, Claim

# A citation bracket: [ ... ] with no nested brackets inside.
_BRACKET = re.compile(r"\[([^\[\]]+)\]")
# One "table:key" pair (key runs to the end of its comma-separated part).
_PAIR = re.compile(r"^([a-z][a-z0-9_]*):(.+)$")
# A bracket that begins with "table:" — used to strip citations for display.
_CITE_BRACKET = re.compile(r"\[[a-z][a-z0-9_]*:[^\[\]]*\]")
_REFUSAL_TOKEN = "[[REFUSED]]"
# Sentence-ish splitter: break on . ! ? or newline followed by space/newline.
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def is_refusal(text: str) -> bool:
    return _REFUSAL_TOKEN in (text or "")


def parse_citations(text: str) -> list[Citation]:
    """Parse [table:key] citations, tolerating several forms the model produces:

    [varieties:Norstar]                          -> one
    [seed_sources:SRC-030, seed_sources:SRC-015] -> two (comma-separated)
    [seed_sources:SRC-030, SRC-015]              -> two (2nd inherits the table)
    """
    seen = set()
    out = []
    for m in _BRACKET.finditer(text or ""):
        table = None
        for part in m.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            pair = _PAIR.match(part)
            if pair:
                table, key = pair.group(1), pair.group(2).strip()
            elif table:
                key = part  # bare key inherits the bracket's current table
            else:
                continue  # not a citation (e.g. [REFUSED], [1])
            if (table, key) not in seen:
                seen.add((table, key))
                out.append(Citation(table=table, key=key))
    return out


def build_claims(text: str) -> list[Claim]:
    """A claim is a sentence that carries at least one inline citation."""
    claims = []
    for sentence in _SENTENCE.split(text or ""):
        s = sentence.strip()
        if not s:
            continue
        cites = parse_citations(s)
        if cites:
            claims.append(Claim(text=strip_tags(s), citations=cites))
    return claims


def strip_tags(text: str) -> str:
    """Remove the inline [table:key] markers and the refusal token for display."""
    t = (text or "").replace(_REFUSAL_TOKEN, "")
    t = _CITE_BRACKET.sub("", t)
    # collapse the spaces/space-before-punctuation the removal leaves behind
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\s+([.,;:])", r"\1", t)
    return t.strip()
