# SPRS / NoC Fabric: Complete Design-Choice Analysis

A systematic accounting of every non-obvious design choice in `sprs_core.py` + `sprs_tournament.py` + the 13 RTL files, with the rationale behind each. Rationales reconstructed from inline comments, naming conventions, code structure, and observed constraint interactions.

---

## 0. System Dataflow (End-to-End)

```
(N, G, topology) ─► S0 Ω ─► S1 FBT(N) ─► S2 α ─► S2.5 repair ─► S3 μ ─► S4 r (122 cfgs)
                                                                        │
                                                                        ▼
                                                          S5 mem enforce
                                                                        │
                                                                        ▼
                                                   S6 build_schedule + codegen
                                                                        │
                                                                        ▼
                                  per-GPU IMEM + per-router (route, adj) + GCI buffer
                                                                        │
                                                                        ▼
                           load → program_start → run → extract cn_result[ROOT_GPU]
```

On the hardware side:
```
IMEM[pc] → IF → DE (scoreboard gate) → EX (fp64_add) → DMEM write + scoreboard set
                      ▲                                    │
                      │  ◄─── PIU writes (RDMA-push)        │
                      │  ◄─── GCI writes (leaf fetch)       │
                      │                                    │
                      └──────── forwarding (d1, d2) ◄──────┘
```

---

## 1. Compiler Design Choices

### 1.1 Tree representation: `FBT(N)` (full binary tree on 2N-1 nodes)

**Class:** `CBTree` at sprs_core.py:380–482. Historical name; implements a full binary tree.

