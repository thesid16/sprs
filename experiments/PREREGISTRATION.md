# PREREGISTRATION — final measurement round (W2, W1, W4, W7)

Author: measurement agent (last agent; only role permitted to create new evidence)
Written: 2026-08-27, BEFORE any experiment was executed.
Worktree: /home/rohit/sprs-fix/   Snapshot /home/rohit/sprs-review/snapshot/ is READ-ONLY.
Raw results: /home/rohit/sprs-fix/experiments/w_final/<WID>/vNNN/ — versioned, never overwritten.

Purpose of this document: to fix, in advance, what each outcome means and what the paper
says in each case, so that no experiment can be quietly dropped because its result was
unfavourable. Every hypothesis below has a written REFUTE branch with paper text.

Hardware: 2x NVIDIA RTX PRO 6000 Blackwell (sm_120, driver 580.159.03, PCIe NODE — NO NVLINK
between GPU0 and GPU1), 72 cores, single node. torch not installed at start (cu128 wheel being
installed into /home/rohit/expscratch/venv). This is a SINGLE-NODE system: the word "cluster"
is not licensed by anything measured here, and no result below will be described as one.

---------------------------------------------------------------------------------------
## W2 — repaired (cut-aligned) pinned-FBT vs stock NCCL     [paper \PENDING at main.tex:192, 3031, 3504]

Construction under test (validated by T16_verify.json, 426/426 (N,G) pairs exact): cut
FBT(N) at level d = ceil(log2 G); the 2^d complete subtrees at that level are dealt to the G
ranks; the cross-rank stage evaluates FBT(N)'s top d levels, exactly 2^d - 1 combines at
depth d. NOT the printed step-1 index-range partition, which T16 proved false.

### W2-H1  Bitwise reshape-invariance
Claim: for fixed N and fixed leaf vector L, the 64-bit root produced by pinned-FBT is
identical for every rank count G, every backend (NCCL/gloo), and every NCCL algo x proto,
and equals the single-process canonical reference R_can(N,L).

* SUPPORTS: 100% of (N, G, backend, algo, proto) cells return the same 64-bit pattern, and
  that pattern == R_can(N,L). PAPER SAYS: "the repaired construction is bitwise
  reshape-invariant; measured over <K> configurations spanning <G-list>, including
  non-power-of-two N and non-power-of-two G, every configuration returned an identical
  64-bit root equal to the canonical FBT(N) reduction."
* REFUTES: any cell differs from R_can, even by 1 ulp. PAPER SAYS: the invariance claim
  fails as implemented; we report the exact failing (N,G,backend) set, the ulp magnitude, and
  the root cause. If the cause is that a library call internally re-associates, we say so and
  state that pinned-FBT is only invariant when every stage is point-to-point. We do NOT
  report a repaired subset as if it were the whole claim.
* PARTIAL (anticipated, pre-planned): invariance holds under p2p-only implementation but
  fails if any stage delegates to library allreduce. PAPER SAYS both halves explicitly.
* NEGATIVE CONTROL (mandatory): a deliberately mis-cut variant (level d-1, or the paper's
  original index-range step 1) MUST produce a root that differs from R_can on at least one
  swept (N,G). If the mis-cut control also passes, the checker cannot fail and no positive
  result from it may be reported.

### W2-H2  Cost vs stock NCCL all-reduce
Claim: the invariance is affordable. TBIK's comparable published figure is <=10% for its
tree all-reduce (Appendix H.1, 4xH20/NVLink, TP=4).

* Pre-specified reported statistics (fixed now, so they cannot be chosen after seeing data):
  per (N or byte-count, G, dtype) — median-of->=20 timed iterations after >=5 warmups, wall
  time; overhead = pinned-FBT / stock ncclAllReduce. Report the FULL size sweep, plus the
  geometric mean, best case and WORST case. Headline = geomean overhead at G=2, fp64, over
  the swept sizes, WITH the worst case printed alongside it in the same sentence.
* SUPPORTS: geomean overhead within roughly 1x-1.3x, i.e. same order as TBIK's <=10%.
  PAPER SAYS: the discipline costs <X>% on commodity GPUs, corroborating that reproducibility
  is a priced-but-payable structural cost.
* REFUTES / UNFAVOURABLE: overhead is large (>2x), especially at large messages. This is a
  LISTED IRREDUCIBLE RISK and it will be reported, not suppressed. PAPER SAYS: "the repaired
  construction is bitwise invariant but costs <X>x-<Y>x stock NCCL, degrading with message
  size because the cross-rank stage is a depth-d tree of 2^d-1 latency-bound combines with no
  bandwidth-optimal ring; on this 2-GPU PCIe node it is <...>. We report this as measured; it
  is the price of the discipline and it is not competitive with a bandwidth-optimal ring at
  large message sizes." No selective size range will be quoted as the headline.
* NOTE ON SCOPE, fixed in advance: 2 GPUs and no NVLink means the NCCL arm is G=2 only and
  PCIe-bound; larger G is measured on gloo/TCP CPU ranks. Any number is labelled with its
  backend. We will not extrapolate to multi-GPU NVLink.

### W2-H3  Load imbalance
Claim (T16): max_rank_leaves / (N/G) <= 2, worst observed 1.969.
* SUPPORTS: all swept (N,G) satisfy <= 2. PAPER SAYS: bound confirmed, worst observed <v>.
* REFUTES: any pair exceeds 2. PAPER SAYS: the bound is wrong; report the counterexample
  and the true observed maximum. (This would contradict T16 and would be reported as such,
  not smoothed over.)

