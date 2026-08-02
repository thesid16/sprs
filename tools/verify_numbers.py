#!/usr/bin/env python3
"""Re-derive every headline number in the paper from the released CSVs.

Run from the repo root. Exits non-zero if any claim fails to reproduce, so it
can gate a release. This is the check that keeps the manuscript honest: any
number quoted in the paper should appear here, computed from data.
"""
import csv, glob, json, os, sys
from collections import defaultdict
csv.field_size_limit(sys.maxsize)

ROOT = os.environ.get("SPRS_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "data", "results")
fails = []

def check(label, got, want, tol=0):
    ok = abs(got - want) <= tol if isinstance(want, (int, float)) else got == want
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}: {got}" + ("" if ok else f"  (expected {want})"))
    if not ok:
        fails.append(label)

# --- SW campaign ---
tot = valid = 0
codes = defaultdict(int)
tbh, ash = set(), set()
for p in glob.glob(f"{RES}/*/sw_results.csv"):
    for r in csv.DictReader(open(p, newline='')):
        tot += 1
        codes[r['error_code'] or 'BLANK'] += 1
        if r['valid'] == 'True':
            valid += 1
            if r['tb_hash']: tbh.add(r['tb_hash'])
            if r['asgn_hash']: ash.add(r['asgn_hash'])
print("software campaign")
check("compilations attempted", tot, 7200)
check("feasible", valid, 6785)
check("unique testbenches", len(tbh), 2920)
check("unique assignments", len(ash), 622)
check("size-gated failures", codes.get('E_BYPASSED', 0), 390)
check("IMEM overflow failures", codes.get('E_IMEM_OF', 0), 278)
check("evaluation timeouts", codes.get('E_EVAL_TIMEOUT', 0), 33)

# --- HW campaign ---
def load(p):
    if not os.path.exists(p): return []
    rows = []
    with open(p, newline='', encoding='utf-8', errors='replace') as f:
        rd = csv.reader(f); first = next(rd, None)
        if first and first[0] != 'Instance' and len(first) >= 7: rows.append(first)
        rows += [r for r in rd if len(r) >= 7]
    return rows
hw = load(f"{RES}/live_hw_results_p1_unified.csv")
print("hardware campaign (original)")
check("HW rows", len(hw), 2844)
check("passing", sum(1 for r in hw if r[3] == 'True'), 2822)
check("instances covered", len({r[0] for r in hw if r[3] == 'True'}), 39)

# --- mutation ---
mp = os.path.join(ROOT, "data", "mutation", "mutation_results.json")
if os.path.exists(mp):
    d = json.load(open(mp))
    det = sum(x['detected'] for v in d['by_N'].values() for x in v.values())
    tt  = sum(x['total']    for v in d['by_N'].values() for x in v.values())
    print("mutation campaign")
    check("mutants detected", det, tt)
    check("no-verdict runs", sum(1 for r in d['runs'] if r['detected'] is None), 0)

print()
if fails:
    print(f"{len(fails)} claim(s) did not reproduce: {', '.join(fails)}")
    sys.exit(1)
print("all claims reproduce")
