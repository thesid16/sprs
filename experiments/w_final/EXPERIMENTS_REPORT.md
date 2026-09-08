# EXPERIMENTS_REPORT — final measurement round (W1, W2, W4, W7)

Author: measurement agent (the only role permitted to create new evidence).
Date: 2026-08-28. Worktree `/home/rohit/sprs-fix/` — the frozen snapshot at
`/home/rohit/sprs-review/snapshot/` was read but never written.
Pre-registration (written before any experiment ran): `/home/rohit/sprs-fix/experiments/PREREGISTRATION.md`.

Every outcome below is stated against the SUPPORT / REFUTE / PARTIAL branch that the
pre-registration committed to in advance, in the words it committed to. Two work items
produced results that are unfavourable to the paper as currently written (W2-H2 and, far
more seriously, the W4 by-product in §5). Both are reported here as the primary finding of
their section, not as a footnote.

Hardware for all of it: single node, 2x NVIDIA RTX PRO 6000 Blackwell Server Edition,
PCIe (`nvidia-smi topo` = NODE), **no NVLink**; 72 CPU cores; torch 2.11.0+cu128;
Vivado/xsim 2025.2. This is a single node. The word "cluster" is not licensed by anything
measured here and no number below should be described as one.

---

## 0. One-paragraph summary for the paper writers

The paper's motivating premise is confirmed on real hardware and the effect is large (W1).
The repaired pinned-FBT construction is bitwise reshape-invariant across every configuration
measured, including the non-power-of-two shapes TBIK does not cover (W2-H1), and the load
bound holds provided the paper specifies LPT (W2-H3). It costs 1.5x-3.9x stock NCCL on this
PCIe node, which is an unfavourable result and is reported as one (W2-H2). Limitation L0b's
fidelity band does not exist: the clocked route-load path is bit-exact and cycle-exact with
the bypass on all 1,326 runs (W4). eta is exactly 1 on all 1,374 power-of-two pipeline
comparisons — a tautology check that nevertheless validates T10's proof through the real
toolchain — and is measured at geomean 1.15 (range 1.03-1.35) on the non-power-of-two
instances where T10 could not settle it (W7). **Separately and most importantly, W4 turned up
a defect in the published cycle data that the paper must disclose: see §5.**

---

## 1. W1 — does reduction order actually diverge on real hardware?

`\PENDING` at `paper/main.tex:2636`. Result file: `/home/rohit/sprs-fix/experiments/w_final/W1/RESULT.json`.
Raw: `W1/v001` (aborted, kept), `W1/v002` (partial, kept), `W1/v003` (primary).

### Question
The paper's motivating claim is that rerunning the same deterministic reduction under a
different rank count or algorithm yields a bit-different result. Nobody had measured it here.

### Design
Identical input **bytes** at every configuration: leaf *i*'s M-vector is a pure function of
*i*, so nothing about the data changes when the job is reshaped — only who holds which leaf
and in what order the partial sums combine. Four axes swept independently: world size,
NCCL algorithm x protocol, NCCL channel count, and repeated runs at a fixed configuration.
12 (N, dtype, data-profile) cases. Reference: the single-process canonical FBT reduction.

### Result
* **Reshape axis: 14 world sizes {1,2,3,4,5,6,7,8,12,16,24,32,48,64}, 14 DISTINCT 64-bit
  roots**, on identical inputs, in every one of the 12 cases. 14 of 14 distinct.
* Magnitude: max spread 9 ulp (fp64, positive data) up to **5,120 ulp** (fp64 signed data,
  N=1000, M=1024); max relative spread 6.4e-13. 1024 of 1024 elements move.
  **0 of the configurations equalled the canonical FBT reduction.**
* Pairwise: 34 fp64 configurations -> 15 distinct roots, **441/561 = 78.6% of configuration
  pairs disagree**; 21 fp32 configurations -> 15 distinct roots, **189/210 = 90.0% disagree**.
* Repeatability at a FIXED configuration: 5/5 identical under NCCL, 5/5 under gloo.
  All ranks within a run agreed bitwise (0 intra-run disagreements).
* Device axis: at a fixed G=2 partition the CPU and GPU roots also differ, in all 12 cases.
* Library axis (NCCL_ALGO x NCCL_PROTO, 7 configurations) and channel axis (3
  configurations) each gave **one** root.

