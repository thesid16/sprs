# paper_v6 — Plan and Gap Decisions

**Date:** 2026-07-27
**Base:** `main (1).tex` (v5, 138 KB, IEEE TPDS, 126 `\todo{}` placeholders)
**Guide:** `hidden_work_inventory.md` §10 (integration priorities) and §11 (structure)
**Constraint from the author:** *the experiments are final — finish the paper with what exists.*

---

## 1. The governing decision

The v5 draft was written ahead of the experiments and its numbers are **placeholders, not
measurements**. Several are demonstrably invented — all eight invariance root values, the
`1.12×` overhead, the four FPGA cycle counts. v6 replaces every one of them with a measured
value, or removes the claim.

Nothing gets published that we cannot trace to a CSV, a log, or a stated structural argument.

---

## 2. Gap-by-gap resolution

### 2.1 Bitwise invariance — **CLOSED, and stronger than v5 claims**

Verified 2026-07-27 across all 5,833 emitted testbenches: every leaf count `N` has **exactly one**
expected root, and 2,822 of those testbenches passed in RTL, so the fabric reproduced it bit-exactly.

| N | reshape span | distinct roots | root |
|---|---|---|---|
| 8 | G=2 linear, G=4 ring | 1 | `0x40E1948E978D4FDF` |
| 32 | 3 configs | 1 | `0x41201D1FCED91687` |
| 128 | G=4 linear → G=128 torus, 5 topologies | 1 | `0x415F7E8FF9581062` |
| 512 | 6 configs | 1 | `0x419F4FA404418938` |
| 1024 | 5 configs | 1 | `0x41BF47D2026872B1` |
| 2048 | 4 configs | 1 | `0x41DF43E900FBE76D` |
| 4096 | 3 configs | 1 | `0x41FF41F48085A1CB` |
| 8192 | 3 configs (2 HW-validated) | 1 | `0x421F40FA40427EFA` |

Cross-check against `_analysis/paper_analysis.py::canonical_root_hex()` before publishing.
Per inventory §7.5, v5 **underreports** this — it is the strongest evidence for Claim 1 and
should be stated as such.

### 2.2 Same-fabric overhead (`1.12×`) — **CLAIM REMOVED, replaced structurally**

No non-deterministic baseline reducer exists in any code on this machine. The number was never
measured. It appears in the abstract, §results-overhead, §results-decomp, the discussion, the
conclusion, and the appendix per-instance table — **all must change.**

Replacement is already written: `hidden_work_inventory.md` §8, *"Cost of Determinism — Why It's
Structural (Not Empirical)"*:

1. **§8.1** FBT mandates depth `log₂N`; an unconstrained reducer could use `log_G N`.
2. **§8.2** Operand binding forbids locality-driven reassociation.
3. **§8.3** GCI serialization `gci_gap = 6` cycles → **predicted inflection at N/G ≈ 6–8**.
4. **§8.4** Root-gather needs `⌈log₂K⌉` merges + one `comm_cost(⌈diameter/2⌉)` — irreducible.
5. **§8.5** Bisection traffic `⌈(K−1)/2⌉` messages is tree-order-fixed.

Quantitative anchors we genuinely have: **measured ratio-to-Ω, best-per-instance 1.23–2.94×**,
and the **N/G ≈ 6–8 inflection, which is testable against the existing dataset**. Testing a
prediction the structural model makes is worth more than an unbacked ratio.

### 2.3 FPGA — **TWO BUILD VARIANTS**

Author states the runs happened; logs are on a collaborator's machine. Manuscript gets a
`\fpgadata` toggle:

- `WITHOUT-LOGS` (**default**) — drop Table `tab:fpga`, soften every FPGA claim to what the
  wrappers demonstrably provide. Always submittable.
- `WITH-LOGS` — table restored, four cycle counts read from a data file, filled if logs arrive.

Both must be internally consistent across abstract, setup, results, limitations, conclusion.

### 2.4 Mutation testing — **BUILD THE HARNESS**

