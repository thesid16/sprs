#!/usr/bin/env python3
"""
gen_tables.py — regenerate every data-driven LaTeX table in paper_v6 from the
authoritative CSVs.

Authoritative dataset: '"+SPRS_ROOT+"/data/results/  (July clean Phase-1
restart; supersedes tournament_portable — see PAPER_V6_PLAN.md §5a).

Every emitted .tex file carries a provenance header naming this script, the
source CSV, and the generation date, so no table in the manuscript can drift
away from the artifact.

Usage:  python3 scripts/gen_tables.py [--out tables/]
"""
import argparse
import csv
import datetime
import glob
import os
import re
import statistics as st
import struct
import sys
from collections import defaultdict, Counter

csv.field_size_limit(sys.maxsize)

P1 = "'"+SPRS_ROOT+"/data/results"
HW_CSV = f"{P1}/live_hw_results_p1_unified.csv"
MAXP_CSV = _os.path.join(SPRS_ROOT, "data", "results", "live_hw_results_maxp_mod_fat.csv")

# (N, G, topology, label) — mirrors sprs_core.TEST_INSTANCES
INSTANCES = [
    (8,4,'ring','tiny_mod_ring'),(8,2,'linear','tiny_dense_1d'),
    (32,16,'torus','small_mod_2d'),(32,8,'fat_tree','small_bal_fat'),
    (32,4,'hypercube','small_dense_hc'),
    (128,64,'ring','med_mod_ring'),(128,32,'fat_tree','med_mod_fat'),
    (128,16,'torus','med_bal_2d'),(128,8,'mesh','med_dense_mesh'),
    (128,4,'linear','med_extreme_1d'),
    (512,256,'ring','large_mod_ring'),(512,64,'fat_tree','large_bal_fat'),
    (512,32,'hypercube','large_dense_hc'),(512,16,'torus','large_dense_2d'),
    (512,8,'linear','large_extreme_1d'),
    (1024,512,'ring','vlarge_mod_ring'),(1024,128,'fat_tree','vlarge_bal_fat'),
    (1024,64,'torus','vlarge_dense_2d'),(1024,32,'hypercube','vlarge_dense_hc'),
    (2048,256,'fat_tree','vlarge2_bal_fat'),(2048,128,'torus','vlarge2_dense_2d'),
    (4096,2048,'fat_tree','max_mod_fat'),(4096,1024,'torus','max_bal_2d'),
    (4096,512,'hypercube','max_dense_hc'),
    (8192,4096,'fat_tree','maxp_mod_fat'),(8192,2048,'torus','maxp_bal_2d'),
    (8192,1024,'hypercube','maxp_dense_hc'),
    (512,64,'mesh','large_bal_mesh'),(2048,256,'mesh','vlarge_bal_mesh'),
    (128,128,'torus','med_full_torus'),(2048,512,'ring','vlarge2_mod_ring'),
    (1024,16,'linear','vlarge_extreme_1d'),
    (10,4,'ring','npow2n_tiny_ring'),(16,5,'mesh','npow2g_small_mesh'),
    (50,7,'hypercube','npow2_tiny_hc'),(100,10,'torus','npow2_small_torus'),
    (200,12,'fat_tree','npow2_med_fat'),(500,32,'torus','large_unbal_torus'),
    (1500,64,'hypercube','vlarge_unbal_hc'),(3000,128,'fat_tree','max_unbal_fat'),
]
META = {lab: (n, g, t) for n, g, t, lab in INSTANCES}

S2_NAMES = {'2a':'HEFT','2b':'RecBisect','2c':'MLfm','2d':'DKway','2e':'ExactBB',
            '2f':'DFSseed','2g':'DSC','2h':'Chretienne','2i':'CPOP','2j':'Centroid',
            '2k':'Lukes','2l':'Frederickson','2m':'CPFD','2n':'ClHEFT','2o':'ParSub',
            '2p':'Spine','2q':'SubPack','2r':'LvlHLF'}
S3_NAMES = {'3a':'Identity','3b':'HopMin','3c':'TreeMatch','3d':'QAP-SA','3e':'MCF',
            '3f':'DRB','3g':'SFC','3h':'Spectral','3i':'RAGreedy','3j':'Tabu'}
TOPO_TEX = {'fat_tree':'fat-tree','hypercube':'hypercube','torus':'torus',
            'mesh':'mesh','ring':'ring','linear':'linear'}