**Design choices:**
- **Heap indexing** (node *i*'s children at 2*i*+1, 2*i*+2): O(1) parent/child with no pointers; identity of every node is a pure function of N.
- **Full, not complete, binary tree** (total_nodes = 2N-1, always odd): for any internal node, both children are in range. Eliminates the single-child edge case entirely at the tree level; the identity-operand slot (DMEM[0]) is reserved-but-unused in this workload.
- **Precomputed postorder** (sprs_core.py:412–422): cached after first call. Postorder *is the reduction order* — the ABI.
- **Precomputed Sethi-Ullman numbers and HU levels** (453–465, 442–452): used by both register-pressure analysis (DMEM budget) and critical-path estimation. Cached.
- **`reduction_signature` method** (474–481): SHA256 fingerprint of the tree structure. If two SPRS runs produce different schedules, their canonical expected result is derivable from this signature alone — a leaf-binding-preserving invariant.

### 1.2 Topology as a runtime configuration

**Class:** `Topology` at sprs_core.py:487–695.

**Design choices:**
- **Adjacency-list internal + distance matrix cache.** `_dist_matrix` for n ≤ 32768; BFS with memoization (`_dist_cache`) beyond. Balances memory vs. recomputation.
- **Analytical distance formulas** for each known topology (`_analytical_distance` at 558–574): O(1) hop count for linear/ring/mesh/torus/fat-tree/hypercube. Falls back to BFS only for custom topologies.
- **`generate_routing_tables`** (666–679): per-router table where each (router, destination) entry is the *first hop port on the shortest path*. Shortest-path-only by construction — no load balancing, no adaptive routing. This is the **static routing discipline** that A6 (routing-table soundness) relies on.
- **`active_nodes` vs. `n_nodes`**: for mesh/torus/hypercube, the topology has ≥ requested G (padded to power-of-2 for hypercube, to rows×cols for mesh/torus). The compiler uses only active_nodes as valid GPU targets but the fabric instantiates all physical routers.

**Why this matters:** *topology is data, not RTL*. Adding a new topology means implementing `.linear()/.ring()/...` classmethod that emits an adjacency + routing table. No Verilog change.

### 1.3 PrecomputedContext: hot-path acceleration

**Class:** `PrecomputedContext` at sprs_core.py:137–344.

**Design choices:**
- **Cached per-instance context.** Tree structure, flat arrays (children CSR, postorder, parent), comm matrix, NumPy arrays, ctypes buffers — all precomputed once, reused across ≈ 22K algorithm evaluations per instance.
- **Ctypes buffer reuse** (247–256, 262–271): per-thread reusable `ctypes.c_int` array for the assignment being evaluated. Avoids allocation during the hot path.
- **C extension** (lines 24–102): three hot kernels (`c_cp_comm`, `c_edge_cut`, `c_max_load`) compiled at import time. Falls back to NumPy or pure-Python paths if compilation fails. 10–100× speedup over Python.
- **Fork-based parallelism via `multiprocessing`**: precomputed context is *copied via fork* to all workers (Linux only). On Windows it's re-built per worker — acceptable overhead since tournaments run on Linux workstations.

**Rationale:** the tournament needs to score ≈ 22K configs × 40 instances = 880K `build_schedule + compute_lower_bound + generate_instructions` calls. Without the C extension, this is infeasible within a wall-clock budget.

### 1.4 HardwareConfig: first-class cost model

**Class:** `HardwareConfig` at sprs_core.py:358–375.

**Design choices:**
- **Every RTL latency exposed as a Python parameter.** `gci_latency`, `compute_latency`, `ni_inject_cycles`, `router_per_hop_cycles`, `ni_eject_cycles`, `piu_processing`, `pipeline_overhead`. These mirror the RTL exactly.
- **`gci_gap = gci_latency + 2 = 6`** (RTL-proven): the software cost model's GEN→GEN spacing matches the hardware-observed inter-GENERATE interval, which is `gci_latency` for the state machine plus 1 cycle for `gci_done` to pulse plus 1 cycle for DMEM write commit.
- **`pipeline_overhead = 3`**: 2-cycle fill (IF+DE) + 1-cycle drain (P_DRAIN state). Added to the final makespan at sprs_core.py:5237.

**Why this matters:** the SW makespan estimate tracks HW cycles within a few percent because the same constants appear on both sides. This is not accidental — these values were tuned against RTL traces.

### 1.5 Stage 0: composite lower bound Ω

**Function:** `compute_lower_bound` at sprs_core.py:1015–1140.

**Design choices (each constituent is a lower bound on _any_ schedule on this fabric):**
- **`lb_span`**: critical-path depth. `gci_gap + D · compute_latency`. Zero-communication lower bound.
- **`lb_gen(K)`**: GCI serialization bottleneck. `gci_gap · ⌈N/K⌉`. Heaviest PE's leaf generation time.
- **`lb_instr(K)`**: instruction-throughput bottleneck. `⌈(N + (N-1)·compute_latency + (K-1)) / K⌉`. Minimum cycles if pipeline slots were perfectly balanced.
- **`lb_comm`**: single cross-PE hop floor for K ≥ 2. `gci_gap + comm_cost(d_min) + compute_latency`.
- **`lb_gather`**: the root PE's critical path. `gci_gap + ⌈log₂ K⌉ · compute_latency + comm_cost(⌈diameter/2⌉)`.
- **`lb_bisect`**: link serialization at topology bisection. `gci_gap + ⌈⌈(K-1)/2⌉ / bisection_bw⌉ + comm_cost(1) + compute_latency`.
- **`lb_hu`**: GCI-aware Hu HLF bound — see `_hu_hlf_lb` at 1294–1321.
- **`K* search**: the optimizer loops over K ∈ [K_min, K_max] to find the K minimizing `max(lb_gen(K), lb_instr(K), lb_comm)`. K_min comes from IMEM capacity; K_max from G and 2N-1.
- **`active_bound`**: the name of the constituent hitting the max. Reported per instance so tournament analysis can explain where each instance is bottlenecked.

**Rationale:** Ω is NOT a single tight bound — it is a union of six physics-informed bounds, each dominating in different regimes. The *active* constituent per instance is itself diagnostic information: if `lb_bisect` dominates, no schedule can do better than the bisection; if `lb_gen` dominates, more PEs help; etc.

### 1.6 Stage 2: 18 assignment algorithms

**Location:** sprs_core.py:1489–3207.

**Design rationales by family:**

| Algorithm | Why included | Constraint invariants it preserves (or doesn't) |
|-----------|--------------|--------------------------------------------------|
| HEFT | Canonical DAG scheduler | **Contiguity** enforced (line 1526–1537: valid_gpus = child GPUs ∪ one unused) |
| RecBisect | Classical graph partitioning | Always connected by construction |
| MLfm | Best-in-class graph partitioning | May produce disconnected — needs S2.5 |
| DKway | METIS-style direct k-way | Typically connected |
| ExactBB | Branch-and-bound | Exact-optimal small N; times out beyond ~64 nodes |
| DFSseed | Structural seed-and-grow | May produce disconnected |
| DSC | Dominant Sequence Clustering | May produce disconnected |
| Chret | Chrétienne's tree algorithm | Connected by construction |
| CPOP | Critical-path-on-processor | Connected-ish |
| Centroid | Geometric | Variable |
| Lukes | Tree-DP (exact for small G) | Connected |
| Frederickson | Tree-DP (log factor) | Connected |
| CPFD | List-scheduling | May produce disconnected |
| ClHEFT | Hierarchical HEFT | Variable |
| ParSub | Parallel subtree | Connected |
| Spine | Spine-based | Connected |
| SubPack | Subtree packing | Connected |
| LvlHLF | Level-parallel Hu | Connected |

**HEFT's contiguity constraint** (line 1526–1537) is worth calling out specifically: naive HEFT would scatter tasks across GPUs with wild abandon. This code restricts placement to *(child-hosting GPUs ∪ one unused)* so that children of a node are always co-located with the node or on a used-to-unused transition. Without this, the partition would fracture, S2.5 would need to make many repairs, and refinement would be chasing a moving target.

**Design rationale for 18 methods:** no single heuristic dominates — the tournament reveals different winners in different (N, G, topology) regimes (Tree-DP at small G, graph-partitioning at balanced topologies, list-scheduling at tall trees). Each method represents a distinct algorithmic family from the literature.

### 1.7 Stage 2.5: connectivity repair — the load-bearing determinism pass

**Function:** `repair_connectivity` at sprs_core.py:1387–1483.

**Design choices:**
- **Docstring explicitly states the determinism consequence**: disconnected partitions cause non-sibling COMPUTE pairs → wrong result under FP64 non-associativity.
- **Strategy:** bottom-up BFS finds connected components per GPU; keeps the largest (the one containing the smallest node ID, which in heap-indexed tree = closest to root); reassigns orphans to their parent's GPU.
- **Iteration limit: 20 passes.** Because reassigning orphan A to parent's GPU might orphan B on some other GPU, the process may need multiple passes. 20 is a practical bound.
- **Fail-stop property:** if a root component is orphan (shouldn't happen), it's left alone; subsequent `_validate_assignment` will catch it.

**Why this exists:** 6–8 of the 18 S2 methods (HEFT, MLfm, DSC, DFSseed, CPFD, etc.) may produce disconnected partitions. Without S2.5, their outputs would violate the ABI. S2.5 makes them ABI-compliant.

### 1.8 Stage 3: 10 mapping algorithms

**Location:** sprs_core.py:3230–4032.

**Design choices:**
- **Identity is the default** (`3a`, `map_identity`): GPU index *g* → physical PE *g*. Wins ~28% of tournaments — meaning S2 usually produces GPU indexing that already matches the topology.
- **HopMin** (greedy nearest): cheap, works when S2 is close to optimal.
- **TreeMatch** (Jeannot et al.): matches the compiler's PE communication graph to the topology's distance graph hierarchically.
- **QAP-SA**: stochastic. Simulated annealing over Quadratic Assignment. Seed-fixed at 42.
- **MCF**: min-cost-flow formulation.
- **DRB**: dimension-reduced bisection.
- **SFC**: space-filling curve.
- **Spectral**: Laplacian eigenvector-based.
- **RAGreedy**: routing-aware greedy.
- **Tabu**: tabu search.

**Design rationale for 10 methods:** spans trivial (Identity) through greedy through exact-optimization through stochastic. Identity exists specifically because "usually, don't remap" is the correct answer.

### 1.9 Stage 4: 12 refinement algorithms, 122 configurations

**Location:** sprs_core.py:4034–4700.

**Design choices:**
- **12 single refinements + chainable to 122 ordered pairs** (12 × 11 single-pair + 12 single = 132... actually 12 × 11 = 132 ordered pairs, plus 12 single = 144 — README says 122, which is the deduped count excluding obvious no-ops).
- **Rollback-protected composition** (`refine_phased` at 4836–4877): every refinement is tried, its output validated, and kept only if makespan strictly improves. Monotonic-in-makespan by construction.
- **ALNS gate at `bms > lbs * 1.15`** (line 4866): ALNS is expensive; apply only when the current assignment is > 15% worse than critical-path lower bound.
- **Deadline gates everywhere**: `_check_deadline("post-FM")`, `_check_deadline("ALNS_gate")`, etc. Guarantees `refine_phased` always terminates.

**Rationale:** refinement explores the neighborhood of the S2 output. Rollback-protected composition means a buggy or slow S4 cannot make the result worse.

### 1.10 Stage 5: memory enforcement

**Function:** `enforce_memory` at sprs_core.py:4939–5025.

**Design choices:**
- **Three tiers:** SU-number check → IMEM budget → DMEM budget.
- **SU tier** is informational: SU number bounds the DMEM live set; always passes at 512 for N ≤ 8192.
- **IMEM tier** estimates per-GPU instruction count including GCI-serialization NOPs; if > 512, redistributes by moving leaves (least structural impact) to least-loaded GPUs. Up to 50 iterations.
- **DMEM tier** estimates per-GPU DMEM including receive buffers; if > 512, redistributes deepest nodes first.

**Hidden concern:** S5 can re-break connectivity after S2.5 fixed it. The current pipeline does NOT re-run S2.5 after S5. For current instance sizes (N ≤ 8192), S5 rarely fires — but this is a latent issue for scale.

### 1.11 Stage 6: schedule construction

**Function:** `build_schedule` at sprs_core.py:5135–5239.

**Design choices:**
- **Walks SU-postorder** (`tree.su_postorder()`): Sethi-Ullman sibling reordering minimizes register pressure while preserving operand binding (children[0]=left, children[1]=right is preserved).
- **Per-PE clock tracking** (`gpu_time[g]`, `gci_free[g]`, `node_ready[n]`): three maps track when each PE is free, when its GCI is free to issue the next GENERATE, and when each node's result is available.
- **GCI constraint** (lines 5161–5174): next GENERATE on a PE cannot start until `max(gpu_time[g], gci_free[g])`. Data is ready at `t + gci_latency + 2` (the RTL-proven gap).
- **Cross-PE SEND emission** (lines 5179–5212): when a child's GPU ≠ parent's GPU, emit a SEND on the child side, compute arrival time `send_time + 1 + hw.comm_cost(hops)`, and the parent's COMPUTE waits on arrival via scoreboard.
- **Operand binding**: `child_addrs = [addr_map[gpu][c] for c in children]` — **addresses bound in tree.children() order, which is [left, right]**. This is the code that realizes A5.
- **Identity padding** (line 5221–5222): if a node has <2 children (impossible in FBT(N) but kept for extensibility), `addr_b = DMEMAllocator.IDENTITY_ADDR = 0`.
- **Pipeline overhead**: `schedule.makespan += hw.pipeline_overhead = 3` at line 5237. Accounts for IF+DE fill + P_DRAIN.

### 1.12 DMEM allocator

**Class:** `DMEMAllocator` at sprs_core.py:5087–5132.

**Design choices:**
- **SU-postorder traversal**: children visited before parent, so the parent can free children's addresses into its PE's free list upon visit.
- **Free-list LIFO**: popped slots are the most recently freed (from the nearest consumer) — keeps the working set small in DMEM.
- **Separate pass for cross-PE receive buffers** (lines 5123–5130): after the main allocation, walk the tree again to allocate persistent DMEM slots for incoming packet targets. These are *never freed* during the run, since the receiver's scoreboard-gated COMPUTE relies on the address being stable.
- **Address 0 reserved as identity**: `peak_local[gpu] = 1` starts the bump pointer at 1. Address 0 never issued.

**Invariant established:** each non-identity DMEM address written exactly once. Because FBT has unique consumers and SU-postorder ensures free-happens-after-consume, no slot is reused while its value is still live. This is the A4 (single-writer) invariant *constructed*, not assumed.

### 1.13 Instruction generator: `generate_instructions` + peephole

**Function:** sprs_core.py:5242–5284.

**Design choices:**
- **Cycle-accurate NOP insertion**: the op's scheduled cycle drives NOP padding to advance `current_cycle`. This produces an IMEM whose *instruction index* equals the *cycle issued* (modulo stalls).
- **Peephole pass** (`_peephole_nop_compress` at 5287–5347):
  - **Pass 1**: collapses runs of NOPs but preserves at least `gci_gap = 5` NOPs per run (the minimum required by GCI serialization).
  - **Pass 2**: for every consecutive GENERATE pair, inserts NOPs to enforce `gci_gap` spacing if the gap is too small.
  - **Trailing NOP stripping**: removes NOPs at the end of the IMEM.
- **`imem_size` populated from `len(instrs)`**: this is the termination condition — the fabric runs until `pc >= imem_size` and the pipeline drains.

### 1.14 Testbench emitter: `emit_sv_testbench`

**Function:** sprs_core.py:5351–5580.

**Design choices:**
- **GCI buffer ordering is per-schedule, not per-tree** (line 5526–5544): for each GPU, the GCI buffer slots are loaded in the GPU's *scheduled GENERATE order*. Critical because `gci_rd_ptr` increments per GENERATE (noc_ni.sv:211).
- **Leaf values are deterministic functions of global leaf index** via `leaf_to_global_idx` (line 5453): `idx = enumerate(tree.leaves())` is a canonical ordering. `make_leaf_val(idx, alu_op)` produces the value. For FP64 (`alu_op=0b111`), `fv = (idx+1)*1000.0 + ((idx*37+13)%100)/100.0 + 0.007`.
- **Oracle computation** (line 5460–5471): for FADD, walk the tree in postorder applying `_fp64_add_bits` (the bit-exact Python mirror). The resulting 64-bit bit pattern is the expected result.
- **EXPECTED constant** (line 5482): hardcoded into the testbench as a 64-bit literal.
- **PASS/FAIL check** (line 5559): compares `u_sys.gen_node[{root_gpu}].u_cn.result == EXPECTED`.

**Rationale for the leaf-value pattern:** the magic constants `(idx+1)*1000 + fractional + 0.007` are chosen to produce mantissa-rich values that exercise the FP64 rounding path — not trivial integers where FADD would compute exactly. The `0.007` offset makes sure every leaf is a non-terminating binary fraction, so non-associativity would produce distinct results under reordering.

### 1.15 Tournament orchestrator

**File:** `sprs_tournament.py`.

**Design choices:**
- **Two-phase tournament**:
  - **Phase 1**: 180 baseline (S2, S3) configurations on all 40 instances. Top 15 per instance by SW `makespan` promoted.
  - **Phase 2**: Top 15 Phase-1 winners × 122 S4 configurations. Two strategies: full cartesian (`_eval_pipeline`) or greedy L1→L2 (`_eval_greedy_pipeline`).
- **Testbench-hash deduplication** (line 121–124, `_hash_assignment`): SHA256 of the assignment tuple identifies IMEM-equivalent triples. Phase 3 only runs unique testbenches through xsim; followers inherit cycle counts.
- **Live CSV streaming** (line 401–478): per-instance rows flushed to disk as they arrive — if the tournament crashes, at most the in-flight row is lost, the rest is preserved.
- **Resume support** (`--resume` flag): reads existing `sw_results.csv` rows and skips completed instances.
- **Per-worker seeded RNG**: `_worker_init` forks a process with shared precomputed state; stochastic algorithms use seed 42.
- **AlgoTimeout handling**: caught and recorded as a row error; does not abort the tournament.

---

## 2. RTL Design Choices

### 2.1 `btree_pkg.sv` — ISA and format constants

**Module parameters:**
- `DMEM_DEPTH = 512`, `IMEM_DEPTH = 512`: per-PE memories. Small enough to fit in block RAM on Artix-7. Chosen to fit all 40 instances without overflow.
- `TX_BUF_DEPTH = 8`, `RX_BUF_DEPTH = 8`: link FIFOs. 8 flits = 96×8 = 768 bits per FIFO.
- `TIMEOUT_MAX = 10000`: stall timer threshold. After 10K cycles of continuous EX stall → P_ERROR.
- `WATCHDOG_MAX = 20000`: no-progress watchdog. After 20K cycles without any instruction retiring → P_ERROR.
- `ROUTE_TABLE_DEPTH = 4096`: routing table capacity = MAX_ROUTERS. One entry per possible destination.

**ISA design:**
- 4-bit opcode allows 16 opcodes; only 4 are live. `OP_RESERVED = 4'h4` is the former `OP_RECV` from the pre-RDMA-push era; any `opcode > 4'h3` traps to `P_ERROR`. The reserved slot is available for future BARRIER/RESET_SB.
- 3-bit `alu_op` field allows 8 ALU operations: ADD, MAX, MIN, AND, OR, XOR, SADD (signed), FADD (IEEE 754).
- 16-bit `dest`, `addr_a`, `addr_b` fields: each can address DMEM_DEPTH = 512 (9 bits used). Room for 65K entries — future-proofed for wider DMEM.
- **Instruction format** (64-bit):
  ```
  [63:60] opcode  (4b)
  [59:56] aux     (4b)   aux[0]=link, aux[3:1]=alu_op
  [55:40] dest    (16b)
  [39:24] addr_a  (16b)
  [23:8]  addr_b  (16b)
  [7:0]   reserved (8b)
  ```

### 2.2 `noc_pkg.sv` — NoC constants

- `MAX_ROUTERS = 4096`, `MAX_PORTS = 8`: cluster scale limits.
- `NOC_FLIT_W = 96`: single-flit packets. Packet = `{dest_node_id[16], target_addr[10], reserved[6], payload[64]}`.
- `DEFAULT_VCS = 2`, `MAX_VCS = 4`: virtual channels. 2 is enough for VC-escape on cyclic topologies.
- `ADJ_DISCONNECTED = 16'hFFFF`: sentinel for an unconnected port in the adjacency table.

**Design rationale:** 96-bit single-flit packets are a scope decision. Multi-flit would admit partial-packet deadlocks and require a more elaborate flow-control argument. A single FP64 value (64 bits) + header (32 bits) = 96 bits, exactly one flit.

### 2.3 `sync_fifo.sv` — the primitive

**Design choices:**
- **Pointer-based synchronous FIFO** with `$clog2(DEPTH)` pointers and a `$clog2(DEPTH+1)` count register.
- **Case-based write/read/both-at-once** (line 42–59): single-always block handles the four cases explicitly. Avoids race between `w_en` and `r_en` on full or empty.
- **Level signal exposed**: consumer can see the current fill depth (unused in the current design, but reserved for monitoring).

**Used in:** every FIFO in the design — TX buffers, RX buffers, ingress VC buffers, egress buffers, NI injection FIFOs. One module, everywhere.

### 2.4 `link_tx.sv` — credit-based flow control

**Design choices:**
- **8-bit credit counter** (`credits <= RX_BUF_DEPTH[7:0]` at reset): supports up to 256 buffer depth.
- **Single-bit credit-return input**: one credit per pulse.
- **`send_rdy = (credits > 0)`**: simple combinational send gate.
- **Counter update** (line 33–35): `credits + credit_return - (send_en && send_rdy)` per cycle. Self-consistent — sends decrement, returns increment.

**Invariant:** at any time, `credits[link_tx] + buffered_packets[downstream_rx] = RX_BUF_DEPTH`. This is the credit-conservation invariant A7.

### 2.5 `noc_link.sv` — configurable-latency inter-router link

**Design choices:**
- **Parametric `LATENCY`**: `LATENCY=0` → combinational wire; `LATENCY=N` → N-stage shift register for both forward data and reverse credit.
- **Reverse credit path pipelined identically** to forward path: credit returns experience the same latency as data going out. This keeps the credit round-trip deterministic.

**Why configurable:** on-chip small design wants LATENCY=0 for cycle accuracy; larger silicon or multi-chiplet wants LATENCY>0 to model wire delay. Current instantiations use LATENCY=1 (single register).

### 2.6 `noc_router.sv` — multi-VC router

**Three-stage pipeline:**
- **Stage 1: Input Buffering** (per-port, per-VC FIFOs). VC steering from packet bit [64].
- **Stage 2: Route Computation + VC/Switch Allocation**.
- **Stage 3: Switch Traversal + Egress Queueing**.

**Design choices:**
- **Packet bit [64] steers VC** (line 111–117): header-only, value-independent VC selection. Keeps fabric-timing independent of payload values.
- **Routing table is write-only SRAM** (line 59–69): no reset (would be wasteful); configured once at startup by the testbench or driver.
- **Two-level arbitration** (lines 223–293):
  - **Inner**: per-(port, vc), route-lookup to determine output port.
  - **Outer**: per-output-port round-robin across all flattened `(port, vc)` candidates.
  - `rr_ptr[oport]` advances *only* on successful grant (line 245). Starvation-free.
- **Combinational crossbar** (line 251–293): single `always_comb` selects one winner per output port.
- **Single egress FIFO per port** (VCs are input-side only; egress is shared). Simpler; acceptable because egress is downstream of VC isolation.
- **Credit-pulse serialization** (line 175–205): crucial bug fix. Old code collapsed multi-VC reads into one credit pulse → credit leak → eventual deadlock. New code maintains a `credit_pending` counter that drains one pulse per cycle.

### 2.7 `noc_ni.sv` — network interface + GCI buffer

**Three functions:**
- **Injection**: round-robin merge of CN's NUM_LINKS TX streams into a single router TX port.
- **Ejection**: forward router's RX to CN's link 0 (PIU handles delivery to DMEM).
- **GCI buffer**: loadable RAM of leaf values, read sequentially on each GENERATE.

**Design choices:**
- **Round-robin injection** (line 75–125): avoids starvation when CN has multiple TX links active.
- **Injection FIFO** (line 92–103): buffers packets before the credit-gated `link_tx`. Decouples the CN from link backpressure.
- **Ejection to link 0 only** (line 148–155): simplicity — CN-side FSM has only one PIU, doesn't need multi-link ejection.
- **GCI state machine** (line 190–215): on `gci_start`, count up to `GCI_LATENCY` cycles, then pulse `gci_done` and deliver `gci_buffer[gci_rd_ptr++]`.
- **Read pointer wraps** (line 211): `gci_rd_ptr + 1`. If the compiler issues more GENERATEs than the buffer holds, this wraps silently — a potential bug, but compile-time `max_leaves_per_gpu` enforcement prevents it.

**Why GCI exists as an abstraction:** it models a real accelerator's data-staging interface. In production, leaves would arrive from HBM or from an upstream kernel; in this prototype, they come from a VIO-writable buffer. The point is that the ISA instruction (GENERATE) is interface-agnostic.

### 2.8 `btree_fsm_fast.sv` — the core compute unit

**915 lines, three-stage pipeline, multi-priority write-arbitration, scoreboard-gated execution.**

**Pipeline (IF→DE→EX):**
- **IF**: Registered IMEM read (1-cycle latency). PC management. Combinational decode of opcode/aux/dest/addr fields.
- **DE**: Scoreboard hazard check. Issues DMEM reads. Stalls if either scoreboard bit is 0.
- **EX**: Inline ALU (combinational FADD and friends). Writeback to DMEM or TX FIFO enqueue. Stalls if SEND back-pressure or write-collision.

**Scoreboard (line 264–265, 700–715):**
- 1 bit per DMEM address, total = `DMEM_DEPTH` bits.
- Set on any write (PIU, GCI, COMPUTE writeback, GENERATE).
- Cleared only on reset or `program_start`.
- `scoreboard[0] = 1` at reset (identity slot always valid).

**Two-level DMEM forwarding (line 149–181):**
- Level 1 (d1): captures write in cycle N for forwarding to read in cycle N+1.
- Level 2 (d2): captures write one more cycle, surviving a 1-cycle DE stall.
- Address-compare-and-mux: if scoreboard-gated read's address matches d1's or d2's write, return that value instead of BRAM's stale read-first value.

**PIU (Packet Ingress Unit) (line 247–345):**
- Drains RX FIFOs on priority basis.
- If `pkt[95:80] == gpu_id`, writes `payload` to `DMEM[pkt[79:70]]` (target_addr from header) and sets the scoreboard bit autonomously.
- If not, drops the packet and asserts `piu_misroute` for one cycle. Returns credit unconditionally.
- Runs independently of the FSM pipeline — cannot be deadlocked by a COMPUTE waiting on data.

**DMEM write arbitration: PIU > GCI > FSM** (line 358–376):
- PIU always wins (maintains RDMA-push semantics — incoming data never blocked).
- GCI has a retry latch (`gci_write_held` at 411–417, 725–732): if GCI completion collides with PIU, GCI waits and re-asserts until arbiter accepts.
- FSM COMPUTE writeback loses to both; gets stalled via `ex_dmem_collision`.

**Fail-stop conditions** (line 791–858):
- `invalid_opcode` (`ex_opcode > 4'h3`): P_ERROR, records `error_pc = ex_pc, error_state = 4'd3`.
- `stall_timer ≥ TIMEOUT_MAX`: P_ERROR, same diagnostic.
- `watchdog ≥ WATCHDOG_MAX`: P_ERROR, same diagnostic.

**Design rationale for 2-level forwarding:** the BRAM has read-first behavior (first cycle of read returns the old value). For back-to-back COMPUTEs where cycle N writes address *a* and cycle N+1 reads it, a 1-level forward suffices. But if a 1-cycle scoreboard stall interposes, the cycle-N write ages out of the d1 register. The d2 register captures it one more cycle — enough to survive any single-cycle stall. Any longer stall would be unusual because it means the FSM is blocked on scoreboard, which means something upstream hasn't completed.

### 2.9 `fp64_add.sv` — combinational IEEE 754 FTZ+RNE adder

**Design choices:**
- **Single `always_comb`, no state, no clock.** 242 lines of pure combinational logic.
- **IEEE 754 subset:** FTZ inputs, FTZ outputs, RNE rounding only. Deterministic NaN canonicalization (sign-preserved, bit 51 forced, payload preserved in low 51 bits). Deterministic signed-zero rule: zero result = `+0`.
- **55-bit aligned mantissa arithmetic**: 1 overflow + 1 implicit + 52 fraction + 1 guard = 55 bits. Plus sticky bit.
- **Shift cap at 54 bits**: if exponent difference > 54, small operand's contribution is wholly in sticky.
- **Effective subtract via magnitude compare**: always `m_big ≥ m_small` after routing, so `m_sum = m_big - m_aligned` is non-negative unless the exponents are equal (same-exp subtract case flips sign via twos-complement).
- **Normalize with leading-zero count**: iterate bits 54→0 to find leading 1, then left-shift. Special cases for bit 55 (carry out, shift right 2) and bit 54 (carry out, shift right 1).
- **Rounding** (line 226–232): RNE via `guard && (sticky || lsb)`. If rounding produces mantissa overflow (fraction wraps to 0), increment exponent.
- **Overflow-to-infinity**: if `e_norm >= 11'h7FF`, emit ±Inf with zero fraction.

**Combinational purity = strongest possible determinism for a hardware FADD.** Not just stateless; no procedural state, no latched rounding mode, no exception flags.

### 2.10 `noc_system.sv` — the parametric top

**Design choices:**
- **Single module supports all six topologies** via adjacency-table parameterization.
- **Port 0 convention**: reserved for local NI on every router. One structural rule.
- **Adjacency table is runtime RAM** (line 88–103): `adj_tgt_rtr[router][port]`, `adj_tgt_port[router][port]`. Set via `adj_wr_en`/`adj_rtr_id`/`adj_port_id`/`adj_target_rtr`/`adj_target_port` before `program_start`.
- **Adjacency-driven wiring** (line 258–295): single `always_comb` loop iterates over all (router, port) pairs and routes data + credit based on the table. Forward data: `R.tx[P] → tgt.rx[tp]`. Reverse credit: `tgt.credit_out[tp] → R.credit_in[P]`.
- **`all_done = &cn_done`**: program terminates when every CN's FSM has reached P_DONE.
- **`result = cn_result[RESULT_NODE]`**: which CN's result register holds the root result. Set at instantiation (default 0, but the compiler passes `root_gpu = asgn[0]` for instances where the root tree node isn't on GPU 0).