Two mutation classes the paper already names: address-substitution and leaf-corruption. Build the
generator, run a real sample through xsim, report measured detection rates. This is what makes the
oracle demonstrably non-vacuous.

### 2.5 `maxp_mod_fat` — **REPORT 39/40 HONESTLY**

8192L × 4096G fat-tree exceeded the simulation budget (~50–70 GB RAM per elaboration,
est. 3–5 days). State it in Limitations; the N=8192 invariance row rests on 2 HW-validated configs
of 3 compiled.

---

## 3. Factual corrections to §results-setup

| v5 says | Reality |
|---|---|
| xsim 2023.1 Linux + 2025.2 Windows | **xsim 2025.2, Linux** |
| 36-thread Xeon W-2295 | **72-thread Xeon w9-3475X, 503 GB** |
| per-simulation timeout 3600 s | **28,800 s** |
| Nexys4 DDR | RTL headers say **Nexys A7** — confirm the board |
| "≈22,000 configs from 18×10×122" | Phase 1 ran **18×10 = 180/instance at S4=None (7,200 total)**; the 122-config sweep never completed (Phase 2 attempted 21,600, finished 6,203) |

## 4. New disclosure required in Limitations

`CLAUDE.md` documents that the force-bypass transform preserves PASS/FAIL bit-exactly but only
**~59% of cycle counts** are bit-exact (~41% run 1–54% low), with ranking preserved on ~80% of
instances. Harmless for the bitwise claim; **any cycle-derived number inherits it.** Disclose
rather than let a reviewer find it.

---

## 5. Structural rewrite (inventory §11)

- **§3** → assumptions split into **6 compiler obligations** (C-α, C-conn, C-sw, C-bind, C-leaf,
  C-route) and **9 fabric invariants** (F-id, F-sb-mono, F-sb-gate, F-fw, F-fadd, F-credit,
  F-misroute, F-arb, F-watchdog); Claim 1 + **Property 2 (fail-stop)**; orthogonality corollary.
- **§4** → "safe by construction": fail-stop discipline, write-arbitration/retry latches,
  scoreboard as universal presence bit across four write agents.
- **§5** → **S2.5 connectivity repair promoted to its own subsection** (inventory calls it the
  single most load-bearing under-reported piece); DMEM allocation as single-writer constructor;
  algorithm catalogues to Appendix B.
- **§7** → tournament characterisation expanded per §7; new cost-of-determinism subsection per §8.

Only seven invariant violations can produce a **silently wrong** result — C-conn, C-sw, C-bind,
C-leaf, F-sb-gate, F-fw, F-fadd. Everything else reaches fail-stop. That table (inventory §5) is
the backbone of Property 2.

---

## 5a. Data provenance — which CSVs the paper cites

Two HW datasets exist and they are **not** nested:

| dataset | rows | pass | fail | instances |
|---|---|---|---|---|
| `tournament_p1/` (Jul, clean restart) | **2,844** | **2,822** | 22 | 39 |
| `tournament_portable/` (Jun) | 2,792 | 2,771 | 21 | 39 |

185 `(instance, TB)` keys exist only in portable and 237 only in p1. Explanation, verified: `2e`
ExactBB is the single largest portable-only group (42) and appears **zero** times among p1-only
keys — consistent with the July restart reclassifying 2e as `BYPASSED` and baking the force-bypass
into the emitted TBs. The remaining spread is dedup **leader-selection** churn: when the valid set
changes, a different member of each `tb_hash` class becomes the emitted representative, changing
filenames without changing the underlying unique solutions.

**Decision: `tournament_p1/` is authoritative.** It supersedes the June run. Every generated table
and figure reads from it, and the paper states this explicitly. Note the CSV has embedded newlines
in the `Error` column (NOCTRC traces) — all tooling must use a real CSV parser, not line splitting.

**`maxp_mod_fat` evidence for Limitations:** 5 configurations were attempted; all 5 hit
`SIM_WALLCLOCK_TIMEOUT_BYPASS` at the 28,800 s cap, longest 11.8 h, **58.9 core-hours expended
without completing a single run.** That is a concrete, defensible resource statement rather than
a bare admission.

---

