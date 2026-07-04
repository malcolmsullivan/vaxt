"""Unit tests for the inline-citation parser (no API, no DB)."""

from vaxt_agent.citations import build_claims, is_refusal, parse_citations, strip_tags


def _pairs(text):
    return [(c.table, c.key) for c in parse_citations(text)]


def test_single_citation():
    assert _pairs("Norstar is winter wheat [varieties:Norstar].") == [("varieties", "Norstar")]


def test_key_with_space_and_punctuation():
    assert _pairs("Accession [grin_accessions:PI 268210] traces origin.") == [
        ("grin_accessions", "PI 268210")
    ]


def test_multiple_citations_one_bracket():
    txt = "Sources include [seed_sources:SRC-030, seed_sources:SRC-015]."
    assert _pairs(txt) == [("seed_sources", "SRC-030"), ("seed_sources", "SRC-015")]


def test_bare_key_inherits_table():
    txt = "See [seed_sources:SRC-030, SRC-015, SRC-016]."
    assert _pairs(txt) == [
        ("seed_sources", "SRC-030"),
        ("seed_sources", "SRC-015"),
        ("seed_sources", "SRC-016"),
    ]


def test_dedup():
    assert _pairs("[varieties:Norstar] ... again [varieties:Norstar]") == [("varieties", "Norstar")]


def test_refusal_token_not_a_citation():
    assert is_refusal("No such data. [[REFUSED]]") is True
    assert _pairs("No such data. [[REFUSED]]") == []


def test_non_citation_brackets_ignored():
    assert _pairs("See reference [1] and [note].") == []


def test_build_claims_only_cited_sentences():
    txt = ("Here is context with no citation. Norstar is wheat [varieties:Norstar]. "
           "It resists mould [disease_resistance:Norstar].")
    claims = build_claims(txt)
    assert len(claims) == 2
    assert all(c.citations for c in claims)


def test_strip_tags_removes_citations_and_token():
    txt = "Norstar is wheat [varieties:Norstar]. No prices [[REFUSED]]."
    out = strip_tags(txt)
    assert "[" not in out and "REFUSED" not in out
    assert "Norstar is wheat." in out
