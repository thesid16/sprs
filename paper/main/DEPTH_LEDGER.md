# DEPTH LEDGER — middle-ground reconstruction of `main.tex`

**Result: 20 pages.** `make` → 0 undefined refs, 0 undefined citations, 0
undefined control sequences, 0 overfull boxes. `make check` → PASS (6
warnings, all pre-existing in the minimal baseline; no new ones introduced).

Start: `main.tex` was byte-identical to `MINIMAL_REFERENCE.tex` (1512 lines,
13 pages). End: 2320 lines, 20 pages. Nothing was pasted from
`FULL_REFERENCE.tex` unedited except the two TikZ figures, the ISA table and
the prior-art comparison table, whose content is data rather than prose.
Every number is a `data/*.tex` macro or a `tables/*.tex` input. No number was
invented; three claims I drafted were deleted for lack of a source (recorded
below).

---

## 1. Shape: before / after

Source lines per stage, and measured page span in the built PDF (spans are
measured from heading positions in the rendered text; title block 0.49 and
references 0.75 make up the balance to 20.0).

| Stage | full | minimal | **mid** | mid pp | verdict |
|---|---:|---:|---:|---:|---|
| Problem (`sec:intro`) | 319 | 76 | **90** | 0.74 | +roadmap only |
| Background + threat model | 111 | **0** | **94** | 0.42† | **restored** |
| Theory (`sec:abi`) | 887 | 256 | **281** | 2.58† | held flat, +1 remark |
| **Hardware (`sec:fabric`)** | 567 | **74** | **454** | 3.75 | **restored** |
| Software (`sec:compiler`) | 239 | 70 | **96** | 0.82 | +schedule/codegen |
| Method | 237 | 95 | **127** | 1.02 | +accounting, +baseline |
| **Co-run results** | 507 | 391 | **408** | **4.14** | +figure, largest block |
| Analysis (`sec:discussion`) | 86* | **0** | **62** | 0.55 | **restored** |
| Software export (pinned-FBT) | 159* | 122 | **122** | 1.08 | untouched |
| Related work | 171 | 50 | **51** | 0.42 | +table pointer |
| Limitations | 265 | 98 | **135** | 1.38 | +L1b, L6, L10, L11 |
| Conclusion | 83 | 58 | **58** | 0.55 | untouched |
| Appendices | 275 | 70 | **190** | 1.85 | +3, net −4 vs full |

† `Table I` is a full-width float from §II that lands at the top of p3, so
~0.35 pp of the theory span is in fact background's table.

\* `FULL` files pinned-FBT as a subsection of Discussion (159 of its 245
lines); the minimal promoted it to a top-level section and that is correct —
it is a measured result, not commentary. Kept as a section.

**The inversion is corrected.** In the full version theory (887) was 1.75× the
results (507). Here the co-run block — method + results + discussion + the
measured software export — is the largest thing
in the paper by a wide margin — **719 lines, 6.79 measured pages** — and
theory (281 lines, 2.58 pp) is 38% of it. Results alone (408 lines,
**4.14 pp**) is the largest single section in the paper, ahead of hardware
(454 lines but 3.75 pp; 95 of those lines are TikZ).

---

## 2. Stage 1 — Problem (`sec:intro`), 76 → 90

**Restored:** a ten-line roadmap. Nothing else.

**Why:** the minimal intro is already the best-argued page in either version.
It measures the premise instead of asserting it, states the conjunction claim,
and disclaims what is not claimed. A TPDS referee needs none of `FULL`'s
319 lines. The roadmap is restored purely because the paper now has twelve
sections and four appendices; without it the reader cannot see the six-stage
arc, and the arc is the paper's argument.

**Left cut:** `FULL`'s separate `Contributions`, `Non-Goals` and `Roadmap`
subsections (219 lines). The minimal folded C1/C2/C3 into one paragraph and
the non-goals into one sentence, and lost nothing a referee acts on. Restoring
the long C1–C3 would have re-stated the abstract for a third time.

**Tempted and rejected:** `FULL`'s "Two Sources of Non-Determinism" and
"Position: Reduction Order Is an Interface Concern" subsections (~100 lines).
The minimal compressed both into two paragraphs that say the same thing. I
re-read the originals looking for a load-bearing sentence the compression
dropped and did not find one. Rejecting this is the single largest page saving
in the ledger.

---

## 3. Stage 1b — Background and Threat Model, 0 → 94

This was **prima facie wrong in the minimal and is the second-biggest fix.**