**`ni_rx_valid[gi] = rtr_tx_valid[gi][0]`** (line 221): the NI's RX is port-0 of router[gi]. This wiring is done outside the adjacency-driven wiring (line 268–273: "Priority 1: Connect local NIs explicitly"). Prevents the adjacency-driven default-assignment from overwriting the NI wiring.

### 2.11 `top_fpga_interactive_g2.sv` / `_g4.sv` — FPGA wrappers

**Design choices:**
- **Parameters hard-coded for specific (N, G, topology)**: G=2 linear, G=4 linear/ring. N=8 for both.
- **VIO-driven leaf input**: physical switches, buttons, and VIOs feed the GCI buffer and trigger program_start.
- **7-segment display of result**: for eyeball validation.
- **UART readback of performance counters**: for quantitative cycle comparison.
- **Compiler-derived constants embedded** (e.g., `G0_SZ = 28`, `G1_SZ = 33`, `ROOT_GPU = 1`): the per-GPU IMEM sizes and root-GPU identity are compile-time constants baked into the FPGA bitstream. A different (N, G) requires a new bitstream.

**Why G=2 and G=4 only:** Artix-7 XC7A100T has ~100K LUTs and ~135 BRAMs. One `btree_fsm_fast` + `noc_ni` + `noc_router` is roughly ~8K LUTs and ~6 BRAMs. At G=4, that's ~32K LUTs + 24 BRAMs — fits comfortably. At G=8 it would be tight; at G=16 you'd need a larger FPGA.

