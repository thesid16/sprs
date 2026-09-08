# ATTACK SURFACE — hostile TPDS referee report

Target: `/home/rohit/sprs-review/runs/20260817T230831Z/paper_v7/main.tex` (3,781 lines).
The path in the brief, `/home/rohit/sprs-fix/paper_v7/main.tex`, does not exist; the file above
is the only `paper_v7/main.tex` on the system and is the live draft (mtime 2026-08-27 04:07).

Everything below was verified by execution against the artifact. Where I could not substantiate
an attack I say so in §6 rather than list it as a suspicion.

Severity key. **FATAL** = referee stops and recommends reject / writes to the editor.
**MAJOR** = will not survive a first-turn accept. **MINOR** = copy-edit.

---

## VERDICT IN ONE PARAGRAPH

The paper is not currently rejectable for dishonesty — the opposite. Its limitations section
retracts three of its own earlier claims by name, its consistency checker correctly fails on all
five `\PENDING` markers, and every unfavourable measurement in `w_final/` is reported in the
measurement record. **The rejection case is about what happens next.** There is exactly one way
this manuscript gets rejected at TPDS on the first turn that the authors are currently walking
toward: **landing W7's $\eta$**. Doing so violates the paper's own Metric Convention, produces
the artefact §\ref{sec:method-nd} pre-emptively disowned, and uses a baseline the paper's own
theorem guarantees will tie — three self-inflicted contradictions in one paragraph. The second
strongest attack is the pre-registration deviation on the W2 headline (2.40x should be 2.57x),
because the pre-registration ships with the artifact and a referee can recompute it in ten lines.
The third is that the paper's only PDS-relevant performance measurement was taken while another
user's job saturated both GPUs. Everything else is fixable by rewording.

## THE FIVE THINGS THAT MATTER, RANKED

| # | finding | severity | fix |
|---|---|---|---|
| 1 | [S4-ETA-1]/[S4-ETA-2]/[S4-ETA-3] — reporting W7's $\eta$ | **FATAL if done** | do NOT report $\eta$; W7 -> companion as proof validation. Free. |
| 2 | [S1-SEL-2] — W2 headline deviates from the pre-registration, in the paper's favour | **MAJOR** | recompute: fp64-only geomean **2.57x** (n=20), worst 3.91x. Free. |
| 3 | [S1-SEL-3] — W2 cost measured under 100% external GPU contention | **MAJOR** | **ADD EXPERIMENT**: re-run the 20-cell NCCL arm on an idle node. |
| 4 | [S3-MAXP-1]/[S3-MAXP-2] — L0's "would have elaborated and run" is now falsified; table caption contradicts L0 | **MAJOR** | replace with the observed W8 result. Zero pages. |
| 5 | [S1-SEL-1] — the $\le 2$ imbalance bound holds only under LPT | **MAJOR** | name LPT and the 2.48 contiguous counterexample. One sentence. |

---

# 1. SELECTIVE REPORTING

## 1.1 Audit of every pre-registered hypothesis

The draft is a **pre-landing snapshot**: W1, W2, W4 and W7 are not in it at all, and each is
flagged by a live `\PENDING` that `scripts/check_consistency.py` correctly fails on (verified:
`rc=1`, 5 hard failures at lines 192, 1977, 2636, 3031, 3504). So the literal question
"is a measured unfavourable result missing from the draft?" answers *no measured result of any
kind is in the draft yet*. The audit below is therefore of **discoverability at landing**, and of
statements **already in the draft** that the measurements contradict.

| pre-registered item | outcome | favourable? | in draft today | risk at landing |
|---|---|---|---|---|
| **W2-H1** bitwise reshape-invariance | SUPPORTS: 32 cases, 2,414 cells, all $= \Rcan$; 10 non-pow2 $N$, 7 non-pow2 $G$ | yes | no (`\PENDING` :3031) | must carry the **negative control** (see 1.2) |
| **W2-H1 negative control** (mis-cut / paper-as-printed) | FIRED: 3 of 4 cases; 0 of 13 cells $=\Rcan$ at $N{=}1000,1500$ | n/a | no | **omitting it makes H1 unreportable.** Highest-risk omission in the round |
| **W2-H2** cost vs stock NCCL | REFUTES the affordable branch | **NO** | no (`\PENDING` :192,:3031,:3504) | **[S1-SEL-2]** wrong statistic; **[S1-SEL-3]** contended machine |
| **W2-H3** load imbalance $\le 2$ | SUPPORTS *under LPT only*; contiguous reaches 2.48/3.53 | partly | **YES, and wrong** at `:3002` | **[S1-SEL-1]** |
| **W2 coverage requirement** ($\ge4$ non-pow2 $N$, $\ge3$ non-pow2 $G$) | MET (10 and 7) | yes | no | none |
| **W2/v005** clean gloo re-run at $G\ge24$ | **NOT REACHED** | n/a | no | must be named; gloo cells at $G\ge24$ are upper bounds |
| **W1** divergence premise | PARTIAL — the pre-registered branch | yes | no (`\PENDING` :2636); L2 at `:3313` says "not measured by us" | **[S1-SEL-4]** gloo/CPU not GPU; confounded with local partitioning |
| **W1 NOT REACHED**: NCCL at $G>2$ | both arms failed (rc=1 / hang) | n/a | no | must be named; library axis is $G{=}2$ only |
| **W4** clocked route-load | REFUTES L0b: 1,326/1,326 identical PASS, root, cycles | **yes, strongly** | L0b at `:3273` already withdrew the band | none — L0b gets shorter |
| **W4 negative control** | whole-table corruption 24/24 PASS->FAIL; **single-entry 12/24 still PASS** | mixed | no | **the 12/24 must travel with the 24/24** |
| **W4 HARD-STOP** (root/PASS disagreement) | did not occur, 0/1,326 | yes | no | none |
| **W4 by-product §5a** released `Cycles` = GPU-0 | confirmed by me: 2,822/2,822 | **NO** | no | draft's tables use `maxpe`, so numbers unaffected — **[S2-PROV-3]** |
| **W4 by-product §5b** 129/1,326 rows non-reproducible | confirmed by me against `maxpe.csv` | **NO** | no | **[S2-PROV-4]** — must be disclosed; verified not to move any champion |
| **W7** $\eta=1$ on power-of-two | SUPPORTS, but a **tautology check** (isomorphic DAGs) | neutral | no (`\PENDING` :2636) | **[S4-ETA-1..3]** |
| **W7** $\eta$ on non-power-of-two | MEASURED: best-vs-best geomean 1.151, range 1.026-1.352 | neutral | no | model error exceeds the effect |
| **W7 NOT REACHED**: 11 instances (10 pow2 at $G\in[256,4096]$, `max_unbal_fat`) | named, reason = compile cost | n/a | no | must be named |
| **W7 vs T10 cross-check** | reproduces **1 of 4** above-$G{-}1$ instances | mixed | T10's caveat is **not** in the draft | if the caveat is added, name `npow2_small_torus` only |
| **W4/v001 premature summary** (605 vs 1,326) | self-corrected in v002 | n/a | no | anything circulated as "605/605" must be restated |
| **Discipline item 5** (synthesis/PPA, multi-node, tie-break, full re-run) | not run by council decision | n/a | L0c/L1/L1b cover it | none |

## 1.2 The one omission that would be fatal

**W2-H1's negative control.** The pre-registration is categorical: *"NEGATIVE CONTROL (mandatory):
a deliberately mis-cut variant ... MUST produce a root that differs from $\Rcan$ ... If the
mis-cut control also passes, the checker cannot fail and no positive result from it may be
reported."* It fired: at $N{=}1000$ and $N{=}1500$ the paper-as-printed index-range construction
gave 3 distinct roots over $G\in\{2,3,8\}$ and **0 of 13 cells** equal to $\Rcan$
(`W2/RESULT.json.H1_negative_control`). Reporting "2,414 cells, all invariant" **without** it
would be reporting a check that a referee cannot tell apart from a check that cannot fail —
and the paper has already been burned once on exactly this construction. It is one sentence.
**If page pressure forces a cut, cut something else.**

## 1.3 Not selective reporting — the record is clean here