**Restored, and why in referee terms:**

1. **`Definition 1` (cross-topology bitwise reproducibility) + the four
   out-of-scope items.** Without this the paper's central claim has no formal
   statement of *what property is being claimed* independent of the mechanism
   that delivers it. A TPDS referee asked to certify "bitwise reproducible"
   will look for exactly this definition, and its absence reads as
   imprecision. It also pre-empts the standard reviewer objection
   ("reproducible against *what*?") in eight lines. Cheap, high leverage.

2. **`Table I`, the prior-art classification.** The paper's whole novelty
   argument is *a conjunction*, not a first. A conjunction claim is
   unverifiable in prose — a referee must hold eight systems and three axes in
   their head at once. The table makes the claim falsifiable in one glance,
   and marks explicitly which columns are *not* ours (`vac.`, the two
   `\checkmark` rows above ours). This is the single highest
   acceptance-per-page item I restored: ~0.35 page for the difference between
   "they claim novelty" and "I can check their novelty".

3. **Where the order comes from** (ring / halving–doubling / double-binary
   tree, τ as a function of (G, topology, message size) never of data). Twelve
   lines. A parallel-and-distributed-systems referee will not accept a paper
   about collective reduction order that never names the collectives whose
   order it is about.

**Left cut:** `FULL`'s worked expansion of the Higham bound under cancellation
(already an equation in the intro), and its restatement of what
`\S sec:related` covers.

**Tempted and rejected:** moving `Table I` to Related Work, where it is
conventionally placed and where the paper's prose already covers the same
rows. Rejected: Related Work sits on page 16, and a referee forms their
novelty judgment on page 2. The ~0.1 page of overlap with §X is the cheapest
insurance in the paper. §X now points at the table rather than re-deriving it.

---

## 4. Stage 2 — Theory (`sec:abi`), 256 → 281

**Deliberately held almost flat.** The correction this exercise exists to make
is that theory outgrew results. Theory is now 281 lines against 408 for
results and 719 for the co-run block. Only one thing was added.

**Restored:** `Remark 1` — the `C-mem` margin and what lies past it. Twenty
lines. This is the constructed counterexample where **Claim 1 fails silently**:
FBT(512) at G=2, peak occupancy 522 of 512 slots, terminates normally with no
`P_ERROR` and returns *two different wrong roots* under two packet-delivery
orders.

**Why:** a referee's first instinct on an invariance claim is to look for its
boundary. A paper that finds its own boundary, exhibits it, and shows the
emitter now refuses such an image is materially more credible than one that
states a hypothesis and moves on. It also converts `C-mem` from a bullet in an
assumption list into a live engineering constraint with a measured margin of
21 slots — which is thin, and saying so is worth more than hiding it. Every
number is in `data/claim_macros.tex`.

**Left cut (606 lines of `FULL` theory, and I would cut them again):**

- The full `\begin{description}` bodies of all fifteen assumptions
  (~240 lines inline). They remain in Appendix A in the minimal's compressed
  form. In-body, they stop the argument dead for two pages.
- `Supporting Arguments` A1–A4 (191 lines). The minimal replaced them with the
  four-step "How the hypotheses carry the claim" paragraph, which is the same
  argument at 1/8 the length and is *better* — it names which of the eleven
  hypotheses does which work, which the A1–A4 form obscured.
- `Mechanisation and Runtime Checks` (64 lines), including the Alloy/Kami
  "path to mechanisation". **No evidence exists for it**; it is future work
  presented as an artefact. Cutting it is a claim reduction, not a page saving.
- `Edge Cases` (N=0, N=1, integer reductions). N=0/N=1 are trivial; the
  integer-reduction case now lives in Discussion where it belongs.

**Tempted and rejected:** `Remark: why address reuse does not break the gate`
(56 lines in `FULL`, in the theory section). This is genuinely load-bearing —
it is the reason `F-gci-haz` and `F-arb` are hypotheses of Claim 1 at all. I
restored it, **but into the hardware section** (§IV-D), not theory, in ~26
lines. It is a fact about the pipeline and the allocator, not about the
contract, and placing it in theory is what made theory look bigger than the
machine.

---

## 5. Stage 3 — Hardware (`sec:fabric`), 74 → 454. **The primary brief.**

