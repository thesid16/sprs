#!/usr/bin/env python3
r"""
distill_wround.py -- vendor the final measurement round's result records into
paper/data/wround/, and distil the two facts that live only in bulk raw logs.

Run once, on the machine that holds experiments/w_final/.  Everything the
paper's macro generator needs is written under data/wround/ so that
`make tables` (and verify_tables.py, which copies the paper tree to scratch)
reproduces every macro without reaching outside the release.

Two records are distilled rather than copied because their sources are bulk:

  W4_reexec.json    from W4/v001/full_bypass_clocked{,_b}.jsonl (6.3 MB of raw
                    per-run records).  Rule, stated so it can be re-run: index
                    by (instance, testbench), last record wins; keep the points
                    whose bypass AND clocked arms both returned code OK; count
                    those where both arms passed, both roots are equal, and both
                    equal the software oracle's expected root.

  W8_maxp.json      from W8_maxp/v00*/{status.txt,run_maxp.sh}: the xelab debug
                    configuration, exit status, elapsed time, peak RSS, and
                    whether xsim.dir/<snap>/xsimk was written.
"""
import json, os, re, sys

W = os.environ.get("SPRS_WFINAL", "/home/rohit/sprs-fix/experiments/w_final")
HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(os.path.dirname(HERE), "data", "wround")
os.makedirs(DEST, exist_ok=True)


