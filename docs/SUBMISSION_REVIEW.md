# SUBMISSION REVIEW — `main.tex`, TPDS first-submission pass

**Build state (verified by execution, `make` + `make check` on a clean tree):**

```
make          → built main.pdf (20 pages)
                undefined refs: 0   undefined citations: 0   overfull boxes: 0
grep build.log: Overfull 0 · Undefined control sequence 0 · Reference undefined 0
                Citation undefined 0 · \todo{} in main.tex 0
make check    → PASS (6 warnings, byte-identical to the pre-existing baseline six;
                no new warning introduced)
```

Start: 2,336 lines / 21 pages-worth of material rendering at 20 pages.
End: 2,297 lines / 20 pages. Backup at
`/home/rohit/sprs-fix/paper_mid/main.tex.bak.council-20260829-052212`.

---

## 1. What I judged was most threatening acceptance, and what I did

I read this as an Associate Editor and three referees at TPDS, not as a
page-count exercise. The science was already in good shape — the fourteen-reviewer
panel's critical themes (T01 headline claim, T02 coverage, T03 Property 2, T04
pipeline-as-run, T05 protocol, T08 circular prediction, T12 phantom verification
artefacts, T15 tie sets, T16 pinned-FBT) are all discharged in the draft I
received. What was wrong was **shape and framing**, and those are what decide a
first-turn verdict.

### 1.1 The paper read as a NoC-simulator paper submitted to a parallel-and-distributed venue

A referee skimming in reading order met: three pages of unsynthesised
SystemVerilog microarchitecture, then a four-page simulator campaign, then a
Discussion — and only *after* the Discussion, at §IX, the one section containing
real GPUs, real NCCL and a real cost number. The paper's TPDS-facing evidence was
positionally peripheral to its own argument.

**Fix.** Moved `sec:pinfbt` ahead of `sec:discussion` (now §VIII and §IX), and
retitled it *Exporting the ABI to Production Collectives*. The measured block is
now contiguous — §VI methodology, §VII fabric campaign, §VIII production
collectives, §IX analysis — which is also exactly the arc you specified. Zero
pages; large effect on what a skimming referee concludes the paper is about.

Measured final shape (page spans in the built PDF): co-run block §VI–§IX ≈ **6.8
pages**, fabric §IV ≈ 3.2, theory §III ≈ 2.4, compiler §V ≈ 1.0. The results
block is by a wide margin the largest thing in the paper, as intended.

### 1.2 "No baseline" — the standard systems-venue reject line — was answered in only one of the two regimes a TPDS referee thinks in

§VI's settled η argument is correct and I did not touch it: two-input `COMPUTE`
forces depth ≥ depth of FBT(N), term ≤ 0 on 39/39; ND-RecDouble is DAG-isomorphic
to the ABI schedule on 88/88 power-of-two pairs; η = 1 by construction on 31 of
39. But a collectives referee's instinctive objection is *"ring all-reduce is
bandwidth-optimal, so your tree does cost something"* — and the paper never said
that this is a **depth** argument valid in the scalar-per-leaf regime the fabric
occupies, nor that the bandwidth-regime cost is measured elsewhere in the same
paper.

**Fix (new, §VI).** A short paragraph stating that the argument is about depth;
that depth binds at D = 1; that at large message size the other term binds and
there a pinned tree does cost something; and that §VIII measures exactly that
against stock `ncclAllReduce`, finding a factor of about two at G = 2 that is
algorithmic. Closing sentence: *"The two regimes are bounded by different terms
and are priced here by different instruments — a construction argument for the
first, a measurement on real collectives for the second — and neither result is
offered as evidence for the other."*

This is the single highest-value edit in the pass. It converts the paper's most
exposed flank from an admission into a two-instrument pricing story, using only
numbers already in the manuscript.

### 1.3 The headline invariance result was stated only in its oracle-dependent form

§VII-B said every settled run matched "the canonical root Rcanonical(N,L) **the
software oracle predicts**", and L13/Appendix C concede the oracle is a
transcription of the RTL rather than an independent model. A referee who joins
those two sentences writes the reject. That is a self-administered wound, because
the *weaker and stronger-standing* reading is available for free.

