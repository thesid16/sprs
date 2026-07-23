#!/usr/bin/env python3
"""
gen_figures.py — data figures for paper_v6, emitted as PGFPlots.

Two figures, both backing §results-overhead:

  figures/omega_by_instance.tex   distance to the lower bound Omega for every
                                  HW-validated instance, grouped by topology
  figures/ng_inflection.tex       cyc/Omega against N/G, with the structural
                                  model's predicted 6-8 inflection band marked

Design decisions worth stating:
  * Identity is never carried by colour alone. Each topology gets a distinct
    marker shape as well as a hue, so the figures survive greyscale printing
    (IEEE prints many copies in B&W) and CVD readers.
  * Palette is Okabe-Ito, the standard colourblind-safe set for scientific
    figures, subset to five hues.
  * One axis per plot. No dual scales.
  * Log x on the N/G plot because the suite spans N/G from 1 to 64.

Reads the same hwdata source selector as the tables, so figures and tables
can never disagree about which dataset they came from.
"""

import os as _os
# Repo root: override with SPRS_ROOT. Defaults to this file's repo.
SPRS_ROOT = _os.environ.get("SPRS_ROOT",
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse
import csv
import datetime
import glob
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwdata

csv.field_size_limit(sys.maxsize)
P1 = _os.path.join(SPRS_ROOT,"data","results")

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

# Okabe-Ito, colourblind-safe. Marker shape duplicates the hue so identity
# never depends on colour alone.
STYLE = {
    'torus':     ('0072B2', '*',          'torus'),
    'fat_tree':  ('D55E00', 'square*',    'fat-tree'),
    'hypercube': ('009E73', 'triangle*',  'hypercube'),
    'ring':      ('CC79A7', 'diamond*',   'ring'),
    'mesh':      ('E69F00', 'pentagon*',  'mesh'),
    'linear':    ('000000', 'x',          'linear'),
}


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


def preamble(src, trusted):
    return ("% GENERATED — do not edit by hand.\n"
            "% script : scripts/gen_figures.py\n"
            f"% source : {src}\n"
            f"% metric : {'max over PEs (corrected)' if trusted else 'GPU 0 only (DEFECTIVE)'}\n"
            f"% date   : {datetime.date.today().isoformat()}\n"
            "% Colours: Okabe-Ito colourblind-safe. Marker shape duplicates hue\n"
            "% so the figure survives greyscale printing.\n")


def colordefs():
    return "\n".join(f"\\definecolor{{c{t.replace('_','')}}}{{HTML}}{{{c}}}"
                     for t, (c, _, _) in STYLE.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="figures")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    rows, src, trusted = hwdata.select()
    om = omegas()
    champ = {}
    for inst, _tb, cyc in rows:
        if inst in META and inst in om:
            if inst not in champ or cyc < champ[inst]:
                champ[inst] = cyc
    print(f"  {len(champ)} instances")

    bytopo = defaultdict(list)
    for inst, c in champ.items():
        n, g, t = META[inst]
        bytopo[t].append((n, g, n / g, c / om[inst], inst))

    # ---------- Figure 1: distance to Omega, ordered by N ----------
    f = [preamble(src, trusted), colordefs(), "",
         r"\begin{tikzpicture}", r"\begin{axis}[",
         r"  width=\columnwidth, height=6.2cm,",
         r"  xmode=log, log basis x=2,",
         r"  xlabel={leaf count $N$}, ylabel={champion cycles $/\ \Omega$},",
         r"  ymin=0.9,",
         r"  grid=major, major grid style={gray!20},",
         r"  legend style={font=\scriptsize, at={(0.5,1.02)}, anchor=south,",
         r"                legend columns=3, draw=none, fill=none},",
         r"  tick label style={font=\footnotesize},",
         r"  label style={font=\footnotesize},",
         r"  mark options={scale=0.9}]"]
    for t in ['torus', 'fat_tree', 'hypercube', 'ring', 'mesh', 'linear']:
        pts = sorted(bytopo.get(t, []))
        if not pts:
            continue
        col, mark, lab = STYLE[t]
        coords = " ".join(f"({n},{r:.3f})" for n, g, ng, r, _ in pts)
        f.append(f"\\addplot+[only marks, mark={mark}, "
                 f"color=c{t.replace('_','')}] coordinates {{{coords}}};")
        f.append(f"\\addlegendentry{{{lab}}}")
    f += [r"\end{axis}", r"\end{tikzpicture}"]
    open(f"{a.out}/omega_by_instance.tex", "w").write("\n".join(f) + "\n")
    print(f"  wrote {a.out}/omega_by_instance.tex")

    # ---------- Figure 2: N/G inflection ----------
    allpts = [(ng, r) for v in bytopo.values() for _, _, ng, r, _ in v]
    ymax = max(r for _, r in allpts) * 1.1 if allpts else 4
    f = [preamble(src, trusted), colordefs(), "",
         r"\begin{tikzpicture}", r"\begin{axis}[",
         r"  width=\columnwidth, height=5.8cm,",
         r"  xmode=log, log basis x=2,",
         r"  xlabel={$N/G$ (leaves per PE)}, ylabel={champion cycles $/\ \Omega$},",
         f"  ymin=0.9, ymax={ymax:.2f},",
         r"  grid=major, major grid style={gray!20},",
         r"  legend style={font=\scriptsize, at={(0.5,1.02)}, anchor=south,",
         r"                legend columns=3, draw=none, fill=none},",
         r"  tick label style={font=\footnotesize},",
         r"  label style={font=\footnotesize},",
         r"  mark options={scale=0.9}]",
         # predicted inflection band
         r"\addplot[draw=none, fill=gray!14, forget plot]"
         f" coordinates {{(6,0.9) (8,0.9) (8,{ymax:.2f}) (6,{ymax:.2f})}}"
         r" \closedcycle;"]
    for t in ['torus', 'fat_tree', 'hypercube', 'ring', 'mesh', 'linear']:
        pts = bytopo.get(t, [])
        if not pts:
            continue
        col, mark, lab = STYLE[t]
        coords = " ".join(f"({ng:.4f},{r:.3f})" for _, _, ng, r, _ in sorted(pts, key=lambda x: x[2]))
        f.append(f"\\addplot+[only marks, mark={mark}, "
                 f"color=c{t.replace('_','')}] coordinates {{{coords}}};")
        f.append(f"\\addlegendentry{{{lab}}}")
    f += [r"\node[font=\scriptsize, anchor=south] at (axis cs:6.9,"
          f"{ymax*0.94:.2f}" r") {predicted};",
          r"\end{axis}", r"\end{tikzpicture}"]
    open(f"{a.out}/ng_inflection.tex", "w").write("\n".join(f) + "\n")
    print(f"  wrote {a.out}/ng_inflection.tex")

    if not trusted:
        print("\n  *** figures carry the DEFECTIVE metric — regenerate after "
              "re-measurement ***", file=sys.stderr)


if __name__ == "__main__":
    main()