### Outcome against the pre-registration: **PARTIAL — the branch named in advance**
The pre-registration anticipated exactly this decomposition and required it be reported
either way: *"divergence appears when the rank count changes ... but not between repeated
runs of the same configuration. PAPER SAYS exactly that decomposition: run-to-run determinism
at fixed configuration, divergence across reshape. That distinction is itself the paper's
point."* That is what happened.

The single-root library and channel axes are **not** an empirical null and must not be
reported as a partial refutation. At G=2 the cross-rank reduction is one floating-point
addition per element, which is commutative and exact whatever the schedule; no NCCL algorithm
or protocol can move it on a 2-GPU node. This is structural. It is stated as such and is
**not** generalised to larger G.

### NOT REACHED, named
NCCL with 3 ranks, and with 4 ranks sharing 2 GPUs, were attempted as declared-exploratory
arms and both failed (rc=1 / 180 s hang): NCCL requires one rank per device. Recorded as
failures in `W1/v003/index.json`. **The library axis is measured only at G=2 on this machine.**

### Control
`W1/v002` and `W1/v003` are independent full re-runs of the gloo arm under two different
result-bookkeeping harnesses: **168/168 cells identical**. The harness change did not move a
single measured bit.

### Draft sentence
> We measured it. On identical input bytes, a production collective reduction returned 14
> distinct 64-bit roots over 14 rank counts from 1 to 64; 78.6% of fp64 configuration pairs
> and 90.0% of fp32 configuration pairs disagree, with spreads to 5,120 ulp, while repeated
> runs at any fixed configuration were bitwise identical (5/5). Reshape moves the answer;
> noise does not.

---

## 2. W2 — repaired (cut-aligned) pinned-FBT vs stock all-reduce

`\PENDING` at `main.tex:192, 3031, 3504`. Result file: `/home/rohit/sprs-fix/experiments/w_final/W2/RESULT.json`.
Raw: `W2/v001` (correctness), `W2/v002` (imbalance), `W2/v003` (invariance + unbatched cost),
`W2/v004` (batched cost, `COST.json`).

### Construction under test
Cut FBT(N) at level d = ceil(log2 G); the 2^d complete subtrees at that level are dealt to
the G ranks; the cross-rank stage evaluates FBT(N)'s top d levels — exactly 2^d - 1 combines
at depth d. This is **not** the index-range partition printed in the paper's step 1, which
T16 proved is not the canonical reduction. T16 verified the corrected construction on
426/426 (N,G) pairs.

### H1 — bitwise reshape-invariance: **SUPPORTS**
32 cases, **32 invariant, 2,414 cells, every cell equal to R_can**, the single-process
canonical FBT(N) reduction.
* World sizes 2,3,4,5,6,7,8,12,16,24,32,48,64 — non-power-of-two G ∈ {3,5,6,7,12,24,48}.
* Leaf counts N ∈ {3,5,6,7,8,12,100,1000,1023,1024,1500,4095,4096} — **10 non-power-of-two
  N**, which is the coverage requirement the pre-registration set (>=4 non-pow2 N, >=3
  non-pow2 G) and the part TBIK does not cover.
* Backends: nccl (G=2, GPU) and gloo (G=2..64, CPU). Both deals (LPT and contiguous).

**Negative control (mandatory, and it fired).** The paper-as-printed index-range partition
was run over the same sweep: **3 of 4 cases failed as they must.** At N=1000 and N=1500 it
produced 3 distinct roots over G ∈ {2,3,8} and **0 of 13 cells equalled R_can**. At N=1024 it
coincides for the G that divide N, and at N=7 it coincides entirely — coincidence, not
correctness. The checker demonstrably can fail, so the positive result above is reportable.

### H2 — cost: **REFUTES the "affordable, TBIK-comparable" branch**
This fired the pre-registered UNFAVOURABLE branch, which is a listed irreducible risk. It is
reported as measured, with no size range cherry-picked as the headline.

Protocol fixed in advance: median over 15 batched regions of B back-to-back collectives
(B = 200/50/20 by size), after 2 warm-up batches; overhead = t(pinned-FBT) / t(stock).

