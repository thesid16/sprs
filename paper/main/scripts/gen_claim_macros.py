#!/usr/bin/env python3
r"""
gen_claim_macros.py -- emit data/claim_macros.tex.

WHY THIS SCRIPT EXISTS.  data/claim_macros.tex shipped for months carrying the
banner "GENERATED FROM COUNCIL VERIFICATION -- do not edit by hand" while no
generator for it existed anywhere in scripts/ or the Makefile.  `make tables`
rewrote 27 of the 28 generated .tex files in this tree and never touched this
one, and scripts/verify_tables.py still counted it in "all 28 generated .tex
files reproduce" -- because verify_tables copies the whole paper to a scratch
directory and, with no generator to rewrite the copy, ended up diffing the file
against a byte-identical copy of itself.  The check could not fail.  That is how
\OrderLRDiff shipped printing "ten" when the value a referee recomputes from the
released source is twelve.

WHAT IT DOES.  Every macro below is either

  [COMPUTED]  re-derived here from released source (src/, rtl/, data/) and
              cross-checked against published output, or
  [DERIVED]   arithmetic over other values on this page, or
  [RECORD]    read out of an executed council verdict file, with the exact
              evidence string asserted present -- so an edited or replaced
              record makes this script FAIL rather than silently typeset a
              stale number (the pattern gen_fabric_macros.py already uses).

SELF-VALIDATION (hard, fails the build).  The \Order* block is produced by a
reconstruction of the canonical reducer -- leaf values per sprs_core's
make_leaf_val at alu_op=0b111, evaluated over the canonical heap-indexed
complete binary tree.  Before any \Order* macro is emitted the script requires
that reconstruction to reproduce ALL SIXTEEN 64-bit roots printed in
tables/invariance.tex, bit-exactly, and to agree with the released CBTree class
in src/sprs_core.py.  A generator that cannot validate itself against published
output is exactly how this defect happened; if the assertion does not hold,
nothing is written and the build stops.

Sources (all read-only):
  data/council/T03_verify.json  -- injected-fault campaign
  data/council/T04_verify.json  -- memory feasibility, static operand binding
  data/council/T07_verify.json  -- order sensitivity (sampling figures only)
  data/council/T14_verify.json  -- address recycling, asynchronous GENERATE
  data/mutation_results.json    -- the 108 recorded mutation runs
  src/sprs_core.py, rtl/*.sv    -- fabric/compiler constants
  tables/invariance.tex         -- the published roots the model is validated on

Usage:  python3 scripts/gen_claim_macros.py [--check]
        --check  validate and print, but do not write the file (exit 1 on any
                 failure, same as a normal run).
Macro names contain no digits (check_consistency.py C1).
"""
import argparse
import itertools
import json
import math
import os
import re
import struct
import sys
import textwrap
from collections import Counter

_AP = argparse.ArgumentParser(description=__doc__)
_AP.add_argument("--check", action="store_true",
                 help="validate only; do not write data/claim_macros.tex")
ARGS = _AP.parse_args()


def _wrap(note):
    return textwrap.wrap(note, 74) or [""]

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
ROOT = os.environ.get("SPRS_ROOT") or os.path.abspath(os.path.join(PAPER, ".."))
OUT = os.path.join(PAPER, "data", "claim_macros.tex")

FAIL = []


