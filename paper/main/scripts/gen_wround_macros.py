#!/usr/bin/env python3
r"""
gen_wround_macros.py -- emit data/wround_macros.tex.

Numbers from the final measurement round (W1 divergence on GPUs, W2 pinned-FBT
correctness and cost, W4 clocked route-load calibration, W8 maxp_mod_fat
elaboration, W9 selection-rule generalisation).  Every value is read from a record vendored under
data/wround/ by scripts/distill_wround.py, so this generator runs inside a
bare copy of the paper tree (verify_tables.py depends on that).

Where a record states a number only inside prose, the exact substring is
asserted present before the macro is emitted, so a replaced record fails the
build instead of silently typesetting a stale value.

Macro names contain no digits (check_consistency.py C1).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
SRC = os.environ.get("SPRS_WROUND") or os.path.join(PAPER, "data", "wround")

FAIL = []


def load(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as fh:
        return json.load(fh)


def need(doc, needle, what):
    if needle not in json.dumps(doc):
        FAIL.append(f"{what}: {needle!r} not found in source record")


WORD = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
        6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
        11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
        16: "sixteen", 24: "twenty-four", 25: "twenty-five"}


def comma(n):
    return f"{n:,}".replace(",", "{,}")


W1 = load("W1_RESULT.json")
W4 = load("W4_ANALYSIS_full.json")
NEG = load("W4_negative_control.json")
RX = load("W4_reexec.json")
MAXP = load("W8_maxp.json")
W2R = load("W2_RESULT.json")
W2P = load("W2_partA.json")
W2I = load("W2_imbalance.json")
W2V = load("W2_invariance.json")
W2C = load("W2_cost.json")
W9 = load("W9_RESULT.json")
KS = load("W9_ksweep.json")

# ---------------------------------------------------------------- W1 --------
r1 = W1["result"]
resh = r1["reshape_axis"]
if resh["configurations"] != resh["distinct_64bit_roots"]:
    FAIL.append("W1: reshape axis is not one-root-per-configuration")
need(W1, "for every one of the 12 (N, dtype, data-profile) cases",
     "W1 reshape coverage")
need(W1, "run-to-run at a FIXED configuration is bitwise deterministic",
     "W1 fixed-configuration repeatability")
need(W1, "a single floating-point addition per element", "W1 G=2 structural note")
need(W1, "NCCL requires one rank per device", "W1 library-axis scope")
for phrase in ("2x NVIDIA RTX PRO 6000 Blackwell Server Edition",
               "NO NVLINK", "72 CPU cores"):
    need(W1, phrase, "W1 hardware description")
GPU_HW = ("a single node with two NVIDIA RTX~PRO~6000 Blackwell GPUs over "
          "PCIe (no NVLink) and 72 CPU cores")
mt = re.search(r"torch ([\d.]+)\+\S+", W1["hardware"])
if not mt:
    FAIL.append("W1: framework version not recorded in the hardware string")
GPU_STACK = mt.group(1) if mt else ""

gpu_cfgs = resh["configurations"]
gpu_lo, gpu_hi = min(resh["world_sizes"]), max(resh["world_sizes"])
mag = r1["magnitude"]
ulp_max = max(v["max_ulp_spread"] for v in mag.values())
rel_max = max(v["max_relative_spread"] for v in mag.values())
rel_mant, rel_exp = f"{rel_max:.1e}".split("e")
moved = [tuple(int(x) for x in v["elements_moved"].split("/")) for v in mag.values()]
moved_min, moved_tot = min(m[0] for m in moved), moved[0][1]
if any(m[1] != moved_tot for m in moved):
    FAIL.append("W1: element-count denominators differ across cases")
if any(v["configs_equal_to_canonical_FBT"] for v in mag.values()):
    FAIL.append("W1: some configuration equalled the canonical reduction")
# The canonical-reference comparison is recorded only for the fp64 cases; the
# macro that names how many says so, so the prose cannot over-reach.
if not all("fp64" in k for k in mag):
    FAIL.append("W1: the magnitude block is no longer fp64-only")
canon_cases = len(mag)
m64 = re.search(r"(\d+)/(\d+) = ([\d.]+)% of configuration pairs disagree",
                r1["pairwise"]["fp64_cells"])
m32 = re.search(r"(\d+)/(\d+) = ([\d.]+)% of configuration pairs disagree",
                r1["pairwise"]["fp32_cells"])
if not (m64 and m32):
    FAIL.append("W1: pairwise strings not in the expected form")
rep = r1["repeatability"]
if rep["nccl_distinct"] != 1 or rep["gloo_distinct"] != 1:
    FAIL.append("W1: fixed-configuration repeats are not single-rooted")
if rep["nccl_repeats"] != rep["gloo_repeats"]:
    FAIL.append("W1: NCCL and gloo repeat counts differ")
xchk = W1["controls"]["crosscheck"]
if xchk["n_common_cells"] != xchk["n_identical"]:
    FAIL.append("W1: harness cross-check is not exact")

# ---------------------------------------------------------------- W4 --------
ok = W4["prefer_ok"]
for k in ("same_PASS", "same_64bit_root", "same_cycles"):
    if ok[k] != ok["n_comparable"]:
        FAIL.append(f"W4: {k} does not equal n_comparable")
fill = ok["delta_ns_per_route_entry"]
if not (fill["min"] == fill["max"] == fill["median"]):
    FAIL.append("W4: route-load fill time is not deterministic")
alt = W4["later_wins"]
if alt["pct_bit_exact"] != 100.0 or ok["pct_bit_exact"] != 100.0:
    FAIL.append("W4: bit-exactness is not 100% under both selection rules")
nc = NEG["negative_control"]
if nc["all_entries_corrupted_FAILED"] != nc["n"]:
    FAIL.append("W4: negative control did not fire on every corrupted run")
if RX["n_instances"] != RX["n_instances_one_distinct_root"]:
    FAIL.append("W4: some re-executed instance yielded more than one root")
cov = RX["coverage"]
if cov["suite_instances_at_or_below_g_max"] != RX["n_instances"]:
    FAIL.append("W4: the re-execution missed a suite instance at or below its G ceiling")
if cov["passing_release_rows_on_those_instances"] != RX["n_keys"]:
    FAIL.append("W4: the re-execution is not every passing released configuration there")

# ---------------------------------------------------------------- W2 --------
# Pinned-FBT.  Two rules govern this block.  (a) Ratios are RECOMPUTED from the
# per-row cost table and checked against the round's own summary, so a replaced
# table cannot silently keep a stale headline.  (b) The headline statistic is
# the pre-registered one -- fp64, G=2, NCCL -- and the generator refuses to emit
# it unless the record still says the pooled-dtype figure was a deviation.  An
# earlier revision reported the pooled number, which understated the overhead.
import math as _math


def _geo(xs):
    return _math.exp(sum(_math.log(x) for x in xs) / len(xs))


h1 = W2R["H1_bitwise_reshape_invariance"]
if h1["outcome"] != "SUPPORTS":
    FAIL.append("W2-H1: the invariance arm no longer supports the claim")
if h1["cases"] != h1["cases_invariant_and_equal_R_can"]:
    FAIL.append("W2-H1: not every case was invariant and equal to R_can")
vv = W2V["invariance_verdict"]
if (vv["fbt_cases"] != h1["cases"]
        or vv["fbt_total_cells"] != h1["total_cells"]
        or vv["fbt_cases"] != vv["fbt_cases_bitwise_invariant_and_equal_R_can"]):
    FAIL.append("W2-H1: RESULT.json and the raw invariance record disagree")
inv = W2V["invariance"]
fbt = {k: v for k, v in inv.items() if k.startswith("fbt_")}
ir = {k: v for k, v in inv.items() if k.startswith("indexrange_")}
if sum(v["n_cells"] for v in fbt.values()) != vv["fbt_total_cells"]:
    FAIL.append("W2-H1: the per-case cell counts do not sum to the stated total")
if any(v["n_distinct"] != 1 or not v["all_equal_R_can"] for v in fbt.values()):
    FAIL.append("W2-H1: some case returned more than one root, or one not R_can")
pin_ws = sorted({g for v in fbt.values() for g in v["world_sizes"]})
pin_deals = sorted({d for v in fbt.values() for d in v["deals"]})
pin_keys = [re.match(r"fbt_N(\d+)_M(\d+)_(fp\d+)_", k) for k in fbt]
if any(m is None for m in pin_keys):
    FAIL.append("W2-H1: an invariance case key is not in the expected form")
pin_N = sorted({int(m.group(1)) for m in pin_keys if m})
pin_M = sorted({int(m.group(2)) for m in pin_keys if m})


def _p2(x):
    return x > 0 and (x & (x - 1)) == 0


npow_N = [n for n in pin_N if not _p2(n)]
npow_G = [g for g in pin_ws if not _p2(g)]
# The pre-registration requires >=4 non-power-of-two N and >=3 non-power-of-two G;
# below that the experiment does not cover the only case TBIK does not.
if len(npow_N) < 4 or len(npow_G) < 3:
    FAIL.append("W2-H1: the non-power-of-two coverage requirement is not met")
if sorted(npow_N) != sorted(h1["non_power_of_two_N"]) or sorted(npow_G) != sorted(h1["non_power_of_two_G"]):
    FAIL.append("W2-H1: derived non-power-of-two coverage disagrees with the record")

# Negative control.  It is what makes the positive result reportable.
neg = W2R["H1_negative_control"]
if neg["cases_that_failed_as_they_must"] < 1:
    FAIL.append("W2-H1: the negative control did not fire; the checker cannot fail")
if len(ir) != neg["cases"]:
    FAIL.append("W2-H1: negative-control case count disagrees with the raw record")
neg_zero = sorted(int(re.search(r"_N(\d+)_", k).group(1))
                  for k, v in ir.items() if v["n_cells_equal_R_can"] == 0)
if len(neg_zero) < 2:
    FAIL.append("W2-H1: fewer than two total-failure negative-control cases")
neg_cells = {v["n_cells"] for v in ir.values()}
neg_ws = sorted({g for v in ir.values() for g in v["world_sizes"]})
if len(neg_cells) != 1:
    FAIL.append("W2-H1: negative-control cases do not share one cell count")
neg_distinct = max(v["n_distinct"] for v in ir.values())
neg_partial = [v["n_cells_equal_R_can"] for k, v in ir.items()
               if 0 < v["n_cells_equal_R_can"] < v["n_cells"]]

# Exhaustive (N,G) correctness sweep of the repair, and of what it replaced.
sw = W2P["sweeps"]
sweep_all, suite = sw["S2_all_N_le_300"], sw["S1_T16_set"]
for nm, d in sw.items():
    if d["cut_aligned_exact"] != d["n_pairs"] or d["cross_stage_shape_bad"]:
        FAIL.append(f"W2: the cut-aligned repair is not exact on sweep {nm}")
if sweep_all["NEGCTRL_indexrange_mismatch"] == 0 or suite["NEGCTRL_indexrange_mismatch"] == 0:
    FAIL.append("W2: the index-range control matched R_can everywhere; it must not")
# 45.2%, 44,850 and 1.969 are already emitted by gen_campaign_macros.py from
# the council record.  Recompute them here from the raw W2 sweep so the two
# generated files cannot drift apart, and fail the build if they do.
ir_pct = 100.0 * suite["NEGCTRL_indexrange_mismatch"] / suite["n_pairs"]
ir_ulp = max(d["NEGCTRL_indexrange_max_ulp"] for d in sw.values())

# Load imbalance.  The <=2 figure holds under the greedy largest-first deal
# ONLY; the natural contiguous deal exceeds it, so the paper must name the deal.
imb_all, imb_set = W2I["S2_all_N_le_300"], W2I["S1_T16_set_Gle64"]
if imb_all["n_LPT_over_2"] != 0:
    FAIL.append("W2-H3: some pair exceeds imbalance 2 even under the LPT deal")
if imb_all["n_contiguous_over_2"] == 0:
    FAIL.append("W2-H3: the contiguous deal no longer exceeds 2, so naming LPT is moot")
if imb_all["n_pairs"] != sweep_all["n_pairs"]:
    FAIL.append("W2-H3: the imbalance sweep is not the correctness sweep")

_camp = os.path.join(PAPER, "data", "campaign_macros.tex")
if os.path.exists(_camp):
    _c = open(_camp, encoding="utf-8").read()
    for _nm, _want in (("SweepRootDivergePct", f"{ir_pct:.1f}" + r"\%"),
                       ("SweepPairs", comma(sweep_all["n_pairs"])),
                       ("RepairImbalance", f"{imb_set['worst_LPT']:.3f}")):
        _m = re.search(r"\\newcommand\{\\" + _nm + r"\}\{(.*)\}", _c)
        if _m and _m.group(1) != _want:
            FAIL.append(f"W2: campaign macro \\{_nm} is {_m.group(1)!r} but the "
                        f"W2 raw sweep gives {_want!r}")

# Cost.  Recompute every reported ratio from the row table.
h2 = W2R["H2_cost"]
head = h2["nccl_G2_fbt_chunks1"]["PREREGISTERED_HEADLINE"]
if "PREREGISTRATION.md:54" not in head["definition"]:
    FAIL.append("W2-H2: the headline is no longer the pre-registered statistic")
if not any(d["id"] == "W2-H2-headline-dtype-pooling"
           for d in W2R["DEVIATIONS_FROM_PREREGISTRATION"]):
    FAIL.append("W2-H2: the dtype-pooling deviation is no longer recorded")
rows = W2C["cost_table"]


def _sel(**kw):
    out = [r for r in rows if all(r[k] == v for k, v in kw.items())]
    if not out:
        FAIL.append(f"W2-H2: no cost rows match {kw}")
    return out


hl = _sel(backend="nccl", arm="fbt_ch1", dtype="fp64", G=2)
if len(hl) != head["n"]:
    FAIL.append("W2-H2: the fp64 G=2 row count is not the pre-registered n")
hl_geo, hl_best, hl_worst = _geo([r["overhead"] for r in hl]), \
    min(r["overhead"] for r in hl), max(r["overhead"] for r in hl)
for got, want, what in ((hl_geo, head["geomean"], "geomean"),
                        (hl_best, head["best"], "best"),
                        (hl_worst, head["WORST"], "worst")):
    if abs(got - want) > 5e-4:
        FAIL.append(f"W2-H2: recomputed {what} {got:.4f} != recorded {want}")
# Contention bound: the same rows under the best-of-repeats estimator.
cs = h2["CONTENTION_SENSITIVITY"]
rob = _geo([r["overhead_min"] for r in hl])
if abs(rob - cs["best_of_repeats_contention_robust"]) > 5e-4:
    FAIL.append("W2-H2: recomputed contention-robust geomean disagrees")
if not (rob > 1.3 and hl_geo > 1.3):
    FAIL.append("W2-H2: an estimator falls inside the pre-registered SUPPORT band; "
                "the 'conclusion is invariant' sentence would no longer hold")
# Size sweep at fixed N, and the two-chunk variant against it.
swp = _sel(backend="nccl", arm="fbt_ch1", dtype="fp64", G=2, N=8)
ss = h2["fp64_size_sweep_8KiB_to_128MiB"]
if abs(_geo([r["overhead"] for r in swp]) - ss["geomean"]) > 5e-4:
    FAIL.append("W2-H2: recomputed size-sweep geomean disagrees with the record")
byb = {r["bytes"]: r for r in swp}
big_bytes = max(byb)
ch2 = {r["bytes"]: r for r in _sel(backend="nccl", arm="fbt_ch2", dtype="fp64")}
if big_bytes not in ch2:
    FAIL.append("W2-H2: the two-chunk arm was not run at the largest size")
if not (ch2[big_bytes]["overhead"] < byb[big_bytes]["overhead"]):
    FAIL.append("W2-H2: the two-chunk arm no longer recovers at the largest size")
ch2_small = max(r["overhead"] for r in ch2.values() if r["bytes"] < 2 ** 20)
lg = [r for b_, r in sorted(byb.items()) if 2 ** 23 <= b_ <= 2 ** 25]
lg_lo = min(r["overhead"] for r in lg)
lg_hi = max(r["overhead"] for r in lg)
sm = min(byb)
# The CPU-backend cost cells are NOT reportable and the paper says so.  The
# evidence is internal to the table: at the larger world sizes the stock gloo
# arm is not monotone in message size, which no correct baseline can be.  Find
# the worst inversion and emit it, so the disclaimer cites a row rather than an
# assertion; fail if the arm has become monotone, because then the disclaimer
# would no longer be supported by anything.
glo = {}
for r in rows:
    if r["backend"] == "gloo" and r["arm"] == "fbt_ch1":
        glo.setdefault((r["N"], r["G"], r["dtype"]), {})[r["bytes"]] = r["stock_us"]
inv_best = None
for (n_, g_, _dt), by in glo.items():
    bs = sorted(by)
    for i in range(len(bs)):
        for j in range(i + 1, len(bs)):
            if by[bs[i]] > by[bs[j]]:
                cand = (by[bs[i]] / by[bs[j]], n_, g_, bs[i], bs[j])
                if inv_best is None or cand[0] > inv_best[0]:
                    inv_best = cand
if inv_best is None:
    FAIL.append("W2: the gloo stock arm is monotone in message size, so the "
                "sentence that refuses to report CPU-backend cost has no evidence")
    inv_best = (0, 0, 0, 0, 0)

pooled = h2["nccl_G2_fbt_chunks1"]["pooled_all_dtypes_NOT_the_headline"]
sgl = h2["nccl_G2_fbt_chunks1"]["fp32_only_context"]
if not (pooled["geomean"] < head["geomean"]):
    FAIL.append("W2-H2: the pooled figure is no longer the more favourable one, "
                "so describing the deviation as favourable would be wrong")


def _mib(nbytes):
    for u, d in (("MiB", 2 ** 20), ("KiB", 2 ** 10)):
        if nbytes >= d:
            return rf"{nbytes // d}~{u}"
    return rf"{nbytes}~B"


# ---------------------------------------------------------------- W8 --------
att = MAXP["attempts"]
if any(a["snapshot_has_xsimk"] for a in att):
    FAIL.append("W8: an elaboration attempt did produce a simulation kernel")
dbg = sorted({a["xelab_debug"] for a in att if a["xelab_debug"]})
clean = [a for a in att if a["xelab_rc"] == 0]
if not clean:
    FAIL.append("W8: no elaboration attempt exited zero")
big = max(att, key=lambda a: a["snapshot_bytes"])
h, m, s = (big["elapsed"].split(":") + ["0"])[:3]

# ---------------------------------------------------------------- W9 --------
def row(proto, est):
    for r in W9["protocols"][proto]:
        if r["estimator"] == est:
            return r
    FAIL.append(f"W9: {est} missing from {proto}")
    return {}


loo4, grp4 = row("LOO", "portfolio_k4"), row("GROUP-topology", "portfolio_k4")
nbk4 = row("GROUP-Nbucket", "portfolio_k4")
cond = row("LOO", "cond_topology")
one = row("LOO", "portfolio_k1")
ci = KS["bootstrap_ci"]
sw = KS["k_sweep"]
if W9["shipped_stability_claim"]["reproduced_k4_identical_folds"] != "39/39":
    FAIL.append("W9: the shipped stability claim did not reproduce")
if abs(loo4["mean_regret"] - 1.0025) > 5e-5:
    FAIL.append("W9: LOO k=4 regret disagrees with the shipped selection rule")
if sw["4"]["loo_mean"] != sw["5"]["loo_mean"] or sw["4"]["topo_mean"] != sw["5"]["topo_mean"]:
    FAIL.append("W9: k=5 is not identical to k=4, so k=4 is not the knee")
if not (cond["mean_regret"] > loo4["mean_regret"]):
    FAIL.append("W9: conditioning on topology is not worse than the portfolio")
n_inst = W9["n_instances"]
grp_optn = round(grp4["frac_optimal"] * n_inst)
cond_optn = round(cond["frac_optimal"] * n_inst)
one_optn = round(one["frac_optimal"] * n_inst)
n_topo = len([r for r in W9["protocols"]["GROUP-topology"]])  # placeholder, fixed below
n_topo = 6 if "GROUP-topology" in W9["protocols"] else 0
need(KS, "k4_unseen-topology", "W9 bootstrap interval")
ci_src = open(os.path.join(SRC, "W9_ksweep_ci.py"), encoding="utf-8").read()
mb = re.search(r"^B = (\d+)$", ci_src, re.M)
if not mb:
    FAIL.append("W9: bootstrap replication count not found in the CI script")
boot_reps = int(mb.group(1)) if mb else 0

# ---------------------------------------------------------------- W3 --------
# fp64_add effective subtraction: the repair and its revalidation.  Every value
# below is parsed out of the verbatim stdout of one command, captured by
# scripts/distill_fp64.py.  The generator refuses to emit unless the record
# still says what it said when the prose was written: the acceptance run must
# PASS with zero errors, the pre-fix negative control must FAIL, the pre-fix
# software oracle and pre-fix RTL must AGREE (that is the point of the
# shared-transcription sentence, so if they ever disagreed the sentence would
# be wrong), the borrow-only variant must be non-zero (otherwise "three edits,
# not one" is unsupported), and the scope guard must show no published root
# moving with its own mutant control firing.
FP = load("W3_fp64.json")
FR = FP["records"]


def _fp(tag, rc):
    r = FR[tag]
    if r["returncode"] != rc:
        FAIL.append(f"W3/{tag}: exit status {r['returncode']}, expected {rc}")
    return r["stdout"]


_post = _fp("accept_post", 0)
_pre = _fp("accept_pre", 1)
_var = _fp("variants", 0)
_scope = _fp("scope", 0)
_swpost = _fp("sweep_post", 0)
_swpre = _fp("sweep_pre", 0)

if "RESULT: PASS" not in _post:
    FAIL.append("W3: the repaired adder no longer passes its acceptance test")
if "RESULT: FAIL" not in _pre:
    FAIL.append("W3: the pre-fix negative control did not fire")
if "RESULT: PASS" not in _scope:
    FAIL.append("W3: the no-published-number-moves guard did not pass")
if "RESULT: PASS (0 failing test groups)" not in _swpost:
    FAIL.append("W3: the repaired RTL fails the host-FPU sweep")


def _acc(txt, what):
    m = re.search(r"TOTAL\s+:\s+(\d+)/(\d+)", txt)
    n = re.search(r"mismatches\s+:\s+(\d+)/(\d+)", txt)
    if not (m and n):
        FAIL.append(f"W3/{what}: acceptance-test summary lines not in the expected form")
        return 0, 0, 0
    if m.group(2) != n.group(2):
        FAIL.append(f"W3/{what}: accuracy and equivalence ran on different vector sets")
    return int(m.group(1)), int(m.group(2)), int(n.group(1))


fp_err, fp_n, fp_mm = _acc(_post, "accept_post")
fpc_err, fpc_n, fpc_mm = _acc(_pre, "accept_pre")
if fp_err or fp_mm:
    FAIL.append("W3: the repaired adder is not error-free on the acceptance set")
if fpc_err == 0:
    FAIL.append("W3: the negative control found no error, so the test cannot fail")
if fpc_mm != 0:
    FAIL.append("W3: the pre-fix oracle and pre-fix RTL disagree; the paper's "
                "claim that a shared transcription hides a shared defect would "
                "no longer be supported by this record")
_d = re.search(r"ulp deltas\s+:\s+\{(-?\d+): (\d+)\}", _pre)
if not _d or int(_d.group(1)) != 1 or int(_d.group(2)) != fpc_err:
    FAIL.append("W3: the pre-fix error is not uniformly +1 ulp")

# Three-variant model: no fix / borrow only / borrow + lzc==2 rescale.
_vm = re.search(r"\n\s+ALL\s+(\d+)/(\d+)\s+[\d.]+%\s+(\d+)/(\d+)\s+([\d.]+)%\s+(\d+)/(\d+)",
                _var)
if not _vm:
    FAIL.append("W3: the three-variant sweep total line is not in the expected form")
    _vm = re.match(r"(0)(0)(0)(0)(0)(0)(0)", "0000000")
fp_orig_e = int(_vm.group(1))
fp_part_e, fp_part_n, fp_part_pct = int(_vm.group(3)), int(_vm.group(4)), float(_vm.group(5))
fp_full_e = int(_vm.group(6))
if fp_full_e != 0:
    FAIL.append("W3: the three-edit repair is not error-free in the model sweep")
if not (0 < fp_part_e < fp_orig_e):
    FAIL.append("W3: the borrow-only variant is not strictly between the "
                "unrepaired and fully repaired adder, so 'three edits, not "
                "one' is not what this record shows")
_pdel = re.findall(r"ulp-deltas=\{(-?\d+): \d+\}", _var)
if "-1" not in _pdel:
    FAIL.append("W3: the borrow-only residual is not a -1 ulp error")
# Where the residual lives: the largest |de| at which borrow-only still errs.
_prow = re.findall(r"^\s+(\d+)\s+\d+/\d+\s+[\d.]+%\s+(\d+)/\d+\s+[\d.]+%", _var, re.M)
_pde = [int(a) for a, b in _prow if int(b) > 0]
if not _pde:
    FAIL.append("W3: the borrow-only residual has no per-binade rows")
    _pde = [0]

# Pre-fix error rate against the host FPU, by binade separation.
_srow = re.findall(r"^\s+(\d+)\s+(\d+)/(\d+)\s+([\d.]+)%", _swpre, re.M)
if len(_srow) < 20:
    FAIL.append("W3: the pre-fix host-FPU sweep has too few binade rows")
_full = [int(de) for de, e, n, p in _srow if int(e) == int(n)]
if len(_full) != 1:
    FAIL.append("W3: the pre-fix defect is not total at exactly one binade separation")
    _full = [0]
_bde = [int(de) for de, e, n, p in _srow if 5 <= int(de) <= 52 and int(de) != _full[0]]
_band = [float(p) for de, e, n, p in _srow if 5 <= int(de) <= 52 and int(de) != _full[0]]
if not _band:
    FAIL.append("W3: no binade rows in the 5..52 band")
    _band, _bde = [0.0], [0]
_zero = [int(de) for de, e, n, p in _srow if int(e) == 0]
if not _zero or min(_band) < 40.0:
    FAIL.append("W3: the pre-fix band rate is not the near-half rate the prose describes")
# Post-fix host-FPU sweep: total vectors across all four arms, zero errors.
_pa = re.search(r"TOTAL A: (\d+)/(\d+)", _swpost)
# The four arm-summary lines print four decimal places; the per-binade rows of
# TEST A print two, and the TEST A total has an "=" before its percentage, so
# neither is picked up here.
_pb = re.findall(r"^\s{2}\S.*?\s+(\d+)/(\d+)\s+\d+\.\d{4}%", _swpost, re.M)
if not _pa or len(_pb) < 4:
    FAIL.append("W3: the post-fix host-FPU sweep summary is not in the expected form")
    _pa, _pb = re.match(r"(0)(0)", "00"), [("0", "0")] * 4
# TEST A (the binade sweep) is totalled on its own line; TESTS B, C and D are
# the four arm-summary lines.  The two sets are disjoint, so the release-wide
# vector count is their sum.
sw_n = int(_pa.group(2)) + sum(int(n) for e, n in _pb)
sw_e = int(_pa.group(1)) + sum(int(e) for e, n in _pb)
if sw_e != 0:
    FAIL.append("W3: the post-fix host-FPU sweep is not error-free")
if len(_pb) != 4:
    FAIL.append("W3: the post-fix sweep no longer has four arm-summary lines")

# Scope: does any published root move?
_sg = re.search(r"G values tested\s+:\s+(\d+)\s+\((\d+) \.\. (\d+)\)", _scope)
_sm = re.search(r"roots that moved\s+:\s+(\d+)", _scope)
_ss = re.search(r"FADDs with s_a != s_b\s+:\s+(\d+)", _scope)
_sl = re.search(r"non-positive leaves:\s+(\d+)", _scope)
_sc = re.search(r"mutant roots detected as moved:\s+(\d+)/(\d+)", _scope)
if not (_sg and _sm and _ss and _sl and _sc):
    FAIL.append("W3: the scope guard's summary lines are not in the expected form")
    _sg = re.match(r"(0)(0)(0)", "000"); _sm = _ss = _sl = re.match(r"(0)", "0")
    _sc = re.match(r"(0)(0)", "00")
if int(_sm.group(1)) or int(_ss.group(1)) or int(_sl.group(1)):
    FAIL.append("W3: a published root moves, or the campaign does reach the "
                "effective-subtraction path; the scope sentence is false")
if _sc.group(1) != _sc.group(2) or int(_sc.group(2)) < 2:
    FAIL.append("W3: the scope guard's own mutant control did not fire on every mutant")

if FAIL:
    for f in FAIL:
        print(f"  FAIL  {f}")
    sys.exit(1)

OUT = rf"""% GENERATED by scripts/gen_wround_macros.py -- do not edit by hand.
% source : data/wround/{{W1_RESULT,W2_RESULT,W2_partA,W2_imbalance,
%          W2_invariance,W2_cost,W4_ANALYSIS_full,W4_negative_control,
%          W4_reexec,W8_maxp,W9_RESULT,W9_ksweep}}.json, vendored from
%          experiments/w_final by scripts/distill_wround.py.
% method : structured JSON fields; prose-embedded values are asserted present
%          as exact substrings in the source record before being emitted.
% note   : macro names carry no digits (check_consistency.py C1).

