# **Peer Review Report**

**Target Publication:** IEEE Transactions on Parallel and Distributed Systems (TPDS)

**Paper Title:** Bitwise-Reproducible Reduction Across Cluster Reshape: A Compiler/Fabric ABI

**Companion Document:** SPRS: Hardware Implementation Reference

## **Section-by-Section Critical Evaluation**

### **1\. Major Scientific and Technical Errors**

* 🔴 **Location:** Main Paper §III.C (F-sb-mono, C-sw), §V.C (Algorithm 1, lines 6–8), §III.E (Argument A2), Companion Doc §III.A  
  **Problem:** Fundamental contradiction between monotone scoreboard bits (F-sb-mono) and address recycling in the DMEM allocator (Algorithm 1).  
  **Why it is a problem:**  
  F-sb-mono explicitly dictates: *"Each scoreboard\[a\] bit transitions $0 \\rightarrow 1$ at most once per program, at the clock edge of the unique write to address $a$, and stays set until the next program-level reset."* Furthermore, C-sw states that every address $a \\neq 0$ is the destination of *exactly one* instruction.  
  However, Algorithm 1 (lines 6–8) explicitly frees child DMEM addresses once consumed by a parent node so they can be recycled. If address $a$ is recycled and written a second time by a parent node $v$:  
  1. It directly violates C-sw (written twice in the emitted IMEM).  
  2. scoreboard\[a\] was set to 1 during the child's write. When parent $v$ is scheduled to write its result to $a$, any dependent reader evaluating $a$ sees scoreboard\[a\] \== 1 *before* parent $v$ completes writeback. The reader will fetch stale child data, causing a data race and non-deterministic corruption.  
  3. Conversely, if address recycling is disabled to preserve C-sw, every node in $FBT(N)$ requires a unique slot. On a PE assigned $M$ nodes, DMEM memory footprint becomes $O(M)$, exceeding the fixed 512-entry DMEM budget for modest problem sizes.  
     **How to fix it:** Eliminate the logical contradiction. If DMEM addresses are unique per node (no recycling), remove the free-list logic from Algorithm 1 and explicitly state that DMEM footprint is bounded by tree node count per PE. If addresses are recycled, you must introduce a RESET\_SB hardware opcode or clear signal to reset scoreboard\[a\] to 0 prior to reuse, update F-sb-mono accordingly, and modify the C-sw definition.  
     **Suggested replacement wording (§III.C / §V.C):**  
* *"Replace Algorithm 1 free-list recycling with static single-assignment (SSA) address mapping where each node $v \\in FBT(N)$ assigned to PE $p$ receives a distinct DMEM slot $a\_v$. Revise §V.C to clarify that DMEM allocation is strictly non-recycling within a single reduction pass to preserve F-sb-mono and C-sw without hardware scoreboard invalidation."*  
* 🔴 **Location:** Main Paper §I, Equation (1), Page 2  
  **Problem:** Mathematical error in Higham's classical bound for floating-point summation non-associativity (missing machine epsilon $u$).  
  **Why it is a problem:**  
  Equation (1) is printed as:  
  $$\\Vert{}\\Sigma a\_i \- \\Sigma a'\_i\\Vert{} \\le (N-1) \\sum\_{i} \\vert{}a\_i\\vert{} \+ O(u^2)$$  
  The unit in last place / machine epsilon factor $u$ (for IEEE 754 binary64, $u \= 2^{-53} \\approx 1.11 \\times 10^{-16}$) is missing from the coefficient $(N-1)$. As written, the equation asserts that reduction reordering error is bounded by $(N-1)$ times the sum of array magnitudes—implying a $100\\%\\times(N-1)$ potential error (e.g., $7,000\\%$ relative error for $N=71$). This is a major mathematical typo in a core foundational formula.  
  **How to fix it:** Insert machine epsilon $u$ into the error bound term.  
  **Suggested replacement wording (§I, Eq. 1):**  
  $$\\Vert{}\\Sigma a\_i \- \\Sigma a'\_i\\Vert{} \\le (N-1) u \\sum\_{i=0}^{N-1} \\vert{}a\_i\\vert{} \+ O(u^2)$$  