I verified the 13%-retention claim and it is worse than it looks: the minimal
kept four `\emph{}`-led paragraphs and no figure, no table, no resource
number, no deadlock statement, and no account of the adder defect. For a
manuscript submitted to *IEEE Transactions on Parallel and Distributed
Systems* whose contribution is a **compiler/fabric** ABI, that is not a
compressed stage — it is a missing one. A PDS referee reading it would find
the fabric asserted rather than described, and there is no route to
first-round acceptance from there.

**Restored, in referee terms:**

| Restored | Cost | Why a TPDS referee needs it |
|---|---|---|
| `Fig. 2` PE microarchitecture | ~0.35 pp | The paper had **zero figures**. The scoreboard-plus-three-write-agents structure is the mechanism of the whole claim; it is a diagram, and prose cannot substitute. Scaled to 0.72\textwidth (from `FULL`'s full width) — same legibility at body-text size, −0.13 pp. |
| `Fig. 1` packet format | ~0.15 pp | Fixes the VC-steering-bit story visually: bit [64] is read by the router and written as a constant, so cycle counts are value-agnostic *by construction*. That is a determinism argument, not decoration. |
| `Table II` ISA + 64-bit instruction word | ~0.20 pp | "Four opcodes" is a claim about auditability. A referee must be able to check that the ISA cannot express an operand rebinding. Also carries the point that **egress port is not an instruction field** — the single design decision that makes topology data. |
| §IV-D *Why the scoreboard alone is not enough* | ~0.45 pp | **The strongest hardware argument in the paper and it had been deleted entirely.** 397,422 measured reuse events, every configuration recycles, two exhaustive cases (31.3% / 68.7%), and the 35.4% of `GENERATE`s into a recycled slot for which the scoreboard *provably cannot* be the protection. This is what makes `F-gci-haz` and `F-arb` hypotheses of Claim 1 rather than liveness trivia. A referee who does not see this reads the fabric as "it has a scoreboard, therefore it is correct". |
| §IV-F flow control, routing, **deadlock** | ~0.45 pp | Non-negotiable for this venue. The CDG is **cyclic on every ring and every torus instance** (length G; 6–32) and acyclic on the other four. A PDS referee *will* ask about deadlock freedom on a torus. Answering it with a measurement, a disclaimer, and the fail-stop containment argument is a strength; silence is a reject. |
| §IV-G resource envelope + `Table III` | ~0.35 pp | A hardware paper without an area/storage number is not evaluable. Radix 3–66, fat-tree router 20× a mesh router, 56% crossbar, and the honest statement that a flat crossbar is the wrong structure at P=66. Restored as text-plus-one-table; `FULL`'s second table (`tables/radix.tex`) folded into one sentence. |
| §IV-E three-detector fail-stop | ~0.15 pp | Property 2 is asserted in the minimal; here it is grounded in the actual detectors (watchdog 20,000 / stall timer 10,000 / opcode trap) and the closed set of three termination outcomes, with the one construction that defeats it named. |
| §IV-H the adder defect and its repair | ~0.35 pp | This is the paper's most transferable engineering finding and it existed only as a limitation note. The three-edit repair, and specifically that the *obvious one-line fix leaves a −1 ulp residual on 1.3% of effective subtractions*, is the kind of result a hardware referee remembers. It also makes L13's method critique concrete rather than abstract. |
| §IV-I what the fabric does not do | ~0.20 pp | Head-of-line blocking, single clock domain, and "validated at one point of a parameterised design — the unused halves are where the defects are". Credibility per line is very high here. |

**Left cut from `FULL`'s fabric:**

- The `Design Goals` subsection — merged into the section opener.
- Line-number citations to `.sv` files (`noc_router.sv:118`, etc.). ~40
  occurrences. They belong in an artefact, not a journal page.
- `tables/radix.tex` — six rows whose content is four numbers already in the
  prose. −0.15 pp for zero information.
- The round-robin allocation guard paragraph — a fairness property with no
  bearing on the bit result and no measurement attached.
- The full three-variant sweep breakdown of the partial adder repair beyond
  the one summary sentence.

**Tempted and rejected:**

- **`FULL`'s compiler-pipeline TikZ diagram** (S0→S1→S2→S3→S6 with the three
  unused passes in a dashed box). Attractive, and it makes the "three passes
  produced none of these results" point visually. Rejected: ~0.3 page to
  render five boxes that the first paragraph of §V already lists, and it
  would have pushed the software stage past the hardware stage in page terms
  without adding an argument. The page went to §IV-D instead.
