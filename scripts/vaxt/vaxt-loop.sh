#!/bin/bash
# vaxt-loop.sh — Orchestrate VAXT Ralph Loop across fresh context windows
#
# Usage:
#   bash scripts/vaxt/vaxt-loop.sh
#
# How it works:
#   1. Reads handoff file at docs/sauce-technologies/vaxt/.vaxt-loop/handoff-next.md
#   2. Launches a fresh `claude` session with that prompt
#   3. When the session exits, checks if a new handoff file was written
#   4. If yes, loops. If no, stops.
#
# The Claude session is responsible for:
#   - Creating/updating the current Phase B guide in Notion
#   - Updating state.json and NOTION-KB-SPEC.md if needed
#   - Writing the NEXT handoff file before exiting (or deleting it when Phase B is complete)
#
# To stop the loop manually: Ctrl+C or let the session finish without writing a handoff file.

set -e

WORKSPACE="/workspace"
HANDOFF="$WORKSPACE/docs/sauce-technologies/vaxt/.vaxt-loop/handoff-next.md"
LOG="$WORKSPACE/docs/sauce-technologies/vaxt/.vaxt-loop/vaxt-loop.log"
STATE="$WORKSPACE/docs/sauce-technologies/vaxt/.vaxt-loop/state.json"

# Run a command in a new terminal. Waits for completion before returning.
# Prefers: tmux (if inside tmux) > gnome-terminal --wait > xterm > fallback (same terminal)
run_in_new_terminal() {
  local cmd="$1"
  local label="${2:-vaxt}"
  if [ -n "${TMUX:-}" ] && command -v tmux &>/dev/null; then
    local winid="vaxt-$$-$RANDOM"
    tmux new-window -n "$winid" "cd $WORKSPACE && $cmd; echo 'Session done. Closing in 3s...'; sleep 3; tmux kill-window 2>/dev/null || true"
    while tmux list-windows 2>/dev/null | grep -q "$winid"; do sleep 1; done
  elif command -v gnome-terminal &>/dev/null && [ -n "${DISPLAY:-}" ]; then
    gnome-terminal --wait -- bash -c "cd $WORKSPACE && $cmd"
  elif command -v xterm &>/dev/null && [ -n "${DISPLAY:-}" ]; then
    xterm -e "bash -c 'cd $WORKSPACE && $cmd'"
  else
    echo "(No tmux/gnome-terminal/xterm — running in same terminal. For new terminals: run inside tmux or install gnome-terminal)" | tee -a "$LOG"
    eval "$cmd"
  fi
}

cd "$WORKSPACE"

echo "========================================" | tee -a "$LOG"
echo "VAXT Ralph Loop Orchestrator" | tee -a "$LOG"
echo "Started: $(date -Iseconds)" | tee -a "$LOG"
echo "========================================" | tee -a "$LOG"

iteration=0

while [ -f "$HANDOFF" ]; do
  iteration=$((iteration + 1))

  # Extract current task from state.json if available
  task="unknown"
  if [ -f "$STATE" ]; then
    task=$(python3 -c "import json; print(json.load(open('$STATE')).get('current_task', 'unknown'))" 2>/dev/null || echo "unknown")
  fi

  echo "" | tee -a "$LOG"
  echo "--- Iteration $iteration: $task ---" | tee -a "$LOG"
  echo "Started: $(date -Iseconds)" | tee -a "$LOG"
  echo "Handoff file: $HANDOFF ($(wc -l < "$HANDOFF") lines)" | tee -a "$LOG"
  echo "Spawning new terminal for Claude session..." | tee -a "$LOG"

  run_in_new_terminal 'claude "$(cat '"$HANDOFF"')" 2>&1 | tee -a '"$LOG" "$task"

  exit_code=0
  echo "Session exited with code: $exit_code" | tee -a "$LOG"
  echo "Ended: $(date -Iseconds)" | tee -a "$LOG"

  sleep 3

  if [ ! -f "$HANDOFF" ]; then
    echo "" | tee -a "$LOG"
    echo "No handoff file found. Loop complete." | tee -a "$LOG"
    break
  fi

  echo "Next handoff file detected. Continuing loop..." | tee -a "$LOG"
done

echo "" | tee -a "$LOG"
echo "========================================" | tee -a "$LOG"
echo "VAXT Ralph Loop finished after $iteration iteration(s)" | tee -a "$LOG"
echo "Ended: $(date -Iseconds)" | tee -a "$LOG"
echo "========================================" | tee -a "$LOG"
