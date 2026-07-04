"""Deterministic grader tests, driven by hand-authored transcripts.

No API key: the grader is pure logic + SQL resolution. These pin exactly which
answers pass and which fail, so the eval gate's meaning can't drift. The keys
used below are real rows in the committed warehouse.
"""

import os
import pathlib

import duckdb
import pytest

from vaxt_mcp.client import _resolve_db_path
from vaxt_agent.grading import grade_item, load_golden

pytestmark = pytest.mark.skipif(
    not os.path.exists(_resolve_db_path()),
    reason=f"DuckDB not available at {_resolve_db_path()}",
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN_FILE = REPO_ROOT / "eval" / "golden.jsonl"


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(_resolve_db_path(), read_only=True)
    yield c
    c.close()


def _claim(text, cites):
    return {"text": text, "citations": [{"table": t, "key": k} for t, k in cites]}


def _transcript(claims, refused=False, answer="An answer."):
    return {"answer": answer, "refused": refused, "refusal_reason": "", "claims": claims}


ANSWERABLE_GOLD = {"id": "t", "kind": "answerable", "gold_citations": [{"table": "varieties", "key": "Norstar"}]}
ANSWERABLE_TABLES = {"id": "t", "kind": "answerable", "must_include_tables": ["eppo_pathogens"]}
REFUSAL_GOLD = {"id": "t", "kind": "refusal"}


def test_grounded_answer_passes(con):
    t = _transcript([_claim("Norstar is winter wheat.", [("varieties", "Norstar")])])
    r = grade_item(t, ANSWERABLE_GOLD, con)
    assert r["passed"], r["checks"]


def test_hallucinated_citation_fails(con):
    t = _transcript([_claim("Bogus.", [("varieties", "NoSuchVariety_XYZ")])])
    r = grade_item(t, ANSWERABLE_GOLD, con)
    assert not r["passed"]
    assert r["checks"]["citations_resolve"] is False


def test_uncited_claim_fails(con):
    t = _transcript([
        _claim("Norstar is winter wheat.", [("varieties", "Norstar")]),
        _claim("It yields 8 tonnes per hectare.", []),  # unsupported
    ])
    r = grade_item(t, ANSWERABLE_GOLD, con)
    assert not r["passed"]
    assert r["checks"]["every_claim_cited"] is False


def test_answerable_but_refused_fails(con):
    t = _transcript([], refused=True)
    r = grade_item(t, ANSWERABLE_GOLD, con)
    assert not r["passed"]
    assert r["checks"]["not_refused"] is False


def test_resolving_but_wrong_anchor_fails(con):
    # Cites a real row, but not the gold anchor for this question.
    t = _transcript([_claim("Goodland is an apple.", [("varieties", "Goodland")])])
    r = grade_item(t, ANSWERABLE_GOLD, con)
    assert not r["passed"]
    assert r["checks"]["grounded_on_gold"] is False
    assert r["checks"]["citations_resolve"] is True  # it did resolve, just wrong row


def test_must_include_tables_pass_and_fail(con):
    ok = _transcript([_claim("Claviceps affects rye.", [("eppo_pathogens", "CLAVPU")])])
    assert grade_item(ok, ANSWERABLE_TABLES, con)["passed"]
    wrong = _transcript([_claim("Norstar is wheat.", [("varieties", "Norstar")])])
    r = grade_item(wrong, ANSWERABLE_TABLES, con)
    assert not r["passed"]
    assert r["checks"]["grounded_on_gold"] is False


def test_correct_refusal_passes(con):
    t = _transcript([], refused=True, answer="I don't have market prices.")
    assert grade_item(t, REFUSAL_GOLD, con)["passed"]


def test_refusal_with_citations_fails(con):
    t = _transcript([_claim("x", [("varieties", "Norstar")])], refused=True)
    r = grade_item(t, REFUSAL_GOLD, con)
    assert not r["passed"]
    assert r["checks"]["no_citations"] is False


def test_golden_set_is_well_formed():
    items = load_golden(GOLDEN_FILE)
    assert len(items) >= 15
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)), "duplicate golden ids"
    for i in items:
        assert i["kind"] in {"answerable", "refusal"}
        assert i["question"].strip()
        if i["kind"] == "answerable":
            assert i.get("gold_citations") or i.get("must_include_tables"), (
                f"{i['id']}: answerable item needs an anchor"
            )