def die(msg):
    print("FAIL gen_claim_macros: " + msg, file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- inputs ----
def _council_default():
    cand = os.path.join(PAPER, "data", "council")
    return cand if os.path.isdir(cand) else \
        "/home/rohit/sprs-review/runs/20260817T230831Z/council/work"


COUNCIL = os.environ.get("SPRS_COUNCIL") or _council_default()


def load_council(name):
    p = os.path.join(COUNCIL, name)
    if not os.path.isfile(p):
        die(f"council record {name} not found under {COUNCIL}. "
            "Set $SPRS_COUNCIL, or vendor the record into <paper>/data/council/.")
    with open(p, encoding="utf-8") as fh:
        return json.dumps(json.load(fh))


def read_src(rel):
    p = os.path.join(ROOT, rel)
    if not os.path.isfile(p):
        die(f"released source {rel} not found under SPRS_ROOT={ROOT}")
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


T03 = load_council("T03_verify.json")
T04 = load_council("T04_verify.json")
T07 = load_council("T07_verify.json")
T14 = load_council("T14_verify.json")


def need(blob, needle, what):
    """Assert an evidence string is present in a source record."""
    if needle not in blob:
        FAIL.append(f"{what}: evidence string {needle!r} absent from its "
                    f"source council record")


def grab(text, pattern, what, group=1):
    """Pull a value out of released source; fail loudly if the anchor moved."""
    m = re.search(pattern, text)
    if not m:
        FAIL.append(f"{what}: pattern {pattern!r} no longer matches its "
                    f"released source file")
        return None
    return m.group(group)


# ------------------------------------------------- the canonical reducer ----
# Leaf values: sprs_core.py make_leaf_val(idx, op=0b111), the op every
# invariance-table row was compiled at.
def leaf_val(idx):
    return (idx + 1) * 1000.0 + ((idx * 37 + 13) % 100) / 100.0 + 0.007


def d2b(x):
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def canon_root(n_leaves):
    r"""evaluate(FBT(N), L, fadd): heap-indexed complete binary tree, node n has
    children 2n+1 and 2n+2, total_nodes = 2N-1, leaves at heap indices
    N-1..2N-2 ascending and carrying idx = 0..N-1 in that order (CBTree,
    src/sprs_core.py:395-437)."""
    total = 2 * n_leaves - 1
    v = [0.0] * total
    for i in range(n_leaves):
        v[n_leaves - 1 + i] = leaf_val(i)
    for n in range(n_leaves - 2, -1, -1):
        v[n] = v[2 * n + 1] + v[2 * n + 2]
    return v[0]


def seq_root(n_leaves, reverse=False):
    idxs = range(n_leaves - 1, -1, -1) if reverse else range(n_leaves)
    s = 0.0
    for i in idxs:
        s = s + leaf_val(i)
    return s


def published_roots():
    """The sixteen (N, root) pairs printed in tables/invariance.tex."""
    p = os.path.join(PAPER, "tables", "invariance.tex")
    if not os.path.isfile(p):
        die("tables/invariance.tex is missing -- the \\Order* block cannot be "
            "validated against published output.  Run gen_tables.py first "
            "(the Makefile orders it before this script).")
    out = {}
    for ln in open(p, encoding="utf-8"):
        m = re.match(r"\s*(\d+)\s*&.*\\texttt\{0x([0-9A-Fa-f]{16})\}", ln)
        if m:
            out[int(m.group(1))] = int(m.group(2), 16)
    return out


PUB = published_roots()
NS = sorted(PUB)
if len(NS) != 16:
    die(f"tables/invariance.tex yielded {len(NS)} root rows, expected 16")

# ---- HARD SELF-VALIDATION 1: reproduce every published root, bit-exactly ----
mismatch = [(N, "0x%016X" % d2b(canon_root(N)), "0x%016X" % PUB[N])
            for N in NS if d2b(canon_root(N)) != PUB[N]]
if mismatch:
    print("FAIL gen_claim_macros: the reconstructed canonical reducer does NOT "
          "reproduce tables/invariance.tex.", file=sys.stderr)
    print("  Nothing was written.  Every \\Order* macro is derived from this "
          "model, so it may not be trusted until it reproduces published "
          "output 16/16.", file=sys.stderr)
    for N, got, want in mismatch:
        print(f"    N={N:<6} model={got}  published={want}", file=sys.stderr)
    print(f"  {len(mismatch)} of {len(NS)} roots differ.", file=sys.stderr)
    sys.exit(1)

# ---- HARD SELF-VALIDATION 2: agree with the released CBTree class ----------
sys.path.insert(0, os.path.join(ROOT, "src"))
try:
    import sprs_core as _sc                                    # noqa: E402
except Exception as e:                                          # pragma: no cover
    die(f"cannot import src/sprs_core.py ({e!r}); the tree shape used by the "
        "\\Order* block cannot be cross-checked against the released compiler")


def cbtree_root(n_leaves):
    t = _sc.CBTree(n_leaves)
    v = {}
    for k, n in enumerate(t.leaves()):
        v[n] = leaf_val(k)
    for n in sorted(t.internals(), reverse=True):
        v[n] = v[t.left_child(n)] + v[t.right_child(n)]
    return v[0]


bad_shape = [N for N in NS if d2b(cbtree_root(N)) != PUB[N]]
if bad_shape:
    die("the released CBTree class in src/sprs_core.py no longer yields the "
        f"published roots at N in {bad_shape}; the reconstruction and the "
        "compiler have diverged")

# ---------------------------------------------------------- formatting ------
WORDS = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
         6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
         11: "eleven", 12: "twelve"}


