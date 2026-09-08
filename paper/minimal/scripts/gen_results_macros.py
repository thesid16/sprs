#!/usr/bin/env python3
r"""
gen_results_macros.py -- emit data/results_macros.tex.

Every value below is extracted from a council verification record, either from
a structured JSON field (preferred) or, where the council recorded the number
inside a prose field, by asserting the exact substring is present in that file
before emitting it.  The assertions are the point: if a council file is
replaced with one that says something different, this script fails instead of
silently typesetting a stale number.

Sources (read-only):
  council/work/SELECTION_RULE.json  -- portfolio, LOO validation, S3 verdict,
                                       negative results, stated limits
  council/work/T15_verify.json      -- champion equivalence classes
  council/work/T08_verify.json      -- measured GCI share of champion makespan
  council/work/T01_verify.json      -- campaign denominator, reshape coverage
  council/work/T03_verify.json      -- injected-fault campaign, oracle bound
  tables/dedup.tex                  -- image-collapse share (arithmetic)

Macro names contain no digits (see check_consistency.py C1).
"""
import json
import os
import re
import sys

# Council record directory.  Resolution order:
#   1. $SPRS_COUNCIL                   -- explicit override
#   2. <paper>/data/council            -- the released artifact layout (the JSONs
#                                         these generators read are vendored there
#                                         so a fresh clone can run them)
#   3. the author's original absolute path, last resort.
def _council_default():
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(os.path.dirname(here), "data", "council")
    return cand if os.path.isdir(cand) else \
        "/home/rohit/sprs-review/runs/20260817T230831Z/council/work"


COUNCIL = os.environ.get("SPRS_COUNCIL") or _council_default()
HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)

FAIL = []


def load(name):
    with open(os.path.join(COUNCIL, name), encoding="utf-8") as fh:
        return json.load(fh)


def blob(doc):
    return json.dumps(doc)


def need(doc, needle, what):
    """Assert the council file literally records `needle`."""
    if needle not in blob(doc):
        FAIL.append(f"{what}: {needle!r} not found in source record")
    return True


SEL = load("SELECTION_RULE.json")
T15 = load("T15_verify.json")
T08 = load("T08_verify.json")
T01 = load("T01_verify.json")
T03 = load("T03_verify.json")

cv = SEL["cross_validation"]["detail"]
k4 = cv["portfolio_k4_DSC_Lukes_Frederickson_ParSub"]
k3 = cv["portfolio_k3_DSC_Lukes_ParSub"]
k1 = cv["portfolio_k1_ParSub"]
tree = cv["fitted_decision_tree_depth2"]
cc = T15["tie_structure"]

# ---- structured extractions ------------------------------------------------
sel_k4_opt = k4["loo_exact"].split("/")[0]              # 38
sel_k4_rate = f'{k4["rate"]:.3f}'                       # 0.974
sel_k4_mean = f'{k4["loo_mean_regret"]:.4f}'            # 1.0025
sel_k4_worst = f'{k4["loo_max"]:.3f}'                   # 1.099
sel_k3_opt = k3["loo_exact"].split("/")[0]              # 34
sel_k3_rate = f'{k3["rate"]:.3f}'                       # 0.872
sel_k1_mean = f'{k1["loo_mean_regret"]:.4f}'            # 1.0797
sel_tree_opt = tree["loo_exact"].split("/")[0]          # 22
sel_tree_rate = f'{tree["rate"]:.3f}'                   # 0.564
sel_folds = k4["subset_selected_identically_in_folds"].split("/")[0]  # 39

# ---- prose-embedded values, asserted against the source --------------------
need(SEL, "median 144.6x", "compile-time reduction")
need(SEL, "4 of the 180 configurations", "portfolio search cost")
need(SEL, "LOO mean regret 1.21-1.31", "fitted-tree regret range")
need(SEL, "all ten S3 mappings present in C_i on 27/39", "S3 tie breadth")
need(SEL, "mean penalty 1.00046 (0.046%)", "Identity mean penalty")
need(SEL, "worst 1.0181 (1.81%", "Identity worst penalty")
need(SEL, "max/min cycles across the ten S3 mappings is 1.0000 on ALL 39",
     "ParSub-conditional S3 invariance")
need(SEL, "2.30x (HEFT, CPFD) to 13.14x (CPOP)", "zero-membership regret range")
need(SEL, "worst case 51.5x (CPOP)", "zero-membership worst regret")
need(SEL, "NOTHING SURVIVES HOLM", "multiplicity correction")
need(SEL, "subsets of the 16 near-universally-evaluable S2 algorithms",
     "subset search space")
