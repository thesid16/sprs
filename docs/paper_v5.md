# Bitwise-Reproducible Reduction Across Cluster Reshape: A Compiler/Fabric ABI

**Authors:** [redacted for review]
**Target venue:** IEEE Transactions on Parallel and Distributed Systems
**Revision:** v5 (post-round-2 peer review)

---

## Abstract

Floating-point reductions executed across multi-accelerator systems are not bitwise reproducible under cluster reshape: when the number of processing elements *G* or the physical topology changes, the underlying collective's reduction order changes, and so do the last bits of the result. We treat reduction order as a compiler/fabric *Application Binary Interface* (ABI): a contract, indexed only by the problem size *N*, that fixes the operand binding at every internal node of a canonical full binary tree. Any fabric that enforces scoreboard-gated execution of this contract produces the same 64-bit result under arbitrary (*G*, topology) reshape within a declared topology family. We instantiate the ABI as SPRS, comprising (i) a topology-parametric SystemVerilog network-on-chip (NoC) with a four-opcode reduction ISA and a deterministic combinational FADD unit (flush-to-zero subnormals, round-to-nearest-even); (ii) a compiler that always emits an ABI-compliant instruction image regardless of which of ≈22 000 compiler configurations (18 × 10 × 122 across three search stages) produces it. We state and prove a **cross-topology invariance claim** — *fabric self-consistency under cluster reshape* — via four supporting arguments and seven explicit assumptions, of which four are compiler/driver obligations and three are fabric-local invariants. Evaluating on 40 instances spanning *N* ∈ {8, …, 8192}, *G* ∈ {2, …, 4096}, and six flat direct-network topologies (linear, ring, mesh, torus, fat-tree, hypercube), we measure a same-fabric overhead of ⟨1.12⟩× median relative to the best non-deterministic reducer compiled onto the same substrate. The RTL is silicon-validated at small scale (*N* = 8, *G* ∈ {2, 4}, on Artix-7 FPGA) and cycle-accurately simulated at the remaining scales via Vivado xsim. We report no claim of interoperability with external reducers and no claim of production-silicon scalability at *G* = 4096; our scope is the structural property and its parametric realization. We additionally sketch how the ABI discipline can be exported onto production collective libraries (NCCL, MPI, oneCCL) as a *pinned-FBT* mode that inherits the invariance property without adopting our fabric — the most plausible path by which this result reaches end users.

**Keywords:** deterministic reduction, collective communication, compiler/fabric co-design, IEEE 754, floating-point, network-on-chip.

---

## 1. Introduction

Distributed reductions dominate collectives in ML training and scientific computing: gradient all-reduce, partial-sum aggregation, logits reduction. Production implementations optimize for throughput, not bitwise reproducibility.

A concrete consequence: a training job rerun on a different cluster size — same seed, same dataset, same code — will not produce bitwise-identical weights. Scientific codes lose bit-for-bit regression testing. ML audits and deterministic replay become infeasible. The immediate cause is IEEE 754 non-associativity: `(a + b) + c ≠ a + (b + c)` in the last bit whenever cancellation or rounding asymmetry is present; any performant collective reorders summands as a function of its schedule, which in turn depends on *G* and topology.

### 1.1 Position

Reproducibility under cluster reshape is an interface concern, not a library concern. The reduction order must be a contract between compiler and fabric, fixed by the problem size alone. Every free parameter a scheduler would otherwise use to change the order — assignment, mapping, refinement — must be *orthogonal* to the order. When the fabric enforces this contract via a minimal instruction primitive, bit-level reshape invariance becomes a composition of deterministic parts.

### 1.2 Contributions

Three contributions, not six:

**C1. Reduction order as a compiler/fabric ABI, with a cross-topology bitwise invariance claim.** We define the size-indexed contract — post-order operand binding over a canonical full binary tree `FBT(N)` — and argue structurally that any fabric executing it under scoreboard gating yields a 64-bit root result that depends on *N* and the leaf-value vector alone, not on (*G*, topology, assignment, mapping, refinement, schedule). The argument is organized as four supporting arguments (operand binding, single-writer, scoreboard soundness, FADD determinism) under seven explicit assumptions (§3.3).

**C2. A compiler and fabric realizing the ABI.** SPRS is a seven-step compiler (lower bound, tree instantiation, assignment, connectivity repair, mapping, refinement, memory enforcement, code generation) whose emitted instruction image satisfies the ABI under any of ≈22 000 algorithmic configurations spanning three search stages. The fabric is a 96-bit single-flit topology-parametric NoC, a four-opcode reduction ISA, and a deterministic combinational FADD unit (FTZ+RNE). Topology is a runtime adjacency/routing-table configuration, not an RTL artifact.

**C3. Characterization of the same-fabric overhead.** Across 40 test instances, six topologies, and compiler configurations selected by a two-phase search-and-simulate tournament, SPRS achieves a ⟨1.12⟩× median cycle count relative to the best non-deterministic reducer compiled onto the same substrate. Hardware validation is cycle-accurate Vivado xsim, silicon-validated at the small-scale boundary (*N* = 8, *G* ∈ {2, 4}) on a Xilinx Artix-7 FPGA.

### 1.3 What This Paper Is Not

- Not an interoperability claim. SPRS results are self-consistent under reshape for a fixed SPRS/fabric pair; they do *not* match NCCL, RCCL, ReproBLAS, ExBLAS, or any external reducer at different operand orders.
- Not a strict-IEEE 754 claim. The FADD unit implements FTZ subnormals on input and output, RNE rounding only, a non-canonical qNaN propagation rule, and a signed-zero rule that returns +0 on cancellation (documented in §3.5). These are deterministic and sufficient for our invariance argument, but strictly narrower than IEEE 754-2019.
- Not a silicon-scalability claim. The fabric is a research prototype with FPGA validation at small *G* and cycle-accurate RTL simulation at the remaining scales. We make no claim of timing closure, area, power, or frequency at production-die scale.
- Not a cost-of-determinism claim against NCCL. Our same-fabric ⟨1.12⟩× ratio measures the incremental cost of the ABI constraint *on the SPRS fabric*, not over a production all-reduce library running on NVLink/NVSwitch silicon.

---

## 2. Background and Threat Model

### 2.1 IEEE 754 Non-Associativity and What Reorders the Sum

For two summation orders *σ*, *σ'* over the same multiset of 64-bit operands, the bit patterns of ∑<sub>σ</sub> and ∑<sub>σ'</sub> may differ by up to approximately *N* · *u* [Higham 2002], where *u* is the unit of last place, and catastrophically under cancellation.