* 🟠 **Location:** Companion Doc §II.B vs. Main Paper §IV.C & Fig. 3  
  **Problem:** Direct contradiction regarding which packet bit steers Virtual Channel (VC) selection.  
  **Why it is a problem:**  
  Companion Doc §II.B states: *"Bit 63 of the payload additionally steers the virtual channel..."*  
  Main Paper §IV.C and Fig. 3 state: *"Bit \[64\] is the VC-steering bit... VC selection is a function of a header bit, not any payload bit."*  
  Bit 63 of payload is the sign bit (MSB) of the 64-bit IEEE 754 floating-point payload. If VC selection were steered by payload bit 63, packet routing and virtual channel allocation would depend on whether a floating-point value is positive or negative. This contradicts the main paper's claim that NoC routing and timing are value-agnostic.  
  **How to fix it:** Correct Companion Doc §II.B to consistently reference header bit 64\.  
  **Suggested replacement wording (Companion §II.B):**  
  *"Bit 64 of the packet header (located in the reserved field above the payload) steers the virtual channel, ensuring routing decisions remain strictly independent of the 64-bit FP64 payload."*  
* 🟠 **Location:** Companion Doc §II.A (Instruction word layout)  
  **Problem:** Insufficient bit-width allocation for link selection in the 64-bit instruction word.  
  **Why it is a problem:**  
  Companion §II.A defines \[59:56\] aux as aux\[0\] link, aux\[3:1\]=alu\_op. A 1-bit link field (aux\[0\]) can only select between 2 egress links (0 or 1). However, the NoC router specification (§IV, Table III) explicitly supports up to 8 ports (MAX\_PORTS \= 8), requiring 3 bits ($\\lceil \\log\_2 8 \\rceil \= 3$). A 1-bit link field cannot address ports 2 through 7 in 5-port or 8-port routers.  
  **How to fix it:** Reallocate reserved instruction bits (e.g., from \[7:0\]) or clarify that egress port selection is resolved exclusively via the hardware route\_table\[dest\_gpu\] lookup rather than an explicit instruction field.  
  **Suggested replacement wording (§II.A):**  
  *"For SEND instructions, egress link selection is performed by the router's hardware routing table using dest\_gpu (\[7:0\]); aux\[0\] is unmapped for egress port selection."*

### **2\. Novelty and Contribution**

* 🟠 **Location:** Main Paper §I.C, §III.D, §III.F (Theorem 1\)  
  **Problem:** Overclaiming formal verification status ("Theorem 1") backed by informal code inspection.  
  **Why it is a problem:**  
  The manuscript presents "Theorem 1 (Mapping/topology orthogonality)" with a proof stating: *"Proof. By inspection of build\_schedule and generate\_instructions (§V-E)..."* In an IEEE TPDS paper, labeling Python code inspection as a "Theorem" with a formal "Proof" overclaims mathematical rigor. The authors acknowledge in §III.D that these claims are based on inspection and dynamic SVA assertions rather than machine-checked proofs (e.g., Coq, Isabelle, Lean, Z3).  
  **How to fix it:** Reframe "Theorem 1" as "Proposition 1" or "Property 1 (Structural Orthogonality)", and replace "Proof" with "Structural Argument".  
  **Suggested replacement wording (§III.F):**  
  *"Proposition 1 (Mapping/Topology Structural Orthogonality). Fix $N, L$, assignment $\\alpha$, refinement $r$, and the FADD unit... Structural Argument: By construction of the code generation pipeline (§V-E)..."*  
