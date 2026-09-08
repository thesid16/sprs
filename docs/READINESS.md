# READINESS — paper_mid/main.tex (TPDS submission)

Audit date: 2026-09-02. Every claim below was re-verified by execution against the
tree as it stands (`main.tex` mtime 2026-08-29 05:54, `main.pdf` built 3 s later).
Nothing here is asserted from memory or from a prior pass's write-up.

---

## 1. VERDICT

**Not submittable today, for exactly one reason: the manuscript is 20 formatted
pages and TPDS's hard ceiling for regular-paper submissions is 18.** This is an
administrative check applied at upload, not a referee judgement — at 20pp the paper
is returned before review, so every other question about it is moot until the page
count comes down. I verified both halves myself: `pdfinfo main.pdf` reports 20, a
clean rebuild from scratch reproduces 20 exactly, and there is no formatting trick
inflating it (no `geometry`, no `\addtolength`, no leading changes; `compsoc` builds
to 20 as well). I fetched `MOPC_policy.pdf` from ieeecs-media.computer.org and
extracted the text directly: TPDS is in the covered-journal list, "Regular paper
submissions to Transactions may not exceed 18 formatted pages", and "strictly
enforced". Beyond the page count there are six textual defects that would materially
damage a first-turn verdict — one wrong number, one unreconciled arithmetic gap
sitting directly under the paper's central "no shortlist" claim, and four
self-contradictions where the 20pp compression left a sentence pointing at an
argument that no longer says what it used to. All six are one-to-four-sentence edits
that touch no measurement, no table, no figure and no generated macro; together they
are perhaps two hours of careful work. **The paper is one page-reduction pass and six
text edits from submittable.** Nothing in the audit challenges a headline number, a
validated result, or any item on the settled list.

---

## 2. MUST FIX BEFORE SUBMISSION

Seven items. Ranked by damage to the first-turn verdict, not by cost.

### M1 — BLOCKER: 20 pages against an 18-page hard cap
**Where:** `paper_mid/main.tex:9` (document budget); appendices at `main.tex:2141`–`2293`.

Verified: baseline rebuild = `Output written on main.pdf (20 pages, 504572 bytes)`.
Policy verified by direct fetch and `pdftotext`, not from memory.

**Fix, measured end to end:**
1. Move Appendices A–C (`main.tex:2141` `\appendices` through the line before
   `\bibliographystyle`, i.e. lines 2141–2293) to supplemental material — the route
   the MOPC policy itself names. **Measured: 19 pages.** Costs no result, no table,
   no figure. Only two in-body pointers need rewording: `main.tex:426`
   (`Appendix~\ref{app:assumptions}`) and `main.tex:1294` (`Appendix~\ref{app:repro}`).
2. Then cut prose to reach 18. **Measured threshold, by bisection on real builds:**
   from the 19-page build, removing ~349 words still yields 19; removing ~946 words
   yields **18**; removing ~1,939 words overshoots to 17. So budget **~900–950 words**
   at the measured 1,024 words/page. Do not budget 1.5–3 pages — the 19-page build's
   last page is already only 83% full (5,473 chars vs 6,605 on a typical body page).

**Levers that do NOT work — each tested, do not spend time on them:**
- Deleting Table I on top of the appendix move: **still 19 pages.** A full-width
  `table*` here buys nothing.
- Deleting Fig. 1 alone, or Table I alone, from the 20pp build: **still 20.**
- Swapping `ieeetr` for the official `IEEEtran.bst`: **21 pages.** The bibliography
  holds no free page; the current `ieeetr` choice is already the more compact one.

**Also correct `SUBMISSION_REVIEW.md:260-265`**, which records the decision to ship
at 20 against a false premise: "TPDS's regular-paper norm is 14 pages … a page costs
money." The charge-free limit is 12, and past 18 it is not a money question at all —
it is a desk return. The decision was made on a wrong fact, so it is live, not settled.

---

### M2 — The 2,920 → 2,844 gap sits directly under the "no shortlist" claim
**Where:** `paper_mid/main.tex:1180` and `:1183`.

`main.tex:1180` states the dedup result over all 40 instances — "collapses the
$6{,}777$ to $2{,}920$ distinct ones" — and `:1183` immediately asserts "Every
distinct image was then queued for xsim --- no shortlist of any kind stands between
the compiler and the invariance evidence." But `\InvAttempted` is 2,844. Nothing in
the 20pp submission closes the 76-image difference.

