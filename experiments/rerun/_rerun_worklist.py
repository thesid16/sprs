#!/usr/bin/env python3
"""
_rerun_worklist.py — build the re-measurement worklist for the corrected
max-over-PEs cycle metric.

Background: _bypass_runner.py recorded GPU 0's perf_total as "Cycles" rather
than the max over PEs, so 140/2822 passing rows held per-PE local work instead
of end-to-end makespan. The runner is fixed; these worklists drive the re-run.

Split into phases by RAM footprint so the watchdog can use a safe worker count
for each. Phase A is 34 light instances (~66 core-h); phase B is the 4 giants
(~286 core-h). maxp_mod_fat is excluded — 5 attempts, all exceeding the
28,800 s cap, 58.9 core-h expended without one completion.

Usage:  python3 _rerun_worklist.py [--outdir /tmp]
"""

import os as _os
# Repo root: override with SPRS_ROOT. Defaults to this file's repo.
SPRS_ROOT = _os.environ.get("SPRS_ROOT",
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse
import csv
import json
import os
import sys
from collections import defaultdict

csv.field_size_limit(sys.maxsize)

BASE = SPRS_ROOT
RES = f"{BASE}/results"
SRC_CSV = f"{RES}/live_hw_results_p1_unified.csv"

# Heavy elaboration footprint (~5-15 GB/worker) -> lower worker count.
GIANTS = ["max_mod_fat", "maxp_bal_2d", "maxp_dense_hc", "max_bal_2d", "max_dense_hc"]
# Never completes: 5 attempts, all SIM_WALLCLOCK_TIMEOUT_BYPASS at 28,800 s.
EXCLUDE = ["maxp_mod_fat"]

META = {}
for n, g, t, lab in [
    (8,4,'ring','tiny_mod_ring'),(8,2,'linear','tiny_dense_1d'),
    (32,16,'torus','small_mod_2d'),(32,8,'fat_tree','small_bal_fat'),
    (32,4,'hypercube','small_dense_hc'),(128,64,'ring','med_mod_ring'),
    (128,32,'fat_tree','med_mod_fat'),(128,16,'torus','med_bal_2d'),
    (128,8,'mesh','med_dense_mesh'),(128,4,'linear','med_extreme_1d'),
    (512,256,'ring','large_mod_ring'),(512,64,'fat_tree','large_bal_fat'),
    (512,32,'hypercube','large_dense_hc'),(512,16,'torus','large_dense_2d'),
    (512,8,'linear','large_extreme_1d'),(1024,512,'ring','vlarge_mod_ring'),
    (1024,128,'fat_tree','vlarge_bal_fat'),(1024,64,'torus','vlarge_dense_2d'),
    (1024,32,'hypercube','vlarge_dense_hc'),(2048,256,'fat_tree','vlarge2_bal_fat'),
    (2048,128,'torus','vlarge2_dense_2d'),(4096,2048,'fat_tree','max_mod_fat'),
    (4096,1024,'torus','max_bal_2d'),(4096,512,'hypercube','max_dense_hc'),
    (8192,4096,'fat_tree','maxp_mod_fat'),(8192,2048,'torus','maxp_bal_2d'),
    (8192,1024,'hypercube','maxp_dense_hc'),(512,64,'mesh','large_bal_mesh'),
    (2048,256,'mesh','vlarge_bal_mesh'),(128,128,'torus','med_full_torus'),
    (2048,512,'ring','vlarge2_mod_ring'),(1024,16,'linear','vlarge_extreme_1d'),
    (10,4,'ring','npow2n_tiny_ring'),(16,5,'mesh','npow2g_small_mesh'),
    (50,7,'hypercube','npow2_tiny_hc'),(100,10,'torus','npow2_small_torus'),
    (200,12,'fat_tree','npow2_med_fat'),(500,32,'torus','large_unbal_torus'),
    (1500,64,'hypercube','vlarge_unbal_hc'),(3000,128,'fat_tree','max_unbal_fat')]:
    META[lab] = (n, g)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="/tmp")
    a = ap.parse_args()

    # Every (instance, TB) that produced a settled result in the original
    # campaign is a re-measurement target. Reading the source CSV rather than
    # globbing the directory keeps us to exactly what was measured before.
    seen = set()
    with open(SRC_CSV, newline='', encoding='utf-8', errors='replace') as f:
        rdr = csv.reader(f)
        first = next(rdr, None)
        rows = [first] if (first and first[0] != 'Instance' and len(first) >= 7) else []
        rows += [r for r in rdr if len(r) >= 7]
    for r in rows:
        inst, tb = r[0], r[2]
        if inst in EXCLUDE:
            continue
        if not os.path.exists(f"{RES}/{inst}/{tb}.sv"):
            continue          # TB no longer on disk; cannot re-simulate
        seen.add((inst, tb))

    phase = defaultdict(list)
    for inst, tb in sorted(seen):
        n, g = META[inst]
        phase["B" if inst in GIANTS else "A"].append([inst, tb, n, g])

    for ph in ("A", "B"):
        path = os.path.join(a.outdir, f"rerun_phase{ph}.json")
        with open(path, "w") as f:
            json.dump(phase[ph], f)
        insts = sorted({x[0] for x in phase[ph]})
        print(f"phase {ph}: {len(phase[ph]):5d} TBs across {len(insts):2d} instances -> {path}")

    total = sum(len(v) for v in phase.values())
    print(f"\ntotal to re-measure: {total}")
    print(f"excluded ({','.join(EXCLUDE)}): never completes, see PAPER_V6_PLAN.md")


if __name__ == "__main__":
    main()