* 🔵 **Location:** Main Paper §I.D, §V.A, §VIII.A  
  **Problem:** Space spent detailing prior-art heuristic algorithms rather than sharpening the unique ABI contribution.  
  **Why it is a problem:**  
  Section V spends extensive space detailing 18 assignment algorithms (HEFT, Lukes, CPOP), 10 mapping algorithms, and 122 refinement combinations. As the authors admit in §I.D, all of these component algorithms are standard prior art. The core novelty lies in the insight that establishing a size-indexed $FBT(N)$ contract renders the entire compiler optimization space structurally orthogonal to arithmetic results. Detailed descriptions of standard scheduling heuristics dilute the main thesis.  
  **How to fix it:** Condense the descriptions of standard heuristics in §V and explicitly reframe the search space as an evaluation testbed demonstrating invariant result convergence across diverse schedules.

### **3\. Methodology and Reproducibility**

* 🔴 **Location:** Main Paper §IV.I, §VII.C, Companion Doc §V  
  **Problem:** Unvalidated single-cycle combinational FP64 adder implementation on FPGA target.  
  **Why it is a problem:**  
  The design employs a fully combinational, unpipelined 64-bit IEEE 754 adder (fp64\_add.sv). Performing a double-precision addition (mantissa alignment up to 53 bits, 106-bit shift, 54-bit addition, leading-zero detection, normalization shift, and rounding) in a single clock cycle on a Xilinx Artix-7 (XC7A100T) FPGA results in a deep combinational delay path (\~18–28 ns). This restricts maximum clock frequency ($F\_{\\max}$) to \<35 MHz and will fail timing closure at standard operating frequencies. The paper presents no synthesis timing closure reports, $F\_{\\max}$ values, or Worst Negative Slack (WNS) metrics.  
  **How to fix it:** Provide synthesis timing reports for the Artix-7 target (stating achievable clock frequency and WNS). Explicitly clarify in §IV.I that the 1-cycle execution model is an unpipelined simulation abstraction, and discuss how multi-cycle pipelined FPADD units affect scoreboard release latency without altering numerical results.  
* 🟠 **Location:** Main Paper §VI.B, §VII.D, §X  
  **Problem:** Absence of an empirical non-deterministic hardware baseline.  
  **Why it is a problem:**  
  The paper evaluates performance overhead strictly against an analytical lower-bound model ($\\Omega$). It provides no empirical comparison against a standard non-deterministic NoC reduction implementation (e.g., dynamic ring or recursive-doubling reduction running on the identical NoC architecture). Without this, the exact execution time penalty ($\\eta$) paid for enforcing bitwise reproducibility vs. throughput-optimized non-deterministic hardware cannot be empirically isolated.  
  **How to fix it:** Either implement a baseline non-deterministic reduction schedule on the fabric to report empirical $\\eta$, or clearly emphasize this limitation in the main evaluation section (§VII.D) alongside the structural pricing analysis.  
* 🟡 **Location:** Main Paper §IV.I, §VI.D, Companion Doc §VI  
  **Problem:** Unstated coverage gaps caused by fixed 512-entry IMEM/DMEM limits.  
  **Why it is a problem:**  
  IMEM and DMEM capacities are hardcoded to 512 entries per PE. For large reductions ($N=8192$) on small cluster configurations ($G=2$ or $G=4$), each PE must store $N/G \\ge 2048$ nodes, exceeding memory limits and causing compilation failure. Section VI.D lists ranges $N \\in \[8, 8192\]$ and $G \\in \[2, 4096\]$, but does not explicitly outline which $(N, G)$ sub-regions are uncompilable due to memory bounds.  
  **How to fix it:** Add an explicit constraint formula in §VI.D stating that compilation requires $\\max\_{p} \\vert{}\\alpha^{-1}(p)\\vert{} \\le 512$, and include a feasibility grid in Appendix D showing valid $(N, G)$ compilation pairs.

### **4\. Results and Analysis**