---

## 3. Cross-Cutting Design Decisions

### 3.1 RDMA-push vs. explicit RECV

The design eliminated `OP_RECV` (now `OP_RESERVED`) in favor of autonomous PIU-driven DMEM writes. Rationale:

- **Eliminates a class of deadlocks**: with RECV, a receiver blocked on COMPUTE cannot post RECVs, which stalls the sender. With RDMA-push, the sender is only stalled by credit-based back-pressure (bounded), and the receiver's DMEM is written unconditionally.
- **Reduces instruction count**: each SEND would otherwise be paired with a RECV at the receiver, doubling cross-PE instruction count.
- **Simplifies the ABI**: receiver's COMPUTE instructions don't need to encode RECV order; they just wait for the scoreboard bit to flip.

Trade-off: PIU must always be able to write (hence highest DMEM priority). A malicious or buggy sender cannot corrupt the receiver's DMEM because `target_addr` is part of the packet header and the allocator has reserved the target address.

### 3.2 Scoreboard vs. explicit synchronization

The scoreboard is *the* synchronization primitive. Alternatives considered (implicitly) and rejected:

- **FIFO-based RECV**: requires pairing each SEND with a RECV. Reviewed above.
- **Tag-based barriers**: would need an ISA extension (BARRIER). The ABI doesn't need barriers because the tree structure provides implicit data dependencies.
- **Ordering via NOPs**: the compiler would need to know exact cycle counts. Fragile under RTL changes.

