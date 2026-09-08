#!/usr/bin/env python3
"""
gen_cost_tables.py — the two measured tables backing §results-overhead.

  tables/nginflection.tex   N/G banding, testing the structural model's
                            prediction that GCI serialisation stops binding
                            above N/G ~ 6-8.
  tables/omegaratio.tex     Distance to the composite lower bound Omega,
                            per topology.

Reads the RE-MEASURED cycle CSV (max over PEs) when it is available and
sufficiently complete, else falls back to the original with a loud warning.
The original recorded GPU 0's counter rather than the max, which understated
cycles on ~54% of rows; see PAPER_V6_PLAN.md §5b.
"""
import argparse
import csv
import datetime
import glob
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwdata
from collections import defaultdict

csv.field_size_limit(sys.maxsize)

# Dataset root.  Resolution order:
#   1. $SPRS_P1                        -- explicit override
#   2. $SPRS_ROOT/data/results         -- the released artifact layout
#   3. the author's original absolute path, kept only as a last resort so that
#      re-running these scripts on the machine the campaign ran on still works.
# The hardcoded path is what made this script unrunnable from a fresh clone.
def _p1_default():
    root = os.environ.get("SPRS_ROOT") or os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    cand = os.path.join(root, "data", "results")
    return cand if os.path.isdir(cand) else "/home/rohit/tournament_p1/results"


P1 = os.environ.get("SPRS_P1") or _p1_default()
MAXPE = f"{P1}/live_hw_results_p1_maxpe.csv"
ORIG = f"{P1}/live_hw_results_p1_unified.csv"

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
    META[lab] = (n, g, t)

TOPO_TEX = {'fat_tree': 'fat-tree', 'hypercube': 'hypercube', 'torus': 'torus',
            'mesh': 'mesh', 'ring': 'ring', 'linear': 'linear'}
MIN_ROWS = 2000          # below this the re-measured set is too partial to use


def load(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, newline='', encoding='utf-8', errors='replace') as f:
        rdr = csv.reader(f)
        first = next(rdr, None)
        if first and first[0] != 'Instance' and len(first) >= 7:
            rows.append(first)
        rows += [r for r in rdr if len(r) >= 7]
    out = []
    for r in rows:
        if r[3] != 'True':
            continue
        try:
            out.append((r[0], int(r[4])))
        except ValueError:
            pass
    return out


def pick_source():
    """Delegate source selection to hwdata so both generators agree.
    hwdata yields (instance, tb, cycles); this module only needs (instance, cycles)."""
    rows, src, trusted = hwdata.select()
    return [(inst, cyc) for inst, _tb, cyc in rows], src, trusted


def omegas():
    om = {}
    for p in glob.glob(f"{P1}/*/sw_results.csv"):
        inst = os.path.basename(os.path.dirname(p))
        with open(p, newline='') as f:
            for r in csv.DictReader(f):
                if r.get('omega'):
                    om[inst] = float(r['omega'])
                    break
    return om


def hdr(source, trusted):
    return ("% GENERATED — do not edit by hand.\n"
            f"% script : scripts/gen_cost_tables.py\n"
            f"% source : {source}\n"
            f"% metric : {'max over PEs (corrected)' if trusted else 'GPU 0 only (DEFECTIVE)'}\n"
            f"% date   : {datetime.date.today().isoformat()}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tables")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    rows, source, trusted = pick_source()
    om = omegas()
    champ = {}
    for inst, cyc in rows:
        if inst not in META or inst not in om:
            continue
        if inst not in champ or cyc < champ[inst]:
            champ[inst] = cyc
    print(f"  {len(champ)} instances with a champion from {os.path.basename(source)}")

    # ---- N/G inflection ----
    bands = [(0, 2, "$\\le 2$"), (2, 6, "$(2,6]$"),
             (6, 8, "$(6,8]$"), (8, 32, "$(8,32]$"), (32, 1e9, "$>32$")]
    agg = defaultdict(list)
    for inst, c in champ.items():
        n, g, _ = META[inst]
        ng = n / g
        for lo, hi, lab in bands:
            if lo < ng <= hi or (lo == 0 and ng <= hi):
                agg[lab].append(c / om[inst])
                break

    b = [r"\begin{table}[!t]",
         r"\caption{Champion cycle count normalised by the lower bound $\Omega$, "
         r"banded by $N/G$. The structural model predicts GCI serialisation binds "
         r"only while $N/G \lesssim 6$--$8$.}",
         r"\label{tab:nginflect}", r"\centering", r"\footnotesize",
         r"\begin{tabular}{@{}lrrr@{}}", r"\toprule",
         r"$N/G$ band & instances & median cyc/$\Omega$ & range \\", r"\midrule"]
    for _, _, lab in bands:
        v = agg.get(lab)
        if not v:
            continue
        b.append(f"{lab} & {len(v)} & {st.median(v):.2f} & "
                 f"{min(v):.2f}--{max(v):.2f} \\\\")
    b += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    with open(f"{a.out}/nginflection.tex", "w") as f:
        f.write(hdr(source, trusted) + "\n".join(b) + "\n")
    print(f"  wrote {a.out}/nginflection.tex")

    # ---- distance to Omega, by topology ----
    bytopo = defaultdict(list)
    for inst, c in champ.items():
        bytopo[META[inst][2]].append(c / om[inst])
    b = [r"\begin{table}[!t]",
         r"\caption{Distance to the composite lower bound $\Omega$ by topology. "
         r"$\Omega$ bounds any schedule on this fabric, so these ratios "
         r"upper-bound what an unconstrained reducer could have recovered.}",
         r"\label{tab:omegaratio}", r"\centering", r"\footnotesize",
         r"\begin{tabular}{@{}lrrr@{}}", r"\toprule",
         r"Topology & instances & median cyc/$\Omega$ & best \\", r"\midrule"]
    for t in sorted(bytopo, key=lambda k: st.median(bytopo[k])):
        v = bytopo[t]
        b.append(f"{TOPO_TEX[t]} & {len(v)} & {st.median(v):.2f} & {min(v):.2f} \\\\")
    allv = [x for v in bytopo.values() for x in v]
    b += [r"\midrule",
          f"\\textbf{{all}} & {len(allv)} & {st.median(allv):.2f} & {min(allv):.2f} \\\\",
          r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    with open(f"{a.out}/omegaratio.tex", "w") as f:
        f.write(hdr(source, trusted) + "\n".join(b) + "\n")
    print(f"  wrote {a.out}/omegaratio.tex")

    if not trusted:
        print("\n  *** tables carry the defective metric — regenerate after re-measurement ***",
              file=sys.stderr)


if __name__ == "__main__":
    main()