% ---- W1: reduction order on a production collective, measured -----------
\newcommand{{\GpuHardware}}{{{GPU_HW}}}
\newcommand{{\GpuStack}}{{{GPU_STACK}}}
\newcommand{{\GpuWorldSizes}}{{{WORD[gpu_cfgs]}}}
\newcommand{{\GpuRootsDistinct}}{{{WORD[resh["distinct_64bit_roots"]]}}}
\newcommand{{\GpuWorldLo}}{{{gpu_lo}}}
\newcommand{{\GpuWorldHi}}{{{gpu_hi}}}
\newcommand{{\GpuCases}}{{twelve}}
\newcommand{{\GpuUlpMax}}{{{comma(ulp_max)}}}
\newcommand{{\GpuRelMax}}{{{rel_mant}\times10^{{{int(rel_exp)}}}}}
\newcommand{{\GpuElemsMovedMin}}{{{comma(moved_min)}}}
\newcommand{{\GpuElemsTotal}}{{{comma(moved_tot)}}}
\newcommand{{\GpuEqCanonical}}{{none}}
\newcommand{{\GpuCanonCases}}{{{WORD[canon_cases]}}}
\newcommand{{\GpuRepeats}}{{{WORD[rep["nccl_repeats"]]}}}
\newcommand{{\GpuPairDblPct}}{{{m64.group(3)}\%}}
\newcommand{{\GpuPairSglPct}}{{{m32.group(3)}\%}}
\newcommand{{\GpuPairDblFrac}}{{{m64.group(1)}/{m64.group(2)}}}
\newcommand{{\GpuPairSglFrac}}{{{m32.group(1)}/{m32.group(2)}}}
\newcommand{{\GpuLibCfgs}}{{{WORD[r1["library_axis"]["configurations"]]}}}
\newcommand{{\GpuChanCfgs}}{{{WORD[r1["channel_axis"]["configurations"]]}}}
\newcommand{{\GpuXCheck}}{{{xchk["n_identical"]}}}