The scoreboard is the minimum mechanism that makes arrival-order irrelevant to the semantics.

### 3.3 Single-flit packets

The choice to use 96-bit single-flit packets constrains the payload to 64 bits. Consequences:

- **Pro**: no head-of-line blocking across flits; each packet is atomic; no mid-packet reassembly at the receiver.
- **Pro**: deadlock analysis is simpler — channel-dependency graphs don't need per-flit tracking.
- **Con**: SIMD workloads (e.g., 512-bit AVX vectors) require multiple SENDs, one per scalar.
- **Decision**: for reduction, one-flit-per-scalar is natural because the reduction binary-tree processes two 64-bit values at a time anyway. SIMD would need a different ISA.

### 3.4 Static compilation vs. dynamic scheduling

Every decision is made at compile time:
- Assignment α fixed by S2.
- Mapping μ fixed by S3.
- Operand binding fixed by S6.
- Schedule timing fixed by S6 (NOPs baked in).
- Routing tables fixed at boot.

No runtime dynamic scheduling. Rationale:
- **Determinism** is trivially inherited from static bindings.
- **Tournament is practical**: 22K configurations can be cycle-modeled without running hardware.
- **Debuggability**: the IMEM is a human-readable trace of exactly what will happen.

Trade-off: no adaptive response to runtime conditions (network congestion, PE failure). For reduction, these are not concerns in the threat model.

