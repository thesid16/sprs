#!/usr/bin/env bash
# =============================================================================
# rerun_watchdog.sh — supervised, disconnect-proof re-measurement of HW cycles
# with the corrected max-over-PEs metric.
#
#   ./rerun_watchdog.sh start     detach and run (safe to close the terminal)
#   ./rerun_watchdog.sh status    progress, phase, ETA
#   ./rerun_watchdog.sh stop      stop the supervisor and its children
#   ./rerun_watchdog.sh log       follow the live log
#
# Design notes
#   * setsid + nohup: the supervisor is session-leader, so SIGHUP on disconnect
#     never reaches it. Survives logout, ssh drop, and terminal close.
#   * Checkpointing is the output CSV itself. _bypass_runner.py appends one row
#     per completed TB under a lock, and on start skips every (Instance,TB_Name)
#     already carrying a settled ErrorCode. Killing the run at any instant loses
#     at most the in-flight TBs.
#   * Crash recovery: if the runner exits non-zero (OOM-killer, xsim segfault,
#     machine reboot mid-phase) the supervisor waits and relaunches. Because the
#     runner resumes from the CSV, each relaunch strictly advances.
#   * Two phases with different worker counts: phase A is 34 light instances,
#     phase B is 4 giants at ~5-15 GB per elaboration.
#   * The original live_hw_results_p1_unified.csv is NEVER written to.
# =============================================================================
set -uo pipefail

BASE="${SPRS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
OUT="$BASE/data/results/live_hw_results_p1_maxpe.csv"
LOG="$BASE/rerun_watchdog.log"
PIDF="$BASE/.rerun_watchdog.pid"
RUNNER="$BASE/_bypass_runner.py"
TIMEOUT=28800                 # per-TB cap, same as the original campaign

# phase : worklist : workers   (workers sized so peak RSS stays well under 503 GB)
PHASES=(
  "A:/tmp/rerun_phaseA.json:32"
  "B:/tmp/rerun_phaseB.json:16"
  # Phase C: maxp_mod_fat (8192 leaves x 4096 GPUs, fat-tree) -- the one
  # instance the campaign never completed. Five prior attempts each burned
  # ~12 h and died at the 8 h cap while emitting [NOCTRC] packet traces; the
  # traces are now compile-gated (-d NOC_TRACE, off by default), which was
  # verified cycle-identical on five reference TBs across five topologies.
  # 5 workers keeps peak RSS near 350 GB against 503 GB installed.
  "C:/tmp/rerun_phaseC.json:5"
)
# Per-phase overrides. Phase C elaborates a 4096-node design, so it gets more
# elaboration threads (the box has 72) and a far longer cap than the 8 h that
# defeated every earlier attempt.
declare -A PHASE_TIMEOUT=( [C]=43200 )
declare -A PHASE_MT=( [C]=6 )

ts() { date '+%Y-%m-%d %H:%M:%S'; }

