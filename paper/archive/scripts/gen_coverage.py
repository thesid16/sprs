#!/usr/bin/env python3
"""
gen_coverage.py — Appendix D: instance-suite coverage and per-instance
xsim wall-clock.

Round-2 review finding A: the hand-maintained coverage table summed to 42
against a 40-instance suite (mesh alone was over by 3). Round-2 finding F:
Sec. VII-A forward-references per-instance wall-clock "in Appendix D", which
Appendix D did not contain. Both are fixed by generating the appendix from
the instance manifest and the measured CSV instead of maintaining it by hand.

Produces:
  tables/coverage.tex   (N-bucket x topology cell counts; sums to 40)
  tables/walltime.tex   (per-instance xsim wall-clock)
  data/coverage_macros.tex
"""
import argparse
import csv
import datetime
import os
import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwdata

csv.field_size_limit(sys.maxsize)

SUITE = [
    (8, 4, 'ring', 'tiny_mod_ring'), (8, 2, 'linear', 'tiny_dense_1d'),
    (32, 16, 'torus', 'small_mod_2d'), (32, 8, 'fat_tree', 'small_bal_fat'),
    (32, 4, 'hypercube', 'small_dense_hc'), (128, 64, 'ring', 'med_mod_ring'),
    (128, 32, 'fat_tree', 'med_mod_fat'), (128, 16, 'torus', 'med_bal_2d'),
    (128, 8, 'mesh', 'med_dense_mesh'), (128, 4, 'linear', 'med_extreme_1d'),
    (512, 256, 'ring', 'large_mod_ring'), (512, 64, 'fat_tree', 'large_bal_fat'),
    (512, 32, 'hypercube', 'large_dense_hc'), (512, 16, 'torus', 'large_dense_2d'),
    (512, 8, 'linear', 'large_extreme_1d'), (1024, 512, 'ring', 'vlarge_mod_ring'),
    (1024, 128, 'fat_tree', 'vlarge_bal_fat'), (1024, 64, 'torus', 'vlarge_dense_2d'),
    (1024, 32, 'hypercube', 'vlarge_dense_hc'), (2048, 256, 'fat_tree', 'vlarge2_bal_fat'),
    (2048, 128, 'torus', 'vlarge2_dense_2d'), (4096, 2048, 'fat_tree', 'max_mod_fat'),
    (4096, 1024, 'torus', 'max_bal_2d'), (4096, 512, 'hypercube', 'max_dense_hc'),
    (8192, 4096, 'fat_tree', 'maxp_mod_fat'), (8192, 2048, 'torus', 'maxp_bal_2d'),
    (8192, 1024, 'hypercube', 'maxp_dense_hc'), (512, 64, 'mesh', 'large_bal_mesh'),
    (2048, 256, 'mesh', 'vlarge_bal_mesh'), (128, 128, 'torus', 'med_full_torus'),
    (2048, 512, 'ring', 'vlarge2_mod_ring'), (1024, 16, 'linear', 'vlarge_extreme_1d'),
    (10, 4, 'ring', 'npow2n_tiny_ring'), (16, 5, 'mesh', 'npow2g_small_mesh'),
    (50, 7, 'hypercube', 'npow2_tiny_hc'), (100, 10, 'torus', 'npow2_small_torus'),
    (200, 12, 'fat_tree', 'npow2_med_fat'), (500, 32, 'torus', 'large_unbal_torus'),
    (1500, 64, 'hypercube', 'vlarge_unbal_hc'), (3000, 128, 'fat_tree', 'max_unbal_fat'),
]

TOPOS = [('linear', 'Lin.'), ('ring', 'Ring'), ('mesh', 'Mesh'),
         ('torus', 'Torus'), ('fat_tree', 'Fat-tree'), ('hypercube', 'Hyp.')]
BUCKETS = [(8, 32, '8--32'), (33, 256, '33--256'), (257, 1024, '257--1K'),
           (1025, 4096, '1K--4K'), (4097, 8192, '8K')]


def bucket(n):
    for lo, hi, lab in BUCKETS:
        if lo <= n <= hi:
            return lab
    raise ValueError(f"N={n} falls in no bucket")


