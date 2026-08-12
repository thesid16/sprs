# SPRS / TPDS Manuscript — Round 2 Peer Review

**Scope:** Full re-review of the revised `SPRS_paper.pdf` and `SPRS_companion.pdf`, cross-checked against Round 1. Same methodology as before: every numerical claim I could independently reconstruct (canonical tree, leaf-value formula, FADD reduction, Table IV roots, appendix arithmetic) was recomputed from the paper's own stated definitions in Python, not read for plausibility.

---

## 0. Correction to Round 1 — the N=200 finding was my error, not the paper's

This needs to be said plainly before anything else. Round 1 flagged, as the single **🔴 Critical** issue, that my independent recomputation of the Table IV root for N=200 gave `0x41732B4046666666` against the paper's stated `0x41732B4046666667` — a 1-ULP mismatch in a paper whose entire thesis is bitwise precision.

The revised Definition 3 adds a paragraph explaining exactly this failure mode: ascending heap-index order and left-to-right visual leaf order coincide only when N is a power of two; for non-power-of-2 N, FBT(N) is depth-imbalanced and the two enumerations diverge. It names N=200 specifically and states the two conventions differ by one ULP there — precisely what I found.

I rebuilt the canonical leaf enumeration both ways and re-ran all 16 Table IV roots:

| Leaf-enumeration convention | Result |
|---|---|
| Ascending heap index (Definition 3, as written) | **All 16/16 match exactly**, including N=200 |
| Left-to-right visual order (what my Round-1 reimplementation used) | 15/16 match; N=200 off by 1 ULP — reproduces my Round-1 finding exactly |

Both of Round 1's worked examples (N=4, N=8) are powers of two, where the two conventions are identical — so my implementation validated cleanly against them while silently encoding the wrong general rule, and the bug only surfaced on the one Table IV row where it mattered. I also checked *why* only N=200 showed a divergence when seven N values (10, 50, 100, 200, 500, 1500, 3000) have the same structural ambiguity: the two orderings only reorder values that are close enough in magnitude that rounding absorbs the difference at six of the seven; N=200 is the one case where it doesn't. That's consistent with the paper's own framing elsewhere about when reordering is and isn't observable at the root.

**Bottom line: the Table IV data is correct as printed. The fix in Definition 3 is well-targeted — it forecloses exactly the misreading I made, which is likely to recur for anyone else reimplementing from the paper's prose rather than its code.** I'm flagging this prominently rather than quietly dropping it, since it was the headline finding last round.

---

## 1. Status of every Round 1 finding