NCCL, G=2, fp64, 1-chunk pinned tree — **geomean 2.57x, best 1.49x, worst 3.91x (n=20)**.
(Correction, 2026-08-28: an earlier revision reported 2.40x / n=28 under this same
"fp64" label. That figure pooled 8 fp32 rows, which geomean 2.02x and diluted the
result. PREREGISTRATION.md:54 fixes the headline as fp64 at G=2, so the fp64-only
figure of 2.57x is the reportable one. The deviation had moved the unfavourable
number in the paper's favour.)
Restricted to the clean 8 KiB -> 128 MiB size sweep: geomean 2.27x, best 1.49x, worst 3.29x.

| bytes | stock (us) | pinned-FBT (us) | overhead |
|---:|---:|---:|---:|
| 8 Ki | 57.4 | 188.8 | 3.29x |
| 32 Ki | 35.2 | 102.6 | 2.92x |
| 128 Ki | 43.3 | 135.1 | 3.12x |
| 512 Ki | 106.3 | 169.4 | 1.59x |
| 2 Mi | 162.4 | 436.2 | 2.69x |
| 8 Mi | 767.9 | 1140.4 | 1.49x |
| 32 Mi | 2636.8 | 4397.9 | 1.67x |
| 128 Mi | 10794.5 | 23820.2 | 2.21x |

Non-power-of-two N at 128 KiB (the genuinely new coverage): N=3 2.19x, 5 2.50x, 6 3.91x,
7 3.01x, 12 2.43x, 100 2.90x, 1000 2.39x, 1023 2.50x, 1500 2.45x, 4095 3.46x — against
N=1024 3.26x and N=4096 2.98x. **There is no non-power-of-two penalty**: the non-pow2 shapes
sit inside the same band as their power-of-two neighbours, which is itself the reportable
result for this axis.

Structural explanation, stated so the number is not mistaken for a tuning failure: at G=2 the
pinned tree performs one directed send of the full M-vector plus a broadcast of the full
M-vector = 2M bytes moved, against a ring all-reduce's M per rank; and it issues two
*dependent* library calls from Python against one fused NCCL kernel, which dominates below
~1 MiB. A 2-chunk bidirectional variant recovers part of the bandwidth term at 128 MiB
(1.85x vs 2.21x) and is far worse below 1 MiB (up to 29x), because it doubles the number of
Python-level point-to-point calls.

### Draft sentence, with the cost caveat that MUST travel with it
> The repaired construction is bitwise reshape-invariant — 2,414 cells over 32 configurations
> spanning rank counts 2 to 64 and leaf counts 3 to 4,096, including ten non-power-of-two N
> and seven non-power-of-two G, every one returning a 64-bit root identical to the canonical
> FBT(N) reduction. On a contended 2-GPU PCIe node with no NVLink it costs a geometric mean
> of 2.57x stock NCCL all-reduce, best 1.49x and **worst 3.91x**, degrading below 1 MiB
> because the cross-rank stage is a latency-bound tree of dependent point-to-point calls with
> no bandwidth-optimal ring. We report this as measured; it is the price of the discipline on
> this fabric and it is not competitive with a bandwidth-optimal ring.

### Cost measurement conditions — read before quoting the number
1. **Both GPUs were held at 100% utilisation by an unrelated user job (`mayank`,
   `model_v8.train`) for the entire measurement window.** An isolated GPU kernel cost a fixed
   ~2.26 ms scheduling slice under that contention, so every timing uses batched regions
   (B back-to-back ops / B) with a co-timed 1-element-add floor probe recorded beside it.
2. The node is **PCIe, `topo = NODE`, no NVLink**, and has only **two** GPUs — so the NCCL arm
   is G=2 only. Everything at G>2 is gloo over TCP loopback on CPU ranks and is labelled as
   such (gloo geomean is 0.65x, i.e. the pinned tree is *faster* than gloo's all-reduce; that
   number measures gloo, not the discipline, and is not a headline).
3. **This figure must NOT be quoted beside TBIK's <=10% number** (Appendix H.1, 4xH20 over
   NVLink, TP=4, uncontended). They are different fabrics, different rank counts, different
   contention states and different software stacks. Quoting them side by side would be
   misleading in the paper's favour in one direction and against it in the other. I repeat
   my own instruction: state the conditions or omit the comparison.
4. The `W2/v004` gloo cells at G>=24 were CPU-contended by the W4 campaign running
   concurrently. A clean re-run was queued as `W2/v005` and **was not reached**; the gloo
   cost cells at G>=24 should be treated as upper bounds, and the NCCL arm (which is the
   headline) is unaffected.

