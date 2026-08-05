# SPRS Tournament — Project Guide for Claude Code

## What this project is

This is a **NoC (Network-on-Chip) hardware-simulation tournament**. We have:
- A SystemVerilog RTL design of a btree-based NoC with parameterized topology (mesh, torus, hypercube, fat-tree, ring, 1D)
- A Python tournament framework (`sprs_core.py` + `sprs_tournament (1).py`) that:
  1. **SW phase:** runs thousands of scheduler/mapper algorithm combinations ("pipelines" like `2a|3a`, `2b|3c`, etc.) to produce schedules
  2. **HW phase:** generates a SystemVerilog testbench per (instance, pipeline) and runs it through Vivado xsim
  3. Compares results to rank pipelines

40 "instances" (named like `max_bal_2d`, `vlarge_mod_ring`, `maxp_mod_fat`) — each defines a leaf count + GPU count + topology.

## Current status (as of migration)

### What's done
- **SW phase: 100% complete** across all 40 instances (`results/<instance>/sw_results.csv`)
- **HW phase via original protocol: 2356 PASS + 17 functional fails** stored as the pre-tier2 baseline in `results/live_hw_results_p1_unified.csv`
- **HW phase via force-bypass (this is the new technique — see below):** 415 PASS + 4 fails on Tier 2 instances (max_bal_2d, maxp_bal_2d, maxp_dense_hc, max_mod_fat)
- **Total in unified CSV right now: 2771 PASS + 21 fail = 2792 rows** (covers 39 of 40 instances)

### What's left
- **`maxp_mod_fat`** (56 TBs, 8192L × 4096G fat-tree) — this is the only remaining gap. xelab on the bypass-rewritten TB needs ~50-70 GB of RAM, which exceeded the original 62 GB machine. **This is the primary reason for migration.** Should run cleanly on the new 512 GB box.

### Known failure patterns (don't try to "fix" these)
- **Pipeline `2f|3c`** doesn't converge on multiple topologies (max_bal_2d, max_mod_fat, maxp_bal_2d, maxp_dense_hc, max_dense_hc, vlarge2_mod_ring all failed). Confirmed by hitting the TB-internal cycle counter at ~20K cycles. **It's a structurally bad pipeline, not an infrastructure issue.** Leave the fail rows as-is.
- **Pipelines `2g|3*` on vlarge_dense_hc** (7 functional fails) — same kind of structural fail. Pre-existing in unified.
- **Pipelines `2i|3*` on vlarge2_mod_ring** (8 functional fails) — same. Pre-existing.

## The force-bypass technique (CRITICAL to understand)

The auto-generated TBs initialize the NoC route table via **~1M-17M `write_route(r,d,p)` task calls**, each pulsing `rt_wr_en` for one clock cycle. For large fat-tree/2D instances, this takes 8+ hours of xsim time just for init. Most of the original tournament's Tier 2 attempts (max_*, maxp_*) timed out before computation could start.

**The fix:** rewrite each `write_route(r,d,p);` call as a direct hierarchical procedural assignment:

```verilog
// Original (slow, one cycle per call):
write_route(0, 5, 3);

// Bypass (zero simulated cycles):
u_sys.gen_rtr[0].u_rtr.route_table[5] = 3;
```

This is done at runtime by `_bypass_runner.py`, per-TB, in each worker's work_dir, before xvlog. The TBs on disk are never modified.

### ⚠️ Critical bit-width gotcha
**Do NOT use `3'd{p}` (sized literal) in the rewrite — use plain `{p}`** (integer literal, auto-extends to LHS width).

Why: the route_table element width is `clog2(NUM_PORTS)`. For most topologies that's 3 bits (5-port routers → PORT_W=3), but **fat-tree has 4-bit ports** (and HC/mesh can have more). A `3'd<p>` literal truncates port values > 7 to the low 3 bits, breaking fat-tree routing silently. The current `_bypass_runner.py` already does this correctly — don't change it back.

### What bypass does and doesn't preserve

| Property | Status |
|---|---|
| PASS/FAIL correctness | ✅ Always — bit-exact `root_result` match |
| `perf_total[0]` cycle counts vs original protocol | ~59% bit-exact, ~41% deterministically lower by 1-54% |
| Ranking of pipelines within an instance | ~80% of instances preserve rankings (Spearman ≥0.85 vs original); ~20% have meaningful shift |
| All instances completable | All except maxp_mod_fat on this machine — RAM-constrained |

The cycle drift in 41% is **structural, not temporal** (proven via a settling-delay experiment with delays 0 → 1M cycles, no convergence). Don't try to fix it with delays.

## Recommended workflow on the new machine

### To run `maxp_mod_fat` (the main task)

```bash
cd <project root>
# Use the included runme.sh (designed for this) or directly:
nohup python3 _bypass_runner.py \
  --jobs 8 \
  --timeout 172800 \
  --tb-list-json /tmp/maxp_mod_fat.json \
  --out-csv results/live_hw_results_p1_unified.csv \
  > results/_maxp_mod_fat.log 2>&1 &