| # | Round 1 issue | Status | Notes |
|---|---|---|---|
| 1 | Table IV N=200 root mismatch | ✅ **Resolved — reviewer error** | See §0. Not a paper bug. |
| 2 | Instruction-word format contradiction (32-bit vs 64-bit) | ✅ **Fixed** | Appendix A now specifies the 64-bit `opcode·aux·dest·addr_a·addr_b·reserved` word, matching Table III's 512×64 IMEM sizing and the companion doc field-for-field. Appendix A even says so explicitly now. |
| 3 | VC-steering bit: "bit 63" (companion) vs "bit 64" (main paper) | ⚠️ **Partially fixed — see new finding B below** | Main paper and companion §II-B are now fully consistent on bit 64, with the FP64-sign-bit rationale spelled out. But companion §IV (Router) still says "packet bit 63" — now a *self*-contradiction inside the companion doc alone. |
| 4 | Property 1 / Property 2 numbering inconsistent | ❌ **Not fixed** | Same pattern as before. See new finding tracking below — still present in 3 places. |
| 5 | Fat-tree port count (>8 ports) vs. `MAX_PORTS=8` hard cap | ❌ **Not fixed** | Companion §II-C still states fat-tree routing tables need 4 bits ("port numbers above seven"); main paper Table III, §IV-A, and Appendix A all still hard-cap at 8 ports / 3 bits. |
| 6 | No measured non-deterministic baseline (L1b) | ⚪ **Unchanged, self-disclosed** | §VI-B now has a substantially fuller explanation of *why* they didn't build one and why an analytical proxy would mislead (η̂≈1 artifact discussion is new and good). Still the single biggest open scientific gap, honestly labeled as such. |
| 7 | Undefined "term 5" in §VII-D-3 | ✅ **Fixed** | No longer present; decomposition consistently uses terms 1–4 throughout. |
| 8 | Counter-intuitive bisection-width direction needs explanation | ✅ **Fixed** | New paragraph in §VII-D-2 ("The direction deserves a word...") directly explains why linear beats ring despite worse bisection width. |
| 9 | Ref [23] (Koopman) misattributed as VC/wormhole reference | ✅ **Fixed** | [23] is now Dally & Seitz, "Deadlock-free message routing" — topically correct, sits in the `[17]–[24]` range citation for routing/VC-escape. |
| 10 | Ref [22] (Jeannot/TreeMatch) ambiguously paired with "Huffman trees" | ✅ **Fixed** | Now explicitly split: "Huffman trees [33], TreeMatch's topology-aware trees [22]". |
| 11 | Undefined symbol K (Kmin/Kmax) in Eq. 10 | ✅ **Fixed** | K, Kmin=1, Kmax=min(G,2N−1) all defined immediately after the equation. |
| 12 | Eq. (1) missing factor-of-2 for difference of two orders | ✅ **Fixed (explained)** | New sentence explicitly notes the factor-of-2 from the triangle inequality and why it's absorbed into the constant. |
| 13 | N=4/N=8 examples both powers of 2; non-power-of-2 imbalance never shown | ✅ **Fixed** | New N=7 worked example in Definition 3 — verified computationally, matches exactly (§0). |
| 14 | Credit-pulse-counter (2b) vs. credit-balance-counter (8b) confusion | ⚠️ **Named as a limitation, but explanation sentence is now broken** | See new finding E below. |
| 15 | Abstract doesn't disclose the 1-of-40 non-hardware-validated instance | ✅ **Fixed** | Abstract now reads "(39 of the 40 hardware-validated)". |
| 16 | 62% vs 61.5% (Identity win-share) rounding inconsistency | ❌ **Not fixed** | Still present, still cosmetic. |

**9 of 16 fully fixed, 1 resolved as reviewer error, 1 explicitly and honestly disclosed rather than "fixed," 5 still open.** That's a genuinely strong response — most of the fixes show real engagement with the specific mechanism of the issue rather than surface patching (the K-definition, the factor-of-2, the bisection-direction paragraph, and the N=7 example are all substantive, well-reasoned additions, not one-line patches).

---

## 2. New findings in this revision

### 🟠 A. Table VIII (Appendix D) cell counts sum to 42, not 40

Table VIII's own "Total" row (5, 7, 7, 11, 6, 6 by topology) is internally consistent with its column sums — but that row totals **42**, while the caption states "ROWS SUM TO THE 40-INSTANCE TOTAL" and the paper states "forty instances" everywhere else (abstract, §VI-D, Fig. 5/6 axes). I verified this two independent ways (summing by row-bucket and by topology-column; both give 42) and cross-checked against Table IV's "compiled (G,topo)" column, which sums to exactly 40 on its own. Table IV is very likely the correct one — it's independently self-consistent with the 2,822/7,200/278-rejected accounting checked in Round 1. Table VIII appears to have two extra cells somewhere (a likely double-count during construction, e.g. an instance counted in two N-buckets or two topology columns).

This doesn't touch Claim 1 — Table IV is what the invariance claim rests on, and it's fine — but it's a clean, verifiable arithmetic error in a table whose entire purpose is documenting the instance count, in a paper about numerical rigor. Worth fixing before submission; a reviewer doing the same five-second sum will catch it.

### 🟠 B. Companion doc now contradicts *itself* on the VC-steering bit

Companion §II-B: VC selection reads **bit 64** — stated with a specific rationale (bit 63 is the FP64 sign bit; steering on it would make contention value-dependent) and an RTL line reference (`rx_data[p][64 -: VC_W]`).

Companion §IV (Router): "The VC is selected by **packet bit 63**, that is, by the compiler rather than by hardware policy."