**Fix (new, §VII-B).** The testbench's `EXPECTED` constant is a function of N and
the opcode alone — it names no G, topology, assignment, mapping or schedule. A
`PASS` therefore certifies the run's root equals a value fixed by N, so **every
settled run at a given leaf count produced the same 64-bit root as every other**,
across all its (G, topology) points and all its compiler triples. That is
Definition 1 verbatim and it does not depend on oracle independence at all. What
does depend on the oracle is the stronger reading — that the shared root is the
*correct* Rcanonical. The paper now reports both and keeps them apart.

No new data; it is a logical consequence of what was already reported, and it
neutralises the two most-corroborated critical themes (T01, T07) simultaneously.

### 1.4 The bibliography knew about the 2024–25 determinism literature but never cited it

`references.bib` contained `shanmugavelu2024`, `repdl2025`, `ahrens2020reproducible`,
`balaji2013reproducible`, `dally1987deadlock` and `devietti2009dmp` — all
uncited. For a 2026 submission on reproducible reduction, *not* citing
Shanmugavelu et al. (FP non-associativity in HPC/DL) or Balaji & Kimpe (MPI
reduction reproducibility) is an unforced error a referee in the area notices in
thirty seconds. Likewise, discussing a channel-dependency graph without Dally &
Seitz.

**Fix.** Six citations added at the natural places: `shanmugavelu2024` (§I,
premise), `balaji2013reproducible` (§II, where the order comes from),
`dally1987deadlock` (§IV-F, CDG acyclicity), `ahrens2020reproducible` (§X,
reproducible arithmetic), `repdl2025` (§X, fixed-order schemes),
`devietti2009dmp` (§X, a new clause on hardware-enforced determinism in
shared-memory multiprocessing, positioning it as fixing thread interleaving
rather than arithmetic order). Cost ≈ 18 lines of bibliography, which I paid for
elsewhere.

### 1.5 C1 handed the referee the reject line without saying where the work is

The old text: *"We claim the framing, not the difficulty — once operand binding
is a function of tree-node identity alone, invariance follows by unwinding
definitions."* Honest, and I kept it. But incomplete, and a hostile referee
quotes it verbatim as grounds.

**Fix.** Same honesty, plus one sentence naming the three places the proof does
not reach: building a fabric that enforces the binding with no silently-wrong
failure mode; establishing that every remaining degree of freedom in a real
compiler is orthogonal to it; and carrying the discipline onto a production
collective and paying its price. Those three are what the rest of the paper
actually is.

### 1.6 The abstract was ~400 words with cross-references in it

IEEE abstracts must be self-contained; this one carried `Claim~\ref{claim:1}` and
`Property~\ref{prop:2}`. It also sold "the compiler's ≈22,000-point configuration
space", which T02 identified as the single easiest overstatement for a referee to
verify in ten minutes.

**Fix.** Rewritten: cross-references removed, the 22,000 figure removed (a claim
*reduction* — the coverage story now lives in §VI and L0a where it is stated
exactly), the conjunction enumerated once instead of twice, the selection-rule
block compressed from four sentences to one, and a closing clause added that
about a factor of two of the 2.57× is the algorithmic price of the pinned tree
and the remainder an export artefact — so the abstract's last impression is a
priced result rather than a bad ratio.

---

## 2. Every substantive change, in referee terms

### Additions (each justified by a referee question it answers)

| # | Change | Why a TPDS referee needs it | Cost |
|---|---|---|---|
| A1 | §VI: the depth-vs-bandwidth regime bridge (§1.2 above) | Answers "you have no baseline" and "a ring is bandwidth-optimal" in one place | +0.07 pp |
| A2 | §VII-B: the oracle-independent reading (§1.3) | Answers "your zero-divergence column is the oracle's own expectation" | +0.09 pp |
| A3 | **Table III**, the compiler-pass table (§V): 8 passes × {alternatives, status in the reported campaign} | T04 was flagged critical by 7 reviewers in 6 views — *"the paper describes a pipeline that did not run"*. Prose said it; a table makes it checkable at a glance, and it gives the software stage a visible artefact | +0.13 pp |
| A4 | Six citations (§1.4) | Recency and completeness of positioning | +0.15 pp (bib) |
| A5 | C1 rewritten (§1.5) | Removes a quotable reject line without losing the honesty | +0.03 pp |
| A6 | Appendix C: artefact-availability sentence naming compiler, testbench generator, mutation harness, pinned-FBT implementation and result files, with a deposit commitment | TPDS weighs reproducibility; the paper had no availability statement anywhere | +0.02 pp |
| A7 | §VII opening: pointer to Appendix C (which was **unreferenced from the body** — an orphaned appendix) | Editorial defect; a referee should be told the artefact description exists | +0.01 pp |
| A8 | §VII-F: one clause reconciling Table VI's "Regime" rows with the text's "a regime map is actively harmful" | Table VI's generated caption says *"For each regime, the S2 algorithms a practitioner should run"* while the text says regime maps are harmful. A referee reads that as the paper contradicting its own table. The clause states that the row to adopt is the unconditional default and the restricted rows are shown for completeness | +0.02 pp |