# ─────────────────────────── loaders ───────────────────────────
def load_hw(path=HW_CSV):
    """HW rows. Handles embedded newlines in the Error column."""
    rows = []
    with open(path, newline='', encoding='utf-8', errors='replace') as f:
        rdr = csv.reader(f)
        first = next(rdr, None)
        if first and first[0] != 'Instance' and len(first) >= 7:
            rows.append(first)
        rows += [r for r in rdr if len(r) >= 7]
    out = []
    for r in rows:
        try:
            cyc = int(r[4])
        except ValueError:
            cyc = -1
        try:
            sim = float(r[5])
        except ValueError:
            sim = 0.0
        out.append(dict(inst=r[0], pipeline=r[1], tb=r[2],
                        ok=(r[3] == 'True'), cycles=cyc, sim_s=sim, code=r[6]))
    return out


def load_sw():
    """Per-instance SW rows keyed by instance label."""
    sw = {}
    for path in sorted(glob.glob(f"{P1}/*/sw_results.csv")):
        inst = os.path.basename(os.path.dirname(path))
        with open(path, newline='') as f:
            sw[inst] = list(csv.DictReader(f))
    return sw


def canonical_roots():
    """Expected 64-bit root per N, read from the emitted testbenches.

    The TB embeds EXPECTED as computed by the software oracle; scanning the
    emitted files verifies compiler and fabric agree on the same constant.
    """
    rx = re.compile(rb"EXPECTED\s*=\s*64'h([0-9A-Fa-f]{16})")
    byN = defaultdict(lambda: defaultdict(set))
    for lab, (N, G, T) in META.items():
        for tb in sorted(glob.glob(f"{P1}/{lab}/tb_*.sv")):
            with open(tb, 'rb') as f:
                head = f.read(300_000)
            m = rx.search(head)
            if m:
                byN[N][m.group(1).upper().decode()].add((lab, G, T))
    return byN


# ─────────────────────────── helpers ───────────────────────────
def header(script_rel, source, note=""):
    d = datetime.date.today().isoformat()
    s = (f"% GENERATED — do not edit by hand.\n"
         f"% script : {script_rel}\n"
         f"% source : {source}\n"
         f"% date   : {d}\n")
    if note:
        s += f"% note   : {note}\n"
    return s


def write(out_dir, name, body, source, note=""):
    path = os.path.join(out_dir, name)
    with open(path, 'w') as f:
        f.write(header("scripts/gen_tables.py", source, note))
        f.write(body)
    print(f"  wrote {path}")


# ─────────────────────────── tables ───────────────────────────
def tbl_invariance(out_dir, hw, roots):
    """Cross-topology bitwise invariance — the paper's primary result."""
    hw_ok = defaultdict(list)
    for r in hw:
        if r['ok']:
            hw_ok[r['inst']].append(r)

    rows = []
    for N in sorted(roots):
        exps = roots[N]
        compiled = sorted({(lab, g, t) for s in exps.values() for (lab, g, t) in s})
        validated = [(lab, g, t) for lab, g, t in compiled if hw_ok.get(lab)]
        n_cfg = sum(len(hw_ok[lab]) for lab, _, _ in validated)
        assert len(exps) == 1, f"N={N} has {len(exps)} distinct roots — invariance violated"
        root = next(iter(exps))
        rows.append((N, len(compiled), len(validated), n_cfg, root))

    # Mutation results fill the last two columns once scripts/mutate.py has run.
    mut = {}
    mpath = os.path.join(os.path.dirname(out_dir) or ".", "data", "mutation_results.json")
    if os.path.exists(mpath):
        import json
        with open(mpath) as f:
            raw = json.load(f)
        mut = {int(k): v for k, v in raw.get("by_N", {}).items()}

    def mcell(N, key):
        d = mut.get(N)
        if not d or key not in d:
            return r"\todo{--}"
        det, tot_ = d[key]["detected"], d[key]["total"]
        return f"{det}/{tot_}"

    body = [r"\begin{tabular}{@{}rrrrlrrr@{}}", r"\toprule",
            r"$N$ & compiled & HW-val. & HW configs & 64-bit root result & "
            r"Div. & Addr-sub & Leaf-corr. \\",
            r"    & $(G,\text{topo})$ & $(G,\text{topo})$ & (passing) & & & "
            r"detected & detected \\",
            r"\midrule"]
    for N, nc, nv, ncfg, root in rows:
        body.append(f"{N:<5} & {nc} & {nv} & {ncfg} & \\texttt{{0x{root}}} & 0 & "
                    f"{mcell(N,'addr_sub')} & {mcell(N,'leaf_corrupt')} \\\\")
    body += [r"\bottomrule", r"\end{tabular}"]

    tot = sum(r[3] for r in rows)
    note = (f"{tot} passing HW configs; every N has exactly 1 distinct root; "
            f"mutation columns {'filled' if mut else 'PENDING scripts/mutate.py'}")
    write(out_dir, "invariance.tex", "\n".join(body) + "\n", HW_CSV, note)
    return rows


