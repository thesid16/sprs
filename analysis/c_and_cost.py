#!/usr/bin/env python3
import csv, os, glob, statistics, collections
RES="./results"
HW=f"{RES}/live_hw_results_p1_unified.csv"
hw_cyc=collections.defaultdict(dict); hw_st=collections.defaultdict(list)
with open(HW) as f:
    for row in csv.reader(f):
        if len(row)<8: continue
        inst,pipe,tb,pas,cyc,st,ec,err=row[:8]
        try: c=int(cyc)
        except: continue
        if ec in ('OK_BYPASS','OK_BYPASS_REUSED') and c>0:
            if tb not in hw_cyc[inst] or c<hw_cyc[inst][tb]: hw_cyc[inst][tb]=c
            if not err.startswith('REUSED'):
                try: hw_st[inst].append(float(st))
                except: pass
sw={}; sw_time={}; sw_n={}
for swp in glob.glob(f"{RES}/*/sw_results.csv"):
    inst=os.path.basename(os.path.dirname(swp)); d={}; tt=0.0; nn=0
    for r in csv.DictReader(open(swp)):
        try: ms=float(r['makespan'])
        except: continue
        if r['valid'] in ('True','1') and ms>0:
            try: tt+=float(r['time_s']); nn+=1
            except: pass
            if r.get('tb_fname') and r['tb_fname'] not in d:
                d[r['tb_fname']]=(ms,r['s2'],r['s3'])
    sw[inst]=d; sw_time[inst]=tt; sw_n[inst]=nn
def pct(x):return f"{100*x:.1f}%"

FILT=1.5
top1=[]; tier3_reg=[]; tier3_rec=[]; degen=0; degen_inst=0
decept_s2=collections.Counter(); decept_s3=collections.Counter(); decept_pair=collections.Counter()
hwwin_s2=collections.Counter(); hwwin_s3=collections.Counter(); real_fail=[]
for inst in sorted(sw):
    P=[(ms,s2,s3,hw_cyc[inst][tb]) for tb,(ms,s2,s3) in sw[inst].items() if tb in hw_cyc[inst]]
    if len(P)<5: continue
    msmin=min(p[0] for p in P); plaus=[p for p in P if p[0]<=FILT*msmin]
    hwbest=min(p[3] for p in plaus)
    dg=[p for p in P if p[0]>FILT*msmin and p[3]<hwbest]
    if dg: degen+=len(dg); degen_inst+=1
    hb=min(plaus,key=lambda p:p[3]); hwwin_s2[hb[1]]+=1; hwwin_s3[hb[2]]+=1
    swopt=[p for p in P if p[0]==msmin]; r=min(q[3] for q in swopt)/hwbest-1; top1.append(r)
    ums=sorted(set(p[0] for p in P)); thr=ums[min(2,len(ums)-1)]; win=[p for p in P if p[0]<=thr]
    tier3_reg.append(min(q[3] for q in win)/hwbest-1); tier3_rec.append(1 if min(q[3] for q in win)==hwbest else 0)
    for ms,s2,s3,c in plaus:
        if c>=3*hwbest: decept_s2[s2]+=1; decept_s3[s3]+=1; decept_pair[(s2,s3)]+=1
    if r>0.5: real_fail.append((inst,r,f"{swopt[0][1]}|{swopt[0][2]}",hb[1]+'|'+hb[2]))
print("="*70); print("(C) SELECTION FIDELITY  [degenerate collapsed-mappings excluded]")
print(f"  degenerate collapsed TBs (raw-HW-min traps, high makespan/tiny cycles): {degen} across {degen_inst} inst")
print(f"  STRICT TOP-1 regret: median={pct(statistics.median(top1))} mean={pct(statistics.mean(top1))} "
      f"p90={pct(sorted(top1)[int(.9*len(top1))-1])}")
