# SPRS Phase‑2 (S4 Local Optimization) — Analysis, Experiments & Final Plan

**Date:** 2026‑07‑05
**Context:** SPRS NoC tournament, 40 instances (leaf‑count × GPU‑count × topology
{mesh, torus, hypercube, fat‑tree, ring, 1D}). Phase‑1 (SW eval + force‑bypass HW sim
of the S2×S3 grid) is complete: **2,842 HW results across 39 instances**. This document
records the investigation into **reducing Phase‑2 compute**, i.e. the S4 local‑optimization
(refinement) stage.

---

## 1. Question

Phase‑2 applies **11 local‑optimization algorithms** (the S4 refiners) on top of Phase‑1
solutions, then HW‑simulates winners. Goal: cut this from 11 → 2–3, or otherwise bound the
compute, without losing the best solutions.

The question evolved across the discussion:
1. Reduce 11 → 2–3 refiners: prune in both SW+HW, or run all in SW and HW only winners?
2. Run S4 over **all ~2,800 unique solutions** (not just winners) — what does that cost?
3. Gate HW on improvement + final SW makespan — but ε is confusing and SW makespan misleads.
4. Anchor the champion in **HW**, run all‑improving HW on low‑correlation instances, or pick a
   single algorithm (universal / per‑topology / per‑instance)?
5. Can the **S2/S3 compute from Phase‑1 be reused** instead of recomputed?

---

## 2. What the code actually does (ground truth)

- **`STAGE4_METHODS`** = 12 entries; `4a='None'` → **11 real refiners**:
  `4b CPcoloc, 4c FM, 4c2 MCFM, 4d ALNS, 4e LeafMig, 4f NetW, 4g SubMig, 4h CentReb,
  4i TERe, 4j VCycles, 4k FlowMC`.
- **`_eval_greedy_pipeline(s2,s3,…)`**: computes `ms_base`; for each of 11 refiners applies it
  to `asgn_base` (the **S2 output**), keeps it **only if `ms_L1 < ms_base`** (strict final‑value
  improvement); then greedily chains a 2nd refiner (`4a+4b` style), kept only if it beats L1.
  → **Selection metric already coded = final makespan improvement; non‑improving refiners are never written.**
- **Refiners operate on the S2 assignment (S3‑independent).** `_get_metrics` then runs `s3f` on
  the refined assignment + `build_schedule` + `generate_instructions`.
- Data shapes: **6,785 valid pipelines** (of 7,200 = 180×40), dedup → **2,920 unique solutions
  (`tb_hash`)**, collapsing to only **641 unique S2‑assignments (`asgn_hash`)**.

---

## 3. Experiments & Results

### 3.1 S4 on winners is a near‑no‑op
Probe: 11 refiners on 22 real Phase‑1 winner pipelines (tiny→large, 6 topologies).
- **21/22 got ZERO improvement; 1 improved by 0.6%.** (~0.4% fire rate.)
- Reason: refiners are *local* optimizers; winners are already near‑locally‑optimal.

### 3.2 Improvement is strongly quality‑dependent (tiered probe)
Sampling solutions by makespan quantile, all sizes/topologies:

| Tier | improve rate (of 11) | typical gain |
|---|---|---|
| best (winners) | **0%** | 0% |
| median | ~25% | 3–33% |
| worst | ~48% | **74–98%** |
| **overall** | **24.2%** | (change rate 45%) |

Refiners **rescue bad solutions dramatically** (e.g. `large_mod_ring` worst 17,488 → 265) but
**cannot improve good ones**. Crucially, **no rescued solution ever beat its instance's champion**
(e.g. `med_mod_ring` worst 2020→~100 vs champion **71**).

### 3.3 SW makespan is an unreliable fine selector
Selection fidelity (HW cycles vs SW makespan), degenerate "collapsed" TBs excluded:

| Selector | picks true HW‑best | median regret | mean regret |
|---|---|---|---|
| Top‑1 (SW‑best) | **54%** | 0% | 232% |
| Top‑3 makespan tiers | **85%** | 0% | 11% |

- **Degenerate traps:** 13 TBs across 7 instances report ~5 cycles at 3–5× makespan (collapsed
  ≈1‑GPU mappings). SW makespan correctly ranks them terribly; they only pollute the raw HW‑argmin.
- **SW‑deceptive methods** (low makespan, catastrophic HW cycles): S2 **2p Spine (57×), 2o ParSub (34×),
  2g DSC (41×)**; S3 **3e MCF, 3i RAGreedy**. Worst pair `2p|3b` on rings (34× HW gap at a 1‑unit makespan tie).
- **HW‑winner methods:** S2 **2b RecBisect wins 35/39**; S3 **3e (17), 3a (11), 3b (5)** — all cheap.

### 3.4 Reliability is governed by TOPOLOGY (factor analysis)
Competitive‑band Spearman (ranking among *good* solutions — what gating needs):