* 🟠 **Location:** Main Paper §I.C, §VII.B, Table IV  
  **Problem:** Inconsistent mutant detection metrics between text summary and Table IV.  
  **Why it is a problem:**  
  Section I.C states: *"confirms the oracle is non-vacuous at 107/107 detection."*  
  Section VII.B text states: *"Of the 108 mutants run, 107 reached a verdict and the oracle flagged all 107..."*  
  Table IV lists Addr-sub detection for $N=32$ as 5/6 and for $N=512$ as 5/6.  
  Summing Table IV yields $51/53$ Addr-sub detected and $56/56$ Leaf-corr detected (total $107/109$). Reporting 5/6 in Table IV implies 2 mutants were tested but missed, which contradicts the text claim that 100% of mutants reaching a verdict were detected ($107/107$).  
  **How to fix it:** Reconcile Table IV entries with the text. If 1 mutant in $N=32$ and 1 in $N=512$ timed out / failed to reach a verdict, denote them as 5/5 (1 timeout) in Table IV to ensure consistency across the manuscript.  
* 🟡 **Location:** Main Paper §VI.D, Equation (11) vs. surrounding text  
  **Problem:** Formula discrepancy in synthetic leaf generation specification.  
  **Why it is a problem:**  
  Equation (11) specifies leaf values as:  
  $$L\[i\] \= (i+1) \\cdot 1000.0 \+ \\frac{((i \- 37 \+ 13\) \\bmod 100)}{100} \+ 0.007$$  
  The text immediately following Equation (11) states: *"The additive $((37i \+ 13\) \\bmod 100)/100 \+ 0.007$ term..."*  
  The formula uses $(i \- 37 \+ 13)$, whereas the text references $(37i \+ 13)$.  
  **How to fix it:** Align Equation (11) and the inline text to use the exact same indexing expression.

### **5\. Related Work and Citations**

* 🟡 **Location:** Main Paper §II.C, §IX  
  **Problem:** Missing citations for relevant prior work on deterministic FP summation and NoC in-network reduction.  
  **Why it is a problem:**  
  The background and related work sections omit key references in exact/reproducible floating-point accumulation architectures and NoC-based in-network reduction trees.  
  **How to fix it:** Add citations to:  
  1. Collange et al., *Parallel Exact Summation* (for exact floating-point accumulators).  
  2. SwitchML / NetRec / SPIN literature (for hardware in-network reduction state management).

### **6\. Writing, Presentation, and Formatting**

* 🟡 **Location:** Main Paper §III.C, Page 6  
  **Problem:** Typo in compiler obligation enumeration header.  
  **Why it is a problem:**  
  The first item under Compiler Obligations is printed as C- (Compilation determinism). with the subscript identifier missing.  
  **How to fix it:** Change C- (Compilation determinism). to C-det (Compilation determinism). or C-alg (Compilation determinism)., matching the tag referenced in §III.D.  
* 🟡 **Location:** Main Paper §I.C, §III.D, §III.E, Fig. 2  
  **Problem:** Inconsistent naming for the fail-stop property (Property 1 vs. Property 2).  
  **Why it is a problem:**  
  Section I.C and Figure 2 label the fail-stop guarantee as "Property 2", whereas §III.D header labels it "Property 1 (Fail-stop fabric)".  
  **How to fix it:** Standardize the label across the entire manuscript as **Property 2 (Fail-stop fabric)**.  
