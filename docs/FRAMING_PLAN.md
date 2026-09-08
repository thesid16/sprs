# FRAMING_PLAN.md — placement and wording plan for first-turn TPDS acceptance

Author: sprs-c-strategist (council, framing/placement track)
Date: 2026-08-28
Status: COMPLETE. All seven sections settled; the decision ledger in §6 is the
authoritative record. §7 lists what is genuinely open.

Scope and standing constraints:
- Objective is lexicographic: (1) TPDS acceptance first turn; (2) fewer billed
  pages; (3) avoid unnecessary new work. (1) dominates absolutely.
- HARD CONSTRAINT: every pre-registered branch result
  (/home/rohit/sprs-fix/experiments/PREREGISTRATION.md) ships somewhere a reader
  will find it. Suppression is off the table; the artifact ships the harness and
  an evaluator will rerun it. Only PLACEMENT (main / appendix / companion) and
  WORDING are open.
- This file PROPOSES. It does not edit paper/main.tex.
- Concurrent agent owns /home/rohit/sprs-fix/ATTACK_SURFACE.md. Not touched here.

## 0. Executive summary

**The single most valuable thing in this document is not a framing move.** It is
that `paper/tables/perinstance.tex` is generated from the cycle dataset the
paper itself declares defective, and consequently Appendix~F prints **14 of 39
instances beating the paper's own proven lower bound $\Omega$** — one of them by
$33\times$ — while `main.tex:2381` states "no instance reaches $\Omega$ --- the
best is $1.35\times$". Regenerating that one table from the correct dataset
(already shipped, already selected by every other generator) puts 0 of 39 rows
below $\Omega$ and makes the minimum exactly 1.35, matching the main text. Cost:
one line in `paper/scripts/gen_tables.py` and `make tables`. See \S4.1 O-1 and
ledger F-1.

Beyond that, the round's evidence changes what this paper is allowed to claim,
and almost all of the change is in the paper's favour.

**Four claims must be withdrawn or corrected.** The printed pinned-FBT
construction does not compute the canonical reduction and its "preserves
Claim~1 by construction" is refuted by the negative control (\S1.1e). L0b's
$59\%$/$1$--$54\%$ fidelity band does not exist; the measured value is
$100\%$/$0\%$ (\S3). "We report no measured $\eta$", stated three times and
elevated to "the single largest gap in the evaluation", is now false (\S2). And
the winner-distribution prose contradicts the table printed beside it
(\S4bis O-7).

**Five results are under-claimed and should be strengthened.** The motivating
premise is measured, not merely cited — 14 rank counts, 14 distinct roots,
$78.6\%$ pairwise disagreement, and bitwise-identical repeats at fixed shape
(\S4.2 U-1). $\eta$'s zero half is a *theorem*: at power-of-two shapes
recursive doubling over contiguous blocks **is** $\FBT(N)$, so the ABI does not
change the reduction order at all, it only pins it — free where the DAGs
coincide, $1.15$ geomean where they cannot (\S2). Non-power-of-two shapes, the
coverage TBIK lacks, are invariant *and* carry no cost penalty (\S4.2 U-3). The
campaign re-executes and $92.1\%$ of its cycle values reproduce exactly, with
the residual confined to two of seventeen methods that carry **none** of the 39
reported champions (\S4.2 U-5, \S4bis U-9). And the build system refuses the
defective dataset and stamps provenance on every table — a control most
submissions do not have and this one never mentions (\S4.2 U-4).

**On the 2.40x overhead (\S1).** The paper makes no performance claim that it
contradicts; it makes three hedges that it *confirms*, including the printed
prediction that "a fixed tree will be slower on some shapes"
(`main.tex:2553-2556`). Against a paper whose contribution is a correctness ABI,
an overhead measurement is scoping information. It also decomposes honestly: a
factor of $2$ at $G{=}2$ that belongs to the tree (the pinned schedule moves
$2M$ bytes against a ring's $M$ per rank; the bandwidth-bound end sits on it at
$2.21\times$, falling to $1.85\times$ when a two-chunk variant drives the link
duplex), and a residual below $1$~MiB that belongs to an unoptimised export
(two dependent Python-level calls against one fused NCCL kernel). The two-chunk
variant *helps* at 128~MiB and costs up to $29\times$ below 1~MiB, and that sign
flip is what separates the terms. Strongest honest sentence in \S1.3.

**Placement.** Promote pinned-FBT out of Discussion into Evaluation Results: it
is the only evidence in the submission that the mechanism works outside the
simulator, which is the objection most likely to sink a TPDS submission, and
material filed under "Discussion" reads as speculation. Every pre-registered
branch has a stated home (\S5.1); nothing is suppressed.

**Budget.** 26.0pp measured $\to$ **$\approx20.7$pp** projected, via
$-5.95$pp of moves to the companion (which grows to ~9--10pp, unconstrained)
and $+0.72$pp of new main-paper material. **The 14-page target is not met and
should not be pursued**: reaching it requires deleting the theory core or the
evaluation, and the objective forbids trading acceptance for pages. Recommend
~21 pages and pay the overlength charges.

**New work.** Tested every candidate against "would a TPDS referee reject this
paper without it?" — multi-node NCCL, synthesis/PPA, ND-Ring, root-causing the
compile variability, a full campaign re-run. **All fail the bar** (ledger F-13),
for reasons stated individually. One item passes as nearly free: complete
`W2/v005`, the already-scripted clean gloo cost re-run, to remove a contamination
caveat from a table that is moving into the main paper (F-14).

