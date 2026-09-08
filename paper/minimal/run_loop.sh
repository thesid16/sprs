#!/usr/bin/env bash
# Outer loop. Safe to kill and re-launch at any moment: iterate.sh is atomic and
# LOOP_STATE.json is the cursor. Re-running this command always resumes correctly.
#   start/resume : setsid nohup bash /home/rohit/sprs-fix/paper_min/run_loop.sh > /dev/null 2>&1 & disown
#   stop         : touch /home/rohit/sprs-fix/paper_min/STOP
#   watch        : tail -f /home/rohit/sprs-fix/paper_min/loop.log
set -uo pipefail
M=/home/rohit/sprs-fix/paper_min
cd "$M" || exit 1
MAX=${MAX_ITER:-40}
STREAK=0
BROKEN=0
FAILS=0
START_EPOCH=$(date +%s)

while :; do
  [ -f STOP ] && { echo "STOP file present; exiting $(date -Is)" >> loop.log; exit 0; }
  IT=$(python3 -c "import json;print(json.load(open('LOOP_STATE.json'))['iteration'])")
  [ "$IT" -ge "$MAX" ] && { echo "reached MAX_ITER=$MAX $(date -Is)" >> loop.log; exit 0; }

  T0=$(date +%s)
  bash iterate.sh >> loop.log 2>&1
  IRC=$?
  DUR=$(( $(date +%s) - T0 ))
  if [ "$IRC" = "75" ]; then
    echo "  quota exhausted; sleeping 1200s then retrying iteration $IT" >> loop.log
    sleep 1200; continue
  fi
  # A real iteration reads a paper and edits LaTeX. Seconds means it did nothing.
  if [ "$DUR" -lt 30 ]; then
    FAILS=$((FAILS+1))
    echo "  iteration took ${DUR}s - too fast to be real (fail $FAILS/3)" >> loop.log
  else
    FAILS=0
  fi
  if [ "$FAILS" -ge 3 ]; then
    echo "HALT: three iterations completed implausibly fast; something is broken $(date -Is)" >> loop.log
    exit 1
  fi
  D="iterations/$(printf %03d "$IT")"
  PAGESNOW=$(pdfinfo main.pdf 2>/dev/null | awk '/^Pages/{print $2}')

  # Rate limit / quota: back off and retry the SAME iteration. iterate.sh reverts
  # any partial work, so nothing is lost and nothing is double-applied.
  if grep -qiE 'session limit|rate.?limit|429|usage limit' "$D/agent.log" 2>/dev/null; then
    NOW=$(python3 -c "import json;print(json.load(open('LOOP_STATE.json'))['iteration'])")
    if [ "$NOW" = "$IT" ]; then
      echo "  rate-limited on iteration $IT; sleeping 900s $(date -Is)" >> loop.log
      sleep 900; continue
    fi
  fi

  # Convergence: N CONSECUTIVE cold readers each finding nothing necessary. One
  # pass declaring completion is weak evidence; three independent cold reads
  # agreeing is strong, because none of them can see the others' conclusions.
  NEED=${CONVERGE_N:-3}
  # Objective no-op test: did main.tex actually change? This does not depend on how
  # the agent phrased its notes, which is far more reliable than grepping prose.
  if git diff --quiet "HEAD~2" "HEAD" -- main.tex 2>/dev/null; then
    STREAK=$((STREAK+1))
  else
    STREAK=0
  fi
  echo "  noop-streak=$STREAK/$NEED" >> loop.log
  if [ "$STREAK" -ge "$NEED" ]; then
    echo "CONVERGED: $NEED consecutive cold reads added nothing $(date -Is)" >> loop.log
    python3 - <<'PYX'
import json; s=json.load(open('LOOP_STATE.json')); s['phase']='CONVERGED'
json.dump(s,open('LOOP_STATE.json','w'),indent=1)
PYX
    exit 0
  fi

  # Guard: a build that stays broken means stop before damage accumulates.
  if [ "$PAGESNOW" = "null" ] || [ -z "$PAGESNOW" ]; then
    BROKEN=$((BROKEN+1))
  else
    BROKEN=0
  fi
  if [ "$BROKEN" -ge 2 ]; then
    echo "HALT: build produced no PDF twice running $(date -Is)" >> loop.log
    exit 1
  fi

  # Size is guidance, not a limit: warn past half the 35-page reference, never stop.
  if [ "$PAGESNOW" != "null" ] && [ -n "$PAGESNOW" ] && [ "$PAGESNOW" -gt 18 ] 2>/dev/null; then
    echo "  NOTE: $PAGESNOW pages, past half the reference - restoration bar should be high" >> loop.log
  fi

  sleep 10
done