### 3.5 Synthetic leaf values from `make_leaf_val`

The formula `(idx+1)*1000.0 + ((idx*37+13)%100)/100.0 + 0.007`:

- **`(idx+1)*1000`**: ensures monotonically-increasing magnitude → exponent alignment during FADD, exercising the alignment + shift path.
- **`((idx*37+13)%100)/100.0`**: adds a pseudo-random fractional part → non-zero mantissa, non-trivial rounding.
- **`+ 0.007`**: 0.007 = 0x3F7CED916872B020 in IEEE 754 — not representable exactly, so every leaf is a non-terminating binary fraction.

The combination ensures that:
1. No two leaves have the same exponent (no degenerate same-magnitude addition).
2. Every FADD exercises guard + sticky + RNE rounding.
3. Reordering would change the last bits — so any bit mismatch between hardware and oracle *must* indicate a determinism violation.

### 3.6 GCI gap of 6 cycles

`gci_gap = gci_latency + 2 = 6`. Why 6?

- `gci_latency = 4`: the GCI state machine counts 0..3 (4 cycles) from `gci_start` to `gci_done`.
- `+1`: `gci_done` pulses one cycle after the counter reaches `GCI_LATENCY - 1`.
- `+1`: DMEM write commits one cycle after `gci_done` (via the GCI→DMEM arbitration path).