### H3 — load imbalance: **SUPPORTS, with a required paper change**
The frontier assignment does not affect the root, so it is a free load-balancing choice.
Greedy LPT: worst ratio **1.969** over the 426 T16 pairs at G<=64, 1.996 over all 1,546,
1.993 over 44,850 pairs with N<=300 — **none above 2**. The natural **contiguous** deal
reaches **2.48**, with 45 pairs above 2 at G<=64. **The paper must specify LPT for the <=2
bound to hold.** Source: `W2/v002/imbalance.json`.

---

## 3. W4 — clocked route-load calibration, and the refutation of L0b

Raw: `/home/rohit/sprs-fix/experiments/w_final/W4/v001/` (runner, logs, 1,326 raw jsonl
records). Complete re-analysis: `/home/rohit/sprs-fix/experiments/w_final/W4/v002/ANALYSIS_full.json`.

### Correction to my own earlier reporting, stated first
`W4/v001/ANALYSIS.json` reports `meta.n_runs = 605`. `analyse_w4.py` sets `n_runs = len(rows)`,
and the raw jsonl files contain **1,326 unique (instance, pipeline) keys**. v001's ANALYSIS.json
was therefore computed from a partial file while the campaign was still writing (`full.log`
reaches DONE only at 5,511 s). **The raw data in v001 is complete and untouched; only the
derived summary was premature.** v002 recomputes it over all 1,326 and supersedes it. v001 is
kept, not overwritten. Anything already circulated as "605/605" should be restated as
1,326/1,326 — the direction of the result is unchanged and the coverage is more than doubled.

### Question
Every RTL result in the artifact was produced with the route-table bypass — the emitter at
`src/sprs_core.py:~5610` writes hierarchical forces `u_sys.gen_rtr[R].u_rtr.route_table[D] = P;`
instead of calling the clocked `write_route` task it emits at `:5546` and never calls.
Limitation L0b asserts a fidelity band (59% bit-exact, cycles 1-54% lower) for which **no
clocked run exists anywhere in the artifact**, and T11 found no mechanism that would produce
that band.

### Design
Three arms per (instance, pipeline), on the same RTL (which carries the W3 fp64_add repair):
BYPASS (emitter as shipped), CLOCKED (every force textually replaced by
`write_route(R,D,P)`), CORRUPT (clocked with route entries deliberately wrong — the negative
control). The one-line change is applied to the *emitted text*, not to `sprs_core.py`, so no
shipped artifact byte changes.

### Result: **REFUTES L0b**
**1,326 of 1,326 comparable runs: same PASS, same 64-bit root, same cycle count.
100.0% bit-exact. Zero root mismatches, zero PASS flips, zero cycle mismatches.**

The only difference is a strictly deterministic route-load fill time:
**exactly 10.0 ns per route-table entry — min = max = median = 10.0 ns**, i.e. one clock per
entry at the testbench clock period, and nothing else.

This is the pre-registered REFUTE branch, which T11 anticipated:
*"the measured effect is bit-exact on 100%, cycle count higher by route-load fill time only.
L0b's previously stated 59% / 1-54% band is replaced by this measurement. The old band is
deleted, not defended."*

The HARD-STOP case (clocked and bypass disagreeing on the root, or flipping PASS->FAIL) did
**not** occur: 0 of 1,326. Published fabric numbers do not depend on the bypass.

### Negative control (mandatory): **VALID**
24 corrupted-route runs. Corrupting the **whole** clocked route table flips PASS->FAIL on
**24 of 24**. Corrupting a **single** entry still PASSed on 12 of 24 — reported, but that is
expected and is not the control: a single wrong (router, dest) entry may legitimately land on
a pair the schedule never exercises. The control that matters is the all-entries arm, and it
fires.

### What L0b should now read
Replace the existing L0b text with:

> **L0b (route-table loading).** Every fabric result in this paper is produced by writing the
> per-router route tables through a hierarchical force at time zero rather than through the
> clocked configuration port. We have now measured the difference. On all 1,326
> (instance, pipeline) points at G<=64, the clocked path and the force path agree exactly:
> the same PASS/FAIL verdict, the same 64-bit reduction root, and the same cycle count on
> 1,326 of 1,326 — 100% bit-exact, with no exceptions. The only effect of clocked loading is a
> deterministic configuration prologue of exactly one clock per route-table entry (10.0 ns at
> our testbench period, min = max = median), which occurs before `program_start` and therefore
> does not enter any reported cycle count. A negative control confirms the clocked path is
> genuinely exercising routing: corrupting the route table flips PASS to FAIL on 24 of 24
> runs. We therefore withdraw the previously stated fidelity band (59% bit-exact, cycle counts
> 1-54% lower); it was an estimate for which no run existed, and it is wrong.

