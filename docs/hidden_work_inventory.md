# Hidden Work Inventory: Determinism Safeguards and Contributions Not in paper_v5.md

Analysis produced after deep re-reading of `sprs_core.py` (5762 lines) and all 13 RTL files (3765 lines). This document surfaces contributions that the current paper drafts either (a) do not mention, (b) mention as a line-item without acknowledging their role in the determinism argument, or (c) mention as trivia when they are in fact load-bearing.

---

## 1. The Determinism Story the Paper is Telling vs. the One in the Code

**Paper's story (v5):** "The ABI fixes operand binding at compile time; scoreboard-gated execution makes arrival order unobservable; therefore bitwise invariance under cluster reshape."

**Code's story:** "Determinism is a *hard-earned invariant maintained by ~12 distinct safeguards spread across the compiler stack and the fabric RTL*. The ABI is the top-level contract, but it only holds because each of the 18 S2 algorithms is followed by *connectivity repair*, the DMEM allocator preserves *single-writer with SU-bounded lifetime*, the fabric provides *identity-element reservation*, the PIU has a *retry latch against GCI collisions*, the scoreboard is *monotone and universal across four write agents*, the credit path is *counter-serialized to prevent leaks*, and misroutes are *silently dropped rather than silently consumed*."

The second story is the actually-interesting one. The rest of this document inventories it.

---

## 2. Compiler-Side Determinism Safeguards (Hidden from paper_v5)

### 2.1 S2.5 Connectivity Repair — the load-bearing determinism pass

