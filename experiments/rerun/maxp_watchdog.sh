#!/usr/bin/env bash
# =============================================================================
# maxp_watchdog.sh — dedicated supervisor for maxp_mod_fat (8192 leaves x
# 4096 GPUs, fat-tree), the one instance the campaign never completed.
#
#   ./maxp_watchdog.sh start | status | stop | log
#
# WHY A SEPARATE SUPERVISOR
#   rerun_watchdog.sh runs its phases sequentially, and a single pathological
#   testbench that never reaches a settled state can be retried up to 20 times
#   ahead of this work. maxp_mod_fat is the highest-value remaining result --
#   one passing testbench takes instance coverage from 39/40 to 40/40 and turns
#   the N=8192 invariance row into a three-configuration reshape -- so it gets
#   its own supervisor and starts immediately.
#
# WHY IT SHOULD SUCCEED THIS TIME
#   Five earlier attempts each burned ~12 h and died at the 8 h cap. The logs
#   show they were emitting [NOCTRC] packet traces the whole time: one $display
#   per packet per router, across 4096 routers. Those traces are now compile-
#   gated behind `ifdef NOC_TRACE (off by default), verified cycle-identical on
#   five reference testbenches spanning five topologies. The cap is also raised
#   from 8 h to 12 h and elaboration gets 6 threads instead of 2.
#
# ORDERING
#   The worklist is sorted by simulated makespan ascending (40 .. 80,048), so
#   the cheapest results land first. If the campaign is cut short, what is on
#   disk is still the most useful subset rather than an arbitrary one.
#
# SAFETY
#   * setsid: survives logout, SSH drop, terminal close.
#   * Checkpointed in the output CSV; a restart skips settled work.
#   * 4 workers: peak RSS ~280 GB against 503 GB installed, leaving headroom
#     for the other supervisor still finishing its last testbench.
#   * Writes to the same corrected-metric CSV as the main re-measurement, so
#     all cycle data lives in one place. The original CSV is never touched.
# =============================================================================
set -uo pipefail

BASE="${SPRS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
OUT="$BASE/data/results/live_hw_results_p1_maxpe.csv"
LIST=/tmp/rerun_phaseC.json
LOG="$BASE/maxp_watchdog.log"
PIDF="$BASE/.maxp_watchdog.pid"
RUNNER="$BASE/_bypass_runner.py"
JOBS=4
TIMEOUT=43200          # 12 h; the 8 h cap defeated every earlier attempt
MT=6                   # elaboration threads per worker (4 x 6 = 24 of 72)

ts() { date '+%Y-%m-%d %H:%M:%S'; }

done_count() {
  [[ -f "$OUT" ]] || { echo 0; return; }
  python3 - "$OUT" <<'PY' 2>/dev/null || echo 0
import csv,sys
csv.field_size_limit(sys.maxsize)
S={'OK_BYPASS','OK_BYPASS_REUSED','SIM_TB_TIMEOUT_BYPASS','SIM_FAIL_BYPASS','SIM_UNKNOWN_BYPASS'}
n=0
with open(sys.argv[1],newline='',encoding='utf-8',errors='replace') as f:
    for r in csv.reader(f):
        if len(r)>=7 and r[0]=='maxp_mod_fat' and r[6] in S: n+=1
print(n)
PY
}

total() { python3 -c "import json;print(len(json.load(open('$LIST'))))" 2>/dev/null || echo 118; }

supervise() {
  echo "[$(ts)] === maxp supervisor up (pid $$), $JOBS workers, cap ${TIMEOUT}s, -mt $MT ===" >>"$LOG"
  [[ -f "$BASE/.maxp_start" ]] || date +%s >"$BASE/.maxp_start"
  local attempt=0
  while :; do
    attempt=$((attempt+1))
    echo "[$(ts)] --- attempt $attempt ($(done_count)/$(total) settled) ---" >>"$LOG"
    XELAB_MT="$MT" python3 -u "$RUNNER" --jobs "$JOBS" --timeout "$TIMEOUT" \
            --tb-list-json "$LIST" --out-csv "$OUT" >>"$LOG" 2>&1
    rc=$?
    [[ $rc -eq 0 ]] && { echo "[$(ts)] finished cleanly" >>"$LOG"; break; }
    if [[ $attempt -ge 15 ]]; then
      echo "[$(ts)] giving up after $attempt attempts (rc=$rc)" >>"$LOG"; break
    fi
    echo "[$(ts)] exited rc=$rc — relaunching in 60s (resumes from CSV)" >>"$LOG"
    sleep 60
  done
  echo "[$(ts)] === maxp done: $(done_count)/$(total) ===" >>"$LOG"
  rm -f "$PIDF"
}

case "${1:-status}" in
  start)
    if [[ -f "$PIDF" ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      echo "already running (pid $(cat "$PIDF"))"; exit 1
    fi
    [[ -f "$LIST" ]] || { echo "missing worklist $LIST"; exit 1; }
    setsid nohup "$0" __supervise </dev/null >>"$LOG" 2>&1 &
    echo $! >"$PIDF"; sleep 2
    echo "maxp supervisor started (pid $(cat "$PIDF"))"
    echo "  log:    $LOG"
    echo "  status: $0 status"
    ;;
  __supervise) supervise ;;
  status)
    if [[ -f "$PIDF" ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      echo "maxp supervisor RUNNING (pid $(cat "$PIDF"))"
    else echo "maxp supervisor NOT running"; fi
    d=$(done_count); t=$(total)
    echo "maxp_mod_fat: $d / $t settled"
    if [[ -f "$BASE/.maxp_start" ]]; then
      python3 - "$OUT" "$d" "$t" "$BASE/.maxp_start" "$JOBS" <<'PY'
import csv,sys,time
csv.field_size_limit(sys.maxsize)
out,d,t,sf,jobs=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),sys.argv[4],int(sys.argv[5])
el=max(1.0,time.time()-float(open(sf).read().strip()))
sim=[]; passes=0
with open(out,newline='',encoding='utf-8',errors='replace') as f:
    for r in csv.reader(f):
        if len(r)>=7 and r[0]=='maxp_mod_fat':
            if r[6]=='OK_BYPASS': passes+=1
            try: sim.append(float(r[5]))
            except: pass
print(f"elapsed {el/3600:.1f}h   passing {passes}")
if sim:
    per=sum(sim[-8:])/len(sim[-8:])
    print(f"recent mean {per/60:.0f} min/TB")
    if d<t: print(f"ETA ~{(t-d)*per/jobs/3600:.1f}h for the remaining {t-d}")
if passes: print(">>> instance coverage is now 40/40 <<<")
PY
    fi
    tail -2 "$LOG" 2>/dev/null | sed 's/^/  /'
    ;;
  stop)
    if [[ -f "$PIDF" ]]; then
      p=$(cat "$PIDF"); kill -9 -- "-$(ps -o pgid= -p "$p" | tr -d ' ')" 2>/dev/null
      pkill -9 -f "_bypass_runner.py.*phaseC" 2>/dev/null
      rm -f "$PIDF"; echo "stopped (progress checkpointed; 'start' resumes)"
    else echo "not running"; fi
    ;;
  log) tail -f "$LOG" ;;
  *) echo "usage: $0 {start|status|stop|log}"; exit 1 ;;
esac