def word(n):
    if n not in WORDS:
        die(f"no spelled-out form for {n}")
    return WORDS[n]


def tex_int(n):
    return f"{int(n):,}".replace(",", "{,}")


def pct1(num, den):
    return f"{round(100.0 * num / den, 1):.1f}\\%"


M = []


def emit(name, value, note):
    M.append((name, str(value), note))


# ============================================================================
# T14 -- local-temporary address recycling
# ============================================================================
need(T14, "562 compiled configurations", "RecycleConfigs")
need(T14, "108,607 recycled addresses and 397,422 reuse events",
     "RecycleAddrs/RecycleEvents")
need(T14, "rem_readers_1_selfcompute = 273,009 (68.7%)", "RecycleSelfReaderPct")
need(T14, "rem_readers_0 = 124,413 (31.3%)", "RecycleZeroReaderPct")
need(T14, "UNSAFE_read_after_overwrite = 0", "RecycleUnsafe")

RECYCLE_CONFIGS = 562
RECYCLE_ADDRS = 108607
RECYCLE_EVENTS = 397422
REM_SELF = 273009
REM_ZERO = 124413
UNSAFE = 0
if REM_SELF + REM_ZERO != RECYCLE_EVENTS:
    FAIL.append("T14 reuse-event classes do not sum to the reuse-event total "
                f"({REM_SELF} + {REM_ZERO} != {RECYCLE_EVENTS})")

emit("RecycleConfigs", tex_int(RECYCLE_CONFIGS),
     "[RECORD] T14: 562 compiled configurations (all TEST_INSTANCES with "
     "N<=2048 x all STAGE2_METHODS)")
emit("RecycleAddrs", tex_int(RECYCLE_ADDRS), "[RECORD] T14")
emit("RecycleEvents", tex_int(RECYCLE_EVENTS), "[RECORD] T14")
emit("RecycleUnsafe", word(UNSAFE),
     "[RECORD] T14: UNSAFE_read_after_overwrite = 0")
emit("RecycleZeroReaderPct", pct1(REM_ZERO, RECYCLE_EVENTS),
     f"[DERIVED] {REM_ZERO}/{RECYCLE_EVENTS} reuse events with zero remaining "
     "readers")
emit("RecycleSelfReaderPct", pct1(REM_SELF, RECYCLE_EVENTS),
     f"[DERIVED] {REM_SELF}/{RECYCLE_EVENTS} reuse events matching rem:recycle")

# ---- T14 -- asynchronous GENERATE into a recycled slot ---------------------
need(T14, "29,097 of 82,084 GENERATEs (35.4%)", "GenRecycled/GenTotal")
need(T14, "GCI gap leaves min 6 / median 12 cycles", "GciGapMin/GciGapMedian")
GEN_TOTAL, GEN_RECYCLED, GCI_GAP_MIN, GCI_GAP_MED = 82084, 29097, 6, 12
emit("GenTotal", tex_int(GEN_TOTAL), "[RECORD] T14, N<=512 instances")
emit("GenRecycled", tex_int(GEN_RECYCLED), "[RECORD] T14")
emit("GenRecycledPct", pct1(GEN_RECYCLED, GEN_TOTAL),
     f"[DERIVED] {GEN_RECYCLED}/{GEN_TOTAL}")

# GCI_LATENCY is a released RTL parameter -- compute it, do not transcribe.
_ni = read_src("rtl/noc_ni.sv")
gci_lat = grab(_ni, r"parameter\s+int\s+GCI_LATENCY\s*=\s*(\d+)", "GciLatency")
emit("GciLatency", gci_lat, "[COMPUTED] rtl/noc_ni.sv parameter GCI_LATENCY")
emit("GciGapMin", GCI_GAP_MIN, "[RECORD] T14: compiler's GCI gap, min")
emit("GciGapMedian", GCI_GAP_MED, "[RECORD] T14: compiler's GCI gap, median")

# ============================================================================
# T04 -- memory feasibility and the DMEM counterexample
# ============================================================================
_core = read_src("src/sprs_core.py")
dmem_depth = grab(_core, r"dmem_depth\s*:\s*int\s*=\s*(\d+)", "DmemDepth")
DMEM_DEPTH = int(dmem_depth) if dmem_depth else 0

