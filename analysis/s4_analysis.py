#!/usr/bin/env python3
"""Analysis for the S4-reduction decision, all from EXISTING Phase-1 data:
  (A) Phase-1 winner-feed size  (select_winners logic) -> Phase-2 feed
  (B) per-instance winner variance (does best (S2,S3) vary by instance?)
  (C) SW->HW selection fidelity: top-1 regret + top-3-tier winner-set recall
  (D) SW time / HW time distributions for the compute estimate
"""
import csv, os, glob, statistics, collections

RES="./results"
HW=f"{RES}/live_hw_results_p1_unified.csv"
UCOLS=['Instance','Pipeline','TB_Name','Pass','Cycles','SimTime_s','ErrorCode','Error']

# ---------- load HW cycles per (inst, tb_name) ----------
hw_cyc=collections.defaultdict(dict)   # inst -> {tb_name: cycles}
hw_simtime=collections.defaultdict(list)
hw_reused=collections.defaultdict(int)
with open(HW) as f:
    for row in csv.reader(f):
        if len(row)<8: continue
        inst,pipe,tb,pas,cyc,st,ec,err=row[:8]
        try: c=int(cyc)
        except: c=-1
        if ec in ('OK_BYPASS','OK_BYPASS_REUSED') and c>0:
            # keep best (min) cycles if dup rows
            if tb not in hw_cyc[inst] or c<hw_cyc[inst][tb]:
                hw_cyc[inst][tb]=c
            reused = err.startswith('REUSED')
            if reused: hw_reused[inst]+=1
            else:
                try: hw_simtime[inst].append(float(st))
                except: pass

# ---------- load SW per instance ----------
# all 180 pipeline rows (makespan) + representative tb_fname map
sw_rows=collections.defaultdict(list)      # inst -> [(ms,s2,s3,tb_fname)]
sw_time=collections.defaultdict(float)     # inst -> sum time_s
sw_neval=collections.defaultdict(int)
for swp in glob.glob(f"{RES}/*/sw_results.csv"):
    inst=os.path.basename(os.path.dirname(swp))
    for r in csv.DictReader(open(swp)):
        try:
            ms=float(r['makespan']); valid=r['valid'] in ('True','true','1')
        except: continue
        if not valid or ms<=0: continue
        sw_rows[inst].append((ms,r['s2'],r['s3'],r.get('tb_fname','')))
        try: sw_time[inst]+=float(r['time_s']); sw_neval[inst]+=1
        except: pass

instances=sorted(sw_rows.keys())
print(f"instances with SW data: {len(instances)}\n")

# ================= (A) WINNER FEED (select_winners n_tiers=3, max_per=15) =================
print("="*70); print("(A) PHASE-1 WINNER FEED  ->  what Phase-2 S4 would run on")
print("="*70)
n_tiers,max_per=3,15
global_pairs=set(); per_inst_winner_ct={}; winner_tbs=collections.defaultdict(set)
for inst in instances:
    rows=sorted(sw_rows[inst])                      # by makespan asc
    ums=sorted(set(ms for ms,_,_,_ in rows))
    thr=ums[min(n_tiers-1,len(ums)-1)]
    sel=[(ms,s2,s3,tb) for ms,s2,s3,tb in rows if ms<=thr][:max_per]
    per_inst_winner_ct[inst]=len(sel)
    for ms,s2,s3,tb in sel:
        global_pairs.add((s2,s3))
print(f"  winners per instance: min={min(per_inst_winner_ct.values())} "
      f"median={int(statistics.median(per_inst_winner_ct.values()))} "
      f"max={max(per_inst_winner_ct.values())} "
      f"mean={statistics.mean(per_inst_winner_ct.values()):.1f}")
print(f"  total winner rows across 40 inst = {sum(per_inst_winner_ct.values())}")
print(f"  GLOBAL unique (S2,S3) pairs among winners = {len(global_pairs)}")
print(f"  => run_phase2 feed = {len(global_pairs)} pairs x 40 inst = "
      f"{len(global_pairs)*40} base pipelines fed to S4")

# ================= (B) PER-INSTANCE WINNER VARIANCE =================
print(); print("="*70); print("(B) DOES THE BEST PIPELINE VARY BY INSTANCE?")
print("="*70)
best_pair=collections.Counter(); best_s2=collections.Counter(); best_s3=collections.Counter()
for inst in instances:
    ms,s2,s3,tb=min(sw_rows[inst])
    best_pair[(s2,s3)]+=1; best_s2[s2]+=1; best_s3[s3]+=1
print(f"  distinct winning (S2,S3) pairs across 40 inst: {len(best_pair)}")
print("  top winning (S2|S3) pairs:  " +
      ", ".join(f"{a}|{b}:{n}" for (a,b),n in best_pair.most_common(6)))
print("  winning S2 spread:  " + ", ".join(f"{k}:{n}" for k,n in best_s2.most_common(8)))
print("  winning S3 spread:  " + ", ".join(f"{k}:{n}" for k,n in best_s3.most_common(10)))
# coverage: how many distinct pairs to cover K% of instances' winners
cov=best_pair.most_common()
cum=0; need_for={}
for i,((a,b),n) in enumerate(cov,1):
    cum+=n
    for pct in (0.5,0.8,0.9,1.0):
        if cum>=pct*len(instances) and pct not in need_for: need_for[pct]=i
print("  #distinct winner-pairs needed to cover: " +
      ", ".join(f"{int(p*100)}%={need_for[p]}" for p in (0.5,0.8,0.9,1.0)))