count_done() {   # settled rows currently in the output CSV
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

total_tbs() {
  python3 -c "import json,os;print(sum(len(json.load(open(p))) for p in ['/tmp/rerun_phaseA.json','/tmp/rerun_phaseB.json','/tmp/rerun_phaseC.json'] if os.path.exists(p)))" 2>/dev/null || echo 2962
}

supervise() {
  echo "[$(ts)] === watchdog up (pid $$) ===" >>"$LOG"
  echo "[$(ts)] output: $OUT" >>"$LOG"

  # Header on a fresh file. The resume scan ignores it: 'ErrorCode' is not a
  # settled code, so the header row is never mistaken for completed work.
  if [[ ! -f "$OUT" ]]; then
    echo "Instance,Pipeline,TB_Name,Pass,Cycles,SimTime_s,ErrorCode,Error,CyclesGPU0,PerfAllGPUs" >"$OUT"
    echo "[$(ts)] created $OUT with header" >>"$LOG"
  fi
  # Start marker for ETA. The CSV's own ctime is useless here: on Linux it is
  # the inode change time, which every append refreshes, so elapsed always
  # read as ~0.
  [[ -f "$BASE/.rerun_start" ]] || date +%s >"$BASE/.rerun_start"

  for spec in "${PHASES[@]}"; do
    IFS=: read -r ph list jobs <<<"$spec"
    [[ -f "$list" ]] || { echo "[$(ts)] MISSING worklist $list — skipping phase $ph" >>"$LOG"; continue; }

    local attempt=0
    while :; do
      attempt=$((attempt+1))
      local to="${PHASE_TIMEOUT[$ph]:-$TIMEOUT}" mt="${PHASE_MT[$ph]:-2}"
      echo "[$(ts)] --- phase $ph attempt $attempt ($jobs workers, cap ${to}s, -mt $mt) ---" >>"$LOG"
      XELAB_MT="$mt" python3 -u "$RUNNER" --jobs "$jobs" --timeout "$to" \
              --tb-list-json "$list" --out-csv "$OUT" >>"$LOG" 2>&1
      rc=$?
      if [[ $rc -eq 0 ]]; then
        echo "[$(ts)] phase $ph finished cleanly" >>"$LOG"
        break
      fi
      # Non-zero: crash, OOM, or kill. Resume advances, so retry — but cap it
      # so a deterministically-failing phase cannot spin forever.
      if [[ $attempt -ge 20 ]]; then
        echo "[$(ts)] phase $ph FAILED rc=$rc after $attempt attempts — giving up" >>"$LOG"
        break
      fi
      echo "[$(ts)] phase $ph exited rc=$rc — relaunching in 60s (resumes from CSV)" >>"$LOG"
      sleep 60
    done
  done

  echo "[$(ts)] === all phases done: $(count_done)/$(total_tbs) settled ===" >>"$LOG"
  rm -f "$PIDF"
}

case "${1:-status}" in
  start)
    if [[ -f "$PIDF" ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      echo "already running (pid $(cat "$PIDF")) — use 'status' or 'stop'"; exit 1
    fi
    [[ -f /tmp/rerun_phaseA.json ]] || python3 "$BASE/_rerun_worklist.py" --outdir /tmp
    setsid nohup "$0" __supervise </dev/null >>"$LOG" 2>&1 &
    echo $! >"$PIDF"
    sleep 2
    echo "watchdog started (pid $(cat "$PIDF"))"
    echo "  log:    $LOG"
    echo "  output: $OUT"
    echo "  safe to disconnect; check back with: $0 status"
    ;;
  __supervise) supervise ;;
  status)
    if [[ -f "$PIDF" ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      echo "watchdog RUNNING (pid $(cat "$PIDF"))"
    else
      echo "watchdog NOT running"
    fi
    d=$(count_done); t=$(total_tbs)
    echo "progress: $d / $t settled"
    if [[ -f "$OUT" && "$d" -gt 0 ]]; then
      python3 - "$OUT" "$d" "$t" "$BASE/.rerun_start" <<'PY'
import csv,sys,time,os
csv.field_size_limit(sys.maxsize)
out,d,t,startf=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),sys.argv[4]
try: start=float(open(startf).read().strip())
except Exception: start=os.path.getmtime(out)
el=max(1.0, time.time()-start)
# ETA from a TRAILING window, not the global average. Phase A (light
# instances) runs ~600 TB/h; phase B is giants at hours per TB, so a global
# rate extrapolates to a wildly optimistic finish once phase B starts.
sim=[]
with open(out,newline='',encoding='utf-8',errors='replace') as f:
    for r in csv.reader(f):
        if len(r)>=7 and r[6].startswith(('OK_BYPASS','SIM_')):
            try: sim.append(float(r[5]))
            except: pass
print(f"elapsed {el/3600:.1f}h  overall {d/(el/3600):.0f} TB/h")
if d>=t:
    print("COMPLETE")
elif len(sim)>=20:
    recent=sim[-20:]
    per=sum(recent)/len(recent)          # mean seconds per TB, recent work
    workers=int(os.environ.get("RERUN_WORKERS","16"))
    rem=(t-d)*per/max(1,workers)
    print(f"recent mean {per/60:.0f} min/TB  ->  ETA ~{rem/3600:.1f}h "
          f"for the remaining {t-d} (dominated by the giant instances)")
sim=[]
with open(out,newline='',encoding='utf-8',errors='replace') as f:
    for r in csv.reader(f):
        if len(r)>=7 and r[6]=='OK_BYPASS':
            try: sim.append(float(r[5]))
            except: pass
if sim: print(f"passing {len(sim)}  sim-time so far {sum(sim)/3600:.1f} core-h")
PY
      echo "last:"; tail -3 "$LOG" | sed 's/^/  /'
    fi
    ;;
  stop)
    if [[ -f "$PIDF" ]]; then
      pid=$(cat "$PIDF"); kill -- "-$(ps -o pgid= "$pid" | tr -d ' ')" 2>/dev/null
      pkill -f "_bypass_runner.py.*live_hw_results_p1_maxpe" 2>/dev/null
      rm -f "$PIDF"; echo "stopped (progress is checkpointed; 'start' resumes)"
    else echo "not running"; fi
    ;;
  log) tail -f "$LOG" ;;
  *) echo "usage: $0 {start|status|stop|log}"; exit 1 ;;
esac
