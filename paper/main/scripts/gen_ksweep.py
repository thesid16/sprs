#!/usr/bin/env python3
r"""
gen_ksweep.py -- tables/ksweep.tex, the portfolio-size sweep behind the
selection rule.

The manuscript reports the k=4 portfolio and its leave-one-out regret; the
sweep that justifies stopping at four, and the bootstrap intervals that say how
much of the held-out number is real given only 39 instances, existed only as a
figure.  This is the table.

Inputs, in resolution order:
  $SPRS_W9  or  $SPRS_ROOT/experiments/w_final/W9_selection/   (where the
            experiment ran: RESULT_ksweep.json, RESULT.json)
  <paper>/data/council/W9_KSWEEP.json, W9_SELECTION.json       (vendored, so a
            fresh clone of the paper alone still regenerates the table)

Nothing here recomputes the sweep: the regret numbers and bootstrap intervals
are read verbatim from the experiment's own JSON (B = 2000 resamples of the 39
instances, seed 20260828, percentile interval -- see w9b_ksweep_ci.py).

What IS recomputed, from the released HW CSV, is the greedy portfolio
membership at each k, because the JSON does not record it and a table of
regrets without the algorithm names is not usable.  The recomputation reuses
gen_selection.py's loader and regret matrix, and the script FAILS if the greedy
k=4 set is not the four algorithms the manuscript recommends -- so this table
cannot quietly disagree with tables/selection.tex.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_tablestyle as ts
import gen_selection as GS

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
ROOT = os.environ.get("SPRS_ROOT") or os.path.abspath(os.path.join(PAPER, ".."))

# The four the manuscript recommends (tables/selection.tex, "Default" row).
SHIPPED_K4 = {"2g", "2k", "2l", "2o"}


def _find(*names):
    cands = []
    w9 = os.environ.get("SPRS_W9")
    if w9:
        cands.append(w9)
    cands.append(os.path.join(ROOT, "experiments", "w_final", "W9_selection"))
    out = []
    for want, vendored in names:
        got = None
        for d in cands:
            p = os.path.join(d, want)
            if os.path.exists(p):
                got = p
                break
        if got is None:
            p = os.path.join(PAPER, "data", "council", vendored)
            if os.path.exists(p):
                got = p
        if got is None:
            sys.exit(f"gen_ksweep.py: required input missing: {want}\n"
                     f"  looked in {cands} and data/council/{vendored}\n"
                     f"  set $SPRS_W9 or $SPRS_ROOT")
        out.append(got)
    return out


def greedy(ACT, R, INST, k):
    """The same greedy portfolio w9b_ksweep_ci.py builds, on all 39 instances."""
    sel = []
    for _ in range(k):
        sel.append(min((a for a in ACT if a not in sel),
                       key=lambda a: sum(min(R[i][x] for x in sel + [a])
                                         for i in INST)))
    return sel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(PAPER, "tables"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    ksw_p, sel_p = _find(("RESULT_ksweep.json", "W9_KSWEEP.json"),
                         ("RESULT.json", "W9_SELECTION.json"))
    with open(ksw_p, encoding="utf-8") as f:
        KS = json.load(f)
    with open(sel_p, encoding="utf-8") as f:
        SEL = json.load(f)

    sweep = {int(k): v for k, v in KS["k_sweep"].items()}
    ci = KS["bootstrap_ci"]

    # ---- membership, recomputed from the released CSV ----------------------
    INST, meta, cyc = GS.load_champions()
    ACT, OPT, R = GS.build_regret(INST, cyc)
    if len(ACT) != KS["n_algorithms"]:
        sys.exit(f"gen_ksweep.py: {len(ACT)} evaluable algorithms from the CSV "
                 f"but the sweep JSON was computed over {KS['n_algorithms']}; "
                 f"the two are not describing the same experiment.")
    if len(INST) != SEL["n_instances"]:
        sys.exit(f"gen_ksweep.py: {len(INST)} instances from the CSV but the "
                 f"selection JSON has {SEL['n_instances']}.")
    order = greedy(ACT, R, INST, max(sweep))
    if set(order[:4]) != SHIPPED_K4:
        sys.exit(f"gen_ksweep.py: greedy k=4 is {sorted(order[:4])}, but "
                 f"tables/selection.tex recommends {sorted(SHIPPED_K4)}. "
                 f"One of the two is wrong; refusing to emit a table that "
                 f"disagrees with the manuscript's own rule.")

    ks = sorted(sweep)
    lo_ax = min([ci[k]["lo"] for k in ci] + [1.0])
    hi_ax = max([ci[k]["hi"] for k in ci] +
                [sweep[k]["loo_mean"] for k in ks] +
                [sweep[k]["topo_mean"] for k in ks])
    excess_max = max(max(sweep[k]["loo_mean"], sweep[k]["topo_mean"])
                     for k in ks) - 1.0

    loo_m = ts.align_decimal([f"{sweep[k]['loo_mean']:.4f}" for k in ks])
    loo_o = ts.align_decimal([f"{sweep[k]['loo_pct_opt']:.1f}" for k in ks])
    top_m = ts.align_decimal([f"{sweep[k]['topo_mean']:.4f}" for k in ks])
    top_o = ts.align_decimal([f"{sweep[k]['topo_pct_opt']:.1f}" for k in ks])

    def cicell(k, proto):
        key = f"k{k}_{proto}"
        if key not in ci:
            return r"\multicolumn{2}{c}{" + ts.band("") + "}" if False else \
                   r"\multicolumn{2}{c}{---}"
        d = ci[key]
        return (f"{d['lo']:.4f} & {d['hi']:.4f} "
                f"{ts.span(d['lo'], d['hi'], lo_ax, hi_ax, 'spVerm', 3.0)}")

    tab = [r"\begin{tabular}{@{}c l r@{\ }l r r@{\,--\,}l r@{\ }l r "
           r"r@{\,--\,}l@{}}",
           r"\toprule",
           ts.band(ts.HEAD) +
           r" & & \multicolumn{5}{c}{\sphd{Leave-one-out}} & "
           r"\multicolumn{5}{c}{\sphd{Held-out topology}} \\",
           r"\cmidrule(lr){3-7}\cmidrule(l){8-12}",
           ts.band(ts.HEAD) +
           r"\sphd{$k$} & \sphd{Algorithm added at this $k$} & "
           r"\multicolumn{2}{c}{\sphd{Mean regret}} & \sphd{Opt.\ (\%)} & "
           r"\multicolumn{2}{c}{\sphd{95\% CI}} & "
           r"\multicolumn{2}{c}{\sphd{Mean regret}} & \sphd{Opt.\ (\%)} & "
           r"\multicolumn{2}{c}{\sphd{95\% CI}} \\",
           r"\midrule"]
    for i, k in enumerate(ks):
        name = GS.S2FAM[order[k - 1]][0]
        mark = ""
        if k == 4:
            mark = r"$^{\star}$"
        tab.append(
            f"{ts.zebra(i)}{k} & \\sv{{{name}}}{mark} & "
            f"{loo_m[i]} & "
            f"{ts.bar(sweep[k]['loo_mean'] - 1.0, excess_max, 'spBlue', 2.6)} & "
            f"{loo_o[i]} & {cicell(k, 'LOO')} & "
            f"{top_m[i]} & "
            f"{ts.bar(sweep[k]['topo_mean'] - 1.0, excess_max, 'spBlue', 2.6)} & "
            f"{top_o[i]} & {cicell(k, 'unseen-topology')} \\\\")
    tab += [r"\bottomrule", r"\end{tabular}"]

    k4 = ci["k4_LOO"]
    k4t = ci["k4_unseen-topology"]
    cap = (
        r"\caption{Portfolio-size sweep for the selection rule of "
        r"Sec.~\ref{sec:selrule}, over the \TournNInst{} HW-validated "
        r"instances and the " + str(len(ACT)) + r" S2 algorithms evaluable on "
        r"almost all of them. Regret is measured cycles of the portfolio's best "
        r"member divided by the instance optimum, so $1.0000$ is optimal; "
        r"algorithms are added greedily, so each row is the row above plus one. "
        r"Bars encode mean regret above optimal on a common axis "
        rf"($0$--{100 * excess_max:.1f}\%); intervals are percentile bootstrap "
        r"over the \TournNInst{} instances ($B=2000$, seed 20260828) and were "
        r"computed for $k=2$--$5$ only. $^{\star}$ marks the shipped portfolio. "
        r"The one thing to take from it: $k=4$ is the knee --- a fifth "
        rf"algorithm changes nothing ($k{{=}}5$ is identical), the leave-one-out "
        rf"interval [{k4['lo']:.4f}, {k4['hi']:.4f}] already reaches the "
        r"optimum, and even on a topology the portfolio has never seen the mean "
        rf"cost is {k4t['mean']:.4f} against {sweep[1]['loo_mean']:.4f} for the "
        r"best single algorithm.}")

    out = [r"\begin{table*}[!t]", cap, r"\label{tab:ksweep}", r"\centering",
           r"\footnotesize", r"\renewcommand{\arraystretch}{1.18}"]
    out += ts.wrap(tab)
    out += [r"\end{table*}"]

    hdr = ("% GENERATED — do not edit by hand.\n"
           "% script : scripts/gen_ksweep.py\n"
           f"% source : {ksw_p}\n"
           f"%          {sel_p}\n"
           "%          portfolio membership recomputed from the released HW CSV\n"
           "%          via gen_selection.load_champions/build_regret\n"
           f"% date   : {datetime.date.today().isoformat()}\n"
           f"% note   : greedy order {', '.join(GS.S2FAM[x][0] for x in order)};"
           f" k=4 set asserted equal to the shipped portfolio\n")
    with open(os.path.join(a.out, "ksweep.tex"), "w", encoding="utf-8") as f:
        f.write(hdr + "\n".join(out) + "\n")
    print(f"  tables/ksweep.tex  (k=1..{max(ks)}, {len(ACT)} algorithms, "
          f"{len(INST)} instances; greedy k=4 matches the shipped portfolio)")


if __name__ == "__main__":
    main()
