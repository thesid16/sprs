# Peer Review: "Bitwise-Reproducible Reduction Across Cluster Reshape: A Compiler/Fabric ABI" + Hardware Companion

**Reviewed as:** submission to IEEE TPDS (main paper, 24pp incl. appendices) plus the accompanying hardware-implementation reference document.
**Reviewer stance:** strict, adversarial pre-submission review. Every equation, table, and numeric claim below was either re-derived by hand or independently recomputed; I did not take correctness on faith.

**Methodology note, so you can reproduce my checks:** I re-implemented the canonical-tree construction (Def. 2), the leaf-value formula (Eq. 11), and the post-order FADD reduction (Eq. 4) from scratch in Python and (a) validated it against both worked examples in the paper (Appendix C's N=4 case, Fig. 1's N=8 leaf enumeration — both reproduced exactly), then (b) recomputed all 16 root values in Table IV, then (c) spot-checked three of the more specific factual claims in Related Work against public documentation. Findings from that process are folded in below with 🔴/🟠/🟡/🔵 severity tags (Critical/Major/Minor/Optional). I flag my confidence level explicitly wherever I'm inferring rather than certain.

**Up front, what's genuinely strong here:** the internal arithmetic self-consistency of this paper is well above average — I checked the 2,822/39-instance/7,200-config/22,000-point/algorithm-win-share numbers across Tables IV, VI, VII, Appendix E and every one of them reconciles exactly (shown below where relevant). The mutation-testing methodology (escalating the flip until the oracle itself confirms the root moved) is genuinely careful and self-aware. The limitations section (X) is unusually honest — flagging the missing baseline, the N=8192 shortfall, and the measurement-bug re-run rather than hiding them is exactly what a strict reviewer wants to see, and it costs you less credibility than leaving them for a reviewer to find unassisted. That said, there are several internal contradictions serious enough that, as currently written, I would not let this go out.

---

## 1. Novelty and Contribution

This needs to be said plainly before the line items, because it colors how a TPDS reviewer will read everything else.

Once you accept the ABI framing (operand binding is a function of tree-node identity alone, fixed at compile time, read by address under a scoreboard gate), Claim 1 is close to a direct unwinding of the definitions rather than a discovered result — and the paper itself says as much ("not a new component but the interface observation," "argued... not... mechanised proof"). That's fine as a contribution *shape*, but the theoretical apparatus built around it — 15 individually lettered/labeled assumptions, four "Arguments," a "Claim," a "Property," a "Theorem" — is more formal machinery than the depth of the underlying insight really needs, and a methodologically strict reviewer (there's usually at least one on a PDS-adjacent paper) may read this as dressing up a fairly intuitive point ("if every PE always adds the same predetermined pair of addresses, timing and physical location can't matter") in theorem-grade notation. The genuinely hard, valuable part of this paper is not the theory — it's that you built 3,738 lines of SV implementing this discipline, ran it through 2,822 RTL-validated configurations across six topologies and G up to 4096, and it never broke. That's a real, checkable, unglamorous engineering result, and it is currently under-sold relative to the theory section's length. **Suggested fix:** state explicitly, early (even in the abstract), that invariance-by-construction is definitional given the ABI, and reframe the contribution as *"we show this discipline survives contact with a real compiler search space and real RTL at scale, which is not guaranteed"* — then trim Section III's formal apparatus by 30–40%, keeping Theorem 1 (the orthogonality result) since that one is the least obvious part of the theory.

Related work (SHARP, P4-programmable switches) is the correct comparison class and is fairly treated, though "ideologically adjacent... framing as a size-indexed ABI... are new" (§IX-C) is a claim of framing-novelty, not results-novelty — worth being explicit about that distinction to preempt a reviewer who reads it as an overclaim.

---

## 2. Section-by-Section Issues

### Abstract / framing