- **Restoring `MAX_ROUTERS`/`MAX_PORTS` vestigial-parameter discussion in
  full.** Kept to one sentence. A reader auditing the RTL for a cluster-size
  bound will find those declarations first and be misled, so the sentence
  earns itself; a paragraph does not.
- **Pseudocode for the DMEM allocator.** `FULL` explicitly defers it to the
  companion, and that is right. The three properties of the walk are what
  carry `C-sw`, and they are prose.

---

## 6. Stage 4 — Software (`sec:compiler`), 70 → 96

**Restored:** schedule construction (the three per-PE clocks; the GCI constant
taken from the RTL rather than fitted, and the observation that the *same*
constant reappears as the GCI term of Ω and as the dominant cost term at high
N/G), plus the one source line that realises `C-bind`.

**Why:** the minimal's compiler section proves that one pass *constructs*
`C-sw`, which is the right emphasis, but it never shows the compiler and the
fabric agreeing on a number. The `gci_latency + 2` constant is that agreement,
and it is the seam between stage 3 and stage 4 of the author's arc. The
`child_addrs = [addr_map[gpu][c] for c in tree.children(v)]` line is
Proposition 1 in code: a referee can see in one line that μ and the routing
tables are not in scope where operands are bound.

**Left cut:** `FULL`'s `Orthogonality of the Compiler Variation Space`
subsection (21 lines) — it restates Proposition 1 and the results section
already measures the collapse. `Codegen` peephole detail. Line-number
citations.

**Tempted and rejected:** typesetting the operand-binding line as a proper
`lstlisting` code block. That would need `\usepackage{listings}` and a float,
costing ~0.1 page for one line of Python. Inlined as `\texttt{}` instead —
same evidence, no float.

---

## 7. Stage 5a — Method, 95 → 127

**Restored:** (a) the campaign's core-hour accounting split three ways
(1,003.3 total = 821.5 passing + 122.9 non-settling + 58.9 on the instance
that never settled), and the IMEM feasibility caveat (278 of 7,200
compilations exceed the reference budget, 113 of them among the validated
set); (b) the *named* non-deterministic baselines ND-Ring and ND-RecDouble
and a concrete account of why building them is not a small change.

**Why (b) especially:** "we did not build a baseline" is the single most
likely reject trigger at TPDS. The minimal says it plainly, which is right,
but a bare refusal reads as evasion. Naming the two baselines, stating that
relaxing `C-bind` forces a re-derivation of the allocator's single-writer
discipline and the scoreboard gating, and stating that an unoptimised
baseline would measure *our relative implementation effort* rather than the
ABI, converts a refusal into a reasoned scope decision. Fifteen lines for the
paper's most exposed flank.

**Left cut:** the `SW-FixedTree` third baseline (17 lines in `FULL`). It
promises "the analytical overhead of (b) as an upper bound" and cross-refers
to an appendix that contains no such number in this release. It is an
unsupported claim; the pinned-FBT export supersedes it and *is* measured. Cut,
not compressed.

**Tempted and rejected:** the full six-term informal gloss of Ω. The minimal
compressed it to one clause and kept the two structurally essential points —
that two terms shrink in K so a valid bound must minimise over K, and that Ω
bounds non-deterministic schedules too, so it is not a determinism
denominator. Those two are the whole argument.

---

## 8. Stage 5b — Co-run results, 391 → 408. **Largest block, as required.**

The minimal retained 77% here and its judgment was sound; I added one thing
and one pointer.