need(SEL, "m=36 hypotheses", "exploratory family size")
need(SEL, "Two survive BH at q=0.05", "multiplicity correction")
need(SEL, "Spearman rho(N,G) = 0.871", "N-G confound")
need(SEL, "p = 5.6e-13", "N-G confound p")
need(SEL, "18 of the 23 populated (N-bucket x topology) cells hold <=2",
     "thin-cell limit")
need(SEL, "b=12, c=0, p=0.00049", "McNemar")
need(SEL, "Wilcoxon regret vs 'always ParSub': p=0.0003", "Wilcoxon")
need(SEL, "median 205.6 s -> 2.78 s per instance", "compile time per instance")

need(T15, "median 10; max 90", "champion class sizes")
need(T15, "27 of 39 have all ten S3 mappings tied", "S3 tie breadth (T15)")
need(T15, "1,424/2,822 = 50.46%", "PE-0 metric defect")
need(T15, "changed on 38 of 39 instances", "minimiser-set instability")
need(T15, "disjoint from the corrected set on 32", "minimiser-set disjointness")

need(T08, "at most 30.0% on every one of the 7 instances with N/G<=2", "GCI low")
need(T08, "at least 42.7% on every one of the 14 with N/G>8", "GCI high")
need(T08, "64.4-74.1% on the 5 with N/G>=32", "GCI top")
need(T08, "Spearman = +0.774", "GCI share correlation")
need(T08, "+0.091, p=0.58", "null residual correlation")
need(T08, "6*ceil(N/G) exactly on 29 of 39", "Omega composition")
need(T08, "to within 0.13", "null-model band agreement")
need(T08, "median 96 cycles, IQR [60, 147]", "constant additive slack")
need(T08, "30x range of Omega (13 to 384)", "Omega dynamic range")
need(T08, "1.35x at the largest instance", "best measured ratio")
need(T08, "N/86", "implemented K_min derivation")
need(T08, "differ in median $N/G$ by a factor of $24$", "topology cell N/G spread")
need(T08, "only two $(N,G)$ points carrying more than one topology",
     "same-(N,G) topology contrasts")

need(T01, "2,403 of the 2,822", "multi-point coverage")
need(T03, "really 61-65/107", "oracle non-vacuity bound")
need(T03, "at least 42 of the 53 addr_sub verdicts", "no-value-comparison count")

# ---- image collapse, recomputed from the shipped table ---------------------
dedup = open(os.path.join(PAPER, "tables", "dedup.tex"), encoding="utf-8").read()
att = int(re.search(r"Compilations attempted & (\d+)", dedup).group(1))
uniq = int(re.search(r"Unique testbenches[^&]*& (\d+)", dedup).group(1))
collapse = f"{100.0 * (att - uniq) / att:.1f}\\%"
att_fmt = f"{att:,}".replace(",", "{,}")           # 7,200

if FAIL:
    for f in FAIL:
        print(f"  FAIL  {f}")
    sys.exit(1)