This is measured from the RTL, not chosen. The `+2` in `gci_gap = gci_latency + 2` is the RTL-proven adjustment.

### 3.7 IMEM / DMEM depth of 512

Why 512?
- Largest instance: N = 8192, G = 4096, leaves-per-GPU ≈ 2. Peak IMEM ≈ 2 + NOPs ≈ 10. Peak DMEM ≈ 2 + receive buffers ≈ 5.
- For N = 8192, G = 64: leaves-per-GPU = 128. Peak IMEM with GCI gap = 128 × 6 = 768 — over 512! This is where S5 enforcement fires.
- 512 was chosen because on Artix-7, 512 × 64 bits = 32 kbit per memory = exactly 1 BRAM.
- On larger silicon, this would expand to 4096 or more.

### 3.8 Timeout and watchdog thresholds

- `TIMEOUT_MAX = 10000`: stall timer. A continuous EX stall of 10K cycles likely indicates a SEND back-pressure deadlock or a credit leak.
- `WATCHDOG_MAX = 20000`: no-progress timer. 20K cycles with no instruction retired likely indicates a scoreboard stall (missing data) or a pipeline deadlock.

These are generous (for reference, the largest instance runs in ~4K cycles). They exist to catch bugs, not to bound normal operation.

### 3.9 8-bit credit counter in `link_tx`