def copy(src, name):
    with open(os.path.join(W, src), encoding="utf-8") as fh:
        doc = json.load(fh)
    with open(os.path.join(DEST, name), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    print(f"  copied {src} -> data/wround/{name}")


# ---- bulk copies -----------------------------------------------------------
copy("W1/RESULT.json", "W1_RESULT.json")
copy("W4/v002/ANALYSIS_full.json", "W4_ANALYSIS_full.json")
# v001's ANALYSIS.json was computed from a partially written file (its
# meta.n_runs = 605 against 1,326 raw keys) and is superseded by v002 for every
# comparison figure.  Only its negative_control block is read, and only because
# the corrupted-route arm is recorded nowhere else.
copy("W4/v001/ANALYSIS.json", "W4_negative_control.json")
copy("W9_selection/RESULT.json", "W9_RESULT.json")
# W2: pinned-FBT.  Five records, all small, all copied verbatim:
#   RESULT.json           the round's verdict, incl. the pre-registration
#                         deviation and the contention sensitivity bound
#   v001/partA_...json    the exhaustive (N,G) correctness sweep of the
#                         cut-aligned repair, with the paper-as-printed
#                         index-range construction as negative control
#   v002/imbalance.json   frontier load imbalance under two deals
#   v003/ANALYSIS_v2.json the on-hardware bitwise-invariance cells
#   v004/COST.json        the timed cost table (every row, both arms)
copy("W2/RESULT.json", "W2_RESULT.json")
copy("W2/v001/partA_correctness.json", "W2_partA.json")
copy("W2/v002/imbalance.json", "W2_imbalance.json")
copy("W2/v003/ANALYSIS_v2.json", "W2_invariance.json")
copy("W2/v004/COST.json", "W2_cost.json")
copy("W9_selection/RESULT_ksweep.json", "W9_ksweep.json")

# The CI script is vendored as provenance: the macro generator reads its
# bootstrap replication count directly from the source that produced the
# intervals rather than restating it.
import shutil
shutil.copy(os.path.join(W, "W9_selection", "w9b_ksweep_ci.py"),
            os.path.join(DEST, "W9_ksweep_ci.py"))
print("  copied W9_selection/w9b_ksweep_ci.py -> data/wround/W9_ksweep_ci.py")

# ---- W4 re-execution against the software oracle ---------------------------
rows = {}
for fn in ("full_bypass_clocked.jsonl", "full_bypass_clocked_b.jsonl"):
    path = os.path.join(W, "W4", "v001", fn)
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            r = json.loads(line)
            rows[(r["instance"], r["tb"])] = r          # last record wins
both, agree, insts = 0, 0, {}
for (inst, _tb), r in rows.items():
    b, c = r.get("bypass") or {}, r.get("clocked") or {}
    if b.get("code") == "OK" and c.get("code") == "OK":
        both += 1
        if (b.get("pass") and c.get("pass")
                and b.get("root") == c.get("root") == b.get("expected") == c.get("expected")):
            agree += 1
            insts.setdefault(inst, set()).add(b["root"])
# Coverage of the re-execution, joined against the instance table.
import csv as _csv
IC = os.environ.get("SPRS_INSTANCES",
                    "/home/rohit/sprs-fix/benchmarks/instances.csv")
ITAB = {r["instance"]: r for r in _csv.DictReader(open(IC, encoding="utf-8"))}
gs = [int(ITAB[i]["n_gpus"]) for i in insts if i in ITAB]
ns = [int(ITAB[i]["n_leaves"]) for i in insts if i in ITAB]
tp = sorted({ITAB[i]["topology"] for i in insts if i in ITAB})
# How much of the release those instances account for: the re-execution covered
# every passing configuration the trusted (max-over-PEs) results file records
# for them, so the count below must equal the number of re-executed points.
HW = os.environ.get("SPRS_HWCSV",
                    "/home/rohit/sprs-fix/results/results/live_hw_results_p1_maxpe.csv")
passing = sum(1 for r in _csv.DictReader(open(HW, encoding="utf-8"))
              if r["Instance"] in set(insts) and r["Pass"].strip().lower() == "true")
in_suite_le_gmax = sum(1 for r in ITAB.values()
                       if int(r["n_gpus"]) <= max(gs))

reexec = {
    "source": "W4/v001/full_bypass_clocked{,_b}.jsonl",
    "coverage": {"g_min": min(gs), "g_max": max(gs), "n_min": min(ns),
                 "n_max": max(ns), "topologies": tp,
                 "instances_in_suite_table": len(ITAB),
                 "suite_instances_at_or_below_g_max": in_suite_le_gmax,
                 "passing_release_rows_on_those_instances": passing},
    "rule": "index by (instance, testbench), last record wins",
    "n_keys": len(rows),
    "n_both_arms_ok": both,
    "n_agree_with_each_other_and_oracle": agree,
    "n_instances": len(insts),
    "n_instances_one_distinct_root": sum(1 for v in insts.values() if len(v) == 1),
}
json.dump(reexec, open(os.path.join(DEST, "W4_reexec.json"), "w"), indent=1)
print(f"  distilled W4 re-execution -> data/wround/W4_reexec.json  {reexec}")

# ---- W8: maxp_mod_fat elaboration attempts ---------------------------------
attempts = []
for v in sorted(os.listdir(os.path.join(W, "W8_maxp"))):
    d = os.path.join(W, "W8_maxp", v)
    st = os.path.join(d, "status.txt")
    sh = os.path.join(d, "run_maxp.sh")
    if not (os.path.isfile(st) and os.path.isfile(sh)):
        continue
    s, script = open(st, encoding="utf-8").read(), open(sh, encoding="utf-8").read()
    dbg = re.search(r"xelab[^\n]*?(-O0 --debug off|-debug typical)", script)
    log = os.path.join(d, "xelab.log")
    txt = open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) else ""
    rc = re.search(r"xelab rc=(-?\d+)", s)
    if rc is None and "Exit status:" in txt:
        rc = re.search(r"Exit status: (\d+)", txt)
    el = re.search(r"Elapsed \(wall clock\) time \([^)]*\):\s*([\d:.]+)", txt)
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", txt)
    # Snapshot contents: read the working directory directly when it is still
    # present (the ls listing in status.txt is overwritten if the script is
    # re-launched), otherwise fall back to that listing.
    wd = re.search(r"^WD=(\S+)", script, re.M)
    snap = os.path.join(wd.group(1), "xsim.dir", "maxp_snap") if wd else None
    if snap and os.path.isdir(snap):
        names = os.listdir(snap)
        nbytes = sum(os.path.getsize(os.path.join(snap, n)) for n in names)
        has_k = "xsimk" in names
        where = "filesystem"
    else:
        listing = re.findall(r"^-rw[^\n]*?\s(\d+)\s+\w{3}\s+\d+\s+[\d:]+\s+(\S+)$", s, re.M)
        nbytes = sum(int(b) for b, _ in listing)
        has_k = any(n == "xsimk" for _, n in listing)
        where = "status.txt listing"
    attempts.append({
        "version": v,
        "xelab_debug": dbg.group(1) if dbg else None,
        "xelab_rc": int(rc.group(1)) if rc else None,
        "elapsed": el.group(1) if el else None,
        "peak_rss_kb": int(rss.group(1)) if rss else None,
        "snapshot_dir": snap,
        "snapshot_read_from": where,
        "snapshot_bytes": nbytes,
        "snapshot_has_xsimk": has_k,
        "built_snapshot_line": "Built simulation snapshot" in txt,
        "no_snapshot_line": "NO_SNAPSHOT" in s,
    })
json.dump({"source": "W8_maxp/v00*/{status.txt,run_maxp.sh,xelab.log}",
           "attempts": attempts},
          open(os.path.join(DEST, "W8_maxp.json"), "w"), indent=1)
print("  distilled W8 maxp elaboration -> data/wround/W8_maxp.json")
for a in attempts:
    print("   ", a)
