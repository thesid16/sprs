% Bitwise-Reproducible Reduction Across Cluster Reshape
% A Compiler/Fabric ABI

# The same sum, twice, different answers

Reduce the identical bytes on a cluster. Reshape it. Reduce again.

- Floating-point addition is not associative.
- Changing the worker count changes *which operands pair*.
- So the bit pattern changes.

Measured, not asserted: across fourteen world sizes, fourteen distinct roots on identical input.

![](../paper_mid/figures/rendered/f01_premise_a.png)

# Why this matters

- **Debugging** — a run that cannot be reproduced cannot be bisected.
- **Regulation and audit** — "same input, same output" is often a requirement.
- **Elasticity** — cloud clusters reshape by design.

The usual answers: fix the worker count (gives up elasticity), or sort and compensate at every step (costly, and still order-dependent under reshape).

# The idea: name one order, and make it a contract

Fix a canonical reduction tree FBT(N) — heap-indexed, leaves in ascending index order.

The result is defined by the **tree**, not by the machine that walks it.

The compiler must prove it emits that tree; the fabric must refuse to execute anything else.

![](../paper_mid/figures/rendered/f02_canonical_tree_a.png)

# Claim 1 — the root does not depend on the topology

![](../paper_mid/figures/rendered/f03_claim1_a.png)

Routes differ. The reduction DAG does not. The 64-bit root does not.

# The fabric enforces it below the software

![](../paper_mid/figures/rendered/f04_fabric_a.png)

# Property 2 — fail-stop, not wrong-answer

A missing or misrouted operand must **halt** the run.

It must never silently produce a different root — a wrong answer that looks like a right one is the failure mode that matters.

![](../paper_mid/figures/rendered/f05_failstop_a.png)

# The compiler discharges the obligations

![](../paper_mid/figures/rendered/f06_compiler_a.png)

# The campaign

- 2,844 compilations attempted
- 2,822 passing hardware runs
- 39 of 40 instances hardware-validated
- 6 topologies, N from 8 to 8192

The 40th instance elaborates completely; the simulator emits no kernel for it. We report that, and assert no cause.

![](../paper_mid/figures/rendered/f07_campaign_a.png)

# Cross-topology invariance holds

- Every passing configuration yields a single root per instance.
- Mutation testing shows the oracle is not vacuous — reordering *does* change the root, at twelve of the sixteen leaf counts.

![](../paper_mid/figures/rendered/f09_omega_a.png)

# Which algorithm should you actually run?

A portfolio of **four** configurations, run and minimised over:

- 1.0391 mean regret on a topology it never saw (95% CI [1.0025, 1.0885])
- versus 1.0488 for a rule that *conditions* on topology

Ignoring topology beats conditioning on it.

![](../paper_mid/figures/rendered/f10_selection_a.png)

# What it costs, in software

Pre-registered, and unfavourable:

- 2.57x stock `ncclAllReduce` at G=2
- provisional — measured under GPU contention
- about half of it is algorithmic at G=2, not an implementation defect

We pre-registered this comparison before running it, and report the branch we hit.

![](../paper_mid/figures/rendered/f11_export_cost_a.png)

# What we got wrong

Our own FP64 adder had a defect on effective subtraction — and our Python oracle was a transcription of that RTL, so it agreed.

Found by scoring against references **external** to the design: exact rationals and the host FPU.

Zero errors on 160,800 vectors after repair, beside a control that fires on 15,717 of 62,320.

![](../paper_mid/figures/rendered/f12_fp64_defect_a.png)

# Limitations we are not hiding

- No silicon: RTL simulation of a single-chip fabric.
- No measured same-fabric eta at non-power-of-two scale. At power-of-two, eta = 1 is a **theorem**, not a measurement.
- The suite confounds N and G; no cell-level recommendation is derivable.
- The software export is slower than stock NCCL, and we say by how much.

# Takeaway

Reproducibility across reshape is achievable as an **interface contract**: the compiler proves the order, the fabric refuses anything else, and the result stops depending on the shape of the machine.

- Bitwise-identical roots across six topologies.
- Fail-stop rather than silently wrong.
- A four-configuration portfolio that transfers to unseen topologies.