def hdr():
    return ("% GENERATED — do not edit by hand.\n"
            "% script : scripts/gen_coverage.py\n"
            "% source : instance manifest + measured HW CSV\n"
            f"% date   : {datetime.date.today().isoformat()}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tables")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs("data", exist_ok=True)

    assert len(SUITE) == 40, f"manifest has {len(SUITE)} instances, expected 40"
    assert len({x[3] for x in SUITE}) == 40, "duplicate instance label in manifest"

    # ---- cell counts -------------------------------------------------------
    cell = defaultdict(int)
    for n, g, t, lab in SUITE:
        cell[(bucket(n), t)] += 1

    L = [hdr(), r'\begin{tabular}{@{}l' + 'c' * len(TOPOS) + r'r@{}}', r'\toprule',
         '$N$-bucket & ' + ' & '.join(p for _, p in TOPOS) + r' & Total\\', r'\midrule']
    coltot = defaultdict(int)
    grand = 0
    for _, _, blab in BUCKETS:
        cells, rt = [], 0
        for t, _ in TOPOS:
            c = cell[(blab, t)]
            coltot[t] += c
            rt += c
            cells.append(str(c) if c else '$-$')
        grand += rt
        L.append(f'{blab} & ' + ' & '.join(cells) + f' & {rt} ' + r'\\')
    L += [r'\midrule',
          'Total & ' + ' & '.join(str(coltot[t]) for t, _ in TOPOS) +
          f' & \\textbf{{{grand}}} ' + r'\\',
          r'\bottomrule', r'\end{tabular}']
    assert grand == 40, f"coverage table sums to {grand}, not 40"
    assert sum(coltot.values()) == 40, "column totals disagree with 40"
    open(f"{a.out}/coverage.tex", "w").write("\n".join(L) + "\n")

    # ---- per-instance wall-clock ------------------------------------------
    rows, src, trusted = hwdata.select()
    if not trusted:
        raise SystemExit("DEFECTIVE source — refusing to emit wall-clock table")

    sim = defaultdict(list)
    with open(src, newline='', encoding='utf-8', errors='replace') as f:
        rdr = csv.reader(f)
        first = next(rdr, None)
        allrows = ([first] if first and first[0] != 'Instance' and len(first) >= 7 else [])
        allrows += [r for r in rdr if len(r) >= 7]
    # Passing runs only: the headline figures in Sec. VII-A (2,822 runs,
    # 821.5 core-h, 99 s median, 5.51 h longest) are over PASSes, and this
    # table must reconcile to them exactly rather than to all attempts.
    for r in allrows:
        if r[3] != 'True':
            continue
        try:
            sim[r[0]].append(float(r[5]))
        except (ValueError, IndexError):
            pass

    meta = {lab: (n, g, t) for n, g, t, lab in SUITE}
    body, tot_h, ntb = [], 0.0, 0
    for lab in sorted(sim, key=lambda k: (meta.get(k, (0,))[0], k)):
        if lab not in meta:
            continue
        v = sim[lab]
        n, g, t = meta[lab]
        h = sum(v) / 3600.0
        tot_h += h
        ntb += len(v)
        body.append(f"\\sv{{{lab.replace('_', r'\_')}}} & {n} & {g} & "
                    f"{dict(TOPOS)[t] if t in dict(TOPOS) else t} & {len(v)} & "
                    f"{st.median(v):.0f} & {max(v)/3600:.2f} & {h:.1f} \\\\")

    W = [hdr(), r'\begin{tabular}{@{}lrrlrrrr@{}}', r'\toprule',
         r'Instance & $N$ & $G$ & Topo. & TBs & Med.~(s) & Max~(h) & Total~(core-h)\\',
         r'\midrule'] + body + [
        r'\midrule',
        f'\\textbf{{Total}} & & & & \\textbf{{{ntb}}} & & & \\textbf{{{tot_h:.1f}}} \\\\',
        r'\bottomrule', r'\end{tabular}']
    open(f"{a.out}/walltime.tex", "w").write("\n".join(W) + "\n")

    giants = sorted(sim, key=lambda k: -sum(sim[k]))[:5]
    giant_h = sum(sum(sim[k]) for k in giants) / 3600.0
    allv = [x for v in sim.values() for x in v]
    print(f"  reconcile: {ntb} passing TBs, {tot_h:.1f} core-h, "
          f"median {st.median(allv):.0f}s, max {max(allv)/3600:.2f}h, "
          f"giants {100*giant_h/tot_h:.1f}% ({', '.join(giants)})")

    open("data/coverage_macros.tex", "w").write(
        hdr() +
        f"\\newcommand{{\\SuiteSize}}{{{grand}}}\n"
        f"\\newcommand{{\\SuiteThinCells}}{{{sum(1 for v in cell.values() if v and v <= 2)}}}\n"
        f"\\newcommand{{\\SuiteEmptyCells}}{{{len(BUCKETS)*len(TOPOS) - len([1 for v in cell.values() if v])}}}\n"
        f"\\newcommand{{\\WallTBs}}{{{ntb:,}}}\n".replace(",", "{,}") +
        f"\\newcommand{{\\WallTotalH}}{{{tot_h:.1f}}}\n"
        f"\\newcommand{{\\WallMedianS}}{{{st.median(allv):.0f}}}\n"
        f"\\newcommand{{\\WallMaxH}}{{{max(allv)/3600:.2f}}}\n"
        f"\\newcommand{{\\WallGiantShare}}{{{100*giant_h/tot_h:.1f}\\%}}\n")

    print(f"  coverage: {grand} instances, {sum(1 for v in cell.values() if v)} populated cells; "
          f"walltime: {ntb} TBs, {tot_h:.1f} core-h over {len(body)} instances")


if __name__ == "__main__":
    main()
