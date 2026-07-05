#!/usr/bin/env python3
"""VAXT plugin Stop hook — machine-verify the answer's citations, no model call.

After the assistant finishes a turn, this parses the final answer for `[table:key]`
citations and resolves each against the VAXT DuckDB warehouse using the SAME
`resolve_citation` the agent and eval grader use (imported from vaxt_mcp.provenance —
one definition, no duplication). It then surfaces a code-stamped verdict:

    VAXT grounding ✓  3/3 citations resolve against the warehouse.
    VAXT grounding ⚠  2/3 resolve — UNRESOLVED: [markers:FAKE]. Treat as unverified.

This is the plugin's enforcement checkpoint: it does not trust the model to have
cited honestly — a fabricated `[table:key]` resolves to zero rows and is flagged in
code the plugin owns. The grounding skill instructs the citation FORMAT; this hook
is what actually verifies it.

Discipline (all deliberate):
- **Flag-and-surface, never block.** Always exits 0 (a Stop hook that exits 2 loops,
  and there is no built-in loop guard). The verdict goes in `systemMessage`.
- **Fail soft-to-neutral, never false-green.** The transcript JSONL format is
  internal to Claude Code and changes between versions; if it can't be parsed, we
  fall back to a raw token scan of the transcript tail, and if THAT finds nothing we
  stay silent rather than ever printing a ✓ we didn't earn.
- **Quiet on non-VAXT turns.** No citations and no refusal -> no output.
"""

import json
import re
import sys
from pathlib import Path

# The plugin ships the repo, so the single-source provenance module and the
# committed warehouse are both under the plugin root (this file's grandparent).
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PLUGIN_ROOT / "packages" / "vaxt" / "src"))

_DB_PATH = _PLUGIN_ROOT / "data" / "datasets" / "heritage-grain" / "heritage-grain.duckdb"

# [table:key] — table is our snake_case identifier; key may be a comma list, e.g.
# [varieties:Norstar] or [markers:a,b]. Combined pairs are split on commas.
_CITE = re.compile(r"\[([a-z_][a-z0-9_]*):([^\]\[]+)\]")
_REFUSED = "[[REFUSED]]"


def _emit(system_message: str | None) -> None:
    """Exit 0 with an optional visible verdict; never block, never loop."""
    out: dict = {"hookSpecificOutput": {"hookEventName": "Stop"}}
    if system_message:
        out["systemMessage"] = system_message
    else:
        out["suppressOutput"] = True
    print(json.dumps(out))
    sys.exit(0)


def _last_assistant_text(transcript_path: str) -> str | None:
    """Best-effort extraction of the final assistant message text.

    The transcript entry format is internal to Claude Code and may change between
    versions, so this is defensive and returns None (not a guess) on any surprise.
    """
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "assistant":
            continue
        message = entry.get("message", entry)
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                b["text"] for b in content
                if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
            ]
            if parts:
                return "\n".join(parts)
        return None  # found the last assistant entry but couldn't read its text
    return None


def _raw_tail_scan(transcript_path: str, tail_lines: int = 40) -> str | None:
    """Format-independent fallback: scan the raw tail for [table:key] tokens.

    Used only when the structured parse fails (format drift). The tokens are the
    plugin's own contract, so they survive JSON structure changes; scoping to the
    tail keeps it close to the latest answer.
    """
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    return "\n".join(lines[-tail_lines:]) if lines else None


def _citations(text: str) -> list[tuple[str, str]]:
    cites: list[tuple[str, str]] = []
    for table, keyblob in _CITE.findall(text):
        for key in keyblob.split(","):
            key = key.strip()
            if key:
                cites.append((table, key))
    # De-dupe, preserve order.
    seen: set[tuple[str, str]] = set()
    unique: list[tuple[str, str]] = []
    for c in cites:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        _emit(None)  # can't read the hook input — stay silent, never false-green

    transcript_path = payload.get("transcript_path") if isinstance(payload, dict) else None
    if not transcript_path:
        _emit(None)

    text = _last_assistant_text(transcript_path)
    scanned_fallback = False
    if text is None:
        text = _raw_tail_scan(transcript_path)
        scanned_fallback = True
    if not text:
        _emit(None)

    cites = _citations(text)
    refused = _REFUSED in text

    if not cites:
        # Honest refusal is a positive grounding signal worth surfacing; a plain
        # non-VAXT turn is not.
        if refused and not scanned_fallback:
            _emit("VAXT grounding ✓  honest refusal — no citations to verify.")
        _emit(None)

    # Resolve every citation against the warehouse — the actual, deterministic check.
    try:
        import duckdb

        from vaxt_mcp.provenance import resolve_citation

        con = duckdb.connect(str(_DB_PATH), read_only=True)
        try:
            resolved = {c: resolve_citation(con, c[0], c[1]) for c in cites}
        finally:
            con.close()
    except Exception:  # noqa: BLE001 — verifier failure must never crash the session
        # Could not run the check (missing warehouse / import). Say so; never ✓.
        _emit("VAXT grounding: verifier could not run (warehouse or dependency unavailable); citations NOT checked.")

    ok = [c for c, good in resolved.items() if good]
    bad = [c for c, good in resolved.items() if not good]
    total = len(cites)

    if not bad:
        note = " (via raw transcript scan)" if scanned_fallback else ""
        _emit(f"VAXT grounding ✓  {len(ok)}/{total} citations resolve against the warehouse{note}.")
    else:
        unresolved = " ".join(f"[{t}:{k}]" for t, k in bad)
        _emit(
            f"VAXT grounding ⚠  {len(ok)}/{total} citations resolve. "
            f"UNRESOLVED: {unresolved} — a fabricated [table:key] resolves to zero rows; treat these as unverified."
        )


if __name__ == "__main__":
    main()
