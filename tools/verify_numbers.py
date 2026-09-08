#!/usr/bin/env python3
"""Re-derive every headline number in the paper from the released CSVs.

Run from the repo root. Exits non-zero if any claim fails to reproduce, so it
can gate a release. This is the check that keeps the manuscript honest: any
number quoted in the paper should appear here, computed from data.

MISSING INPUT IS A FAILURE, NOT A SKIP.  The earlier version guarded the
mutation block with `if os.path.exists(mp):` and guarded the HW loader with
`if not os.path.exists(p): return []`.  With data/mutation absent it therefore
ran 10 checks instead of 13 and still printed "all claims reproduce"; with
data/results absent the SW loop globbed zero files and reported 0 for every
count.  Every input this script needs is now declared up front in REQUIRED and
verified to exist and be non-empty before any checking starts, and the script
asserts at the end that it actually ran the full expected number of checks.
"""
import csv, glob, json, os, sys
from collections import defaultdict
csv.field_size_limit(sys.maxsize)

ROOT = os.environ.get("SPRS_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "data", "results")
MUT = os.path.join(ROOT, "data", "mutation")
fails = []
missing = []

# Every check this script performs, so that a silently-skipped block is caught.
EXPECTED_CHECKS = 13

# (path, kind, why) -- kind is 'dir', 'file' or 'glob'.
REQUIRED = [
    (RES, "dir", "per-instance software campaign results"),
    (os.path.join(RES, "*", "sw_results.csv"), "glob", "software campaign CSVs"),
    (os.path.join(RES, "live_hw_results_p1_unified.csv"), "file", "hardware campaign CSV"),
    (MUT, "dir", "mutation campaign results"),
    (os.path.join(MUT, "mutation_results.json"), "file", "mutation campaign JSON"),
]


def preflight():
    """Refuse to check anything until every declared input is present."""
    for path, kind, why in REQUIRED:
        if kind == "glob":
            hits = glob.glob(path)
            if not hits:
                missing.append(f"{path}  ({why}: no files match)")
            continue
        if not os.path.exists(path):
            missing.append(f"{path}  ({why}: absent)")
            continue
        if kind == "file" and os.path.getsize(path) == 0:
            missing.append(f"{path}  ({why}: empty)")
        if kind == "dir" and not os.path.isdir(path):
            missing.append(f"{path}  ({why}: not a directory)")
    if missing:
        print("REQUIRED INPUT MISSING -- refusing to report on partial data:")
        for m in missing:
            print(f"  [MISSING] {m}")
        print()
        print(f"SPRS_ROOT is {ROOT}.  The release ships these under data/; the review")
        print("snapshot renames that tree to results/.  Create the alias with")
        print(f"    ln -s results {os.path.join(ROOT, 'data')}")
        print(f"{len(missing)} required input(s) missing; 0 of {EXPECTED_CHECKS} claims checked.")
        sys.exit(2)


preflight()

n_checks = 0


def check(label, got, want, tol=0):
    global n_checks
    n_checks += 1
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
    # preflight() has already established that p exists and is non-empty; if it
    # vanished between then and now that is a hard error, not an empty list.
    if not os.path.exists(p):
        print(f"  [FAIL] hardware CSV disappeared during the run: {p}")
        sys.exit(2)
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
mp = os.path.join(MUT, "mutation_results.json")
d = json.load(open(mp))
det = sum(x['detected'] for v in d['by_N'].values() for x in v.values())
tt  = sum(x['total']    for v in d['by_N'].values() for x in v.values())
nv = sum(1 for r in d['runs'] if r['detected'] is None)
print("mutation campaign")
check("leaf classes covered", len(d['by_N']), 16)
check("mutants detected", det, tt)
# One mutant on maxp_dense_hc (N=8192) produced neither PASS nor FAIL. It is
# excluded from the detection rate rather than counted as a miss, and
# asserted here so the exclusion stays visible.
check("runs without a verdict", nv, 1)

print()
if n_checks != EXPECTED_CHECKS:
    print(f"CHECK COUNT MISMATCH: ran {n_checks} checks, expected {EXPECTED_CHECKS}.")
    print("A block was skipped. Refusing to report success on a partial run.")
    sys.exit(2)
if fails:
    print(f"{len(fails)} of {n_checks} claim(s) did not reproduce: {', '.join(fails)}")
    sys.exit(1)
print(f"all {n_checks} claims reproduce")
