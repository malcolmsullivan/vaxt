"""Deterministic grader — no model call, every check is a structural or SQL fact.

This is the crown jewel's safety layer: it decides whether an Ask VAXT answer is
grounded by checking, against the warehouse, that every citation resolves and that
the answer is anchored to the known-correct row(s) for the question. Because it
needs no API key it runs on every PR and cannot be flaky.
"""

import json

import duckdb

from vaxt_agent.provenance import resolve_citation


def load_golden(path) -> list[dict]:
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _emitted(transcript: dict) -> list[tuple[str, str]]:
    return [
        (str(cit.get("table", "")), str(cit.get("key", "")))
        for claim in transcript.get("claims", []) or []
        for cit in (claim.get("citations", []) or [])
    ]


def _gold_check(golden: dict, emitted: list[tuple[str, str]]) -> bool:
    emitted_ci = {(t.lower(), k.lower()) for t, k in emitted}
    emitted_tables = {t.lower() for t, _ in emitted}
    if golden.get("gold_citations"):
        gold = {(g["table"].lower(), str(g["key"]).lower()) for g in golden["gold_citations"]}
        return len(gold & emitted_ci) >= 1
    if golden.get("must_include_tables"):
        required = {t.lower() for t in golden["must_include_tables"]}
        return required <= emitted_tables
    return True  # no anchor specified -> correctness not asserted here


def grade_item(transcript: dict, golden: dict, con: duckdb.DuckDBPyConnection) -> dict:
    """Grade one transcript against its golden item. Returns per-check detail."""
    kind = golden["kind"]
    emitted = _emitted(transcript)
    checks: dict[str, bool] = {}

    if kind == "refusal":
        checks["refused"] = bool(transcript.get("refused"))
        checks["no_citations"] = len(emitted) == 0
    elif kind == "answerable":
        claims = transcript.get("claims", []) or []
        checks["not_refused"] = not transcript.get("refused", False)
        checks["has_answer"] = bool((transcript.get("answer") or "").strip())
        checks["every_claim_cited"] = bool(claims) and all(
            len(c.get("citations", []) or []) >= 1 for c in claims
        )
        checks["citations_resolve"] = bool(emitted) and all(
            resolve_citation(con, t, k) for t, k in emitted
        )
        checks["grounded_on_gold"] = _gold_check(golden, emitted)
    else:
        checks["known_kind"] = False

    return {
        "id": golden["id"],
        "kind": kind,
        "passed": all(checks.values()),
        "checks": checks,
        "emitted": emitted,
    }