need(T04, "Disconnected partitions: n=437, median 25, MAX 491", "DmemPeakMax")
need(T04, "Peak DMEM = 522 > 512, so 11 emitted addresses exceed the depth",
     "DmemCexPeak/DmemCexOver")
need(T04, "FBT(512), G=2, linear", "DmemCexLeaves/DmemCexWorkers")
DMEM_PEAK_MAX, CEX_LEAVES, CEX_WORKERS = 491, 512, 2

emit("DmemDepth", DMEM_DEPTH,
     "[COMPUTED] src/sprs_core.py HW.dmem_depth (= rtl DMEM_DEPTH)")
emit("DmemPeakMax", DMEM_PEAK_MAX,
     "[RECORD] T04: max peak DMEM over the 681 (instance,s2) pairs")
emit("DmemMargin", DMEM_DEPTH - DMEM_PEAK_MAX,
     f"[DERIVED] {DMEM_DEPTH} - {DMEM_PEAK_MAX}")

# ---- the counterexample, RECONSTRUCTED rather than transcribed -------------
# T04-X2: FBT(512) on G=2 with every leaf on PE0 and every internal node on
# PE1.  Run the released allocator on exactly that assignment and read both
# numbers off it.  Peak DMEM is "max allocated slot + 1", per PE; the
# over-depth count is over the whole emitted image, i.e. summed over PEs --
# 10 on PE1 plus 1 on PE0.  Deriving DmemCexOver as (peak - depth) instead
# gives 10 and is WRONG: it silently drops PE0's single over-depth address.
_cex_tree = _sc.CBTree(CEX_LEAVES)
_cex_asg = {n: (0 if _cex_tree.is_leaf(n) else 1)
            for n in range(_cex_tree.total_nodes)}
if hasattr(_sc, "_validate_assignment") and \
        not _sc._validate_assignment(_cex_tree, _cex_asg, CEX_WORKERS):
    FAIL.append("the T04-X2 counterexample assignment is no longer legal under "
                "_validate_assignment; the construction has changed")
_cex_map = _sc.DMEMAllocator(_cex_tree, _cex_asg, CEX_WORKERS).allocate()
_cex_peaks = {g: (max(a.values()) + 1 if a else 0) for g, a in _cex_map.items()}
CEX_PEAK = max(_cex_peaks.values())
CEX_OVER = sum(len({a for a in _cex_map[g].values() if a >= DMEM_DEPTH})
               for g in _cex_map)
if str(CEX_PEAK) not in T04 or f"so {CEX_OVER} emitted addresses" not in T04:
    FAIL.append(f"the reconstructed counterexample gives peak {CEX_PEAK} and "
                f"{CEX_OVER} over-depth addresses, which is not what the T04 "
                "record reports")
emit("DmemCexLeaves", CEX_LEAVES, "[RECORD] T04-X2 construction: FBT(512)")
emit("DmemCexWorkers", CEX_WORKERS,
     "[RECORD] T04-X2 construction: G=2, linear, leaves on PE0")
emit("DmemCexPeak", CEX_PEAK,
     "[COMPUTED] max over PEs of (max allocated DMEM slot + 1) from the "
     "released DMEMAllocator on that construction; per-PE peaks "
     + ", ".join(f"PE{g}={p}" for g, p in sorted(_cex_peaks.items())))
emit("DmemCexOver", CEX_OVER,
     f"[COMPUTED] distinct emitted addresses >= DMEM_DEPTH ({DMEM_DEPTH}), "
     "summed over PEs: "
     + " + ".join(
         f"{len({a for a in _cex_map[g].values() if a >= DMEM_DEPTH})} on PE{g}"
         for g in sorted(_cex_map)))

# SEND target addresses are truncated to the ex_dest slice the FSM puts on the
# transmit word -- read the width out of the RTL rather than trusting prose.
_fsm = read_src("rtl/btree_fsm_fast.sv")
hi = grab(_fsm, r"fsm_txf_data\s*=\s*\{ex_addr_b,\s*ex_dest\[(\d+):0\]",
          "SendAddrBits")
emit("SendAddrBits", word(int(hi) + 1) if hi else "?",
     "[COMPUTED] rtl/btree_fsm_fast.sv: ex_dest slice on fsm_txf_data")