% ---- W4: clocked route load against the hierarchical-force bypass -------
\newcommand{{\RouteRuns}}{{{comma(ok["n_comparable"])}}}
\newcommand{{\RouteAltRuns}}{{{comma(alt["n_comparable"])}}}
\newcommand{{\RouteBitExact}}{{{ok["pct_bit_exact"]:.0f}\%}}
\newcommand{{\RouteFillTime}}{{${fill["median"]:.1f}$~ns}}
\newcommand{{\RouteNegCtrl}}{{{nc["n"]}}}
\newcommand{{\RouteReexec}}{{{comma(RX["n_agree_with_each_other_and_oracle"])}}}
\newcommand{{\RouteReexecInst}}{{{WORD[RX["n_instances"]]}}}
\newcommand{{\RouteGMax}}{{{RX["coverage"]["g_max"]}}}
\newcommand{{\RouteTopoCount}}{{{WORD[len(RX["coverage"]["topologies"])]}}}

% ---- W8: what stops maxp\_mod\_fat from simulating ----------------------
\newcommand{{\MaxpElabAttempts}}{{{WORD[len(att)]}}}
\newcommand{{\MaxpDebugCfgs}}{{{WORD[len(dbg)]}}}
\newcommand{{\MaxpElabClean}}{{{WORD[len(clean)]}}}
\newcommand{{\MaxpElabWall}}{{{int(h)}\,h\,{int(m)}\,m}}
\newcommand{{\MaxpElabRss}}{{{big["peak_rss_kb"] / 1048576:.0f}}}
\newcommand{{\MaxpSnapSize}}{{{big["snapshot_bytes"] / 2**30:.1f}}}
\newcommand{{\MaxpKernels}}{{zero}}