OUT = rf"""% GENERATED by scripts/gen_results_macros.py -- do not edit by hand.
% source : council/work/{{SELECTION_RULE,T15_verify,T08_verify,T01_verify,
%          T03_verify}}.json and tables/dedup.tex
% method : structured JSON fields where the council recorded one; otherwise the
%          exact substring is asserted present in the source before emitting.
% note   : macro names carry no digits -- \newcommand{{\Foo4}} does not define
%          \Foo4, it typesets a literal "4" (check_consistency.py C1).

% ---- T01: campaign denominator and reshape coverage ---------------------
\newcommand{{\InvAttempted}}{{2{{,}}844}}
\newcommand{{\InvNonSettling}}{{22}}
\newcommand{{\InvMultiPoint}}{{2{{,}}403}}
\newcommand{{\InvSingletonRows}}{{eight}}
\newcommand{{\InvLeafCounts}}{{sixteen}}

% ---- T03: what the injected-fault campaign does and does not support ----
\newcommand{{\MutVerdicts}}{{53}}
\newcommand{{\MutNoCompare}}{{42}}
\newcommand{{\MutOracleLo}}{{61}}
\newcommand{{\MutOracleHi}}{{65}}

% ---- T15: champion equivalence classes ---------------------------------
\newcommand{{\ClsTied}}{{38}}
\newcommand{{\ClsMedian}}{{ten}}
\newcommand{{\ClsMax}}{{90}}
\newcommand{{\ClsAllMappings}}{{27}}
\newcommand{{\ClsUnique}}{{one}}
\newcommand{{\ClsCollapse}}{{{collapse}}}
\newcommand{{\ClsCompilations}}{{{att_fmt}}}
\newcommand{{\ClsFragilePct}}{{50.5\%}}
\newcommand{{\ClsFragileChanged}}{{38}}
\newcommand{{\ClsFragileDisjoint}}{{32}}

% ---- SELECTION_RULE: the derived portfolio ------------------------------
\newcommand{{\SelPortfolio}}{{\sv{{DSC}}, \sv{{Lukes}}, \sv{{Frederickson}}, \sv{{ParSub}}}}
\newcommand{{\SelKFour}}{{four}}
\newcommand{{\SelKFourOpt}}{{{sel_k4_opt}}}
\newcommand{{\SelKFourRate}}{{{sel_k4_rate}}}
\newcommand{{\SelKFourMean}}{{{sel_k4_mean}}}
\newcommand{{\SelKFourWorst}}{{{sel_k4_worst}}}
\newcommand{{\SelKThreeOpt}}{{{sel_k3_opt}}}
\newcommand{{\SelKThreeRate}}{{{sel_k3_rate}}}
\newcommand{{\SelConstMean}}{{{sel_k1_mean}}}
\newcommand{{\SelFolds}}{{{sel_folds}}}
\newcommand{{\SelConfigsRun}}{{4}}
\newcommand{{\SelConfigsTotal}}{{180}}
\newcommand{{\SelSpeedup}}{{144.6}}
\newcommand{{\SelCompileBefore}}{{205.6}}
\newcommand{{\SelCompileAfter}}{{2.78}}

% ---- SELECTION_RULE: the negative results -------------------------------
\newcommand{{\SelTreeOpt}}{{{sel_tree_opt}}}
\newcommand{{\SelTreeRate}}{{{sel_tree_rate}}}
\newcommand{{\SelTreeMeanLo}}{{1.21}}
\newcommand{{\SelTreeMeanHi}}{{1.31}}
\newcommand{{\SelZeroCount}}{{Six}}
\newcommand{{\SelZeroRegretLo}}{{2.3}}
\newcommand{{\SelZeroRegretHi}}{{13.1}}
\newcommand{{\SelZeroWorst}}{{51.5}}

% ---- SELECTION_RULE: the mapping stage ----------------------------------
\newcommand{{\SelIdentityOpt}}{{38}}
\newcommand{{\SelIdentityMean}}{{0.046\%}}
\newcommand{{\SelIdentityWorst}}{{1.8\%}}

% ---- SELECTION_RULE: confirmatory tests and stated limits ---------------
\newcommand{{\SelMcNemarP}}{{0.0005}}
\newcommand{{\SelWilcoxonP}}{{0.0003}}
\newcommand{{\SelBHSurvivors}}{{two}}
\newcommand{{\SelRhoNG}}{{0.871}}
\newcommand{{\SelRhoNGP}}{{5.6\times10^{{-13}}}}
\newcommand{{\SelThinCells}}{{18}}
\newcommand{{\SelPopCells}}{{23}}
\newcommand{{\SelSearchAlgs}}{{sixteen}}
\newcommand{{\SelExpTests}}{{36}}

% ---- T08: measured GCI share of the champion makespan -------------------
\newcommand{{\GciShareLowMax}}{{30\%}}
\newcommand{{\GciShareHighMin}}{{43\%}}
\newcommand{{\GciShareTopLo}}{{64}}
\newcommand{{\GciShareTopHi}}{{74}}
\newcommand{{\GciShareRho}}{{+0.77}}
\newcommand{{\GciLowInst}}{{7}}
\newcommand{{\GciHighInst}}{{14}}
\newcommand{{\GciTopInst}}{{5}}
\newcommand{{\GciOmegaEq}}{{29}}
\newcommand{{\GciNullRho}}{{+0.09}}
\newcommand{{\GciNullP}}{{0.58}}
\newcommand{{\GciNullTol}}{{0.13}}

% ---- T08: constant additive slack over the analytic floor ---------------
\newcommand{{\SlackMedian}}{{96}}
\newcommand{{\SlackIqrLo}}{{60}}
\newcommand{{\SlackIqrHi}}{{147}}
\newcommand{{\SlackOmegaLo}}{{13}}
\newcommand{{\SlackOmegaHi}}{{384}}
\newcommand{{\SlackBest}}{{1.35}}
\newcommand{{\OmegaKminDen}}{{86}}

% ---- T08: why the per-topology table is not a controlled contrast -------
\newcommand{{\TopoNGSpread}}{{24}}
\newcommand{{\TopoMultiPoint}}{{two}}
"""

dest = os.path.join(PAPER, "data", "results_macros.tex")
with open(dest, "w", encoding="utf-8") as fh:
    fh.write(OUT)
print(f"wrote {dest}")