`RX_BUF_DEPTH = 8` implies max 8 outstanding packets per link. 8-bit counter supports up to 256 buffer depth — future-proofed for deeper FIFOs.

### 3.10 2-VC default

Why 2, not 1 or 4?
- 1 VC: can't implement VC-escape → cyclic topologies deadlock under adversarial schedules.
- 2 VC: minimal for VC-escape. One for non-wrap traffic, one for wrap traffic.
- 4 VC: overkill for this threat model; more buffer area without deadlock benefit.

---

## 4. What Was Deliberately NOT Designed

These choices reveal the scope as sharply as the inclusions do:

- **No multi-flit packets**: scope decision. Would need head-of-line management.
- **No dynamic routing**: static tables only. Deterministic routing is a determinism safeguard.
- **No adaptive routing**: wouldn't help cycle counts on structured workloads.
- **No ECC / error correction**: out of threat model (A2).
- **No multi-clock-domain**: single `clk` across the whole design. Multi-chiplet deployment would add CDC.
- **No wormhole forwarding**: store-and-forward per-VC FIFOs. HoL pressure at high fan-in; a known limitation.
- **No runtime assignment change**: IMEM is static after program_start.
- **No ILP/MILP compiler path**: heuristic-ensemble only. Exact methods would time out at scale.
- **No GPU/TPU/NCCL integration**: research artifact, not a production collective library.
- **No dynamic frequency / voltage scaling**: fixed clock.
- **No multi-reduction scope**: one reduction per program_start. The reserved opcode slot is earmarked for BARRIER/RESET_SB.

---

## 5. The Design's Core Intellectual Move

Every choice above serves **one goal**: making the 64-bit root result a pure function of (N, L, fabric) — nothing else. The mechanisms are:

1. **Compile-time binding** of everything non-deterministic → moved to compiler, deterministic under seed.
2. **Static operand pairing** (addr_a, addr_b = dmem(left), dmem(right)) → ABI contract.
3. **Scoreboard gating** → arrival order invisible to ALU.
4. **Single-writer DMEM discipline** → no write races possible.
5. **Combinational pure FADD** → no internal state.
6. **Fail-stop on violation** → never silently wrong.
7. **Connectivity repair** → ABI's structural prerequisite established.
8. **Seeded stochastic algorithms** → compile-time determinism.
9. **RDMA-push** → eliminates a class of synchronization deadlocks.
10. **Topology as data, not RTL** → the fabric itself doesn't know which topology it's on.

Each item is cheap on its own; the intellectual move is recognizing that *all ten together* are necessary-and-sufficient for the bitwise-invariance property to hold. Remove any one and the guarantee breaks in a specific, predictable way. The paper currently names items 2, 3, 5, and partial 1; the other six are present in the code but not elevated to the argument structure.

---

## 6. Consequences for the Paper

The "Claim 1 via A1–A7" framing in paper_v5 covers about half of the design's actual determinism surface. A faithful framing would have:

- **A set of fabric-local invariants** (items 3, 4, 5, 6 from §5) derivable from RTL inspection.
- **A set of compiler obligations** (items 1, 2, 7, 8) discharged at compile time with runtime asserts.
- **A set of scope decisions** (items 9, 10) that define the fabric family.

The hidden-work inventory (`hidden_work_inventory.md`) is consistent with this structure and identifies the 16 specific items the paper should promote. Items 1–5 in that inventory's §10 ("must be added") are the highest priority.
