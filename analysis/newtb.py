import csv, glob, os, copy, signal, collections, statistics, importlib.util
spec=importlib.util.spec_from_file_location("sc","./sprs_core.py")
sc=importlib.util.module_from_spec(spec); os.chdir("."); spec.loader.exec_module(sc)
CBTree=sc.CBTree; bt=sc.build_topology; gc=sc.get_ctx; S2=sc.STAGE2_METHODS; S3=sc.STAGE3_METHODS; S4=sc.STAGE4_METHODS
HW=sc.HW; vv=sc._validate_assignment; meta={t[3]:(t[0],t[1],t[2]) for t in sc.TEST_INSTANCES}
CHOSEN=['4c2','4j','4g']; RES="results"
def canon(a,N): return tuple(a.get(i,-1) for i in range(N)) if isinstance(a,dict) else tuple(a[i] for i in range(N))
class TO(Exception): pass
signal.signal(signal.SIGALRM, lambda s,f:(_ for _ in ()).throw(TO()))
st=collections.defaultdict(list)
with open(f"{RES}/live_hw_results_p1_unified.csv") as f:
    for r in csv.reader(f):
        if len(r)<8: continue
        if r[6] in ('OK_BYPASS','OK_BYPASS_REUSED') and not r[7].startswith('REUSED'):
            try: st[r[0]].append(float(r[5]))
            except: pass
gmed=statistics.median([statistics.mean(v) for v in st.values() if v])
simt={i:(statistics.mean(st[i]) if st[i] else gmed) for i in meta}
rows=[]
order=sorted(meta,key=lambda i:meta[i][0]*meta[i][1])   # small first
for inst in order:
    p=f"{RES}/{inst}/sw_results.csv"
    if not os.path.exists(p): continue
    N,G,tn=meta[inst]; tree=CBTree(N); topo=bt(tn,G); ge=min(G,tree.total_nodes); gc(tree,topo); NN=tree.total_nodes
    sols=[]
    for r in csv.DictReader(open(p)):
        try: ms=float(r['makespan'])
        except: continue
        if r['valid'] in ('True','1') and ms>0: sols.append((r['s2'],r['s3']))
    base={}; refined={}
    for s2 in sorted(set(s for s,_ in sols)):
        _,s2f=S2[s2]
        try:
            ab=s2f(tree,ge,topo,HW)
            if not vv(tree,ab,ge): continue
            base[s2]=hash(canon(ab,NN))
            for ref in CHOSEN:
                _,af=S4[ref]
                try:
                    signal.alarm(30); a1=af(tree,copy.deepcopy(ab),ge,topo,HW); signal.alarm(0)
                    if vv(tree,a1,ge): refined[(s2,ref)]=hash(canon(a1,NN))
                except TO: signal.alarm(0)
                except Exception: signal.alarm(0)
        except Exception: continue
    orig=set((base[s2],s3) for s2,s3 in sols if s2 in base)
    ref=set()
    for s2,s3 in sols:
        for r_ in CHOSEN:
            k=refined.get((s2,r_))
            if k is not None: ref.add((k,s3))
    new=ref-orig
    rows.append((inst,tn,len(orig),len(new),simt[inst]))
    print(f"{inst:<20}{tn:<9} orig={len(orig):>4} NEW={len(new):>4} simt={simt[inst]:>7.0f}s new_hw={len(new)*simt[inst]/3600:6.1f}h",flush=True)
TO_=sum(r[2] for r in rows); TN=sum(r[3] for r in rows); hw=sum(r[3]*r[4] for r in rows)/3600
print(f"\nTOTAL: orig_uniq={TO_}  NEW_uniq={TN} ({TN/TO_:.2f}x)  new-HW={hw:.0f} core-h")
G={'maxp_mod_fat','maxp_bal_2d','max_mod_fat','maxp_dense_hc','max_bal_2d','max_dense_hc','maxp_dense_hc'}
print(f"EXCL 6 giants: NEW={sum(r[3] for r in rows if r[0] not in G)}  new-HW={sum(r[3]*r[4] for r in rows if r[0] not in G)/3600:.0f} core-h")