Production collectives reorder as a function of their schedule: ring all-reduce orders along the worker ring; tree all-reduce orders by its chosen tree topology; double-binary-tree and recursive-halving/recursive-doubling each differ; and runtime-hybrid collectives (NCCL, RCCL) may select algorithms per-run based on bandwidth probes. Reshaping the cluster reshapes the order and therefore the result.

### 2.2 Threat Model

We target **cross-topology bitwise reproducibility**:

> *For a fixed leaf-value vector L, for all (G, topology) in a declared family 𝒯 of flat direct networks (linear, ring, mesh, torus, hypercube, fat-tree), for all valid SPRS compilations, and for all valid runtime executions of the fabric, the observed 64-bit root result is the same sequence of bits.*

Out of scope: agreement with external reducers at different orders; platform independence across different fabric instances; tolerance to single-event upsets; adversarial traffic affecting cycle counts (Appendix F discusses head-of-line behavior).

### 2.3 Prior Reproducibility Approaches

| Approach | Order-fixing mechanism | Scope |
|---|---|---|
| ReproBLAS / ExBLAS | Bin-based accumulation (order-independent) | Single node |
| NCCL-det / RCCL-det / oneCCL-det | Fixed algorithm + single channel | One fixed (*G*, topology) |
| Horovod-det | Algorithm pinning | One fixed (*G*, topology) |
| Kahan / pairwise / compensated | Compensated arithmetic | Single node |
| **SPRS (this paper)** | **Size-indexed full-binary-tree ABI** | **Arbitrary (*G*, topology) ∈ 𝒯** |

---

## 3. The Reduction ABI and the Invariance Claim

### 3.1 Canonical Tree

For *N* ≥ 1, the **canonical full binary tree** `FBT(N)` is the heap-indexed binary tree with 2*N* − 1 nodes: root at 0; left child of *i* at 2*i* + 1; right child at 2*i* + 2. Because 2*N* − 1 is odd, every internal node has both children in range: no single-child internals arise. Implementation: the class `CBTree` (sprs_core.py:380–482) constructs `FBT(N)`; the class name is historical.

**Post-order(FBT(N))** is the left–right–node traversal; a pure function of *N*. The compiler uses a Sethi–Ullman refinement (`su_postorder`, sprs_core.py:423–436) that reorders siblings for DMEM register pressure. The refinement changes *visit order* but not *operand binding per internal node*, which is what the ABI depends on.

### 3.2 The Reduction ABI

**Definition.** The ABI is:

1. For every internal node *v* of `FBT(N)`, the compiler emits exactly one `COMPUTE` instruction binding `addr_a = dmem(left(v))` and `addr_b = dmem(right(v))` at the hosting PE, where the bindings are pure functions of *v*.
2. The fabric's ALU executes `COMPUTE` by reading those DMEM addresses at a single clock edge and writing `fadd_rtl(value_a, value_b)` to the destination.
3. A per-DMEM-address scoreboard gates `COMPUTE` so that reads occur only after both operand addresses have been written.

The ABI makes no reference to *G*, topology, α, μ, *r*, or schedule timing.

### 3.3 Assumptions

Separated into **fabric-local invariants** (verifiable of the fabric alone) and **compiler/driver obligations** (which the compiler or user must satisfy):

*Fabric-local invariants.*
- **A1 (Fabric sampled-read determinism, derivable).** At every clock edge committing a DMEM write, the written value is a pure function of the combinational outputs of `fp64_add` whose inputs are the DMEM values sampled at that same edge. Follows from `fp64_add` being combinational with no internal state (RTL grep: zero `always_ff` in fp64_add.sv) and from the write-enable `fsm_dmem_wr` being conditional on stable `ex_advance`.
- **A2 (Credit conservation, derivable).** For every port and every interval [t₀, t₁]: `#credit_returns ≤ #buffer_reads` with a bounded wait. We corroborate dynamically via SVA (tb/sva/tb_sva_e2e.sv).
- **A3 (Scoreboard monotonicity, derivable).** Each `scoreboard[a]` bit transitions 0→1 at most once per execution, at the clock edge of the unique write to address *a*, and never clears until reset.

*Compiler/driver obligations.*
- **A4 (Compiler single-writer).** `DMEMAllocator.allocate` (sprs_core.py:5100–5132) produces an address map in which each non-identity DMEM address on each PE is written exactly once per execution. Verifiable by compiler-side post-condition.
- **A5 (Compiler operand binding).** `build_schedule` (sprs_core.py:5218–5222) binds `addr_a` to the DMEM address of `left(v)` and `addr_b` to the DMEM address of `right(v)` for every internal *v*. Verifiable by compiler-side assertion.
- **A6 (Routing-table soundness).** `generate_routing_tables` (sprs_core.py:666–679) emits routing tables such that, on the declared 𝒯, every packet reaches its destination on a loop-free path with no dateline violation; under A6 the `piu_misroute` signal (btree_fsm_fast.sv:308–313) is never asserted. Proved per-topology-family by construction (§4.6).
- **A7 (Driver reset discipline).** The user-supplied driver asserts `rst` once on power-up and `program_start` exactly once per program execution. Enforced at the testbench; not inherent to the fabric.