I could not edit `tables/selection.tex` (generated; `verify_tables.py` enforces
byte-equality), so A8 is the correct fix available from `main.tex`.

### Removals

| # | Removed | Why it costs nothing | Saving |
|---|---|---|---|
| R1 | The packet-format TikZ figure | Its one load-bearing fact — bit [64] is a VC selector written as a constant, so cycle counts are value-agnostic by construction — is a sentence, now folded into §IV-B prose, and the VC0 fact is stated again in §IV-F. A referee does not need a picture of a 96-bit field layout | −0.15 pp |
| R2 | The resource-envelope table (was Table III) | Per-component storage-equivalent bit counts from a prototype with **no synthesis, no place-and-route, no power**. All headline numbers (750,976 vs 37,728 bits, 20×, 56 % crossbar, 147 vs 3002.3 Mbit, 65,536 bits/PE, 256 Mbit) are retained in prose, and the exclusion list moved into the prose too. It supported no claim in the paper and invited *"you present a resource table with no P&R data"* | −0.20 pp |
| R3 | Appendix B, the worked N = 4 invariance example | Two reasons. (i) Its content is stated three times already: Def. 4 (operand binding), Prop. 1's structural argument, and §V's `child_addrs = [addr_map[gpu][c] for c in tree.children(v)]` line. (ii) More importantly, it spends half a page *dramatising how easy the central claim is* in a paper whose main positioning risk is "near-definitional". The prior reconstruction rated it highest verification-per-page; I disagree on the second ground | −0.45 pp |
| R4 | §IV-B identity-slot elaboration retained, §IV-I clock-domain item compressed to one sentence | The `DMEM[0]` note duplicates §III-C; the clock-domain item was four lines for a point no referee weighs | −0.05 pp |

### Compressions (no evidence removed; duplication and narration removed)

- **§IV-G resource envelope**: three paragraphs → two; every macro retained.
- **§VII-D "A prediction we withdraw"** → *"The obvious test of term 3 is circular,
  and we withdraw it"*. Kept ρ, p, and the mechanism-free null model — those are
  the negative result. Dropped the "an earlier version tested…" narration: this
  is a first submission, the withdrawn banding is not in the arXiv companion
  (I checked `snapshot/companion/main.tex`: no "knee", no "inflection"), so
  there is nothing public to protect against.
- **§VII-D topology-ordering caveat**: kept the three disqualifying facts, dropped
  the withdrawal narration for the same reason.
- **§VII-B re-execution paragraph** and **L0b**: were near-duplicates. §VII-B now
  owns the root-provenance disclosure (released file has verdicts, not root
  words; current RTL, not the exact tree), L0b owns the bypass-fidelity result.
- **L6** and **L10**: were re-statements of Remark 1 and §IV-F. Now cross-refer.
- **§VII-E**: the winner-table withdrawal narration compressed ~40 %. Kept the
  tie-set numbers, kept the arrival-order confession (it is a genuine and
  disarming disclosure and the generated `tables/catalogue.tex` caption depends
  on the withdrawal being stated), dropped the rhetorical flourish.
- **§VII-F closing paragraph**: the N/G confound and thin-cell numbers now
  cross-refer to L5 instead of repeating it — L5 is the item you restored for
  exactly this purpose.
- **§VI "the baseline we did not build"** second paragraph: with η = 1 stated as a
  theorem on 31/39, the long justification for *not* building ND-Ring/ND-RecDouble
  reads as apology. Recast around the actual residual — the 8 non-power-of-two
  instances — which is stronger and shorter.
- **§V repair pass**, **§VII opening**, **§IX operator-generalisation list**,
  **§IV-H repair mechanism**, **Conclusion**, **Appendix B prose**, **Appendix C
  oracle paragraph**: tightened, no numbers lost.

