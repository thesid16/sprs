#!/usr/bin/env python3
"""
W9 -- generalization of the selection rule.

The shipped validation (gen_selection.py HDR "Validation:") establishes that
PORTFOLIO MEMBERSHIP is stable: re-selected in each of 39 leave-one-out folds,
the k=1..4 choices were identical in 39/39. That is stability, and because the
selected set never changes, in-sample and LOO regret of the portfolio coincide.

It does NOT establish the claim the project set out to make -- "tell which
algorithm to use for a given (N, G, topology)". A portfolio does not predict;
it hedges: it says run these k and take the best. This script measures what a
predictor would actually achieve out-of-sample, and reports the honest number
whether or not it beats the trivial baselines.

Estimators compared, all scored by regret = achieved cycles / instance optimum
(1.000 = optimal), always evaluated on a HELD-OUT instance:
  oracle              per-instance best (regret 1 by construction)
  portfolio_k         the shipped rule: min over the k selected configurations
  single_global       one algorithm for everything, fitted on the training fold
  cond_topology       best algorithm for this instance's topology, from training
  cond_nbucket        best algorithm for this instance's N-bucket, from training
  random_single       expectation over algorithms (chance level)

Protocols:
  LOO        hold out one instance
  GROUP-topo hold out an entire topology (tests transfer to an unseen topology)
  GROUP-N    hold out an entire N-bucket (tests extrapolation in scale)

Grouped CV is the honest protocol here: instances sharing a topology are not
independent, so LOO leaks structure a real user would not have.
"""
import collections, json, os, statistics as st, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = "/home/rohit/sprs-fix/paper_canonical/scripts"
sys.path.insert(0, SCRIPTS)
os.chdir(SCRIPTS)
import gen_selection as GS

OUT = HERE
def log(m):
    print(m, flush=True)
    open(os.path.join(OUT, "status.txt"), "a").write(m + "\n")

log(f"START {datetime.datetime.now().isoformat()}")
INST, meta, cyc = GS.load_champions()
ACT, OPT, R = GS.build_regret(INST, cyc)
log(f"instances={len(INST)} candidate_algorithms={len(ACT)}")

BUCKETS = [(0,32,'8-32'),(33,256,'33-256'),(257,1024,'257-1K'),
           (1025,4096,'1K-4K'),(4097,99999,'8K')]
def nbucket(i):
    n = meta[i]['N']
    for lo,hi,lab in BUCKETS:
        if lo <= n <= hi: return lab
    return '?'
def topo(i): return meta[i]['topo']

def best_alg(train, subset=None):
    """Algorithm minimising mean regret over `train` (optionally restricted)."""
    pool = [i for i in train if subset is None or subset(i)]
    if not pool: pool = list(train)
    return min(ACT, key=lambda a: sum(R[i][a] for i in pool)/len(pool))

def portfolio(train, k):
    """Greedy min-max-regret portfolio, refitted on the training fold."""
    sel = []
    for _ in range(k):
        cand = min((a for a in ACT if a not in sel),
                   key=lambda a: sum(min([R[i][x] for x in sel+[a]]) for i in train))
        sel.append(cand)
    return sel

def evaluate(folds, kmax=4):
    """folds: list of (train, test) instance-id lists."""
    acc = collections.defaultdict(list)
    for train, test in folds:
        if not train or not test: continue
        gsingle = best_alg(train)
        pf = {k: portfolio(train, k) for k in range(1, kmax+1)}
        for i in test:
            acc['oracle'].append(1.0)
            acc['single_global'].append(R[i][gsingle])
            for k in range(1, kmax+1):
                acc[f'portfolio_k{k}'].append(min(R[i][a] for a in pf[k]))
            a_t = best_alg(train, subset=lambda j, t=topo(i): topo(j) == t)
            acc['cond_topology'].append(R[i][a_t])
            a_n = best_alg(train, subset=lambda j, b=nbucket(i): nbucket(j) == b)
            acc['cond_nbucket'].append(R[i][a_n])
            acc['random_single'].append(sum(R[i][a] for a in ACT)/len(ACT))
    return acc

def summarize(acc, label):
    rows = []
    for k in sorted(acc, key=lambda x: st.mean(acc[x])):
        v = acc[k]
        rows.append(dict(estimator=k, n=len(v),
                         mean_regret=round(st.mean(v), 4),
                         median_regret=round(st.median(v), 4),
                         max_regret=round(max(v), 4),
                         frac_optimal=round(sum(1 for x in v if x <= 1.0+1e-9)/len(v), 4)))
    log(f"\n=== {label} ===")
    log(f"  {'estimator':<16}{'n':>4}{'mean':>9}{'median':>9}{'max':>9}{'%opt':>8}")
    for r in rows:
        log(f"  {r['estimator']:<16}{r['n']:>4}{r['mean_regret']:>9.3f}"
            f"{r['median_regret']:>9.3f}{r['max_regret']:>9.3f}"
            f"{100*r['frac_optimal']:>7.1f}%")
    return rows

res = {"generated": datetime.datetime.now().isoformat(), "n_instances": len(INST),
       "n_algorithms": len(ACT), "protocols": {}}

loo = [([j for j in INST if j != i], [i]) for i in INST]
res['protocols']['LOO'] = summarize(evaluate(loo), "LOO (one instance held out)")

for name, key in (("GROUP-topology", topo), ("GROUP-Nbucket", nbucket)):
    groups = sorted({key(i) for i in INST})
    folds = [([j for j in INST if key(j) != g], [j for j in INST if key(j) == g])
             for g in groups]
    res['protocols'][name] = summarize(evaluate(folds), f"{name} ({len(groups)} groups held out whole)")

# Reproduce the shipped stability claim.
full = portfolio(INST, 4)
identical = sum(1 for i in INST if portfolio([j for j in INST if j != i], 4) == full)
res['shipped_stability_claim'] = {
    "claim": "k=1..4 portfolio selections identical in 39/39 LOO folds",
    "reproduced_k4_identical_folds": f"{identical}/{len(INST)}",
    "note": "Stability of membership, not out-of-sample accuracy."}
log(f"\nshipped stability claim: k=4 portfolio identical in {identical}/{len(INST)} LOO folds")

json.dump(res, open(os.path.join(OUT, "RESULT.json"), "w"), indent=1)
log(f"\nDONE {datetime.datetime.now().isoformat()} -> {OUT}/RESULT.json")
