#!/usr/bin/env bash
# =============================================================================
# rerun_autoresume.sh — keep the re-measurement alive across reboots, and
# finish the paper automatically once it completes.
#
# Installed as a @reboot crontab entry AND a every-15-minutes watchdog-watcher.
# Two failure modes it covers that the watchdog itself cannot:
#
#   1. Machine reboot. The watchdog is setsid-detached, so it survives logout
#      and SSH drops, but not a reboot. This box has rebooted mid-campaign
#      before and lost hours of work; @reboot restarts it, and because
#      progress is checkpointed in the output CSV, the restart resumes rather
#      than starting over.
#   2. Supervisor death (OOM-killer taking the parent, kill -9, etc.).
#      The 15-minute check notices the pid is gone with work outstanding and
#      brings it back.
#
# When all testbenches are settled it runs the completion hook once: regenerate
# every table and figure from the corrected data, rebuild the paper, and run
# the submission gate. A marker file makes that idempotent.
# =============================================================================
set -uo pipefail

BASE="${SPRS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PAPER="${SPRS_PAPER:-$BASE/paper/main}"
OUT="$BASE/data/results/live_hw_results_p1_maxpe.csv"
LOG="$BASE/rerun_autoresume.log"
DONE_MARK="$BASE/.rerun_finished"
TOTAL=2962

ts() { date '+%Y-%m-%d %H:%M:%S'; }

settled() {
  [[ -f "$OUT" ]] || { echo 0; return; }
  python3 - "$OUT" <<'PY' 2>/dev/null || echo 0
import csv,sys
csv.field_size_limit(sys.maxsize)
S={'OK_BYPASS','OK_BYPASS_REUSED','SIM_TB_TIMEOUT_BYPASS','SIM_FAIL_BYPASS','SIM_UNKNOWN_BYPASS'}
n=0
with open(sys.argv[1],newline='',encoding='utf-8',errors='replace') as f:
    for r in csv.reader(f):
        if len(r)>=7 and r[6] in S: n+=1
print(n)
PY
}

running() {
  local p
  p=$(cat "$BASE/.rerun_watchdog.pid" 2>/dev/null) || return 1
  [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null
}

n=$(settled)

# ---- completion: regenerate everything and gate the paper ----
if [[ "$n" -ge "$TOTAL" ]]; then
  if [[ ! -f "$DONE_MARK" ]]; then
    echo "[$(ts)] re-measurement COMPLETE ($n/$TOTAL) — finishing the paper" >>"$LOG"
    {
      cd "$PAPER" || exit 1
      echo "--- regenerating tables and figures from the corrected data ---"
      make tables 2>&1
      echo "--- rebuilding ---"
      make 2>&1 | tail -3
      echo "--- submission gate ---"
      make check 2>&1 | tail -6
    } >>"$LOG" 2>&1
    date +%s >"$DONE_MARK"
    echo "[$(ts)] completion hook finished" >>"$LOG"
  fi
  exit 0
fi

# ---- refresh the paper whenever new maxp_mod_fat data lands ----
# The completion hook below only fires when EVERYTHING is settled. maxp is a
# long tail, so regenerate incrementally: the moment the first testbench
# passes, instance coverage becomes 40/40 and the invariance table gains a
# third configuration at N=8192. Waiting for all 118 would leave that on the
# floor for days.
STAMP="$BASE/.maxp_lastcount"
cur=$(python3 - "$OUT" <<'PY2' 2>/dev/null || echo 0
import csv,sys
csv.field_size_limit(sys.maxsize)
n=0
with open(sys.argv[1],newline='',encoding='utf-8',errors='replace') as f:
    for r in csv.reader(f):
        if len(r)>=7 and r[0]=='maxp_mod_fat' and r[6]=='OK_BYPASS': n+=1
print(n)
PY2
)
prev=$(cat "$STAMP" 2>/dev/null || echo -1)
if [[ "${cur:-0}" -ne "${prev:-(-1)}" ]]; then
  echo "$cur" >"$STAMP"
  if [[ "${cur:-0}" -gt 0 ]]; then
    echo "[$(ts)] maxp_mod_fat passing count now $cur — refreshing paper" >>"$LOG"
    ( cd "$PAPER" && make tables && make ) >>"$LOG" 2>&1
    echo "[$(ts)] paper refreshed ($(cd "$PAPER" && make check >/dev/null 2>&1 && echo 'gate PASS' || echo 'gate FAIL'))" >>"$LOG"
  fi
fi

# ---- maxp_mod_fat runs under its own supervisor; revive it too ----
maxp_running() {
  local p
  p=$(cat "$BASE/.maxp_watchdog.pid" 2>/dev/null) || return 1
  [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null
}
maxp_settled=$(python3 - "$OUT" <<'PY2' 2>/dev/null || echo 0
import csv,sys
csv.field_size_limit(sys.maxsize)
S={'OK_BYPASS','OK_BYPASS_REUSED','SIM_TB_TIMEOUT_BYPASS','SIM_FAIL_BYPASS','SIM_UNKNOWN_BYPASS'}
n=0
with open(sys.argv[1],newline='',encoding='utf-8',errors='replace') as f:
    for r in csv.reader(f):
        if len(r)>=7 and r[0]=='maxp_mod_fat' and r[6] in S: n+=1
print(n)
PY2
)
if [[ "${maxp_settled:-0}" -lt 118 ]] && ! maxp_running; then
  echo "[$(ts)] maxp supervisor down at ${maxp_settled:-0}/118 — restarting" >>"$LOG"
  rm -f "$BASE/.maxp_watchdog.pid"
  "$BASE/maxp_watchdog.sh" start >>"$LOG" 2>&1
fi

# ---- not finished: make sure it is actually running ----
if running; then
  exit 0
fi

# The supervisor is gone but its worker children are NOT killed by its death:
# each xelab/xsim runs in its own process group. Restarting on top of them
# double-simulates every in-flight testbench, wasting hours and — at ~17 GB per
# max_mod_fat elaboration — risking OOM. Reap the orphans first.
orphans=$(ps -eo pid,cmd \
          | grep -E "unwrapped/lnx64\.o/(xelab|xsim|xvlog)|_bypass_runner\.py" \
          | grep -v grep | awk '{print $1}')
if [[ -n "$orphans" ]]; then
  echo "[$(ts)] reaping $(echo "$orphans" | wc -w) orphaned worker process(es)" >>"$LOG"
  for p in $orphans; do kill -9 "$p" 2>/dev/null; done
  sleep 5
fi

# Their scratch directories are dead weight and confuse a fresh start.
find "$BASE/data/results" -maxdepth 2 -type d -name 'work_bypass_*' -exec rm -rf {} + 2>/dev/null

echo "[$(ts)] watchdog not running with $n/$TOTAL settled — restarting" >>"$LOG"
rm -f "$BASE/.rerun_watchdog.pid"
"$BASE/rerun_watchdog.sh" start >>"$LOG" 2>&1