🟡 **Minor — abstract doesn't disclose the one un-validated instance.**
*Location:* Abstract, "On 40 instances... 2,822 RTL-validated configurations produce bit-identical roots."
*Problem:* A reader has no way to know from the abstract that 1 of the 40 instances (N=8192, G=4096, fat-tree) never actually completed hardware validation (§X, L0) — the abstract's "40 instances" and the results' "39 of 40" are technically consistent (2,822 is still correct) but the phrasing invites the wrong inference.
*Fix:* "...on 40 instances (39 hardware-validated)..." — six words, closes the gap.

🔵 **Optional — venue framing.** The user's submission note calls this "TDPS"; the paper itself correctly says TPDS throughout. Almost certainly just a slip in the review request, not the manuscript — flagging only so it doesn't propagate into a cover letter.

### Section II — Background & Threat Model

🟡 **Minor — Eq. (1) applied to the wrong quantity.**
*Location:* §II-A, Eq. (1) and the surrounding text.
*Problem:* The classical bound as commonly stated (Higham [9]) bounds the error of *one* summation order against the true sum: `|Σ_σ x_i − Σx_i| ≤ (N−1)u Σ|x_i| + O(u²)`. The paper applies this same expression directly to the *difference between two orders*, `|Σ_σ − Σ_σ'|`. By triangle inequality that difference is bounded by *twice* the single-order expression, not the expression itself.
*Why it matters:* It's motivating text, not load-bearing for any later claim, so this doesn't threaten anything downstream — but a numerical-analysis-literate reviewer will notice a bound stated without its constant.
*Fix:* Either insert "up to a factor of two" or restate as bounding each order separately then combining via triangle inequality.

### Section III — Theoretical Core

🟠 **Major — Property numbering is inconsistent in four places, including the abstract.**
*Location:* Abstract ("fail-stop under assumption violation (Property 2)"); Intro C1 ("Property 2 (fail-stop fabric) establishes..."); Fig. 2 caption ("Property 1 rests additionally on..."); §III-D formal definition environment (**"Property 1 (Fail-stop fabric)"**); the very next line, "**Remark (On Property 2)**," referring to the same fail-stop property.
*Why it's a problem:* There is only one fail-stop property defined anywhere in the paper. It's called "Property 2" in the abstract and introduction, "Property 1" where it's actually formally stated, and then "Property 2" again one paragraph later. This reads as a leftover from a restructuring (perhaps an earlier draft had two separate safety properties that got merged) where the renumbering wasn't propagated. It's exactly the kind of inconsistency that undermines a reader's trust in the paper's proofreading, in a section whose whole point is precision about what depends on what.
*Fix:* Pick one number (I'd suggest keeping "Property 1" since that's what the `\newtheorem` environment actually instantiates) and grep-replace every other instance, including the abstract.