### Bugs found and fixed (both would have shipped)

1. `\RadixMaxInst ---` in §IV-G: LaTeX swallows the space after a control word, so
   this typeset as `maxp_mod_fat—the regime`. Fixed to `\RadixMaxInst{} ---`.
   I ran a systematic scan of all 200+ `data/*.tex` macros for the same pattern;
   this was the only live instance (the other three hits are inside math mode).
2. My own §V lead sentence began with `\StagesRun{}` = "five", so it typeset as
   *"…reported here. five did; three…"*. Rewritten to keep the macro mid-sentence.
3. Conclusion still said the ABI is priced "structurally rather than against a
   non-deterministic baseline, which remains the principal open item" — that
   predates the η theorem. Now: priced by construction where the ABI fixes the
   schedule and by measurement where it does not, with the non-power-of-two
   residual named as the open item. This matters: the old wording contradicted
   §VI and L1b.

---

## 3. What I was tempted to change and deliberately did not

- **Table I (prior-art classification), a full-width `table*` costing ≈0.35 pp.**
  It is the most expensive single exhibit and the conventional advice is to move
  it to Related Work on page 16. Kept where it is. The novelty claim is a
  *conjunction*, a conjunction is unverifiable in prose, and a referee forms
  their novelty judgment on page 2. T06 — novelty contradicted by ReproBLAS /
  ExBLAS / oneMKL CNR — is the theme with the highest desk-reject risk in the
  whole docket, and this table is what discharges it.
- **Fig. 1 (PE microarchitecture), a full-width `figure*` costing ≈0.35 pp.**
  It is the mechanism of Claim 1 and, after R1, the paper's only structural
  diagram. Squeezing it to one column would make it illegible. Kept.
- **Fig. 2 (`omega_by_instance`).** I considered cutting it — the additive
  argument is fully stated numerically (median 96, IQR [60,147], Ω from 13 to
  384, ρ = +0.09). Kept: cutting would leave a 20-page systems paper with one
  figure, and the scatter is the only place a referee can see the argument
  rather than read it.
- **Restoring the compiler-pipeline TikZ diagram from `FULL_REFERENCE.tex`.** The
  previous reconstruction rejected it at ≈0.3 pp; I agree, and Table III does the
  same job in a third of the space *and* carries the "ran / never invoked" column
  the diagram could not.
- **The favourable pinned-FBT numbers that exist in the data and are not in the
  paper.** `data/wround/W2_cost.json` records `gloo_fbt_ch1` at geomean **0.65×**
  — i.e. the export is *faster* than stock all-reduce on the CPU backend — and
  `\PinBigChunkTwo` = 1.85× at 128 MiB for the two-chunk arm. Both would soften
  the 2.57× headline. I did not use either. The pre-registered headline is NCCL
  fp64; stock gloo is not a credible baseline; and the two-chunk arm's own geomean
  is **3.59×** with a worst case of **29.18×**, so quoting only its favourable
  size would be cherry-picking of exactly the kind the paper spends L13 warning
  against. The honest unfavourable verdict is worth more than the spin.
- **The η framing, L1b, L5, the SHARP/SwitchML/Groq paragraph, the pinned-FBT
  self-correction, the 39-of-40 disclosure, the selection rule with its held-out
  interval [1.0025, 1.0885], the 2.57× with its provisional/contention caveat.**
  All settled by you and all verified present and unmodified in the built PDF.
  The DMP clause I added in §X sits *after* the SHARP paragraph, not inside it.
- **The title.** High risk, no measurable reward. Unchanged.
- **`Property~\ref{prop:2}` renders as "Property 1"** because it is the first
  `property` environment. Consistent throughout the output, so I left the label
  name alone rather than churn twelve cross-references for zero reader benefit.
- **Softening "we withdraw" / "the construction we published is incorrect".**
  These are the paper's strongest credibility assets. Untouched.

---

## 4. The page decision, stated explicitly

TPDS's regular-paper norm is 14 pages; this is **20**, so roughly six overlength
pages of charges. I could have reached ~17–18 by cutting Table I, Fig. 1 and the
selection-rule subsection. I judged each of those to cost more first-turn
acceptance probability than a page costs money, and your objective is
lexicographic with acceptance strictly dominating. The 1.15 pages I did remove
(R1–R4) plus ~1.1 pages of compression paid for ~0.5 pages of additions and the
new bibliography, landing at 20 with the last page essentially full.