### Consequence for T11's list — and what must NOT be reinstated
T11 maintained a list of cycle-based conclusions that "fail the band", i.e. conclusions whose
margin was smaller than L0b's asserted 1-54% cycle uncertainty. **That band does not exist.
The measured route-load uncertainty on cycle counts is exactly zero.** T11's list therefore
needs revisiting: every conclusion that was demoted *only* because its margin fell inside
L0b's band should be re-examined, because the reason for the demotion has been removed.

**T08's withdrawal of the N/G knee stands and must NOT be reinstated.** T08 withdrew it on
separate grounds — it is a denominator artefact (Omega's composition changes across the knee,
so the ratio moves for reasons unrelated to the schedule), not a measurement-margin problem.
Nothing in W4 touches that argument. Re-examining T11's list must not be allowed to sweep the
knee back in.

**However, before any conclusion is re-promoted on the strength of a now-zero L0b band, read
§5.** W4's zero-uncertainty result concerns *route loading*. It says nothing about the
separate defect in the published cycle *metric*, which is large and which does affect
cycle-based conclusions.

---

## 4. W7 — measured eta

Result file: `/home/rohit/sprs-fix/experiments/w_final/W7/RESULT.json`.
Raw: `W7/v001/eta_v001.json`, `W7/v001/eta_npow2.json`, harness `W7/v001/w7_eta2.py` and
`nd_tree.py`, logs `w7.log` and `w7_npow2.log`.

### Definition and design
eta = makespan(FBT(N) compiled by pipeline P) / makespan(ND-RecDouble(N,G) compiled by **the
same** pipeline P) — same topology, same G, same two-input ALU, same stage-2/3/4 methods, same
scheduler, same cost model. eta > 1 means the ABI-compliant tree is slower. Both trees are put
through the **real compiler** (`STAGE2/3/4_METHODS` + `build_schedule`), not a model. Every
pipeline the published campaign recorded as `OK_BYPASS` for that instance is replayed on both
trees. DAG isomorphism is checked exactly by canonical form, not assumed.

Two statistics per instance: `eta_champion` (the min-makespan FBT pipeline, with ND under that
same pipeline) and `eta_best_vs_best` (best FBT over all pipelines / best ND over all
pipelines — the fairer head-to-head, since it lets each tree pick its own best pipeline).

### Coverage
29 of the 40 defined instances (39 hardware-validated), **1,716 pipeline comparisons**.
**NOT REACHED, named:** `max_mod_fat`, `max_bal_2d`, `max_dense_hc`, `maxp_mod_fat`,
`maxp_bal_2d`, `maxp_dense_hc`, `large_bal_mesh`, `vlarge_bal_mesh`, `med_full_torus`,
`vlarge2_mod_ring` (all power-of-two, G ∈ 256..4096) and `max_unbal_fat` (N=3000, G=128, the
one unmeasured non-power-of-two instance). Reason is compile cost, not a result: replay time
scales sharply with G — `vlarge_mod_ring` (G=512) took 9,086 s and `large_mod_ring` (G=256)
4,875 s for a single instance.

### Result on power-of-two instances: **SUPPORTS; the REFUTE branch did not fire**
22 instances, **1,374 pipeline comparisons, eta = 1.000000 on every single one. Zero
exceptions.** Isomorphism held exactly (canonical forms equal) on 22 of 22.

The pre-registered REFUTE branch was *"eta != 1 somewhere T10 proves it must be 1 -> the
harness or the proof is wrong; I report WHICH."* It did not fire.

**Honest reading, which the paper must carry.** On these instances eta = 1 is **not**
independent evidence that the ABI is free. The two DAGs are isomorphic, so the same pipeline
necessarily schedules them to the same makespan; the measurement is a **tautology check**.
What it establishes, and what T10's pen-and-paper argument did not, is that the isomorphism
survives the real toolchain end to end — stage-2 assignment, stage-3 mapping, stage-4
refinement and the scheduler — rather than only the abstract construction. It validates the
proof and the harness. The genuinely new information is below.

