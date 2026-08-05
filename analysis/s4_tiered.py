#!/usr/bin/env python3
"""Improvement/change rate of the 11 S4 refiners across the QUALITY SPECTRUM
(best/median/worst SW solutions), not just winners. Grounds HW count + SW skippability
for refining all ~2920 unique solutions."""
import sys, os, csv, copy, time, signal, statistics, collections
import importlib.util
spec=importlib.util.spec_from_file_location("sprs_core","./sprs_core.py")
sc=importlib.util.module_from_spec(spec); os.chdir("."); spec.loader.exec_module(sc)
CBTree=sc.CBTree; bt=sc.build_topology; gc=sc.get_ctx; S2=sc.STAGE2_METHODS; S3=sc.STAGE3_METHODS; S4=sc.STAGE4_METHODS
bs=sc.build_schedule; HW=sc.HW; ALU=sc.ALU_FADD; vv=sc._validate_assignment; TI=sc.TEST_INSTANCES
def hh(a,N):
    return tuple(a.get(i,-1) for i in range(N)) if isinstance(a,dict) else tuple(a[i] for i in range(N))
RES="./results"
meta={t[3]:(t[0],t[1],t[2]) for t in TI}
S4R=[k for k in S4 if k!='4a']
PROBE=['small_dense_hc','small_mod_2d','med_bal_2d','med_mod_ring','med_dense_mesh','large_dense_hc','large_mod_ring']
class TO(Exception): pass
signal.signal(signal.SIGALRM, lambda s,f:(_ for _ in ()).throw(TO()))

def tiers(inst):
    rows=[]
    for r in csv.DictReader(open(f"{RES}/{inst}/sw_results.csv")):
        try: ms=float(r['makespan'])
        except: continue
        if r['valid'] in ('True','1') and ms>0: rows.append((ms,r['s2'],r['s3']))
    rows.sort()
    if len(rows)<3: return []
    idx={'best':0,'median':len(rows)//2,'worst':len(rows)-1}
    return [(t,rows[i][1],rows[i][2],rows[i][0]) for t,i in idx.items()]

agg=collections.defaultdict(lambda:[0,0,0])  # tier -> [n_pairs, sum_improve, sum_changed]
detail=[]
for inst in PROBE:
    if inst not in meta: continue
    n,g,tn=meta[inst]; tree=CBTree(n); topo=bt(tn,g); ge=min(g,tree.total_nodes); ctx=gc(tree,topo)
    N=tree.total_nodes
    for tier,s2,s3,ms0 in tiers(inst):
        _,s2f=S2[s2]; _,s3f=S3[s3]
        try:
            ab=s2f(tree,ge,topo,HW)
            if not vv(tree,ab,ge): continue
            mp=s3f(tree,ab,ge,topo,HW); msb=bs(tree,ab,mp,ge,topo,HW,alu_op=ALU).makespan
            hb=hh(ab,N)
        except Exception: continue
        nimp=nchg=0; bestg=0.0
        for s4a in S4R:
            _,af=S4[s4a]
            try:
                signal.alarm(75); a1=af(tree,copy.deepcopy(ab),ge,topo,HW); signal.alarm(0)
                if not vv(tree,a1,ge): continue
                if hh(a1,N)!=hb:
                    nchg+=1
                    m1=bs(tree,a1,s3f(tree,a1,ge,topo,HW),ge,topo,HW,alu_op=ALU).makespan
                    if m1<msb: nimp+=1; bestg=max(bestg,(msb-m1)/msb*100)
            except TO: signal.alarm(0)
            except Exception: signal.alarm(0)
        a=agg[tier]; a[0]+=1; a[1]+=nimp; a[2]+=nchg
        detail.append((inst,tier,s2+'|'+s3,int(ms0),nchg,nimp,round(bestg,2)))
        print(f"  {inst:<16} {tier:<7} {s2}|{s3:<4} base={int(ms0):<5} changed={nchg}/11 improved={nimp}/11 gain={bestg:.2f}%",flush=True)

print("\n=== RATE BY QUALITY TIER (of 11 refiners) ===")
for tier in ('best','median','worst'):
    n,si,sc_=agg[tier]
    if n: print(f"  {tier:<7}: change={si and sc_/(n*11)*100:5.1f}%  improve={sc_ and si/(n*11)*100:5.1f}%  "
                f"(n={n} pairs, {si} improvements, {sc_} changes)")
allp=sum(a[0] for a in agg.values()); alli=sum(a[1] for a in agg.values()); allc=sum(a[2] for a in agg.values())
print(f"  OVERALL: improve={alli/(allp*11)*100:.1f}%  change={allc/(allp*11)*100:.1f}%  (n={allp} pairs)")
print(f"  => of ALL solutions, ~{alli/(allp*11)*100:.1f}% of (solution x refiner) pairs improve -> HW candidates")