# ---- T04 -- static operand-binding check on the emitted images -------------
need(T04, "681 campaign configurations", "BindConfigs")
need(T04, "1,010,895 COMPUTE and 731,982 SEND instructions",
     "BindComputes/BindSends")
need(T04, "bind_wrong=0, multi_remote_write=0", "BindViolations")
need(T04, "2,061 of 2,822 (73.0%)", "DisconnCount")
BIND_CONFIGS, BIND_COMPUTES, BIND_SENDS = 681, 1010895, 731982
DISCONN, PASSING = 2061, 2822
emit("BindConfigs", tex_int(BIND_CONFIGS), "[RECORD] T04")
emit("BindComputes", tex_int(BIND_COMPUTES), "[RECORD] T04")
emit("BindSends", tex_int(BIND_SENDS), "[RECORD] T04")
emit("BindViolations", word(0),
     "[RECORD] T04: bind_wrong=0 and every other violation class 0")
emit("DisconnCount", tex_int(DISCONN),
     "[RECORD] T04: passing HW configs with a disconnected partition")
emit("DisconnShare", pct1(DISCONN, PASSING),
     f"[DERIVED] {DISCONN}/{PASSING} passing HW configurations")

# ---- router-id addressability of the adjacency interface -------------------
# Both values are released RTL facts: the adjacency field width, and the
# all-ones code reserved as the disconnected sentinel.
_nsys = read_src("rtl/noc_system.sv")
adj_w = grab(_nsys, r"parameter\s+int\s+ADJ_ID_W\s*=\s*(\d+)", "RouterIdBits")
need(_nsys, "ADJ_DISC_CODE = {ADJ_ID_W{1'b1}}", "RouterIdMax sentinel")
ADJ_W = int(adj_w) if adj_w else 0
emit("RouterIdBits", ADJ_W, "[COMPUTED] rtl/noc_system.sv parameter ADJ_ID_W")
emit("RouterIdMax", tex_int((1 << ADJ_W) - 2) if ADJ_W else "?",
     f"[DERIVED] 2^{ADJ_W} - 2: the all-ones code is the disconnected sentinel")

# ============================================================================
# T03 -- presence boundary and the injected-fault campaign
# ============================================================================
_pkg = read_src("rtl/btree_pkg.sv")
wdog = grab(_pkg, r"parameter\s+int\s+WATCHDOG_MAX\s*=\s*(\d+)", "WatchdogMax")
emit("WatchdogMax", tex_int(int(wdog)) if wdog else "?",
     "[COMPUTED] rtl/btree_pkg.sv parameter WATCHDOG_MAX")

# The mutation campaign's own released record: count the runs, do not transcribe.
_mut_p = os.path.join(PAPER, "data", "mutation_results.json")
if not os.path.isfile(_mut_p):
    die("data/mutation_results.json is missing; the \\Mut* block cannot be "
        "counted from the released campaign record")
_mut = json.load(open(_mut_p, encoding="utf-8"))
_runs = _mut.get("runs")
if not _runs:
    die("data/mutation_results.json carries no 'runs' array")
_kinds = Counter(r["kind"] for r in _runs)
_detected = sum(1 for r in _runs if r.get("detected") is True)
for k in ("addr_sub", "leaf_corrupt"):
    if k not in _kinds:
        FAIL.append(f"data/mutation_results.json has no {k!r} runs")
emit("MutAddrSub", _kinds["addr_sub"],
     "[COMPUTED] data/mutation_results.json: runs with kind=addr_sub")
emit("MutLeaf", _kinds["leaf_corrupt"],
     "[COMPUTED] data/mutation_results.json: runs with kind=leaf_corrupt")
emit("MutTotal", _detected,
     f"[COMPUTED] data/mutation_results.json: runs with detected=true "
     f"(of {len(_runs)} recorded)")

need(T03, "43 of 54 target an address NO agent ever writes", "MutAddrStall")
need(T03, "at most 11 of the 54 addr_sub mutants", "MutLiveSlotMax")
if _kinds["addr_sub"] != 54:
    FAIL.append("T03's addr_sub classification is stated over 54 mutants but "
                f"the released record holds {_kinds['addr_sub']}")
emit("MutAddrStall", 43,
     "[RECORD] T03: addr_sub mutants repointing at an address no agent ever "
     "writes, so the COMPUTE stalls and the fabric fail-stops")