### Result on non-power-of-two instances: **MEASURED — new information**
7 instances (N,G ∈ {10/4, 16/5, 50/7, 100/10, 200/12, 500/32, 1500/64}), 342 pipeline
comparisons. The DAGs are **not** isomorphic on any of them (0 of 7), so eta is a real
measurement here.

| statistic | geomean | median | min | max |
|---|---:|---:|---:|---:|
| eta_best_vs_best (head to head) | **1.151** | 1.090 | 1.026 | **1.352** |
| eta_champion | 1.058 | 1.090 | 0.755 | 1.272 |

Per-instance `eta_best_vs_best`: npow2n_tiny_ring 1.032, npow2g_small_mesh 1.026,
npow2_tiny_hc 1.090, npow2_small_torus 1.295, npow2_med_fat 1.352, large_unbal_torus 1.042,
vlarge_unbal_hc 1.272.

Across all 342 individual pipeline comparisons the geomean is **1.003**, and the
ABI-compliant tree is **faster on 168 of 342**, equal on 10, slower on 164, range
0.539-2.752. The choice of pipeline moves eta far more than the choice of tree does.

The pre-registration's second REFUTE branch — *"eta >> 1 on the ring/torus instances beyond
the 1.07-1.95x band anticipated"* — did **not** fire. Nothing exceeded 1.352 on either
summary statistic.

### Cross-check against T10, including where it diverges
T10 claimed eta = 1 by construction on 31 of 39 instances; W7 measured 22 of those 31 and
confirmed all of them, on 1,374 comparisons.

T10 also reported that the champion cuts FBT with exactly G-1 cross-PE edges on 33 of 39, and
named four instances that cut *above* G-1: npow2_small_torus 1.22, large_mod_ring 1.07,
med_mod_ring 1.78, vlarge2_mod_ring 1.95. **W7 reproduces only one of those four.** Measured
here: exactly G-1 on 27 of 29, at most G-1 on 28 of 29, above G-1 on **1** —
npow2_small_torus (11 vs 9, ratio 1.222). On `large_mod_ring` and `med_mod_ring` the champion
measured here cuts exactly G-1 (255 and 63) and eta = 1.000000 on all 109 pipelines of each.
`vlarge2_mod_ring` was not measured.

The divergence is a definition, not a contradiction: **T10 read edge_cut from the released
tournament record; W7 selects the min-makespan pipeline among those the hardware campaign
validated, and recompiles it.** Both objects are defensible; they are not the same object and
the paper must not quote them interchangeably. The practical effect is that T10's suggested
residual caveat — *"on the four ring and torus instances whose champion cuts the tree at
1.07-1.95 times G-1, a locality-regrouping reducer might do better"* — is **weakened**: on two
of the three rings measured here, eta is exactly 1 on every pipeline. If the paper keeps that
caveat, it should name npow2_small_torus and say that the other three were not reproduced or
not measured.

### Draft sentence
> We measured eta rather than only arguing it. On 22 hardware-validated instances with N and G
> both powers of two, replaying all 1,374 validated compiler pipelines on both trees gives
> eta = 1.000000 without exception, confirming through the full toolchain the DAG isomorphism
> we prove analytically. On the seven non-power-of-two instances, where no isomorphism exists,
> the measured head-to-head ratio is a geometric mean of 1.15 (median 1.09, range 1.03-1.35);
> across all 342 individual pipeline comparisons the geometric mean is 1.003 and the
> ABI-compliant tree is faster on 168 of them.

---

## 5. DISCLOSURE — the published cycle column, and rows that reproduce under neither metric

This was not a work item. It came out of W4's bypass arm, which re-simulated all 1,326
published `OK_BYPASS` points. **Under Rule 4 I have changed nothing and edited no published
number. I am reporting it.** Raw: `W4/v002/ANALYSIS_full.json`, `W4/v002/gpu0_underreport.json`,
`W4/v002/anomalies21.json`, probes `W4/v002/probe21.py` and `W4/v002/nondet_probe.py`.

The 1,326 published values split three ways. The split is exact, not approximate:

| bucket | rows |
|---|---:|
| max-over-PEs and GPU-0 counter are the SAME number; published agrees (metric indistinguishable) | 628 |
| the two metrics DIFFER, and published equals the **GPU-0 counter** | **569** |
| the two metrics DIFFER, and published equals **max-over-PEs** | **0** |
| published matches **neither** | **129** |

### 5a. The Cycles column is GPU 0's counter, not the makespan
On every one of the 569 rows where the distinction is visible, the published number is GPU 0's
`perf_total`. **Not one row uses max-over-PEs.** The earlier note that the parser was "fixed to
max-over-PEs on 2026-07-27" is not reflected in the shipped
`results/results/live_hw_results_p1_unified.csv`; the column as shipped is GPU 0 throughout.
(My own v001 summary said "298 match max-over-PEs, 286 match GPU-0" — that was the premature
605-row snapshot, and it counted the 628 metric-indistinguishable rows as max-over-PEs
matches. It was wrong in a way that flattered the data. v002 supersedes it.)

Magnitude of the under-report on those 569 rows, true makespan / published:
**geomean 1.61x, median 1.18x, min 1.004x, max 148.4x**; >=1.10x on 326 rows, >=1.5x on 191,
>=2x on 111. Over all 1,326 rows the geomean is **1.23x**. The extreme cases are configurations
where GPU 0 finished almost immediately — e.g. `vlarge_unbal_hc/tb_2c_3i_none` published 5
cycles against a true makespan of 742.

Why this matters beyond the numbers themselves: `cycles/Omega` is understated wherever the
distinction is visible, and — more seriously — **the per-instance champion was selected on this
metric**, so an instance's reported champion may be a configuration in which GPU 0 happened to
idle rather than the fastest schedule. I have not re-derived any champion and I am not
proposing any edit. This needs a decision from the paper owners.

### 5b. The rows that match neither metric: 129, and what they are
127 of the 129 are stage-2 **CPOP (`2i`)** or **ClHEFT (`2n`)**. The concentration is total:

| stage-2 | rows | anomalies | rate |
|---|---:|---:|---:|
| `2i` CPOP | 128 | 75 | 58.6% |
| `2n` ClHEFT | 107 | 52 | 48.6% |
| `2g` | 59 | 2 | 3.4% |
| the other 14 methods | 1,032 | **0** | **0.0%** |

**What they are: the compiler does not always emit the same program for these two stage-2
methods.** Within W4's own campaign, 505 (instance, pipeline) points were compiled and
simulated twice. 483 produced an identical testbench SHA. **22 did not — and on all 22 the
recorded compiler makespan differed too**, so it is the compile that varied, not the
simulation. All 22 are `2i` or `2n`. The reduction **root was identical in every OK/OK pair**,
so correctness is not affected; only the schedule and hence the cycle count. Examples:
`large_unbal_torus/tb_2i_3b` gave makespan 1886 -> 3100 cycles on one occasion and 1755 -> 2992
on the other, with **3100 being the published value**; `large_dense_2d/tb_2n_3a` gave 1375 ->
1606 and 2109 -> 3266; `vlarge_unbal_hc/tb_2i_3a` gave 4303 -> 7043 and 3986 -> 6548.

I could not reproduce the variation in isolation, and I am reporting that rather than
asserting a mechanism I have not shown. Negative control on the mechanism: six of the affected
points were recompiled in 12 fresh processes (4 repetitions x 3 arms — alone, after a priming
compile of a different point, and twice within one process), with `PYTHONHASHSEED=random`.
**72 observations, one distinct (assignment hash, makespan) per target — perfectly
deterministic**, and equal to the second campaign draw in each case. The wall-clock
`AlgoTimeout` path is ruled out: the W4 runner never calls `_set_eval_deadline`, so
`_DEADLINE` stays `+inf` and `_check_deadline` cannot fire. Snapshot and worktree compilers
were also compared head to head on ten of these points and produced **identical assignments
and identical makespans on 10 of 10** (`W4/v002/snapshot.json` vs `worktree.json`), so this is
not drift introduced by the worktree's repairs.

The honest statement is therefore: *for stage-2 CPOP and ClHEFT the compile is reproducible
under controlled single-purpose conditions but was not reproducible under the concurrent
campaign harness, and roughly half of the published cycle values for those two methods cannot
be reproduced by recompiling and re-simulating the same (instance, pipeline).* The other
fourteen stage-2 methods reproduce exactly, 1,032 of 1,032.