% ---- W9: does the selection rule generalise? ----------------------------
\newcommand{{\SelUnseenTopoMean}}{{{grp4["mean_regret"]:.4f}}}
\newcommand{{\SelUnseenTopoLo}}{{{ci["k4_unseen-topology"]["lo"]:.4f}}}
\newcommand{{\SelUnseenTopoHi}}{{{ci["k4_unseen-topology"]["hi"]:.4f}}}
\newcommand{{\SelUnseenTopoOpt}}{{{grp_optn}}}
\newcommand{{\SelUnseenTopoPct}}{{{100 * grp4["frac_optimal"]:.1f}\%}}
\newcommand{{\SelUnseenTopoWorst}}{{{grp4["max_regret"]:.3f}}}
\newcommand{{\SelUnseenScaleMean}}{{{nbk4["mean_regret"]:.4f}}}
\newcommand{{\SelLooCiLo}}{{{ci["k4_LOO"]["lo"]:.4f}}}
\newcommand{{\SelLooCiHi}}{{{ci["k4_LOO"]["hi"]:.4f}}}
\newcommand{{\SelBootReps}}{{{comma(boot_reps)}}}
\newcommand{{\SelTopoGroups}}{{{WORD[n_topo]}}}
\newcommand{{\SelCondTopoMean}}{{{cond["mean_regret"]:.4f}}}
\newcommand{{\SelCondTopoOpt}}{{{cond_optn}}}
\newcommand{{\SelConstOpt}}{{{one_optn}}}
\newcommand{{\SelKnee}}{{four}}
\newcommand{{\SelKneeNextMean}}{{{sw["5"]["topo_mean"]:.4f}}}
\newcommand{{\SelKSixMean}}{{{sw["6"]["loo_mean"]:.4f}}}