# ================= (C) SW -> HW SELECTION FIDELITY =================
print(); print("="*70); print("(C) HOW WELL DOES SW-MAKESPAN CATCH THE HW-BEST?")
print("="*70)
# TB-level: unique TBs with (makespan, cycles). makespan from representative sw row (tb_fname set).
top1_regret=[]; top1_regret_mean=[]; tier3_regret=[]; tier3_recall=[]; ranks=[]
per_inst_detail=[]
for inst in instances:
    # build tb -> makespan from sw rows that have a tb_fname
    tb_ms={}
    for ms,s2,s3,tb in sw_rows[inst]:
        if tb and tb not in tb_ms: tb_ms[tb]=ms
    # pair with hw cycles
    pairs=[(tb_ms[tb],hw_cyc[inst][tb]) for tb in tb_ms if tb in hw_cyc[inst]]
    if len(pairs)<5: continue
    hw_best=min(c for _,c in pairs)
    ms_min=min(m for m,_ in pairs)
    # SW top-1 set = all TBs at min makespan
    sw_opt=[c for m,c in pairs if m==ms_min]
    r_opt=min(sw_opt)/hw_best-1.0
    r_mean=statistics.mean(sw_opt)/hw_best-1.0
    top1_regret.append(r_opt); top1_regret_mean.append(r_mean)
    # rank (1-based) of the best SW-opt TB in HW ordering
    hw_sorted=sorted(c for _,c in pairs)
    rank=hw_sorted.index(min(sw_opt))+1
    ranks.append((inst,rank,len(pairs)))
    # top-3 makespan tiers (mirror select_winners) -> winner set
    ums=sorted(set(m for m,_ in pairs))
    thr=ums[min(2,len(ums)-1)]
    win=[c for m,c in pairs if m<=thr]
    tier3_regret.append(min(win)/hw_best-1.0)
    tier3_recall.append(1 if min(win)==hw_best else 0)
    per_inst_detail.append((inst,r_opt,min(win)/hw_best-1.0,rank,len(pairs)))

def pct(x): return f"{100*x:.1f}%"
print(f"  instances analyzed (>=5 TBs w/ HW): {len(top1_regret)}")
print("  -- STRICT TOP-1 (pick single SW-best makespan; aggressive pruning) --")
print(f"     HW-cycle regret vs true HW-best:  median={pct(statistics.median(top1_regret))}  "
      f"mean={pct(statistics.mean(top1_regret))}  "
      f"p90={pct(sorted(top1_regret)[int(0.9*len(top1_regret))-1])}  "
      f"max={pct(max(top1_regret))}")
exact=sum(1 for r in top1_regret if r<1e-9)
print(f"     SW-best IS HW-best exactly: {exact}/{len(top1_regret)} ({pct(exact/len(top1_regret))})")
within5=sum(1 for r in top1_regret if r<=0.05)
print(f"     SW-best within 5% of HW-best: {within5}/{len(top1_regret)} ({pct(within5/len(top1_regret))})")
print("  -- TOP-3 MAKESPAN TIERS (the tournament's actual winner set, <=15) --")
print(f"     HW-cycle regret of best-in-winner-set:  median={pct(statistics.median(tier3_regret))}  "
      f"mean={pct(statistics.mean(tier3_regret))}  max={pct(max(tier3_regret))}")
print(f"     winner set CONTAINS HW-best: {sum(tier3_recall)}/{len(tier3_recall)} "
      f"({pct(sum(tier3_recall)/len(tier3_recall))})")
# worst offenders (top-1 regret)
print("  worst top-1 regret instances:")
for inst,ro,rt,rk,n in sorted(per_inst_detail,key=lambda x:-x[1])[:6]:
    print(f"     {inst:<22} top1_regret={pct(ro):>7}  tier3_regret={pct(rt):>6}  "
          f"SWbest_HWrank={rk}/{n}")

# ================= (D) COMPUTE INGREDIENTS =================
print(); print("="*70); print("(D) TIMING INGREDIENTS FOR THE ESTIMATE")
print("="*70)
tot_sw=sum(sw_time.values()); tot_eval=sum(sw_neval.values())
print(f"  Phase-1 SW: {tot_eval} evals, sum(time_s)={tot_sw/3600:.2f} core-h, "
      f"mean/eval={tot_sw/max(1,tot_eval):.3f}s")
print(f"  per-instance SW mean/eval (proxy for one S4 refiner eval):")
sw_per=sorted(((inst,sw_time[inst]/max(1,sw_neval[inst])) for inst in instances),key=lambda x:-x[1])
for inst,t in sw_per[:5]: print(f"     {inst:<22} {t:.3f}s/eval  (n={sw_neval[inst]})")
print(f"     ... median instance {statistics.median([t for _,t in sw_per]):.3f}s/eval")
# HW simtime
allst=[t for inst in instances for t in hw_simtime[inst]]
print(f"  HW fresh sims: {len(allst)}  sum={sum(allst)/3600:.2f} core-h "
      f"(wallclock-under-contention)  mean={statistics.mean(allst):.1f}s  "
      f"median={statistics.median(allst):.1f}s")
print(f"  HW reused (SimTime=0): {sum(hw_reused.values())}")
print(f"  per-instance HW mean SimTime (biggest):")
hw_per=sorted(((inst,statistics.mean(hw_simtime[inst])) for inst in instances if hw_simtime[inst]),key=lambda x:-x[1])
for inst,t in hw_per[:6]: print(f"     {inst:<22} {t:.1f}s/sim  (n={len(hw_simtime[inst])})")