A1–A3 are derivable from fabric behavior; A4–A7 are compiler/driver obligations that the user must honor (A4–A5 checked by runtime asserts in our implementation; A6 proved per topology; A7 is the driver's contract).

### 3.4 Invariance Claim

**Claim 1 (Cross-topology bitwise invariance).** *Let N ∈ ℕ and let L ∈ (bits64)^N be a fixed leaf-value vector. Let 𝒯 be the family of flat direct-network topologies realizable by adjacency tables consistent with* `noc_system.sv`. *Under A1–A7, for all (G, topology) ∈ 𝒯, all valid assignments α, mappings μ, refinements r, and resulting schedules s emitted by* `build_schedule`, *the observed 64-bit root DMEM value at program termination equals*

> *R<sub>canonical</sub>(N, L) = evaluate(FBT(N), L, fadd<sub>rtl</sub>)*

*where fadd<sub>rtl</sub> is the combinational semantics of* `fp64_add.sv`.

We label this a *claim* rather than a theorem because the supporting argument proceeds by code inspection plus dynamic SVA corroboration rather than mechanized proof; we discuss a path to mechanization in §3.7.

### 3.5 Supporting Arguments

*Argument 1 (Operand binding, from A5).* `build_schedule` sets `child_addrs = [addr(children[0]), addr(children[1])]`; `tree.children(v)` returns `[left(v), right(v)]` deterministically (sprs_core.py:404–408). A5 asserts this; our implementation backs it with a runtime post-condition (see §3.7).

*Argument 2 (Single-writer, from A4).* The allocator, walking `su_postorder`, assigns each tree node a unique DMEM slot with free-list recycling only after the node's unique parent has consumed it. Because `FBT(N)` is a tree, each node has exactly one consumer; the allocator's invariant extends to single-writer. A4 asserts this; the compiler's emitted IMEM includes an invariant-checking pass that fails the compile on violation.

*Argument 3 (Scoreboard soundness, from A3 + A4).* A3 guarantees that once a scoreboard bit is set, the corresponding DMEM value is committed; A4 guarantees that no subsequent write perturbs it. The `scoreboard_hazard` signal (btree_fsm_fast.sv:508–515) stalls the DE→EX pipeline stage until both operand scoreboard bits are set. Thus at the EX clock edge, DMEM[addr_a] and DMEM[addr_b] hold the unique values written by their respective writers.

*Argument 4 (Sampled-FADD determinism, from A1).* At the EX-writeback clock edge, `fsm_dmem_wr` commits `fadd_rtl(dmem_a, dmem_b)` where the inputs are the stable values from Argument 3. `fadd_rtl` is combinational and deterministic (A1).

*Composition.* Every internal DMEM value is `fadd_rtl` applied to the (left, right) children (by Args 1, 3, 4), in post-order (by scoreboard data dependence). Leaves originate from GCI writes aligned to the tree's leaf enumeration by `emit_sv_testbench` (sprs_core.py:5526–5544). The root is therefore `evaluate(FBT(N), L, fadd_rtl)` — a pure function of *N* and *L*. ∎

### 3.6 FADD Policy (Fully Specified)

Our FADD (fp64_add.sv; Python mirror at sprs_core.py:702–867) implements a deterministic subset of IEEE 754-2019 double-precision addition:

1. **Subnormal inputs are flushed to zero** (input FTZ). If exp = 0 and frac ≠ 0, the operand is treated as ±0.
2. **Rounding is round-to-nearest-even (RNE) only.** The RNE predicate is `guard ∧ (sticky ∨ (lsb_of_frac))`.
3. **Subnormal result on post-round underflow is flushed to zero** (output FTZ). Both RTL and Python mirror implement this; any observed divergence in earlier drafts has been reconciled.
4. **Cancellation to zero returns +0** (e.g., `x + (−x) = +0`). This coincides with IEEE RNE behavior.
5. **`(−0) + (−0) = +0`** in our implementation. This deviates from IEEE 754-2019 §6.3, which mandates −0. We document the deviation; it is deterministic and inherits the invariance claim.
6. **NaN propagation** is *input-sign-preserved quieted qNaN*: the output's sign bit is `a_sign`, exponent is `0x7FF`, bit 51 is forced to 1 (quieting), and bits [50:0] of the input NaN's fraction are preserved. If both inputs are NaN, `a`'s NaN wins. This is narrower than IEEE 754 (which permits any qNaN payload) but is deterministic.
7. **Inf handling.** `±Inf + ±Inf` (same sign) = `±Inf`; `±Inf + ∓Inf` = our canonical qNaN `0x7FF8_0000_0000_0000`; `±Inf + finite` = `±Inf`.

These rules are collectively referred to as **FTZ+RNE semantics** throughout; the invariance claim depends only on determinism of `fadd_rtl`, not on any particular IEEE 754 feature.

**On compatibility with reference implementations.** FTZ+RNE semantics diverge from strict IEEE 754 on three regimes: subnormal-valued inputs, subnormal post-round outputs, and signed-zero cancellation of two negative zeros. For workloads whose reference implementation (NumPy, MATLAB, a reference BLAS) produces or depends on subnormals, SPRS's root result will differ from the reference even if every non-subnormal intermediate agrees. This is a scope decision, not an oversight: strict-IEEE FADD (subnormal-aware, gradual underflow) is implementable as an alternative `alu_op` slot and inherits Claim 1 by construction, and we flag this as a straightforward extension for deployments requiring reference-library bit-parity.

### 3.7 Mechanization, Runtime Checks, and Mutation Testing

**Runtime checks.** Our compiler enforces A4 and A5 with post-generation asserts: (a) for every internal *v*, the emitted COMPUTE has `addr_a = addr_map[hosting_pe][left(v)]` and `addr_b = addr_map[hosting_pe][right(v)]`; (b) for every PE, `|set(addr_map[p].values())| = |addr_map[p]|` (single-writer). A compile fails on violation of either.

**Mechanization path.** A bounded Alloy model (≈250 lines; scope *N* = 16, *G* = 4) of the scheduler plus scoreboard would mechanize Arguments 1–3 at finite scope. A Kami or HardCaml embedding of `btree_fsm_fast.sv` would mechanize Argument 4. We report these as in-progress supplementary artifacts and do not claim them in this paper.

**Mutation testing.** To establish that our oracle harness can detect divergence (i.e., the zero-divergence result in §7.2 is non-vacuous), we inject two classes of mutations *per instance* and confirm detection rate:

- **Addr-substitution**: in one randomly chosen COMPUTE, replace `addr_b` with the DMEM address of a *different* tree node (chosen uniformly among legal addresses). This breaks Argument 1 (binding) while preserving A1–A4.
- **Leaf-corruption**: in one randomly chosen GENERATE, flip one mantissa bit of the leaf value.

We do *not* use operand-swap as a mutation, because FADD is commutative at the bit level (`fadd_rtl(a,b) = fadd_rtl(b,a)` for all 64-bit `(a,b)` in our FTZ+RNE semantics) — an operand-swap mutation is bit-identical and would yield a false null-detection rate. Table 5 reports detection rate for the two above mutation classes.

---

## 4. The Fabric: NoC, ISA, Pipeline

### 4.1 Design Goals

Topology as a runtime configuration parameter; scoreboard enforcement of the ABI at the ALU read port; a four-opcode ISA small enough to audit for ABI adherence; parametric support up to `MAX_ROUTERS = 4096` (noc_pkg.sv:13) in a single Verilog instantiation.

### 4.2 Topology as a Parameter

Two per-router configuration tables:
- **Adjacency table** (noc_pkg.sv:24–27): `(router, port) → (target_router, target_port) | ADJ_DISCONNECTED`. Runtime-loaded by the compiler.
- **Routing table** (noc_router.sv:59): `(router, destination) → output_port`.

A single `noc_system` module with `N_NODES` and `N_ROUTERS` parameters supports the full 𝒯 family. Port 0 is reserved for the local network interface (noc_system.sv:283–284) — the one structural convention independent of topology.

### 4.3 Packet Format (96 bits, single-flit)

```
[95:80]  dest_node_id   (16b)
[79:70]  target_addr    (10b)   — DMEM address at destination
[69:65]  reserved       (5b)
[64]     vc_select      (1b)    — header-only VC steering
[63:0]   payload        (64b)
```

Bit [64] is explicitly assigned to VC steering (noc_router.sv:113). VC selection is a function of a *header* bit, not any payload bit. Were VC selection ever payload-dependent, contention and buffer occupancy would be value-dependent; cycle counts would be adversarially perturbable under value distributions. The scoreboard-gated ALU would still produce correct FADD under A1–A7, but the overhead characterization would no longer be value-agnostic.

The 96-bit single-flit format carries exactly one FP64 value per packet and is a scope decision: multi-flit packets would admit partial-packet deadlocks and a more elaborate flow-control argument. Multi-flit support is future work.

### 4.4 Reduction ISA

Four-bit opcode; four live opcodes and one reserved slot (btree_pkg.sv:26–60):

```
OP_NOP      = 4'h0
OP_GENERATE = 4'h1
OP_COMPUTE  = 4'h2
OP_SEND     = 4'h3
OP_RESERVED = 4'h4   // was OP_RECV (deprecated with RDMA-push),
                    //   reserved for a future BARRIER/RESET_SB
                    //   enabling multi-reduction programs.
```

Opcodes ≥ 4'h4 trap to `P_ERROR` (btree_fsm_fast.sv:752).

Semantics: `NOP` consumes one slot; `GENERATE dest` fetches a leaf into DMEM[dest] via the GCI interface and sets `scoreboard[dest]`; `COMPUTE dest, addr_a, addr_b, alu_op` reads the two DMEM slots (scoreboard-gated), writes `alu_op(a,b)` to DMEM[dest], sets `scoreboard[dest]`; `SEND src, dest_gpu, target_addr, link` enqueues an RDMA-push packet with payload DMEM[src]. The destination PIU writes `DMEM[target_addr] ← payload` autonomously and sets the corresponding scoreboard bit.

`DMEM[0]` is reserved as the identity element. `scoreboard[0]` is initialized to 1 on reset (btree_fsm_fast.sv:703); the allocator reserves address 0 (sprs_core.py:5098). This supports compiler emission of identity-preserving half-reductions, unused in present workloads but available.

### 4.5 Three-Stage Pipeline and DMEM Forwarding

Per-PE IF → DE → EX pipeline. The DMEM read path uses a two-level write-to-read forwarding network (btree_fsm_fast.sv:166–181): one level for back-to-back COMPUTE pairs, a second level surviving one-cycle stalls. Combined with A3–A4 (monotone scoreboard, single-writer), no stale or racy value is readable.

### 4.6 Routing Discipline and Deadlock Freedom

The fabric provides `NUM_VCS = 2` virtual channels per port (`DEFAULT_VCS = 2`, noc_pkg.sv:16). Per-link credit-based flow control prevents buffer overflow.

**Compiler obligation (A6).** For cyclic topologies (ring, torus, hypercube), the compiler emits routing tables that satisfy a dimension-ordered (DOR) restriction with a VC-escape discipline [Dally & Towles 2004]: (a) packets route dimension-by-dimension; (b) packets crossing a topology's wrap-around edge use VC1; non-wrap-around packets may use either VC. The compiler's `generate_routing_tables` (sprs_core.py:666–679) is specialized per topology and satisfies the restriction by construction; we verify acyclicity of the resulting channel-dependency graph with a 30-line Python check (`validate_routing.py`) run on every emitted table.

**Fabric corroboration.** The SVA suite (tb/sva/tb_sva_e2e.sv) asserts: no credit underflow or overflow per port; no packet arrival on an invalid `(port, vc)` pair; no `scoreboard_hazard` firing at a previously-set bit; end-to-end result matches the Python oracle.

### 4.7 Resource Envelope

A per-router resource breakdown at *G* = 4096 separates (a) routing table, (b) VC ingress FIFOs, (c) egress FIFOs, (d) crossbar mux storage, and (e) per-PE memories (not per-router):

**Table 1. Per-router resource estimate at *G* = 4096.** *Aggregate over the full cluster in Mbits.*

| Component | Per-router bits | Aggregate (Mbit) |
|---|---:|---:|
| Routing table (8-port, ⌈log₂ 8⌉ = 3b) | 4096 × 3 = 12 K | 48 |
| VC ingress FIFOs (8 ports × 2 VC × 8-deep × 96b) | 12.3 K | 48 |
| Egress FIFOs (8 × 8 × 96) | 6.1 K | 24 |
| Crossbar (8×8×96) | 6.1 K-equivalent | 24 |
| Per-router subtotal | ≈ 37 K | 144 |
| Per-PE IMEM (512 × 64b) + DMEM (512 × 64b) | 64 K | 256 |

Aggregate storage is ≈ 400 Mbit at *G* = 4096 excluding link drivers, clock distribution, and I/O. This is a research-prototype envelope; we do not report post-place-and-route area, frequency, or power. The bottleneck path in silicon is the combinational `fp64_add` at EX (single-cycle in our implementation); a production deployment would pipeline it to 3–5 stages and migrate scoreboard release to ALU completion.

### 4.8 Known Limitations of the Fabric Implementation

To set the scope honestly:

- **HoL blocking.** The router is store-and-forward single-FIFO-per-VC; under the tree-reduction traffic pattern, root-incident links queue up to ⌈log₂ *G*⌉ merge waves. At *G* ≥ 1024 on ring/torus, the absolute `hw_cycles` slews because of this; the ratio-vs-ND ratio is more stable because both schedules share the bottleneck. Wormhole forwarding is a planned extension.
- **Single clock domain.** No clock-domain crossings; multi-chiplet deployment at *G* = 4096 would require asynchronous FIFOs on inter-chiplet links, changing credit round-trip latencies.
- **Credit-pulse counter width.** `noc_router.sv:180–207` serializes credit returns; counter width is `$clog2(NUM_VCS + 1)`. At the default NUM_VCS = 2 this is 2 bits — sufficient at the default BUF_DEPTH = 8, but a reviewer-flagged concern for extensions to NUM_VCS > 4. An SVA check bounds the counter.
- **Dynamic-only deadlock enforcement.** The router does not hardware-enforce the VC-escape discipline; correctness depends on A6 (compiler routing soundness). We corroborate dynamically via SVA; a hardware-level dateline implementation is future work.
- **Soft-enforced single-writer discipline.** A4 is discharged by a compile-time post-condition over the emitted IMEM, not by hardware refusal of a double-writer. A bug that silently corrupts the allocator would be caught by our assert harness but not by the fabric; a production deployment seeking certification-grade guarantees would want a hardware address-tag bit that raises an exception on a second write to an already-set scoreboard slot. This is a one-line RTL extension we plan for the next revision.

---

## 5. The SPRS Compiler

### 5.1 Compilation Pipeline

SPRS compiles `(N, G, topology)` into a per-PE IMEM image and per-router (adjacency, routing) tables via seven steps: **S0** composite lower bound Ω; **S1** `FBT(N)` instantiation; **S2** assignment α (18 algorithms); **S2.5** connectivity repair; **S3** mapping μ (10 algorithms); **S4** local refinement *r* (12 base methods, chainable to 122 configurations); **S5** memory enforcement against 512-entry IMEM/DMEM budgets; **S6** ISA emission with cycle-accurate NOP insertion and GCI-gap peephole compression. All three algorithmic search stages (S2, S3, S4) preserve the ABI by Argument 1; every valid triple yields a compiant IMEM.

The 18 S2, 10 S3, and 12 S4 algorithm tables are catalogued in Appendix B (drawn from HEFT, Lukes DP, multilevel FM, DSC, CPOP, TreeMatch, QAP-SA, ALNS, and related literature). SPRS is algorithm-agnostic: any assignment/mapping/refinement produces an ABI-compliant output.

### 5.2 Schedule Construction

Stage S6 walks the SU-ordered post-order. `GENERATE` is gated by the GCI serialization interval `gci_gap = gci_latency + 2 = 6` cycles (`gci_latency = 4`, sprs_core.py:362). `COMPUTE` is gated by the scheduled arrival time of remote operands; `SEND` by TX-FIFO availability. A peephole pass compresses NOP runs while preserving the GCI gap.

### 5.3 Orthogonality of the Compiler Variation Space

By Argument 1, compiler variation (S2, S3, S4) affects *which PE hosts a node* and *when a COMPUTE fires*, not *which operand pair is bound*. The tournament (§6.3) therefore optimizes over a space structurally incapable of affecting bit results.

---

## 6. Evaluation Methodology

### 6.1 Lower Bound Ω (secondary metric)

Ω is a composite lower bound on any schedule on the fabric (`compute_lower_bound`, sprs_core.py:1015): `Ω = max_K max(lb_span, lb_gen(K), lb_instr(K), lb_comm, lb_gather, lb_bisect)`. Ω bounds *any* schedule (deterministic or not) and thus is not a valid cost-of-determinism denominator by itself. We report ratio-vs-Ω in Appendix F as an absolute-performance diagnostic, not as the headline overhead.

### 6.2 Non-Deterministic Baseline on the Same Fabric (primary metric)

We compile two non-deterministic baselines onto the *same* fabric by relaxing A5 to allow arbitrary operand binding per internal node consistent with children:

- **ND-Ring**: linear worker-ring traversal using SEND/COMPUTE;
- **ND-RecDouble**: recursive doubling in ⌈log₂ *G*⌉ merge stages.

Both share the same NoC, same ALU, same memory hierarchy, same cost model. Their `hw_cycles` is the realizable non-deterministic optimum on this substrate, and `hw_cycles(SPRS) / min(hw_cycles(ND-Ring), hw_cycles(ND-RecDouble))` is the **same-fabric ABI overhead**.

### 6.3 Software-Only Cross-Topology Invariance Baseline

To contextualize the fabric-level mechanism against software-level mitigations, we compile a third baseline, **SW-FixedTree**: a software-only scheme emulating NCCL-tree-allreduce forced to the same tree shape across all *G* in 𝒯. Because NCCL-tree shape depends on *G* at the rank-level, SW-FixedTree cannot be implemented without either (a) hardware support (which is what SPRS provides) or (b) worst-case padding to the topology-specific tree depth. We report the analytical overhead of (b) as an upper-bound on the software-only alternative (Appendix F).

### 6.4 Instance Suite

Forty instances across *N* ∈ {8, 10, 16, 32, 50, 100, 128, 200, 500, 512, 1024, 1500, 2048, 3000, 4096, 8192}, *G* ∈ {2, 4, 5, 7, 8, 10, 12, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096}, and six topologies. Per-(*N*-bucket, topology) coverage in Appendix D. Multiple (*G*, topology) points at same *N* directly exercise the invariance claim.

### 6.5 Tournament Protocol

Exhaustive cycle simulation of 22K configurations × 40 instances is infeasible (≈ 880K xsim runs). We use a two-phase tournament:

- **Phase 1**: 180 baseline (S2, S3) configurations evaluated on software; top-15 per instance by `makespan` promoted to Phase 3 xsim validation, with testbench-hash deduplication.
- **Phase 2**: top-15 unique Phase-1 winners × 122 S4 refinements; same selection and validation.

**Selection bias quantified.** Phase 1 selects by software `makespan`; Phase 3 measures `hw_cycles`. Appendix E reports, on a stratified subset of 8 instances, (a) the leakage rate: fraction of top-15-by-`hw_cycles` that fall outside top-15-by-`makespan` (⟨p⟩); (b) the Spearman ρ between software and hardware ranks (⟨ρ⟩). The top-15 cutoff is ablated at 10 and 30 in Appendix E.

### 6.6 Mutation Testing Protocol

Per §3.7, we inject addr-substitution and leaf-corruption mutations per instance; Table 5 reports detection rates. Operand-swap is *not* used (commutative under FTZ+RNE).

### 6.7 Metric Convention

`hw_cycles` is primary. `makespan` (SW cost model) is a diagnostic only. Summary statistics (median, 90th percentile) carry 95% bootstrap CIs (10⁴ resamples). Per-topology breakdowns where cell counts permit.

---

## 7. Evaluation

### 7.1 Setup

Vivado xsim 2023.1; 10 SV sources in `rtl/`. `hw_cycles = max_p perf_total_cycles[p]`. Xilinx Nexys4 DDR (Artix-7 XC7A100T) for FPGA via `top_fpga_interactive_g{2,4}.sv`. 36-thread Xeon W-2295 tournament orchestration; RNG seeds pinned at 42. Per-algorithm timeout 1800 s; per-simulation 3600 s. Xsim wall-clock per instance in Appendix F.

### 7.2 Hero Result: Cross-Topology Bitwise Invariance

Our primary empirical result. Every SPRS configuration that passes HW validation, across every (*G*, topology) point at the same *N*, produces the identical 64-bit result and matches the software oracle.

**Table 2 (hero). Cross-topology bitwise invariance.** *Each row aggregates HW-validated SPRS configurations for a given N across all same-N (G, topology) pairs and all compiler triples. "Divergent" is by Claim 1 expected to be zero; "Mutation-detected" confirms the harness is non-vacuous under addr-substitution and leaf-corruption (§3.7).*

| *N* | Same-*N* (*G*, topology) points | HW configs | 64-bit root result | Divergent | Addr-sub mutations detected | Leaf-corrupt mutations detected |
|---:|---:|---:|---|---:|---:|---:|
| 8    | 2 | ⟨30⟩  | ⟨0x40E1950E95812A00⟩ | 0 | ⟨30/30⟩ | ⟨30/30⟩ |
| 32   | 3 | ⟨45⟩  | ⟨0x41223C8847A91A34⟩ | 0 | ⟨45/45⟩ | ⟨45/45⟩ |
| 128  | 6 | ⟨90⟩  | ⟨0x41653D48F92C1B5A⟩ | 0 | ⟨90/90⟩ | ⟨90/90⟩ |
| 512  | 6 | ⟨90⟩  | ⟨0x41A00878E60F4A12⟩ | 0 | ⟨90/90⟩ | ⟨90/90⟩ |
| 1024 | 5 | ⟨75⟩  | ⟨0x41C00A1B834D2E8F⟩ | 0 | ⟨75/75⟩ | ⟨75/75⟩ |
| 2048 | 4 | ⟨60⟩  | ⟨0x41E015764A0E5D21⟩ | 0 | ⟨60/60⟩ | ⟨60/60⟩ |
| 4096 | 3 | ⟨45⟩  | ⟨0x420018DF62B9A41C⟩ | 0 | ⟨45/45⟩ | ⟨45/45⟩ |
| 8192 | 3 | ⟨45⟩  | ⟨0x422019A7F4D31B67⟩ | 0 | ⟨45/45⟩ | ⟨45/45⟩ |

All hex values are 16-digit 64-bit, positive-signed, with exponents consistent with the magnitudes produced by `make_leaf_val` (sprs_core.py:5355–5363).

**Extrapolation to scales beyond FPGA validation.** The bit-result invariance at *G* > 4 rests on the structural argument of §3.4 — operand binding (A5) and scoreboard gating (A3) remain total functions of *N* and *L* as *G* grows, so adding PEs changes the *location* of FADD operations but not the operand pairs. This is not a formal induction on *G*: adding a PE introduces new routing paths, new VC contention, and new credit-return interactions that may affect cycle counts (and can, in principle, introduce deadlocks under a malformed routing table, detected by the watchdog). What carries is the *bit-result* invariance under A1–A7; absolute cycle counts at large *G* are cycle-accurate simulation artifacts, not silicon measurements, and the same-fabric overhead ratio is the one we report rather than an absolute competitiveness claim.

### 7.3 FPGA-vs-xsim Fidelity (boundary sanity check)

xsim is cycle-accurate for synchronous RTL; Δ = 0 is expected by construction, not a discovery.

**Table 3. FPGA-vs-xsim agreement.** *Four boundary-validation points at N = 8.*

| *N* | *G* | Topology | xsim cycles | FPGA cycles | Δ (%) |
|---:|---:|---|---:|---:|---:|
| 8 | 2 | linear | ⟨48⟩ | ⟨48⟩ | 0.00% |
| 8 | 2 | ring   | ⟨46⟩ | ⟨46⟩ | 0.00% |
| 8 | 4 | linear | ⟨52⟩ | ⟨52⟩ | 0.00% |
| 8 | 4 | ring   | ⟨50⟩ | ⟨50⟩ | 0.00% |

### 7.4 Same-Fabric ABI Overhead

Ratio of SPRS to the better of ND-Ring and ND-RecDouble on the same substrate.

**Table 4. Same-fabric ABI overhead on 8 representative instances** (full 40-row table in Appendix F).

| *N* | *G* | Topology | SPRS hw_cycles | ND-best hw_cycles | Overhead |
|---:|---:|---|---:|---:|---:|
| 128  | 4    | linear     | ⟨780⟩  | ⟨710⟩  | ⟨1.10⟩ |
| 128  | 16   | torus      | ⟨270⟩  | ⟨240⟩  | ⟨1.13⟩ |
| 512  | 16   | torus      | ⟨870⟩  | ⟨780⟩  | ⟨1.12⟩ |
| 512  | 64   | fat_tree   | ⟨490⟩  | ⟨440⟩  | ⟨1.11⟩ |
| 1024 | 64   | torus      | ⟨1120⟩ | ⟨1010⟩ | ⟨1.11⟩ |
| 4096 | 512  | hypercube  | ⟨2550⟩ | ⟨2300⟩ | ⟨1.11⟩ |
| 8192 | 2048 | torus      | ⟨3330⟩ | ⟨2990⟩ | ⟨1.11⟩ |
| 8192 | 1024 | hypercube  | ⟨3760⟩ | ⟨3360⟩ | ⟨1.12⟩ |

Across all 40 instances: **median overhead ⟨1.12⟩× [95% bootstrap CI ⟨1.10⟩–⟨1.14⟩]**. Rises to ⟨1.18–1.25⟩× at small *N*/*G* on low-bisection topologies. This is the paper's headline overhead figure.

### 7.5 Where the Overhead Goes

Two irreducible sources, both consequences of the ABI:

1. **Tree-depth critical path:** log₂ *N* regardless of *G*; non-deterministic schedules on high-*G* systems can exploit shallower *k*-ary reductions.
2. **ABI locality constraint:** static (left, right) binding forbids reassociation across PEs, forcing partial sums along tree edges.

Both are structural. Lower `gci_latency` or multi-channel GCI would reduce the serialization component, not the reassociation component.

### 7.6 Tournament Characterization (supporting)

The 18×10×122 compiler configuration space is explored by the two-phase tournament; winner-distribution by algorithm family is in Appendix B (Table B.4) and Appendix F's per-instance rows. Briefly: graph-partitioning assignments dominate high-bisection regimes (⟨42%⟩ of winners), tree-DP dominates low-bisection regimes, and no single triple wins across (*N*, *G*, topology). The result empirically corroborates that the ABI orthogonality (§5.3) is satisfied in practice: all 22K configurations produce the same 64-bit result; they differ only in cycle count.

---

## 8. Discussion

### 8.1 What the Claim Does and Does Not Buy

The claim guarantees *fabric self-consistency under cluster reshape*, not agreement with external reducers and not cross-fabric portability of bit patterns. Two SPRS deployments with different FADD microarchitectures (for example, one with subnormal support, another without) would disagree on inputs involving underflow or cancellation at the subnormal boundary. The claim's scope is: one fixed SPRS/fabric pair, arbitrary (*G*, topology) in 𝒯.

A thin input-permutation adapter can align leaf indices to any external reducer's canonical order at zero runtime cost, recovering interoperability at the cost of dropping the cross-reshape guarantee. A more substantive path to interoperability — exporting the ABI discipline onto existing collective libraries such that NCCL, MPI, or oneCCL can inherit the invariance property without adopting our fabric — is sketched in §8.4.

### 8.2 When Not To Use

Workloads tolerating last-bit drift in exchange for ≈10–25% overhead — most production ML training and inference — should continue to use performance-tuned NCCL. SPRS targets workloads where cross-cluster bit-identity is a hard functional requirement: scientific regression testing, deterministic-replay training, differential debugging, and audit/regulatory reproducibility.

### 8.3 Generalization to Other Deterministic ALU Ops

Claim 1 requires only (a) a deterministic binary operation, (b) static (addr_a, addr_b) binding, (c) scoreboard gating. Any deterministic `alu_op` inherits the invariance claim. We empirically validate FADD; SADD, integer ADD, bitwise, min/max inherit the result by *extension of Claim 1*, not by independent experiment. This is a structural extension, not an empirical generalization.

### 8.4 Exporting the ABI: Path to Production Collectives

The most valuable export of this work is not the custom fabric but the **ABI discipline**. An external collective library can inherit cross-topology invariance without adopting our NoC by adopting three rules that are implementable on top of any existing collective runtime:

1. **Fixed tree shape:** force the reduction tree to `FBT(N)` regardless of *G*, by padding the worker set to a power-of-two virtual shape and mapping virtual → physical workers by any function (the mapping is orthogonal by Argument 1).
2. **Fixed operand binding per merge node:** at every internal node of the virtual tree, fix `(operand_a, operand_b)` to `(left_subtree_result, right_subtree_result)` as a pure function of the node index.
3. **Deterministic FADD:** select a single, documented FADD implementation (e.g., the host FPU's RNE path with FTZ disabled or enabled, whichever is chosen) and pin that choice across all workers.

We call this the **pinned-FBT mode**. In NCCL, it would be an algorithm mode parallel to `NCCL_ALGO=Tree` but with an explicit size-indexed tree shape. In MPI, it would be a `MPI_Op` variant with a fixed reduction schedule. In ReproBLAS, it would be an extension that preserves bin accumulation within a worker but imposes a fixed inter-worker tree.

The invariance argument survives into this software-only export because Arguments 1–4 do not depend on our specific NoC or ISA — they depend on static operand binding, single-writer memory discipline, and a deterministic FADD. Any runtime that can be made to honor these three properties inherits Claim 1. The overhead in such a software export would be higher than our ⟨1.12⟩× same-fabric figure — NCCL's ring and double-binary-tree are bandwidth-optimized for NVLink in ways that a fixed `FBT(N)` tree is not — but the overhead trades for a guarantee that NCCL's current deterministic mode does not provide (invariance across *G*).

We view the SPRS fabric and compiler as a *proof of realizability*: showing that the ABI is implementable cleanly with a small ISA surface. The export to production collective libraries is future work and the path by which this research most plausibly reaches end users.

---

## 9. Related Work

**Software reproducibility.** ReproBLAS [Demmel & Nguyen 2013] and ExBLAS [Iakymchuk et al. 2016] achieve order-independent reductions via binned accumulation, single-node. Horovod-det, oneCCL-det, NCCL `NCCL_ALGO=Tree` + single channel fix a reduction algorithm within one cluster configuration but do not preserve bit-identity under reshape. SPRS targets the cross-reshape axis.

**Compilers for collectives.** TACCL [Shah et al. 2023], SCCL [Cai et al. 2021], BLINK [Wang et al. 2020] synthesize performance-optimized collective schedules; reproducibility is out of scope for them. An SPRS-style ABI constraint could in principle be layered as an additional scheduler invariant.

**In-network reduction.** SHARP and Tofino-based in-switch reductions pin operand orders at the switch. These share with SPRS the insight that the fabric is the correct level for reproducibility, but do not frame it as an ABI and do not provide a cross-topology-invariance property.

**Deterministic accelerators.** Cambricon [Liu et al. 2016] and TPU [Jouppi et al. 2017] provide deterministic per-chip execution; cross-chip collectives inherit the non-reshape guarantee of the vendor library.

**NoC.** Dally & Towles [2004] — the adjacency/routing-table abstraction and VC-escape discipline.

**On novelty as composition.** A fair reading is that SPRS's individual components — HEFT/Lukes/MLfm on the compiler side, XY routing/VC escape/scoreboarded pipelines on the fabric side — are individually due to prior work. Our contribution is not a new component algorithm or a new router primitive. It is the **interface observation**: that *if* compiler and fabric agree on a size-indexed reduction tree as a shared contract, *then* any choice among those prior-art components inherits cross-topology bitwise invariance by composition. We argue this is the under-explored axis.

---

## 10. Limitations

1. **FPGA coverage**: four small-scale points; all other scales are xsim only.
2. **Synthetic workload values**: leaf values from `make_leaf_val`, not a real gradient distribution. The claim is value-independent; overhead ratios may vary modestly under heavy-tail cancellation workloads.
3. **No head-to-head vs NCCL**: NCCL does not target cross-reshape invariance; a fair comparison would require a GPU cluster and is out of scope.
4. **Convenience-sampled instance suite**: per-cell coverage in Appendix D; some cells thin.
5. **Tournament selection bias**: quantified in Appendix E; qualitative claims insensitive to top-15 cutoff in [10, 30].
6. **FADD is FTZ+RNE, not strict IEEE 754**: fully documented in §3.6.
7. **Dynamic-only deadlock enforcement**: hardware dateline and bounded-model-checked routing soundness are future work (see §4.8).
8. **Single-reduction ISA scope**: OP_RESERVED slot earmarked for BARRIER/RESET_SB extension.
9. **Single clock domain**: no CDC; multi-chiplet extension future work.
10. **Store-and-forward router**: HoL pressure at large *G* (see §4.8); wormhole extension future work.
11. **Absolute-vs-relative performance**: our same-fabric ⟨1.12⟩× is a *ratio*, not an absolute-competitiveness claim against NCCL on NVLink or RCCL on InfinityFabric. Those production collectives are bandwidth-optimized for hardware we do not model (high-radix NVSwitch, multi-flit wormhole routing, overlapping-pipeline ring). SPRS's absolute `hw_cycles` on our fabric should not be compared to production collectives' measured times; the paper reports the ABI overhead on a shared substrate where both schedules face identical hardware constraints.
12. **Regulated-deployment gap**: for customers requiring IEEE-754-compliance-*and*-cross-reshape-invariance (regulated ML, bit-parity with NumPy/MATLAB reference implementations), the FTZ+RNE adder is insufficient. A subnormal-aware FADD variant is a one-instruction extension (§3.6) but not implemented in this revision.

---

## 11. Conclusion

Cross-topology bitwise reproducibility has been treated as a library-level performance flag, tunable within one cluster and lost under reshape. Treating reduction order as a compiler/fabric ABI, indexed only by *N*, moves the guarantee into the interface. Under seven explicit assumptions, the composition of (i) a four-opcode scoreboarded ISA, (ii) a topology-parametric NoC, and (iii) an ABI-compliant compiler produces fabric self-consistency under arbitrary (*G*, topology) reshape within the declared family 𝒯. The overhead is a ⟨1.12⟩× median relative to the best non-deterministic schedule on the same substrate. These results suggest that cross-topology invariance is best addressed at the compiler/fabric interface rather than purely in software libraries below which the physical network is unobservable.

---

## References

[IEEE BibTeX. Key citations: Higham 2002; Demmel & Nguyen 2013 (ReproBLAS); Iakymchuk et al. 2016 (ExBLAS); Dally & Towles 2004; Topcuoglu et al. 2002 (HEFT); Lukes 1974; Yang & Gerasoulis 1994 (DSC); Karypis & Kumar 1998 (multilevel FM); Shah et al. 2023 (TACCL); Cai et al. 2021 (SCCL); Wang et al. 2020 (BLINK); Jeannot et al. 2014 (TreeMatch); Jouppi et al. 2017 (TPU); Liu et al. 2016 (Cambricon); Goldberg 1991.]

---

## Appendix A — ISA and Packet Formats

Instruction (64b, btree_pkg.sv:50–60); packet (96b, noc_pkg.sv:29–38); ALU ops (btree_pkg.sv:39–48).

## Appendix B — Algorithm Catalog and Winner Distribution

**Table B.1.** S2 assignment (18 algorithms: HEFT, RecBisect, MLfm, DKway, ExactBB, DFSseed, DSC, Chret, CPOP, Centroid, Lukes, Frederik, CPFD, ClHEFT, ParSub, Spine, SubPack, LvlHLF).

**Table B.2.** S3 mapping (10: Identity, HopMin, TreeMatch, QAP-SA, MCF, DRB, SFC, Spectral, RAGreedy, Tabu).

**Table B.3.** S4 refinement (12 base: None, CPcoloc, FM, MCFM, ALNS, LeafMig, NetW, SubMig, CentReb, TERe, VCycles, FlowMC; chainable to 122).

**Table B.4.** Winner distribution by family: S2 graph-partitioning ⟨42%⟩, list-scheduling ⟨22%⟩, tree-DP ⟨14%⟩, hierarchical ⟨11%⟩, other ⟨11%⟩; S3 Identity ⟨28%⟩, TreeMatch ⟨19%⟩, HopMin ⟨17%⟩, QAP-SA ⟨12%⟩, other ⟨24%⟩; S4 None ⟨19%⟩, CPcoloc ⟨22%⟩, FM/MCFM ⟨18%⟩, ALNS ⟨12%⟩, other ⟨29%⟩.

Each entry maps to a function registered in `STAGE{2,3,4}_METHODS` (sprs_core.py:5030–5054).

## Appendix C — Worked Invariance Example

*N* = 4. `FBT(4)` has 7 nodes, post-order `[3, 4, 1, 5, 6, 2, 0]`. Every valid SPRS compilation emits: `DMEM[1] ← FADD(DMEM[3], DMEM[4])`; `DMEM[2] ← FADD(DMEM[5], DMEM[6])`; `DMEM[0] ← FADD(DMEM[1], DMEM[2])`. The root result is always `FADD(FADD(L₀, L₁), FADD(L₂, L₃))`.

## Appendix D — Instance-Suite Coverage

Per-(*N*-bucket, topology) cell counts. Buckets ≤ 32, 33–256, 257–2048, 2049–8192.

|   | linear | ring | mesh | torus | fat_tree | hypercube |
|---|---:|---:|---:|---:|---:|---:|
| ≤ 32      | 2 | 2 | 0 | 1 | 1 | 1 |
| 33–256    | 1 | 1 | 1 | 2 | 1 | 0 |
| 257–2048  | 2 | 2 | 2 | 3 | 2 | 2 |
| 2049–8192 | 0 | 0 | 0 | 2 | 3 | 2 |

## Appendix E — Tournament Selection-Bias Quantification

On a stratified subset of 8 instances: leakage ⟨p⟩ (95% CI); Spearman ρ(SW, HW) ⟨ρ⟩; cutoff ablation at 10 / 15 / 30 with qualitative-invariance confirmation.

## Appendix F — Full Per-Instance Results, Figures, and Ω Diagnostics

Per-instance 40-row table: *N*, *G*, topology, Ω, SPRS hw_cycles, ND-Ring, ND-RecDouble, ND-best, SW-FixedTree upper bound, same-fabric overhead, ratio-vs-Ω diagnostic, xsim wall-clock. Figures F.1 (hw_cycles vs *N*, faceted); F.2 (overhead vs *N*/*G*); F.3 (root-port queue occupancy distributions, 4 representative instances).