### 5c. Suggested disclosure text
> The `Cycles` column of our released results is GPU 0's cycle counter rather than the maximum
> over processing elements; on the 569 of 1,326 configurations where the two differ, the
> released value understates the makespan by a geometric mean of 1.61x (median 1.18x).
> Separately, for two of the seventeen stage-2 assignment methods (CPOP and cluster-HEFT) the
> compiler did not reproduce the same schedule when the same configuration was recompiled
> under our concurrent measurement harness; roughly half of the released cycle values for
> those two methods therefore do not reproduce, although the reduction result is unaffected
> and identical in every case we re-ran.

---

## 6. Cost of the measurement round, and what was not run

Approximate machine cost: W4 ~14 core-hours of xsim across 1,326 runs x 3 arms (`full.log`
DONE at 5,511 s wall on 72 cores) plus the 505-point re-run; W7 ~8 core-hours dominated by
two G>=256 instances (9,086 s and 4,875 s); W1 and W2 well under 2 GPU-hours, on GPUs that
were **never idle** — see §2's conditions block.

**Not run, by council decision and not revisited here:** synthesis/PPA, multi-node, tournament
tie-break, full campaign re-run. All four were assessed and rejected before this round began.

**`maxp_mod_fat` (instance 40 of 40).** T13 established that the blocker was never a RAM or
elaboration ceiling: at G=4096 the adjacency fields truncated to 12 bits, 0 of 8,223 installed
links matched the intended fat-tree and 0 of 900 sampled routes delivered. The worktree
emitter now auto-sizes `ADJ_ID_W` (`src/sprs_core.py:~5510`), and any instance that fitted in
12 bits still emits byte-identical SystemVerilog, so every previously recorded tb_hash is
preserved. With 273 GB of RAM reclaimed, an elaboration at `ADJ_ID_W=16` has been launched
**detached** under `/home/rohit/sprs-fix/experiments/w_final/W8_maxp/v001/` (`run_maxp.sh`,
progress in `status.txt`). `xvlog` completed rc=0; `xelab` is running. It is not blocking, and
nothing in this report depends on its outcome. If it produces a snapshot and the simulation
settles, instance coverage goes from 39/40 to 40/40 and Limitation L0's stated explanation
(a router-count ceiling) is wrong and should be corrected to the adjacency-width cause
regardless of whether the run finishes.

---

## 7. Index of files

| item | path |
|---|---|
| pre-registration | `/home/rohit/sprs-fix/experiments/PREREGISTRATION.md` |
| this report | `/home/rohit/sprs-fix/experiments/w_final/EXPERIMENTS_REPORT.md` |
| W1 result | `/home/rohit/sprs-fix/experiments/w_final/W1/RESULT.json` |
| W1 raw | `/home/rohit/sprs-fix/experiments/w_final/W1/v001,v002,v003/` |
| W2 result | `/home/rohit/sprs-fix/experiments/w_final/W2/RESULT.json` |
| W2 raw | `/home/rohit/sprs-fix/experiments/w_final/W2/v001..v004/` (`v004/COST.json`) |
| W4 raw (complete, 1,326 runs) | `/home/rohit/sprs-fix/experiments/w_final/W4/v001/full_bypass_clocked*.jsonl` |
| W4 premature summary (superseded, kept) | `/home/rohit/sprs-fix/experiments/w_final/W4/v001/ANALYSIS.json` |
| W4 complete analysis | `/home/rohit/sprs-fix/experiments/w_final/W4/v002/ANALYSIS_full.json` |
| W4 GPU-0 under-report table | `/home/rohit/sprs-fix/experiments/w_final/W4/v002/gpu0_underreport.json` |
| W4 nondeterminism probe | `/home/rohit/sprs-fix/experiments/w_final/W4/v002/nondet_probe.py`, `nondet.jsonl` |
| W4 snapshot-vs-worktree compiler probe | `/home/rohit/sprs-fix/experiments/w_final/W4/v002/probe21.py`, `snapshot.json`, `worktree.json` |
| W7 result | `/home/rohit/sprs-fix/experiments/w_final/W7/RESULT.json` |
| W7 raw | `/home/rohit/sprs-fix/experiments/w_final/W7/v001/` |
| maxp_mod_fat (detached, running) | `/home/rohit/sprs-fix/experiments/w_final/W8_maxp/v001/status.txt` |