ex=sum(1 for r in top1 if r<1e-9); w5=sum(1 for r in top1 if r<=0.05)
print(f"    SW-best==HW-best: {ex}/{len(top1)} ({pct(ex/len(top1))}); within5%: {w5}/{len(top1)} ({pct(w5/len(top1))})")
print(f"  TOP-3 TIERS regret median={pct(statistics.median(tier3_reg))} mean={pct(statistics.mean(tier3_reg))}; "
      f"contains HW-best {sum(tier3_rec)}/{len(tier3_rec)} ({pct(sum(tier3_rec)/len(tier3_rec))})")
print(f"  REAL top-1 failures (>50% regret): {len(real_fail)}")
for i,r,sp,hp in sorted(real_fail,key=lambda x:-x[1])[:8]:
    print(f"     {i:<20} regret={pct(r):>8}  SWpicked {sp:<7} vs HWbest {hp}")
print(f"  SW-DECEPTIVE (competitive SW ms but >=3x HW cyc)  S2: "+", ".join(f"{k}:{n}" for k,n in decept_s2.most_common(5)))
print(f"                                                    S3: "+", ".join(f"{k}:{n}" for k,n in decept_s3.most_common(5)))
print(f"                                                  pair: "+", ".join(f"{a}|{b}:{n}" for (a,b),n in decept_pair.most_common(5)))
print(f"  HW-WINNER methods  S2: "+", ".join(f"{k}:{n}" for k,n in hwwin_s2.most_common(5))+
      "   S3: "+", ".join(f"{k}:{n}" for k,n in hwwin_s3.most_common(6)))

# ===================== COMPUTE ESTIMATE =====================
print("\n"+"="*70); print("COMPUTE ESTIMATE: all 11 S4 in SW, HW only when improvement observed")
print("="*70)
insts=sorted(sw)
mean_eval={i:(sw_time[i]/sw_n[i] if sw_n[i] else 0) for i in insts}
N_FEED_GLOBAL=65     # union of P1 winners (as run_phase2 is coded)
N_FEED_OWN=10        # median per-instance winners (a leaner design)
MULT=2.0             # S4 refiner eval ~2x base eval (probe: 1.3-2.6x on non-tiny)
IMPR=0.004           # measured improving fraction (1/22 pairs, ~0.4% of refiners)
def sw_cost(nfeed):
    per={i: nfeed*11*MULT*mean_eval[i] for i in insts}
    return per, sum(per.values())
for tag,nfeed in (("as-coded (65 global winner pairs/inst)",N_FEED_GLOBAL),
                  ("leaner (each inst's own ~10 winners)",N_FEED_OWN)):
    per,tot=sw_cost(nfeed)
    top=sorted(per.items(),key=lambda x:-x[1])[:5]
    print(f"\n  S4 SW, {tag}:")
    print(f"    total = {tot/3600:.1f} core-h  ({tot/3600/24:.1f} core-days)")
    print(f"    top-5 instances: "+", ".join(f"{i}={t/3600:.1f}h" for i,t in top))
    print(f"    (those 5 = {sum(t for _,t in top)/tot*100:.0f}% of S4 SW cost)")
# HW: improving TBs only
allmean_st={i:(statistics.mean(hw_st[i]) if hw_st[i] else 0) for i in insts}
n_improv_tbs=N_FEED_GLOBAL*11*IMPR*len(insts)/len(insts)  # per pair fraction
tot_impr=N_FEED_GLOBAL*len(insts)*11*IMPR
print(f"\n  HW (only improving S4 pipelines):")
print(f"    improving fraction measured = {IMPR*100:.1f}% -> ~{tot_impr:.0f} improving S4 TBs across all inst")
print(f"    (probe: 21/22 winner pairs had ZERO improvement; the 1 was large_mod_ring +0.6%)")
med_st=statistics.median([t for t in allmean_st.values() if t>0])
print(f"    if spread at median instance HW cost ({med_st:.0f}s/sim): ~{tot_impr*med_st/3600:.1f} core-h")
print(f"    if all landed on a max-class inst (worst case ~20000s/sim): ~{tot_impr*20000/3600:.0f} core-h")
print(f"    realistic (improvements concentrate on mid/large): tens of core-h at most")