| Factor | reliable (high ρ) | unreliable (low ρ) |
|---|---|---|
| **Topology** ⭐ | 1D/linear **0.75**, mesh 0.56 | ring **0.36**, fat 0.42, hypercube 0.45 |
| N/G ratio | N/G≥8 → 0.55 | N/G<8 → 0.41 |
| Size | small/med 0.57 | big 0.45 (weak) |
| Non‑power‑of‑2 | 0.51 | 0.45 (negligible) |

**21 low‑correlation instances (ρ<0.6)** = all rings/tori/fat/most hypercubes → SW makespan can't
be trusted to gate there.

### 3.5 Which of the 11 refiners earn their keep (per‑refiner probe)

| refiner | improved (of 48) | was best |
|---|---|---|
| **4c2 MCFM** | 23 | **12** |
| **4j VCycles** | 20 | **12** |
| **4g SubMig** | 22 | 8 |
| 4e LeafMig / 4c FM | 13 / 14 | 4 / 3 |
| 4f,4k,4d,4i | 11–16 | 1–2 |
| **4b CPcoloc / 4h CentReb** | 6 / 2 | **0 / 0** |

- **Top‑3 (MCFM 4c2, VCycles 4j, SubMig 4g) = 67% of all best outcomes.** CPcoloc & CentReb are dead weight.
- **No topology clustering** — the same 3 win on every topology. → algorithm choice is **universal**, not per‑instance.
- Contrast: *which refiner* is universal; *whether to trust SW for gating* is topology‑dependent.

### 3.6 Stage timing profile (where the compute actually goes)
`vlarge2_dense_2d (N=2048)`:

```
S3 Tabu 11,852 ms   S3 Spectral 4,980 ms   S2 CPFD 808 ms
build_schedule 17 ms   generate_instructions 9 ms     ← trivial
```

**The S2/S3 algorithms dominate; scheduling+codegen is ~25 ms.** The expensive S3 methods
(3j Tabu, 3h Spectral) **never produce an HW champion** (§3.3), so re‑running them on refined
partitions doesn't change what gets simulated — only how much SW compute it costs to confirm that.