**Restored:** `Fig. 3`, cycles/Ω per instance against leaf count, six
topologies (`figures/omega_by_instance.tex`, already generated, previously
unused by either version's build).

**Why:** the surrounding text makes an *additive* argument — the absolute
distance from Ω is near-constant (median 96 cycles, IQR [60,117]) across Ω
spanning 13 to 384, so relative efficiency improves with scale. That argument
is invisible in `Table V`, which reports ratios. A scatter is the correct
instrument and it already exists. It also gives the results section a visual
anchor, which matters when a referee skims.

**Also added:** a two-clause pointer from §VII-E to the new `Table VII`
(champion-class membership), so the withdrawn winner-distribution has a
tie-invariant replacement the reader can actually see.

**Left cut:** `FULL`'s `No Silicon Measurements` subsection — the minimal
folded it into the invariance discussion, which is the right place (it scopes
that result, it is not a result of its own).

**Tempted and rejected:** `tables/nginflection.tex` and
`figures/ng_inflection.tex`. Both are generated and both build. **Both belong
to the prediction the paper withdraws as circular.** Restoring them would
re-introduce a refuted reading in visual form. Not restored, and the
withdrawal text stays.

---

## 9. Stage 5c — Analysis (`sec:discussion`), 0 → 62

The other prima facie error: the author's arc says "results *and analysis*",
and the analysis was deleted wholesale.

**Restored, three paragraphs:**

1. *What the ABI buys, and where the work went* — the interface observation,
   and the statement that every design decision downstream is either
   discharging a `C-*` or establishing an `F-*`. Compressed from `FULL`'s two
   paragraphs, with the marketing register removed and the two measurement
   pointers (§VII-A, §VII-B) added.
2. *When not to use it* — three regimes, two of them consequences of the
   contract rather than of the implementation. **A referee will not accept an
   unbounded applicability claim.** This is the paragraph that converts the
   unfavourable pinned-FBT cost from an embarrassment into a design rule.
3. *What generalises, and what a real workload would need* — operator
   generalisation (structural, no measurement claimed) and, more importantly,
   **the tensor extension**. This is the question a PDS referee asks first:
   real all-reduce is over tensors of millions of elements. The honest answer
   is that the extension is element-wise, the invariant is per element, and
   *our evaluation is at D = 1*; a tensor-rate implementation is engineering
   we have not done. Saying so is worth more than leaving the referee to
   discover it.

**Left cut:** `FULL`'s non-reduction-collective paragraph is kept but reduced
to two clauses; the "replay debugging / regression testing / same weights
three months later" payoff list is compressed from a paragraph to one
sentence.

**Tempted and rejected:** re-stating the interoperability adapter as a
contribution ("a direction we sketch"). No evidence, no design. It is stated
as a requirement on such a deployment, not as our work.

---

## 10. Related work, 50 → 51

One clause added, pointing at `Table I`. The SHARP / SwitchML / Groq
paragraph is untouched, as required — it is the paragraph that discharges the
in-network-reduction novelty obligation, and it does so by conceding what
those systems do better (SHARP prices the discipline structurally; we claim
no advantage in speed or cost of the reduction itself) and naming exactly
where the index differs (per-deployment mapping vs. per-N).

---

## 11. Limitations, 98 → 135

**Restored, four items:**

- **L1b — no measured η.** Promoted out of the L1 grab-bag into its own item
  and labelled *the largest gap in the evaluation and the first thing we
  would close*. A referee who finds this stated plainly is far less likely to
  treat it as concealment; buried in a list of eleven clauses, it looks like
  it was hoped to pass unnoticed.
- **L6 — the `C-mem` margin is thin and past it the failure is silent.**
  Cross-refers to `Remark 1`. Margin: 21 slots.
- **L10 — no deadlock-freedom property.** The measured CDG cycles, no escape
  channel, and the fail-stop containment. Mandatory at this venue.
- **L11 — mutation testing covers two classes**, so the detection figures are
  a lower bound on harness sensitivity, not a characterisation of it.

**Also fixed:** the minimal's L1 contained two dangling references to items
`L9` and `L12` that do not exist in this version's numbering. Repointed to
§IV-I and removed respectively.

**Left cut:** `FULL`'s L0c (combinational FADD), L0d (one reduction per
program), L2, L3, L4, L5, L7, L8, L9, L12 as separate headed items — all ten
are present, compressed, inside L1 or inside the fabric/method sections that
own them. Ten headed items whose bodies are one sentence each read as padding;
a referee counts limitations sections by weight, not by numbering.

**Tempted and rejected:** restoring L4's full account of the adder deviation.
Its content now lives in §IV-H where the engineering belongs, and L13 already
carries the method lesson. Duplicating it a third time would be the paper
apologising twice for a defect that moves no reported number.

---

## 12. Appendices, 70 → 190 (`FULL` had 275 across seven)

**Kept:** Appendix A, the fifteen assumptions (the minimal's own invention,
and a good one — it lets §III state the partition in eight lines while
remaining checkable).

**Restored, three:**

- **B — worked invariance example at N = 4.** ~34 lines. The single most
  checkable thing in the paper: two topologies, the emitted instructions, and
  the explicit list of what changes (PE count, SENDs, cycles, routers) versus
  what does not (the operand pair, the commit order, the 64 bits). A referee
  who wants to believe Claim 1 without reading the RTL can verify the
  mechanism here in two minutes. Highest verification-per-page item in the
  paper.
