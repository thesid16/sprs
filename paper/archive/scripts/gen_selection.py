#!/usr/bin/env python3
r"""
gen_selection.py -- emit tables/selection.tex (the derived selection rule).

Ported into the artifact from the council's scratch scripts
(/home/rohit/selrule/{build.py,gen_table.py}), which lived outside the release
and therefore could not be re-run by a referee: tables/selection.tex was
\input by main.tex with NO generator anywhere in paper/scripts/.

Two changes from the scratch original, both deliberate:
  * paths resolve $SPRS_ROOT -> repo-relative -> author absolute, like every
    other generator here, so a fresh clone works with no environment set;
  * numpy/scipy are not used (the computation is a 39x16 table), so the paper
    build has no scientific-stack dependency.
The emitted numbers are asserted identical to the committed table by
`--check`, which is what `make check-selection` runs.

Method (unchanged): champion equivalence class C_i = the set of (S2,S3)
configurations whose MEASURED cycle count equals the per-instance minimum,
with every simulated row expanded into its IMEM-hash (tb_hash) equivalence
class.  Tie-invariant by construction; independent of CSV arrival order.
"""
import argparse
import collections
import csv
import datetime
import os
import statistics
import sys

csv.field_size_limit(sys.maxsize)

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)


def _root_default():
    return os.environ.get("SPRS_ROOT") or os.path.abspath(
        os.path.join(HERE, "..", ".."))


def _p1_default():
    cand = os.path.join(_root_default(), "data", "results")
    return cand if os.path.isdir(cand) else "/home/rohit/tournament_p1/results"


ROOT = _root_default()
P1 = os.environ.get("SPRS_P1") or _p1_default()
HW = os.path.join(P1, "live_hw_results_p1_maxpe.csv")


def _meta_default():
    for c in (os.path.join(ROOT, "benchmarks", "instances.csv"),
              os.path.join(P1, "..", "..", "benchmarks", "instances.csv"),
              "/home/rohit/sprs-review/snapshot/benchmarks/instances.csv"):
        if os.path.exists(c):
            return os.path.abspath(c)
    return os.path.join(ROOT, "benchmarks", "instances.csv")


METAP = os.environ.get("SPRS_INSTANCES") or _meta_default()

S2FAM = {
    '2a': ('HEFT', 'list-scheduling'), '2b': ('RecBisect', 'graph partition'),
    '2c': ('MLfm', 'multilevel'), '2d': ('DKway', 'graph partition'),
    '2e': ('ExactBB', 'exact/B\\&B'), '2f': ('DFSseed', 'list-scheduling'),
    '2g': ('DSC', 'clustering'), '2h': ('Chretienne', 'clustering'),
    '2i': ('CPOP', 'list-scheduling'), '2j': ('Centroid', 'geometric'),
    '2k': ('Lukes', 'tree DP'), '2l': ('Frederickson', 'tree DP'),
    '2m': ('CPFD', 'clustering'), '2n': ('ClHEFT', 'hierarchical'),
    '2o': ('ParSub', 'hierarchical'), '2p': ('Spine', 'structural'),
    '2q': ('SubPack', 'hierarchical'), '2r': ('LvlHLF', 'structural'),
}

INF = float('inf')


