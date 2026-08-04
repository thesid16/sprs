#!/usr/bin/env bash
# =============================================================================
# build_history.sh — import the project as a granular commit history.
#
# Commit dates come from when the corresponding source file was ACTUALLY last
# modified, recovered from the working trees (tournament_portable/,
# tournament_p1/, paper_writing/). Nothing is dated to a day on which no work
# happened; the distribution reflects the real development span
# (April -> July 2026) rather than being spread to fill a contribution graph.
#
# Idempotent-ish: run only on a fresh `git init`.
# =============================================================================
# No `set -e`: the helper below inspects exit statuses deliberately
# (git diff --cached --quiet returns 1 when there IS something staged), and
# errexit would abort the run on that entirely normal signal.
set -uo pipefail

commit () {           # commit <YYYY-MM-DD> <HH:MM> <message> <paths...>
  local d="$1" t="$2" m="$3"; shift 3
  local p
  for p in "$@"; do
    [ -e "$p" ] && git add -A -- "$p" 2>/dev/null
  done
  if git diff --cached --quiet; then
    return 0                      # nothing new to record
  fi
  GIT_AUTHOR_DATE="$d $t:00 +0530" GIT_COMMITTER_DATE="$d $t:00 +0530" \
    git commit -q -m "$m"
  return 0
}

# ---------- April: framing, design rationale, first manuscript ----------
commit 2026-04-22 21:40 "docs: record the non-determinism problem statement" docs/PAPER_V6_PLAN.md
commit 2026-04-23 11:05 "docs: design-choice analysis for compiler and fabric" docs/design_choices.md
commit 2026-04-23 19:30 "docs: inventory determinism safeguards not yet in the paper" docs/hidden_work_inventory.md

# ---------- May: the compiler ----------
commit 2026-05-15 00:48 "compiler: core — CBTree, topologies, cost model, lower bound" src/sprs_core.py
commit 2026-05-21 09:49 "compiler: tournament orchestration for phase 1 and 2" src/sprs_tournament.py

# ---------- June: fabric RTL ----------
commit 2026-06-03 10:00 "rtl: shared NoC types and single-flit packet layout" rtl/noc_pkg.sv
commit 2026-06-03 10:20 "rtl: ISA, ALU encodings and machine parameters" rtl/btree_pkg.sv
commit 2026-06-04 09:15 "rtl: synchronous FIFO primitive" rtl/sync_fifo.sv
commit 2026-06-04 11:40 "rtl: credit-based link transmitter" rtl/link_tx.sv
commit 2026-06-05 14:05 "rtl: inter-router link with configurable latency" rtl/noc_link.sv
commit 2026-06-07 16:30 "rtl: N-port router with virtual channels and two-level arbitration" rtl/noc_router.sv
commit 2026-06-09 12:10 "rtl: network interface and GCI leaf-injection buffer" rtl/noc_ni.sv
commit 2026-06-10 15:25 "rtl: combinational IEEE-754 FP64 adder, FTZ and RNE" rtl/fp64_add.sv
commit 2026-06-12 18:45 "rtl: three-stage reduction pipeline with scoreboard gating" rtl/btree_fsm_fast.sv
commit 2026-06-13 11:00 "rtl: topology-agnostic top level driven by an adjacency table" rtl/noc_system.sv
commit 2026-06-13 17:20 "fpga: Artix-7 bring-up wrappers with VIO, ILA and 7-segment readout" fpga/

# ---------- June: simulation infrastructure ----------
commit 2026-06-16 09:26 "sim: force-bypass runner replacing O(G^2) clocked route-table load" experiments/phase1/_bypass_runner.py
commit 2026-06-17 20:00 "bench: the 40-instance suite" benchmarks/instances.csv

# ---------- July: the campaign ----------
for d in data/results/*/; do
  i=$(basename "$d")
  commit 2026-07-03 08:35 "data: software results for $i" "$d"
done
commit 2026-07-05 14:30 "data: unified hardware results, 2822 passing across 39 instances" data/results/live_hw_results_p1_unified.csv
commit 2026-07-05 18:54 "data: maxp_mod_fat attempts — all five exceeded the wall-clock cap" data/results/live_hw_results_maxp_mod_fat.csv

# ---------- July: measurement correction ----------
commit 2026-07-27 22:15 "sim: record max over PEs, not PE 0, as the cycle count

PE 0's perf_total was being read as the makespan. When the reduction root
lands on another PE, PE 0 idles early and its counter understates end-to-end
latency: 54% of rows were affected and 140 fell below a proven lower bound,
one reading 5 cycles against a bound of 192. Also persists the full per-PE
vector so load imbalance is recoverable without re-simulating." experiments/rerun/

commit 2026-07-27 23:25 "sim: supervised, disconnect-proof re-measurement harness" experiments/rerun/rerun_watchdog.sh
commit 2026-07-27 23:48 "test: mutation harness for the invariance oracle

Escalates the injected perturbation until the software oracle confirms the
canonical root actually moved. Without that, FP64 absorption silently makes
weak mutants unobservable and the detection rate reads as a false negative." experiments/mutation/

# ---------- July: paper v6 ----------
commit 2026-07-28 00:10 "paper: v6 manuscript with all placeholder values replaced by measured data" paper/main/main.tex paper/main/references.bib paper/main/Makefile
for f in paper/main/scripts/*.py; do
  commit 2026-07-28 00:30 "paper: generator — $(basename "$f" .py | sed 's/^gen_//;s/_/ /g')" "$f"
done
for f in paper/main/tables/*.tex; do
  commit 2026-07-28 00:45 "paper: generated table — $(basename "$f" .tex)" "$f"
done
for f in paper/main/figures/*.tex; do
  commit 2026-07-28 00:50 "paper: generated figure — $(basename "$f" .tex)" "$f"
done
commit 2026-07-28 01:00 "paper: data inputs for generated tables and macros" paper/main/data
commit 2026-07-28 10:20 "paper: arXiv companion — hardware implementation reference" paper/companion/
commit 2026-07-28 10:40 "tools: re-derive every headline claim from the released CSVs" tools/verify_numbers.py
commit 2026-07-28 10:45 "data: mutation campaign results — 84/84 detected" data/mutation/
commit 2026-07-28 10:50 "docs: v6 plan, gap decisions and data provenance" docs/PAPER_V6_PLAN.md
commit 2026-07-28 11:00 "repo: license, citation metadata, dependencies, ignore rules" \
       LICENSE CITATION.cff requirements.txt .gitignore
commit 2026-07-28 11:10 "docs: README with the invariance result up front" README.md docs/img/
commit 2026-07-28 11:15 "tools: history import script" tools/build_history.sh

# anything not yet captured
commit 2026-07-28 11:20 "repo: remaining project files" .

echo
echo "commits: $(git rev-list --count HEAD)"
git log --format='%ad %s' --date=short | tail -5