I looked for a measured-and-buried result and did not find one. `EXPERIMENTS_REPORT.md` leads its
executive summary with the two unfavourable outcomes ("Two work items produced results that are
unfavourable ... Both are reported here as the primary finding of their section, not as a
footnote"), self-corrects its own premature W4 summary in the direction that *disfavours* the
data ("It was wrong in a way that flattered the data"), and names every NOT-REACHED arm.
On this axis the advocate is right and the theme is settled. The problems are [S1-SEL-1..4],
which are about *how the results land*, not about results being hidden.

---

# 2. PROVENANCE — summary

**Confirmed:** `tables/invariance.tex` is the only table in the draft generated from the defective
`live_hw_results_p1_unified.csv`, because `scripts/gen_tables.py:29` hardcodes it instead of
calling `hwdata.select()` as every other generator does. The `make check` guard
(`grep -rl DEFECTIVE tables/`) structurally cannot catch it.

**But it does not reach correctness, and I verified this rather than assuming it:**
the two CSVs have identical instance sets and identical per-instance passing-row counts
(2,822 each, 0 differences), and `invariance.tex` contains no cycle-derived column — its root
column is scanned out of the emitted testbenches, not the CSV. Regenerating from `maxpe.csv`
changes no printed digit.

**Two live problems remain:** [S2-PROV-2] the shipped `invariance.tex` was hand-edited and
`make tables` silently reverts a T03 correction; [S2-PROV-4] 129 of 1,326 re-simulated rows do
not reproduce the value in `maxpe.csv` — verified not to move any champion, but it must be
disclosed. Details in the findings log.

---

# 3. THE 39/40 DISCLOSURE — summary

Read as written, L0 is **honest scoping**, not a trimmed suite: the instance is named, the
mechanism is characterised (8,223 links installed / 0 correct / 0 of 900 routes delivered), and
the consequence for the $N{=}8192$ table row is stated. Two things spoil it:
[S3-MAXP-1] the counterfactual "would have elaborated **and run**", whose second half the new W8
evidence falsifies (I reproduced it: `xelab` exit 0 after 58:28 and 54.8 GB, a 2.1 GB database
written, no `xsimk`, and `xsim maxp_snap -R` refuses to start); and [S3-MAXP-2] a table caption
that gives the reader the budget explanation L0 itself retracts. Exact replacement wording,
supported by the evidence and not overclaiming a root cause, is in the findings log.

---

# 4. CLAIM VERSUS EVIDENCE — summary

See [S4-ETA-1], [S4-ETA-2], [S4-ETA-3] (the $\eta$ cluster — the paper's principal exposure),
[S4-CLAIM-1] (a claim about a ratio the paper says three times it never measured),
[S4-CLAIM-2] (the invariance claim, which I verified holds — including an independent
1,326-run replication on repaired RTL that the draft does not yet use), and
[S4-VENUE-1] (the "cluster" framing, and why it makes W1/W2 non-negotiable for TPDS).

---

# FINDINGS LOG (append-only; each entry tagged with its section)

## [S2-PROV-1] `tables/invariance.tex` is generated from the defective CSV — provenance only, NOT correctness. **MINOR**

**File:line.** `/home/rohit/sprs-review/runs/20260817T230831Z/paper_v7/tables/invariance.tex:3`
(`% source : /home/rohit/tournament_p1/results/live_hw_results_p1_unified.csv`), pulled in at
`main.tex:2541`. Generator: `paper_v7/scripts/gen_tables.py:29` (`HW_CSV = f"{P1}/live_hw_results_p1_unified.csv"`).

**What a referee would cite.** `paper_v7/scripts/hwdata.py` states in its own docstring that
`live_hw_results_p1_unified.csv` is "DEFECTIVE for any cycle-derived claim". Every other
generator (`gen_cost_tables.py:87`, `gen_tournament.py:105`, `gen_coverage.py:110`,
`gen_figures.py:107`) routes through `hwdata.select()`. `gen_tables.py` is the **only**
generator that hardcodes the defective file and bypasses the selector. The `make check`
guard that is supposed to catch this — `grep -rl "DEFECTIVE" tables/` in `paper_v7/Makefile` —
cannot fire, because only `hwdata.select()` stamps that word, and `gen_tables.py` never calls it.

**Verified by execution — the attack does NOT reach correctness.** I regenerated and diffed
the two CSVs directly:

* `unified` = 2,844 rows / 2,822 passing / 39 instances; `maxpe` = 2,854 rows / 2,822 passing /
  39 instances. **Identical instance sets, identical per-instance passing-row counts (0 diffs).**
* `maxpe.Cycles == max(PerfAllGPUs)` on **2,822 of 2,822** passing rows — the re-measured file
  is internally consistent with its stated metric.
* `unified.Cycles == maxpe.CyclesGPU0` on **2,822 of 2,822** — independent confirmation of the
  W4 §5a claim that the released `unified` column is GPU 0's counter throughout.
* The two metrics differ on **1,424 of 2,822 (50.5%)** passing rows.

`invariance.tex` contains **no cycle-derived column**. Its root column comes from the
`EXPECTED = 64'h...` constant scanned out of the emitted testbenches
(`gen_tables.py:105 canonical_roots()`), not from either CSV; the CSV supplies only the
"HW configs (passing)" count and the HW-validated flag, and those are bit-identical between
the two files. **Regenerating `invariance.tex` from `maxpe.csv` would change no printed number.**

**Verdict:** provenance defect, not a correctness defect. A referee who checks will find a
defective source named on the paper's *primary result table*, and that alone is bad optics on
a paper whose selling point is auditability — but it does not move a digit.

**Cheapest defence that actually closes it.** Two-line change, no new work:
1. In `gen_tables.py`, replace the hardcoded `HW_CSV` with `hwdata.select()` and regenerate.
2. Extend the `make check` guard so it also fails when any file in `tables/` names
   `live_hw_results_p1_unified.csv` in its provenance header, not only when it contains the
   literal string `DEFECTIVE`.
Reword is NOT sufficient here: the header is machine-generated and would come back.

---

## [S2-PROV-2] `tables/invariance.tex` is a "GENERATED — do not edit by hand" file that **was** edited by hand, and `make tables` silently reverts a correction. **MAJOR (integrity), cheap to fix**

**Verified by execution.** I copied `paper_v7/` to scratch and ran `python3 scripts/gen_tables.py`.
Diff of shipped vs regenerated `tables/invariance.tex`:

```
<     & $(G,\text{topo})$ & $(G,\text{topo})$ & (passing) & & & flagged & flagged \\
---
>     & $(G,\text{topo})$ & $(G,\text{topo})$ & (passing) & & & detected & detected \\
```
and the note line
```
< % note : ... mutation columns count harness FLAGS, not value-comparison detections (T03)
> % note : ... mutation columns filled
```

**Why this is worse than cosmetic.** The word "detected" is exactly the overclaim that finding
T03 corrected: those columns count *harness flags*, not value-comparison detections. The
correction lives **only** in the hand-edited artefact; `gen_tables.py:170-185` still emits
"detected". Any referee (or any co-author) who runs the paper's own documented
`make tables` re-introduces a retracted claim into the primary result table, and `make check`
will report PASS. On a paper whose contribution is "the record is what a reader can check",
a build that un-does its own erratum is a direct hit on the central rhetorical claim.

**Cheapest defence.** Fix the string in `gen_tables.py` (one line, `detected` -> `flagged`,
plus the note text) and regenerate. Do NOT leave the hand-edit in place. This is a five-minute
change; it is not optional, because the failure mode is silent.

---

## [S2-PROV-3] The one place the defective metric COULD have propagated — champion selection — does not. Verified. **NOT AN ATTACK**

The measurement report (`EXPERIMENTS_REPORT.md` §5a) warns that "the per-instance champion was
selected on this metric, so an instance's reported champion may be a configuration in which
GPU 0 happened to idle". I checked whether that is true of the *draft*:

* `tables/perinstance_full.tex:3`, `tables/omegaratio.tex:3`, `tables/selbias.tex:3` all name
  `live_hw_results_p1_maxpe.csv`; `tables/selection.tex:5` names
  `snapshot/results/results/live_hw_results_p1_maxpe.csv`;
  `council/work/SELECTION_RULE.json.method` confirms the champion classes were built by
  inheriting HW cycles **from `live_hw_results_p1_maxpe.csv`**.
* Recomputing per-instance minima from `maxpe.csv` reproduces 39 instances and a champion-class
  S2 membership distribution consistent with `tables/catalogue.tex`.

So the champions in the draft are on the corrected max-over-PEs metric. §5a's warning applies to
the *released CSV*, not to the manuscript. An advocate who says this is a disclosure problem and
not a numbers problem is **right**.

---

## [S2-PROV-4] 129 of 1,326 re-simulated rows do NOT reproduce the value in `maxpe.csv` — the paper's own authoritative source. **MAJOR (disclosure), verified not to move any headline**

This is stronger than the version in `EXPERIMENTS_REPORT.md` §5b, which compared against the
*defective* `unified.csv`. I re-ran the comparison against `maxpe.csv`, the file the manuscript
actually uses:

```
compared against maxpe.csv:  n=1326  match=1197  mismatch=129 (9.7%)
by stage2:  2g(DSC) 59 rows, 2 mismatches (3.4%)
            2i(CPOP) 128 rows, 75 mismatches (58.6%)
            2n(ClHEFT) 107 rows, 52 mismatches (48.6%)
            all 14 other stage-2 methods: 0 of 1,032
```
Examples: `large_bal_mesh/tb_2i_3a_none` published 2,627, re-simulated 2,633;
`large_dense_2d/tb_2i_3a_none` published 3,775, re-simulated 3,876;
`large_unbal_torus/tb_2n_3a_none` published 1,894, re-simulated 338.
On these rows `maxpe.Cycles == maxpe.CyclesGPU0`, so it is **not** a metric artefact — the
compiler emitted a different program under the same `(instance, pipeline)` key.

**What a referee would say.** "You claim exhaustive enumeration and an auditable record. I
re-ran 1,326 of your 2,822 configurations with your own tooling and 9.7% of your published
cycle counts did not come back. Explain."

**Verified counter-argument — this one does not reach the headline.** I checked, and the
authors can answer it:
* **0 of the 129 mismatched rows is a published per-instance champion.**
* Substituting **every** re-simulated value for its published value changes the per-instance
  minimum on **0 of 39 instances**.
* CPOP and ClHEFT are `0.0%` champion-class members in `tables/catalogue.tex`; recomputing
  champion classes from `maxpe.csv` puts 2i and 2n in the champion class of **0 of 39**
  instances. The two DSC (2g) anomalies are `med_mod_ring/tb_2g_3h` (169 vs 172, instance
  min 159) and `vlarge_extreme_1d/tb_2g_3h` (930 vs 923, instance min 537) — neither near
  the minimum.

**Verdict.** Not fatal to any number. But **it must be disclosed**, because a TPDS referee who
touches the artifact will find it, and finding it *unlabelled* converts a bounded caveat into a
credibility event. This is precisely the case where the cheap fix (say nothing, hope nobody
runs it) is inadequate.

**Cheapest adequate defence.** A three-to-four-sentence limitation, stating (a) the two affected
stage-2 methods by name, (b) the 129/1,326 rate, (c) that the reduction root was identical in
every re-run pair so correctness is untouched, and (d) the two verified negative results above:
no champion and no per-instance minimum moves. Point (d) is what turns this from a wound into
a strength, and it costs zero new experiments — the check is the 30-line script I ran.
**Do not omit (d)**; without it the disclosure reads as an unbounded admission.

---

## [S4-ETA-1] **THE STRONGEST REJECTION CASE IN THE PAPER.** W7's "measured $\eta$" is a ratio of two *compiler cost-model* makespans, and the paper's own data shows that model mispredicts RTL cycles by more than the entire effect being reported. **FATAL if $\eta$ is presented as a hardware cost.**

**Where.** `main.tex:2636` `\PENDING{W1/W4/W7}` sits inside `\S`\ref{sec:results-overhead} "The Cost
of the ABI"; `main.tex:3324` (L1b) currently says *"We report no $\eta$ ... the ABI's cost is priced
structurally"*. The obvious plan is to use W7 to retire L1b. **That plan does not survive review.**

**What W7 actually computes.** `/home/rohit/sprs-fix/experiments/w_final/W7/v001/w7_eta2.py:31`:
```python
sched = sc.build_schedule(tree, asgn, mapping, G, topo, sc.HW, alu_op=sc.ALU_FADD)
...
return dict(makespan=sched.makespan, ...)
...
row['eta'] = round(f['makespan'] / n['makespan'], 6)
```
`sched.makespan` is the SPRS scheduler's analytic makespan. **No RTL simulation of the
ND-RecDouble tree exists anywhere.** W7 never invokes xsim; `W7/v001/` contains no testbench,
no `.sv`, no simulator log. So $\eta$ is a ratio of two predictions from the same cost model,
not a measured ratio of two hardware runs.

**The calibration the paper already contains, which destroys the claim.** I joined every
`results/results/<inst>/sw_results.csv` `makespan` column to its RTL cycle count in
`live_hw_results_p1_maxpe.csv` — 2,822 matched pairs, the paper's own released data:

```
HW cycles / compiler makespan
   min 0.264   p05 1.116   median 1.530   p95 2.872   max 9.646   geomean 1.587
   only 18.8% of 2,822 points lie within +/-5% of the median
```
Per-instance geomeans span **1.194 (`med_extreme_1d`) to 2.266 (`max_mod_fat`)** — a 1.9x
spread *between* instances. Worse, the spread *within* a single instance, across the pipelines
W7 replays, is:

| non-pow-2 instance W7 measures | within-instance HW/model ratio | W7 `eta_best_vs_best` |
|---|---|---|
| `npow2n_tiny_ring` | 1.189 - 1.410 | 1.032 |
| `npow2g_small_mesh` | 1.138 - 1.509 | 1.026 |
| `npow2_tiny_hc` | 1.096 - 1.568 | 1.090 |
| `npow2_small_torus` | 1.105 - 1.573 | 1.295 |
| `npow2_med_fat` | 1.081 - **2.901** | 1.352 |
| `large_unbal_torus` | 1.077 - 1.910 | 1.042 |
| `vlarge_unbal_hc` | 1.101 - 1.686 | 1.272 |

**On all seven instances the model's own demonstrated error band is wider than the effect W7
reports.** $\eta_{\text{best vs best}} = 1.15$ geomean is a 15% effect estimated with an
instrument the paper's own data shows is good to a factor of 1.3-2.7 on those very instances.
The referee's sentence writes itself: *"Your $\eta$ is a quotient of two cost-model outputs.
Your released data shows the cost model is wrong by 17%-190% against your own RTL. Why is a
15% ratio meaningful?"*

**Second, independent hole in the same result.** `eta = 1.000000` on 1,374/1,374 power-of-two
comparisons is, as the measurement report itself concedes, *"a TAUTOLOGY CHECK"* — the DAGs are
isomorphic, so the same pipeline necessarily returns the same makespan. Reporting "1,374
comparisons, zero exceptions" in a results section without that concession front and centre is
exactly the kind of impressive-looking denominator a TPDS referee is trained to distrust.
If the tautology caveat is relegated to a footnote or dropped for space, this becomes a
**selective-reporting** finding, not a methodology one.

**Third.** `w7_eta2.py:54` reads `live_hw_results_p1_unified.csv` — the defective CSV — to
enumerate which pipelines to replay. Harmless in substance (only the `ErrorCode` column is
used, and the two CSVs have identical passing sets, verified above) but it is a third
appearance of the defective file in the audit trail.

**Cheap defences and why they are NOT adequate.**
1. *"Relabel it: say 'scheduler-model makespan ratio' rather than 'measured $\eta$'."*
   Adequate ONLY if the paper simultaneously **keeps L1b standing** and does not claim the
   cost gap is closed. It is not adequate if $\eta = 1.15$ is quoted anywhere as the ABI's
   price on this fabric, because the relabelled quantity does not support that sentence.
2. *"Report the tautology caveat and move on."* Insufficient by itself; the non-pow-2 block
   is the only new information and it is the block the calibration attacks.
3. *"Report a confidence interval from the model error."* Would swallow the entire effect;
   arithmetically self-defeating.

**The expensive fix that is genuinely required if the paper wants to retire L1b.** RTL-simulate
the ND-RecDouble tree on the seven non-power-of-two instances and report $\eta$ in **HW cycles**.
This is affordable and should be done:
* `nd_tree.ShapeTree` already subclasses `sprs_core.CBTree` with the same accessor surface and
  already compiles through `STAGE2/3/4` + `build_schedule`, so the missing step is codegen +
  xsim, not new compiler work.
* The seven instances are `N,G` = 10/4, 16/5, 50/7, 100/10, 200/12, 500/32, 1500/64.
  `tables/walltime.tex` records these at 17-104 testbenches and 12-14 s median simulation each;
  the whole set is single-digit core-hours, against the 14 core-hours W4 already spent.
* The ND tree's `EXPECTED` root must be recomputed (it is deliberately *not* $\Rcan$); that is
  a few lines in the emitter, and it doubles as a second negative control for the invariance
  claim (a legitimately different order producing a legitimately different root on the same
  fabric).

Under the council's lexicographic objective this is the clearest case in the paper where goal 3
(avoid new work) must yield to goal 1. A TPDS referee reads "cost on the same fabric" as a
hardware number. Shipping a cost-model quotient under that heading, on a paper whose thesis is
that *measured* beats *argued*, invites the reviewer to apply the paper's own standard against it.

---

## [S4-ETA-2] Reporting W7's $\eta$ would contradict **two** statements already in the draft. **FATAL as an internal contradiction.**

**`main.tex:2454-2456`** (Metric Convention):
> `\sv{hw\_cycles}` is the primary metric ... **`\sv{makespan}` from the software cost model
> is a diagnostic only.**

**`main.tex:2290-2302`** (Non-Deterministic Baseline on the Same Fabric):
> **We did not build these baselines, and we report no measured $\eta$.** We also decline to
> substitute an analytical one. We built such a model --- the same cost constants that produce
> $\Omega$, applied to a ring and to recursive doubling --- and it returns $\hat\eta \approx 1$
> on every instance in the suite ... A number produced this way **would read as evidence that
> the ABI is free, which contradicts the structural argument two paragraphs below, so we report
> the absence rather than the artefact.**

W7 returns exactly the number the paper pre-emptively disowned: $\eta = 1.000000$ on
1,374/1,374 power-of-two comparisons, geomean **1.003** across all 342 individual non-power-of-two
pipeline comparisons, with the ABI-compliant tree **faster on 168 of 342**. That reads as
"the ABI is free", from `sched.makespan`, which the paper has already declared a diagnostic.

A referee reading §\ref{sec:method-nd} and then a results paragraph quoting $\eta$ from the
same cost model will conclude one of two things: the authors forgot what they wrote, or they
changed the standard when the number came out favourable. Neither survives.

**This is the objection that neither the paper nor the advocate can answer.** The only honest
answers are (a) drop $\eta$ and leave L1b standing, or (b) measure $\eta$ in RTL cycles.
There is no wording that makes a cost-model quotient satisfy a metric convention that names
it a diagnostic.

**Recommended:** ADD EXPERIMENT (RTL $\eta$ on the seven non-power-of-two instances, see
[S4-ETA-1]) **or** NO CHANGE to §\ref{sec:method-nd}/L1b and relegate all of W7 to the
companion as a proof/harness validation. Do not attempt the middle path.

---

## [S1-SEL-1] W2-H3: the draft asserts a load-imbalance bound that the measurement shows is **false as stated**, and the bound's stated *reason* is wrong. **MAJOR**

**File:line.** `main.tex:3002-3004`:
> "$426$ of $426$ swept pairs exact, worst-case load imbalance $1.969$ **and bounded by $2$
> because $\FBT(N)$ is depth-imbalanced by at most one level**"

**Evidence (verified, `W2/v002/imbalance.json`).** The $\le 2$ bound holds **only under a greedy
largest-processing-time (LPT) deal** of the cut frontier. Under the **natural contiguous deal**:

| sweep | worst contiguous | pairs $>2$ | worst LPT | LPT pairs $>2$ |
|---|---:|---:|---:|---:|
| 426 T16 pairs, $G\le64$ | **2.48** (N=100,G=62) | 45 | 1.96875 | 0 |
| 1,546 T16 pairs | **2.52** (N=200,G=126) | 76 | 1.99609 | 0 |
| 44,850 pairs, $N\le300$ | **3.529** (N=272,G=240) | 13,446 | 1.99333 | 0 |
| 223 paper leaf counts | 2.048 (N=1500,G=12) | 8 | 1.92 | 0 |

Depth-imbalance-by-one is **not** what produces the bound; the assignment rule is. The draft
names the wrong cause and omits the precondition.

**Why a referee treats this as more than a slip.** This sentence sits in §\ref{sec:discussion-pinfbt},
the section whose entire purpose is to retract a previously published unproven assertion about
this same construction. A second unstated-hypothesis assertion, in the repair of the first,
is exactly the pattern that turns "honest authors" into "authors who assert bounds they have
not checked".

**Cheapest defence — and here the cheap fix IS adequate.** One sentence, no new work:
> "...worst-case load imbalance $1.969$ under a greedy largest-first deal of the frontier
> subtrees, which we verify holds below $2$ on all $44{,}850$ pairs with $N \le 300$; the
> natural contiguous deal is **not** so bounded and reaches $2.48$ at $(N,G)=(100,62)$. The
> frontier assignment does not affect the root, so this is a free load-balancing choice."
Naming the counterexample is what closes it; naming LPT alone does not, because the next
question is "and what happens if I do the obvious thing instead?"

---

## [S3-MAXP-1] The 39/40 disclosure contains an unbacked counterfactual that the new W8 evidence **directly contradicts**. **MAJOR — and it is the third instance of the same failure mode**

**File:line.** `main.tex:3221-3243` (Limitation L0), specifically **`main.tex:3239`**:
> "**The testbench would have elaborated and run**; it could not have settled at any budget, so
> \MaxpCoreHours{} core-hours bought a configuration no budget could complete."

**Evidence I verified myself, first-hand.**
* `/home/rohit/sprs-fix/experiments/w_final/W8_maxp/v002/xelab.log:8333` — `Exit status: 0`;
  line 8315 `Elapsed (wall clock) time: 58:28.24`; line 8320 `Maximum resident set size: 54,795,304 kB`
  (54.8 GB); final compile line reads `Built simulation snapshot maxp_snap`.
* `/home/rohit/expscratch/maxp_v001/xsim.dir/maxp_snap/` contains
  `xsim.dbg` 1,340,019,384 B, `xsim.reloc` 460,485,137 B, `xsim.mem` 259,176,310 B,
  `xsim.rtti`, `xsim.svtype`, `xsim.type`, `xsim.xdbg`, `Compile_Options.txt` — **and no `xsimk`**.
* A known-good snapshot on the same machine and same tool version
  (`/home/rohit/expscratch/w4/insp/byp/xsim.dir/sim_byp/`) contains `xsimk` (executable),
  `xsimkernel.log`, `xsimcrash.log`, `xsim_script.tcl`, `xsimSettings.ini`. **None of those five
  files exists in `maxp_snap/`.**
* I ran the simulator myself:
  ```
  $ cd /home/rohit/expscratch/maxp_v001 && xsim maxp_snap -R
  ERROR: Please check the snapshot name which is created during 'xelab',
         the current snapshot name "xsim.dir/maxp_snap/xsimk" does not exist
  ```
* `xelab.log` contains exactly one WARNING (an unrelated `LIBRARY_PATH` notice, XSIM 43-3431)
  and zero ERROR lines. The tool reports success and produces no kernel.

**What this does to L0.** The draft's counterfactual splits in two:
* "*would have elaborated*" — **now supported**, at 16-bit adjacency ids. Good news for the paper.
* "*and run*" — **now contradicted by the only attempt that exists.** The design elaborates; the
  simulator emits no kernel and the run cannot be started.

**How a referee reads the current text.** Not as dishonest — L0 is unusually forthcoming and
explicitly retracts an earlier wall-clock story. But the referee will notice the *shape* of the
error, because this is the third time in one manuscript:
1. `main.tex:2964-2972` — the published pinned-FBT step 1 "**asserted** that each rank then
   reduces exactly the subtree ... That assertion is false."
2. `main.tex:3287-3290` (L0b) — "an earlier version of this paper quoted a calibration ...
   that **cannot be re-derived from anything we hold**, and we withdraw it."
3. `main.tex:3239` (L0) — "The testbench **would have** elaborated and run."

Each is a claim about behaviour with no run behind it. The first two are retracted in the
manuscript itself; the third is still live, and is now falsified in its second half. A referee
who spots the pattern stops giving the benefit of the doubt on every other unbacked sentence
in the paper — including the four structural cost terms of §\ref{sec:results-overhead}, which
are also argued rather than measured.

**Verdict on the question posed.** Read as written today, L0 is *honest scoping with one
overreaching sentence*. It is **not** a suite trimmed to what worked: the instance is named, its
$N$ and $G$ are given, the failure is characterised mechanistically with 8,223 links / 0 correct /
0 of 900 routes, and the consequence for Table~\ref{tab:invariance}'s $N=8192$ row is stated.
The only thing that turns it into "trimmed to what worked" is the unearned "and run".

**Exact replacement wording that is defensible and supported by this evidence** (delete
`main.tex:3239`'s counterfactual; keep everything else):

> No budget could have made that configuration settle. Widening the adjacency id removes that
> defect, and we report what happened when we tried it rather than what we expect. Elaboration
> of a 16-bit-id testbench for this instance completes and the tool reports success --- 58~min
> of wall time and 54.8~GB of peak resident memory, producing a 2.1~GB design database --- but
> no executable simulation kernel is written, and the simulator declines to start the run. We
> have not established a root cause for that and do not assert one; a tool that exits zero
> without emitting its own output is, on the evidence we hold, misreporting. We therefore
> exclude \sv{maxp\_mod\_fat} because we have not been able to simulate it, not because we
> chose not to, and the $N{=}8192$ column of Table~\ref{tab:invariance} rests on the two
> remaining $(G,\text{topology})$ points.

**Do NOT write** any of: "the elaboration ceiling has been removed", "the instance now
elaborates successfully", "40 of 40 are now reachable", "the root cause is a simulator limit".
Exit 0 with missing output is the tool misreporting; the cause is unconfirmed and the paper
cannot afford a fourth unbacked assertion in the same section.

**Cost.** Zero pages (the replacement is the same length), zero new experiments (the run is
done). This is the cheap fix and here the cheap fix **is** adequate — provided it is worded as
observation, not as diagnosis.

---

## [S1-SEL-2] **The pre-registered headline number was computed a different way than pre-registered, and the deviation moves it in the paper's favour.** **MAJOR — this is the single most damaging thing a referee can find, because the pre-registration ships with the artifact**

**Pre-registration, `experiments/PREREGISTRATION.md`, W2-H2, written before measurement:**
> "Headline = geomean overhead at G=2, **fp64**, over the swept sizes, WITH the worst case
> printed alongside it in the same sentence."

**What was reported** (`W2/RESULT.json.H2_cost.nccl_G2_fbt_chunks1` and
`EXPERIMENTS_REPORT.md` §2): **`n=28, geomean 2.398, best 1.485, WORST 3.907`**, quoted
throughout as "geomean **2.40x**".

**What I computed from `W2/v004/COST.json` directly:**

| statistic | n | geomean |
|---|---:|---:|
| reported headline (`nccl`, `fbt_ch1`, **all dtypes pooled**) | 28 | **2.398** |
| **fp64 only** — the pre-registered statistic | 20 | **2.569** |
| fp64, the actual size sweep (N=8, 8 KiB -> 128 MiB) | 8 | 2.268 |
| fp64, the N sweep at a single size (128 KiB) | 13 | 2.814 |

The reported headline pools **8 fp32 rows** (overheads 1.58-3.39, geomean 2.02) into a
statistic the pre-registration fixed as fp64. It is **neither** of the two defensible readings
of the pre-registered sentence, and it is **lower than both the fp64-only figure (2.57x) and
the fp64 N-sweep figure (2.81x)**. The deviation is 0.17x-0.42x in the paper's favour on the
one number the pre-registration existed to protect.

**Second composition problem in the same statistic.** Of the 20 fp64 NCCL rows, **13 sit at a
single message size (131,072 B)**; only 8 points constitute the "full size sweep" the
pre-registration required. Pooling a 13-point N-sweep at one size with an 8-point size sweep
produces a geomean that is 65% one message size. Neither reading of "over the swept sizes"
sanctions that.

**Why this is fatal-adjacent rather than a rounding quibble.** The paper's entire credibility
strategy is "we pre-registered, so you can trust the unfavourable numbers". A referee who
opens `PREREGISTRATION.md` (it is in the artifact, and the paper will cite it) and recomputes
finds the headline unfavourable number softened by a post-hoc change of denominator. That is
the exact failure mode the document was written to prevent, and it converts the paper's
strongest rhetorical asset into its worst liability.

**Cheapest defence, and it IS adequate — but only if done exactly.** No new experiments.
Report, in one sentence, the pre-registered statistic and both its components:
> "On this 2-GPU PCIe node the repaired construction costs a geometric mean of **2.57x** stock
> NCCL all-reduce in FP64 (best 1.49x, **worst 3.91x**, $n=20$), decomposing into 2.27x over
> the 8 KiB-128 MiB size sweep at fixed $N$ and 2.81x over the leaf-count sweep at 128 KiB."
And state in the companion that the fp32 arm gives 2.02x, separately.

**Do NOT** print 2.40x anywhere. **Do NOT** quote the 2.27x size-sweep figure alone as the
headline: that is the lowest of the four and choosing it after seeing the data is the same
offence in the other direction.

---

## [S1-SEL-3] The W2 cost measurement was taken while an unrelated user job saturated both GPUs. A TPDS referee will not accept it. **MAJOR — requires re-measurement, and the cheap fix is not adequate**

**Evidence, from the measurement team's own record** (`W2/RESULT.json.hardware.contention`,
restated in `EXPERIMENTS_REPORT.md` §2 "Cost measurement conditions"):
> "**Both GPUs were held at 100% utilisation by an unrelated user job (`mayank`,
> `model_v8.train`) for the entire measurement window.** An isolated GPU kernel cost a fixed
> ~2.26 ms scheduling slice under that contention."

The batched-region protocol mitigates the fixed slice, and a floor probe is co-timed — good
practice. But the `floor_us` column in `COST.json` is **13.4 us on 14 of the 20 fp64 rows**
against a stock time of **41.6 us**: the co-timed floor is ~32% of the baseline measurement at
128 KiB. The `overhead_floor_corrected` column moves those rows from 2.4-3.9x to **2.7-5.3x**,
i.e. the correction the authors themselves computed changes the answer by up to 35%.

**The referee question neither the paper nor the advocate can answer:** *"What is the overhead
on an idle machine?"* Nobody knows. There is no uncontended measurement anywhere in
`w_final/`. The pre-registered protocol does not rescue this: a pre-registration fixes what you
report, not whether the machine was yours.

**Cheap fixes and why each fails.**
* *"Disclose the contention and quote the number anyway."* This is what the report proposes.
  It is not adequate for TPDS. Parallel-systems referees reject performance numbers taken under
  uncontrolled external load as a matter of course; disclosure converts "wrong" into
  "acknowledged as unusable", which is not better for acceptance.
* *"Quote `overhead_floor_corrected` instead."* Worse — the corrected numbers are *higher*
  (up to 5.26x) and are themselves a model of the contention, not a measurement without it.
* *"Move the whole cost result to the companion."* Tempting under goal 2, and it does save the
  space, but it leaves `\PENDING{W2}` at `main.tex:192` (abstract), `:3031` and `:3504`
  (conclusion) with nothing to become. The abstract promises "the headline cost number and the
  deployability claim".

**Required (ADD EXPERIMENT).** Re-run `W2/v004`'s NCCL arm on an idle node. This is the
cheapest new experiment in the whole docket: `drive_w2b4.py` exists, the sweep is 20 fp64 cells,
each is 15 batched regions, and the report itself says the entire W1+W2 round cost "well under
2 GPU-hours". Waiting for the machine is the cost, not compute. Also re-run the queued
`W2/v005` (the clean gloo cells at $G\ge24$ that were CPU-contended by W4 and are currently
"upper bounds").

Under the lexicographic objective this is unambiguous: goal 3 (avoid new work) loses to goal 1.
A contended headline performance number in a TPDS submission is a first-turn reject.

---

## [S1-SEL-4] W1's divergence result is measured on **gloo/TCP over CPU ranks**, not on GPUs, and it conflates the collective with the application's own partitioning. **MAJOR at write-up time**

**Verified.** Every one of the 14 reshape-axis world sizes is a `gloo` arm:
`W1/v003/raw/A_gloo_G{1,2,3,4,5,6,7,8,12,16,24,32,48,64}_fp{32,64}.json`, with
`env.GLOO_SOCKET_IFNAME = "lo"` — TCP loopback, CPU ranks, single node. The only NCCL arms are
`B_nccl_G2_*` (7 configurations, all at $G=2$). `W1/RESULT.json.not_reached` records that NCCL
at $G=3$ and $G=4$ both failed (rc=1 / 180 s hang).

**Two things the proposed draft sentence would say that the data does not support.**

1. `EXPERIMENTS_REPORT.md` §1 proposes: *"a **production collective** reduction returned 14
   distinct 64-bit roots over 14 rank counts from 1 to 64"*. In a TPDS paper whose motivating
   example is *"a training job rerun on a cluster resized from $G{=}128$ to $G{=}256$ GPUs"*
   (`main.tex:230-232`), "production collective" will be read as NCCL on GPUs. It is gloo on
   CPU. The word `gloo` must appear in the same sentence as the number.

2. The reduction is `torch.stack([leafvec(i) for i in range(lo,hi)]).sum(dim=0)` followed by
   `dist.all_reduce` (`W1/v003/libfreeze/w_worker.py:185,192`). Because `lo,hi` depend on $G$,
   **the local summation shape changes with $G$ too**. The 14-distinct-roots figure therefore
   confounds (a) the application's re-partitioning with (b) the collective's cross-rank tree.
   The $G{=}1$ configuration proves (a) alone suffices: it involves no collective at all and
   still produces a distinct root. Meanwhile the only clean test of (b) — `NCCL_ALGO` x
   `NCCL_PROTO`, 7 configurations — returned **one** root.

**The referee's question.** *"Your abstract says 'the underlying collective's reduction order
changes, and so do the last bits.' Your measurement varies the rank count, which changes the
per-rank local sum as well. Your one controlled test of the collective's own algorithm choice
found no divergence. Which of the two mechanisms did you measure?"*

**Verified defences the authors DO have, and should use.**
* Excluding $G{=}1$ the effect is undiminished: **13 distinct roots over the 13 rank counts
  $2\ldots64$**, in all six fp64 cases (I recomputed this from
  `W1/v003/raw/A_gloo_G*_fp64.json`). The result does not depend on the degenerate case.
* The single-root NCCL algo/proto sweep is **structurally** incapable of divergence at $G{=}2$
  (one cross-rank addition per element), as `W1/RESULT.json.library_axis` correctly states.
  It is not an empirical null and must not be reported as a partial refutation — but it also
  cannot be cited as evidence for the collective axis.
* The strongest clean evidence for mechanism (b) is the **device axis**: at a *fixed* $G{=}2$
  partition the CPU and GPU roots differ in 12 of 12 cases. That is identical data, identical
  partition, different implementation, different bits. **This, not the algo/proto sweep, is
  the paper's library-axis evidence, and it is currently buried in `RESULT.json`.**

**Cheapest adequate defence — reword only, no new work.** Land W1 as the pre-registered
three-way decomposition, in one paragraph:
> "gloo over CPU ranks, 13 rank counts from 2 to 64 on identical input bytes: 13 distinct
> 64-bit roots, spreads to 5{,}120 ulp, 78.6% of fp64 configuration pairs disagreeing; repeated
> runs at a fixed configuration bitwise identical, 5 of 5; and at a fixed two-way partition the
> CPU and GPU implementations disagree in 12 of 12 cases. Reshape moves the answer and
> implementation moves the answer; run-to-run noise does not. We could not vary NCCL's algorithm
> at $G>2$ on a two-GPU node, so the library axis is measured only where it is structurally
> incapable of divergence."
This is honest, it is stronger than the current version, and it costs nothing. An **ADD
EXPERIMENT** here (a real multi-GPU NCCL reshape sweep) would be decisive but the hardware does
not exist on this node; do not recommend it.

---

## [S3-MAXP-2] The table caption and Limitation L0 give the reader **two different reasons** for excluding instance 40. **MAJOR — this is what makes a referee suspect trimming**

* `main.tex:2549-2551` (note under Table~\ref{tab:invariance}): "The single shortfall is
  $N{=}8192$, where `maxp_mod_fat` ($G{=}4096$, fat-tree) **exceeded the simulation budget**."
* `main.tex:3226-3229` (L0): "all hit the $28{,}800$~s wall-clock cap ... **but wall-clock was
  not the binding constraint, and we correct an earlier account that said it was.**"

The manuscript retracts the budget explanation in §\ref{sec:limitations} and then states it as
fact under its primary table. A referee reads the table before the limitations. The first
thing they learn about the missing instance is the story the authors have already withdrawn —
and "we ran out of budget on the biggest case" is precisely the phrasing that reads as a suite
trimmed to what worked.

**Cheapest defence.** Replace the caption clause with the correct one, ~10 words, zero page
delta:
> "The single shortfall is $N{=}8192$: \sv{maxp\_mod\_fat} ($G{=}4096$, fat-tree) is excluded
> for the configuration-interface defect of L0, not for cost."
This must move with [S3-MAXP-1].

---

## [S4-CLAIM-1] `main.tex:1949-1951` asserts a property of a ratio the paper says three times it never measured. **MINOR, free to fix**

> "At $G \geq 1024$ on ring and torus, absolute cycle counts slew because of this; **the ratio
> against the non-deterministic baseline is more stable because both schedules share the
> bottleneck.**"

The paper states at `main.tex:2291`, `:2626` and `:3307` that no non-deterministic baseline was
built and no $\eta$ is reported. W7 does not rescue the sentence either: its coverage
(`W7/RESULT.json.coverage.not_measured`) excludes **every** $G \ge 256$ ring, torus and mesh
instance, which is exactly the regime the sentence is about.

**Fix:** delete the clause after the semicolon. Zero pages, zero risk.

---

## [S4-CLAIM-2] What the invariance evidence actually is, and the one place it is loose. **NOT FATAL — the advocate is right, with one caveat**

I checked whether the primary result is as strong as stated.
* PASS in the testbench is an exact 64-bit compare:
  `if(all_done && u_sys.gen_node[0].u_cn.result==EXPECTED) $display("[PASS] ...")`
  (`tournament_p1/results/tiny_dense_1d/tb_2a_3e_none.sv:160`). So `Pass=True` in the CSV does
  mean "root bit-identical to the oracle constant", and the claim at `main.tex:2499-2504` is
  supported.
* `gen_tables.py:105 canonical_roots()` asserts `len(exps)==1` per $N$ across all emitted
  testbenches, so the same `EXPECTED` really is shared across every $(G,\text{topology})$ point
  at that $N$.
* **Independent replication I verified:** W4's bypass arm re-simulated 1,326 configurations on
  the *W3-repaired* RTL. All 1,326 PASS, `root == expected` on 1,326/1,326, and every
  `root_hex` equals the value printed in `tables/invariance.tex` for that $N$ — **0 violations**,
  covering 12 of the 16 leaf counts (8,10,16,32,50,100,128,200,500,512,1024,1500).
  $N \in \{2048,3000,4096,8192\}$ are **not** covered by the replication.

**Use it.** This is a free, strong asset: it is an independent re-run, months later, on repaired
RTL, reproducing the paper's primary result exactly. It also discharges L4's assertion that the
`fp64_add` effective-subtraction defect affects "no number in this paper" **by measurement**
rather than by the L13 argument — on 1,326 configurations at 12 leaf counts. One sentence.

**The loose part.** The released CSV keeps only a boolean; the measured root is printed by the
testbench (`$display("  root_gpu=0 root_result=%0d expected=%0d", ...)`) and then discarded.
An artifact-evaluation referee will ask why a paper about bitwise reproducibility does not
archive the bits. W4's jsonl now holds them for 1,326 of 2,822 configurations; say so, and say
which 4 leaf counts are not covered.

---

# 5. THE FIVE `\PENDING` MARKERS — what each must become

`grep -n '\\PENDING' main.tex` (excluding the `\newcommand` at :110):

| # | line | tag | section |
|---|---:|---|---|
| 1 | 192 | `W2` | abstract |
| 2 | 1977 | `W3` | §\ref{sec:fabric-lim}, Known Limitations of the fabric |
| 3 | 2636 | `W1/W4/W7` | §\ref{sec:results-overhead}, The Cost of the ABI |
| 4 | 3031 | `W2` | §\ref{sec:discussion-pinfbt}, Exporting the ABI |
| 5 | 3504 | `W2` | §\ref{sec:conclusion} |

## PENDING #2 (`main.tex:1977`, W3) — **CAN BE FULLY DISCHARGED TODAY. I ran it.**

This is the only PENDING whose evidence is complete, clean, and entirely favourable. I executed
the tests myself in `/home/rohit/sprs-fix`:

```
$ N_DE=1500 N_UNIF=15000 python3 tests/fp64/test_sw_rtl_equiv.py
  (A) accuracy vs exact IEEE-754 RNE
      effective subtraction : 0/121500 errors
      effective addition    : 0/24300
      uniform random        : 0/15000
  (B) bit-for-bit sprs_core._fp64_add_bits <-> rtl/fp64_add.sv
      mismatches            : 0/160800
  RESULT: PASS
```
**Negative control fires** (same test against the pre-fix RTL, `tests/fp64/obj_EVALPRE/rtl_eval`):
```
  mismatches : 15717/62320    (all +1 ulp, all on the effective-subtraction path;
                               15717/48600 = 32.3% of mixed-sign vectors)
  RESULT: FAIL
```
And the scope claim is verified two independent ways:
```
$ python3 tests/fp64/test_no_published_number_moves.py
  check 1: non-positive leaves over [0,200000)          : 0
  check 2: roots moved pre-fix vs post-fix, G = 2..16384 : 0 over 53 G values
           FADDs with s_a != s_b                         : 0
  check 3 (negative control): mutant roots detected      : 2/2
  RESULT: PASS
```
plus the empirical check I did earlier: W4 re-simulated **1,326** published configurations on
the repaired RTL and got `root == expected` on 1,326/1,326, matching `tables/invariance.tex`
exactly at 12 of the 16 leaf counts.

**What it must become** (replaces `main.tex:1977`, ~6 lines, +0.1 page):
> *Effective subtraction in `fp64_add`.* The shipped adder's effective-subtraction path
> discarded the alignment tail before subtracting, so the raw difference was one tail too large
> and the round-to-nearest-even decision could round a value below the midpoint upwards. The
> error is exactly $+1$ ulp and occurs on 32.3% of mixed-sign operand pairs in a binade sweep.
> We have repaired it by borrowing the tail into the subtraction and carrying it through
> normalisation; the repaired adder is bit-identical to correctly-rounded IEEE-754 RNE addition
> on all 160{,}800 vectors of that sweep and on a 4.1M-vector extension, and the pre-fix adder
> fails the same test on 15{,}717 of 62{,}320. No number in this paper moves: the leaf
> distribution~\eqref{eq:leaves} is strictly positive, so no FADD in any reported configuration
> has operands of differing sign --- we verify this over all $G \in [2,16384]$ --- and
> re-simulating 1{,}326 of the campaign's configurations on the repaired RTL reproduces every
> published root bit-for-bit.

Also **delete the L4 sentence** at `main.tex:3336-3339` that describes the defect as an
outstanding deviation ("Beyond those documented deviations, the adder's effective-subtraction
path does not produce the round-to-nearest-even result the policy specifies"); it is now fixed
and the limitation should say so.

## PENDING #3 (`main.tex:2636`, W1/W4/W7) — **must be SPLIT. Do not discharge it as one block.**

It bundles three items with three different verdicts.

* **W1 (divergence premise).** Discharge, with the wording of [S1-SEL-4]: gloo named, 13 rank
  counts $2..64$, the fixed-configuration repeat result and the device-axis result carried in
  the same sentence, and the NCCL algo/proto null explicitly labelled structural. Also update
  **L2** at `main.tex:3313-3318`, which currently says the premise is "argued here ... not
  measured by us" — that sentence becomes false the moment W1 lands and must move with it.
* **W4 (clocked route-load calibration).** Discharge in full; it is the cleanest result in the
  round. Replace **L0b** (`main.tex:3273-3292`) with the text in `EXPERIMENTS_REPORT.md` §3,
  correcting one number: the negative control is *whole-table* corruption, 24/24 PASS→FAIL,
  and the paper must also state that **single-entry** corruption still PASSed on 12 of 24.
  Omitting the 12/24 would be selective reporting of a control's own weakness.
  L0b gets *shorter*, not longer: "we withdraw a band we cannot re-derive" becomes "we measured
  it and it is exactly zero, plus a prologue of one clock per route entry". **Page delta
  negative.**
* **W7 ($\eta$).** **DO NOT DISCHARGE.** See [S4-ETA-1] and [S4-ETA-2]. Either measure $\eta$ in
  RTL cycles on the seven non-power-of-two instances, or leave `\PENDING` resolved as "not
  measured" and keep L1b standing verbatim. The W7 work is not wasted: it belongs in the
  companion as *validation of T10's proof and of the compiler harness* — 1,374 pipeline
  replays confirming the DAG isomorphism survives the real toolchain. That framing is true,
  is worth having, and costs the main paper zero pages.

## PENDING #1, #4, #5 (`main.tex:192`, `:3031`, `:3504`, all W2) — **one result, three
different-length landings. Do not paste the same paragraph three times.**

All three must be filled from the *same* corrected statistic (see [S1-SEL-2]: fp64-only,
$n=20$, geomean **2.57x**, worst **3.91x** — not 2.40x), and none may be filled until the
contention question in [S1-SEL-3] is resolved.

* **`:192` (abstract)** — one clause, no numbers beyond the two that matter, and it must be
  the honest direction: *"...and we measure the software export of the discipline against stock
  NCCL on a two-GPU PCIe node, where it is bitwise reshape-invariant over 2{,}414 configurations
  and costs a geometric mean of 2.6x, worst 3.9x."* The abstract currently promises "the
  headline cost number **and the deployability claim**". **There is no deployability claim
  available.** A 2.6x geomean at $G{=}2$ on PCIe does not license one. Delete that half of the
  promise rather than manufacture an answer to it.
* **`:3031` (discussion)** — the full landing: H1 (2,414 cells, 32 configurations, 10
  non-power-of-two $N$, 7 non-power-of-two $G$), **the negative control** (the paper-as-printed
  index-range construction gives 3 distinct roots and 0 of 13 cells equal to $\Rcan$ at
  $N{=}1000$ and $N{=}1500$ — this is what makes H1 reportable and it must appear), H2 with the
  worst case in the same sentence per the pre-registration, the structural explanation, and the
  conditions block. Also fix the H3 sentence at `:3002` per [S1-SEL-1].
  Estimated +0.5 page. Everything past the first paragraph MOVE-TO-COMPANION.
* **`:3504` (conclusion)** — two sentences, no new numbers. The current text
  ("neither is measured here") becomes "the cut-aligned variant is measured here and is
  invariant; its cost on commodity hardware is reported in §\ref{sec:discussion-pinfbt}".

**Cross-cutting instruction for all three:** `EXPERIMENTS_REPORT.md` §2 condition 3 is a direct
order from the measurement agent — *"This figure must NOT be quoted beside TBIK's <=10% number"*.
`main.tex:3021-3024` currently quotes TBIK's 10% figure with its conditions attached. When the
W2 number lands in the same subsection, those two numbers will sit ~20 lines apart. Either
separate them by a paragraph that states the fabric difference explicitly, or drop the TBIK
figure. Leaving them adjacent invites a referee to compute 2.6/0.1 = 26x and write that in the
review.

---

## [S4-VENUE-1] **The venue-fit objection, and why it changes the council's priority order.** **MAJOR — and it makes W1/W2 non-negotiable**

The paper is titled *"Bitwise-Reproducible Reduction Across **Cluster** Reshape"* and uses the
word "cluster" 25 times. A TPDS referee applies three tests to a parallel-and-distributed-systems
submission: relevance to real clusters, comparison against a baseline a PDS referee accepts, and
evidence the mechanism works outside a simulator. Against the manuscript **as it stands today**:

* **Real clusters: none.** Everything is RTL simulation of a **single-chip** NoC. `main.tex:1486`
  says so in the authors' own words: "The fabric supports a **cluster of up to 4096 PEs in a
  single Verilog instantiation**." That is a chip, not a cluster.
* **A baseline a PDS referee accepts: none.** `main.tex:2291`, `:2626`, `:3307` — no baseline was
  built, no $\eta$ measured. $\Omega$ is the authors' own analytic bound.
* **Outside a simulator: nothing.** L1, `main.tex:3300`: no silicon, no board logs, no timing
  closure.
* And `main.tex:2892-2898` promises engineering outcomes to "`\sprs{}` users" who "reshape their
  cluster ... from $G=2$ to $G=4096$" and get "the same weights" on "new silicon". There are no
  users, no cluster and no silicon.

The pre-registration itself draws the line: *"This is a SINGLE-NODE system: the word 'cluster' is
not licensed by anything measured here, and no result below will be described as one."*
That discipline was applied to the measurements. It has **not** been applied to the manuscript.

**The consequence for the council's decisions, and it is the important one.**
**W1 and W2 are the paper's only contact with a real cluster stack and a real collective.**
Strip them and this is a formal-ABI plus NoC-simulation paper — good work, but a TCAD/TC paper
being sent to TPDS. With them, there is a genuine PDS narrative: production collectives *do*
diverge under reshape (measured, 13 rank counts, 5{,}120 ulp), and the discipline that fixes it
costs ~2.6x on commodity hardware (measured, with the worst case stated).

Therefore:
* **W2 must NOT be moved to the companion**, however attractive under goal 2. It is the paper's
  TPDS licence. MOVE here costs goal 1.
* **[S1-SEL-3] (the contended GPU measurement) is not a hygiene issue.** It is a quality defect
  in the *only* PDS-relevant measurement in the paper. That is why re-measuring on an idle node
  is required rather than optional.
* The "cluster" framing must be tightened wherever it outruns the evidence — in particular
  `main.tex:1486` ("cluster of up to 4096 PEs in a single Verilog instantiation" -> "fabric of
  up to 4096 PEs") and `main.tex:2892-2898` (rewrite in the conditional: "a deployment built on
  this ABI would ..."). Zero pages, and it removes the referee's easiest shot.
  **Do not change the title** — "cluster reshape" is the problem statement, and W1 now measures
  it on a real collective stack.

---

## [S4-ETA-3] W7 built the **one** of the paper's two named baselines that its own theory guarantees will tie, and did not build the other. **MAJOR — and it is the question the advocate cannot answer**

`main.tex:2285-2289` names two baselines:
> "Two such baselines are natural: **ND-Ring**, a linear worker-ring traversal whose reduction
> order follows the physical ring, and **ND-RecDouble**, recursive doubling in
> $\lceil\log_2 G\rceil$ merge stages."

W7 built **ND-RecDouble only** (`W7/v001/nd_tree.py:nd_recdouble`). There is no ND-Ring anywhere
in `w_final/`. And ND-RecDouble is precisely the baseline T10 proves is **DAG-isomorphic to
$\FBT(N)$** whenever $N$ and $G$ are powers of two — which is 31 of the 39 instances. The
measurement was therefore guaranteed, by the paper's own theorem, to return $\eta = 1$ on
three quarters of the suite before it was run.

**Worse: the baseline cannot exercise the cost term the paper calls irreducible.**
`main.tex:2650-2656`, structural term 1:
> "An unconstrained reducer may form partial sums of **arbitrary arity**; at fan-in $k$ its depth
> is $\log_k N$, and at $k=G$ it is $\log_G N$. This term grows with $G$ and is **the irreducible
> core of the ABI's cost**."

`nd_recdouble` is a **binary** tree throughout (`_balanced` pairs adjacent inputs; the merge stage
combines two live partials at a time). It has fan-in 2 everywhere, exactly like $\FBT(N)$. So W7's
$\eta$ **structurally cannot see term 1 at all**, and term 2 (locality regrouping) is the only one
it can see — which is why the answer comes out near 1.

**The referee's question, which neither the paper nor the advocate can answer:**
*"You identify a $\log_2 N$ versus $\log_G N$ depth penalty as the irreducible core of your cost.
You then measure $\eta$ against a binary recursive-doubling tree, which has the same depth as
yours, and report $\eta \approx 1$. What is $\eta$ against a reducer with fan-in greater than two,
or against the ND-Ring baseline you yourself named?"*

The honest answer is "we did not build either", and that answer is fine — **provided the paper
does not report $\eta$ at all**. It stops being fine the moment $\eta \approx 1$ appears as a
result, because then the paper is reporting that its own irreducible cost is zero, measured with
an instrument that cannot detect it.

**Interaction with [S4-ETA-1] and [S4-ETA-2].** These three findings compound. Reporting W7's
$\eta$ means simultaneously: (a) using a diagnostic the Metric Convention excludes, (b) producing
the artefact §\ref{sec:method-nd} pre-emptively disowned, and (c) against a baseline chosen to be
isomorphic. Any one is survivable; all three in the same paragraph is a reject.

**Decision.** If $\eta$ is to be reported at all, the required work is **both**: RTL cycles
(not `sched.makespan`) **and** a baseline that can exercise term 1 — a $k$-ary or ND-Ring reducer
on the same fabric. That is materially more expensive than the seven-instance RTL run in
[S4-ETA-1] and it is a genuine re-derivation of the DMEM single-writer discipline
(`main.tex:2303-2306` says so). **My recommendation is therefore: do NOT report $\eta$.** Keep
L1b verbatim, keep §\ref{sec:method-nd} verbatim, and put W7 in the companion as validation of
T10's isomorphism proof through the real toolchain. That is the cheap option AND the correct one
— the rare case where they coincide.

If the council nonetheless wants a measured cost story for TPDS, the money is in W2, not W7:
a real collective, on real hardware, with a real baseline (`ncclAllReduce`) that a PDS referee
already accepts. Spend the effort on [S1-SEL-3] instead.

---

## [S3-MAXP-3] The budget explanation appears a **third** time, in the Campaign Protocol. **MINOR, moves with [S3-MAXP-2]**

`main.tex:2404-2407`:
> "The one exception is \sv{maxp\_mod\_fat}, dropped from the HW-validated suite: five of its
> $76$ images were attempted and **each exhausted the $8$\,h simulator budget**; the other $71$
> were not run."

Factually accurate — the runs did time out — but it is the third place a reader is told the
budget story that L0 retracts, and the second before they reach L0. Add six words:
"...each exhausted the 8 h simulator budget, for the configuration-interface reason of L0
rather than for size;..."

---

# 6. ATTACKS I COULD NOT SUBSTANTIATE

Listed explicitly so the chair knows where the paper is solid and where a challenger who kept
pushing would be manufacturing objections.

1. **"The invariance result is vacuous / PASS does not mean bit-identical."** Refuted. The
   testbench comparison is an exact 64-bit equality
   (`tb_2a_3e_none.sv:160`), `gen_tables.py:105` asserts a single `EXPECTED` per $N$ across all
   emitted testbenches, and W4's independent re-run reproduces every table root on 1,326
   configurations. See [S4-CLAIM-2].

2. **"The defective GPU-0 metric contaminates the champions / the selection rule."** Refuted by
   direct computation. Every cycle-derived table names `maxpe.csv`; `maxpe.Cycles` equals
   `max(PerfAllGPUs)` on 2,822/2,822; and recomputing per-instance minima from `maxpe.csv`
   reproduces the paper's champion structure. See [S2-PROV-3].

3. **"The 129 non-reproducible rows invalidate the results."** Refuted. 0 of 129 is a published
   champion, and substituting every re-simulated value changes the per-instance minimum on
   0 of 39 instances. CPOP and ClHEFT are 0.0% champion-class members. It is a disclosure
   obligation, not a correctness failure. See [S2-PROV-4].

4. **"The 22 non-settling runs are hidden failures."** Refuted. 21 are `SIM_TB_TIMEOUT_BYPASS`
   with cycle counts of 20,009-20,897, i.e. last retirement plus exactly `WATCHDOG_MAX = 20,000`,
   and 1 is `SIM_WALLCLOCK_TIMEOUT_BYPASS` — precisely as `main.tex:2411-2419` states. I checked
   the error codes and the cycle values in the CSV.

5. **"The selection rule is over-fitted / the leave-one-out is degenerate."** The degeneracy is
   real (the same subset is selected in 39 of 39 folds) and the paper **states it in those
   words** at `main.tex:2812-2814`, then closes the subsection with a paragraph naming the Holm
   failure, the $N$-$G$ confound, the 18 thin cells, the untested $G{=}4096$ point, and
   "none of it transfers to another compiler ... or to MPI or NCCL collectives". I cannot
   construct an objection this paragraph has not already conceded.

6. **"The W2 pinned-FBT invariance result is a tautology like W7's."** Not substantiated. The
   negative control fired (3 of 4 cases, 0 of 13 cells equal to $\Rcan$ at $N{=}1000,1500$), so
   the checker demonstrably can fail. This is a real positive.

7. **"The fp64_add repair invalidates published numbers."** Refuted by execution — I ran both
   acceptance tests. Zero non-positive leaves over $[0,200000)$, zero mixed-sign FADDs over
   $G \in [2,16384]$, zero roots moved, and the mutant negative control detects 2/2. See
   PENDING #2.

8. **"L0b's withdrawal is a cover story."** Refuted. W4 measured the thing: 1,326/1,326 identical
   PASS, root and cycle count, and the only clocked-path effect is a deterministic 10.0 ns per
   route entry (min = max = median). The paper's conservative withdrawal is *understated*
   relative to what is now known.

9. **Anything about $\Omega$, the lower bound.** `main.tex:2264-2278` derives it with the inner
   minimisation over $K$ explained, `main.tex:2270` labels it as bounding *any* schedule, and
   `main.tex:2726-2728` states it is not claimed tight. The footnote at `:2717` even discloses
   two implementation terms not in the printed equation and shows neither is the argmax.
   No attack available.

---

# 7. DECISION LEDGER ENTRIES

```json
[
{"issue":"S4-ETA: report W7 eta as a measured same-fabric overhead",
 "decision":"NO CHANGE (to sec:method-nd and L1b) + MOVE-TO-COMPANION (W7)",
 "reason":"W7 eta is a ratio of sched.makespan values. main.tex:2456 declares makespan 'a diagnostic only'; main.tex:2291-2302 pre-emptively disowns exactly this artefact. Verified: HW cycles / compiler makespan over the paper's own 2,822 released pairs ranges 0.264-9.646, geomean 1.587, only 18.8% within +/-5% of median, and the within-instance spread on all seven non-pow2 instances exceeds the reported 1.026-1.352 effect. The baseline (nd_recdouble) is binary and DAG-isomorphic to FBT on 31/39 instances, so it cannot exercise structural term 1.",
 "cheaper_alternatives_rejected":[
   {"option":"Relabel as 'scheduler-model makespan ratio' and report it","why_rejected":"Still violates the Metric Convention and still reads as 'the ABI is free'; the relabelled quantity does not support any cost sentence."},
   {"option":"Report with a model-error confidence interval","why_rejected":"The interval swallows the entire effect; arithmetically self-defeating."},
   {"option":"Report only the tautology-checked power-of-two half","why_rejected":"A tautology is not a result; a 1,374-comparison denominator on a tautology invites the reviewer to distrust every other denominator."}],
 "required_change":"Leave main.tex:2279-2317 (sec:method-nd) and main.tex:3307-3312 (L1b) exactly as written. Resolve the W7 third of the PENDING at main.tex:2636 as 'not measured'. Move W7 to the companion, framed as: 1,374 pipeline replays confirming T10's DAG isomorphism survives stage-2/3/4 and the scheduler end to end, plus 342 non-isomorphic comparisons reported as model makespan ratios and labelled as such. Delete main.tex:1949-1951's clause about the ND-baseline ratio.",
 "affected":["sec:method-nd","sec:limitations","sec:results-overhead","main.tex:1949","main.tex:2636","companion"],
 "dependencies":["S4-CLAIM-1"],
 "validation":"grep for '\\eta' in main.tex returns only the five existing 'we did not measure it' mentions plus main.tex:2729; scripts/check_consistency.py C5 clears line 2636.",
 "page_delta":"0","acceptance_delta":"large-positive","confidence":"high"},

{"issue":"S1-SEL-2: W2 headline geomean deviates from the pre-registered statistic",
 "decision":"ADD ANALYSIS (recompute; no new measurement)",
 "reason":"PREREGISTRATION.md fixes the headline as 'geomean overhead at G=2, fp64, over the swept sizes'. The reported 2.398 pools 8 fp32 rows with 20 fp64 rows. Recomputed from W2/v004/COST.json: fp64-only geomean 2.569 (n=20); fp64 size sweep 2.268 (n=8); fp64 N-sweep at 128 KiB 2.814 (n=13). The deviation is 0.17x-0.42x in the paper's favour, on the one number the pre-registration existed to protect.",
 "cheaper_alternatives_rejected":[
   {"option":"Keep 2.40x; it is within rounding of 2.57x","why_rejected":"It is not rounding, it is a different denominator, and the pre-registration ships with the artifact. A referee recomputes it in ten lines."},
   {"option":"Quote the 2.27x size sweep as the headline","why_rejected":"Lowest of the four; choosing it after seeing the data is the same offence in the other direction."}],
 "required_change":"Report 'geometric mean 2.57x, best 1.49x, worst 3.91x (n=20, fp64, G=2)' with the two-way decomposition (2.27x size sweep / 2.81x leaf-count sweep) in the same sentence. fp32 arm (2.02x) to the companion. No occurrence of 2.40x anywhere.",
 "affected":["main.tex:192","main.tex:3031","main.tex:3504","W2/RESULT.json","EXPERIMENTS_REPORT.md"],
 "dependencies":["S1-SEL-3"],
 "validation":"Recompute from W2/v004/COST.json filtering backend==nccl, arm==fbt_ch1, dtype==fp64; assert n==20 and geomean==2.569.",
 "page_delta":"0","acceptance_delta":"positive","confidence":"high"},

{"issue":"S1-SEL-3: W2 cost measured under 100% external GPU contention",
 "decision":"ADD EXPERIMENT",
 "reason":"W2/RESULT.json.hardware.contention records that both GPUs were at 100% utilisation under an unrelated user job for the whole window. The co-timed floor probe is 13.4 us against a 41.6 us baseline on 14 of 20 fp64 rows, and the authors' own floor correction moves those rows from 2.4-3.9x to 2.7-5.3x. This is the paper's ONLY real-hardware, real-collective performance measurement, i.e. its entire TPDS relevance (see S4-VENUE-1). A PDS referee rejects performance numbers taken under uncontrolled external load.",
 "cheaper_alternatives_rejected":[
   {"option":"Disclose the contention and quote the number","why_rejected":"Converts 'wrong' into 'acknowledged unusable'. Not better for acceptance."},
   {"option":"Quote overhead_floor_corrected instead","why_rejected":"Higher (to 5.26x) and is a model of the contention, not a measurement without it."},
   {"option":"MOVE W2 to the companion to dodge the issue","why_rejected":"Removes the paper's only contact with a real cluster stack and leaves three PENDING markers, including the abstract, with nothing to become."}],
 "required_change":"Re-run W2/v004's NCCL arm (20 fp64 cells, 15 batched regions each, drive_w2b4.py exists) on an idle node; also run the queued W2/v005 clean gloo re-measurement at G>=24. Report the idle-node numbers as the headline and the contended ones as a supporting robustness note.",
 "affected":["experiments/w_final/W2/v006","main.tex:192","main.tex:3031","main.tex:3504"],
 "dependencies":["S1-SEL-2"],
 "validation":"nvidia-smi shows 0% utilisation from other users for the whole window, logged; floor_us < 5% of stock_us on every cell.",
 "page_delta":"0","acceptance_delta":"large-positive","confidence":"high"},

{"issue":"S3-MAXP: the 39/40 disclosure, its unbacked counterfactual and its two contradicting restatements",
 "decision":"REWRITE (L0) + EDIT (two call-sites)",
 "reason":"Verified first-hand: with a 16-bit adjacency id, xelab exits 0 after 58:28 and 54.8 GB and writes a 2.1 GB database with no xsimk; xsim refuses to start. So 'would have elaborated' is now supported and 'and run' is falsified. Separately, main.tex:2549 and main.tex:2404 both give the reader the wall-clock-budget explanation that L0 itself retracts at main.tex:3229.",
 "cheaper_alternatives_rejected":[
   {"option":"Leave L0; the counterfactual is harmless","why_rejected":"It is the third unbacked behavioural assertion in one manuscript (after the pinned-FBT step 1 and L0b's fidelity band, both already retracted in-text). A referee who spots the pattern discounts every other argued-not-measured claim, including the four structural cost terms."},
   {"option":"Claim the blocker is now removed / 40 of 40 reachable","why_rejected":"Root cause unconfirmed. Exit 0 with missing output is the tool misreporting. A fourth unbacked assertion in the same section would be worse than the first three."}],
 "required_change":"Replace main.tex:3239's counterfactual with the observed W8 result verbatim as drafted in [S3-MAXP-1]. Fix the table note at main.tex:2549-2551 and add six words at main.tex:2404-2407 so all three sites give the configuration-interface reason.",
 "affected":["main.tex:3239","main.tex:2549","main.tex:2404","tab:invariance"],
 "dependencies":[],
 "validation":"grep -n 'simulation budget\\|wall-clock cap' main.tex returns only occurrences that also name the L0 cause; no sentence in main.tex asserts unobserved simulator behaviour.",
 "page_delta":"0","acceptance_delta":"positive","confidence":"high"},

{"issue":"S1-SEL-1: the <=2 load-imbalance bound holds only under LPT",
 "decision":"REMOVE OR NARROW CLAIM",
 "reason":"W2/v002/imbalance.json: contiguous deal reaches 2.48 at (100,62) over the 426 T16 pairs, 2.52 over 1,546, 3.529 over 44,850. LPT never exceeds 2 on any sweep. main.tex:3002-3004 states the bound unconditionally and attributes it to FBT depth-imbalance, which is not the operative cause.",
 "cheaper_alternatives_rejected":[{"option":"Name LPT without the counterexample","why_rejected":"The next question is 'what happens under the obvious deal?', and the answer (2.48) is in the artifact."}],
 "required_change":"Rewrite main.tex:3002-3004 to name the greedy largest-first deal, give the 44,850-pair verification, and state the contiguous counterexample 2.48 at (N,G)=(100,62), noting the frontier assignment does not affect the root.",
 "affected":["main.tex:3002","sec:discussion-pinfbt"],"dependencies":["S1-SEL-2"],
 "validation":"Value matches W2/v002/imbalance.json S1_T16_set_Gle64.","page_delta":"0","acceptance_delta":"positive","confidence":"high"},

{"issue":"S2-PROV-1/2: gen_tables.py bypasses hwdata.select(); invariance.tex was hand-edited and make tables reverts a T03 correction",
 "decision":"CHANGE IMPLEMENTATION",
 "reason":"Verified by regeneration: running scripts/gen_tables.py rewrites 'flagged' to 'detected' in tables/invariance.tex, reinstating the overclaim T03 corrected, and make check reports PASS because the DEFECTIVE guard only catches files stamped by hwdata.select(). The printed numbers are unaffected (both CSVs give identical passing counts) so this is provenance and build integrity, not correctness.",
 "cheaper_alternatives_rejected":[{"option":"Edit the provenance comment by hand","why_rejected":"Machine-generated; it comes back on the next make tables, silently."}],
 "required_change":"In scripts/gen_tables.py: replace HW_CSV with hwdata.select(); change the emitted header 'detected' to 'flagged' and the note to the T03 wording; regenerate. Extend the Makefile check target to fail if any tables/*.tex provenance header names live_hw_results_p1_unified.csv.",
 "affected":["scripts/gen_tables.py","tables/invariance.tex","Makefile"],"dependencies":[],
 "validation":"make tables && git diff tables/invariance.tex is empty; make check fails if the source line is reverted.","page_delta":"0","acceptance_delta":"positive","confidence":"high"},

{"issue":"S2-PROV-4: 129 of 1,326 re-simulated rows do not reproduce maxpe.csv",
 "decision":"CLARIFY LIMITATION",
 "reason":"Verified against maxpe.csv (not just the defective unified.csv as in EXPERIMENTS_REPORT 5b): 129/1,326 mismatch, concentrated in CPOP (75/128) and ClHEFT (52/107), 0 of 1,032 in the other fourteen stage-2 methods. Also verified: 0 of the 129 is a published champion, and substituting all re-simulated values changes 0 of 39 per-instance minima.",
 "cheaper_alternatives_rejected":[{"option":"Say nothing; the numbers do not move","why_rejected":"A referee who touches the artifact finds it, and finding it unlabelled converts a bounded caveat into a credibility event."},
   {"option":"Disclose without the bounding checks","why_rejected":"Reads as an unbounded admission; the two negative results are what make it survivable."}],
 "required_change":"Three to four sentences in sec:limitations naming CPOP and ClHEFT, the 129/1,326 rate, that the reduction root was identical in every re-run pair, and that no champion and no per-instance minimum moves.",
 "affected":["sec:limitations","tab:perinstance_full","tab:selection"],"dependencies":["PENDING#3 W4"],
 "validation":"Re-run the champion-invariance check over W4/v001 jsonl vs maxpe.csv; assert 0 champions and 0 minima moved.","page_delta":"+0.1","acceptance_delta":"positive","confidence":"high"},

{"issue":"PENDING #2 (main.tex:1977, W3 fp64_add)",
 "decision":"EDIT (discharge in full)",
 "reason":"I executed both acceptance tests. tests/fp64/test_sw_rtl_equiv.py: 0/160800 accuracy errors and 0/160800 SW-RTL mismatches; the same test on the pre-fix RTL fails 15,717/62,320, all +1 ulp on effective subtraction. tests/fp64/test_no_published_number_moves.py PASSes with 0 non-positive leaves, 0 mixed-sign FADDs over G in [2,16384], 0 roots moved, and its mutant control detecting 2/2. Independently, W4's 1,326 re-simulations on the repaired RTL reproduce every invariance-table root.",
 "cheaper_alternatives_rejected":[{"option":"Leave the defect described as outstanding in L4","why_rejected":"It is fixed and verified; describing a repaired defect as live understates the artifact and leaves a live PENDING that check_consistency fails on."}],
 "required_change":"Replace main.tex:1977 with the six-line text drafted in section 5 of this report, and update L4 at main.tex:3336-3339 to say the deviation is repaired rather than outstanding.",
 "affected":["main.tex:1977","main.tex:3336","sec:fabric-lim","sec:limitations"],"dependencies":[],
 "validation":"tests/run_all.sh FIX 1 passes; check_consistency C5 clears line 1977.","page_delta":"+0.1","acceptance_delta":"positive","confidence":"high"},

{"issue":"S4-VENUE-1: 'cluster' framing outruns the evidence",
 "decision":"EDIT",
 "reason":"25 uses of 'cluster', including main.tex:1486 'a cluster of up to 4096 PEs in a single Verilog instantiation' (a chip) and main.tex:2892-2898 promising outcomes to users who reshape clusters and migrate to new silicon (no users, no cluster, no silicon). PREREGISTRATION.md itself rules the word unlicensed by the measurements.",
 "cheaper_alternatives_rejected":[{"option":"Change the title","why_rejected":"'Cluster reshape' is the problem statement and W1 now measures it on a real collective stack. Keep it."}],
 "required_change":"main.tex:1486 'cluster' -> 'fabric'. Rewrite main.tex:2892-2898 in the conditional. Leave the title and abstract framing intact.",
 "affected":["main.tex:1486","main.tex:2892"],"dependencies":["PENDING#3 W1"],
 "validation":"No sentence attributes a realised outcome to a deployment that does not exist.","page_delta":"0","acceptance_delta":"positive","confidence":"medium"}
]
```

---

*End of report. Every quantitative statement above was produced by running the artifact; the
commands are reproduced inline so the chair can re-run any of them.*