```

Build the JSON list first:
```bash
python3 -c "
import os, json
tbs = sorted(f[:-3] for f in os.listdir('results/maxp_mod_fat')
             if f.startswith('tb_') and f.endswith('.sv'))
out = [['maxp_mod_fat', t, 8192, 4096] for t in tbs]
json.dump(out, open('/tmp/maxp_mod_fat.json','w'))
print(f'{len(out)} TBs')
"
```

**RAM budget**: each xelab uses ~50-70 GB on maxp_mod_fat. With 512 GB RAM, **8 workers is safe maximum** (peak ~480 GB). 10 workers risks OOM if all 10 xelabs peak simultaneously.

### To retry any failed TBs with longer timeout

```bash
# Drop the failed rows from unified (so they get re-run)
python3 -c "
import csv, os
src = 'results/live_hw_results_p1_unified.csv'
# Drop only SIM_WALLCLOCK_TIMEOUT (could pass with more time);
# keep SIM_TB_TIMEOUT (functional fail, more time won't help)
with open(src) as f:
    rdr = csv.DictReader(f); fields = rdr.fieldnames
    kept = [r for r in rdr if r['ErrorCode'] != 'SIM_WALLCLOCK_TIMEOUT_BYPASS']
with open(src + '.new','w',newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
    for r in kept: w.writerow(r)
os.replace(src + '.new', src)
"
# Then rebuild JSON for the dropped TBs and re-launch with --timeout 86400 (24 hr)
```

### Monitoring (user preference!)
**User does NOT want background polling/monitor watchers unless explicitly requested.** They prefer to check progress themselves via `tail -F` on the log. See `~/.claude/projects/.../memory/feedback_no_monitoring.md`.

If they DO ask to monitor, use the Monitor tool (shell-based, no LLM cost) or an Agent with `model=haiku`.

## Repository layout

```
tournament_portable/
├── CLAUDE.md                        ← this file
├── README.md                        ← migration / setup guide
├── sprs_core.py                     ← TB generator + scheduler algorithms (5781 lines)
├── sprs_tournament (1).py          ← orchestration of phase1/phase2 SW + HW
├── _bypass_runner.py                ← THE main thing — bypass-rewrite + Vivado driver
├── _recheck_runner.py               ← Original-protocol runner (writes ErrorCode without _BYPASS)
├── _merge_recheck_to_unified.py    ← Helper to translate recheck CSV to unified schema
├── _probe_worker.py                 ← Diagnostic tool for hung simulation cases
├── _phase2_launcher.sh              ← Old launcher (probably stale)
├── _progress_watcher.sh             ← Old progress tracker (probably stale)
├── runme.sh                         ← Quick-start launcher (uses _bypass_runner)
├── rtl/                             ← SystemVerilog RTL (10 files, ~3K lines)
│   ├── noc_pkg.sv, btree_pkg.sv   ← packages
│   ├── noc_router.sv               ← router with route_table[0..DEPTH-1]
│   ├── noc_ni.sv                   ← network interface
│   ├── noc_system.sv               ← top-level instantiation (gen_rtr, gen_node generates)
│   ├── btree_fsm_fast.sv           ← compute node FSM
│   ├── fp64_add.sv                 ← floating-point add
│   └── sync_fifo.sv, link_tx.sv, noc_link.sv  ← link layer
├── results/
│   ├── live_hw_results_p1_unified.csv         ← THE crown jewel: 2792 rows of HW results
│   ├── live_hw_results_p1_unified.csv.bak_*   ← timestamped backups (keep these!)
│   └── <instance>/                            ← one dir per instance (40 dirs)
│       ├── tb_2a_3a_none.sv                   ← Vivado testbenches (the "TBs")
│       ├── tb_2*_3*_none.sv                   ← named by pipeline (s2|s3)
│       ├── sw_results.csv                     ← SW phase output per pipeline
│       └── lower_bounds.json                  ← computed bounds (for reference)
└── experiment_*/                    ← Historical experiment dirs (force, validate, drift, etc.)
                                       Keep for reference but don't need to regenerate.
```

## Unified CSV schema

```
Instance,Pipeline,TB_Name,Pass,Cycles,SimTime_s,ErrorCode,Error
```
- `Pipeline` is derived from `TB_Name`: `tb_2a_3b_none` → `2a|3b` (s2|s3 names)
- `Pass`: `True` or `False` strings
- `Cycles`: int, `perf_total[0]` from xsim output (GPU 0's perf counter)
- `ErrorCode` values you'll encounter:
  - `OK` — original protocol pass
  - `OK_BYPASS` — force-bypass pass
  - `E_OK` — old tournament code's "OK" variant
  - `SIM_TB_TIMEOUT_BYPASS` — TB-internal cycle counter hit ⇒ functional fail (don't retry)
  - `SIM_WALLCLOCK_TIMEOUT_BYPASS` — hit wallclock ⇒ might pass with more time (retry candidate)
  - `XELAB_FAIL_BYPASS`, `XELAB_TIMEOUT_BYPASS` — elaboration issue (RAM/CPU)
  - `SIM_FAIL_BYPASS` — sim completed but wrong result (very rare)

## Per-instance resource notes (useful for choosing JOBS/TIMEOUT)

Average observed bypass per-TB wallclock at 4 workers on a 62 GB machine:

| Instance | Module | TB count | Avg per-TB | RAM/proc | Notes |
|---|---|---|---|---|---|
| max_dense_hc | 4096L × 512G | 106 | ~7 min | ~5 GB | Completed |
| max_bal_2d | 4096L × 1024G | 120 | ~22 min | ~5 GB | Completed |
| max_mod_fat | 4096L × 2048G | 80 | ~6 hr (at 8-hr cap) | ~10 GB | Completed |
| maxp_dense_hc | 8192L × 1024G | 98 | ~55 min | ~15 GB | Completed |
| maxp_bal_2d | 8192L × 2070G | 117 | ~90 min | ~15 GB | Completed |
| **maxp_mod_fat** | **8192L × 4096G** | **56** | **~10-18 hr est** | **~50-70 GB** | ⏳ **THE TARGET** |

On the new 512 GB machine: expect maxp_mod_fat at ~10-15 hr/TB × 56 / 8 workers = ~3-5 days total.

## GPU considerations (96 GB VRAM available)

The target server has a powerful GPU. Two things to keep in mind:

1. **GL0AM (NVIDIA's GPU-accelerated gate-level simulator)** — evaluated earlier. **Not a fit** because:
   - Needs gate-level netlist (we have RTL — would need synthesis pass)
   - Procedural TB needs conversion to waveform inputs
   - Tooling not fully OSS
   - Worth revisiting only if a synthesis flow is already set up

2. **Vivado xsim does NOT use GPU.** All HW sim runs on CPU. The GPU is unused for the main workflow.

3. **Possible future use:** Verilator 5.x with `--timing` (needs g++ 10+ for `<coroutine>`). Could investigate if maxp_mod_fat is too slow even on this machine. Verilator failed last attempt because the system g++ was 9.4 (no C++20 coroutines).

## Failed paths to NOT retry (saving you the time)

These were attempted on the original machine and don't work:
- ❌ `force` keyword on route_table array elements (Vivado xelab rejects: not allowed on array elements with constant index in this context)
- ❌ Settling delays (`#1us` ... `#10ms` before `program_start`) — drift is structural, not temporal
- ❌ Verilator with system g++ 9.4 — needs C++20 coroutines
- ❌ Running with 10+ workers — OOM on heavy instances

These work:
- ✅ Force-bypass with plain integer literal (not `3'd<p>`)
- ✅ 4-8 workers depending on instance size
- ✅ 8-48 hour timeout depending on instance

## Active behavioral preferences (from memory)
- **No proactive monitoring.** User checks progress themselves. Only set up Monitor/agents if explicitly asked.
- Override: when explicitly asked ("launch a monitor", "use haiku low"), use cheap Agent (model=haiku) or shell Monitor.

## When you wrap up

When all 56 maxp_mod_fat TBs are done, run:
```bash
python3 -c "
import csv
rows=list(csv.DictReader(open('results/live_hw_results_p1_unified.csv')))
p=sum(1 for r in rows if r['Pass']=='True')
f=len(rows)-p
print(f'Final: {len(rows)} rows ({p} pass, {f} fail)')
# Instance coverage check
from collections import Counter
instances=Counter(r['Instance'] for r in rows)
print(f'Instance coverage: {len(instances)}/40')
"
```

Target: **2792 + 56 = 2848 rows, 40/40 instance coverage.** That closes the tournament.