def tbl_suite(out_dir, hw):
    """The 40-instance benchmark suite."""
    cov = {r['inst'] for r in hw if r['ok']}
    body = [r"\begin{tabular}{@{}lrrlrc@{}}", r"\toprule",
            r"Instance & $N$ & $G$ & Topology & $N/G$ & HW \\", r"\midrule"]
    for N, G, T, lab in sorted(INSTANCES, key=lambda x: (x[0], x[1])):
        mark = r"\checkmark" if lab in cov else r"--"
        body.append(f"\\sv{{{lab.replace('_',chr(92)+'_')}}} & {N} & {G} & "
                    f"{TOPO_TEX[T]} & {N/G:.3g} & {mark} \\\\")
    body += [r"\bottomrule", r"\end{tabular}"]
    write(out_dir, "suite.tex", "\n".join(body) + "\n", "sprs_core.TEST_INSTANCES",
          f"{len(INSTANCES)} instances, {len(cov)} with HW validation")


def tbl_perinstance(out_dir, hw, sw):
    """Per-instance champion, Omega, ratio, and HW cost."""
    byi = defaultdict(list)
    for r in hw:
        if r['ok']:
            byi[r['inst']].append(r)

    body = [r"\begin{tabular}{@{}lrrlrrrr@{}}", r"\toprule",
            r"Instance & $N$ & $G$ & Topology & TBs & Champion & $\Omega$ & "
            r"cyc/$\Omega$ \\", r"\midrule"]
    stats = []
    for N, G, T, lab in sorted(INSTANCES, key=lambda x: (x[0], x[1])):
        rs = byi.get(lab)
        if not rs:
            body.append(f"\\sv{{{lab.replace('_',chr(92)+'_')}}} & {N} & {G} & "
                        f"{TOPO_TEX[T]} & \\multicolumn{{4}}{{c}}{{not HW-validated}} \\\\")
            continue
        champ = min(r['cycles'] for r in rs)
        om = None
        for row in sw.get(lab, []):
            if row.get('omega'):
                om = float(row['omega'])
                break
        ratio = f"{champ/om:.2f}" if om else "--"
        omtxt = f"{om:.0f}" if om else "--"
        stats.append((lab, champ, om))
        body.append(f"\\sv{{{lab.replace('_',chr(92)+'_')}}} & {N} & {G} & {TOPO_TEX[T]} & "
                    f"{len(rs)} & {champ} & {omtxt} & {ratio} \\\\")
    body += [r"\bottomrule", r"\end{tabular}"]
    write(out_dir, "perinstance.tex", "\n".join(body) + "\n", HW_CSV,
          f"{len(stats)} HW-validated instances")


def tbl_catalogue(out_dir, sw):
    """S2/S3 win share over instances, by measured SW makespan."""
    win2, win3 = Counter(), Counter()
    n = 0
    for lab, rows in sw.items():
        vr = [r for r in rows
              if r.get('valid') == 'True' and r.get('makespan') not in ('', '-1', None)]
        if not vr:
            continue
        w = min(vr, key=lambda r: float(r['makespan']))
        win2[w['s2']] += 1
        win3[w['s3']] += 1
        n += 1

    def block(counter, names, label):
        b = [r"\begin{tabular}{@{}llr r@{}}", r"\toprule",
             rf"ID & {label} & wins & share \\", r"\midrule"]
        for k in sorted(names, key=lambda k: (-counter.get(k, 0), k)):
            c = counter.get(k, 0)
            b.append(f"\\sv{{{k}}} & {names[k]} & {c} & {100*c/n:.1f}\\% \\\\")
        b += [r"\bottomrule", r"\end{tabular}"]
        return "\n".join(b) + "\n"

    write(out_dir, "catalogue_s2.tex", block(win2, S2_NAMES, "Assignment (S2)"),
          f"{P1}/*/sw_results.csv", f"win share over {n} instances, min SW makespan")
    write(out_dir, "catalogue_s3.tex", block(win3, S3_NAMES, "Mapping (S3)"),
          f"{P1}/*/sw_results.csv", f"win share over {n} instances, min SW makespan")
    return win2, win3, n


