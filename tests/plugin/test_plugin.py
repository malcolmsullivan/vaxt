"""Plugin scaffolding + the enforcing Stop hook.

Covers: the marketplace/plugin manifests are well-formed and pinned to the plugin
root (never a floating remote); the grounding skill has not drifted from the
canonical SYSTEM_PROMPT contract; and the Stop hook deterministically flags a
fabricated citation while never blocking the session.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_HOOK_DB = REPO / "data" / "datasets" / "heritage-grain" / "heritage-grain.duckdb"


def _load(rel: str) -> dict:
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


def test_marketplace_manifest_valid():
    m = _load(".claude-plugin/marketplace.json")
    assert m["name"] == "vaxt"
    assert m["owner"]["name"]
    assert any(p["name"] == "vaxt" and p["source"] == "./" for p in m["plugins"])


def test_plugin_manifest_valid_and_pinned():
    p = _load(".claude-plugin/plugin.json")
    assert p["name"] == "vaxt"
    # MCP server is pinned to the installed plugin root — never a floating remote.
    srv = p["mcpServers"]["vaxt"]
    assert srv["command"] == "uvx"
    assert any("${CLAUDE_PLUGIN_ROOT}" in a for a in srv["args"])
    # The enforcing Stop hook is wired.
    hook = p["hooks"]["Stop"][0]["hooks"][0]
    assert hook["type"] == "command"
    assert "verify_citations.py" in hook["command"]


def test_skill_has_not_drifted_from_canonical_contract():
    from vaxt_agent.prompt import SYSTEM_PROMPT  # the single canonical source

    skill = (REPO / "skills" / "vaxt-grounding" / "SKILL.md").read_text(encoding="utf-8")
    for phrase in ("[table:key]", "[[REFUSED]]", "never a confident guess"):
        assert phrase in SYSTEM_PROMPT, f"canonical prompt lost invariant: {phrase!r}"
        assert phrase in skill, f"skill drifted from canonical contract: {phrase!r}"


@pytest.mark.skipif(not _HOOK_DB.exists(), reason=f"warehouse missing at {_HOOK_DB}")
def test_stop_hook_flags_fabricated_and_never_blocks(tmp_path):
    tx = tmp_path / "transcript.jsonl"
    tx.write_text(
        '{"type":"user","message":{"content":"which varieties for zone 3?"}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text",'
        '"text":"Norstar is cold-hardy [varieties:Norstar]. A fake marker [markers:FAKE_XYZ] is not real."}]}}\n',
        encoding="utf-8",
    )
    payload = json.dumps({"transcript_path": str(tx), "hook_event_name": "Stop"})
    proc = subprocess.run(
        [sys.executable, str(REPO / "hooks" / "verify_citations.py")],
        input=payload, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr  # flag-and-surface, never block
    msg = json.loads(proc.stdout)["systemMessage"]
    assert "1/2" in msg
    assert "[markers:FAKE_XYZ]" in msg  # the fabricated citation is named


@pytest.mark.skipif(not _HOOK_DB.exists(), reason=f"warehouse missing at {_HOOK_DB}")
def test_stop_hook_silent_on_non_vaxt_turn(tmp_path):
    tx = tmp_path / "transcript.jsonl"
    tx.write_text(
        '{"type":"assistant","message":{"content":[{"type":"text","text":"Sure, here is a haiku."}]}}\n',
        encoding="utf-8",
    )
    payload = json.dumps({"transcript_path": str(tx), "hook_event_name": "Stop"})
    proc = subprocess.run(
        [sys.executable, str(REPO / "hooks" / "verify_citations.py")],
        input=payload, capture_output=True, text=True,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out.get("suppressOutput") is True
    assert "systemMessage" not in out