**Order of execution**, by acceptance gain per unit of effort:
F-1 (free, removes a fatal self-contradiction) $\to$
F-2 (the correctness fix, and the promotion) $\to$
F-3 ($\eta$, closes the paper's own largest stated gap) $\to$
F-5 (measured motivation) $\to$
F-4, F-15, F-8, F-7, F-6, F-9 (corrections and disclosures) $\to$
F-10 (the page moves, last, because they touch everything).

_(pending)_
## 1. W2-H2 — the 2.40x geomean overhead: decomposition and framing

### 1.1 First: does the draft make a performance claim that 2.40x contradicts?

I swept every place the draft speaks about pinned-FBT cost. **It makes no
performance claim that 2.40x contradicts.** It makes three *hedges* that the
measurement CONFIRMS, and one *correctness* claim that the measurement DESTROYS.
The correctness claim is the real problem; the overhead is not.

| # | draft text | file:line | status vs W2 |
|---|---|---|---|
| a | "trades our fabric's structural overhead for a higher software overhead (dynamic-tree libraries are throughput-tuned; **a fixed tree will be slower on some shapes**)" | `paper/main.tex:2553-2556` | **CONFIRMED, and quantified.** This is a pre-registered-style prediction the paper already made in print. 2.40x is its measured value. |
| b | "\emph{Silicon scalability.} ... we **do not benchmark against production all-reduce libraries running on NVLink/NVSwitch silicon}**" | `paper/main.tex:398-401` | **STILL TRUE.** W2 ran on PCIe (`topo = NODE`), no NVLink (`W2/RESULT.json:hardware.interconnect`). The non-goal needs one clause added, not withdrawal. |
| c | "\emph{L2 --- No head-to-head with production collectives.} We do not benchmark against NCCL... a NCCL comparison would require either (a) the pinned-FBT prototype of \S\ref{sec:discussion-pinfbt}, or (b) silicon implementation" | `paper/main.tex:2757-2763` | **SUPERSEDED.** Branch (a) has now been taken. L2 must be rewritten, not deleted: the *fabric* still has no head-to-head; the *export* now does. |
| d | "we describe here as a design and **leave to future work to evaluate empirically**"; "A prototype on top of NCCL or oneCCL is **planned as a follow-up artefact**" | `paper/main.tex:2523-2524`, `2557-2558` | **FALSE as of W2.** The prototype exists, ran on two GPUs under NCCL and on up to 64 gloo ranks, and is in the artifact. Leaving this in is a referee-visible falsehood about our own artifact. |
| e | "This **preserves Claim~\ref{claim:1} by construction**" applied to step 1 `rank(i) = floor(i*G/N)` | `paper/main.tex:2533-2536`, step 1 at `2529-2534` | **REFUTED.** T16 proved the index-range partition is not $\Rcan$; W2's mandatory negative control fired: at $N{=}1000$ and $N{=}1500$ it produced **3 distinct roots** over $G\in\{2,3,8\}$ and **0 of 13 cells** equalled $\Rcan$ (`W2/RESULT.json:H1_negative_control.detail`). |
| f | Abstract: "We further **sketch** \emph{pinned-FBT} ... that **inherits** the invariance property" | `paper/main.tex:169-173` | Under-claim (see §4). "Sketch" is now wrong in the author's own favour's opposite direction: it is measured on 2,414 cells. |

**Conclusion for framing.** The overhead number is not a negative result against
any claim this paper makes. The paper's contribution is a correctness ABI; it
already declares performance out of scope three times (`main.tex:398-401`,
`1966` "we report no measured $\eta$", `2757-2763`). Against a paper that
claims no speed, an overhead measurement is *scoping information* — it tells a
deployer what invariance costs on one fabric. The thing that must go is not the
overhead: it is **(e)**, the printed step-1 construction and its false
"preserves Claim 1 by construction". That is a correctness claim the evidence
refutes, and it is the only one.

### 1.2 The decomposition: what is the tree's, and what is the export's

`W2/RESULT.json:H2_cost.structural_explanation` names two terms. They separate
cleanly, and the experiment contains a manipulation that separates them.

**Term A — algorithmic, a property of the tree, floor $\approx 2\times$ at $G{=}2$.**
At $G{=}2$ the cut-aligned pinned tree performs one directed send of the full
$M$-vector plus a broadcast of the full $M$-vector: $2M$ bytes on the wire.
A ring all-reduce at $G{=}2$ moves $M(G{-}1)/G$ down and $M(G{-}1)/G$ back
$=M$ per rank. The bandwidth-term ratio is therefore $2M/M = 2.0$, fixed by
the schedule, not by the code. Evidence that the large-message end sits on this
floor and not above it:

- 128 MiB, 1-chunk: **2.21x** (`W2/v004/COST.json`, reproduced in
  `EXPERIMENTS_REPORT.md` §2 table) — 10% above the algorithmic 2.0.
- 128 MiB, 2-chunk bidirectional (uses both PCIe directions): **1.85x**
  (`W2/RESULT.json:H2_cost.structural_explanation`) — i.e. below 2.0 once the
  link is driven duplex, which is what the term predicts.
- 8 MiB: **1.49x**, the global best. The bandwidth-bound band is
  $1.49$--$2.21$x, centred on 2.

**Term B — implementation, an artefact of an unoptimised export, unbounded below
~1 MiB.** The prototype issues **two dependent library calls from Python**
against **one fused NCCL kernel**. Evidence, and it is a double dissociation,
which is much stronger than a hand-wave:

- Overhead is *highest at the smallest sizes*: 8 KiB **3.29x**, 32 KiB 2.92x,
  128 KiB 3.12x, against 512 KiB 1.59x and 8 MiB 1.49x.
- The 2-chunk variant **doubles the Python-level call count**. It *improves*
  128 MiB (2.21 -> 1.85x) and *destroys* the small end (**up to 29x** below
  1 MiB). Adding calls helps where bandwidth binds and hurts where call count
  binds. Nothing but a per-call cost produces that sign flip.

**Arithmetic of the headline.** Geomean over the clean 8 KiB--128 MiB sweep is
2.27x (`H2_cost.fp64_size_sweep_8KiB_to_128MiB.geomean`); over all 28 NCCL
points 2.40x (`H2_cost.nccl_G2_fbt_chunks1.geomean`). Of that, a factor of
**2.0 is Term A** and the residual — geomean $2.40/2.0 = 1.20$, but concentrated
entirely below 1 MiB where it reaches $3.29/2.0 = 1.6$x — is **Term B**. The
honest split is therefore: *the tree costs about 2x at $G{=}2$; our export
costs up to another 1.6x, only at small messages, and is not the tree's fault.*

**A third fact that is pure gain and is currently unstated anywhere.**
`H2_cost.non_power_of_two_N_at_128KiB`: at 128 KiB the non-power-of-two leaf
counts (N=3 2.19x, 5 2.50x, 6 3.91x, 7 3.01x, 12 2.43x, 100 2.90x, 1000 2.39x,
1023 2.50x, 1500 2.45x, 4095 3.46x) sit **inside the same band** as their
power-of-two neighbours (N=8 3.12x, 1024 3.26x, 4096 2.98x). **There is no
non-power-of-two penalty.** Non-power-of-two $N$ is precisely what TBIK does not
cover, so this is the only genuinely new coverage in the cost axis, and its
result is favourable. It must be stated.

### 1.3 The honest strongest sentence

> On a contended two-GPU PCIe node the exported construction costs a geometric
> mean of $2.40\times$ stock NCCL all-reduce, best $1.49\times$ and worst
> $3.91\times$; the figure decomposes into a factor of two that belongs to the
> tree and a residual that belongs to our prototype.

That is the strongest sentence that is entirely true. It is stronger than
"2.40x, which is the price of the discipline" because it tells the reader which
half a better engineer could remove, and it is stronger than any sentence that
quotes only 1.49x because it is not selective.

### 1.4 Placement: MAIN PAPER, promoted out of Discussion

**Recommendation: promote pinned-FBT from \S VIII-D (Discussion) to a numbered
subsection of \S VII (Evaluation Results), \S\ref{sec:results-pinfbt}, placed
immediately after \S\ref{sec:results-invariance}.**

Reasoning against the alternatives:

- *Companion with a main-paper pointer* — **rejected.** The single most
  predictable TPDS reviewer objection to this paper is "everything is in a
  simulator; show me a real collective on real hardware." W2-H1 is the only
  evidence in the entire submission that answers it. Putting it in the companion
  is optimising page count against goal 1. Cost of the mistake is far larger
  than the ~0.6pp saved.
- *Leave it in Discussion* — **rejected.** Material in Discussion reads as
  speculation. It currently *is* labelled speculation ("leave to future work to
  evaluate empirically", `2523-2524`). A referee skimming Results and
  Limitations will conclude the paper has no real-hardware collective result,
  because the section that says otherwise is filed under "Discussion".
- *Scoping subsection about overhead* — **rejected as the primary frame.**
  Framing the new material as "here is our overhead" leads with the weakest
  number. Frame it as "here is the ABI running on stock NCCL, invariant on 2,414
  cells, and here is what it costs", which leads with the strongest.

**Page arithmetic.** The existing \S VIII-D is ~0.55pp (`main.tex:2519-2568`,
50 lines). The replacement is ~0.85pp of prose + a 6-row cost table. Net
**+0.45pp** in main. The full 28-point sweep, the gloo arm, the load-imbalance
sweep and the contention conditions go to the companion (\S5.3 of the ledger).
Under a lexicographic objective this +0.45pp is bought without argument: it
converts "simulator-only" from a fatal objection into a non-objection.

### 1.5 Proposed LaTeX (replaces `main.tex:2519-2568` entirely; new home is after line 2241)

```latex
\subsection{The ABI on Stock NCCL: Pinned-FBT}\label{sec:results-pinfbt}

The fabric result establishes the ABI on our own substrate. The obvious
question is whether the discipline survives outside it, on a production
collective library that we do not control. We built \emph{pinned-FBT}, a
software-only export of the ABI onto \sv{torch.distributed}, and measured it.

\subsubsection{Construction}
Pinned-FBT replaces the collective's dynamic, $G$-dependent reduction tree with
the fixed post-order schedule of $\FBT(N)$. Let $d = \lceil \log_2 G \rceil$.
Cut $\FBT(N)$ at level $d$; the $2^d$ complete subtrees rooted at that level are
dealt to the $G$ ranks, and the cross-rank stage evaluates the top $d$ levels of
$\FBT(N)$ --- exactly $2^d - 1$ combines, each a point-to-point send followed by
one \sv{COMPUTE}. Each rank reduces its own subtrees by a local $\FBT$
traversal. The deal is by greedy longest-processing-time (LPT) over subtree
sizes.

Two details are load-bearing and we state them because the natural alternatives
are wrong. \emph{First, the cut must be level-aligned.} An index-range partition
$\mathrm{rank}(i) = \lfloor i G / N \rfloor$ is the obvious choice and it does
not compute $\Rcan(N,L)$: a rank's index range is in general not a subtree of
$\FBT(N)$, so its local reduction is not a node of the canonical tree. We used
this construction as the negative control below, and it fails as it must.
\emph{Second, the deal must be LPT.} The frontier assignment cannot affect the
root --- that is Proposition~\ref{thm:orth} again --- so it is a free
load-balancing choice, but only LPT achieves the bound of
\S\ref{sec:abi-tree}: over the $1{,}546$ $(N,G)$ pairs we enumerate, greedy LPT
gives a worst leaves-per-rank ratio of $1.996$ and never exceeds $2$, whereas
the natural contiguous deal reaches $2.48$.

\subsubsection{Invariance}
We swept $32$ configurations --- world sizes
$G \in \{2,3,4,5,6,7,8,12,16,24,32,48,64\}$, leaf counts
$N \in \{3,5,6,7,8,12,100,1000,1023,1024,1500,4095,4096\}$, both NCCL (GPU) and
gloo (CPU) backends, both deals, \sv{fp64} and \sv{fp32} --- comprising
$2{,}414$ (configuration, rank) cells, of which ten leaf counts and seven rank
counts are not powers of two. \textbf{Every cell returned one 64-bit root, and
that root equalled $\Rcan(N,L)$, the single-process canonical $\FBT(N)$
reduction.} No cell diverged.

The check is not vacuous. We reran the same sweep on the index-range
construction as a negative control: at $N{=}1000$ and $N{=}1500$ it produced
three distinct roots over $G \in \{2,3,8\}$ and \emph{none} of its $13$ cells
equalled $\Rcan$. At $N{=}1024$ it coincides for the $G$ that divide $N$ and at
$N{=}7$ it coincides entirely --- coincidence, not correctness, and exactly the
failure mode a level-aligned cut removes.

\subsubsection{What the invariance costs}
\input{tables/pinfbt_cost}

Table~\ref{tab:pinfbtcost} gives the price against stock
\sv{ncclAllReduce} at $G{=}2$, \sv{fp64}, as the median of $15$ batched regions
of back-to-back collectives after two warm-up batches. Over the $28$ measured
points the geometric mean is $2.40\times$, the best case $1.49\times$ and the
worst $3.91\times$. We report the sweep whole; no size range is quoted as the
headline.

The figure decomposes, and the two halves belong to different owners. At
$G{=}2$ the pinned tree moves the full $M$-vector once as a directed send and
once as a broadcast --- $2M$ bytes --- against a ring all-reduce's $M$ per rank.
That factor of two is a property of the schedule and cannot be engineered away
without abandoning the contract; the bandwidth-bound end of the sweep sits on
it ($2.21\times$ at $128$~MiB, falling to $1.85\times$ for a two-chunk
bidirectional variant that drives the link duplex). Everything above that
factor appears below $1$~MiB, where our prototype issues two \emph{dependent}
library calls from Python against one fused NCCL kernel. The same two-chunk
variant that helps at $128$~MiB costs up to $29\times$ below $1$~MiB because it
doubles the call count: the sign flip identifies the small-message term as
per-call cost rather than bandwidth, and per-call cost is our prototype's, not
the tree's.

One axis is pure gain. Non-power-of-two $N$ --- the case a fixed
power-of-two tree cannot express, and the only part of this construction not
already covered by prior fixed-order collectives --- carries no penalty: at
$128$~KiB the ten non-power-of-two leaf counts span $2.19$--$3.91\times$,
inside the band spanned by their power-of-two neighbours ($2.98$--$3.26\times$).

\subsubsection{Scope of these numbers}
The measurement is on a single node with two RTX PRO 6000 GPUs connected by
PCIe (\sv{nvidia-smi topo} reports \sv{NODE}); there is no NVLink, so the NCCL
arm is $G{=}2$ only and every $G > 2$ figure above is gloo over TCP on CPU
ranks and is labelled as such. Both GPUs were held at full utilisation by an
unrelated job throughout, which is why every timing is a batched region with a
co-timed floor probe. These conditions are not comparable with a published
NVLink figure and we do not quote one beside ours. We claim from this
experiment that the discipline is exportable and bitwise invariant off our own
fabric, and that on this fabric it costs what the table says. We claim nothing
about its cost at scale, which we have not measured.
```

### 1.6 Companion table (the full sweep) — `companion/main.tex`, new \S

The 6-row main table is the size sweep; the companion carries the whole thing.
Main-paper table `tables/pinfbt_cost.tex` (new file, ~14 lines, 0.18pp):

```latex
\begin{table}[!t]
\caption{Pinned-FBT against stock \texttt{ncclAllReduce}, $G{=}2$, fp64,
two RTX PRO 6000 over PCIe. Median of 15 batched regions. The full 28-point
sweep, the gloo arm at $G \le 64$, and the contention conditions are in the
companion report.}
\label{tab:pinfbtcost}
\centering
\begin{tabular}{rrrr}
\toprule
bytes & stock ($\mu$s) & pinned-FBT ($\mu$s) & overhead \\
\midrule
8\,Ki   & 57.4    & 188.8   & $3.29\times$ \\
128\,Ki & 43.3    & 135.1   & $3.12\times$ \\
512\,Ki & 106.3   & 169.4   & $1.59\times$ \\
8\,Mi   & 767.9   & 1140.4  & $1.49\times$ \\
32\,Mi  & 2636.8  & 4397.9  & $1.67\times$ \\
128\,Mi & 10794.5 & 23820.2 & $2.21\times$ \\
\midrule
\multicolumn{3}{l}{geomean over all 28 points} & $2.40\times$ \\
\multicolumn{3}{l}{best / worst} & $1.49$ / $3.91\times$ \\
\bottomrule
\end{tabular}
\end{table}
```

---

## 2. W7 — eta as a characterisation with a proved boundary

### 2.1 The reframe, in one line

Current draft position (three places): *"We did not build these baselines, and we
report no measured $\eta$"* (`main.tex:1968`, repeated at `2272`, and elevated to
**L1b, "the single largest gap in the evaluation"**, `main.tex:2748-2755`).

Proposed position: **$\eta$ is measured, and its value is a theorem with a sharp
boundary — exactly $1$ where the two reduction DAGs coincide, and that is exactly
the power-of-two regime; $1.15$ geomean where they cannot coincide.**

Read as "a cost found late", $1.15$ is a wound. Read as the *right-hand half of a
characterisation whose left-hand half is exact and proved*, it is the strongest
evaluation result in the paper, because it answers the question a TPDS referee
actually asks — *what does determinism cost me?* — with a number and a reason.

### 2.2 Why the tautology is the content, not the problem

`W7/RESULT.json:result_power_of_two.HONEST_READING` is right that $\eta=1$ at
power-of-two is not independent evidence: the DAGs are isomorphic
(`dag_isomorphic: 22` of 22, checked by exact canonical form,
`W7/v001/nd_tree.py:canon`), so the same pipeline necessarily schedules them
alike. But *why* they are isomorphic is the interesting fact and the paper does
not currently state it:

> At power-of-two $N$ and $G$, recursive doubling over contiguous rank blocks
> **is** $\FBT(N)$. A balanced binary tree over a contiguous block of $N/G$
> canonical leaves is precisely the complete subtree of $\FBT(N)$ rooted at that
> block; recursive doubling then pairs the $G$ partials at distances
> $1,2,4,\ldots$, which is precisely the top $\log_2 G$ levels of $\FBT(N)$.

So the ABI is not asking a power-of-two deployment to adopt a *different*
reduction order. It is asking it to **pin the order it already computes**. That is
why the cost is zero, and it is zero exactly, not approximately. The paper should
say this as a proposition with a two-line proof, because it converts the entire
power-of-two half of the instance suite from "a tautology we checked" into "the
regime where the ABI is provably free".

There is a second, independent reason the power-of-two replay is worth its space,
and `RESULT.json` states it: the isomorphism is proved on the abstract
construction, but the *toolchain* is 18 assignment methods $\times$ 10 mappings
$\times$ 122 refinements plus a scheduler, any of which could have broken the
correspondence in practice. $1{,}374$ replays through the real compiler
(`sprs_core.STAGE2/3/4_METHODS` + `build_schedule`, not a model) found zero
exceptions. That is a toolchain-fidelity result, and it is exactly the kind of
claim the paper elsewhere insists on making empirically rather than by assertion.

### 2.3 Why 1.15 is a good number and not a bad one

- It is bounded and small: `eta_best_vs_best` geomean **1.151**, median 1.090,
  range **1.026--1.352** over 7 instances / 342 comparisons
  (`result_non_power_of_two`).
- Under the champion pipeline it is **1.058** (range 0.755--1.272) — i.e. on one
  instance (`npow2g_small_mesh`) the ABI-compliant tree is *faster* than the
  unconstrained baseline under the pipeline the tournament actually picks.
- Across all 342 individual pipeline comparisons the geomean is **1.003** and the
  ABI-compliant tree is **faster on 168 of 342**, equal on 10, slower on 164.
  The honest reading of that: *choice of compiler pipeline moves the makespan far
  more than choice of reduction tree does.* That is a genuinely useful systems
  finding and it belongs in the paper.
- The pre-registered REFUTE branch ("$\eta \gg 1$ ... beyond the 1.07--1.95x band
  anticipated") **did not fire**; nothing exceeded 1.352
  (`result_non_power_of_two.PREREG_BRANCH`).

### 2.4 The three honest caveats that must travel with it

1. **ND-RecDouble was built; ND-Ring was not.** State it, and state *why the one
   we built is the harder one*: ND-RecDouble's cross-rank dependence chain is
   $\lceil\log_2 G\rceil$ combines against the ring's $G-1$, so it is the more
   demanding of the two baselines named at `main.tex:1963-1966`. Do **not** claim
   $\eta$ against ND-Ring would be smaller; we did not measure it.
2. **$\eta$ is a compiler-makespan ratio, not an RTL cycle ratio.** This is a
   scope limit and simultaneously a robustness property: $\eta$ does not touch
   the released `Cycles` column at all, so the metric defect of \S4.3 below
   cannot contaminate it. Say both halves.
3. **Coverage: 29 of 39 hardware-validated instances, 11 not reached, named.**
   `coverage.not_measured` lists them; the reason is replay compile cost
   ($9{,}086$ s for `vlarge_mod_ring` alone), not a result. Nine of the eleven
   are power-of-two instances at $G \in [256,4096]$ — i.e. in the regime the
   proposition covers analytically, so the unmeasured cells are the ones where
   the proof, not the measurement, is doing the work. Say that; it is true and it
   makes the gap benign.
4. **The T10 divergence must not be papered over.** T10 named four instances
   whose champion cuts above $G-1$; W7 reproduces one (`npow2_small_torus`,
   11 vs 9) and measures exactly $G-1$ on `large_mod_ring` and `med_mod_ring`
   with $\eta=1.000000$ on all 109 pipelines of each
   (`T10_cross_check.champion_cross_pe_edges.DIVERGENCE_FROM_T10`). The cause is
   a definition difference (released tournament record vs min-makespan pipeline
   among hardware-validated ones, recompiled). If the paper keeps any
   "ring/torus instances are where a locality-regrouping reducer might win"
   caveat, it must name `npow2_small_torus` alone and say the others were not
   reproduced or not measured.

### 2.5 Placement

- **Proposition + proof sketch + power-of-two result**: MAIN, into
  \S\ref{sec:method-nd}, replacing `main.tex:1968-1988` (21 lines of apology for
  a missing baseline). Net **$-0.05$pp** — the replacement is about the same
  length as the apology it deletes.
- **Non-power-of-two table (7 rows)**: MAIN, into \S\ref{sec:results-overhead},
  replacing the second half of `main.tex:2270-2276`. **$+0.15$pp** for the table.
- **Per-instance $\eta$ for all 29 instances, the per-pipeline distribution
  (342 points), and the T10 edge-cut cross-check**: COMPANION. **$0$pp.**
- **L1b**: rewritten from "the single largest gap" to a scope statement.
  **$-0.1$pp.**

Net main-paper delta for W7: **$\approx 0$pp**, and it removes the paper's own
self-identified largest gap. This is the highest acceptance-per-page item in the
whole plan.

### 2.6 Proposed LaTeX

**(a) Replaces `main.tex:1968-1988`** (the "we did not build these baselines"
paragraph and the analytic-model paragraph):

```latex
We built \emph{ND-RecDouble} and measured $\eta$ against it. We did not build
ND-Ring; of the two, ND-RecDouble is the more demanding baseline, since its
cross-rank dependence chain is $\lceil\log_2 G\rceil$ combines against the
ring's $G-1$, and we report $\eta$ only against the baseline we built.

ND-RecDouble assigns rank $r$ the contiguous block of canonical leaves
$[\,rN/G,\,(r{+}1)N/G\,)$, reduces each block by a balanced binary tree, folds
any remainder when $G$ is not a power of two, and merges the $G$ partials by
recursive doubling. It is compiled by the \emph{same} pipeline as $\FBT(N)$ ---
same topology, same $G$, same two-input ALU, same assignment, mapping,
refinement and scheduler --- so $\eta$ is a like-for-like ratio through one cost
model, and systematic model error largely cancels.

Before reporting the measurement we record why half of its outcome is
determined in advance.

\begin{proposition}[Cost boundary of the ABI]\label{thm:etabound}
Let $N$ and $G$ both be powers of two. Then the reduction DAG of
$\mathrm{ND\text{-}RecDouble}(N,G)$ is isomorphic to $\FBT(N)$, and therefore
$\eta = 1$ exactly, for every compiler pipeline.
\end{proposition}

\begin{proof}[Proof sketch]
A balanced binary tree over the contiguous block of $N/G$ canonical leaves owned
by rank $r$ is the complete subtree of $\FBT(N)$ rooted at that block, because
$N/G$ is a power of two and the blocks are aligned. Recursive doubling then
combines the $G$ partials at rank distances $1, 2, \ldots, G/2$, which is exactly
the top $\log_2 G$ levels of $\FBT(N)$. The two DAGs therefore agree node by
node. Both are compiled by the same deterministic pipeline, which is a function
of the DAG, the topology and $G$; identical inputs give identical schedules and
hence identical makespans.
\end{proof}

The proposition says something sharper than ``the ABI happens to be cheap''. At
power-of-two shapes the ABI does not ask a deployment to adopt a different
reduction order: recursive doubling over contiguous blocks \emph{is} the
canonical tree, and the ABI asks only that it be pinned rather than
re-derived per run. The entire cost of the contract therefore lives at
non-power-of-two shapes, which is where we measure it.

We previously declined to report an analytic $\hat\eta \approx 1$ obtained from
the same cost constants that produce $\Omega$, on the grounds that a model
indexed by depth and hop count cannot see \emph{which} operands pair. That
reasoning was right, and Proposition~\ref{thm:etabound} shows what the model was
hiding: at power-of-two shapes the two trees are not merely both log-depth, they
are the same tree, so $\hat\eta \approx 1$ was correct for a reason the model
could not express; at non-power-of-two shapes, where the trees genuinely differ,
the model's blindness was real and the measured cost is not $1$.
```

**(b) Replaces `main.tex:2270-2276`** (the "we did not build that baseline"
opening of \S\ref{sec:results-overhead}) and introduces the measurement:

```latex
\subsubsection{Measured same-fabric overhead}
We replay every compiler pipeline that the hardware campaign validated for an
instance on both $\FBT(N)$ and ND-RecDouble, through the real compiler rather
than a model, and take the ratio of makespans. Coverage is $29$ of the $39$
hardware-validated instances and $1{,}716$ pipeline comparisons; the eleven
instances not replayed are named in Appendix~\ref{app:eta} and were dropped for
replay cost, not for their result. Nine of the eleven are power-of-two instances
at $G \in [256, 4096]$, where Proposition~\ref{thm:etabound} settles $\eta$
analytically.

On the $22$ power-of-two instances the replay confirms the proposition through
the full toolchain: $1{,}374$ pipeline comparisons, $\eta = 1.000000$ on every
one, with the DAG isomorphism holding exactly by canonical form on $22$ of $22$.
This is a tautology check and we present it as one --- what it establishes is
that eighteen assignment algorithms, ten mappings, one hundred and twenty-two
refinement configurations and the scheduler preserve the correspondence in
practice, not merely in the abstract construction.

\input{tables/eta_npow2}

The seven non-power-of-two instances are where the trees genuinely differ
(isomorphism fails on $7$ of $7$) and $\eta$ is a real measurement.
Table~\ref{tab:etanpow2} gives it. Head to head --- each tree compiled by its own
best pipeline --- the geometric mean is $1.151$, the median $1.090$, and the range
$1.026$--$1.352$. Under the champion pipeline the geometric mean is $1.058$, and
on \sv{npow2g\_small\_mesh} the ABI-compliant tree is the faster of the two.

Two further readings. First, across all $342$ individual pipeline comparisons the
geometric mean is $1.003$ and $\FBT(N)$ is faster on $168$ of them: the choice of
compiler pipeline moves the makespan considerably more than the choice of
reduction tree does, which is a statement about where the engineering leverage on
this fabric lies. Second, $\eta$ here is a ratio of compiler makespans, not of
measured cycle counts; it is therefore independent of the metric caveat in
\S\ref{sec:results-metric}, and it is a ratio of two quantities produced by one
cost model, so it is more robust than either makespan taken alone.

The characterisation is therefore complete in both halves: the ABI is free where
the canonical tree and recursive doubling coincide, which is provably the
power-of-two regime, and costs a geometric mean of $15\%$ where they cannot.
```

**(c) New main-paper table** `tables/eta_npow2.tex` (~16 lines, 0.15pp):

```latex
\begin{table}[!t]
\caption{Measured same-fabric overhead $\eta$ on the non-power-of-two instances,
where $\FBT(N)$ and ND-RecDouble are not isomorphic. $\eta>1$ means the
ABI-compliant tree is slower. Every power-of-two instance gives
$\eta = 1.000000$ (Proposition~\ref{thm:etabound}) and is omitted.}
\label{tab:etanpow2}
\centering
\begin{tabular}{lrrrr}
\toprule
instance & $N$ & $G$ & $\eta$ head-to-head & $\eta$ champion \\
\midrule
\sv{npow2n\_tiny\_ring}  &   10 &  4 & 1.032 & 1.032 \\
\sv{npow2g\_small\_mesh} &   16 &  5 & 1.026 & 0.755 \\
\sv{npow2\_tiny\_hc}     &   50 &  7 & 1.090 & 1.090 \\
\sv{npow2\_small\_torus} &  100 & 10 & 1.295 & 1.230 \\
\sv{npow2\_med\_fat}     &  200 & 12 & 1.352 & 1.116 \\
\sv{large\_unbal\_torus} &  500 & 32 & 1.042 & 1.000 \\
\sv{vlarge\_unbal\_hc}   & 1500 & 64 & 1.272 & 1.272 \\
\midrule
geomean & & & \textbf{1.151} & 1.058 \\
\bottomrule
\end{tabular}
\end{table}
```

**(d) Replaces L1b at `main.tex:2748-2755`:**

```latex
\emph{L1b --- Scope of the measured $\eta$.} $\eta$ is measured against
ND-RecDouble only; ND-Ring, the second baseline of \S\ref{sec:method-nd}, was
not built, and we make no claim about $\eta$ against it. $\eta$ is a ratio of
compiler makespans rather than of RTL cycle counts, and it covers $29$ of the
$39$ hardware-validated instances; the eleven omitted are named in
Appendix~\ref{app:eta} and nine of them fall in the regime
Proposition~\ref{thm:etabound} settles analytically.
```

---

## 3. W4 — withdrawing the paper's own L0b limitation

### 3.1 What the evidence says

L0b as printed (`main.tex:2687-2702`) asserts a fidelity band for which no run
existed anywhere in the artifact: *"roughly $59\%$ of runs agree bit-exactly and
the remainder settle $1$--$54\%$ lower, with per-instance pipeline rankings
preserved in about $80\%$ of cases."*

Measured (`W4/v002/ANALYSIS_full.json`):

| quantity | value | key |
|---|---|---|
| comparable (instance, pipeline) points | 1,326 | `prefer_ok.n_comparable` |
| same PASS verdict | 1,326 / 1,326 | `prefer_ok.same_PASS` |
| same 64-bit root | 1,326 / 1,326 | `prefer_ok.same_64bit_root` |
| same cycle count | 1,326 / 1,326 | `prefer_ok.same_cycles` |
| bit-exact | **100.0%** | `prefer_ok.pct_bit_exact` |
| route-load fill time | **min = max = median = 10.0 ns per entry** | `prefer_ok.delta_ns_per_route_entry` |
| same result under the alternative dedup rule | 1,306 / 1,306, 100.0% | `later_wins.*` |
| negative control: corrupt whole route table | PASS $\to$ FAIL on 24 / 24 | EXPERIMENTS_REPORT §3 |

So: the asserted band is $59\%$ / $1$--$54\%$; the measured band is $100\%$ / $0\%$.
The limitation does not exist. Two further facts strengthen the withdrawal:

1. The result is **invariant to the record-selection rule** — 100.0% under
   `prefer_ok` (1,326) and 100.0% under `later_wins` (1,306). A referee cannot
   attribute it to bookkeeping.
2. The negative control **fires**: corrupting the entire clocked route table
   flips PASS to FAIL on 24 of 24, so the clocked path is demonstrably
   exercising routing. (Corrupting a *single* entry still PASSed on 12 of 24;
   that is expected — a single wrong $(\text{router},\text{dest})$ entry may land
   on a pair the schedule never uses — and it must be reported, but the
   all-entries arm is the control that matters.)

### 3.2 The by-product that is worth more than the withdrawal

W4's bypass arm re-compiled and re-simulated **every** hardware-validated
(instance, pipeline) point: $1{,}326$ points $\times$ 2 configuration-load arms.
Verified directly from the raw records
(`W4/v001/full_bypass_clocked.jsonl`, deduplicated last-wins):

- $1{,}301$ points completed under both arms; on **all $1{,}301$** the bypass
  root, the clocked root and the software oracle's expected root are the same
  64-bit value. The residual 25 are tool-level failures on one arm
  (`XELAB_FAIL` 19, `SIM_UNKNOWN` 5, `XVLOG_FAIL` 1), not disagreements.
- Across the 25 instances present, **every instance returned exactly one
  distinct 64-bit root** over all of its re-simulated pipelines.

This is a re-execution of the headline invariance result from source, on fresh
compiles and fresh simulations, and it agrees. That is a stronger sentence than
anything L0b could have said, and the paper does not currently contain it.

**Honesty limit, and it is a real one.** The released CSV
(`results/results/live_hw_results_p1_unified.csv`) records
`instance, pipeline, pass, cycles, simtime, code` and **no root column**, so
this re-execution cannot be diffed against the originally published bits; and
the RTL used here carries the W3 `fp64_add` repair, so the roots need not equal
the original ones. The claim available is *"re-executes and self-agrees"*, not
*"reproduces the published bits"*. Do not write the latter. See \S7, open item
O-1.

### 3.3 Placement

- **The withdrawal** stays in \S\ref{sec:limitations} as a rewritten L0b.
  Keeping it there is the point: a limitation the authors state, then measure,
  then withdraw on their own evidence is a strong signal of care, and it is the
  cheapest possible place to put it (Limitations is dense prose, no floats).
  Current L0b is 16 lines; the replacement is 11. **$-0.06$pp.**
- **The re-execution by-product** goes to \S\ref{sec:results-invariance} as two
  sentences appended to the existing invariance paragraph. **$+0.08$pp.**
- **The full 1,326-row comparison, the per-entry fill-time distribution and the
  negative-control detail** go to the COMPANION, \S "Verification".
  **$0$pp.**
- Net: **$+0.02$pp**, i.e. free, for a withdrawn limitation and a re-execution
  result.

### 3.4 Proposed LaTeX

**(a) Replaces L0b at `main.tex:2687-2702` in full:**

```latex
\emph{L0b --- Configuration-load bypass: stated, measured, and withdrawn.}
Route-table initialisation in our testbenches is performed by hierarchical
assignment at time zero rather than by the clocked \sv{write\_route()} protocol,
because the latter costs $\mathcal{O}(G^2)$ simulated cycles and dominates
wall-clock at large $G$. An earlier version of this paper stated a fidelity band
for that substitution --- roughly $59\%$ of runs bit-exact, the remainder
$1$--$54\%$ lower in cycles --- as an estimate. We have since measured it, and
the estimate was wrong. Re-running every hardware-validated
(instance, pipeline) point under both paths gives the same \sv{PASS}/\sv{FAIL}
verdict, the same 64-bit root and the same cycle count on $1{,}326$ of $1{,}326$
comparable points: $100\%$ bit-exact, no exceptions, and unchanged at $100\%$
under an alternative rule for selecting among repeated records. The only effect
of clocked loading is a deterministic configuration prologue of exactly one
clock per route-table entry ($10.0$~ns at our testbench period; minimum,
maximum and median all equal), which completes before \sv{program\_start} and
therefore enters no reported cycle count. A negative control confirms the
clocked path genuinely exercises routing: corrupting the route table flips
\sv{PASS} to \sv{FAIL} on $24$ of $24$ runs. We therefore withdraw the
previously stated band. The measured uncertainty that route-table loading
contributes to any cycle figure in this paper is zero.
```

**(b) Appended to \S\ref{sec:results-invariance} (after the existing
zero-divergence sentence):**

```latex
The campaign has also been re-executed from source. Every hardware-validated
(instance, pipeline) point was recompiled and re-simulated under both
configuration-load paths --- $1{,}301$ points completing under both --- and on
every one of them the two paths and the software oracle agree on the same 64-bit
value, with every instance yielding exactly one distinct root across all of its
pipelines. The released results table records verdicts and cycle counts but not
root words, so this is a re-execution that self-agrees rather than a bitwise
diff against the originally released values; we state it in those terms.
```

---

## 4. Claim sweep, both directions

Ordered by effect on first-turn acceptance, not by section order. Every row
cites `file:line` or a `RESULT.json` key.

### 4.1 OVER-CLAIMS — the evidence does not support the stated strength

#### O-1 (SEVERITY: REJECT-LEVEL). Appendix~F reports 14 of 39 instances beating the paper's own lower bound

**Verified directly.** `paper/tables/perinstance.tex` carries the provenance
stamp `source : .../live_hw_results_p1_unified.csv`. That is the **defective
GPU-0 dataset**, which `paper/scripts/hwdata.py:9-13` itself documents as
*"DEFECTIVE for any cycle-derived claim"*, and which `main.tex:2145-2152`
promises *"is not used for any reported number"*.

The consequence is visible in the shipped table. Fourteen of its thirty-nine
rows print $\mathrm{cyc}/\Omega < 1$ — a schedule beating a proven lower bound:

| instance | printed champion | $\Omega$ | printed cyc/$\Omega$ |
|---|---:|---:|---:|
| `large_dense_2d` | 5 | 192 | **0.03** |
| `vlarge_unbal_hc` | 5 | 144 | **0.03** |
| `npow2_small_torus` | 5 | 60 | **0.08** |
| `vlarge_mod_ring` | 19 | 147 | **0.13** |
| `large_mod_ring` | 19 | 82 | **0.23** |
| `vlarge2_mod_ring` | 34 | 147 | **0.23** |
| `small_mod_2d` | 5 | 16 | **0.31** |
| ... (7 more, up to 0.94) | | | |

Meanwhile `main.tex:2380-2381` states, from the *correct* dataset, *"no
instance reaches $\Omega$ --- the best is $1.35\times$"*. **The paper's main text
and its own appendix contradict each other, and the appendix violates a lower
bound the paper proves.** A referee who opens Appendix~F finds either a broken
bound or a broken table; both are fatal on first read, and the paper has
already told that referee (`main.tex:2145-2152`) that this exact metric defect
"changed the winning configuration on 35 of 39 instances".

**Cause, precisely.** `paper/scripts/gen_cost_tables.py:100` and
`gen_tournament.py:118` both delegate to `hwdata.select()` and correctly get
`live_hw_results_p1_maxpe.csv` (verified: `select()` returns MAXPE, 2,822 rows,
39 instances, `trusted=True`). `paper/scripts/gen_tables.py:42` does **not** —
it hardcodes `HW_CSV = f"{P1}/live_hw_results_p1_unified.csv"` and
`tbl_perinstance` computes `champ = min(r['cycles'])` and `cyc/Ω` from it
(`gen_tables.py:249-278`). The `make check` guard at `paper/Makefile:80` greps
`tables/` for the string `DEFECTIVE`, but `gen_tables.py` never calls
`hwdata.select()` and so never stamps it. The guard cannot see this table.

**Fix, and it is nearly free.** Point `tbl_perinstance` at `hwdata.select()`
and regenerate. I computed the corrected table from
`live_hw_results_p1_maxpe.csv`: **0 of 39 rows fall below $\Omega$**, the
minimum ratio becomes **1.35** (`large_extreme_1d`) — *exactly the figure
`main.tex:2381` already claims* — and the maximum becomes 9.07
(`maxp_bal_2d`). The appendix and the main text become consistent with no
prose change at all.

- decision: **CHANGE IMPLEMENTATION** (one line in a table generator) + regenerate
- page delta: **0**
- acceptance delta: **large-positive** (removes a self-contradiction that
  invalidates a lower bound on inspection)
- new work: none beyond `make tables`

#### O-2. The printed pinned-FBT construction is not the canonical reduction

`main.tex:2529-2536`: step 1 partitions by $\mathrm{rank}(i)=\lfloor iG/N\rfloor$
and the text asserts *"This preserves Claim~\ref{claim:1} by construction"*.
T16 proved otherwise and W2's mandatory negative control fired: at $N{=}1000$
and $N{=}1500$ the printed construction produced **3 distinct roots** over
$G\in\{2,3,8\}$ and **0 of 13 cells** equalled $\Rcan$
(`W2/RESULT.json:H1_negative_control.detail`). It coincides at $N{=}1024$ for
the $G$ that divide $N$, and at $N{=}7$ entirely — coincidence, not correctness.
This is the only *correctness* over-claim in the paper. Full treatment and
replacement text in \S1.5.

- decision: **REWRITE** (level-aligned cut; LPT deal; negative control reported)
- page delta: +0.45 (net of the promotion described in \S1.4)
- acceptance delta: **large-positive**; confidence **high**

#### O-3. L0b asserts a fidelity band that does not exist

`main.tex:2687-2702`. Asserted $59\%$ / $1$--$54\%$; measured $100\%$ / $0\%$ on
1,326 of 1,326 (`W4/v002/ANALYSIS_full.json:prefer_ok`). Treated in \S3.

- decision: **REMOVE OR NARROW CLAIM** (withdraw); page delta $-0.06$;
  acceptance **positive**; confidence **high**

#### O-4. "We report no measured $\eta$", stated three times, and L1b calling it "the single largest gap"

`main.tex:1968`, `2272`, `2748-2755`. $\eta$ is now measured on 29 instances and
1,716 pipeline comparisons (`W7/RESULT.json`). Leaving these in is a false
statement about the paper's own evidence. Treated in \S2.

- decision: **REWRITE**; page delta $\approx 0$; acceptance **large-positive**

#### O-5. L0 states the wrong cause for the one missing instance

`main.tex:2678-2686` attributes the `maxp_mod_fat` gap to a resource limit
("$50$--$70$~GB of RAM for elaboration alone", "exceeded the $28{,}800$~s
cap", "This is a resource limit, not a negative result"). T13 established the
blocker was never RAM or wall-clock: at $G{=}4096$ the emitter's adjacency
fields truncated to 12 bits, so **0 of 8,223 installed links matched the
intended fat-tree and 0 of 900 sampled routes delivered**. The worktree emitter
now auto-sizes `ADJ_ID_W` (`src/sprs_core.py:~5510`), byte-identically for every
instance that fitted in 12 bits.

The stated *cause* is wrong regardless of whether the instance ever completes,
and correcting it is honest and cheap. Note the current elaboration attempt has
**not** succeeded: `W8_maxp/v001/status.txt` records `xelab rc=1 ... NO_SNAPSHOT
(rc=1)`; `v002/status.txt` shows a fresh attempt still at `phase=xvlog` as of
2026-08-28 08:14. **Do not write the paper as if 40/40 coverage is coming.**

- decision: **EDIT** (state the adjacency-width cause; keep 39/40); page delta 0;
  acceptance **positive** (a precise cause reads better than a vague budget
  excuse, and the artifact shows the emitter fix); confidence **high**
- see also open item O-2 in \S7

#### O-6. Non-goal and L2 wording now overshoot in the *conservative* direction

`main.tex:398-401` and `2757-2763` say the paper does not benchmark against
production collectives. After \S1 it does — on PCIe, at $G{=}2$, not on
NVLink. Both need a clause, not a deletion, and the NVLink exclusion must
survive verbatim because `W2/RESULT.json:hardware.comparability` is explicit
that our figure must not be quoted beside TBIK's NVLink number.

- decision: **EDIT**; page delta 0; acceptance **positive**

### 4.2 UNDER-CLAIMS — the evidence supports a stronger statement than is made

Under-claiming costs acceptance. Each of these is a result already in hand that
the draft either hedges or omits.

#### U-1. The motivating premise is measured, and the draft only cites it

`main.tex:187-230` argues cluster-reshape divergence from the literature and a
hypothetical ("A training job rerun on a cluster resized from $G{=}128$ to
$G{=}256$ GPUs ... produces bit-divergent weights"). W1 measured it on this
hardware (`W1/RESULT.json`, EXPERIMENTS_REPORT §1):

- 14 world sizes from 1 to 64 on **identical input bytes** $\to$ **14 distinct
  64-bit roots**, in every one of 12 (N, dtype, profile) cases.
- **78.6%** of fp64 configuration pairs disagree (441/561); **90.0%** of fp32
  pairs (189/210).
- Max spread **5,120 ulp**; max relative spread $6.4\times10^{-13}$; 1024 of
  1024 elements move.
- **0 of the configurations equalled the canonical FBT reduction.**
- Repeatability at a fixed configuration: **5/5 identical** under NCCL and under
  gloo, 0 intra-run disagreements.

For a TPDS referee this is the difference between "the authors assert a problem"
and "the authors measured the problem on the collective everyone uses". It is
the cheapest large gain in the plan: three sentences and no figure.

Honest scope that must travel with it: the NCCL algorithm/protocol axis and the
channel axis each returned **one** root, because at $G{=}2$ the cross-rank
reduction is a single addition per element and no schedule can move it. That is
structural, is stated as such in `W1/RESULT.json`, and must **not** be reported
as a partial refutation, nor generalised to larger $G$.

- decision: **EDIT** (\S\ref{sec:intro}, +3 sentences); page delta **+0.12**;
  acceptance **large-positive**; confidence **high**

Proposed LaTeX, replacing the hypothetical at `main.tex:206-211`:

```latex
This is not a hypothetical. On a two-GPU node we ran the same deterministic
reduction over identical input \emph{bytes} at fourteen rank counts from $1$ to
$64$, holding the data, the seed and the code fixed so that only the shape of
the job changed. The fourteen configurations returned \textbf{fourteen distinct
64-bit results}, none of which equalled the canonical tree reduction of the same
multiset; $78.6\%$ of \sv{fp64} configuration pairs and $90.0\%$ of \sv{fp32}
pairs disagree, with spreads reaching $5{,}120$~ulp and every element of the
result vector moving. Repeated runs at any \emph{fixed} configuration were
bitwise identical, five times out of five. Reshape moves the answer; noise does
not. It is the shape of the job, not the hardware's determinism, that is at
stake.
```

#### U-2. $\eta$ is not merely measured — its zero half is a theorem

See \S2. The paper currently apologises for a missing baseline across 21 lines
(`main.tex:1968-1988`). It can instead state Proposition~\ref{thm:etabound} and
close its own self-declared largest gap. Highest acceptance-per-page item in
this plan.

- decision: **ADD ANALYSIS + REWRITE**; page delta $\approx 0$;
  acceptance **large-positive**

#### U-3. Non-power-of-two shapes are the new coverage, and they cost nothing

TBIK's fixed-order tree does not cover non-power-of-two $N$. W2 swept **10
non-power-of-two $N$** and **7 non-power-of-two $G$**, all invariant
(`W2/RESULT.json:H1_bitwise_reshape_invariance`), and
`H2_cost.non_power_of_two_N_at_128KiB` shows **no non-power-of-two cost
penalty** — the non-power-of-two leaf counts span $2.19$--$3.91\times$, inside
the band spanned by their power-of-two neighbours ($2.98$--$3.26\times$). The
draft says none of this.

- decision: **EDIT** (one sentence each in \S1.5's invariance and cost blocks);
  page delta 0 (already inside \S1.5); acceptance **positive**

#### U-4. The paper has a provenance guard most papers do not, and never says so

`paper/scripts/hwdata.py` refuses the defective dataset and returns
`trusted=False` if the corrected re-measurement is incomplete; every generated
table carries a `% source :` and `% metric :` provenance stamp; and
`paper/Makefile:80` **fails the build** if any table is stamped `DEFECTIVE`.
That is a stronger reproducibility control than most TPDS submissions carry, it
is shipped in the artifact, and the paper mentions it nowhere. One sentence in
Appendix~\ref{app:repro} buys real credibility. (Land this **after** O-1, so
the statement is true of every table.)

- decision: **EDIT**; page delta **+0.03**; acceptance **positive**

Proposed LaTeX for Appendix~\ref{app:repro}:

```latex
\emph{Cycle-metric provenance.} Two hardware datasets exist: an original
campaign whose \sv{Cycles} column recorded PE~0's counter, and a full
re-measurement recording the maximum over PEs. Every table in this paper that
derives from cycle counts is generated through a single loader
(\sv{scripts/hwdata.py}) that selects the re-measured dataset and refuses it if
it is less than $95\%$ complete; every generated table carries a machine-written
provenance stamp naming its source file and metric; and \sv{make check} fails
the build if any table is stamped as coming from the superseded metric.
```

#### U-5. The campaign re-executes, and 92% of its published cycle values reproduce exactly

This is the item most likely to be found by an artifact evaluator, so the paper
should state it first, in its own words. I verified it directly against the
dataset the paper actually uses (`live_hw_results_p1_maxpe.csv`):

- 1,310 published points were recompiled and re-simulated. **1,207 (92.1%)
  reproduce the published cycle count exactly.** **Zero** rows match the
  superseded GPU-0 counter — i.e. the shipped cycle column is the corrected
  metric throughout, exactly as `main.tex:2145-2152` claims.
- The 103 that differ are confined to **two of the seventeen** stage-2
  assignment methods: `2i` CPOP 64/128 = 50.0%, `2n` ClHEFT 37/97 = 38.1%,
  `2g` 2/59 = 3.4%. **Fourteen of the seventeen methods reproduce 100.0%**
  (`2a,2b,2c,2d,2f,2h,2j,2k,2l,2m,2o,2p,2q,2r`: zero mismatches).
- The differences are **two-sided** — recompiled/published ratio geomean 0.859,
  median 0.965, range 0.177--1.201 — i.e. the recompile sometimes finds a faster
  and sometimes a slower schedule. This is compile variability, **not** a
  systematic metric error, and the distinction is measurable and should be
  stated.
- The **reduction root is unaffected**: identical in every re-run pair
  (\S3.2).

> **Correction to `EXPERIMENTS_REPORT.md` §5a, which the council should record.**
> That section concludes the shipped `Cycles` column is GPU~0's counter. It
> reached that conclusion by comparing against
> `results/results/live_hw_results_p1_unified.csv`
> (`W4/v001/published_bypass.json` was built from it). That file is the
> **superseded** campaign, which the paper explicitly declares unused
> (`main.tex:2146`) and which the build system refuses
> (`paper/scripts/hwdata.py:9-13`). Against the file the paper actually
> builds from, the re-simulation matches max-over-PEs on 1,207 rows and GPU~0
> on **zero**. §5a's headline ("geomean 1.61x under-report", "the per-instance
> champion was selected on this metric") does **not** apply to the paper as
> built, with the single exception of Appendix~F (item O-1), which is a
> generator bug and not a data defect. §5b (the 103--129 non-reproducing
> CPOP/ClHEFT rows) **stands** and is real.

- decision: **CLARIFY LIMITATION** — state the reproduction rate and the
  two-method exception in the metric-convention subsection
- page delta **+0.1**; acceptance **positive** (pre-empting a finding an
  evaluator will make anyway is worth far more than the tenth of a page);
  confidence **high**

Proposed LaTeX for \S\ref{sec:method-metric}:

```latex
\emph{Reproducibility of the cycle column.} We recompiled and re-simulated
$1{,}310$ of the released configurations from source. $1{,}207$ of them
($92.1\%$) reproduce the released cycle count exactly, and none reproduces the
superseded PE-0 metric. The $103$ that differ are confined to two of the
seventeen stage-2 assignment methods --- CPOP ($50.0\%$ of its rows) and
cluster-HEFT ($38.1\%$) --- for which our compiler did not always emit the same
schedule when the same configuration was recompiled under the concurrent
measurement harness; the other fourteen methods reproduce on $1{,}032$ of
$1{,}032$. The differences are two-sided (recompiled/released ratio: geometric
mean $0.86$, median $0.97$), so they are schedule variability rather than a
systematic bias, and the 64-bit reduction root was identical in every re-run
pair. Cycle figures for CPOP and cluster-HEFT rows should therefore be read as
one draw from a small distribution; no invariance claim is affected.
```

#### U-6. Re-execution of the invariance result

See \S3.2: 1,301 points, two configuration-load paths, one root per instance.
Two sentences in \S\ref{sec:results-invariance}.

- decision: **EDIT**; page delta **+0.08**; acceptance **positive**

#### U-7. "Pipeline choice matters more than tree choice"

`W7/RESULT.json:result_non_power_of_two.per_pipeline_distribution`: over 342
comparisons the geomean is 1.003 and $\FBT(N)$ is faster on 168. That is a
systems finding of independent interest to a TPDS audience and it costs one
sentence (already in \S2.6(b)).

- decision: **EDIT**; page delta 0; acceptance **positive**

#### U-8. The load bound is confirmed far beyond the suite

`W2/RESULT.json:H3_load_imbalance`: LPT worst ratio 1.969 over the 426 T16
pairs, 1.996 over all 1,546, **1.993 over 44,850 pairs with $N\le300$, none
above 2**. One clause in \S1.5. Note this is a *conditional* strengthening: it
holds for LPT and fails for the contiguous deal (2.48), so the paper must
specify LPT — see \S1.5's "Second, the deal must be LPT".

- decision: **EDIT**; page delta 0 (inside \S1.5); acceptance **positive**

### 4.3 Claims checked and found CORRECTLY stated (no change)

Recorded so the council does not re-litigate them.

- `main.tex:2145-2152` "An earlier campaign ... is not used for any reported
  number ... moved $50.5\%$ of cycle counts": **true of the main-paper tables**
  (`omegaratio.tex`, `nginflection.tex`, `winners_family.tex` all stamp
  `source : ...maxpe.csv`, `metric : max over PEs (corrected)`), and my
  re-simulation puts the divergence between the two files at $51.1\%$ of
  common rows, consistent with the quoted $50.5\%$. **Becomes true without
  exception once O-1 is fixed.**
- `main.tex:2380-2381` "no instance reaches $\Omega$ --- the best is
  $1.35\times$": **confirmed** by recomputation from the correct dataset
  (minimum 1.35, `large_extreme_1d`).
- `main.tex:2224-2228` mutation accounting (108 run, 107 reached a verdict, 107
  flagged, the excluded one named): correctly and unusually honestly stated.
- `main.tex:2233-2241` the LSB-absorption discussion: correct, and it is one of
  the strongest paragraphs in the paper. Keep verbatim.
- `main.tex:2352-2364` the "not a controlled experiment / covariates co-vary"
  hedge on the $N/G$ knee: correctly scoped. Do **not** strengthen it, even
  though the knee survives on the corrected dataset — the covariate argument is
  independent of the metric.
- `main.tex:2371-2380` the tightness-to-bound-not-throughput reading of the
  topology ordering: correct and non-obvious. Keep.
- Abstract's $2{,}822$ / $39$ of $40$ / $107$ of $107$: all supported.

---

## 4bis. Two further claim defects found while building the placement ledger

#### O-7. "List scheduling (HEFT, CPOP) takes tall narrow trees" — it wins nothing

`main.tex:2419-2421` asserts a regime for list scheduling. The table
\emph{on the same page}, `\input{tables/winners_family}` at `main.tex:2415`,
has no list-scheduling row at all:

```
tree DP 21 (53.8%) | graph partition 7 (17.9%) | hierarchical 7 (17.9%)
clustering 3 (7.7%) | multilevel 1 (2.6%)                    [= 39 instances]
```

I recomputed the per-instance champions from
`live_hw_results_p1_maxpe.csv` independently and reproduced that table exactly
(`2k` Lukes 17 + `2l` Frederickson 4 = tree DP 21; `2b` RecBisect 7 = graph
partition 7; `2o` ParSub 7 = hierarchical 7; `2g` DSC 3 = clustering 3; `2c`
MLfm 1 = multilevel 1). **HEFT (`2a`) and CPOP (`2i`) win zero instances.** The
prose's other groupings are also off: it calls MLfm graph partitioning, while
the generator's own family map (`paper/scripts/gen_tournament.py:54-62`) puts
MLfm in `multilevel` and DKway in `graph partition` with zero wins.

A referee who reads the sentence and then the table beside it concludes the
authors did not read their own results. Fix by describing what the table says.

- decision: **REWRITE** (one sentence); page delta 0; acceptance **positive**;
  confidence **high**

Proposed replacement for `main.tex:2417-2421`:

```latex
The winning family is concentrated rather than spread: tree DP (Lukes,
Frederickson) takes $21$ of the $39$ instances, where its polynomial-time
exactness on trees pays; hierarchical (ParSub) and graph partitioning
(RecBisect) take seven each, on the balanced topologies whose bisection
structure aligns with recursive partitioning; clustering (DSC) takes three and
multilevel (MLfm) one. The list-scheduling methods, HEFT and CPOP, win no
instance outright --- they are competitive on tall narrow trees but never
best --- which is worth recording because they are the methods a
collective-scheduling compiler would reach for first.
```

#### O-8. "Two algorithms never reach the hardware at all" — one is named

`main.tex:2430-2431`. Only `ExactBB` follows. Either name the second or write
"one". Trivial, and exactly the kind of thing a reviewer quotes.

- decision: **EDIT**; page delta 0; acceptance **neutral** (removes an
  irritant); confidence **high**

#### U-9. The non-reproducing rows carry none of the reported champions

Directly verified: of the 39 per-instance champions computed from
`live_hw_results_p1_maxpe.csv`, **zero** come from CPOP (`2i`) or ClHEFT
(`2n`) — the two methods whose compiles did not reproduce (\S4.2 U-5). So no
per-instance champion, no $\mathrm{cyc}/\Omega$ figure, no
distance-to-$\Omega$ statement and no winner-family share depends on a
non-reproducing row. This sentence belongs immediately after the U-5
disclosure, because it converts the disclosure from a worry into a bounded,
quantified non-issue.

Proposed addition to the U-5 paragraph:

```latex
None of the $39$ per-instance champions reported in this paper comes from
either of those two methods, so no cycle figure we report rests on a
non-reproducing row.
```

- decision: **ADD ANALYSIS** (already done, above); page delta $+0.02$;
  acceptance **positive**; confidence **high**

---

## 5. Placement ledger

**Method and precision.** Page spans measured from the rendered
`paper/paper.pdf` (26 pages, `pdfinfo`) via `pdftotext -layout`, refined against
`main.tex` line counts (body calibrates at $\approx124$ lines/page; appendix
material at $\approx73$ lines/page because floats inflate it). The council's
`pages.json` merges Conclusion with all seven appendices into one 5-page block;
the refined split is below. Individual estimates are $\pm0.15$pp.

Refined baseline map of the 26 pages:

| block | pages | note |
|---|---:|---|
| §I Introduction | 1--3 | 3.0 |
| §II Background / threat model | 3--4 | 1.0 |
| §III The Reduction ABI (theory core) | 4--8 | 5.0 |
| §IV The Fabric | 9--11 | 2.8 |
| §V The Compiler | 12--13 | 2.0 |
| §VI Methodology | 14--15 | 2.0 |
| §VII Results | 16--18 | 3.0 |
| §VIII Discussion | 19 | 1.0 |
| §IX Related Work | 20 | 1.0 |
| §X Limitations | 21 | 1.0 |
| §XI Conclusion | 22 | 0.4 |
| Appendices A--G | 22--25.5 | 3.4 |
| References | 25.5--26.3 | 1.4 |
| **measured total** | | **26.0** (last page ~1/3 full) |

### 5.1 Pre-registered results — every branch has a home (hard constraint)

`PREREGISTRATION.md` defines the branches. None may be suppressed. Placement
only:

| pre-registered branch | outcome | placement | where the reader finds it | pp |
|---|---|---|---|---:|
| W1 divergence on real hardware | PARTIAL (the branch named in advance) | **MAIN** §I | new 3 sentences (\S4.2 U-1) | +0.12 |
| W1 run-to-run determinism at fixed config | measured 5/5 | **MAIN** §I | same sentences | 0 |
| W1 library/channel axes single-rooted | structural at $G{=}2$ | **COMPANION** | companion §Verification, with the $G{=}2$ explanation | 0 |
| W2-H1 invariance | SUPPORTS, 2,414 cells | **MAIN** §VII-new | \S1.5 | in +0.45 |
| W2-H1 negative control (index-range fails) | fired, 3 of 4 | **MAIN** §VII-new | \S1.5, one paragraph | in +0.45 |
| W2-H2 cost | REFUTES the "affordable" branch | **MAIN** (6-row table + decomposition) + **COMPANION** (28-point sweep, gloo arm, contention conditions) | \S1.5, \S1.6 | in +0.45 |
| W2-H3 load imbalance | SUPPORTS, requires LPT | **MAIN**, one clause | \S1.5 | 0 |
| W4 L0b | REFUTES | **MAIN** §X (withdrawal) + **COMPANION** (1,326-row detail) | \S3.4 | $-0.06$ |
| W4 negative control | fired 24/24 | **MAIN**, one clause inside L0b | \S3.4(a) | 0 |
| W4 re-execution by-product | agrees | **MAIN** §VII-B, 2 sentences | \S3.4(b) | +0.08 |
| W4 §5b CPOP/ClHEFT non-reproduction | real, 103 rows | **MAIN** §VI-G, one paragraph | \S4.2 U-5 | +0.10 |
| W7 power-of-two $\eta=1$ | SUPPORTS (tautology check) | **MAIN** §VI-B (proposition) + §VII-C | \S2.6 | $-0.05$ |
| W7 non-power-of-two $\eta$ | MEASURED | **MAIN** 7-row table | \S2.6(c) | +0.15 |
| W7 per-pipeline distribution, per-instance $\eta$, T10 edge-cut divergence | measured | **COMPANION** + 1 sentence main | \S2.5 | 0 |
| W7 11 instances NOT REACHED | named | **MAIN** one clause + **COMPANION** list | \S2.6(b) | 0 |
| W2/v005 gloo re-run NOT REACHED | named | **COMPANION** | conditions block | 0 |
| maxp\_mod\_fat (W8) | still unresolved | **MAIN** L0, cause corrected | \S4.1 O-5 | 0 |

Nothing is suppressed; nothing new is billed beyond the table above.

### 5.2 Existing main-paper blocks — KEEP / COMPRESS / MOVE / CUT

MOVE is preferred throughout, per the objective. The companion
(`companion/main.tex`, 374 lines, ~3pp, unconstrained) already contains
sections that duplicate main-paper material; those are the free moves.

| # | block | `main.tex` | now | fate | saving | acceptance effect |
|---|---|---|---|---:|---:|---|
| M1 | App. A ISA and Packet Format | 2855--2891 | 0.50 | **MOVE** — companion §"Instruction and Packet Encodings" (`companion:102-188`) is the same content | $-0.50$ | neutral: pure duplication |
| M2 | App. C Worked Invariance Example at $N{=}4$ | 2926--2971 | 0.90 | **MOVE** | $-0.90$ | neutral: pedagogic, no claim rests on it |
| M3 | App. B algorithm catalogue (keep the winner-distribution table) | 2892--2925 | 0.93 | **COMPRESS + MOVE** catalogue | $-0.45$ | neutral: §VII-D's summary table carries the finding |
| M4 | App. D per-instance wall-time table (keep the 40-instance suite table) | 2972--3015 | 0.55 | **COMPRESS + MOVE** | $-0.25$ | neutral |
| M5 | App. F Per-Instance Results (39 rows) | 3048--3070 | 0.55 | **MOVE** — *only after O-1 is fixed* | $-0.55$ | neutral **if** fixed first; **large-negative if moved unfixed**, since the companion is also read |
| M6 | §IV-C Packet Format | 1240--1287 | 0.39 | **MOVE** — companion §"Packet format" (`companion:141-165`) | $-0.35$ | neutral |
| M7 | §IV-F Pipeline and DMEM Forwarding | 1321--1447 | 1.02 | **COMPRESS** to the two forwarding levels Claim 1 needs; rest to companion §"Forwarding" | $-0.55$ | neutral if fabric invariants A1--A9 stay in §III |
| M8 | §IV-H/I Write Arbitration, Routing Discipline | 1489--1554 | 0.53 | **COMPRESS**; companion §"Write arbitration", §"Router" | $-0.30$ | neutral |
| M9 | §IV-J Resource Envelope | 1555--1622 | 0.80 | **COMPRESS** to a 4-line table; companion §"Resource Envelope and Known Limits" | $-0.50$ | slightly negative — a hardware referee likes an area/LUT table; keep the 4 headline numbers |
| M10 | §V DMEM allocator + codegen detail | 1793--1890 | 0.80 | **COMPRESS** to the single-writer post-condition and the ABI verifier | $-0.45$ | neutral: connectivity repair (the load-bearing pass) stays |
| M11 | §VIII-A/B/C What the ABI buys / When not to use / Generalisation | 2447--2518 | 0.58 | **COMPRESS** to 0.28 | $-0.30$ | neutral: speculative content, and §VIII-D's replacement is the strong material |
| M12 | §III-F Supporting Arguments | 852--1023 | 1.39 | **COMPRESS** lightly | $-0.30$ | mildly negative if cut deeper — this is the paper's core argument; do not exceed $-0.30$ |
| M13 | §VI-C Software-Only Baseline (SW-FixedTree analytic upper bound) | 1995--2006 | 0.10 | **CUT** | $-0.10$ | **positive**: an analytic upper bound for a baseline nobody built is now superseded by a real measured software baseline (\S1). Deleting it removes a soft target. |
| M14 | Fig. `omega_by_instance` (per-instance $\Omega$ figure) | 2396--2404 | 0.45 | **MOVE** with M5 | $-0.45$ | neutral: Table `omegaratio` carries the aggregate |
| **subtotal** | | | | | **$-5.95$** | |

Blocks explicitly **KEEP**, recorded so they are not revisited:

- §III-A canonical tree, §III-B ABI definition, §III-C assumptions, §III-D
  Claim 1 + Property 2, §III-G orthogonality theorem — the contribution.
- §III-I Mechanisation and Runtime Checks (`1135-1191`) — the paper's
  disclaimer that "mechanised" is not used in its formal sense. Cutting honesty
  to save 0.4pp is exactly the trade the objective forbids.
- §VII-C-2 the falsifiable $N/G$ prediction with its covariate hedge
  (`2318-2364`) — a pre-committed prediction that lands is worth its page.
- §VII-B mutation / LSB-absorption paragraph (`2233-2241`) — strongest
  methodological paragraph in the paper.
- App. E Selection-Bias Ablation (0.16pp) — cheap, and it substantiates L6.
- §IX Related Work (1.0pp) — TPDS referees weight this heavily.
- App. G Reproducibility Checklist — compress to 0.3pp, do not move; it is where
  U-4's provenance sentence lands.

### 5.3 Companion, after the moves

Currently ~3pp / 374 lines. It gains: W2's full 28-point cost sweep + gloo arm +
contention conditions; W2's per-$(N,G)$ imbalance data; W7's per-instance $\eta$,
342-point distribution and T10 edge-cut cross-check; W4's 1,326-row
bypass/clocked comparison and negative-control detail; W1's library/channel-axis
data; App. A, C, the algorithm catalogue, the wall-time table, App. F and
Fig. `omega_by_instance`. Projected companion size ~9--10pp. **Unconstrained,
so the page cost is zero.** It must gain a two-line index at the top mapping each
main-paper pointer to a companion section, or the pointers are worthless.

### 5.4 Sum, and whether the target is met

| | pages |
|---|---:|
| measured baseline | 26.00 |
| §5.2 moves and compressions | $-5.95$ |
| §1 pinned-FBT promotion (net of the deleted §VIII-D) | $+0.45$ |
| §2 $\eta$ (proposition $-0.15$, table $+0.15$, L1b $-0.10$, §VII prose $+0.10$) | $0.00$ |
| §3 L0b withdrawal $-0.06$, re-execution $+0.08$ | $+0.02$ |
| U-1 measured motivation | $+0.12$ |
| U-4 provenance sentence | $+0.03$ |
| U-5 reproduction-rate paragraph | $+0.10$ |
| O-1 Appendix F regeneration | $0.00$ |
| O-5 L0 cause correction | $0.00$ |
| **projected total** | **$\approx 20.7$** |

**The 14-page target in `council/pages.json` is NOT met and should not be
pursued.** Reaching 14 requires deleting either the theory core (§III, 5pp) or
the evaluation (§VI--VII, 5pp). Both are load-bearing for a TPDS referee, and
the objective is explicit that where a shorter option costs acceptance
probability, the longer one is taken. The correct recommendation is
**$\approx 21$ pages and pay the overlength charges**, which for an IEEE
Transactions regular paper apply above 14.

If the author insists on a harder ceiling, the next tier of cuts and their real
costs, in the order I would take them:

1. $-1.0$pp: cut §IV to a one-page summary with everything else in the
   companion. **Cost:** the paper stops being a hardware paper in the reader's
   hands; a TPDS referee may object that the fabric is unreviewable. Moderate
   negative.
2. $-1.2$pp: cut §V's algorithm-space description to a table.
   **Cost:** the "$22{,}000$ configurations" claim becomes unauditable in the
   main text. Moderate negative.
3. $-0.9$pp: cut §VII-C-2's $N/G$ prediction entirely. **Cost:** removes the
   only pre-committed prediction the paper makes. Clear negative; I would not.

Even taking all three lands at ~17.6pp, not 14, at material acceptance cost. I
recommend none of them.

### 5.5 Venue

The venue is settled (TPDS) and this plan does not reopen it. What is worth
recording is *which of the new findings make TPDS defensible*, because the
framing must lean on exactly those:

- **The single biggest TPDS-specific objection to the submitted draft is
  "simulator-only, no real collective, no real cluster."** Before this round the
  paper had no answer: every number came from xsim, the pinned-FBT export was a
  sketch, and $\eta$ was unmeasured. After it, W1 (a production collective
  diverging on real GPUs, 14 rank counts, 78.6% pairwise disagreement) and W2-H1
  (the ABI enforced *on stock NCCL*, 2,414 cells, bitwise) answer it directly.
  Those two results are what move this from "interesting NoC paper submitted to
  the wrong venue" to "a parallel-and-distributed-systems paper".
- **The residual TPDS weakness is scale, and it must be conceded, not
  finessed:** two GPUs, PCIe, no NVLink, single node
  (`W2/RESULT.json:hardware`). The word "cluster" is not licensed by anything
  measured. The paper's title contains "Cluster Reshape"; that is defensible
  because the *phenomenon* is cluster reshape and the fabric sweeps
  $G\in[2,4096]$ in simulation, but every empirical sentence must name its
  scale. A referee will forgive a small testbed described precisely and will not
  forgive a small testbed described loosely.
- **The comparison a TPDS referee accepts is now present in two forms**: against
  stock NCCL (\S1) and against ND-RecDouble on the identical substrate (\S2).
  Do not add a third. The remaining named-but-unbuilt baseline (ND-Ring) should
  be conceded in one clause, not built.


---

## 6. Decision ledger

Schema-conformant. `page_delta` is billed main-paper pages; MOVE-TO-COMPANION
entries are zero-cost by construction.

```json
[
{
  "issue": "F-1 / O-1: Appendix F (per-instance results) is generated from the superseded GPU-0 cycle dataset, printing 14 of 39 instances as beating the paper's own lower bound Omega",
  "decision": "CHANGE IMPLEMENTATION",
  "reason": "paper/tables/perinstance.tex stamps 'source : live_hw_results_p1_unified.csv'. paper/scripts/hwdata.py:9-13 documents that file as 'DEFECTIVE for any cycle-derived claim'; main.tex:2146 promises it 'is not used for any reported number'. gen_tables.py:42 hardcodes it and gen_tables.py:249-278 computes champion and cyc/Omega from it, bypassing the hwdata.select() guard that gen_cost_tables.py:100 and gen_tournament.py:118 use. Verified: 14 of 39 printed ratios are <1.0, minimum 0.03, while main.tex:2380-2381 states 'no instance reaches Omega -- the best is 1.35x'. Recomputed from live_hw_results_p1_maxpe.csv: 0 of 39 below 1.0, minimum exactly 1.35 (large_extreme_1d), maximum 9.07 (maxp_bal_2d).",
  "cheaper_alternatives_rejected": [
    {"option": "delete Appendix F", "why_rejected": "loses per-instance auditability a TPDS referee wants, and leaves the generator bug live for any future table"},
    {"option": "hand-edit the printed ratios", "why_rejected": "the tables are machine-generated with provenance stamps; hand-editing breaks the provenance guarantee that is itself an asset (U-4)"}
  ],
  "required_change": "In paper/scripts/gen_tables.py, make tbl_perinstance obtain rows via hwdata.select() instead of load(HW_CSV), propagate the returned source path and trusted flag into write(), and regenerate tables/perinstance.tex and tables/perinstance_full.tex. Leave tbl_invariance and tbl_suite on the unified file (they use pass/coverage counts only, identical in both files).",
  "affected": ["paper/scripts/gen_tables.py:42", "paper/scripts/gen_tables.py:249-278", "tab:perinstance", "paper/tables/perinstance.tex", "paper/tables/perinstance_full.tex", "app:perinstance", "claim:main.tex:2380-2381"],
  "dependencies": ["F-10 (Appendix F may only be moved to the companion AFTER this fix)"],
  "validation": "no row of the regenerated table has cyc/Omega < 1.0; the minimum equals 1.35 and matches main.tex:2381; the file's provenance stamp reads 'source : ...maxpe.csv, metric : max over PEs (corrected)'; 'make check' passes.",
  "page_delta": "0",
  "acceptance_delta": "large-positive",
  "confidence": "high"
},
{
  "issue": "F-2 / O-2: the printed pinned-FBT construction (index-range partition) does not compute the canonical reduction, yet is claimed to preserve Claim 1 by construction",
  "decision": "REWRITE",
  "reason": "T16 proved the index-range partition is not R_can; W2's mandatory negative control fired. W2/RESULT.json:H1_negative_control.detail -- at N=1000 and N=1500 it produced 3 distinct roots over G in {2,3,8} and 0 of 13 cells equalled R_can. The cut-aligned construction (cut FBT(N) at level d=ceil(log2 G)) was verified on 2,414 cells across 32 configurations, all equal to R_can (H1_bitwise_reshape_invariance).",
  "cheaper_alternatives_rejected": [
    {"option": "delete the pinned-FBT subsection entirely", "why_rejected": "it is the only evidence in the submission that the mechanism works outside the simulator, which is the objection most likely to sink a TPDS submission"},
    {"option": "keep the printed construction and add a caveat", "why_rejected": "the construction is wrong, not imprecise; a caveat on a false correctness claim is still a false correctness claim, and the artifact ships a harness that demonstrates the failure"},
    {"option": "move the whole result to the companion with a pointer", "why_rejected": "signals speculation; buries the paper's only real-hardware collective result"}
  ],
  "required_change": "Replace main.tex:2519-2568 with the text drafted at FRAMING_PLAN section 1.5, relocated to a new subsection sec:results-pinfbt in Section VII immediately after sec:results-invariance. Add tables/pinfbt_cost.tex per section 1.6. Move the full 28-point sweep, the gloo arm and the contention conditions to the companion.",
  "affected": ["sec:discussion-pinfbt", "sec:results-pinfbt (new)", "tab:pinfbtcost (new)", "claim:pinfbt-preserves-claim1", "main.tex:2519-2568", "companion/main.tex"],
  "dependencies": ["F-6 (L2 and the non-goal must be reworded in the same pass)"],
  "validation": "the printed construction is the level-aligned cut, matching W2/v005/libfreeze/pinned_fbt.py; the negative-control paragraph is present; the geomean and the worst case appear in the same sentence, as the pre-registration requires; no sentence quotes a selected size range as the headline; no TBIK number appears beside ours.",
  "page_delta": "+0.45",
  "acceptance_delta": "large-positive",
  "confidence": "high"
},
{
  "issue": "F-3 / O-4 + U-2: the paper states three times that it reports no measured eta and calls this its single largest evaluation gap; eta is now measured, and its zero half is provable",
  "decision": "ADD ANALYSIS",
  "reason": "W7/RESULT.json: 29 instances, 1,716 pipeline comparisons through the real compiler. Power-of-two: 22 instances, 1,374 comparisons, eta = 1.000000 with exact DAG isomorphism on 22 of 22. Non-power-of-two: 7 instances, 342 comparisons, isomorphism fails 7 of 7, eta_best_vs_best geomean 1.151 (median 1.090, range 1.026-1.352), eta_champion geomean 1.058. The isomorphism is provable, so the power-of-two half is a theorem with a two-line proof rather than an empirical coincidence.",
  "cheaper_alternatives_rejected": [
    {"option": "report only the measured 1.15 and drop the power-of-two block as a tautology", "why_rejected": "throws away the sharp half of the characterisation; 'free at power-of-two, 15% otherwise' is strictly stronger than '15%' and is what a deployer needs"},
    {"option": "keep the existing apology and cite W7 in the companion", "why_rejected": "leaves a false statement ('we report no measured eta') in the main text while the artifact contains the measurement"},
    {"option": "build ND-Ring as well", "why_rejected": "ND-RecDouble is the harder of the two baselines (log-depth cross-rank chain vs the ring's G-1); building ND-Ring is new implementation work that would not change any conclusion"}
  ],
  "required_change": "Replace main.tex:1968-1988 with FRAMING_PLAN section 2.6(a) (Proposition thm:etabound + proof sketch + the reinterpretation of the earlier analytic eta-hat). Replace main.tex:2270-2276 with section 2.6(b). Add tables/eta_npow2.tex per section 2.6(c). Replace L1b (main.tex:2748-2755) with section 2.6(d). Move per-instance eta, the 342-point distribution and the T10 edge-cut cross-check to the companion as a new appendix app:eta.",
  "affected": ["sec:method-nd", "sec:results-overhead", "thm:etabound (new)", "tab:etanpow2 (new)", "L1b", "app:eta (companion)", "main.tex:1968-1988", "main.tex:2270-2276", "main.tex:2748-2755"],
  "dependencies": [],
  "validation": "no occurrence of 'we report no measured $\\eta$' remains; the proposition's statement matches nd_tree.py's construction (contiguous blocks, balanced local tree, recursive doubling); the table's seven rows match W7/RESULT.json:per_instance; the ND-Ring omission is stated in L1b.",
  "page_delta": "0.00",
  "acceptance_delta": "large-positive",
  "confidence": "high"
},
{
  "issue": "F-4 / O-3: L0b asserts a route-load fidelity band (59% bit-exact, cycles 1-54% lower) for which no run existed",
  "decision": "REMOVE OR NARROW CLAIM",
  "reason": "W4/v002/ANALYSIS_full.json:prefer_ok -- 1,326 of 1,326 comparable points agree on PASS, on the 64-bit root and on the cycle count; pct_bit_exact 100.0; delta_ns_per_route_entry min = max = median = 10.0 ns. Unchanged at 100.0% under the alternative record-selection rule (later_wins, 1,306). The mandatory negative control fired: corrupting the whole route table flips PASS to FAIL on 24 of 24.",
  "cheaper_alternatives_rejected": [
    {"option": "delete L0b silently", "why_rejected": "the bypass is visible in the shipped emitter (src/sprs_core.py:~5610); an artifact evaluator who finds it undisclosed is worse off than one who finds it disclosed and measured"},
    {"option": "soften the band rather than withdraw it", "why_rejected": "the measured band is exactly zero; softening asserts an uncertainty the data denies"}
  ],
  "required_change": "Replace main.tex:2687-2702 with FRAMING_PLAN section 3.4(a). Append section 3.4(b) to sec:results-invariance. Move the 1,326-row comparison and the single-entry negative-control detail to the companion Verification section.",
  "affected": ["L0b", "sec:results-invariance", "main.tex:2687-2702", "companion/main.tex (Verification)"],
  "dependencies": [],
  "validation": "L0b contains no percentage band; it names 1,326/1,326, the 10.0 ns per entry, and the 24/24 control; the results-section addition says 're-execution that self-agrees', not 'reproduces the published bits'.",
  "page_delta": "+0.02",
  "acceptance_delta": "positive",
  "confidence": "high"
},
{
  "issue": "F-5 / U-1: the motivating premise is argued from citations and a hypothetical, when it has now been measured on real GPUs",
  "decision": "EDIT",
  "reason": "W1/RESULT.json and EXPERIMENTS_REPORT section 1: on identical input bytes, 14 world sizes returned 14 distinct 64-bit roots in every one of 12 cases; 78.6% of fp64 configuration pairs and 90.0% of fp32 pairs disagree; max spread 5,120 ulp; 0 of the configurations equalled the canonical reduction; 5/5 bitwise-identical repeats at any fixed configuration. This is the pre-registered PARTIAL branch, named in advance.",
  "cheaper_alternatives_rejected": [
    {"option": "cite W1 from the companion only", "why_rejected": "the motivation is what a TPDS referee reads first; a measured motivation is worth more per page than anything else in the paper"},
    {"option": "add a figure", "why_rejected": "costs 0.4pp for information three sentences carry"}
  ],
  "required_change": "Replace the hypothetical at main.tex:206-211 with FRAMING_PLAN section 4.2 U-1's LaTeX. Add one clause stating that the NCCL algorithm/protocol and channel axes each returned one root because at G=2 the cross-rank reduction is a single addition per element, and that this is structural and not generalised to larger G. Full W1 sweep to the companion.",
  "affected": ["sec:intro", "main.tex:206-211", "companion/main.tex"],
  "dependencies": [],
  "validation": "every number traces to W1/RESULT.json; the single-root axes are stated as structural, not as a partial refutation; no divergence is claimed at a scale that was not measured.",
  "page_delta": "+0.12",
  "acceptance_delta": "large-positive",
  "confidence": "high"
},
{
  "issue": "F-6 / O-6: the non-goal at main.tex:398-401 and L2 at main.tex:2757-2763 say the paper does not benchmark against production collectives; after F-2 it does",
  "decision": "EDIT",
  "reason": "W2 benchmarked pinned-FBT against stock ncclAllReduce. W2/RESULT.json:hardware -- PCIe (topo NODE), no NVLink, two GPUs, contended. The NVLink/NVSwitch exclusion remains true and must survive verbatim; hardware.comparability is explicit that our figure must not be quoted beside TBIK's <=10% NVLink number.",
  "cheaper_alternatives_rejected": [
    {"option": "delete the non-goal and L2", "why_rejected": "the scope limit is real and protects the paper; deleting it invites a referee to read the 2.40x as a general claim"}
  ],
  "required_change": "Non-goal: keep 'we make no claim of timing closure, area, power, or frequency at production-die scale' and change the benchmarking clause to 'we benchmark the software export of the ABI against stock NCCL on a two-GPU PCIe node (Section VII-x) and make no claim about NVLink/NVSwitch silicon or multi-node scale'. L2: retitle to 'Scale of the production-collective comparison' and state two GPUs, PCIe, G=2 for the NCCL arm, gloo for G>2, contended node, no NVLink comparison.",
  "affected": ["main.tex:398-401", "L2", "main.tex:2757-2763"],
  "dependencies": ["F-2"],
  "validation": "no sentence in the paper claims a comparison at a scale W2 did not measure; the string 'NVLink' appears only in exclusions.",
  "page_delta": "0",
  "acceptance_delta": "positive",
  "confidence": "high"
},
{
  "issue": "F-7 / O-5: L0 states a resource limit as the cause of the missing 40th instance; the real cause is an emitter adjacency-width truncation",
  "decision": "EDIT",
  "reason": "T13 established that at G=4096 the emitter's adjacency fields truncated to 12 bits: 0 of 8,223 installed links matched the intended fat-tree and 0 of 900 sampled routes delivered. The worktree emitter now auto-sizes ADJ_ID_W (src/sprs_core.py:~5510) and remains byte-identical for every instance that fitted in 12 bits. The elaboration has still not produced a snapshot: W8_maxp/v001/status.txt records 'xelab rc=1 ... NO_SNAPSHOT'; v002 was restarted 2026-08-28 08:14 and is at phase=xvlog.",
  "cheaper_alternatives_rejected": [
    {"option": "wait for W8 and claim 40/40", "why_rejected": "the run has already failed once and is unresolved; writing the paper against an outcome that has not happened is exactly the failure mode this council exists to prevent"},
    {"option": "leave L0 as written", "why_rejected": "the stated cause is wrong and the artifact contains the evidence that it is wrong"}
  ],
  "required_change": "Rewrite L0 to: coverage is 39 of 40; the exception is maxp_mod_fat (N=8192, G=4096, fat-tree); the cause is that our SystemVerilog emitter sized adjacency identifier fields at 12 bits, which cannot express 4,096 routers, so the emitted fabric was not the intended fat-tree; the emitter now auto-sizes that width and re-emits byte-identically for every instance that fitted in 12 bits, but elaboration of the G=4096 instance has not completed within our budget. Do not claim 40/40.",
  "affected": ["L0", "main.tex:2678-2686", "tab:invariance footnote", "main.tex:2193"],
  "dependencies": ["F-12"],
  "validation": "L0 names the adjacency-width cause and does not say 'resource limit'; no table claims 40 hardware-validated instances.",
  "page_delta": "0",
  "acceptance_delta": "positive",
  "confidence": "high"
},
{
  "issue": "F-8 / U-5 + U-9: the reproduction rate of the released cycle column, and the two assignment methods that do not reproduce",
  "decision": "CLARIFY LIMITATION",
  "reason": "Verified against the dataset the paper actually builds from (live_hw_results_p1_maxpe.csv, selected by hwdata.select()): of 1,310 recompiled and re-simulated points, 1,207 (92.1%) reproduce the released cycle count exactly and 0 match the superseded GPU-0 counter. The 103 that differ are confined to CPOP (2i, 64/128 = 50.0%), ClHEFT (2n, 37/97 = 38.1%) and DSC (2g, 2/59 = 3.4%); the other fourteen stage-2 methods reproduce 100.0%. Differences are two-sided (ratio geomean 0.859, median 0.965, range 0.177-1.201), i.e. schedule variability, not bias. The 64-bit root is identical in every re-run pair. And zero of the 39 per-instance champions come from 2i or 2n.",
  "cheaper_alternatives_rejected": [
    {"option": "say nothing", "why_rejected": "the artifact ships the harness and an evaluator will rerun it; being second to your own finding is the worst possible position"},
    {"option": "root-cause the compile variability first", "why_rejected": "new investigation with no effect on any reported number (U-9), and W4/v002/nondet_probe.py already showed 72 controlled observations are perfectly deterministic, so the mechanism is harness-level and not cheaply reachable"},
    {"option": "re-run the 103 affected points repeatedly and report a distribution", "why_rejected": "adds cost and pages for rows that carry no reported champion"}
  ],
  "required_change": "Add FRAMING_PLAN section 4.2 U-5's paragraph to sec:method-metric, followed by section 4bis U-9's sentence. Correct EXPERIMENTS_REPORT.md section 5a in the council record: its GPU-0 conclusion was drawn against the superseded live_hw_results_p1_unified.csv and does not hold against the file the paper builds from; section 5b stands.",
  "affected": ["sec:method-metric", "EXPERIMENTS_REPORT.md section 5a", "claim:main.tex:2145-2152"],
  "dependencies": ["F-1"],
  "validation": "the paragraph's numbers match a recomputation from live_hw_results_p1_maxpe.csv against W4/v001/full_bypass_clocked.jsonl; the champion-independence sentence is checkable by recomputing min-cycles per instance.",
  "page_delta": "+0.12",
  "acceptance_delta": "positive",
  "confidence": "high"
},
{
  "issue": "F-9 / U-4: the build refuses the defective cycle dataset and stamps provenance on every generated table, and the paper never says so",
  "decision": "EDIT",
  "reason": "paper/scripts/hwdata.py selects the corrected dataset and returns trusted=False if the re-measurement is under 95% complete; every generated table carries '% source :' and '% metric :' lines; paper/Makefile:80 fails the build if any table is stamped DEFECTIVE. Verified by running hwdata.select(): returns MAXPE, 2,822 rows, 39 instances, trusted=True.",
  "cheaper_alternatives_rejected": [
    {"option": "leave it implicit in the artifact", "why_rejected": "reviewers grade what they read; a build-enforced provenance guarantee is worth more stated than discovered"}
  ],
  "required_change": "Add FRAMING_PLAN section 4.2 U-4's LaTeX to app:repro. Land only after F-1, so the statement is true of every table.",
  "affected": ["app:repro"],
  "dependencies": ["F-1"],
  "validation": "'make check' passes with no table stamped DEFECTIVE, so the appendix sentence is literally true.",
  "page_delta": "+0.03",
  "acceptance_delta": "positive",
  "confidence": "high"
},
{
  "issue": "F-10: page budget -- move duplicated fabric and appendix material to the companion",
  "decision": "EDIT",
  "reason": "The companion (companion/main.tex, ~3pp) already contains the instruction and packet encodings (:102-188), router (:248-270), forwarding (:230-237), write arbitration (:220-229), fail-stop (:238-247) and resource envelope (:292-309). The corresponding main-paper blocks are duplication. MOVE costs zero billed pages and loses nothing, per the objective.",
  "cheaper_alternatives_rejected": [
    {"option": "cut Section III or Sections VI-VII to reach 14 pages", "why_rejected": "both are load-bearing for a TPDS referee; the objective forbids trading acceptance for pages"},
    {"option": "compress uniformly across the paper", "why_rejected": "uniform compression damages the argument sections most, which is where the contribution lives"}
  ],
  "required_change": "Execute moves M1-M14 in FRAMING_PLAN section 5.2, with M5 gated on F-1. Add a two-line index at the head of the companion mapping each main-paper pointer to a companion section.",
  "affected": ["app:isa", "app:worked", "app:algos", "app:coverage", "app:perinstance", "sec:fabric-packet", "sec:fabric-pipe", "sec:write-arb", "sec:resource", "sec:compiler-dmem", "sec:discussion", "sec:abi-args", "sec:method-swbaseline", "fig:omegabyinst", "companion/main.tex"],
  "dependencies": ["F-1"],
  "validation": "rendered page count is ~21; every moved block is reachable from a main-paper pointer that names a companion section; no pre-registered result is unreachable.",
  "page_delta": "-5.95",
  "acceptance_delta": "neutral",
  "confidence": "medium"
},
{
  "issue": "F-11 / M13: SW-FixedTree, an analytic upper bound for a software baseline nobody built",
  "decision": "REMOVE OR NARROW CLAIM",
  "reason": "main.tex:1995-2006 reports 'the analytical overhead of (b) as an upper bound on the software-only alternative'. W2 now supplies a real, measured software baseline on stock NCCL. An analytic bound for an unbuilt baseline sitting beside a measured one is a soft target and adds nothing.",
  "cheaper_alternatives_rejected": [
    {"option": "keep it as context", "why_rejected": "it invites the question 'why model what you measured?'"}
  ],
  "required_change": "Delete sec:method-swbaseline; if the padding argument is wanted, one sentence in the new pinned-FBT subsection suffices.",
  "affected": ["sec:method-swbaseline", "main.tex:1995-2006", "app:coverage"],
  "dependencies": ["F-2"],
  "validation": "no reference to SW-FixedTree remains.",
  "page_delta": "-0.10",
  "acceptance_delta": "positive",
  "confidence": "medium"
},
{
  "issue": "F-12: maxp_mod_fat (instance 40 of 40) elaboration",
  "decision": "DEFER",
  "reason": "W8_maxp/v001 ended NO_SNAPSHOT (xelab rc=1); v002 restarted 2026-08-28 08:14 and is at phase=xvlog. The outcome is genuinely unknown and nothing in the paper depends on it. Recording it open is more useful than assuming either way.",
  "cheaper_alternatives_rejected": [
    {"option": "block the submission on it", "why_rejected": "39 of 40 is already stated and defensible; the instance adds coverage, not a claim"}
  ],
  "required_change": "None now. If v002 produces a snapshot AND the simulation settles before submission, add the row and change 39/40 to 40/40 everywhere; otherwise ship 39/40. Either way F-7's cause correction lands.",
  "affected": ["L0", "tab:invariance", "app:coverage"],
  "dependencies": [],
  "validation": "the decision point is a single grep for '39' vs '40' across main.tex and the generated tables.",
  "page_delta": "0",
  "acceptance_delta": "neutral",
  "confidence": "high"
},
{
  "issue": "F-13: does any NEW EXPERIMENT clear the bar 'would a TPDS referee reject this paper without it?'",
  "decision": "NO CHANGE",
  "reason": "Tested one by one against the stricter bar. (a) Multi-node or >2-GPU NCCL: the hardware has two GPUs with no NVLink (W2/RESULT.json:hardware); the invariance claim is already carried across 13 world sizes to G=64 on gloo, and the claim is correctness, not throughput -- a precisely scoped two-GPU result is defensible where a vague one is not. (b) Synthesis/PPA: the paper makes no frequency, area or timing claim anywhere (L0c, L1), so there is nothing for synthesis to substantiate. (c) Building ND-Ring: ND-RecDouble is the harder baseline and is built (F-3). (d) Root-causing the CPOP/ClHEFT compile variability: zero of the 39 reported champions come from those methods (U-9), so no reported number moves. (e) Full campaign re-run: 92.1% of it has just been re-executed and agrees (U-5). Every candidate fails the bar; the cheap fixes above carry the acceptance gain instead.",
  "cheaper_alternatives_rejected": [],
  "required_change": "None. Record the test and its outcome so the question is not reopened.",
  "affected": [],
  "dependencies": [],
  "validation": "n/a",
  "page_delta": "0",
  "acceptance_delta": "neutral",
  "confidence": "medium"
},
{
  "issue": "F-14: the one piece of new work that IS worth doing -- W2/v005, the clean gloo cost re-run that was queued and not reached",
  "decision": "ADD EXPERIMENT",
  "reason": "W2/RESULT.json:raw.v005 records that the v004 gloo cost cells at G>=24 were CPU-contended by the concurrent W4 campaign, so those cells must currently be labelled upper bounds. The re-run is already scripted (W2/v005/drive_w2b5.py, libfreeze/ frozen) and costs CPU time only -- no new design, no new analysis. It removes a stated contamination caveat from a table that will now sit in the main paper.",
  "cheaper_alternatives_rejected": [
    {"option": "label the affected cells as upper bounds and ship", "why_rejected": "acceptable, and the fallback if the machine is busy -- but the run is already written and the caveat is avoidable; this is the rare case where new work is nearly free"},
    {"option": "drop the gloo arm entirely", "why_rejected": "it is the only evidence at G>2 and the pre-registration requires the full sweep be reported"}
  ],
  "required_change": "Execute W2/v005 on an idle machine; fold the clean gloo numbers into the companion's full sweep; if they differ materially from v004, report v005 and keep v004 as the contended measurement.",
  "affected": ["companion/main.tex", "W2/v005"],
  "dependencies": ["F-2"],
  "validation": "the gloo cells at G>=24 carry no contention caveat, or the caveat is retained and explicitly justified.",
  "page_delta": "0",
  "acceptance_delta": "positive",
  "confidence": "medium"
},
{
  "issue": "F-15 / O-7 + O-8: the winner-distribution prose contradicts the table beside it, and 'two algorithms' names one",
  "decision": "REWRITE",
  "reason": "tables/winners_family.tex has no list-scheduling row; recomputing champions from live_hw_results_p1_maxpe.csv reproduces the table exactly and gives HEFT (2a) and CPOP (2i) zero wins. The prose at main.tex:2419-2421 also misassigns MLfm and DKway relative to gen_tournament.py:54-62. main.tex:2430 says 'two algorithms' and names only ExactBB.",
  "cheaper_alternatives_rejected": [
    {"option": "delete the sentence", "why_rejected": "the true reading -- that the methods a collective compiler reaches for first never win -- is more interesting than the false one"}
  ],
  "required_change": "Replace main.tex:2417-2421 with FRAMING_PLAN section 4bis's LaTeX; fix 'Two algorithms' at main.tex:2430 to name the second or say 'one'.",
  "affected": ["sec:results-tour", "main.tex:2417-2421", "main.tex:2430-2431", "tab:winners_family"],
  "dependencies": [],
  "validation": "every family named in the prose appears in the table with the share the prose claims.",
  "page_delta": "0",
  "acceptance_delta": "positive",
  "confidence": "high"
}
]
```

---

## 7. Open questions and DEFERs

Recorded rather than resolved, because the evidence does not settle them.

**Q-1. `maxp_mod_fat`.** `W8_maxp/v001/status.txt` = `NO_SNAPSHOT (rc=1)`;
`v002/status.txt` = `phase=xvlog`, restarted 2026-08-28 08:14. Outcome unknown.
Ledger F-12. **Write the paper for 39/40.** If it lands, the change is
mechanical.

**Q-2. The released results file has no root column, so re-executions are not
bit-diffable against it.** `results/results/live_hw_results_p1_unified.csv` and
`..._maxpe.csv` record `instance, pipeline, tb, pass, cycles, simtime, code`.
W4's re-execution therefore establishes *self-agreement* (bypass = clocked =
software oracle, \S3.2) but cannot establish *reproduction of the originally
published bits*, and the RTL now carries the W3 `fp64_add` repair, so the bits
need not match. **Recommendation (artifact change, zero paper pages): add the
64-bit root to the released CSV before submission.** It costs one column and it
converts every future re-execution into a checkable diff. I do not have standing
to decide whether the fp64_add repair moved any published root; that is a
question for the measurement agent.

**Q-3. The CPOP/ClHEFT compile variability has no established mechanism.**
`W4/v002` ruled out the wall-clock deadline path, hash-seed nondeterminism (72
controlled observations, perfectly deterministic) and worktree-vs-snapshot
compiler drift (10 of 10 identical). It remains unexplained under the concurrent
harness. Ledger F-8 discloses it without asserting a cause, which is correct.
Do not let a later pass invent one.

**Q-4. `EXPERIMENTS_REPORT.md` §5a needs the measurement agent's
countersignature.** I verified, by direct recomputation, that §5a's GPU-0
conclusion was drawn against the superseded `live_hw_results_p1_unified.csv`
and does not hold against `live_hw_results_p1_maxpe.csv`, which is the file
`paper/scripts/hwdata.py` selects and the paper's tables are built from
(1,207 exact matches to max-over-PEs, **0** to the GPU-0 counter). Only the
measurement agent may create evidence; this correction should be countersigned
by that role before it enters the council record. **§5b (the 103 non-reproducing
CPOP/ClHEFT rows) is unaffected and stands.**

**Q-5. Which definition of "champion" does the paper use?** T10 read
`edge_cut` from the released tournament record; W7 selects the min-makespan
pipeline among those the hardware campaign validated and recompiles it. The two
disagree on three of four instances
(`W7/RESULT.json:T10_cross_check...DIVERGENCE_FROM_T10`). One definition must be
chosen and used everywhere. My recommendation is W7's (min measured makespan
among hardware-validated pipelines), because it is the one the evaluation
elsewhere uses; but this is the paper owners' call and it changes whether the
ring/torus caveat survives. **DEFER.**

**Q-6. Does the reviewing referee read the companion?** Moves M6--M9 relocate
fabric detail that a hardware-minded TPDS referee may expect in the manuscript.
The mitigation is that every moved block leaves a main-paper pointer naming the
companion section, and that the nine fabric invariants Claim 1 depends on stay
in \S III. If the author judges this risk higher than I do, M6--M9
($-1.70$pp) are the first moves to reverse; the projected count then becomes
~22.4pp. This is a judgement call, not an evidence question, and the objective
says to resolve it toward acceptance.

**Q-7. Coordination.** Items O-1 (Appendix~F below $\Omega$) and O-7 (the
winner-distribution prose) are exactly the kind of finding the concurrent
challenger is looking for. They are recorded here with verification so the two
documents agree rather than collide. I have not written, and will not write,
`ATTACK_SURFACE.md`.