If you want a shorter submission, the next three cuts in order of least damage
are: (1) §VII-F's transfer-to-unseen-topology paragraph moved to a footnote-scale
statement (−0.35 pp, costs the held-out interval's prominence); (2) Appendix B's
prose around Tables VII–VIII (−0.2 pp); (3) §IV-D compressed by a third (−0.3 pp,
costs the strongest hardware argument in the paper). I do not recommend any of
them.

---

## 5. Outstanding — things I could not resolve

1. **Thirteen `% TODO verify` markers in `references.bib`.** Page ranges, DOIs,
   editions and — for `tbik2025` and `repdl2025` — **author given names** are
   recorded as surnames only. `repdl2025` is now cited, so `[26]` will print as
   *"Xie, Zhang, and Chen"*. Verify before submission; an incomplete author list
   in a reference is a small but avoidable ding.
2. **"The construction we published is incorrect" (§VIII).** I could not establish
   *where* it was published. The arXiv companion in the snapshot
   (`snapshot/companion/main.tex`) is a hardware implementation reference and
   contains no pinned-FBT construction. If nothing is public, "published" should
   become "first formulated"; if a preprint is public, leave it. I left the
   author's wording because getting this wrong in the *understating* direction is
   worse than in the overstating one. **This needs a one-line decision from you.**
3. **The one real evaluation gap remains open and is stated in its own item.**
   L1b: no measured same-fabric η on the 8 non-power-of-two instances. The η = 1
   theorem covers 31 of 39; nothing covers the other 8. Closing it needs
   CBTree made shape-parametric plus 39 compiles and simulations — real work,
   correctly deferred, honestly flagged.
4. **pinned-FBT cost is provisional.** Measured at G = 2 for NCCL only (the node
   has two GPUs), under an unrelated job saturating both GPUs. The paper says so,
   gives the contention-corrected 2.08×, and says a quiet-machine re-run is owed.
   A referee may well ask for it. It is half a day of compute and would firm up
   the paper's only production-hardware cost number — **if you have the machine,
   do it.**
5. **No silicon, no synthesis, no F_max/area/power** anywhere. Stated four times.
   An architecture referee may still hold it against the fabric sections; there
   is no textual fix.
6. **Mutation testing covers two classes** (address substitution, leaf
   corruption); scoreboard, forwarding and credit-return mutations are untested.
   L11 says so. Detection figures are a lower bound on harness sensitivity.
7. **18 underfull hboxes** in the log. Cosmetic only (`\raggedright` columns and
   the smallcaps captions); zero overfull, which is the requirement.
8. **`check_consistency` still emits its six baseline warnings** — four are
   literals in prose that shadow macros (`2048`, `256`, `512`, `8192`) and two
   are C4 wording probes that cannot see through `\SuiteSize` / `\TournNInst`.
   Identical to the pre-existing set; I introduced none.

---

## 6. Honest assessment of what remains weak

The paper is now saying exactly what it can prove, and saying it in the order a
TPDS referee reads. What it still cannot do:

- **The artefact is a simulator.** Every fabric number is xsim. The paper is
  scrupulous about this, but a referee who wants a systems paper to touch silicon
  will not be satisfied, and no amount of writing changes that.
- **The one deployable thing is 2.57× slower than stock.** The paper prices it
  honestly and separates the algorithmic factor of two from the export artefact,
  which is the best available position — but a referee looking for a performance
  result will not find one.
- **The core claim is close to definitional and the paper says so.** I have made
  the paper state where the work actually is, but I have not manufactured
  difficulty that is not there. That is the right trade, and it is also the most
  likely single ground on which this gets a major revision rather than an accept.
- **The oracle is a transcription of the RTL.** §VII-B's new oracle-free reading
  removes this as an objection to *invariance*. It does not remove it as an
  objection to *accuracy*, and L13 says so plainly.

My estimate: the reordering, the regime bridge, the oracle-free reading and the
recency citations together move this from "likely major revision on framing" to a
genuine shot at accept-with-minor-revision. The residual risk is concentrated in
"is a simulated NoC plus a 2.57× software export enough of a systems contribution
for TPDS?" — a judgement call no edit to `main.tex` can settle.
