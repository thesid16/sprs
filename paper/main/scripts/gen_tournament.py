#!/usr/bin/env python3
"""
gen_tournament.py — tournament characterisation tables, from measured data.

Produces:
  tables/winners_family.tex   S2/S3 winner distribution by algorithm family
  tables/catalogue.tex        per-algorithm win share (Appendix B)
  tables/perinstance_full.tex per-instance winning triple + cycles + cyc/Omega
  tables/selbias.tex          selection-bias ablation
  data/tournament_facts.json  scalars for inlining into prose

WINNER METRIC: measured HW cycles (not SW makespan). The two disagree --- by
SW makespan RecBisect wins 27/40 and HopMin 14/40, by HW cycles the picture
differs --- and for a hardware-validated paper the measured quantity is the
defensible one.

Reads the re-measured max-over-PEs CSV when complete; otherwise falls back to
the original with a loud warning and stamps the output DEFECTIVE, which
`make check` treats as a build failure.
"""

import os as _os
# Repo root: override with SPRS_ROOT. Defaults to this file's repo.
SPRS_ROOT = _os.environ.get("SPRS_ROOT",
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse
import csv
import datetime
import glob
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwdata
from collections import defaultdict, Counter

csv.field_size_limit(sys.maxsize)

P1 = _os.path.join(SPRS_ROOT,"data","results")
MAXPE = f"{P1}/live_hw_results_p1_maxpe.csv"
ORIG = f"{P1}/live_hw_results_p1_unified.csv"
MIN_ROWS = 2000

S2 = {'2a':('HEFT','list-scheduling'),'2b':('RecBisect','graph partition'),
      '2c':('MLfm','multilevel'),'2d':('DKway','graph partition'),
      '2e':('ExactBB','exact/B\\&B'),'2f':('DFSseed','list-scheduling'),
      '2g':('DSC','clustering'),'2h':('Chr\\\'etienne','clustering'),
      '2i':('CPOP','list-scheduling'),'2j':('Centroid','geometric'),
      '2k':('Lukes','tree DP'),'2l':('Frederickson','tree DP'),
      '2m':('CPFD','clustering'),'2n':('ClHEFT','hierarchical'),
      '2o':('ParSub','hierarchical'),'2p':('Spine','structural'),
      '2q':('SubPack','hierarchical'),'2r':('LvlHLF','structural')}
S3 = {'3a':('Identity','trivial'),'3b':('HopMin','greedy'),
      '3c':('TreeMatch','tree-aware'),'3d':('QAP-SA','metaheuristic'),
      '3e':('MCF','flow'),'3f':('DRB','recursive'),'3g':('SFC','geometric'),
      '3h':('Spectral','spectral'),'3i':('RAGreedy','greedy'),
      '3j':('Tabu','metaheuristic')}

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
TOPO = {'fat_tree':'fat-tree','hypercube':'hypercube','torus':'torus',
        'mesh':'mesh','ring':'ring','linear':'linear'}


def load_hw(path):
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
            out.append((r[0], r[2], int(r[4])))
        except ValueError:
            pass
    return out


def pick():
    return hwdata.select()


def split_tb(tb):
    p = tb.split('_')
    return (p[1], p[2]) if len(p) > 2 else (None, None)


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


def sw_makespans():
    """(instance, tb_fname) -> SW makespan, for the selection-bias ablation."""
    ms = {}
    for p in glob.glob(f"{P1}/*/sw_results.csv"):
        inst = os.path.basename(os.path.dirname(p))
        with open(p, newline='') as f:
            for r in csv.DictReader(f):
                if r.get('valid') == 'True' and r.get('tb_fname') and r.get('makespan'):
                    try:
                        ms[(inst, r['tb_fname'])] = int(r['makespan'])
                    except ValueError:
                        pass
    return ms


def hdr(src, trusted):
    return ("% GENERATED — do not edit by hand.\n"
            "% script : scripts/gen_tournament.py\n"
            f"% source : {src}\n"
            f"% metric : HW cycles, {'max over PEs (corrected)' if trusted else 'GPU 0 only (DEFECTIVE)'}\n"
            f"% date   : {datetime.date.today().isoformat()}\n")


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return float('nan')

    def rank(v):
        idx = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[idx[j + 1]] == v[idx[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[idx[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** .5
    return num / den if den else float('nan')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tables")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs("data", exist_ok=True)

    rows, src, trusted = pick()
    om, sw = omegas(), sw_makespans()

    byinst = defaultdict(list)
    for inst, tb, cyc in rows:
        byinst[inst].append((tb, cyc))
    print(f"  {len(byinst)} instances, {len(rows)} passing rows "
          f"from {os.path.basename(src)}")

    # ---- winners by measured HW cycles ----
    win2, win3, fam2, fam3, per = Counter(), Counter(), Counter(), Counter(), []
    for inst, lst in byinst.items():
        tb, cyc = min(lst, key=lambda x: x[1])
        s2, s3 = split_tb(tb)
        if not s2:
            continue
        win2[s2] += 1
        win3[s3] += 1
        fam2[S2.get(s2, ('?', 'other'))[1]] += 1
        fam3[S3.get(s3, ('?', 'other'))[1]] += 1
        n, g, t = META[inst]
        per.append((n, g, t, s2, s3, cyc, om.get(inst)))
    ninst = sum(win2.values())

    # ---- family distribution ----
    b = [r"\begin{tabular}{@{}lrr@{}}", r"\toprule",
         r"Family & instances won & share \\", r"\midrule"]
    for f, c in fam2.most_common():
        b.append(f"{f} & {c} & {100*c/ninst:.1f}\\% \\\\")
    b += [r"\bottomrule", r"\end{tabular}"]
    open(f"{a.out}/winners_family.tex", "w").write(hdr(src, trusted) + "\n".join(b) + "\n")

    # ---- per-algorithm catalogue ----
    b = [r"\begin{tabular}{@{}llrr@{}}", r"\toprule",
         r"Algorithm & Family & wins & share \\", r"\midrule"]
    for k in sorted(S2, key=lambda k: (-win2.get(k, 0), k)):
        nm, fam = S2[k]
        c = win2.get(k, 0)
        b.append(f"\\sv{{{nm}}} & {fam} & {c} & {100*c/ninst:.1f}\\% \\\\")
    b += [r"\midrule", r"\multicolumn{4}{@{}l}{\emph{Mapping (S3)}} \\", r"\midrule"]
    for k in sorted(S3, key=lambda k: (-win3.get(k, 0), k)):
        nm, fam = S3[k]
        c = win3.get(k, 0)
        b.append(f"\\sv{{{nm}}} & {fam} & {c} & {100*c/ninst:.1f}\\% \\\\")
    b += [r"\bottomrule", r"\end{tabular}"]
    open(f"{a.out}/catalogue.tex", "w").write(hdr(src, trusted) + "\n".join(b) + "\n")

    # ---- per-instance ----
    b = [r"\begin{tabular}{@{}rrlllrr@{}}", r"\toprule",
         r"$N$ & $G$ & Topology & $\asgn$ & $\map$ & cycles & cyc/$\Omega$ \\",
         r"\midrule"]
    for n, g, t, s2, s3, cyc, o in sorted(per):
        r = f"{cyc/o:.2f}" if o else "--"
        b.append(f"{n} & {g} & {TOPO[t]} & \\sv{{{S2.get(s2,('?',))[0]}}} & "
                 f"\\sv{{{S3.get(s3,('?',))[0]}}} & {cyc} & {r} \\\\")
    b += [r"\bottomrule", r"\end{tabular}"]
    open(f"{a.out}/perinstance_full.tex", "w").write(hdr(src, trusted) + "\n".join(b) + "\n")

    # ---- selection-bias ablation ----
    # If HW simulation had been restricted to the top-K by SW makespan, would
    # the true HW champion have been missed? Leakage = fraction of the true
    # top-K-by-cycles that falls outside the top-K-by-makespan.
    rho, leak = {}, {}
    for K in (10, 15, 30):
        rs, ls = [], []
        for inst, lst in byinst.items():
            pairs = [(tb, c, sw.get((inst, tb))) for tb, c in lst]
            pairs = [(tb, c, m) for tb, c, m in pairs if m is not None]
            if len(pairs) < K + 2:
                continue
            rs.append(spearman([m for _, _, m in pairs], [c for _, c, _ in pairs]))
            top_hw = {tb for tb, _, _ in sorted(pairs, key=lambda x: x[1])[:K]}
            top_sw = {tb for tb, _, _ in sorted(pairs, key=lambda x: x[2])[:K]}
            ls.append(len(top_hw - top_sw) / K)
        rho[K], leak[K] = rs, ls

    b = [r"\begin{tabular}{@{}rrrr@{}}", r"\toprule",
         r"$K$ & instances & median $\rho$ & median leakage \\", r"\midrule"]
    for K in (10, 15, 30):
        if rho[K]:
            b.append(f"{K} & {len(rho[K])} & {st.median(rho[K]):.2f} & "
                     f"{st.median(leak[K]):.2f} \\\\")
    b += [r"\bottomrule", r"\end{tabular}"]
    open(f"{a.out}/selbias.tex", "w").write(hdr(src, trusted) + "\n".join(b) + "\n")

    facts = {
        "generated": datetime.date.today().isoformat(),
        "source": src, "trusted_metric": trusted, "n_instances": ninst,
        "s2_family_share": {k: round(100*v/ninst, 1) for k, v in fam2.items()},
        "s3_family_share": {k: round(100*v/ninst, 1) for k, v in fam3.items()},
        "s2_wins": dict(win2), "s3_wins": dict(win3),
        "selbias": {str(K): {"median_rho": round(st.median(rho[K]), 3),
                             "median_leak": round(st.median(leak[K]), 3),
                             "n": len(rho[K])} for K in (10, 15, 30) if rho[K]},
    }
    json.dump(facts, open("data/tournament_facts.json", "w"), indent=1)

    # Macros so prose numbers cannot drift from the tables. Any figure quoted
    # in running text must come from here, never be typed inline.
    top2f, top2v = fam2.most_common(1)[0]
    top3k, top3v = win3.most_common(1)[0]
    m = [hdr(src, trusted),
         r"% Usage: \TournTopFamily, \TournTopFamilyShare, ...",
         f"\\newcommand{{\\TournNInst}}{{{ninst}}}",
         f"\\newcommand{{\\TournTopFamily}}{{{top2f}}}",
         f"\\newcommand{{\\TournTopFamilyShare}}{{{100*top2v/ninst:.0f}\\%}}",
         f"\\newcommand{{\\TournTopMap}}{{{S3[top3k][0]}}}",
         f"\\newcommand{{\\TournTopMapShare}}{{{100*top3v/ninst:.0f}\\%}}",
         f"\\newcommand{{\\TournTopAsgn}}{{{S2[win2.most_common(1)[0][0]][0]}}}",
         f"\\newcommand{{\\TournTopAsgnWins}}{{{win2.most_common(1)[0][1]}}}"]
    for K in (10, 15, 30):
        if rho[K]:
            m += [f"\\newcommand{{\\TournRho{K}}}{{{st.median(rho[K]):.2f}}}",
                  f"\\newcommand{{\\TournLeak{K}}}{{{st.median(leak[K]):.2f}}}"]
    open("data/tournament_macros.tex", "w").write("\n".join(m) + "\n")

    print(f"  wrote 4 tables + data/tournament_facts.json")
    print(f"  S2 families: {', '.join(f'{k} {100*v/ninst:.0f}%' for k, v in fam2.most_common(4))}")
    print(f"  S3 top: {', '.join(f'{S3[k][0]} {v}' for k, v in win3.most_common(4))}")
    for K in (10, 15, 30):
        if rho[K]:
            print(f"  K={K:<3} median rho={st.median(rho[K]):.2f} "
                  f"median leakage={st.median(leak[K]):.2f} (n={len(rho[K])})")
    if not trusted:
        print("\n  *** DEFECTIVE metric — regenerate after re-measurement ***", file=sys.stderr)


if __name__ == "__main__":
    main()
