#!/usr/bin/env python3
"""Ask VAXT eval runner.

  replay  (no API key): grade the committed transcripts in eval/transcripts/
          against eval/golden.jsonl. Fails if any golden item has no transcript
          (coverage) or any check fails. This is the gate CI runs on every PR.

  live    (needs ANTHROPIC_API_KEY): run the agent for each golden question, save
          the transcripts, then grade them (optionally with the semantic judge).
          Use this to (re)generate the frozen transcripts.

Both modes fail loudly if the golden set is empty or the warehouse is missing —
there is no path where this reports success while checking nothing.
"""

import argparse
import json
import pathlib
import sys

import duckdb

from vaxt_mcp.client import _resolve_db_path
from vaxt_agent.grading import grade_item, load_golden

HERE = pathlib.Path(__file__).resolve().parent
GOLDEN = HERE / "golden.jsonl"
TRANSCRIPTS = HERE / "transcripts"


def _transcript_path(item_id: str) -> pathlib.Path:
    return TRANSCRIPTS / f"{item_id}.json"


def _generate_live(golden, model, only=None):
    from vaxt_agent.agent import run_agent
    TRANSCRIPTS.mkdir(exist_ok=True)
    for item in golden:
        if only and item["id"] not in only:
            continue
        print(f"  running {item['id']}: {item['question'][:60]}...", file=sys.stderr)
        t = run_agent(item["question"], model=model)
        _transcript_path(item["id"]).write_text(t.model_dump_json(indent=2), encoding="utf-8")


def _load_transcript(item_id: str):
    p = _transcript_path(item_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the Ask VAXT eval.")
    ap.add_argument("--mode", choices=["replay", "live"], default="replay")
    ap.add_argument("--model", default=None, help="Agent model for live mode.")
    ap.add_argument("--semantic", action="store_true", help="Also run the API-gated semantic judge (live only).")
    ap.add_argument("--only", default=None,
                    help="Comma-separated golden ids to (re)generate in live mode; others are kept.")
    args = ap.parse_args(argv)
    only = {s.strip() for s in args.only.split(",")} if args.only else None

    golden = load_golden(GOLDEN)
    if not golden:
        print("FATAL: golden set is empty — nothing to evaluate.", file=sys.stderr)
        return 2

    db_path = _resolve_db_path()
    if not pathlib.Path(db_path).exists():
        print(f"FATAL: warehouse not found at {db_path} — cannot resolve citations.", file=sys.stderr)
        return 2

    if args.mode == "live":
        n = len(only) if only else len(golden)
        print(f"Generating {n} transcript(s) (live)...", file=sys.stderr)
        _generate_live(golden, args.model, only=only)

    con = duckdb.connect(db_path, read_only=True)
    results, missing = [], []
    try:
        for item in golden:
            transcript = _load_transcript(item["id"])
            if transcript is None:
                missing.append(item["id"])
                continue
            results.append(grade_item(transcript, item, con))

        semantic = {}
        if args.mode == "live" and args.semantic:
            from vaxt_agent.judge import judge
            for item in golden:
                if item["kind"] != "answerable":
                    continue
                t = _load_transcript(item["id"])
                semantic[item["id"]] = judge(item["question"], t.get("answer", ""))
    finally:
        con.close()

    # --- report ---
    passed = sum(1 for r in results if r["passed"])
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        detail = "" if r["passed"] else "  <- " + ", ".join(
            k for k, v in r["checks"].items() if not v
        )
        print(f"[{mark}] {r['id']} ({r['kind']}){detail}")
        if not r["passed"]:
            print(f"        emitted citations: {r['emitted']}")
        if r["id"] in semantic:
            v = semantic[r["id"]]
            print(f"        semantic: {'ok' if v['correct'] else 'WRONG'} - {v['reason'][:80]}")

    for mid in missing:
        print(f"[MISSING] {mid} - no transcript in eval/transcripts/ (run --mode live)")

    total = len(golden)
    print(f"\n{passed}/{total} passed, {len(missing)} missing transcripts.")
    ok = (passed == total) and not missing
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