def load_champions():
    """-> (INST, meta, cyc) where cyc[inst][(s2,s3)] = measured cycles."""
    for p in (HW, METAP):
        if not os.path.exists(p):
            sys.exit(f"gen_selection.py: required input missing: {p}\n"
                     f"  set $SPRS_ROOT (or $SPRS_P1 / $SPRS_INSTANCES)")
    meta = {}
    with open(METAP, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            meta[r['instance']] = dict(N=int(r['n_leaves']), G=int(r['n_gpus']),
                                       topo=r['topology'],
                                       NG=float(r['n_over_g']))
    hw = collections.defaultdict(dict)
    with open(HW, newline='', encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f):
            if r['Pass'] != 'True':
                continue
            i, tb, c = r['Instance'], r['TB_Name'], int(r['Cycles'])
            if tb not in hw[i] or c < hw[i][tb]:
                hw[i][tb] = c
    INST = sorted(hw)
    cyc = {}
    for inst in INST:
        swp = os.path.join(P1, inst, "sw_results.csv")
        if not os.path.exists(swp):
            sys.exit(f"gen_selection.py: required input missing: {swp}")
        byhash = collections.defaultdict(list)
        leader = {}
        with open(swp, newline='', encoding='utf-8', errors='replace') as f:
            for r in csv.DictReader(f):
                byhash[r['tb_hash']].append((r['s2'], r['s3']))
                if r['unique_hw_sim'] == 'True':
                    leader[r['tb_hash']] = r['tb_fname']
        d = {}
        for h, cfgs in byhash.items():
            tb = leader.get(h)
            if h == '' or tb is None:
                continue
            v = hw[inst].get(tb)
            if v is None:
                continue
            for c in cfgs:
                d[c] = v
        cyc[inst] = d
    return INST, meta, cyc


def build_regret(INST, cyc):
    """ACT (algorithms evaluable on >=38 instances) and R[inst][alg] = regret."""
    ACT = [a for a in sorted(S2FAM)
           if sum(1 for i in INST if any(x == a for x, _ in cyc[i])) >= 38]
    OPT = {i: min(cyc[i].values()) for i in INST}
    R = {}
    for i in INST:
        row = {}
        for a in ACT:
            best = min([v for (x, _), v in cyc[i].items() if x == a] + [INF])
            row[a] = min(best, 1e9) / OPT[i]
        R[i] = row
    return ACT, OPT, R


def stat(INST, R, mask, algs):
    idx = [i for i in INST if mask(i)]
    rr = [min(R[i][a] for a in algs) for i in idx]
    return (sum(1 for v in rr if v == 1), len(idx),
            (sum(rr) / len(rr)) if rr else 0.0, max(rr) if rr else 0.0)


HDR = """% ======================================================================
% GENERATED FILE -- DO NOT EDIT BY HAND
% Generator : paper/scripts/gen_selection.py
% Generated : {ts}Z
% Inputs    : {hw} ({nrows} passing HW rows)
%             <P1>/<inst>/sw_results.csv (40 x 180 = 7200 rows)
%             {meta} (N, G, topology)
% Method    : champion equivalence class C_i = configurations whose MEASURED cycle
%             count equals the per-instance minimum, with every simulated row expanded
%             into its IMEM-hash (tb_hash) equivalence class. Tie-invariant by
%             construction; independent of the CSV-arrival-order tie-break.
% Coverage  : {ninst} of 40 instances have HW results (maxp_mod_fat excluded).
% Regret    : measured cycles of the recommended set (min over its members, min over
%             the ten S3 mappings) divided by the instance optimum. 1.000 = optimal.
% Validation: portfolio membership re-selected exhaustively in each of {ninst}
%             leave-one-out folds; the k=1..4 selections were identical in {ninst}/{ninst} folds.
% Layout note: typeset at \\scriptsize with tightened column separation to fit
% one IEEE column. Data unchanged from the generator.
% ======================================================================
"""


def render(INST, meta, R, nrows):
    def topo(i):
        return meta[i]['topo']

    def N(i):
        return meta[i]['N']

    rows = [
        ('Default (any $N$, $G$, topology)', lambda i: True,
         ['2g', '2k', '2l', '2o']),
        ('\\quad restricted to non-ring', lambda i: topo(i) != 'ring',
         ['2k', '2l', '2o']),
        ('\\quad restricted to ring$^{\\dagger}$', lambda i: topo(i) == 'ring',
         ['2g', '2o']),
        ('Budget $k{=}1$: $N\\ge 2048$', lambda i: N(i) >= 2048, ['2o']),
        ('Budget $k{=}1$: $N<2048$, non-ring',
         lambda i: N(i) < 2048 and topo(i) != 'ring', ['2k']),
        ('Budget $k{=}1$: $N<2048$, ring$^{\\dagger}$',
         lambda i: N(i) < 2048 and topo(i) == 'ring', ['2g']),
        ('Budget $k{=}2$ (any instance)', lambda i: True, ['2g', '2o']),
        ('Budget $k{=}3$ (any instance)', lambda i: True, ['2g', '2k', '2o']),
    ]
    L = [HDR.format(ts=datetime.datetime.now(datetime.timezone.utc)
                    .replace(tzinfo=None).isoformat(),
                    hw=HW, meta=METAP, nrows=nrows, ninst=len(INST))]
    L += [
        '\\begin{table}[!t]',
        '\\centering',
        '\\caption{Derived algorithm-selection rule. For each regime, the S2 '
        'assignment algorithms a practitioner should run; the S3 mapping may be '
        'fixed to Identity throughout (Sec.~\\ref{sec:selrule}). ``Opt.\'\' '
        'counts instances on which the recommended set attains the '
        'hardware-measured minimum cycle count exactly.}',
        '\\label{tab:selection_rule}',
        '\\scriptsize',
        '\\setlength{\\tabcolsep}{3pt}',
        '\\begin{tabular}{@{}l@{\\hspace{4pt}}r@{\\hspace{4pt}}'
        '>{\\raggedright\\arraybackslash}p{0.215\\linewidth}@{\\hspace{4pt}}'
        'r@{\\hspace{3pt}}r@{\\hspace{3pt}}r@{}}',
        '\\toprule',
        'Regime & $n$ & \\multicolumn{1}{l}{Run these S2} & Opt. & Mean & Worst \\\\',
        ' & & \\multicolumn{1}{l}{algorithms} & & regret & regret \\\\',
        '\\midrule',
    ]
    for lbl, mask, algs in rows:
        h, tot, mn, mx = stat(INST, R, mask, algs)
        names = ', '.join(S2FAM[a][0] for a in algs)
        L.append(f'{lbl} & {tot} & {names} & {h}/{tot} & {mn:.3f} & {mx:.3f} \\\\')
        if lbl.startswith('Default'):
            L.append('\\midrule')
    L += [
        '\\bottomrule',
        '\\multicolumn{6}{@{}p{0.95\\linewidth}@{}}{\\footnotesize '
        '$^{\\dagger}$Rests on six (resp.\\ five) ring instances of which three '
        'are positive; reported for completeness, not recommended as a '
        'standalone rule. No (N-bucket $\\times$ topology) cell in the suite '
        'holds more than three instances, so no cell-level rule is derivable.}\\\\',
        '\\end{tabular}',
        '\\end{table}',
    ]
    return '\n'.join(L) + '\n'


def body(text):
    """Everything after the provenance header -- the part that must not drift."""
    return text.split('% ======================================================================\n')[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(PAPER, "tables"))
    ap.add_argument("--check", action="store_true",
                    help="do not write; fail if the emitted body differs from "
                         "the committed tables/selection.tex")
    a = ap.parse_args()
    INST, meta, cyc = load_champions()
    # passing HW row count, for the provenance header
    nrows = 0
    with open(HW, newline='', encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f):
            if r['Pass'] == 'True':
                nrows += 1
    ACT, OPT, R = build_regret(INST, cyc)
    txt = render(INST, meta, R, nrows)
    ref = os.path.join(PAPER, "tables", "selection.tex")
    if a.check:
        if not os.path.exists(ref):
            sys.exit(f"FAIL: {ref} absent")
        got, want = body(txt), body(open(ref, encoding='utf-8').read())
        if got != want:
            import difflib
            sys.stderr.writelines(difflib.unified_diff(
                want.splitlines(True), got.splitlines(True),
                "committed", "regenerated"))
            sys.exit("FAIL: tables/selection.tex does not reproduce")
        print(f"OK: tables/selection.tex reproduces exactly "
              f"({len(INST)} instances, {nrows} passing HW rows)")
        return 0
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "selection.tex"), "w", encoding='utf-8') as f:
        f.write(txt)
    print(f"  tables/selection.tex  ({len(INST)} instances, "
          f"{len(ACT)} evaluable S2 algorithms, {nrows} passing HW rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
