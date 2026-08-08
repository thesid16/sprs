#!/usr/bin/env bash
# =============================================================================
# mutation_watchdog.sh — supervisor for the large-N mutation campaign.
#
#   ./mutation_watchdog.sh start | status | stop
#
# WHY THIS EXISTS
#   The invariance table carries one row per leaf-count class and two mutation
#   columns. The first campaign covered ten classes (N = 8 .. 512); the six
#   large ones (1024, 1500, 2048, 3000, 4096, 8192) were left empty and showed
#   up as \todo{--} in the generated table. This fills them.
#
# SURVIVAL
#   setsid-detached, restarts on crash, and --merge means a restart never
#   redoes a leaf class that already has data -- important here, because a
#   single N=8192 elaboration is expensive.
# =============================================================================
set -uo pipefail

BASE="${SPRS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
OUT="$BASE/data/_mutation_results.json"
LOG="$BASE/mutation_watchdog.log"
PIDF="$BASE/.mutation_watchdog.pid"

ts()      { date '+%Y-%m-%d %H:%M:%S'; }
covered() { python3 -c "import json;print(len(json.load(open('$OUT'))['by_N']))" 2>/dev/null || echo 0; }

supervise() {
  echo "[$(ts)] === mutation supervisor up (pid $$) ===" >>"$LOG"
  local a=0
  while :; do
    a=$((a+1))
    echo "[$(ts)] --- attempt $a ($(covered)/16 leaf classes covered) ---" >>"$LOG"
    cd "$BASE" || exit 1
    python3 -u "$BASE/_mutation_runner.py" --merge --sample 2 \
            --jobs 3 --timeout 43200 --out "$OUT" >>"$LOG" 2>&1
    rc=$?
    if [[ $rc -eq 0 ]]; then
      echo "[$(ts)] finished cleanly ($(covered)/16 covered)" >>"$LOG"; break
    fi
    if [[ $a -ge 10 ]]; then
      echo "[$(ts)] giving up after $a attempts (rc=$rc)" >>"$LOG"; break
    fi
    echo "[$(ts)] rc=$rc — relaunching in 60s (merge skips covered classes)" >>"$LOG"
    sleep 60
  done
  rm -f "$PIDF"
}

case "${1:-status}" in
  start)
    if [[ -f "$PIDF" ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      echo "already running (pid $(cat "$PIDF"))"; exit 1
    fi
    setsid nohup "$0" __supervise </dev/null >>"$LOG" 2>&1 &
    echo $! >"$PIDF"; sleep 2
    echo "mutation supervisor started (pid $(cat "$PIDF"))"
    echo "  log: $LOG"
    ;;
  __supervise) supervise ;;
  status)
    if [[ -f "$PIDF" ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
      echo "mutation supervisor RUNNING (pid $(cat "$PIDF"))"
    else echo "mutation supervisor NOT running"; fi
    echo "leaf classes covered: $(covered)/16"
    tail -2 "$LOG" 2>/dev/null | sed 's/^/  /'
    ;;
  stop)
    if [[ -f "$PIDF" ]]; then
      kill -9 -- "-$(ps -o pgid= -p "$(cat "$PIDF")" | tr -d ' ')" 2>/dev/null
      pkill -9 -f _mutation_runner 2>/dev/null
      rm -f "$PIDF"; echo "stopped"
    else echo "not running"; fi
    ;;
  *) echo "usage: $0 {start|status|stop}"; exit 1 ;;
esac
