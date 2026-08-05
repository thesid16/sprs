#!/usr/bin/env python3
"""Per-refiner S4 probe: which of the 11 refiners actually helps, and does the
best refiner cluster by topology / N/G ratio? Records per (instance): each refiner's
improvement frequency + how often it produces the lowest final makespan."""
import sys, os, csv, copy, signal, collections, importlib.util
spec=importlib.util.spec_from_file_location("sc","./sprs_core.py")
sc=importlib.util.module_from_spec(spec); os.chdir("."); spec.loader.exec_module(sc)
CBTree=sc.CBTree; bt=sc.build_topology; gc=sc.get_ctx; S2=sc.STAGE2_METHODS; S3=sc.STAGE3_METHODS; S4=sc.STAGE4_METHODS
bs=sc.build_schedule; HW=sc.HW; ALU=sc.ALU_FADD; vv=sc._validate_assignment
meta={t[3]:(t[0],t[1],t[2]) for t in sc.TEST_INSTANCES}
RES="results"; S4R=[k for k in S4 if k!='4a']
NAME={k:S4[k][0] for k in S4R}
def hh(a,N): return tuple(a.get(i,-1) for i in range(N)) if isinstance(a,dict) else tuple(a[i] for i in range(N))
class TO(Exception): pass
signal.signal(signal.SIGALRM, lambda s,f:(_ for _ in ()).throw(TO()))
PROBE=['tiny_dense_1d','med_extreme_1d','tiny_mod_ring','med_mod_ring','large_mod_ring',
       'npow2_tiny_hc','small_dense_hc','large_dense_hc','npow2g_small_mesh','med_dense_mesh',
       'npow2_small_torus','med_bal_2d','med_full_torus','small_bal_fat','med_mod_fat','large_bal_fat']
def tiers(inst):
    rows=[]
    for r in csv.DictReader(open(f"{RES}/{inst}/sw_results.csv")):
        try: ms=float(r['makespan'])
        except: continue
        if r['valid'] in ('True','1') and ms>0: rows.append((ms,r['s2'],r['s3']))
    rows.sort()
    if len(rows)<5: return []
    return [(t,rows[i][1],rows[i][2],rows[i][0]) for t,i in
            {'q30':int(.3*len(rows)),'q55':int(.55*len(rows)),'q80':int(.8*len(rows))}.items()]
imp=collections.Counter(); best=collections.Counter(); trials=0
per_inst_best=collections.defaultdict(collections.Counter)
for inst in PROBE:
    if inst not in meta: continue
    N,G,tn=meta[inst]; tree=CBTree(N); topo=bt(tn,G); ge=min(G,tree.total_nodes); gc(tree,topo); NN=tree.total_nodes
    for tier,s2,s3,ms0 in tiers(inst):
        _,s2f=S2[s2]; _,s3f=S3[s3]
        try:
            ab=s2f(tree,ge,topo,HW)
            if not vv(tree,ab,ge): continue
            msb=bs(tree,ab,s3f(tree,ab,ge,topo,HW),ge,topo,HW,alu_op=ALU).makespan; hb=hh(ab,NN)
        except Exception: continue
        trials+=1; results={}
        for s4a in S4R:
            _,af=S4[s4a]
            try:
                signal.alarm(50); a1=af(tree,copy.deepcopy(ab),ge,topo,HW); signal.alarm(0)
                if vv(tree,a1,ge) and hh(a1,NN)!=hb:
                    m1=bs(tree,a1,s3f(tree,a1,ge,topo,HW),ge,topo,HW,alu_op=ALU).makespan
                    results[s4a]=m1
                    if m1<msb: imp[s4a]+=1
            except TO: signal.alarm(0)
            except Exception: signal.alarm(0)
        winners=[k for k,v in results.items() if v<msb]
        if winners:
            bm=min(results[k] for k in winners)
            for k in winners:
                if results[k]==bm: best[k]+=1; per_inst_best[inst][k]+=1
    print(f"done {inst}",flush=True)
print(f"\n=== PER-REFINER (trials={trials}) ===")
print(f"{'id':<5}{'name':<10}{'improved':>9}{'was_best':>9}")
for k in sorted(S4R,key=lambda x:-imp[x]):
    print(f"{k:<5}{NAME[k]:<10}{imp[k]:>9}{best[k]:>9}")
top=[k for k,_ in sorted(imp.items(),key=lambda x:-x[1])[:4]]
print(f"\ntop-4 refiners by improvement: {[NAME[k]+'('+k+')' for k in top]}")
print("\nper-instance BEST refiner (does it cluster?):")
for inst in PROBE:
    if inst in per_inst_best and per_inst_best[inst]:
        tn=meta[inst][2]
        top1=per_inst_best[inst].most_common(2)
        print(f"  {inst:<20}({tn:<9}) -> "+", ".join(f"{NAME[k]}({k}):{n}" for k,n in top1))