- **C — assignment-algorithm catalogue (`Table VII`) + suite coverage
  (`Table VIII`).** The selection rule recommends 4 of 18 algorithms; a
  referee must be able to see the 18 and to see that the recommendation is
  champion-class *membership*, which is tie-invariant, rather than the winner
  count the paper withdraws. `Table VIII` makes L5's "thin cells" concrete —
  18 of 23 populated cells hold ≤2 instances — which is the honest basis for
  refusing every cell-level recommendation.
- **D — reproducibility.** Four short paragraphs. TPDS weighs artefact
  description; more importantly this is where the paper records, in the
  reproducibility appendix itself, that **the oracle is a transcription of the
  RTL and not an independent model**. Putting that disclosure in the checklist
  rather than only in L13 is the more honest placement.

**Left cut, and I would cut them again:**

- `app:bias` + `tables/selbias.tex` — the leakage number (median 20% of the
  true top-15 missed at K=15) is already quoted inline in §VI as the reason no
  shortlist was used. The table adds two more cutoffs. → companion.
- `app:perinstance` + `tables/perinstance_full.tex` — a 39-row per-instance
  dump. `Fig. 3` now shows the same data with the argument visible. → companion.
- `tables/walltime.tex` — 39 rows of xsim wall-clock reconciling to totals
  already stated in §VII and §VI. → companion.
- `app:isa` as a separate appendix — its content (the 64-bit instruction word
  and the egress-port argument) was *promoted into §IV-B*, where it is part of
  the hardware stage rather than a footnote to it. Net: same content, one
  fewer appendix header.

**Tempted and rejected:** `app:repro`'s SHA-256 of the leaf-value generator
source. Two lines of hex that no referee will check and that the artefact
carries anyway.

---

## 13. Three claims I drafted and deleted for lack of a source

Recorded because the brief asks for the rejections, and because these are the
places the reconstruction could have gone wrong.

1. **"an image compiled for a mesh is byte-identical to one compiled for a
   torus at the same (N, G, α)."** Drafted in §IV-B as a consequence of egress
   port not being an instruction field. **False, and the paper's own data says
   so**: NOP padding is placed from the cost model's hop counts, which depend
   on topology. Replaced with the supportable statement — the instruction
   stream names logical destinations, and only the adjacency and routing
   tables name the network.
2. **"its data is ready `gci_latency + 2 = 6` cycles later"** written so that
   the RTL latency and the compiler's *minimum emitted gap* — both 6 — were
   identified with each other. They are separate quantities that happen to
   coincide. Rewritten to state the latency and then note that the
   `6⌈N/G⌉` it induces is the Ω term, without asserting the identity.
3. **The `SW-FixedTree` analytical upper bound** (§7 above). `FULL` cites an
   appendix for a number that does not exist in this release. Cut rather than
   carried forward.

## 14. What is still missing, and why I did not manufacture it

The paper has two real gaps and both are now stated in their own headed items
rather than buried: **no measured same-fabric overhead η** (L1b) and **no
silicon** (L1, §VII-B). Neither can be closed by restoring text, and neither
was closed by inventing a number — `FULL` itself records that the analytical η
it built returns ≈1 on every instance because the cost model is structurally
blind to operand pairing, and reporting that number would read as evidence
that the ABI is free. The correct move, which both reference versions already
make and which this one makes more visibly, is to price the ABI structurally,
state the four terms, measure the one that is ours (GCI serialisation: ≥43% of
champion makespan at N/G > 8, 64–74% at N/G ≥ 32), and name the missing
baseline as the first thing to close. Restoring text cannot fix a missing
experiment, and pretending otherwise would have been the one way to make this
reconstruction worse than the minimal it started from.

---

## 15. Verification record

```
make                 → built main.pdf (20 pages)
                       undefined refs: 0   undefined citations: 0   overfull boxes: 0
grep "Undefined control sequence" build.log → 0
make check           → PASS: no placeholders, no undefined refs or citations,
                              numbers consistent
                       (6 warnings, identical to the minimal baseline's 6)
```

Load-bearing items confirmed present in the built PDF: Claim 1 (§III-D);
Property 1, the fail-stop property (§III-D); the cross-topology invariance
result and `Table IV` (§VII-B); the selection rule with its held-out interval
`[1.0025, 1.0885]` (§VII-F); the pinned-FBT cost `2.57×` with the
provisional/GPU-contention caveat (§IX, §XII); the 39-of-40 disclosure (§XI,
L0); the SHARP / SwitchML / Groq prior-art paragraph (§X), unmodified.
