#!/usr/bin/env python3
"""W9b -- (a) is k=4 the knee? (b) bootstrap CI on the held-out regret.

Both bear directly on the deployment recommendation. (a) tells a user whether
running a 5th configuration buys anything. (b) tells a referee how much of the
1.039 unseen-topology figure is real given only 39 instances -- a point
estimate from 39 points with no interval is the standard statistics objection.
"""
import os, sys, json, random, statistics as st, collections, datetime
sys.path.insert(0, "/home/rohit/sprs-fix/paper_canonical/scripts")
os.chdir("/home/rohit/sprs-fix/paper_canonical/scripts")
import gen_selection as GS

INST, meta, cyc = GS.load_champions()
ACT, OPT, R = GS.build_regret(INST, cyc)
topo = lambda i: meta[i]['topo']

def portfolio(train, k):
    sel = []
    for _ in range(k):
        sel.append(min((a for a in ACT if a not in sel),
                   key=lambda a: sum(min([R[i][x] for x in sel+[a]]) for i in train)))
    return sel

def loo_regret(k):
    return [min(R[i][a] for a in portfolio([j for j in INST if j != i], k)) for i in INST]

def group_regret(k):
    out = []
    for g in sorted({topo(i) for i in INST}):
        tr = [j for j in INST if topo(j) != g]
        pf = portfolio(tr, k)
        out += [min(R[i][a] for a in pf) for i in INST if topo(i) == g]
    return out

res = {"generated": datetime.datetime.now().isoformat(), "n_algorithms": len(ACT)}
print(f"{'k':>3}{'LOO mean':>11}{'LOO %opt':>10}{'topo mean':>12}{'topo %opt':>11}")
sweep = {}
for k in range(1, min(9, len(ACT))+1):
    l, g = loo_regret(k), group_regret(k)
    sweep[k] = dict(loo_mean=round(st.mean(l),4),
                    loo_pct_opt=round(100*sum(1 for x in l if x<=1+1e-9)/len(l),1),
                    topo_mean=round(st.mean(g),4),
                    topo_pct_opt=round(100*sum(1 for x in g if x<=1+1e-9)/len(g),1))
    s = sweep[k]
    print(f"{k:>3}{s['loo_mean']:>11.4f}{s['loo_pct_opt']:>9.1f}%"
          f"{s['topo_mean']:>12.4f}{s['topo_pct_opt']:>10.1f}%")
res['k_sweep'] = sweep

# Bootstrap over instances (resample the 39, recompute held-out regret).
random.seed(20260828)
B = 2000
def boot(fn, k):
    vals = fn(k)
    m = []
    for _ in range(B):
        s = [random.choice(vals) for _ in vals]
        m.append(st.mean(s))
    m.sort()
    return st.mean(vals), m[int(.025*B)], m[int(.975*B)]
print(f"\nbootstrap 95% CI on mean regret (B={B}, resampling the 39 instances):")
res['bootstrap_ci'] = {}
for k in (2, 3, 4, 5):
    for lab, fn in (("LOO", loo_regret), ("unseen-topology", group_regret)):
        mean, lo, hi = boot(fn, k)
        res['bootstrap_ci'][f"k{k}_{lab}"] = dict(mean=round(mean,4), lo=round(lo,4), hi=round(hi,4))
        print(f"  k={k} {lab:<18} {mean:.4f}  [{lo:.4f}, {hi:.4f}]")

json.dump(res, open("/home/rohit/sprs-fix/experiments/w_final/W9_selection/RESULT_ksweep.json","w"), indent=1)
print("\nwrote RESULT_ksweep.json")