def tbl_budget(out_dir, hw):
    """Compute budget — what the campaign actually cost."""
    ok = [r for r in hw if r['ok']]
    sims = [r['sim_s'] for r in ok]
    giants = ['max_mod_fat', 'maxp_bal_2d', 'maxp_dense_hc', 'max_bal_2d', 'max_dense_hc']
    gsec = sum(r['sim_s'] for r in ok if r['inst'] in giants)
    tot = sum(sims)

    # maxp_mod_fat: attempted, never completed
    mf_n, mf_h = 0, 0.0
    if os.path.exists(MAXP_CSV):
        for r in load_hw(MAXP_CSV):
            mf_n += 1
            mf_h += r['sim_s'] / 3600

    body = [r"\begin{tabular}{@{}lr@{}}", r"\toprule",
            r"Quantity & Value \\", r"\midrule",
            rf"HW simulations completed & {len(ok)} \\",
            rf"Total simulation time & {tot/3600:.1f} core-h \\",
            rf"Median per testbench & {st.median(sims):.0f} s \\",
            rf"Longest single testbench & {max(sims)/3600:.2f} h \\",
            rf"Share consumed by the 5 giants & {100*gsec/tot:.1f}\% \\",
            r"\midrule",
            rf"\sv{{maxp\_mod\_fat}} attempts & {mf_n} (all timed out) \\",
            rf"\sv{{maxp\_mod\_fat}} time expended & {mf_h:.1f} core-h \\",
            r"\bottomrule", r"\end{tabular}"]
    write(out_dir, "budget.tex", "\n".join(body) + "\n", HW_CSV,
          "giants = max_mod_fat, maxp_bal_2d, maxp_dense_hc, max_bal_2d, max_dense_hc")


def tbl_dedup(out_dir, sw):
    """Compilation feasibility and the deduplication collapse."""
    total = sum(len(v) for v in sw.values())
    valid = [r for v in sw.values() for r in v if r['valid'] == 'True']
    codes = Counter(r['error_code'] or 'BLANK' for v in sw.values() for r in v)
    tbh = {r['tb_hash'] for r in valid if r['tb_hash']}
    ash = {r['asgn_hash'] for r in valid if r['asgn_hash']}

    body = [r"\begin{tabular}{@{}lrr@{}}", r"\toprule",
            r"Stage & Count & Retained \\", r"\midrule",
            rf"Compilations attempted & {total} & 100.0\% \\",
            rf"Feasible & {len(valid)} & {100*len(valid)/total:.1f}\% \\",
            rf"Unique testbenches (\sv{{tb\_hash}}) & {len(tbh)} & "
            rf"{100*len(tbh)/total:.1f}\% \\",
            rf"Unique assignments (\sv{{asgn\_hash}}) & {len(ash)} & "
            rf"{100*len(ash)/total:.1f}\% \\",
            r"\midrule",
            r"\multicolumn{3}{@{}l}{\emph{Infeasibility causes}} \\",
            rf"\quad Size-gated (\sv{{E\_BYPASSED}}) & {codes.get('E_BYPASSED',0)} & \\",
            rf"\quad IMEM overflow (\sv{{E\_IMEM\_OF}}) & {codes.get('E_IMEM_OF',0)} & \\",
            rf"\quad Evaluation timeout & {codes.get('E_EVAL_TIMEOUT',0)} & \\",
            r"\bottomrule", r"\end{tabular}"]
    write(out_dir, "dedup.tex", "\n".join(body) + "\n", f"{P1}/*/sw_results.csv",
          f"dedup eliminates {100*(1-len(tbh)/len(valid)):.1f}% of HW simulations")
    return total, len(valid), len(tbh), len(ash), codes


# ─────────────────────────── main ───────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tables")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    print("loading authoritative dataset (tournament_p1)...")
    hw, sw = load_hw(), load_sw()
    ok = sum(1 for r in hw if r['ok'])
    print(f"  HW: {len(hw)} rows, {ok} passing, "
          f"{len({r['inst'] for r in hw if r['ok']})} instances")
    print(f"  SW: {len(sw)} instances")
    print("scanning testbenches for EXPECTED roots (this reads ~5,800 files)...")
    roots = canonical_roots()

    print("generating tables:")
    inv = tbl_invariance(a.out, hw, roots)
    tbl_suite(a.out, hw)
    tbl_perinstance(a.out, hw, sw)
    w2, w3, ninst = tbl_catalogue(a.out, sw)
    tbl_budget(a.out, hw)
    tot, val, tbh, ash, codes = tbl_dedup(a.out, sw)

    print("\n=== key numbers for the manuscript ===")
    print(f"  invariance   : {sum(r[3] for r in inv)} passing configs, "
          f"{len(inv)} leaf-count classes, all single-rooted")
    print(f"  feasibility  : {val}/{tot} ({100*val/tot:.1f}%)")
    print(f"  dedup        : {val} -> {tbh} TBs -> {ash} assignments")
    print(f"  S2 winner    : {max(w2, key=w2.get)} "
          f"({w2[max(w2,key=w2.get)]}/{ninst} instances)")
    print(f"  S3 winner    : {max(w3, key=w3.get)} "
          f"({w3[max(w3,key=w3.get)]}/{ninst} instances)")


if __name__ == "__main__":
    main()