## Appendix G — Reproducibility Checklist

**Constants (from btree_pkg.sv, noc_pkg.sv, sprs_core.py):** DMEM_DEPTH = 512; IMEM_DEPTH = 512; gci_latency = 4; gci_gap = 6; MAX_ROUTERS = 4096; MAX_PORTS = 8; NOC_FLIT_W = 96; DEFAULT_VCS = 2; MAX_VCS = 4; TX_BUF_DEPTH = RX_BUF_DEPTH = 8; TIMEOUT_MAX = 10 000; WATCHDOG_MAX = 20 000.

**Runtime assertion harness (§3.7):** single-file `validate_abi.py` checks A4, A5 on the emitted IMEM for every `(N, G, topology)` tuple prior to xsim/FPGA. Fails compile on violation.

**Routing-table acyclicity check:** `validate_routing.py` builds the channel-dependency graph on emitted routing tables and verifies acyclicity for each instance prior to xsim.

**Seeds.** Stochastic S2/S3/S4 algorithms (QAP-SA, ALNS, Tabu, Spectral) seeded at 42 uniformly.

**Tools.** Vivado 2023.1 (Linux) / 2025.2 (Windows) for xsim; Xilinx Nexys4 DDR (Artix-7 XC7A100T) for FPGA.

**Entry points.** `python3 sprs_tournament.py --mode phase1 --smoke --workers 4` (≤ 15 s sanity); `--mode phase1` (full Phase 1); `--mode phase2` (full Phase 2).

**FPGA.** `build_interactive.tcl` generates small-scale bitstreams; serial-console driver reads back performance counters at program end.

**Artifact URL.** [placeholder — released at camera-ready].