emit("MutLiveSlotMax", word(11),
     "[RECORD] T03: upper bound on addr_sub mutants that reach a live slot")

# ============================================================================
# T07 -- order sensitivity of the canonical association order
#        COMPUTED from the model validated 16/16 above.  The council record is
#        used for the two sampled probabilities only.
# ============================================================================
ulp = [(abs(d2b(seq_root(N, reverse=True)) - PUB[N]), N) for N in NS]
ULP_MAX, ULP_MAX_N = max(ulp)
emit("OrderUlpMax", ULP_MAX,
     "[COMPUTED] max ulp distance, right-to-left sequential vs Rcan, over the "
     "sixteen leaf counts")
emit("OrderUlpMaxN", ULP_MAX_N, "[COMPUTED] the N attaining OrderUlpMax")

lr_agree = [N for N in NS if d2b(seq_root(N)) == PUB[N]]
LR_DIFF = len(NS) - len(lr_agree)
# The T07 verdict reports 10 here.  It is superseded by this computation, which
# reproduces the published roots 16/16 and the record's own sentence-mate
# (OrderUlpMax = 55 at N = 8192) exactly.  Assert the stale figure is still the
# one in the record, so that a corrected record forces this note to be revisited
# rather than leaving two live numbers with no reconciliation.
need(T07, "Left-to-right sequential differs from canonical at 10 of my 16 N",
     "OrderLRDiff (superseded council figure)")
emit("OrderLRDiff", word(LR_DIFF),
     "[COMPUTED] left-to-right sequential differs from Rcan at this many of "
     "the sixteen leaf counts; they agree only at N = "
     + ", ".join(str(n) for n in lr_agree) +
     ".  SUPERSEDES T07_verify.json, which reports 10.")

# Exhaustive at N=8: every leaf permutation through FBT(8).
_base = [leaf_val(i) for i in range(8)]
_perm = Counter()
for _p in itertools.permutations(range(8)):
    _v = [0.0] * 15
    for _k, _i in enumerate(_p):
        _v[7 + _k] = _base[_i]
    for _n in range(6, -1, -1):
        _v[_n] = _v[2 * _n + 1] + _v[2 * _n + 2]
    _perm[d2b(_v[0])] += 1
PERMS_EIGHT = sum(_perm.values())
if PERMS_EIGHT != math.factorial(8):
    die(f"permutation enumeration at N=8 covered {PERMS_EIGHT}, expected 8!")
CANON8 = PUB[8]
if CANON8 not in _perm:
    die("the canonical root is not among the roots reachable by permuting the "
        "leaves at N=8 -- the model is inconsistent")
emit("OrderPermsEight", tex_int(PERMS_EIGHT),
     "[COMPUTED] 8! leaf permutations through FBT(8), enumerated exhaustively")
emit("OrderRootsEight", word(len(_perm)),
     "[COMPUTED] distinct 64-bit roots over all 8! permutations")
emit("OrderCanonPctEight", pct1(_perm[CANON8], PERMS_EIGHT),
     f"[COMPUTED] {_perm[CANON8]}/{PERMS_EIGHT} permutations give the canonical "
     "root")
emit("OrderDetectEight",
     f"{round(1.0 - _perm[CANON8] / PERMS_EIGHT, 3):.3f}",
     "[COMPUTED] 1 - P(random leaf permutation reproduces Rcan) at N=8")

# Exhaustive at N=16: every in-order binary tree shape, by interval DP.
_L = [leaf_val(i) for i in range(16)]
_dp = {(i, i): {_L[i]: 1} for i in range(16)}
for _ln in range(2, 17):
    for _i in range(0, 16 - _ln + 1):
        _j = _i + _ln - 1
        _acc = {}
        for _k in range(_i, _j):
            for _a, _ca in _dp[(_i, _k)].items():
                for _b, _cb in _dp[(_k + 1, _j)].items():
                    _s = _a + _b
                    _acc[_s] = _acc.get(_s, 0) + _ca * _cb
        _dp[(_i, _j)] = _acc
_root16 = _dp[(0, 15)]
SHAPES = sum(_root16.values())
_catalan15 = math.comb(30, 15) // 16
if SHAPES != _catalan15:
    die(f"in-order shape enumeration at N=16 covered {SHAPES}, expected "
        f"Catalan(15) = {_catalan15}")
_bits16 = Counter()
for _v, _c in _root16.items():
    _bits16[d2b(_v)] += _c