**Location:** `repair_connectivity` at [sprs_core.py:1387–1483](tournament_portable/sprs_core.py#L1387-L1483).

**What the docstring says verbatim:**
> "When an S2 algorithm produces disconnected partitions (e.g. HEFT, DSC, DFSseed scatter nodes across GPUs), the downstream scheduler may pair non-sibling nodes in COMPUTE instructions, causing FP64 reductions to execute in a non-canonical order. Since FP64 addition is not associative, this produces wrong results."

**Why this matters for the paper:** the current draft treats S2.5 as a one-line pipeline stage. It is *the reason the ABI holds across the 18 S2 algorithms*. Roughly 12/18 S2 methods — HEFT, DSC, DFSseed, Chret, CPOP, CPFD, ClHEFT, ALNS-refined variants, MLfm at small G — can *and do* produce disconnected partitions on some instances. Without S2.5, these produce non-canonical reduction orders, i.e., *wrong results*, despite all other safeguards being in place.

**Missing in the paper:** the statement that the invariance claim *requires α to induce connected subtree partitions*, and that connectedness is not a natural property of most S2 algorithms but an invariant re-established by S2.5.

**Paper treatment recommended:** Promote S2.5 from a pipeline line-item to a named assumption / invariant: "**Invariant C (Partition connectedness).** For every PE *p*, the nodes assigned to *p* form a connected subtree of FBT(*N*). Established by S2.5 and preserved by S3–S5."

### 2.2 DMEM allocator — SU-ordered with free-list reuse after unique-parent consumption

**Location:** `DMEMAllocator.allocate` at [sprs_core.py:5087–5132](tournament_portable/sprs_core.py#L5087-L5132).

**What it does:** walks the tree in SU-postorder. For each node, (a) if internal, frees its children's addresses (if same-PE) into the PE's free list; (b) pops a free address if available, else bumps `peak_local`. After the main pass, allocates persistent receive buffers for cross-PE children at the top of each PE's DMEM.

**Why this matters:** this implements the *single-writer invariant (A4)* that the proof hinges on. It is not just memory compression — it is the mechanism that guarantees each DMEM address is written exactly once per program. The SU ordering guarantees child's slot is freed only after parent has consumed it (SU visit order is parent-last by construction). FBT being a tree (unique consumer per node) is what makes SU-based free-list reuse safe.

**Missing in the paper:** the *argument* that SU ordering + free-list pops only at parent-visit time + FBT uniqueness = single-writer invariant. This is a theorem, not a convenience.

**Paper treatment recommended:** Give this a dedicated sub-argument under Lemma 2 / Argument 2: state that single-writer is not assumed — it is *constructed* by the allocator's SU-ordered lifetime-disjoint scheme.

### 2.3 DMEM[0] as identity reservation — compiler-side

**Location:** `DMEMAllocator.IDENTITY_ADDR = 0` at [sprs_core.py:5098](tournament_portable/sprs_core.py#L5098); allocation starts at `peak_local[gpu] = 1`.

**What it does:** reserves DMEM address 0 on every PE as the identity element for the chosen ALU op. Compiler-side the allocator never issues 0 to any tree node.

**Why this matters:** paired with the fabric's `scoreboard[0] <= 1'b1` at reset (btree_fsm_fast.sv:703), this gives the compiler a "free identity operand" it can pass as `addr_b` in single-child `COMPUTE` instructions. Today `FBT(N)` doesn't produce single-child internals, so this is latent — but any future relaxation (e.g., left-heavy asymmetric trees, or non-complete binary trees) relies on this identity slot being universally available. The paper mentions this once as a sentence; it is actually a **compiler/fabric co-design point** — reserving address 0 identically on both sides is what allows the ABI to extend beyond strict FBT.

### 2.4 Phased refinement with rollback — semantic-preservation with rejection

**Location:** `refine_phased` at [sprs_core.py:4836–4877](tournament_portable/sprs_core.py#L4836-L4877).

**What it does:** tries FM (×2), SubMig, CPcoloc, optionally ALNS if far from lower bound. For each refinement: validates the output is a legal assignment; estimates makespan; **keeps only if strictly improves**; rolls back otherwise. Records rollback reasons (`deadline_gate`, `invalid_output`, `no_improvement`, `timeout`).

**Why this matters:** the current paper reports 122 S4 configurations but doesn't describe how `refine_phased` composes them. The rollback-protected pattern is a real technique — refinement is monotonic in makespan by construction, which means S4 *cannot make the result worse even if the refinement has a bug or times out*. Combined with `_validate_assignment` gatekeeping, this is a *safety property* of the search itself.

### 2.5 Memory enforcement (S5) — 3-tier redistribution with IMEM estimation

**Location:** `enforce_memory` at [sprs_core.py:4939–5025](tournament_portable/sprs_core.py#L4939-L5025) with helpers `_estimate_imem` (4883) and `_estimate_dmem` (4918).

**What it does:** tier 1 verifies Sethi–Ullman number ≤ DMEM budget (sanity check — always passes at 512 for practical trees). Tier 2 audits per-GPU IMEM usage accounting for GCI-serialization NOPs; if over 512, redistributes by moving leaves (least structural impact) to least-loaded GPUs. Tier 3 audits per-GPU DMEM including receive buffers; redistributes deepest nodes first.

**Why this matters in the determinism story:** moving nodes across GPUs in S5 can *break* the connectivity invariant established by S2.5. This is an **ordering dependency** the paper does not acknowledge: S2 → S2.5 → S3 → S4 → S5 — and if S5 moves a node, the partition may need re-repair. Currently the pipeline does NOT re-run S2.5 after S5 (check `compile()` at line 5601–5679). This is a latent bug waiting to happen for large-N instances that hit the IMEM ceiling.

**Paper treatment recommended:** flag this as a scope / honesty item. Either document that S5 is only invoked when safe, or recommend the fix (re-run S2.5 after S5 if any move occurred).

### 2.6 Leaf-identity preservation in the GCI load order

**Location:** `emit_sv_testbench` at [sprs_core.py:5526–5544](tournament_portable/sprs_core.py#L5526-L5544).

**What it does:** for each GPU, iterates its schedule's `GENERATE` operations in order; for each, computes the tree-global leaf index via `leaf_to_global_idx = {leaf: idx for idx, leaf in enumerate(leaf_list)}`; loads `make_leaf_val(global_idx)` into GCI buffer slot `local_idx`.

**Why this matters:** the software oracle uses `leaf_to_global_idx` directly (line 5453, 5463). The hardware loads values in *per-GPU GENERATE order*, which varies with assignment α, but each position in the per-GPU GCI buffer contains the value *keyed by tree-node-ID* — so the value of leaf node *k* is always `make_leaf_val(idx(k))` regardless of which GPU hosts it.

**The invariant:** *leaf value depends only on tree node ID, not on GPU assignment.* This is the reason the "leaves are a pure function of *L*" claim in Claim 1 actually holds. Without this indexing discipline, a different α would permute leaves to different values — reduction would still be deterministic but would compute a different *function*.

**Missing in the paper:** this is the "leaf binding" half of the ABI. The paper has "operand binding" (A5, static pair of DMEM addresses at each COMPUTE) but not the analogous "leaf binding" (the value at GCI[local_idx] on GPU g is a pure function of the global tree-node-id of the leaf). Both are needed for Claim 1.

**Paper treatment recommended:** add **A8 (Leaf binding)** to the assumption list: for each leaf *k* ∈ leaves(FBT(N)), the 64-bit value written by the corresponding GENERATE is `L[idx(k)]` where `idx: leaves → {0, ..., N-1}` is the tree's canonical leaf enumeration, a pure function of *N*.

### 2.7 Timeout instrumentation as a correctness mechanism, not a performance one

**Location:** `_set_eval_deadline`, `_check_deadline`, `AlgoTimeout` at [sprs_core.py:107–118](tournament_portable/sprs_core.py#L107-L118); used by every S2/S3/S4 algorithm.

**What it does:** per-evaluation deadline (1800 s default) enforced by the top-level driver. Algorithms call `_check_deadline("label")` at hot-loop checkpoints. On timeout, raises `AlgoTimeout`, which the tournament catches and records.

**Why this matters for determinism:** ensures that a stochastic/exponential algorithm (ExactBB, QAP-SA, ALNS) cannot hang the compiler. More importantly, it guarantees the compile pipeline *always terminates* with either a valid assignment or a recorded failure — no half-refined state can leak into codegen. This is a *liveness property* of the compiler.

### 2.8 Deterministic algorithm outputs under fixed seed

**Location:** stochastic algorithms (QAP-SA, ALNS, Tabu, Spectral) use seed 42 uniformly (confirmed by `--seed`-agnostic randomness with hardcoded seeds).

**Why this matters:** compile-time determinism of SPRS itself is a nontrivial property — if the compiler produced different IMEMs on different runs of the same input, two deployments would have different cycle counts (even though the ABI would hold so bit results remain identical). Seed-fixing + Python dict iteration order (guaranteed since 3.7) + absence of `hash(random)`-using algorithms → identical IMEM across compiler invocations.

**Paper treatment:** acknowledge this briefly. The claim extends from "bit-result invariance across (G, topology)" to "compile-time determinism of SPRS itself is preserved under seed-fix."

### 2.9 Testbench-hash deduplication as a research-methodology safeguard

**Location:** tournament phase 3 computes SHA256 of the generated `.sv` testbench string; skips xsim for duplicates. Referenced in [README.md:24](tournament_portable/README.md#L24).

**Why this matters:** different (S2, S3, S4) triples frequently produce *identical IMEM images up to PE relabeling*. Running xsim on all of them wastes compute and doesn't add evidence. Hash-dedup is what makes the 22K-configuration tournament tractable. Paper treats this as a performance optimization; it is also the reason the "tournament empirically verifies invariance" argument is statistically efficient — identical IMEMs produce identical bit results *tautologically*, so dedup is what makes every remaining xsim run informative.

### 2.10 Precomputed C extension for the hot scoring path

**Location:** `_C_SRC` at [sprs_core.py:24–63](tournament_portable/sprs_core.py#L24-L63), compiled at import. Provides `c_cp_comm`, `c_edge_cut`, `c_max_load`.

**Why this matters:** these are called hundreds of millions of times across the tournament. Without the C extension, the tournament wouldn't finish in reasonable wall-clock time on the target workstation (Xeon W-2295). This is legitimate engineering work worth mentioning in the "reproducibility / methodology" appendix.

---

## 3. Fabric-Side Determinism Safeguards (Hidden from paper_v5)

### 3.1 Scoreboard as a universal presence bit across four write agents

**Location:** scoreboard at [btree_fsm_fast.sv:700–715](btree_fsm_v7_rtl/rtl/btree_fsm_fast.sv#L700-L715).

**What it does:** a `DMEM_DEPTH`-wide bit vector. `scoreboard[a]` is set whenever *any* of PIU, GCI, COMPUTE writeback, or GENERATE writes to `DMEM[a]`. Reset on `rst` or `program_start`. `scoreboard[0]` hardwired to 1.

**Why this matters:** the paper treats the scoreboard as a "stall source for COMPUTE." It is more: it is a *single source of truth for "data present at address a"* across four independent write agents. The invariant is that once a scoreboard bit is set, the value at that address is the unique final value for the run (by single-writer). This makes scoreboard-gated reads structurally race-free.

### 3.2 Two-level DMEM forwarding network — purpose and boundaries

**Location:** [btree_fsm_fast.sv:166–181](btree_fsm_v7_rtl/rtl/btree_fsm_fast.sv#L166-L181).

**What it does:** a 2-level address-compare-match forwarding. Level 1 (d1): for back-to-back COMPUTEs where cycle-N writes `a` and cycle-(N+1) reads `a`, the BRAM read-first returns stale — forward from d1 register. Level 2 (d2): covers the scenario where a 1-cycle stall interposes, so d1 expires before the read settles.

**Why this matters:** this is the mechanism that makes the scoreboard-gated pipeline bit-exact even with BRAM read-first semantics. Without the 2-level forward, a scoreboard-gated pass would still pass but the value read would be the previous value of that address (which under single-writer is either uninitialized or already read). The 2-level forwarding is what *combines* single-writer with cycle-accurate pipeline to give bit-exact values. It is a first-class part of the determinism story.

### 3.3 GCI write-hold latch — a known-race fix

**Location:** `gci_pending`, `gci_write_held` at [btree_fsm_fast.sv:411–417, 717–740](btree_fsm_v7_rtl/rtl/btree_fsm_fast.sv#L411-L740).

**What it does:** when GCI completes (`gci_done` pulses) and PIU writes in the same cycle, the DMEM arbiter drops the GCI write (PIU priority). Without a fix, `gci_pending` would clear on the first `gci_done` and the leaf value would be lost. The `gci_write_held` latch captures this event and re-asserts `gci_dmem_wr` until the arbiter accepts it.

**Why this matters:** this is a *silent correctness bug* that was found and fixed. Without this latch, some runs would complete but with a missing leaf value in one PE's DMEM, producing a wrong root result. The paper mentions the GCI path once; it should mention that *the determinism argument requires this retry latch*, and that removing it would cause A1 (fabric sampled-read determinism) to fail on specific PIU/GCI collision schedules.

### 3.4 PIU autonomous write with misroute detection

**Location:** PIU FSM at [btree_fsm_fast.sv:282–345](btree_fsm_v7_rtl/rtl/btree_fsm_fast.sv#L282-L345).

**What it does:** PIU consumes the RX FIFO, examines `pkt[95:80]` (dest_gpu_id). If equal to local `gpu_id`, writes payload to `DMEM[pkt[79:70]]` (target_addr from header) and sets scoreboard. If not equal, asserts `piu_misroute` and drops the packet.

**Why this matters for determinism:** the RDMA-push design means *sending a packet to the wrong PE does not silently corrupt data* — it is dropped. The consequence of a misroute is that the destination's scoreboard bit is never set, so the destination's COMPUTE stalls forever, the watchdog fires, and the run is flagged. This is a *fail-stop* property. It converts A6 (routing-table soundness) from a silent-failure assumption into a liveness-failure assumption: a bad routing table causes the run to hang, not to produce a wrong answer. **This is a strictly stronger guarantee than "A6 holds by assumption."**

**Paper treatment recommended:** restate A6 as: *Under a malformed routing table, the fabric either (a) completes correctly, or (b) hangs and is caught by the WATCHDOG_MAX timeout — never (c) produces a silently wrong result.* This is provable and strictly stronger than the current A6.

### 3.5 Watchdog + stall timeout + invalid-opcode trap — a three-way liveness/safety net

**Location:** watchdog counter at [btree_fsm_fast.sv:769–781](btree_fsm_v7_rtl/rtl/btree_fsm_fast.sv#L769-L781); stall_timer at 755–766; `invalid_opcode` at 751–752; aggregated in the `P_RUN` state at 790–824.

**What it does:** (a) watchdog fires after 20 000 cycles with no instruction retired → P_ERROR; (b) stall_timer fires after 10 000 cycles of continuous EX stall → P_ERROR; (c) any opcode > 4'h3 → P_ERROR. Each raises `error_pc` and `error_state` for diagnosis.

**Why this matters:** combined with §3.4, this means every failure mode of the fabric is *detected and localized* rather than silently corrupting results. The complete list of bad outcomes is: (i) correct result, (ii) P_ERROR with diagnostic context, (iii) watchdog timeout. There is no silent-corruption outcome under the seven assumptions.

**Paper treatment recommended:** promote to a named property: **Property 2 (Fail-stop fabric).** Under any violation of A1–A7, the fabric terminates in `P_ERROR` with diagnostic context or in watchdog timeout, never with a silently-wrong root result. This is a *strictly stronger* claim than Claim 1 alone — it is saying that the fabric is safe-by-construction even outside the assumption envelope.

### 3.6 DMEM write-arbitration priority PIU > GCI > FSM

**Location:** [btree_fsm_fast.sv:358–376](btree_fsm_v7_rtl/rtl/btree_fsm_fast.sv#L358-L376).

**What it does:** three-way static priority arbitration. PIU always wins (remote packets always ingest). GCI retries via `gci_write_held` (§3.3). FSM COMPUTE stalls via `ex_dmem_collision`.

**Why this matters for determinism:** PIU cannot starve GCI (retry latch). GCI cannot starve FSM indefinitely (GCI is one-shot per GENERATE). FSM can be stalled but under bounded latency (GCI completes in `gci_latency` cycles, PIU in 1 cycle per packet). All three write agents eventually commit; the order is determined by the scoreboard-readiness of the dependent COMPUTEs, which is itself a pure function of the schedule. **Arbitration is not determinism-relevant at the bit level** (single-writer means there's no contention on the same address) but is **latency-relevant** for the cycle count.

### 3.7 Credit-pulse counter serialization — an old bug now fixed

**Location:** [noc_router.sv:175–205](btree_fsm_v7_rtl/rtl/noc_router.sv#L175-L205).

**What it does:** at each output port, count `new_reads = Σ_v ibuf_ren[p][v]` (can be up to NUM_VCS in one cycle). Maintain `credit_pending[p]` counter. Emit one `credit_pulse[p]` per cycle until drained.

**Why this matters for determinism:** the original implementation emitted a single-bit pulse per cycle — if two VCs read in the same cycle, one credit was lost, and over long runs the link would eventually deadlock as the remote side exhausted its buffer. The counter-serialized version is provably conservative: `Σ pulses = Σ reads` across the run. This is an A7 (lossless credit flow) invariant that was *not held* pre-fix and is *held* post-fix. Paper should mention this as a named invariant.

### 3.8 Round-robin arbitration advances only on successful grant

**Location:** [noc_router.sv:239–248](btree_fsm_v7_rtl/rtl/noc_router.sv#L239-L248).

**What it does:** `rr_ptr[i] <= (rr_ptr[i] + 1) % NUM_CANDIDATES` iff `obuf_wen[i]` this cycle.

**Why this matters:** without the "only on grant" guard, RR advance on empty cycles would cause unfairness. With the guard, the arbiter is *starvation-free*: every contending (port, vc) pair gets served within NUM_CANDIDATES cycles of becoming ready. This is a liveness property of the NoC.

### 3.9 VC steering from packet bit 64 — a header-only (value-independent) choice

**Location:** [noc_router.sv:111–117](btree_fsm_v7_rtl/rtl/noc_router.sv#L111-L117) — documented in paper_v5 §4.3, but worth restating as a *determinism* property (not just a design choice).

**Invariant:** VC selection is a pure function of packet bit 64 (header), not of any payload bit. Therefore contention at the ingress FIFOs is a function of the schedule, not the values. This is the hidden determinism-relevant reason the same-fabric cycle-count is value-agnostic.

### 3.10 FP64 adder is stateless and pipelineless

**Location:** [fp64_add.sv](btree_fsm_v7_rtl/rtl/fp64_add.sv) — entire module, 242 lines, single `always_comb`.

**Why this matters:** `grep always_ff fp64_add.sv` returns zero matches. There is no internal register, no latched flag, no rounding-mode MMR, no exception-status register. The adder is a pure function of its 64-bit inputs. This is the strongest possible form of "deterministic FADD": not just "sampled determinism" but *combinational purity*. The paper hedges "combinational" and "sampled" together; the truth is cleaner — FADD has no state at all.

---

## 4. Minimal Conditions for Determinism (Synthesized)

Across §2 and §3, here is the minimal set of invariants that must *all* hold to guarantee `R_observed = R_canonical(N, L)`:

**Compiler-side (obligations):**
- **C-α**: α is a pure function of (tree, topo, G) — no hidden randomness.
- **C-conn**: α induces a connected subtree partition on every PE (S2.5).
- **C-sw**: each non-identity DMEM address is written at most once per PE per run (DMEM allocator).
- **C-bind**: for every internal *v*, the COMPUTE for *v* binds `(addr_a, addr_b) = (dmem(left(v)), dmem(right(v)))` (build_schedule).
- **C-leaf**: for every leaf *k*, the GENERATE writes `L[idx(k)]` where `idx` is the canonical tree-leaf enumeration (emit_sv_testbench / codegen).
- **C-route**: routing tables encode loop-free, dest-correct paths for the declared topology family.

**Fabric-side (properties, derivable):**
- **F-id**: `DMEM[0]` is the identity element of the selected `alu_op`; `scoreboard[0]` = 1 at reset and uncleared.
- **F-sb-mono**: `scoreboard[a]` transitions 0→1 at most once per run at the cycle of the (unique) write to address *a*.
- **F-sb-gate**: COMPUTE blocks DE→EX until both `scoreboard[addr_a]` and `scoreboard[addr_b]` are 1.
- **F-fw**: DMEM read at EX cycle *t* returns the value committed by the unique write to that address at cycle ≤ *t*, even across the adjacent-cycle race (2-level forwarding).
- **F-fadd**: `fp64_add` is combinational and stateless.
- **F-credit**: credit-return conservation: `Σ credits_returned = Σ buffer_reads` per port over the run.
- **F-misroute**: packets with wrong `dest_gpu_id` are dropped, not silently consumed.
- **F-arb**: DMEM write arbitration (PIU > GCI > FSM) and egress RR are fair; GCI has retry latch against PIU collisions.
- **F-watchdog**: any stall > WATCHDOG_MAX cycles raises `P_ERROR`.

**Under {C-α, C-conn, C-sw, C-bind, C-leaf, C-route} and {F-id, F-sb-mono, F-sb-gate, F-fw, F-fadd, F-credit, F-misroute, F-arb, F-watchdog}**, we have:

> *R_observed = evaluate(FBT(N), L, fadd_rtl) = R_canonical(N, L)*

independently of (G, topology, α, μ, *r*, schedule timing).

---

## 5. When Determinism is Impossible / Broken

| Violated invariant | Observable consequence |
|---|---|
| C-α (non-seeded stochastic) | Same input → different IMEMs across runs; bit result can vary across compilations |
| **C-conn** (disconnected partition without S2.5) | **Compiler binds non-sibling nodes to COMPUTE; wrong bit result silently produced** |
| C-sw (duplicate DMEM writes) | Second write silently overwrites; result depends on schedule ordering |
| C-bind (left/right swapped) | With commutative op: no effect. With non-commutative op (SUB, concat): wrong result |
| C-leaf (misindexed leaves) | Deterministic but wrong function evaluated |
| C-route (malformed table) | *Fail-stop*: watchdog timeout, not silent corruption (F-misroute converts to fail-stop) |
| F-sb-gate disabled | Glitchy reads; wrong result with probability dependent on cycle-race |
| F-fw disabled | Back-to-back COMPUTEs read stale operand; wrong result |
| F-fadd non-pure (e.g., latched rounding mode) | Depends on mode-register history; non-deterministic across programs |
| F-credit leak | Eventually: link deadlock, watchdog timeout |

**Summary:** the only determinism-breaking invariants that produce *silent* wrong results are **C-conn, C-sw, C-bind, C-leaf, F-sb-gate, F-fw, F-fadd**. Violations of C-route, F-credit reach fail-stop. The rest are compile-time issues caught by runtime asserts.

---

## 6. Mapping and Topology Orthogonality — The Actual Theorem

The paper states this as a corollary but doesn't prove it. The code makes the proof one line:

**Theorem (Mapping/topology orthogonality).** Fix tree FBT(N), leaves L, assignment α, refinement r, and the fabric's FADD unit. For any two valid mappings μ₁, μ₂ and any two valid routing tables T₁, T₂ for (possibly different) topologies, the observed root result is identical.

**Proof.** By inspection of `build_schedule` and `generate_instructions`: the emitted `COMPUTE` instructions' `(addr_a, addr_b, dest)` triples depend on α and the DMEM allocator's output, neither of which reads μ or the routing tables. `SEND` instructions' `(dest_gpu, target_addr, link)` triples depend on μ (through `mapping.get(gpu, gpu)`) and the routing tables — but these only affect *where* data flows, not the `(addr_a, addr_b)` operand bindings at the receiving PE's COMPUTEs. Under F-sb-gate, the receiving PE's COMPUTE reads the DMEM values by address, not by arrival time or arrival VC. Therefore R is independent of (μ, routing table). ∎

This is the cleanest mini-theorem the paper could include and currently does not state.

---

## 7. What the Tournament Actually Reveals (Hidden Insights)

The paper reports family-level winner distribution as a table. The richer insight is:

### 7.1 Algorithm families that never win at scale

- **`ExactBB` (branch-and-bound)**: theoretical optimum on small instances but `_check_deadline` times it out at N > 64. In practice ExactBB almost never reaches Phase 3. **This tells us: the space is practically infeasible for exact methods beyond tiny inputs.**
- **`refine_none` (identity refinement)**: sometimes wins (⟨19%⟩) — meaning the best assignment from S2+S3 often cannot be improved by any S4 method within timeout. **This tells us: for those instances, S2+S3 was already near-optimal.**

### 7.2 Algorithm families that win at specific scales

- **Tree-DP (`Lukes`, `Frederik`)**: win at small G (≤16) because tree-DP is polynomial in G and exact-optimal for small G. **This tells us: at small G, the problem is solvable exactly and heuristics lose.**
- **Graph partitioning (`MLfm`, `RecBisect`, `DKway`)**: win at balanced topologies (mesh/torus/fat-tree) because these algorithms naturally produce partitions respecting the topology's bisection structure.
- **List scheduling (`HEFT`, `CPOP`)**: win on tall narrow trees where critical path dominates and list-scheduling minimizes CP.

### 7.3 What the S3 mapping winners imply

- **`Identity` (⟨28%⟩) wins most often** — meaning the S2 assignment's GPU indexing already matches the physical topology well. Non-trivial mapping (TreeMatch, QAP-SA) wins only when S2 produced a "good partition with bad index labeling."
- **`HopMin` (greedy) beats `QAP-SA` (stochastic)** at large scale — meaning the QAP landscape flattens at G > 64, and greedy is Pareto-dominant.

### 7.4 S4 refinement's diminishing returns

- **FM and MCFM dominate (⟨40%⟩ combined)** — classical Kernighan-Lin-style refinement is still the best in the tree-partitioning setting.
- **ALNS wins only when makespan > 1.15× critical-path lower bound** — (see `refine_phased:4866`) the gate is intentional: ALNS is expensive, apply only when far from optimal.

### 7.5 The hidden meta-result

The tournament empirically validates the ABI orthogonality claim: **every passing xsim run produces the same bit result, regardless of which of 22K compiler triples produced the IMEM**. This is the strongest empirical evidence of Claim 1 — and the paper underreports it.

---

## 8. Cost of Determinism — Why It's Structural (Not Empirical)

The paper reports ⟨1.12⟩× same-fabric overhead but doesn't explain *why* this specific number is the number. The code reveals the structure:

### 8.1 Binary-tree critical path is log₂N

The ABI mandates FBT(N). Any non-deterministic schedule on a fabric with arbitrary-arity reducers could use a *k*-ary tree with depth log_k N. At k = G (full fan-in), depth would be log_G N rather than log_2 N, and for G large the difference is significant.

### 8.2 Operand binding forbids reassociation

The ABI mandates (left, right) at every internal. A non-deterministic schedule could reassociate to group locality-adjacent operands, saving communication. The SPRS schedule cannot.

### 8.3 GCI serialization is asymptotically bounded

`gci_gap = gci_latency + 2 = 6` cycles between consecutive GENERATEs on the same PE. At *N*/*G* > gci_gap, leaf-generation is not the bottleneck; at *N*/*G* ≤ 6, it is. **Expected inflection at N/G ≈ 6-8.**

### 8.4 Root-gather critical path

Per `lb_gather` in compute_lower_bound (sprs_core.py:1173–1201): the root PE's critical path includes `⌈log₂ K⌉` merge stages and one `comm_cost(⌈diameter/2⌉)` communication. This is irreducible — no matter the schedule, K PEs must contribute to the root and log₂ K merges are the minimum.

### 8.5 Bisection traffic is tree-order-fixed

`lb_bisection` bound at sprs_core.py:1203–1225: `⌈(K-1)/2⌉` cross-bisection messages, each taking 1 cycle per link per direction, over `bisection_bw` links. For SPRS this is tight — every cross-bisection merge goes through the tree.

**Putting it together:** the ⟨1.12⟩× figure = (FBT tree depth overhead) × (no-reassociation penalty) × (GCI serialization at small N/G) / (hardware utilization). Each component is bounded, each is structural. The overhead *cannot* go below a certain asymptotic floor determined by log₂N / log_G N and the bisection structure.

---

## 9. Algorithm Coverage — Taxonomy and Honest Gaps

The paper lists 18 S2 + 10 S3 + 12 S4 = 40 base algorithms (122 S4 pairs). Let me map the actual coverage.

### 9.1 S2 taxonomy

| Family | Members | Coverage |
|---|---|---|
| **List scheduling** | HEFT (2a), CPOP (2i), CPFD (2m) | Comprehensive |
| **Graph partitioning** | RecBisect (2b), MLfm (2c), DKway (2d) | Multilevel + direct |
| **DAG scheduling** | DSC (2g), Chret (2h), DFSseed (2f) | Dominant-sequence + heuristic |
| **Tree dynamic programming** | Lukes (2k), Frederickson (2l) | Exact-optimal for trees |
| **Geometric / spectral** | Centroid (2j), SFC-via-S3 | Partial (SFC is in S3) |
| **Hierarchical** | ClHEFT (2n), ParSub (2o), SubPack (2q) | Good coverage |
| **Structural** | Spine (2p), LvlHLF (2r) | Decent |
| **Exact / branch-and-bound** | ExactBB (2e) | One method, rarely completes |

**Honest gaps:**
- No ILP / MILP formulation (would be a natural baseline for small N).
- No genetic / evolutionary algorithms (ALNS in S4 is the closest analog).
- No reinforcement learning / learned scheduling (TACCL-style).
- No hyper-graph partitioning (PaToH, KaHyPar — arguably subsumed by MLfm).
- No clustering-then-assign two-stage (k-means + HEFT).

### 9.2 S3 taxonomy

| Family | Members |
|---|---|
| **Trivial** | Identity (3a) |
| **Greedy** | HopMin (3b), RAGreedy (3i) |
| **Graph embedding** | TreeMatch (3c) |
| **Optimization** | QAP-SA (3d), MCF (3e), Tabu (3j) |
| **Spatial / spectral** | SFC (3g), Spectral (3h), DRB (3f) |

**Honest gaps:** no Hungarian-assignment baseline; no learned placement.

### 9.3 S4 taxonomy

12 methods covering FM-family (FM, MCFM), local search (ALNS, Tabu), migration (LeafMig, SubMig, CentReb), TE-style (NetW, TERe), multigrid (VCycles), and flow (FlowMC). Broad coverage. Chainable to 122 pairs.

### 9.4 What's excluded deliberately

- Algorithms requiring inter-PE operations beyond the ABI (e.g., in-network reduction, tree-reshape-on-the-fly).
- Algorithms that relax A5 operand-binding (any commutativity-exploiting refinement).
- Algorithms requiring dynamic scheduling (all SPRS compilation is static).

---

## 10. Recommendations for Paper Integration

Not everything above belongs in the paper — many items are supporting-artifact-level. Here is a prioritized integration plan, roughly in order of importance:

### Must be added to paper_v6

1. **Promote S2.5 connectivity repair to a named invariant (C-conn)** — §3.3 assumption list. This is the single most load-bearing piece of compiler work the paper currently underreports.
2. **Add Leaf-binding assumption (C-leaf / A8)** — Claim 1's leaf-value dependence must be justified.
3. **Reclass A6 outcomes: promote the fail-stop argument** — misroute → watchdog → P_ERROR, not silent corruption. This strengthens the theorem from "invariance under A1–A7" to "fail-stop under ¬A1–A7."
4. **Property 2 (Fail-stop fabric)** — new named property pairing with Claim 1.
5. **Mapping/topology orthogonality as an explicit mini-theorem (§6 above)** — one-paragraph proof.

### Should be added to paper_v6

6. **SU-ordered single-writer as a *constructed* invariant** not just an assumed one — §2.2 above.
7. **Scoreboard as universal presence bit across 4 write agents** — reframes the scoreboard's role in §4.
8. **Two-level DMEM forwarding as a first-class determinism mechanism** — not just a pipeline-compression trick.
9. **GCI write-hold latch** — named safeguard against PIU/GCI collision.
10. **Credit counter serialization** — named invariant (F-credit).

### Nice to have in paper_v6

11. **Compile-time determinism property** — seed-fix + dict-iteration-order → identical IMEM across runs.
12. **Rollback-protected refinement** — monotonic-in-makespan property of refine_phased.
13. **Testbench-hash dedup as statistical-efficiency mechanism** in methodology.
14. **Expand tournament insights** per §7 above — which family wins where and why.
15. **Structural cost-of-determinism decomposition** per §8 — attributes overhead to specific ABI constraints.
16. **Honest S2/S3/S4 taxonomy with excluded-methods disclosure** per §9.

### Do not add (acknowledged but out of scope)

- S5 → S2.5 re-run latent ordering bug — worth mentioning as limitation item, not a feature.
- C extension / precomputed context — reproducibility-appendix material.
- ExactBB rarely completing — tournament-characterization-appendix material.

---

## 11. Suggested Paper Structural Change

Current paper structure has Claim 1 with A1–A7 and four Arguments. Proposed structure for v6:

**§3 rewritten:**
- §3.1 FBT, post-order, leaf enumeration.
- §3.2 The ABI (operand binding + leaf binding).
- §3.3 Assumptions split into:
  - *C-obligations (compiler)*: C-α, C-conn, C-sw, C-bind, C-leaf, C-route (6 items)
  - *F-properties (fabric)*: F-id, F-sb-mono, F-sb-gate, F-fw, F-fadd, F-credit, F-misroute, F-arb, F-watchdog (9 items)
- §3.4 **Claim 1** (cross-topology invariance) + **Property 2** (fail-stop).
- §3.5 Supporting arguments.
- §3.6 The mapping/topology orthogonality corollary.
- §3.7 FADD policy (FTZ+RNE specifics).
- §3.8 Edge cases.
- §3.9 Mechanization path.

**§4 rewritten to emphasize safeguards:**
- Existing sections plus:
  - §4.X *Fail-stop discipline* (misroute + watchdog + invalid-opcode).
  - §4.Y *Write-arbitration and retry latches* (GCI write-held, PIU priority).
- The story becomes "the fabric is safe-by-construction, not just correct-under-assumptions."

**§5 rewritten to emphasize construction of C-obligations:**
- §5.1 Compile pipeline.
- §5.2 **Connectivity repair and why it is load-bearing** (new subsection promoted from a line).
- §5.3 DMEM allocation as single-writer constructor.
- §5.4 Code generation preserves (addr_a, addr_b) = (left, right) by direct inspection.
- §5.5–5.7 S2, S3, S4 catalogs (move to Appendix B, keep one-paragraph summaries).

**§7 evaluation:**
- §7.6 (tournament characterization) expanded with the insights from §7 above.
- New §7.8 *Cost-of-determinism decomposition* attributing the ⟨1.12⟩× number to specific components.

This structure treats determinism as an *engineered invariant with named safeguards*, not as a theorem plus a pile of empirical results. It is the story the code is actually telling.