**Decision (2026‑07‑05): re‑map with ALL 10 S3 methods, not just the 3 cheap ones.** User opted
for completeness over the SW‑cost saving. Cost impact: ~10–20× more S3 compute per refined
solution on the instances where 3h/3j dominate (mainly the giants); the HW side is unaffected
(gate is still measured‑cycles vs champion, and 3h/3j still won't win). SW total moves from
"single‑digit core‑h" to a figure the giants will dominate — still well under the ~296–331
core‑h HW cost, so it does not change the overall ~2–4 day critical path.

### 3.7 New‑TB volume for the 3‑refiner plan
Exact count via `(assignment, S3)` keys (per‑unique‑assignment refinement):
- 3 refiners produce **~1.5× new unique TBs** vs the original set.
- Non‑giant instances: cheap (17–34 s/sim → ~1–4 core‑h each).
- **Giants dominate**: each new TB on `max_mod_fat`/`maxp_bal_2d` costs 1.5–5.6 h.

### 3.8 Phase‑1 HW‑cycle feed gate (uses measured cycles, not SW makespan)
Refine only solutions already within M× of the **HW champion** (ground truth):

| Gate (measured cycles) | feed | ~new TBs | HW no‑giants | HW all 40 |
|---|---|---|---|---|
| ≤ 1.5× champ | 312 | ~470 | **9 core‑h** | 200 |
| **≤ 2× champ** | 513 | ~770 | **16 core‑h** | 296 |
| ≤ 3× champ | 819 | ~1,230 | **23 core‑h** | 331 |
| no gate | 2,664 | ~4,000 | 89 core‑h | 1,187 |

---

## 4. Compute estimates

**Naive** (refine all 2,920 solutions × 11 refiners, HW on any improvement):
- SW ~450–750 core‑h (naive) / ~230 (dedup+skip); HW ~800–1,600 core‑h (24% improve rate).
- **Total ~1,000–2,300 core‑h ≈ 1–2 weeks wall‑clock**, HW‑ and giant/RAM‑bound (93% of HW is 5 giants).

**Cost is dominated by giants in both SW (Tabu/Spectral re‑runs) and HW (1.5–5.6 h/sim).**

---

## 5. Conclusions

1. **S4 refinement almost never changes the answer.** Winners are unimprovable; rescued bad
   solutions stay below champion. The value of an exhaustive S4‑HW run is a *research dataset*
   ("refiners fix bad solutions, can't improve good ones"), not better competition results.
2. **Two levers, opposite answers:**
   - *Which refiner to run* → **universal top‑3** (MCFM 4c2, VCycles 4j, SubMig 4g). Topology/size/NG/npow2 irrelevant.
   - *Whether to trust SW for HW gating* → **topology‑dependent** (rings/fat/hypercube untrustworthy).
3. **Anchor everything in Phase‑1 HW, not SW makespan.** Champion = min measured cycles; gate feed
   on measured cycles (≤2–3× champ).
4. **Phase‑1 makes some recompute avoidable:** S2 → 641 unique assignments (cache once); baseline
   makespans already stored → skip base evals. **(S3 re‑map: user opted to run ALL 10 methods, not
   just the cheap winners — see decision note in §3.6/§6. Costs more SW compute but doesn't change
   what gets HW‑simulated, since 3h/3j still never win.)**
5. **Giants (`max*`,`maxp*`) are the entire cost problem** (~94% of S4 HW). Decision: **hold only
   `maxp_mod_fat`** (no Phase‑1 HW); the other 5 giants get S4 HW → they set the ~2–4 day critical path.

---

## 6. FINAL PLAN

**Restrict S4 to 3 refiners + Phase‑1‑anchored gating + giant hold + hash dedup.**

1. **SW sweep:** run only **MCFM (4c2), VCycles (4j), SubMig (4g)** over the **HW‑cycle‑gated feed**
   (solutions with measured Phase‑1 cycles ≤ **2–3× champion**).
   - Reuse S2: compute the **641 unique assignments once** (cache), don't rerun `s2f` per solution.
   - Reuse Phase‑1 baselines: read `ms_base` from `sw_results.csv`, skip base evals.
   - **Re‑map refined partitions with ALL 10 S3 methods** (user decision: completeness over SW‑cost
     saving; 3h Spectral/3j Tabu never win an HW champion but are still run).
   - Cost: SW rises from "single‑digit core‑h" to a figure dominated by the giants (~10–20× more
     S3 compute where 3h/3j apply) — still well under the ~296–331 core‑h HW cost below.
2. **HW:** simulate every **new unique refined TB after hash dedup** (deduped against each other and
   against the existing 2,842 results — never re‑sim). **Scope: only `maxp_mod_fat` is held (it has no
   Phase‑1 HW anyway); the other 39 instances — including the 5 remaining giants — get S4 SW + HW.**

   | gate | 34 non‑giants | 5 giants | **total (39 inst)** |
   |---|---|---|---|
   | ≤2× champ | 16 core‑h | **279** | **296 core‑h** |
   | ≤3× champ | 23 core‑h | 307 | 331 core‑h |

   Per‑giant (≤2×): `max_mod_fat` 177 (~32 TBs × 5.6 h), `maxp_bal_2d` 70, `maxp_dense_hc` 15,
   `max_bal_2d` 11, `max_dense_hc` 6. **~94% of HW is the 5 giants.**
3. **Champion:** min measured HW cycles per instance (degenerate collapsed TBs excluded).

**Total: SW <½ day + HW ~296–331 core‑h ≈ ~2–4 days wall‑clock** (34 non‑giants <1 day; the giants
are the critical path — `max_mod_fat` alone ~177 core‑h, RAM‑bound ~2–3 concurrent). Down from
~1–2 weeks naive, entirely anchored in Phase‑1 HW ground truth. Tightening the gate to ≤1.5× *on the
giants only* would cut this further if needed.

**Caveat:** the HW‑cycle gate assumes a solution far from champion in HW won't be rescued *past*
champion by refinement. The makespan probe supports this, but HW‑cycle gains are unmeasured — use
**≤3× champ** if you want extra safety on low‑correlation (ring/fat/hypercube) instances.

---

## 7. Phase‑1 loose end (status 2026‑07‑05 14:47)

Two giant re‑run TBs (from earlier wall‑clock timeouts) still in progress:
- `max_mod_fat/tb_2f_3a_none` — xsim running, ~3.9 h elapsed, sim‑time 569 ms, no `[PASS]` yet.
- `maxp_bal_2d/tb_2f_3a_none` — xsim running, ~4.5 h elapsed, sim‑time 1076 ms, no `[PASS]` yet.

Runner PID 2324512 (`--jobs 2 /tmp/hw_redo2.json`), cap 28,800 s. Slow due to verbose NOCTRC/PIU
tracing (0.5–1.2 MB logs). CSV at **2,842 rows** until they land. Once done, prepend the header
(`Instance,Pipeline,TB_Name,Pass,Cycles,SimTime_s,ErrorCode,Error`) to
`live_hw_results_p1_unified.csv` for downstream use.

---

## 8. Scripts (in scratchpad unless noted)
- `s4_analysis.py` — winner feed, per‑instance winner variance, selection fidelity, timing ingredients.
- `c_and_cost.py` — fidelity (degenerates excluded) + naive compute estimate.
- `s4_tiered.py` — improvement/change rate by quality tier.
- `s4_perref.py` — per‑refiner improvement + best counts + topology clustering.
- `newtb.py` — exact new‑unique‑TB count for the 3‑refiner plan.
- (inline) HW‑cycle feed‑gate bands; per‑instance correlation × topology/size/NG/npow2; stage timing profile.