if PUB[16] not in _bits16:
    die("the canonical root is not among the roots reachable by reassociating "
        "at N=16 -- the model is inconsistent")
emit("OrderShapesSixteen", tex_int(SHAPES),
     "[COMPUTED] Catalan(15) in-order binary tree shapes over 16 leaves, "
     "enumerated exhaustively by interval DP")
emit("OrderRootsSixteen", word(len(_bits16)),
     "[COMPUTED] distinct 64-bit roots over all "
     f"{tex_int(SHAPES)} shapes, spanning "
     f"{max(_bits16) - min(_bits16)} ulp")

# The two sampled probabilities are a 1,000-sample-per-N measurement recorded in
# T07; they are the only values on this page that are not recomputed here.
need(T07, "0.08 at N=1500", "OrderProbMin")
need(T07, "0.90 at N=1024", "OrderProbMax")
emit("OrderProbMin", "0.08",
     "[RECORD] T07: min over the sixteen N of P(a sampled reassociation moves "
     "the root), 1,000 samples per N.  Sampled, not exhaustive: the only value "
     "here that is not recomputed.")
emit("OrderProbMax", "0.90", "[RECORD] T07: max of the same measurement")

# ------------------------------------------------------------------ emit ----
if FAIL:
    for f in FAIL:
        print("FAIL gen_claim_macros: " + f, file=sys.stderr)
    print(f"{len(FAIL)} check(s) failed; data/claim_macros.tex NOT written.",
          file=sys.stderr)
    sys.exit(1)

seen = set()
for n, _, _ in M:
    if n in seen:
        die(f"duplicate macro {n}")
    seen.add(n)
    if re.search(r"\d", n):
        die(f"macro name {n} contains a digit (check_consistency.py C1)")

BLOCKS = [
    ("T14: local-temporary address recycling", "Recycle"),
    ("T14: asynchronous GENERATE into a recycled slot", "Gen|Gci"),
    ("T04: memory feasibility and the DMEM counterexample", "Dmem|SendAddr"),
    ("T04: static operand-binding check on the emitted images", "Bind|Disconn"),
    ("T04/T13: router-id addressability of the adjacency interface", "RouterId"),
    ("T03: presence boundary and the injected-fault campaign", "Watchdog|Mut"),
    ("T07: order sensitivity of the canonical association order", "Order"),
]

lines = [
    "% GENERATED by scripts/gen_claim_macros.py -- do not edit by hand.",
    "% source : data/council/{T03,T04,T07,T14}_verify.json,",
    "%          data/mutation_results.json, src/sprs_core.py, rtl/*.sv,",
    "%          tables/invariance.tex",
    "% method : [COMPUTED] re-derived from released source here;",
    "%          [DERIVED]  arithmetic over other values on this page;",
    "%          [RECORD]   read from an executed council verdict, with the",
    "%                     evidence string asserted present at generation.",
    "% self-validation : the \\Order* block comes from a reconstruction of the",
    "%          canonical reducer that this script requires to reproduce all",
    f"%          {len(NS)} roots of tables/invariance.tex bit-exactly, and to agree",
    "%          with the released CBTree class, before anything is written.",
    f"%          It does: {len(NS)}/{len(NS)}.",
    "",
]
for title, pat in BLOCKS:
    rx = re.compile(r"^(?:%s)" % pat)
    grp = [(n, v, note) for (n, v, note) in M if rx.match(n)]
    if not grp:
        die(f"block {title!r} matched no macros")
    lines.append("%% ---- %s %s" % (title, "-" * max(3, 68 - len(title))))
    for n, v, note in grp:
        for i, chunk in enumerate(_wrap(note)):
            lines.append(("%   " if i else "% ") + chunk)
        lines.append(f"\\newcommand{{\\{n}}}{{{v}}}")
    lines.append("")

emitted = sum(1 for ln in lines if ln.startswith("\\newcommand"))
if emitted != len(M):
    die(f"emitted {emitted} macros but built {len(M)} -- a block filter dropped one")

text = "\n".join(lines).rstrip("\n") + "\n"
if ARGS.check:
    print(f"OK: {emitted} macros validate ({len(NS)}/{len(NS)} published roots "
          f"reproduced); --check, nothing written")
else:
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote {OUT} ({emitted} macros; {len(NS)}/{len(NS)} published roots "
          f"reproduced by the reducer model)")