🟡 **Minor — worked examples never exercise the non-power-of-2 case.**
*Location:* Fig. 1 (N=8) and Appendix C (N=4) — both powers of two.
*Problem:* I verified this computationally: for power-of-2 N, numeric heap-index order among leaves coincides with left-to-right traversal order, so `idx(node) = node − (N−1)` works as a mental shortcut. For non-power-of-2 N it does not. Concretely, for N=7, I get true left-to-right leaf order `[7,8,9,10,11,12,6]` — node 6, the *smallest* heap index among the leaves, is the *last* leaf left-to-right, not the first. Seven of your sixteen evaluated N values (10, 50, 100, 200, 500, 1500, 3000) hit this case, and neither illustrated example shows it. This is a genuine subtlety in a definition (Def. 2's "left-to-right order") that both your own pedagogical examples happen to paper over.
*Fix:* A one-paragraph aside with a small odd-N example (N=5 or N=7 is small enough to draw) showing that FBT(N) is depth-imbalanced and that `idx` is genuinely a traversal, not an offset, would close this and pre-empt a reviewer re-deriving it themselves (as I had to).

🔵 **Optional —** `R_observed` is introduced with 8 arguments in Claim 1's statement and used with 2 in Theorem 1 (others implicitly fixed). Standard practice, but a footnote noting the fixed arguments would help.

### Section IV / Fabric — cross-checked against the hardware companion document

This is where I found the most serious issues, because the companion document is explicitly pitched as authoritative implementation detail ("the detail a reimplementation would require") — so a reader is entitled to expect it agrees, field-for-field, with the main paper.

🔴 **Critical — the instruction word width is stated as two different numbers within the *same* main paper, and the companion document agrees with only one of them.**
*Location:* Appendix A ("The 32-bit instruction word is: opcode|4b ∥ aux|8b ∥ dest|10b ∥ addr|10b... The dest and addr fields are DMEM addresses") vs. Table III ("Per-PE IMEM (512 × 64) + DMEM (512 × 64) = 65,536" — i.e., a **64-bit** instruction word) vs. the companion document §II-A (64 bits, with **three separate** fields — `dest`, `addr_a`, `addr_b` — each 16 bits).
*Why it's a problem:* This isn't a companion-doc-vs-main-paper mismatch you could wave off as "the companion doc is more detailed" — Table III, inside the *main paper itself*, computes IMEM storage assuming 64-bit instructions, directly contradicting Appendix A's 32-bit, single-`addr`-field description two pages later. And a single `addr` field can't even encode a COMPUTE instruction as Table II defines it ("Read DMEM[addr_a], DMEM[addr_b]") — COMPUTE needs two source operands. Appendix A reads like a stale instruction format from an earlier ISA revision that never got updated when the design moved to the dual-address 64-bit encoding used everywhere else (Table II, §III-B, §IV-D, the companion doc, and Table III's own resource math).
*Fix:* Delete/rewrite Appendix A to match the companion document's 64-bit, `opcode|aux|dest|addr_a|addr_b|reserved` layout. This is a five-minute fix but it's the single most damaging inconsistency in the package — it's in an appendix explicitly meant to be *the* precise ISA reference.
*Suggested replacement:* Mirror the companion doc's Section II-A table verbatim (with field widths 4/4/16/16/16/8 = 64b) rather than maintaining two independent descriptions of the same ISA.

🟠 **Major (borderline Critical) — the companion document's stated VC-steering bit contradicts the main paper's explicit, load-bearing claim about it.**
*Location:* Companion doc §III (Compute Node...): "Bit 63 of the payload additionally steers the virtual channel" — vs. main paper §IV-C / Fig. 3 / Eq. 9: VC-select is header bit **[64]**, explicitly *outside* the 64-bit payload field `[63:0]`, with the main paper stating at length: *"VC selection is a function of a header bit, not any payload bit. Were VC selection payload-dependent, contention and buffer occupancy would be value-dependent... Header-only VC steering therefore plays a role in the empirical-repeatability argument."*
*Why it's a problem:* Bit 63 of a 64-bit FP64 payload **is the sign bit of the reduced value**. If the companion document is the accurate one, VC selection would be literally payload-dependent (sign-dependent) — precisely the property the main paper spends a paragraph arguing does *not* hold and leans on for its "cycle counts are value-agnostic" reasoning (used to justify that a fixed synthetic leaf-value formula, rather than a swept distribution, is a sufficient empirical setup). It doesn't touch Claim 1 (which never depends on VC choice), but it does undercut the specific "empirical-repeatability" argument the main paper makes about *why the fixed leaf-value formula (Eq. 11) is a sufficient test distribution for cycle-count behavior*.
*My confidence:* I'm fairly confident this is a companion-document erratum (probably meant to say "bit 64," or "the bit immediately above the payload") rather than a real hardware bug, given how carefully and repeatedly the main paper argues the header-only property — but I can't rule out the reverse from the documents alone, and this is exactly the kind of detail a hostile reviewer checks by reading both documents side by side (as I just did).
*Fix:* Resolve which document is correct against the actual RTL (`noc_router.sv`'s VC-select comparison) and correct whichever is wrong before submission. Given the companion doc's stated purpose, getting this specific bit position wrong there is the more consequential direction to fix.

🟠 **Major — the fat-tree port count appears to exceed the paper's own stated `MAX_PORTS=8` architectural cap, and Table III's resource estimate doesn't account for it.**
*Location:* Companion doc §II-C: "`route_table` elements are ⌈log2(NUM_PORTS)⌉ bits wide. Most topologies use five-port routers, giving three bits, but fat-tree routers have more ports and need four [bits]... any tooling that writes the table with a sized literal (3'dp) silently truncates port numbers above seven." vs. main paper §IV-A: "`MAX_PORTS = 8` ports per router" (hard cap) and Table III's resource estimate, which computes routing-table width as ⌈log2(8)⌉ = **3 bits, uniformly, for every topology including fat-tree**, at G=4096.
*Why it's a problem:* ⌈log2(8)⌉ is exactly 3, not 4 — so the companion doc's own warning ("port numbers above seven" get truncated) is only meaningful if fat-tree routers actually use port index 8 or higher, i.e., **more than 8 total ports**, which would violate the stated `MAX_PORTS=8` cap. Given the evaluation includes fat-tree instances up to G=2048 (Table IV, N=4096 row), where switch radix plausibly does need to grow past 8 to keep tree depth bounded, this looks like a real, not hypothetical, edge case — meaning Table III's headline resource-envelope number likely *undercounts* the routing-table bits for the fat-tree configurations actually run in this paper's own evaluation.
*Fix:* State explicitly whether any evaluated fat-tree instance exceeds 8 ports per router. If none do, soften the companion doc's warning to "a future-extensibility note, not triggered in this evaluation." If some do, correct Table III (or note the fat-tree row separately) and reconcile against `MAX_PORTS=8`.

🟡 **Minor — "credit-pulse counter" (2 bits) is easy to confuse with the per-link credit *balance* counter (8 bits).**
*Location:* Main paper §IV-H ("At NUM_VCS = 2 the counter is 2 bits, sufficient at BUF_DEPTH = 8") vs. companion doc §IV ("an eight-bit credit counter per link").
*Why it's a problem:* Read in isolation, "2 bits... sufficient at BUF_DEPTH=8" looks wrong (2 bits can't count to 8) until you realize §IV-H is describing a *different* counter — the same-cycle multi-VC read-event tally used to fix the credit-loss bug, not the credit balance register. Both numbers are internally consistent once you know which counter is which, but nothing in the text disambiguates them, and given how much emphasis the paper places elsewhere on precise bit-widths (the fat-tree routing-table warning above is a perfect example of why precision matters here), this deserves one clarifying clause.
*Fix:* "...the *per-cycle read-tally* counter (distinct from the 8-bit per-link credit balance) is 2 bits..."

### Section V — Compiler

🔵 **Optional — the "122 configurations" from 12 base refinement methods isn't derived anywhere.** A one-line formula (or an appendix footnote) showing the combinatorial rule (all pairs? all chains up to length k?) would let a reader independently check 18×10×122≈22,000 rather than take it on faith. I could not reconstruct it from the given text.

### Section VI — Evaluation Methodology

🟠 **Major — the symbol `K` in the Ω lower-bound formula (Eq. 10) is never defined.**
*Location:* Eq. (10), `Ω = max_{K∈[Kmin,Kmax]} max(lb_span, lb_gen(K), lb_instr(K), lb_comm, lb_gather, lb_bis)`.
*Why it's a problem:* `K`, `Kmin`, and `Kmax` appear nowhere else in the text provided. Ω is not a side quantity — it's the yardstick for the entire "cost of the ABI" argument in §VII-D (Tables V, VI, Figs. 5–6 all report `cycles/Ω`), which is doing a lot of work in this paper precisely *because* the paper admits it has no measured non-deterministic baseline (see next item). A central equation with an undefined free variable is a real reproducibility gap, not a style nit.
*Fix:* One sentence stating what `K` physically represents (channel count? window size? something else) and why maximizing over its range yields a bound valid for *any* schedule (the more usual move for "valid regardless of an implicit parameter" would be to minimize, not maximize, over its range — worth a sentence justifying the direction chosen).

🟠 **Major (self-acknowledged, but under-weighted in the framing) — no non-deterministic baseline is ever measured.**
*Location:* §VI-B, §VII-D, §X (L1b).
*Why it's a problem:* You're candid about this (L1b: "the principal open item"), which I want to credit — but I'd push back on how much weight the structural pricing (§VII-D) is asked to carry as a substitute. `cycles/Ω` upper-bounds what *any* scheduler, deterministic or not, could have saved (Ω bounds every schedule on the fabric, not specifically non-deterministic ones), so it answers a *different* question than "what does determinism cost you." The falsifiable-prediction exercise (next item) is a genuinely clever partial substitute, but a TPDS reviewer evaluating the practical case for this ABI is very likely to ask for at least a naive non-deterministic reducer on the same substrate (even an unoptimized one, clearly labeled as a floor rather than a ceiling) before accepting the "affordable" framing implicit in the discussion section.
*Fix:* Even a single naive ND-Ring baseline, explicitly caveated as un-optimized, would change this from "we have no data point" to "we have a lower-effort data point plus a structural argument for why it's a lower bound on the gap." That's a much easier ask than fully re-engineering a competitive non-deterministic scheduler.

🟡 **Minor — per-instance sample size behind the Appendix E Spearman correlations isn't given.**
*Location:* Appendix E table (K=10/15/30, median ρ≈0.95, median leakage 0.30/0.20/0.10).
*Why it's a problem:* Each ρ is computed within a single instance's set of evaluated configurations; if that set is small for some instances, a per-instance ρ can be unstable, and a median-of-ρ across instances doesn't surface that. (The K=30 row correctly drops to 32 "instances," presumably because instances with <30 evaluated configs can't contribute to that statistic — worth stating explicitly, since it's a reasonable but currently unstated inference.)
*Fix:* Report the distribution (or at least min/max) of evaluated-configuration counts per instance alongside the ρ table.

### Section VII — Results

🔴 **Critical — Table IV's N=200 root value does not reproduce under independent re-implementation.**
*Location:* Table IV, N=200 row: `0x41732B4046666667`.
*What I did:* I implemented Def. 2 (canonical tree), Eq. (11) (leaf formula), and Eq. (4) (post-order FADD evaluation) from the paper's own text, in three independent ways — recursive top-down, iterative bottom-up over an explicit heap array, and with leaf constants computed via exact decimal arithmetic before the final round-to-double. All three agree with each other and with a fourth check (summing all 200 leaves in exact/infinite precision and rounding once). All four give **`0x41732B4046666666`** — one hex digit off from the table, specifically the last nibble (**6** vs. the table's **7**), i.e. exactly **1 ULP**.
*Why this matters more than "off by one bit" sounds:* My reconstruction reproduces all *other* 15 rows of Table IV bit-for-bit exactly, including several other non-power-of-2 N (10, 50, 100, 500, 1500, 3000) that exercise the same depth-imbalanced-tree code path as N=200 — so this isn't a systematic bug in my re-implementation of your algorithm; it's specific to this one row. And a 1-ULP discrepancy in the flagship results table of a paper whose entire thesis is bitwise precision is the single easiest thing for an adversarial reviewer to catch and the most damaging to find unassisted — it invites exactly the "if I can't trust this row, why should I trust the other 15" reaction, even though (per my check) the other 15 are fine.
*My confidence:* High that there's a real discrepancy between what Def. 2/Eq. 4/Eq. 11 as literally stated produce and what Table IV reports for N=200 specifically; I can't be certain whether the cause is a transcription slip when the hex value was copied into the table, or something in the actual pipeline (e.g., leaf-migration re-ordering interacting with N=200 specifically, though L8 suggests that's a mapping-only effect that shouldn't touch the canonical root) that isn't visible from the paper text alone.
*Fix:* Re-run your own Python oracle (`sprs_core.py:702--867`) standalone against Eq. 11's leaf formula for N=200 and diff it against both what's in Table IV and what I report above. This is checkable in under a minute and needs to be resolved (even if the resolution is "yes, table typo, fixed") before submission.

🟠 **Major — §VII-D-3 references a "term 5" that does not exist.**
*Location:* "First, the topology ordering in Table VI tracks bisection width **as term 5 implies**..."
*Why it's a problem:* §VII-D-1 enumerates exactly **four** structural cost terms (FBT tree depth, operand-binding/no-reassociation, GCI serialisation, root-gather fan-in), numbered 1–4. There is no term 5 anywhere in the paper. This reads as a leftover from an earlier draft that had a fifth (bisection-width) term, later folded into term 4 or cut, without the cross-reference being updated.
*Additional wrinkle worth resolving while you're in there:* the claimed direction of the bisection-width effect is non-obvious as written — linear topology (typically the *worst*-bisection-width topology of the six) has the *best* (lowest) `cycles/Ω` in Table VI (1.39), and ring (also low-bisection) has the *worst* (4.48). If the intended mechanism is "Ω itself already prices in the bisection constraint via `lb_bis`, so low-bisection topologies have less achievable slack and therefore land closer to their own (elevated) bound" — that's a defensible and actually interesting point, but it's the opposite of the naive reading of "tracks bisection width," and it isn't spelled out.
*Fix:* Renumber/re-derive the missing term, and add one sentence making the "Ω already accounts for bisection, so this ratio measures tightness-to-bound rather than raw speed" mechanism explicit.

🟠 **Major — the "falsifiable prediction" in Table V / Fig. 5 doesn't rule out confounds.**
*Location:* §VII-D-2, the N/G-banding argument for the GCI-serialization inflection at N/G≈6–8.
*Why it's a problem:* This is a nice piece of methodology — pre-registering `gci_gap=6` as the predicted knee location rather than fitting it post-hoc is a real strength, and I want to be clear I'm not disputing that framing. But the five N/G bands (4.16 → 3.96 → 3.28 → 1.91 → 1.37, monotonically decreasing) don't obviously isolate the GCI-serialization term specifically from other things that correlate with larger N/G in this instance suite — topology mix, G, and winning-algorithm family all plausibly co-vary with N/G band too, and any of them could independently produce a declining `cycles/Ω` trend. The single largest relative drop (crossing (6,8]→(8,32], −41.8%) is consistent with the predicted knee, but with only 2 instances in the top band and no control for the other covariates, "the prediction holds" is currently a plausibility check rather than an isolation of the mechanism.
*Fix:* Either regress out the modeled GCI term (`6⌈N/G⌉` cycles, a directly computable quantity from your own cost model) from the total and show the *residual* still exhibits the same qualitative pattern, or explicitly caveat that this is correlational corroboration, not a controlled test.

🔵 **Optional — minor precision mismatch between prose and table.** "Identity wins 62% of instances" (§VII-E prose) vs. 24/39 = 61.5% (Table VII). Not wrong, just inconsistent rounding precision between the two.

### Section IX — Related Work / Citations

I spot-checked the more specific and checkable claims here against public sources rather than trusting memory alone.

🟠 **Major — reference [23]'s topic annotation doesn't match the cited work.**
*Location:* Bibliography, [23]: "P. Koopman, 'Stack computers: The new wave,' in Ellis Horwood, 1989, **classic reference on virtual-channel discipline and wormhole forwarding**."
*Why it's a problem:* I checked. Koopman's 1989 book is exactly what its title says — a survey of stack-based (Forth-style) processor architectures (the Novix NC4016 and similar machines), covering hardware stack support, instruction sets of specific stack processors, and software issues for stack machines. It has no connection to virtual-channel flow control or wormhole routing, which are Dally-lineage NoC concepts (and Dally & Towles is already correctly cited as [24] for exactly that material). I could not find [23] cited inline anywhere in the body text either — if it's genuinely uncited, IEEE TPDS format requires every reference to be cited at least once.
*Fix:* Either this citation is simply wrong (wrong paper attached to this description — check whether you meant an actual Dally wormhole-routing paper) or the annotation is a leftover from reference-manager cleanup. Either way, fix before submission — a reviewer who checks even one reference and finds this will discount the whole list.

🟡 **Minor — reference [22] is cited in a way that reads as supporting the wrong clause.**
*Location:* §IX-B: "Tree-construction algorithms for communication — Huffman trees [22], TreeMatch's topology-aware trees..."
*Why it's a problem:* [22] is Jeannot, Mercier & Tessier's "Process Placement in Multicore Clusters" (IEEE TPDS 2014, incidentally the same venue you're submitting to) — the actual origin paper for TreeMatch, not for Huffman coding (which dates to 1952 and has no citation here at all). As placed, the sentence reads as citing [22] for "Huffman trees," which is a misattribution; it's clearly meant for "TreeMatch."
*Fix:* Reorder: "Tree-construction algorithms for communication — Huffman trees, TreeMatch's topology-aware trees [22]..." (and consider adding an actual Huffman citation if the comparison is meant seriously).

🔵 **Positive note, not a criticism:** I checked "NCCL_ALGO=Tree with a single channel" against current NCCL documentation — this is accurate; NCCL_ALGO does support pinning to Tree, and channel count is separately controllable. No issue here, flagging only because I did check it.

### Section X — Limitations

No issues to raise — this section is a model of the genre. L0 through L12 read like the authors actually tried to break their own paper, which is precisely what's being asked of me in this review. I'd only add L1b (no measured baseline) and the Table IV N=200 discrepancy above it in urgency, once fixed, rather than changing anything about how this section is written.

---

## 3. Final Verdict

### Overall assessment

The core scientific claim (bitwise invariance under an ABI that fixes operand binding by tree-node identity) is sound and, as best I can verify, not threatened by anything I found — it follows fairly directly from the stated definitions, and the paper is honest that its support is structural argument plus extensive dynamic/RTL testing rather than mechanised proof. The engineering behind it is real and the internal-consistency of the *evaluation numbers* (funnel counts, win-share percentages, mutation-detection counts, per-N instance/config tallies) is excellent — I checked a dozen-plus cross-table arithmetic relationships and every one reconciled exactly. Against that: the paper currently contains a genuine self-contradiction about its own instruction word width spanning an appendix and a table, a companion document that disagrees with the main paper on a bit position the main paper explicitly argues matters, inconsistent numbering of one of its two headline properties (including in the abstract), one un-reproduced value in its central results table, a broken cross-reference to an undefined "term 5," an undefined symbol in a load-bearing equation, and two citation problems. None of these threaten Claim 1 itself, but collectively they're more than "polish" — they're the kind of thing that erodes a reviewer's confidence in everything else in a 24-page, notation-heavy paper, and several are trivially fixable without new experiments.

### Recommendation

**Weak Reject** (i.e., not ready as submitted; resubmittable after a focused revision pass — most of what's below doesn't require new experiments, with the honest exception of the missing baseline).

### Top 10 issues to fix before submission, ranked

1. 🔴 Table IV, N=200 root value — independently unreproduced; verify against your own oracle.
2. 🔴 Appendix A instruction-word format contradicts Table III and the companion doc (32-bit/1-addr vs. 64-bit/2-addr).
3. 🟠 Companion doc VC-steering bit ("bit 63 of payload") contradicts the main paper's explicit header-bit-64 argument.
4. 🟠 Property 1/Property 2 numbering inconsistent across abstract, intro, Fig. 2, and §III-D itself.
5. 🟠 Fat-tree port count vs. `MAX_PORTS=8` vs. Table III's uniform 3-bit routing-table assumption.
6. 🟠 No measured non-deterministic baseline; `cycles/Ω` is being asked to answer a question it doesn't answer.
7. 🟠 "Term 5" referenced in §VII-D-3 with only four terms ever defined.
8. 🟠 Reference [23]'s annotation describes a paper unrelated to its actual content (and appears uncited).
9. 🟠 Undefined `K` in the Ω formula (Eq. 10), which everything in §VII-D is measured against.
10. 🟠 Novelty framing: streamline Section III's formalism and foreground the at-scale RTL validation as the real contribution.

### Acceptance probability

**~15–20% in current form.** This is an informed estimate, not a prediction — it reflects a paper with a sound core claim and unusually strong internal numerical hygiene everywhere except the specific spots flagged above, submitted with several reviewer-visible self-contradictions that are individually easy to fix but collectively suggest an incomplete final proofreading pass. After the top-10 fixes (excluding the baseline, which is genuinely more work), I'd expect this to be a plausible Weak-Accept/Accept on a resubmission or major-revision cycle, since none of the identified issues touch the correctness of Claim 1 itself.

### Reviewer-style summary

*This paper proposes treating reduction order as a compiler/fabric ABI to achieve bitwise-reproducible collective reductions under cluster reshape, and backs the claim with a real SystemVerilog NoC, a seven-stage compiler, FPGA bring-up, and a large RTL validation campaign (2,822 configurations, zero divergence, 107/107 mutation detection). The central invariance argument is sound, if largely definitional given the stated ABI, and the paper is commendably candid about its limitations, including the absence of a measured non-deterministic baseline. However, the submission is not yet internally consistent: the instruction-word format is described two incompatible ways within the main paper itself (Appendix A vs. Table III), the hardware companion document's stated virtual-channel steering bit contradicts a claim the main paper explicitly relies on, the fail-stop property is inconsistently numbered including in the abstract, one entry in the headline results table (N=200) does not reproduce under independent re-implementation of the paper's own stated algorithm, and two references have accuracy or attribution problems. None of these threaten the core result, and most are correctable without new experiments, but their number and visibility (appendix, abstract, headline table) warrant a revision pass before this is ready for TPDS review.*

---

## 4. Pre-Submission Action Plan (most urgent first)

1. **Re-verify Table IV's N=200 root** against your own Python oracle standalone; fix the table (or figure out why it disagrees, which would be the more important finding).
2. **Fix Appendix A** to match the 64-bit, dual-address instruction format used everywhere else (companion doc, Table II, Table III, §III-B).
3. **Resolve the VC-steering bit** between the companion doc ("bit 63 of payload") and the main paper (header bit 64) against the actual RTL.
4. **Grep for "Property 1" / "Property 2"** across the whole manuscript and make it consistent, starting with the abstract.
5. **Check whether any evaluated fat-tree instance exceeds 8 ports**; fix Table III or the companion doc's port-width claim accordingly.
6. **Find/renumber the missing "term 5"** in §VII-D-3 and make the bisection-width mechanism explicit.
7. **Define `K` in Eq. (10)** and justify the max-over-K.
8. **Fix reference [23]'s annotation** (or replace the citation) and reorder the [22] citation next to "TreeMatch."
9. **Add a naive non-deterministic baseline**, even unoptimized and clearly labeled as a floor — this is the one item here that costs real time, but it's the difference between "we priced this structurally" and "we measured this."
10. **Trim/reframe Section III**: state up front that invariance is by-construction given the ABI, foreground the at-scale RTL validation as the actual contribution, and cut the formal apparatus that isn't carrying its weight (start with anything not feeding Theorem 1).
11. Lower-priority polish once the above is done: the Eq. (1) factor-of-two, the power-of-2-only worked examples, the credit-counter disambiguation in §IV-H, the 62%/61.5% rounding mismatch, and showing the 12→122 refinement-chaining derivation.