Recomputed from `data/results/*/sw_results.csv` (40 dirs): 7,200 compilation rows;
6,777 emit a `tb_hash`; 2,920 distinct hashes over all 40; `maxp_mod_fat` contributes
exactly **76** distinct images, **all unique to it** (shared with none of the other
39); distinct over the other 39 = **2,844**. So 2,920 − 76 = 2,844 exactly.

The archive carries the reconciling sentence at `paper_canonical/main.tex:2533-2536`
("The one exception is `maxp_mod_fat`, dropped from the HW-validated suite: five of
its 76 images were attempted and each exhausted the 8 h simulator budget; the other
71 were not run"). The 20pp cut removed it and never replaced it. The submission's
two `maxp_mod_fat` disclosures (`:1391` table note, `:1947` L0) say the instance is
unsimulable but never mention the 76 images or the arithmetic. Everything else in the
submission scopes correctly to 39 (`:117`, `:1348`, `:1969`, `:2100`), which is what
makes the orphaned 2,920 conspicuous.

**Why this ranks second:** the paper's central rhetorical asset is that no selection
stands between the compiler and the invariance evidence. A referee who subtracts finds
an unexplained 76-image shortfall two lines under the sentence claiming exactly that.

**Fix:** restore the scope in one clause at `:1183`, e.g. "Every distinct image was
then queued for xsim, except the 76 belonging to \sv{maxp\_mod\_fat}
(\S\ref{sec:limitations}, L0), leaving \InvAttempted{} --- no shortlist of any kind
stands between the compiler and the invariance evidence." This strengthens the claim
rather than weakening it: it shows the only omission is an instance-level one already
disclosed twice.

---

### M3 — Cost-decomposition term 1 asserts the premise the η theorem refutes
**Where:** `paper_mid/main.tex:1486-1489`, with knock-ons at `:1496-1497`, `:1503`, `:1858`.

`§sec:method` (`:1254-1256`) states the theorem: "The ISA's `COMPUTE` is two-input, so
every reducer over $N$ leaves has depth at least $\lceil\log_2 N\rceil$, which is
exactly the depth of $\FBT(N)$: the tree-depth term is $\le 0$ on all 39 validated
instances." `§sec:results-overhead` term 1 (`:1486-1489`) says the opposite: "an
unconstrained reducer forms partial sums of arbitrary arity $k$ and is $\log_k N$
deep. This term grows with $G$ and is the irreducible core of the cost."

Verified by execution, both prongs:
- **Arity.** `main.tex:676-683` gives the 64-bit instruction word with exactly two
  16-bit address fields; `:694` states "Two source fields are mandatory because
  `COMPUTE` names both members of the operand pair the ABI binds"; Table `tab:isa`
  agrees; `rtl/btree_fsm_fast.sv` carries `dmem_rd_addr_a`/`dmem_rd_addr_b` only. An
  arity-$k$ partial sum is not expressible in one op.
- **Depth.** Computed max leaf depth directly from the heap indexing of Def.
  `def:fbt` (leaves at indices $N-1..2N-2$): it equals $\lceil\log_2 N\rceil$ on all
  sixteen suite leaf counts and exhaustively for $N = 2..20{,}000$ — **zero mismatches.**

So no same-fabric reducer is shallower than $\FBT(N)$, "grows with $G$" is false, and
term 1 can never be a positive cost. This is not an orphaned-file issue: lines
1477–1503 are live inside `\section{Evaluation}`, and `main.tex` contains no
`\iffalse`/comment conditionals anywhere.

**Why it matters:** term 1 is the load-bearing defence of L1b (`:2011-2015`, "S.method
shows $\eta = 1$ by construction on the 31 power-of-two instances") — the single most
contested item in review. A referee reading "$\eta = 1$ by construction" beside "the
irreducible core of the cost … grows with $G$" can reasonably demand the baseline be
built after all. Diagnosis: stale text carried from the archive, left behind when the
η passage was deliberately rewritten into a theorem. Note the error runs *against* the
authors' interest — it overstates the ABI's cost.

**Fix — four edits, all textual:**
1. `:1486-1489` — replace term 1's premise with what the theorem gives: the two-input
   `COMPUTE` forces every same-fabric reducer to depth $\ge \lceil\log_2 N\rceil$,
   exactly $\FBT(N)$'s, so the tree-depth term is $\le 0$ and is not a cost. Keep the
   item in the enumeration so depth is still accounted for; it now reports a zero.
2. `:1496-1497` — term 3's back-reference "Unlike the first two this is an artefact of
   *our* GCI" must become "Unlike term 2 …".
3. `:1503` — "Terms 1 and 2 are the price of reproducibility" must name term 2 alone.
   Support it from the paper's own reasoning ("what separates them is which operands
   pair at each level, not how many levels there are"), **not** from
   `paper_canonical:466-470`, which actually names leaf-generation serialisation and
   root-gather fan-in (terms 3 and 4).
4. `:1858` — drop "of arbitrary arity" from the discussion echo.

**Do not** propagate this to `MINIMAL_REFERENCE.tex`: it states no theorem
(`:707-718` keeps the older "structurally blind" framing), so it does not
self-contradict, and the edit would introduce a dangling claim there.

---

### M4 — "That is not a modelling artefact" is scoped to every instance; the support reaches 31
**Where:** `paper_mid/main.tex:1253`.

`:1251-1253` reads: "We did build that model … and it returns $\hat\eta \approx 1$ on
every instance. That is not a modelling artefact, and the reason is structural."

The structural support that follows has two prongs with different reach. The depth
prong covers all 39 but is a claim about *depth*; η is a makespan ratio. The
DAG-isomorphism prong — the one that actually gives η = 1 — covers only the 31
power-of-two instances (`:1258-1262`, "88 of 88 such pairs … On the 31 power-of-two
instances there is nothing a baseline could reveal"). Twenty-four lines later `:1277`
says "On the remaining 8 instances a baseline would say something", and L1b at
`:2013-2016` says "There the isomorphism does not hold, the ABI may cost something we
have not priced." The paper contradicts itself on the page, with no artifact needed.

Corroboration (recomputed from `experiments/w_final/W7/RESULT.json`, not quoted): on
the 7 measured non-power-of-two instances `dag_isomorphic` is False 7/7 and the ratio
is 1.026–1.352, not ≈1. **This is not a request for a measured η** — that harness
returns the compiler cost model itself and is circular, per the settled list. It is
cited only to show that the same class of instrument does not return ≈1 on the 8.

**Fix — one sentence, no deletion, no new measurement.** Scope the negation in place
at `:1253`: "Where $N$ and $G$ are powers of two that is not a modelling artefact, and
the reason is structural; on the other $8$ instances the model is indexed by depth and
hop count, is blind to which operands pair, and we do not read its $\approx 1$ as
evidence." This leaves the theorem paragraph (`:1254-1262`) untouched and restores
consistency with `:1277` and L1b.

**Do not** restore the canonical clause verbatim: `paper_canonical:2421-2430` re-blinds
the model at power-of-two, which this version's own 88/88 proposition refutes. For the
31, paper_mid is stronger than the archive. Only the word "every" is wrong.

---

### M5 — Export-cost narrative: window stops before the trend reverses, and the best case is under the declared floor
**Where:** `paper_mid/main.tex:1799-1807`; floor repeated at `:1271`, `:1802`, `:2131`, and the abstract `:132`.

Recomputed the fp64 / NCCL / G=2 / `fbt_ch1` / N=8 sweep from
`data/wround/W2_cost.json` — all eight points reproduce exactly:

| size | 8 KiB | 32 KiB | 128 KiB | 512 KiB | 2 MiB | 8 MiB | 32 MiB | 128 MiB |
|---|---|---|---|---|---|---|---|---|
| ratio | 3.288 | 2.918 | 3.120 | 1.593 | 2.687 | 1.485 | 1.668 | **2.207** |

Two problems, both referee-visible:

**(a) Truncated window.** `:1806-1807` says the artefact fades "at large ones
($\PinLargeLo$--$\PinLargeHi\times$ between \PinLargeSizeLo{} and
\PinLargeSizeHi{})" = 1.49–1.67× between 8 MiB and 32 MiB. But 128 MiB is the largest
measured size and is **2.207×** — the trend reverses at exactly the point the quoted
window stops. The paper *does* state the sweep spans up to 128 MiB (`:1774`, via
`\PinMsgHi`, and it renders), which makes the omission sharper, not softer: the reader
is told the sweep goes to 128 MiB and then shown a window that ends at 32 MiB. The
value itself already exists as a generated macro — `\PinBigChunkOne` = 2.21 in
`data/wround_macros.tex:115` — **and is never used in `main.tex`.**

**(b) Best case below the declared floor.** `:1790-1791` prints "geometric mean …
$\PinCostGeo\times$ stock, best $\PinCostBest\times$" = best **1.49×**. Eleven source
lines later, `:1801-1802` declares "a factor of about two is algorithmic and no
engineering removes it." Both render in the same paragraph of the PDF. Three of the
eight sizes (1.485, 1.593, 1.668) are below 2.

The floor claim is defensible as stated *about bytes* but not as a wall-clock floor,
and the arithmetic shows why — recomputed from the same rows: at 32 MiB stock moves
$M$ at 12.7 GB/s while pinned-FBT moves $2M$ at 15.3 GB/s; at 8 MiB, 10.9 vs 14.7
GB/s. The time ratio drops below 2 because stock NCCL is not bandwidth-optimal at
those sizes, not because the byte factor vanishes. The paper says neither.

Also: `experiments/PREREGISTRATION.md:53` (W2-H2) pre-committed to "Report the FULL
size sweep, plus the geometric mean, best case and worst case." Geomean/best/worst are
reported correctly; the full sweep appears in no `.tex` and the companion carries no
pinned-FBT material. That clause is undischarged, in a paper whose artifact ships
`PREREGISTRATION.md`.

**Fix — two clauses, zero pages.** The reconciliation is already drafted in the repo:
`FRAMING_PLAN.md:147` reads "The bandwidth-bound band is 1.49–2.21x, centred on 2."
1. Replace the trend clause at `:1804-1807` so it names the largest measured point and
   places the sweep *around* the factor rather than under it — e.g. "…receding at
   bandwidth-bound sizes, where the sweep straddles the algorithmic factor rather than
   sitting above it: 1.49× at 8 MiB to 2.21× at 128 MiB, the largest size measured."
2. Half a clause at `:1802` (mirrored at `:1271`, `:2131`, `:132`): "…a factor of about
   two **in bytes on the wire**, which no engineering removes, though it translates to
   a time ratio only where stock is bandwidth-bound."

Do **not** drop the 128 MiB row as contention-affected. It is excluded on no stated
ground, the same median estimator is used everywhere else, and silently omitting the
one point that breaks the quoted window is precisely the appearance problem.

---

### M6 — `G ∈ [2,4096]` attributed to the 39 hardware-validated instances; the true maximum is 2048
**Where:** `paper_mid/main.tex:1351`.

`:1349-1351`: "Across the \InvAttempted{} distinct ABI-compliant program images
obtained by compiling the complete $18\times10$ grid on the \TournNInst{}
hardware-validated instances --- \InvLeafCounts{} leaf counts $N \in [8,8192]$,
requested worker counts $G \in [2,4096]$, six direct-network topologies ---". The
em-dash apposition attaches unambiguously to the 39.

Recomputed by joining `src/sprs_core.py` `TEST_INSTANCES` (40) against
`data/results/live_hw_results_p1_maxpe.csv` (39 distinct instances, 2,822 passing rows
= `\WallTBs`; `maxp_mod_fat` absent entirely). Over the 39 validated instances:
G ∈ {2,4,5,7,8,10,12,16,32,64,128,256,512,1024,2048} — **min 2, max 2048**; N ∈ [8,8192];
16 distinct N; 6 topologies. Every other item in the list is true of the 39; the G
bound is the only false one, and it is exactly the 40-instance value. `tables/suite.tex:49`
confirms the sole G=4096 row (`maxp_mod_fat`) carries HW "--". The paper contradicts
itself at `:1692` ("untested at $G = 4096$, the one design point without a hardware
result").

**Fix:** at `:1351` change `$G \in [2,4096]$` to `$G \in [2,2048]$`. Verified minimal
and sufficient — no macro, table, or downstream number is touched.

At `:116-117` (abstract) and `:2098-2099` (conclusion) do **not** change the number:
[2,4096] is a true statement of the *suite* envelope. Re-attach it instead, e.g. "on
\SuiteSize{} instances spanning … $G\in[2,4096]$ and six direct networks,
\TournNInst{} of them hardware-validated, …". This keeps the honest 39-of-40
disclosure while removing the attachment ambiguity.

`paper_canonical/main.tex:2673` carries the identical sentence verbatim; fix it there
too when the archive is next built (canonical `:450` already shows the correct pattern).

---

### M7 — `\OrderLRDiff` is wrong: the paper prints "ten", the value is 12
**Where:** `data/claim_macros.tex:58` (definition), used at `paper_mid/main.tex:381`.

`main.tex:380-381`: "right-to-left sequential summation differs from $\Rcan$ by up to
\OrderUlpMax{} ulp at $N = \OrderUlpMaxN$, and left-to-right differs at \OrderLRDiff{}
of the sixteen leaf counts." Renders in the PDF as "differs at ten of the sixteen leaf
counts."

I rebuilt the canonical reducer from released source alone — `src/sprs_core.py`
`CBTree` + `_fp64_add_bits` + the `make_leaf_val` fp64 formula — and **validated it
16/16 against `tables/invariance.tex`'s own hex roots** (every N, exact match). Under
that validated model:
- right-to-left differs from $\Rcan$ by **55 ulp at N = 8192** — the sentence's first
  half reproduces **bit-exactly**, matching `\OrderUlpMax` and `\OrderUlpMaxN`;
- left-to-right differs at **12** of the 16 leaf counts, not ten (right-to-left differs
  at 11; no ordering variant I tried yields ten).

Because the sentence-mate reproduces exactly under the identical model, this is close
to proof that "ten" is wrong. The rest of the T07 block also reproduces exactly:
40,320 permutations → 3 roots, 88.57% canonical, detection 0.1143, Catalan(15) =
9,694,845 → 4 roots.

**Why it matters despite being one subordinate clause:** this paragraph is the *one
passage in the paper a referee can independently check from released source alone* — I
did it in ~40 lines of Python with no council record — and it contains a number that
does not reproduce, in a paper whose thesis is bit-reproducibility and auditable
provenance.

**Fix:** set `\OrderLRDiff` to `twelve`, or delete the clause. Cheapest item on this
list; do it first. (The provenance record `T07_verify.json` does not exist anywhere on
the filesystem, so the intended alternative reading cannot be recovered — see S1.)

---

## 3. SHOULD FIX — worth doing, does not block

### S1 — `data/claim_macros.tex` has no generator and `make check` validates it vacuously
**Where:** `data/claim_macros.tex`; `scripts/verify_tables.py:77-78`; `Makefile:16`.

Verified by execution:
- 7 of the 8 `data/*.tex` files have generators; `claim_macros.tex` has none —
  `grep -rn claim_macros scripts/ Makefile` returns nothing, and no `gen_claim*`
  script exists anywhere on disk (paper_mid, paper_canonical or paper_min).
- There are exactly **28** `.tex` files under `tables/`, `data/`, `figures/` — the same
  28 the guard reports. Back-dating all 28 in a scratch copy and running `make tables`
  rewrites **27**; `data/claim_macros.tex` is **the only file never rewritten**.
- `verify_tables.py:55` does a full `copytree`, so a file no generator rewrites is
  diffed against its own copy at `:77-83` and passes — while still being counted in
  "OK: all 28 generated .tex files reproduce from their generators."
  `scripts/check_inputs_exist.sh` does not save it: despite the Makefile comment, it
  only tests `[ -f "$f.tex" ]`.

This is the process defect behind M7. It is not itself submission-blocking — but note
`claim_macros.tex` is load-bearing: `main.tex:72` inputs it and 44 of its 45 macros are
used, including `\MutTotal` in the abstract.

**Fix, cheapest ordering:**
1. Make the guard non-vacuous: snapshot mtimes before the scratch `make tables` and
   fail for any `.tex` under `tables/`, `data/`, `figures/` that was not rewritten.
   Also correct the output string, which asserts "reproduce from their generators"
   about a file with no generator.
2. Add `scripts/gen_claim_macros.py` for the T07 block — **no JSON required.** I
   verified 9 of its 11 T07 macros are derivable from released `src/sprs_core.py`
   alone (the same model validated 16/16 above): `OrderUlpMax`=55, `OrderUlpMaxN`=8192,
   `OrderPermsEight`=40,320, `OrderRootsEight`=three, `OrderCanonPctEight`=88.6%,
   `OrderDetectEight`=0.114, `OrderShapesSixteen`=9,694,845, `OrderRootsSixteen`=four,
   and `OrderLRDiff`, which re-derives to **12** — making M7 automatic rather than a
   hand edit. Only `OrderProbMin`/`OrderProbMax` need a sampling procedure pinned down.
3. **T14 is the real residual.** Its 12 macros (`Recycle*`/`Gen*`/`Gci*`) have zero
   footprint in any shipped record — `T07_verify.json` and `T14_verify.json` exist
   nowhere on the filesystem, and `grep -i recycl` over all shipped council JSONs
   returns nothing. Either recover the records or, consistent with how L1b and the 40th
   instance were handled, state their provenance honestly rather than leaving them under
   a "GENERATED FROM COUNCIL VERIFICATION" banner no artifact supports.
   (The T03/T04/T13 blocks — 22 macros — **do** trace exactly to shipped records.)
4. **One-token Makefile fix, separate defect:** `Makefile:16` reads
   `$(MAIN).pdf: $(MAIN).tex references.bib $(wildcard tables/*.tex) $(wildcard figures/*)`
   — `data/*.tex` is omitted, so editing any of the eight macro files does not trigger
   a rebuild and `check: all` can validate a stale PDF. Add `$(wildcard data/*.tex)`.

Also: `\MutLiveSlotMax` (`claim_macros.tex:53`) is the one macro of 45 never used. Harmless; a generator would drop it.

### S2 — L5 states 23 populated / 18 thin against a table showing 26 populated / 23 thin
**Where:** `main.tex:2027-2028`; caption `:2228-2230`; `data/results_macros.tex:72-73`; `scripts/gen_results_macros.py:221-222`.

`:2027-2028` cites Table `tab:coverage` then says "Of the \SelPopCells{} populated
(size × topology) cells, \SelThinCells{} hold two instances or fewer" = 23 populated /
18 thin. The caption of that same table says "\SuiteThinCells{} of the populated cells
hold two instances or fewer and \SuiteEmptyCells{} are empty, **which is the basis for
L5**" = 23 thin / 4 empty. Counting `tables/coverage.tex` directly: 5 buckets × 6
topologies = 30 cells, **26 populated, 4 empty, 23 thin, max cell 3, total 40** —
matching the caption exactly and the prose not at all.

Two aggravations: (a) the pointer is bidirectional — the caption names L5, so a referee
following it lands on the contradiction; and prose (23 populated) + caption (23 thin)
jointly imply *every* populated cell is thin, which the printed table visibly refutes
(three cells hold 3). (b) `\SelPopCells`/`\SelThinCells` are **hardcoded literals** in
`gen_results_macros.py:221-222`, transcribed from a prose sentence in
`data/council/SELECTION_RULE.json` (which reproduces only under a coarser 4-bucket
binning), whereas `\SuiteThinCells`/`\SuiteEmptyCells` are computed from the manifest.
`check_consistency.py` has no rule tying them together.

No claim is falsified — L5's conclusion holds under either binning, and is in fact
*stronger* under the table's (23 of 26 thin) than under the prose's (18 of 23).

**Fix (cheapest, touches no generator):** rewrite `:2027-2028` to mirror the caption,
dropping the untraceable populated count:
`Of the populated (size~$\times$~topology) cells, \SuiteThinCells{} hold two instances or fewer, so no cell-level recommendation is derivable and we make none.`
If a populated count is wanted in prose, do **not** hardcode 26 —
`scripts/gen_coverage.py:171` already computes it; emit it as `\SuitePopCells` beside
lines 163-164. Either way, retire `\SelPopCells`/`\SelThinCells`, which are used
nowhere else.

### S3 — Proposition 1 is cited as covering the axis it explicitly fixes
**Where:** `main.tex:1979` (L0a) and `main.tex:1585`.

L0a: "…refinement is \sv{None} in every measured configuration, and the remaining axis
is covered by Proposition~\ref{thm:orth} rather than by measurement." The remaining
axis is refinement $r$. But Proposition 1 (`:568-569`) opens "Fix $N$, $L$, $\asgn$,
$r$ and the FADD unit" and quantifies only over $\map_1,\map_2$ and $\rho_1,\rho_2$ —
it holds $r$ constant. Arithmetic checks: $18\times10\times122 = 21{,}960$,
`\SelConfigsTotal` = 180, $180/21960 = 0.82\%$, and refinement is already fixed in the
preceding clause, so only $r$ is left.

`:1585` is worse in a different way: `\ClsCompilations` = 7,200 = $18\times10\times40$,
so "the compiler's variation space" there is the $(\alpha,\mu)$ face — and Prop 1 fixes
$\alpha$ too. That contradicts the proposition's own framing paragraph at `:563-565`
("Of the axes Claim 1 quantifies over, $(G,\asgn)$ is where the substantive work
lives… The $(\text{topology},\map,\rho,s)$ slice admits a sharper statement").

Provenance: `paper_canonical:3572-3576` pointed the same sentence at
`\S sec:compiler-orth`, which invoked "Argument A1 and Proposition~\ref{thm:orth}";
both `sec:compiler-orth` and Argument A1 were dropped in the 20pp cut and the pointer
was redirected onto an object with the wrong scope.

**Fix — do NOT cite Claim 1**: it is the object under test three lines above (`:1975`,
"Non-settling runs are not evidence for Claim~\ref{claim:1}"), so that would be
circular. Cite **Def.~\ref{def:opbind}** (`:396-402`, "The binding is a pure function
of $v$") together with `:414` ("Neither discipline references $G$, topology, assignment
$\asgn$, mapping $\map$, refinement $r$, or timing") — the surviving object with the
right scope. At `:1585`, "Def.~\ref{def:opbind} and Proposition~\ref{thm:orth} say…".
Two phrase edits. Nothing becomes false without this — only the cross-reference is
out of scope.

### S4 — Bibliography: one undated entry, two bare surname lists
**Where:** `references.bib:157` (`onemkl_cnr`), `:169` (`tbik2025`), `:180` (`repdl2025`).

A scripted scan of all 49 entries returns exactly one with no `year`: `onemkl_cnr`.
It is genuinely the only undated reference among the 35 printed, it is cited twice
(`main.tex:303` in Table I, `:1902` in prose), and it renders as an undated "[18]".
BibTeX emits no warning for it (`main.blg` has two unrelated ones: volume+number
conflicts in `sanders2009two` and `kahan1965summation`).

The other three "missing" items are **not** defects and should not be added: 24 of 35
cited entries carry a `url` that `ieeetr` silently discards, and **zero** of 35 carry
an access date. Adding either would make this the single most decorated entry in the
list — inconsistent, not corrective.

`tbik2025` and `repdl2025` print bare surnames with no initials; these are the only
two personal-author entries of 35 lacking initials (NVIDIA/AMD/IEEE/Intel/Mellanox are
corporate authors, correctly formatted), and `graham2016scalable` prints all 16 authors
under the same `.bst`, so the style is not truncating — the data is.

**No network lookup is needed for any of the three.** All sources are on disk:
- `/home/rohit/t16scratch/arxiv_meta.xml` (raw arXiv API output) gives
  **2511.17826** → Ziyang Zhang, Xinheng Ding, Jiayi Yuan, Rixin Liu, Huizi Mao,
  Jiarong Xing, Zirui Liu; and **2510.09180** → Peichen Xie, Xian Zhang, Shuo Chen.
  I parsed the XML directly to confirm.
- `/home/rohit/t06scratch/cnr.html` is the HTTP 403 page (corroborating the TODO at
  `references.bib:153-156`) and its URL path is
  `…/onemkl/developer-guide-linux/**2024-0**/reproducibility-conditional-numerical.html`;
  `cnr2.html` is the .cn mirror content and cites "starting in version 2024.1". That
  substantiates `year = {2024}` from local evidence.

Strip the now-satisfied TODO comments at `:166-168` and `:178-179` while you are there.
Leave `abts2022groq` as "Dennis Abts and others" — see §4.

### S5 — Archive-only defects (fix before the archive is published, not before submission)
Neither is reachable by a referee: `grep -ncE '\\url|href|http|github|arxiv|companion|supplement'` over `paper_mid/main.tex` returns **0** — the submission contains no pointer of any kind to the archive.

- **`paper_canonical/main.tex:181` and `:457`** claim the campaign "RTL-validates every
  distinct program image it produces" over "each of \SuiteSize{} instances" (= 40).
  False by 76 of 2,920. The enumeration half is true (180 × 40 = 7,200, verified). The
  archive self-corrects within one sentence (`:182` retreats to "2,844 images attempted
  on 39"), states the exception in full at `:2532-2536`, and repeats it in L0 at
  `:3528` — so no archive reader is misled past one sentence. **Fix:** scope the
  trailing clause to "…every distinct program image produced on the 39 hardware-validated
  instances."
- **`paper_canonical/main.tex:2031-2033`** reports "the ratio against the
  non-deterministic baseline is more stable because both schedules share the
  bottleneck" — an empirical claim about a baseline the same document says twice it
  never built (`:2419`, `:3634`). Nothing in the tree supports it; the only ND
  generator is `scripts/gen_ndmodel.py.notused`, disabled by file extension. Reading
  order aggravates it: the claim sits ~375 lines *before* the disclaimer. The error
  direction is the damaging one — it implies ND data was measured and withheld.
  **Fix:** delete the clause so the sentence ends "…absolute cycle counts slew because
  of this. Wormhole forwarding is a planned extension." The submission already reads
  this way in substance (`:1000-1003`); do not attempt a verbatim transplant.
  Rebuild `paper_canonical/main.pdf` afterwards — the stale PDF renders the sentence.

---

## 4. DELIBERATELY NOT DOING

**W2 NCCL re-measurement on a quiet machine.** Both GPUs have been saturated by other
users' jobs for many hours. The pre-registered verdict is invariant to the contention
correction — only the point estimate moves — and the contention is already disclosed
*with a bound*: `main.tex:1793-1798` states the sweep ran under saturation, reports the
best-of-repeats estimator at 2.08×, and quantifies the inflation at ~1.24×, noting both
estimators are far outside the pre-registered support band. A re-run is owed and the
paper says so; it is not a submission dependency. (Independent of M5, which is a
*wording* defect about a window and a floor, not a measurement defect — M5 must still
be fixed with the data already in hand.)

**A measured η.** Settled, and correctly. The only harness in the repo
(`experiments/w_final/W7/v001/w7_eta2.py`) computes `sc.build_schedule(...).makespan`
under `sc.HW` — the compiler's own cost model — so any number it returns is circular.
The η passage states a theorem and should keep doing so. M4 narrows a scope word; it
does not ask for a number.

**Promoting L1b, or removing the 8-instance residual.** Settled. The honest residual stays.

**Making 2.40× pooled the headline.** Settled: 2.57× is the pre-registered fp64-only
n=20 figure (I reproduced geomean 2.5685 / best 1.4851 / worst 3.9074), 2.40× is a
recorded pre-registration deviation, and the favourable gloo numbers stay excluded
because that baseline is demonstrably broken.

**Asserting a root cause for the 40th instance.** Settled. `maxp_mod_fat` elaborates
completely and the simulator emits no kernel; no cause is claimed, deliberately.

**Adding `url` or an access date to `onemkl_cnr`.** `ieeetr` discards `url` (it already
does for 24 of 35 entries), and zero of 35 references carry an access date. Both would
make this entry inconsistent with the other 34. Year only.

**Expanding `abts2022groq` to all 22 authors.** The IEEE Editorial Style Manual permits
"et al." after the first author beyond six, so "D. Abts et al." is arguably conformant
as printed. `ieeetr` would print all 22 — compare `graham2016scalable`, whose 16
authors consume four rendered lines — adding roughly five lines to a paper that is
already two pages over cap, for zero referee benefit.

**Reclaiming pages from the bibliography, Table I, or Fig. 1.** All measured, all
refuted: `IEEEtran.bst` → 21pp; appendices + Table I → still 19pp; Table I alone → 20pp;
Fig. 1 alone → 20pp. The prose cut is the only lever that costs no content.

**Propagating the M3 term-1 edit to `MINIMAL_REFERENCE.tex`.** It states no theorem, so
it does not self-contradict; the edit would introduce a dangling claim.

**Recovering the T14 macro block.** `T07_verify.json` and `T14_verify.json` exist
nowhere on the filesystem, and the T14 values appear in no released record. They cannot
be regenerated; the honest options are recovery or disclosure (S1.3), not invention.

---

## 5. STATE OF THE THREE VERSIONS

| | path | pages | role |
|---|---|---|---|
| **Submission** | `paper_mid/main.tex` | **20** (must reach 18) | The refereed artifact. The only version whose defects can delay review. All of §2 applies here. |
| **Archive** | `paper_canonical/main.tex` | 35 | The complete record that remains available. Carries the material the 20pp cut removed — and, as it turns out, the *repairs* the cut discarded (the `maxp_mod_fat` reconciliation at `:2532-2536`, the `sec:compiler-orth` pointer, the "centred on 2" framing in `FRAMING_PLAN.md`). Has two defects of its own (S5) plus the M6 sentence at `:2673`. Not referenced from the submission — verified, zero pointers — so nothing here blocks submission. |
| **Minimal** | `paper_mid/MINIMAL_REFERENCE.tex` = `paper_min/main.tex` | 13 | The intermediate floor: what survives if the paper must shrink further. Byte-identical to `paper_min/main.tex`. **Materially different in argument, not just in length** — it keeps the older "structurally blind" η framing (`:707-718`) and states no theorem, so several §2 fixes are wrong to apply here (M3 explicitly). Treat it as a distinct argument, not a truncation. |

**Relationship worth keeping in view.** Four of the seven must-fix items (M2, M3, M4,
S3) are the same failure: the 20pp compression removed a supporting passage and left
the sentence that depended on it pointing at something that no longer says what it
used to. None is a defect of the underlying work. If further cutting happens to reach
18 pages, re-check every surviving cross-reference and every apposition against what
actually remains — that is where this class of error lives.