## 5b. Cycle-metric defect and re-measurement (2026-07-27)

`_bypass_runner.py` recorded **GPU 0's** `perf_total` as `Cycles`, because it used
`re.search()` (first match) over a testbench that prints every PE's counter in a loop. When the
reduction root lands on a PE other than 0 — routine on rings and tori — GPU 0 idles early and its
counter understates end-to-end latency.

Detection: Ω is a proven lower bound on makespan, so any row with `Cycles < Ω` cannot be a
makespan. **140/2,822 rows (5.0%)** failed that test, worst `large_dense_2d/tb_2c_3i_none` at
5 cycles against Ω=192.

**The Ω test badly understates the problem.** Re-measurement shows **54.2% of rows change**
(52 of the first 96), e.g. `large_bal_mesh/tb_2b_3e_none` 64 → **159** (2.5×) with `CyclesGPU0=64`
confirming the cause. Most understated values were still above Ω and therefore undetectable by the
bound test. Per-instance champions move materially: `large_bal_fat` was reported at 64, true value
**153**.

Fix: take `max` over all PEs, and persist the full per-PE vector (`PerfAllGPUs`) so load imbalance
is recoverable without re-simulating. Re-run is supervised by `rerun_watchdog.sh` (setsid-detached,
crash-restarting, checkpointed via the output CSV's settled-row scan), writing to
`live_hw_results_p1_maxpe.csv`. The original CSV is never modified.

**Scope of impact:** Claim 1 is untouched — it rests on `Pass`, the bit-exact root comparison, and
all 2,822 witnesses stand. Every cycle-derived number must come from the re-measured CSV.

### Outcome (2026-07-31, campaign complete)

821.5 core-hours, 142 h wall-clock, **2,822 passing across 39 instances — identical coverage to the
original**, so nothing was lost by re-measuring. The correction was far larger than the Ω test
could detect:

| | |
|---|---|
| testbenches whose cycle count changed | **1,424 / 2,822 (50.5%)** |
| median understatement | **1.28×** |
| worst understatement | **148.4×** |
| **per-instance champions that changed** | **35 / 39 (90%)** |

The algorithm-family conclusion *reversed*: on the defective metric graph partitioning won 77% of
instances; on the corrected metric **tree DP wins 54%** and graph partitioning drops to 18%. Had we
published the original numbers, the tournament characterisation would have been almost entirely
wrong — and nothing in the invariance result would have flagged it, because that result never
depended on cycles.

**The structural cost model's prediction was confirmed.** §8.3 predicted GCI serialisation binds
only while N/G ≲ 6–8. Measured, banded by N/G: 4.16 → 3.96 → **3.28 → 1.91** → 1.37 (× Ω). The
sharpest transition in the table is exactly at the predicted band, and the knee location was fixed
in advance by the hardware constant `gci_gap = 6`, not fitted. Topology ordering also tracks
bisection width as §8.5 implies: linear 1.39× best, ring 4.48× worst.

This is a materially better outcome than the fabricated `1.12×` would have been: a confirmed
prediction from a stated model, rather than an unbacked ratio.

---

## 6. Verified numbers available today

40 instances · 7,200 compilations · 6,785 valid (94.2%) · failures 390 size-gated / 278 IMEM
overflow / 33 timeout · dedup **6,785 → 2,920 TBs → 622 assignments** · **2,842 HW rows, 2,822
pass** across 39 instances · **351.9 core-hours**, median 46 s, max 7.06 h · best-per-instance
ratio-to-Ω **1.23–2.94×** · RTL 13 files / 3,726 lines.

---

## 7. Order of work

1. This doc → agreed
2. paper_v6 tree + build + `\todo` counter
3. Table/figure generators from CSVs (numbers before prose)
4. Invariance table (§2.1) — the easy, high-value win
5. Cost-of-determinism rewrite (§2.2) — the biggest change
6. Structural rewrite (§5)
7. Mutation harness (§2.4) → fills the last table columns
8. Setup corrections + limitations (§3, §4)
9. FPGA variants (§2.3)
10. Verification pass — `\todo` count to zero