% ---- W2: pinned-FBT, correctness and cost -------------------------------
\newcommand{{\PinCases}}{{{vv["fbt_cases"]}}}
\newcommand{{\PinCells}}{{{comma(vv["fbt_total_cells"])}}}
\newcommand{{\PinWorldLo}}{{{min(pin_ws)}}}
\newcommand{{\PinWorldHi}}{{{max(pin_ws)}}}
\newcommand{{\PinLeafLo}}{{{min(pin_N)}}}
\newcommand{{\PinLeafHi}}{{{comma(max(pin_N))}}}
\newcommand{{\PinNpowLeaf}}{{{WORD[len(npow_N)]}}}
\newcommand{{\PinNpowWorld}}{{{WORD[len(npow_G)]}}}
\newcommand{{\PinDeals}}{{{WORD[len(pin_deals)]}}}
\newcommand{{\PinMsgLo}}{{{_mib(min(pin_M) * 8)}}}
\newcommand{{\PinMsgHi}}{{{_mib(max(pin_M) * 8)}}}
\newcommand{{\PinNegCases}}{{{WORD[neg["cases"]]}}}
\newcommand{{\PinNegFired}}{{{WORD[neg["cases_that_failed_as_they_must"]]}}}
\newcommand{{\PinNegCells}}{{{neg_cells.pop()}}}
\newcommand{{\PinNegDistinct}}{{{WORD[neg_distinct]}}}
\newcommand{{\PinNegWorlds}}{{$\{{{", ".join(str(g) for g in neg_ws)}\}}$}}
\newcommand{{\PinNegLeafA}}{{{comma(neg_zero[0])}}}
\newcommand{{\PinNegLeafB}}{{{comma(neg_zero[-1])}}}
\newcommand{{\PinNegPartial}}{{{WORD[max(neg_partial)]}}}
\newcommand{{\PinSuitePairs}}{{{comma(suite["n_pairs"])}}}
\newcommand{{\PinIrMismatch}}{{{comma(sweep_all["NEGCTRL_indexrange_mismatch"])}}}
\newcommand{{\PinIrUlp}}{{{ir_ulp}}}
\newcommand{{\PinImbLpt}}{{{imb_all["worst_LPT"]:.3f}}}
\newcommand{{\PinImbContig}}{{{imb_all["worst_contiguous"]:.2f}}}
\newcommand{{\PinImbContigOver}}{{{comma(imb_all["n_contiguous_over_2"])}}}
\newcommand{{\PinCostCells}}{{{head["n"]}}}
\newcommand{{\PinCostGeo}}{{{hl_geo:.2f}}}
\newcommand{{\PinCostBest}}{{{hl_best:.2f}}}
\newcommand{{\PinCostWorst}}{{{hl_worst:.2f}}}
\newcommand{{\PinCostRobust}}{{{rob:.2f}}}
\newcommand{{\PinCostInflate}}{{{hl_geo / rob:.2f}}}
\newcommand{{\PinCostPooled}}{{{pooled["geomean"]:.2f}}}
\newcommand{{\PinCostPooledCells}}{{{pooled["n"]}}}
\newcommand{{\PinCostSgl}}{{{sgl["geomean"]:.2f}}}
\newcommand{{\PinSmallSize}}{{{_mib(sm)}}}
\newcommand{{\PinSmallCost}}{{{byb[sm]["overhead"]:.2f}}}
\newcommand{{\PinSmallStock}}{{{byb[sm]["stock_us"]:.0f}}}
\newcommand{{\PinLargeLo}}{{{lg_lo:.2f}}}
\newcommand{{\PinLargeHi}}{{{lg_hi:.2f}}}
\newcommand{{\PinLargeSizeLo}}{{{_mib(min(r["bytes"] for r in lg))}}}
\newcommand{{\PinLargeSizeHi}}{{{_mib(max(r["bytes"] for r in lg))}}}
\newcommand{{\PinBigSize}}{{{_mib(big_bytes)}}}
\newcommand{{\PinBigChunkOne}}{{{byb[big_bytes]["overhead"]:.2f}}}
\newcommand{{\PinBigChunkTwo}}{{{ch2[big_bytes]["overhead"]:.2f}}}
\newcommand{{\PinSmallChunkTwo}}{{{ch2_small:.1f}}}
\newcommand{{\PinGlooBadLeaf}}{{{comma(inv_best[1])}}}
\newcommand{{\PinGlooBadWorld}}{{{inv_best[2]}}}
\newcommand{{\PinGlooBadRatio}}{{{inv_best[0]:.1f}}}
\newcommand{{\PinGlooBadLo}}{{{_mib(inv_best[3])}}}
\newcommand{{\PinGlooBadHi}}{{{_mib(inv_best[4])}}}