### W2 coverage requirement
Non-power-of-two N is the part TBIK does not cover and therefore the only genuinely new part.
MUST include >=4 non-power-of-two N and >=3 non-power-of-two G. If only power-of-two cases
are measured, the experiment does not discharge the PENDING and will be reported as not done.

---------------------------------------------------------------------------------------
## W1 — does reduction order actually diverge on real hardware?   [\PENDING main.tex:2636]

The paper's motivating premise: rerunning the same deterministic reduction under a different
rank count / algorithm yields a bit-different result.

* SUPPORTS: >1 distinct 64-bit root over the sweep {backend} x {NCCL_ALGO} x {NCCL_PROTO} x
  {world size G} x {dtype}, on IDENTICAL input bytes. PAPER SAYS: "we measured it: over <K>
  configurations of a production collective on identical inputs we observed <D> distinct
  64-bit results, max spread <U> ulp; <F>% of configuration pairs disagree." One figure.
* REFUTES: exactly ONE distinct root across the entire sweep — stock NCCL/gloo is already
  bitwise invariant here. PAPER SAYS, verbatim in spirit: "On our single-node 2-GPU system we
  did NOT reproduce divergence: all <K> configurations returned an identical root. The
  motivating premise is therefore supported here only by the cited literature and by
  <whatever subset did diverge>, not by our own hardware measurement at this scale." We will
  NOT claim divergence we did not observe, and we will not enlarge the sweep post hoc to hunt
  for a positive; any additional sweep run after seeing a null is reported AS post hoc.
* PARTIAL (anticipated): divergence appears when the rank count changes (different tree
  shape / different partitioning) and/or between Tree and Ring, but not between repeated runs
  of the same configuration. PAPER SAYS exactly that decomposition: run-to-run determinism at
  fixed configuration, divergence across reshape. That distinction is itself the paper's
  point and will be reported explicitly either way.
* Also recorded: run-to-run repeatability at fixed configuration (>=5 repeats) — needed to
  distinguish "reshape moves the answer" from "the hardware is just noisy".

---------------------------------------------------------------------------------------
## W4 — clocked route-load calibration                          [\PENDING main.tex:2636]

Every RTL result in the artifact was produced with the route-table bypass (hierarchical
force of u_sys.gen_rtr[r].u_rtr.route_table[d], src/sprs_core.py ~:5610) instead of the
clocked write_route task emitted at ~:5546 and never called. L0b's fidelity figures (59%
bit-exact, 1-54% lower) have no run behind them anywhere in the artifact.

* SUPPORTS L0b: clocked runs reproduce the bypass runs' PASS status and 64-bit roots, and
  the cycle counts differ within the band L0b asserts. PAPER SAYS: L0b's figures are now
  measured, on <n> runs, and stand.
* REFUTES L0b (anticipated, per T11: no mechanism found that would produce that band): the
  measured delta is NOT 59%/1-54%. PAPER SAYS: "we ran the clocked route-load path on <n>
  runs; the measured effect is <X> (e.g. bit-exact on 100%, cycle count higher by <c> cycles
  = route-load fill time only). L0b's previously stated 59% / 1-54% band is replaced by this
  measurement." The old band is deleted, not defended.
* HARD-STOP CASE: if clocked runs disagree with bypass runs on the 64-bit ROOT or flip
  PASS->FAIL, then published fabric numbers depend on the bypass. Under rule 4 I STOP,
  change nothing, and report it as a finding that affects 2,822 results.
* NEGATIVE CONTROL (mandatory): inject one wrong route-table entry into the clocked path and
  confirm the testbench reports FAIL/timeout rather than PASS. If a corrupted route table
  still PASSes, the clocked path is not actually exercising routing and no fidelity claim may
  be drawn from it.
* Doubles as the regression test for the prior fixers' fp64_add repair: any root change
  attributable to fp64_add is reported separately from any change attributable to routing.

---------------------------------------------------------------------------------------
## W7 — measured eta                                            [\PENDING main.tex:2636]

T10 proved eta = 1 by construction on 31/39 instances.
* SUPPORTS: measured eta == 1.00 on the instances where T10 proves it must be, and eta > 1
  only where the champion does not cut at exactly G-1 cross-PE edges. PAPER SAYS: eta is
  measured, not argued; value per instance.
* REFUTES: eta != 1 somewhere T10 proves it must be 1. PAPER SAYS: the harness or the proof
  is wrong; I report WHICH, and do not report a number I cannot explain.
* REFUTES (other direction): eta >> 1 on the ring/torus instances beyond the 1.07-1.95x
  band anticipated. PAPER SAYS the measured value, whatever it is.

---------------------------------------------------------------------------------------
## Discipline

1. Priority if budget runs short: W2 >> W1 > W4 > W7. Anything not reached is named
   explicitly in the final report as NOT REACHED, with the reason. Nothing is silently dropped.
2. Every raw result versioned under experiments/w_final/<WID>/vNNN/. No overwrite, ever.
   Failed and aborted runs are kept too, with their logs.
3. Negative controls are mandatory wherever something is being checked (W2-H1, W4). A check
   that cannot fail produces no reportable positive.
4. No published number is changed. If a measurement implies a published number is wrong, I
   STOP and report it (rule 4) rather than editing it.
5. Not run, by council decision: synthesis/PPA, multi-node, tournament tie-break, full
   campaign re-run.