This is the same substantive contradiction as Round 1, but its shape has changed: it's no longer main-paper-vs-companion, it's companion-vs-itself, with §II-B's own stated reason for avoiding bit 63 sitting two sections above a sentence that says bit 63 anyway. This is the one item in this review I'd actually call *higher* priority than its Round-1 counterpart — a self-contradiction within one four-page document, on a claim the main paper leans on for its "value-agnostic cycle count" argument, is the kind of thing that undermines confidence in the companion doc's care generally. This needs to be resolved against the actual RTL comparison (`rx_data[p][64 -: VC_W]` in `noc_router.sv`), not just picked to make the text agree — see open question below.

### 🟠 C. Appendix E prose doesn't match its own table (and the same error repeats in §X-L6)

The K-ablation table reports median ρ = 0.95 at all three cutoffs, with median leakage 0.30 / 0.20 / 0.10 at K=10/15/30. The prose immediately below it says: *"The correlation is high (ρ ≈ 15 at the median)... at K = 15 a median 15 of the genuine top-15 would have been missed... falling to 30 at K = 30."*

- "ρ ≈ 15" should almost certainly be "ρ ≈ 0.95" — a correlation of 15 isn't possible.
- "a median 15... falling to 30 at K=30" uses the K-values themselves (15, 30) where the leakage figures (20%, 10%) belong — and note the two are backwards even under that reading (15%<30% but the table's leakage *decreases* from K=15 to K=30, not increases).

The same "median 15... falling to 30" phrasing is repeated verbatim in the Limitations section (§X, L6), which tells me this isn't an isolated typo — it's the same drafting error propagated to two places, probably by copying the sentence forward. Doesn't affect any conclusion (the correct numbers are sitting right there in the table), but as written both passages are internally nonsensical, and it's worth a single search-and-fix pass across both occurrences rather than patching one and leaving the other.

### 🟡 D. Definition 5 cites "Definition 2" for `idx`; should be "Definition 3"

"...the 64-bit value L[idx(k)], where idx is the canonical leaf enumeration of Definition 2." `idx` is defined in **Definition 3** ("Canonical leaf enumeration"); Definition 2 is the tree itself (`FBT(N)`). Trivial, unambiguous from context, one-character-class fix.

### 🟡 E. Garbled sentence in §IV-H (credit-pulse-counter explanation)

*"...the tally only has to count simultaneous read events across VCs, which is why two bits suffice at NUM_VCS = 2 even though the balance itself ranges to BUF_DEPTH = 8 fixes a multi-VC credit-loss bug in which a single-bit credit pulse collapsed multi-VC reads into one return..."*

Reads as two sentences merged without a break — as written, "BUF_DEPTH = 8" is grammatically the subject of "fixes," which isn't the intended meaning (the 2-bit tally design is what fixes the bug). Also the sentence right before it ("The counter-serialised credit return (the credit-return counter in noc_router.sv).") is a fragment with no verb. Content is recoverable from context and matches the companion doc's fuller description of the same fix, but this needs a copy-edit pass — it's the one place in the fabric section that's hard to parse on a first read. Nice touch, unrelated to the grammar issue: this is also the passage that explicitly credits "reviewer-flagged" for the NUM_VCS>4 extension note — glad the Round-1 note was useful, but worth cleaning up the sentence itself.

### 🟡 F. §VII-A promises wall-clock-per-instance data "in Appendix D"; Appendix D doesn't have it

"Xsim wall-clock per instance is listed in Appendix D." Appendix D (Table VIII) contains only per-(N-bucket, topology) *cell counts*, not any timing figures — and per finding A, even those counts don't sum right. Either the wall-clock breakdown was meant to be a separate table that didn't make it into this draft, or the reference should point to the released artifact (`live_hw_results_p1_maxpe.csv`) instead of "Appendix D." Doesn't affect any claim made in the main text — the aggregate figures (821.5 core-hours, 99s median, 5.51h longest run) don't depend on the reader seeing the per-instance table — but it's a broken forward-reference a careful reader will trip on.

---

## 3. Also re-verified — no issues found

For completeness, since this is a rigor-focused review: I re-checked Table III's bit/Mbit arithmetic (37,000-bit router subtotal, 144+256=400 Mbit aggregate — exact), the mutation-detection reconciliation (53+54=107 detected, +1 excluded on N=8192 = 108 run — exact), Table IV's HW-configs column summing to 2,822 exactly, and the tree-DP/graph-partition/hierarchical win-share percentages in §VII-E and Appendix B (all reconcile to the stated 39-instance denominator). The new "Remark (Why address reuse does not break the gate)" in §III-C is a genuinely good addition — it closes a real question (why doesn't DMEM slot recycling break the single-writer invariant the scoreboard depends on?) with a clean structural argument rather than an assertion. No issues in any of this.

---

## 4. Open questions for the authors

These are places where I can't resolve the ambiguity from the text alone — they need the actual RTL or your intent, not more careful reading on my end:

1. **VC-steering bit: 63 or 64?** Given the companion doc's own stated rationale (avoiding the FP64 sign bit) only makes sense if it's bit 64, I'd guess §IV's "packet bit 63" is the stale line — but please confirm against `noc_router.sv` directly rather than taking my word for it, since this is exactly the kind of thing where I'd rather you check the RTL comparison line than trust a re-reading of the prose.
2. **Fat-tree port count: is `MAX_PORTS=8` actually a hard cap, or does fat-tree exceed it?** If fat-tree genuinely needs 9+ ports, then `MAX_PORTS=8` (Table III, §IV-A, Appendix A) is wrong wherever it's stated as universal, and Table III's resource estimate understates fat-tree routers specifically. If fat-tree stays within 8 ports, the companion doc's "port numbers above seven" warning is the one to fix. This is a real fork, not a wording nit — I can't tell which side is true from the documents alone.
3. **Table VIII**: which two cells are the extras (or which two are missing from the "40")? Worth a quick regeneration from the actual instance-suite manifest rather than a manual fix, given this is the second table-arithmetic slip found across two review rounds.

---

## 5. Updated verdict

**Recommendation: Weak Accept** (up from Weak Reject in Round 1).

The science hasn't changed — it's the same argument, the same 2,822 validated configurations, the same non-vacuous mutation oracle — but it's now survived two independent rounds of adversarial computational re-derivation without a single defect found in the actual claims. The one finding that looked like it threatened the central thesis turned out to be my misreading of an ambiguous-in-prose (now clarified) definition, not a bug in your data. That's a meaningfully stronger position than Round 1 ended on.

What's left is craftsmanship, not correctness: two unresolved but checkable factual contradictions (VC bit, fat-tree ports) that need five minutes against the RTL to close, one recurring numbering slip (Property 1/2, three locations, still unfixed after being flagged once), and a small crop of new arithmetic/prose slips (Table VIII, Appendix E×2) that suggest the paper would benefit from one more pass — ideally a script that greps every number that's stated more than once (instance counts, win-shares, K-values, ρ) and diffs them against each other, given that's exactly the category where issues keep surfacing.

**Informal acceptance probability: ~40–55%**, up from ~15–20% in Round 1 — contingent mainly on (a) resolving the two open RTL questions above one way or the other, (b) a final consistency pass catching what Table VIII/Appendix E suggest might still be lurking elsewhere, and (c) TPDS reviewers' tolerance for the still-undisclosed-baseline gap (L1b), which is honestly written up but is the kind of thing a tough reviewer could still hold the paper on regardless of how well it's disclosed.

**Priority order for the next pass:**
1. Resolve VC-steering bit against RTL; fix whichever side is wrong (companion §IV most likely).
2. Resolve fat-tree port count against RTL; fix Table III / §IV-A / Appendix A or the companion doc, whichever is wrong.
3. Fix Table VIII to actually sum to 40.
4. Fix Appendix E prose (both occurrences, including §X-L6) to match its own table.
5. Global find-replace "Property 2" → "Property 1" (3 remaining instances: main paper §III-D header, main paper "Remark (On Property 2)", companion §III-D closing sentence).
6. Copy-edit the §IV-H credit-counter paragraph.
7. Fix Definition 5's "Definition 2" → "Definition 3".
8. Fix or repoint the §VII-A "Appendix D" wall-clock reference.

Everything on that list is mechanical. None of it requires new experiments, a new baseline, or a rewritten argument.