* 🟡 **Location:** Companion Doc §II.C  
  **Problem:** Invalid SystemVerilog literal syntax in reference text.  
  **Why it is a problem:**  
  Companion §II.C writes 3'dp when discussing sized literals. In SystemVerilog syntax, 3-bit decimal is specified as 3'd... (e.g., 3'd7). The string 3'dp is syntactically invalid Verilog.  
  **How to fix it:** Replace 3'dp with 3'd... or 3'd0.

### **7\. Hidden Reviewer Objections**

* **Skeptical Reviewer Question 1:**  
  *"How does the SPRS fabric execute multi-step iterative workloads (e.g., thousands of training steps) if scoreboard bits are monotone and never cleared during program execution?"*  
  *Context:* If scoreboard bits transition $0 \\rightarrow 1$ once and are never cleared (F-sb-mono), the fabric as specified can only execute a single reduction pass before requiring a global hardware reset (program\_start). To support production workloads, the authors must explicitly explain how inter-iteration scoreboard clearing or epoch-tagged scoreboarding is handled.  
* **Skeptical Reviewer Question 2:**  
  *"Because the ABI fixes the reduction tree to $FBT(N)$, the dependence depth is locked to $\\lceil \\log\_2 N \\rceil$. For large $N$ (e.g., $N \= 10^7$ gradient elements), how does this approach scale compared to high-arity $k$-ary trees or ring topologies without hitting severe latency degradation?"*  
  *Context:* Reviewers will push back on the efficiency of $FBT(N)$ for massive vector reductions. The paper should emphasize that tensor reductions are executed as $D$ parallel scalar reductions (or vector-tiled $FBT(N)$ trees), where pipeline throughput is bounded by link bandwidth rather than tree latency.

## **Final Verdict**

### **1\. Overall Assessment**

This paper presents a well-structured compiler/fabric co-design approach (SPRS) targeting bitwise-reproducible floating-point reductions across changing cluster sizes and topologies. Framing reduction reproducibility as a size-indexed ABI contract ($FBT(N)$) shared between compiler and NoC fabric is a strong conceptual contribution. The experimental campaign (2,822 RTL-simulated runs, mutation testing, analytical cost modeling) demonstrates rigorous effort.

However, the manuscript currently contains critical logical and technical flaws—most notably a fundamental conflict between monotone scoreboard tracking (F-sb-mono) and address recycling (Algorithm 1), an error in Equation (1), contradictory virtual-channel bit specifications between documents, and unvalidated FPGA timing closure for a single-cycle combinational FP64 adder. These issues must be thoroughly addressed prior to publication.

### **2\. Recommendation**

**Weak Reject** (Reject with encouragement to revise and resubmit).

### **3\. Top 10 Issues to Fix Before Submission**

1. **Resolve Monotone Scoreboard vs. Address Recycling Contradiction (🔴 Critical):** Reconcile Algorithm 1 free-list reuse with F-sb-mono and C-sw. Either enforce unique SSA address mapping or specify explicit scoreboard clearing mechanics.  
2. **Correct Equation (1) Math Error (🔴 Critical):** Insert machine epsilon $u$ into the Higham non-associativity bound in §I.  
3. **Reconcile Virtual Channel Bit Field Discrepancy (🟠 Major):** Standardize Companion Doc §II.B and Main Paper §IV.C/Fig. 3 regarding Bit 64 (header) vs. Bit 63 (payload).  
4. **Fix Single-Cycle FPADD FPGA Timing & Reporting (🔴 Critical / 🟠 Major):** Provide synthesis timing closure reports ($F\_{\\max}$, WNS) for the Artix-7 target, and clarify simulation vs. hardware pipelining assumptions.  
5. **Reframe "Theorem 1" and "Proof" (🟠 Major):** Downgrade formal theorem claims based on code inspection to "Proposition 1" supported by a "Structural Argument".  
6. **Reconcile Mutant Detection Reporting Inconsistencies (🟠 Major):** Align Table IV denominators and text claims regarding the 107/107 mutant detection rate.  
7. **Fix Instruction Encoding Link Field Bit-Width (🟠 Major):** Address the 1-bit link field limitation in Companion §II.A relative to 8-port NoC routers.  
8. **Clarify Memory Constraint Bounds on Feasible $(N, G)$ Pairs (🟡 Minor):** Explicitly document how the 512-entry IMEM/DMEM cap restricts large-$N$ / small-$G$ compilations.  
9. **Standardize Naming Inconsistencies (🟡 Minor):** Fix C- label on page 6, and resolve Property 1 vs. Property 2 naming across sections.  
10. **Correct Leaf Formula Expression Discrepancy (🟡 Minor):** Align Equation (11) (i \- 37 \+ 13\) with text (37i \+ 13\).

### **4\. Acceptance Probability**

* **Current Form:** **15%** (High probability of rejection due to theoretical contradiction in scoreboarding, Equation 1 math typo, and unvalidated FPGA timing).  
* **After Addressing All Top 10 Fixes:** **75–80%** (Strong candidate for acceptance in IEEE TPDS).

### **5\. Reviewer-Style Summary**

> This paper addresses the challenge of non-deterministic floating-point reduction divergence in multi-accelerator clusters under cluster reshaping (changes in node count $G$ or physical topology). The authors propose treating reduction order as a size-indexed compiler/fabric ABI that fixes operand binding to a canonical full binary tree $FBT(N)$. The system is implemented as SPRS, comprising a parametric SystemVerilog NoC with scoreboard-gated execution and a 7-stage scheduling compiler. Across 2,822 cycle-accurate RTL simulations spanning 40 cluster instances, the system achieves zero bit divergence and 100% detection of effective injected fault mutants.

> While the interface co-design perspective is compelling and the evaluation extensive, the paper suffers from critical technical inconsistencies. Specifically, the DMEM allocator's address recycling directly contradicts the monotone scoreboard invariant (F-sb-mono), Equation (1) contains a major mathematical typo omitting machine epsilon, and the hardware evaluation relies on an unpipelined single-cycle FP64 adder on Artix-7 without timing closure verification. Addressing these foundational issues is required before the manuscript can be considered for publication in IEEE TPDS.

## **Pre-Submission Action Plan**

```
[URGENT: Architectural & Theoretical Fixes]
  │
  ├── 1. Fix Scoreboard Monotonicity vs. Address Allocator Logic (§III.C, §V.C)
  │      └── Decision: Enforce non-recycling SSA mapping OR introduce hardware RESET_SB opcode.
  │
  ├── 2. Correct Equation (1) Math Typo (§I)
  │      └── Add machine epsilon 'u' factor: (N-1) * u * \sum |a_i|.
  │
  ├── 3. Reconcile VC Steering Bit Field Specification
  │      └── Fix Companion §II.B to reference Bit 64 (header), matching Main Paper §IV.C.
  │
  └── 4. Validate / Clarify FPGA FP64 Adder Timing & Pipeline Model (§IV.I, Companion §V)
         └── Run Vivado synthesis on Artix-7, report WNS/Fmax, and clarify multi-cycle pipelining.

[HIGH PRIORITY: Framing & Result Reconciliation]
  │
  ├── 5. Reframe "Theorem 1" to "Proposition 1" (§III.F)
  │      └── Replace "Proof by code inspection" with "Structural Argument".
  │
  ├── 6. Reconcile Mutant Detection Statistics
  │      └── Ensure Table IV numbers (5/6 vs 5/5) precisely match the 107/107 text claims.
  │
  └── 7. Resolve Instruction Word Link Field Specification
         └── Update Companion §II.A to explain egress routing via table lookup for >2 port routers.

[MEDIUM PRIORITY: Formatting, Formulas & Terminology]
  │
  ├── 8. Standardize Property & Obligation Naming
  │      └── Rename 'C-' to 'C-det' (§III.C) and standardize 'Property 2' throughout.
  │
  ├── 9. Synchronize Leaf Formula (Eq. 11 vs Text)
  │      └── Align formula string `(i - 37 + 13)` with inline text `(37i + 13)`.
  │
  └── 10. Document Feasible Instance Coverage & Memory Bounds
         └── State explicit constraint \max_p |\alpha^{-1}(p)| <= 512 in §VI.D.
```

