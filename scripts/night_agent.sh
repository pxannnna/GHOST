#!/usr/bin/env bash
# Overnight agent loop (KICKOFF.md §7).
#
# Usage:  NIGHT_END="2026-11-08T07:00" scripts/night_agent.sh
# Runs `claude -p` repeatedly on branch night/agent until the queue is empty,
# NIGHT_END passes, or MAX_ITER is reached. Each iteration is one task.
# Keep the laptop awake:  caffeinate -dims &
set -u
cd "$(dirname "$0")/.."

NIGHT_END="${NIGHT_END:-}"          # ISO local time, e.g. 2026-11-08T07:00
MAX_ITER="${MAX_ITER:-40}"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-60}"
QUEUE="docs/NIGHT_QUEUE.md"
LOG="docs/NIGHT_LOG.md"

[ -f "$QUEUE" ] || { echo "missing $QUEUE (copy from docs/NIGHT_QUEUE.template.md)"; exit 1; }
git rev-parse --abbrev-ref HEAD | grep -q '^night/agent$' || { echo "checkout night/agent first"; exit 1; }
touch "$LOG"

read -r -d '' PROMPT <<'EOF'
You are the overnight agent for the Invisible Signals hackathon repo.
Read docs/KICKOFF.md section 7 and docs/NIGHT_QUEUE.md. Obey the Constraints
section of the queue without exception.

Do exactly ONE task: the first unchecked "- [ ] Txx" line in docs/NIGHT_QUEUE.md.
Steps:
1. Implement it. Match the existing code style. Python must stay 3.10-compatible.
2. Run `make test` (and the task's own script if it has one). Fix failures. If
   the same failure persists after two attempts, mark the task
   "- [ ] Txx BLOCKED: <one-line reason>" and stop.
3. If the task needs hardware, credentials, or a human decision, mark it
   "- [ ] Txx NEEDS-HUMAN: <reason>" and stop.
4. On success tick it "- [x] Txx", then `git add -A && git commit -m "night: Txx <summary>"`.
5. Append to docs/NIGHT_LOG.md: timestamp, task id, what changed (files), test result, anything a human must check in the morning. Three to five lines.
Never touch main, firmware/, requirements.txt, or raw files under data/.
If no unchecked task remains, print QUEUE_EMPTY and stop.
EOF

for i in $(seq 1 "$MAX_ITER"); do
  if [ -n "$NIGHT_END" ] && [ "$(date +%Y-%m-%dT%H:%M)" \> "$NIGHT_END" ]; then
    echo "NIGHT_END reached"; break
  fi
  if ! grep -q '^- \[ \] T[0-9]\+ *[^BN]' "$QUEUE" && ! grep -q '^- \[ \] T[0-9]\+$' "$QUEUE"; then
    echo "queue empty or all blocked"; break
  fi
  echo "=== iteration $i $(date) ===" | tee -a "$LOG"
  out=$(claude -p "$PROMPT" --permission-mode acceptEdits 2>&1 | tail -n 40)
  echo "$out" | tail -n 5
  echo "$out" | grep -q QUEUE_EMPTY && break
  sleep "$SLEEP_BETWEEN"
done
echo "night loop finished $(date)" | tee -a "$LOG"