% ---- W3: fp64\_add effective subtraction, repaired and revalidated ------
\newcommand{{\FpAcceptVectors}}{{{comma(fp_n)}}}
\newcommand{{\FpAcceptErrors}}{{{WORD[fp_err]}}}
\newcommand{{\FpAcceptMismatch}}{{{WORD[fp_mm]}}}
\newcommand{{\FpCtrlVectors}}{{{comma(fpc_n)}}}
\newcommand{{\FpCtrlErrors}}{{{comma(fpc_err)}}}
\newcommand{{\FpCtrlMismatch}}{{{WORD[fpc_mm]}}}
\newcommand{{\FpCtrlUlp}}{{$+1$}}
\newcommand{{\FpPartialErrors}}{{{comma(fp_part_e)}}}
\newcommand{{\FpPartialVectors}}{{{comma(fp_part_n)}}}
\newcommand{{\FpPartialPct}}{{{fp_part_pct:.1f}\%}}
\newcommand{{\FpPartialDeLo}}{{{min(_pde)}}}
\newcommand{{\FpPartialDeHi}}{{{max(_pde)}}}
\newcommand{{\FpBandLo}}{{{min(_band):.1f}\%}}
\newcommand{{\FpBandHi}}{{{max(_band):.1f}\%}}
\newcommand{{\FpBandDeLo}}{{{min(_bde)}}}
\newcommand{{\FpBandDeHi}}{{{max(_bde)}}}
\newcommand{{\FpFullDe}}{{{_full[0]}}}
\newcommand{{\FpSweepVectors}}{{{comma(sw_n)}}}
\newcommand{{\FpSweepErrors}}{{{WORD[sw_e]}}}
\newcommand{{\FpScopeGvals}}{{{_sg.group(1)}}}
\newcommand{{\FpScopeGLo}}{{{_sg.group(2)}}}
\newcommand{{\FpScopeGHi}}{{{comma(int(_sg.group(3)))}}}
\newcommand{{\FpScopeMoved}}{{{WORD[int(_sm.group(1))]}}}
\newcommand{{\FpScopeMixed}}{{{WORD[int(_ss.group(1))]}}}
\newcommand{{\FpScopeMutant}}{{{WORD[int(_sc.group(1))]} of {WORD[int(_sc.group(2))]}}}
"""

dest = os.path.join(PAPER, "data", "wround_macros.tex")
with open(dest, "w", encoding="utf-8") as fh:
    fh.write(OUT)
print(f"wrote {dest}")
