# Response to Round-2 Review

**Manuscript:** SPRS — a compiler/fabric ABI for bitwise-reproducible FP64 reduction
**Round-2 recommendation:** Weak Accept (≈40–55%), up from Weak Reject (≈15–20%)

Thank you for the second round. Two things in particular were unusually useful: the
correction in §0, and open questions 1–2, which named a real fork we could not have
closed by re-reading our own prose. Both are now resolved against the RTL, and one of
them turned out to be a substantive error in the paper rather than a wording nit.

Every item below was verified against the source or the measured data before being
changed. Line references are to the revised manuscript.

---

## §0 — The N=200 finding

Noted with thanks, and no action taken beyond what the reviewer already saw:
Definition 3 (canonical leaf enumeration) stands as written, and the N=7 worked
example stays. We had independently reached the same conclusion — that ascending heap
index and left-to-right visual order diverge exactly when N is not a power of two —
which is why the definition was added. It is worth recording that the ambiguity was
real and ours: the Round-1 prose admitted the reading that produced the 1-ULP
mismatch, and only powers of two were worked, so nothing in the paper would have
caught it. The definition now forecloses it.

---

## Priority list

### 1. VC-steering bit — resolved against RTL: **bit 64**

`rtl/noc_router.sv:118` compares `v[VC_W-1:0] == rx_data[p][64 -: VC_W]`. The reviewer's
inference from the stated rationale was correct: bit 63 is the FP64 sign bit, so
steering on it would make contention value-dependent, and the RTL does not.

Companion §IV ("packet bit 63") was the stale line. **Fixed**, and it now
cross-references §II-B so the two cannot drift apart again. The two remaining
mentions of bit 63 in the companion are deliberate — they are the *rationale* for
avoiding it, not claims about where the field sits.

### 2. Fat-tree port count — resolved against RTL: **`MAX_PORTS` is not a cap, and the paper was wrong**

This one was worth the reviewer's insistence on checking. Two findings:

**`MAX_PORTS` is dead code.** It is declared in `rtl/noc_pkg.sv:14` and referenced by
no module in the design. The live quantity is `PORTS_PER_RTR`, which the compiler emits
per instance.

**Radix reaches 66, not 8.** Read back from the `PPR` localparam of every generated
testbench:

| Topology | Radix rule | Radix P | ⌈log₂P⌉ |
|---|---|---|---|
| linear, ring | 2 + local | 3 | 2 |
| mesh, torus | 4 + local | 5 | 3 |
| hypercube | dim + 1 | 3–11 | 2–4 |
| fat-tree | max(5, k+2) | 5–66 | 3–7 |

So the companion's "port numbers above seven" warning was the correct side of the fork,
and it was in fact understated — it said fat-tree "needs four" bits; it needs seven.
Hypercube also exceeds 8 ports at G ≥ 256, which neither document mentioned.

The reviewer's further inference was also right: **Table III understated fat-tree
routers**, and badly, because the crossbar term is O(P²). Table III is now
radix-parametric, generated from the measured `PPR` values, holding route-table depth
at G = 4096 so the columns isolate radix:

| Component | P=5 (mesh/torus) | P=11 (hypercube) | P=66 (fat-tree) |
|---|---|---|---|
| Routing table | 12,288 | 16,384 | 28,672 |
| VC ingress FIFOs | 7,680 | 16,896 | 101,376 |
| Egress FIFOs | 3,840 | 8,448 | 50,688 |
| Crossbar | 2,400 | 11,616 | 418,176 |
| **Per-router** | **26,208** | **53,344** | **598,912** |

A fat-tree router is 23× a mesh router, and 70% of it is crossbar. The old fixed
8-port estimate (≈37,000 bits) was wrong by ~16× at the top of the range.

Changed: new Table II (measured radix), Table III rebuilt, §IV-A "Design Goals",
Appendix A's egress-port paragraph, and companion §II-C/§IV. The paper now states
plainly that a flat crossbar is not what one would build at radix 66, and that we
report it because it is what we simulated.

### 3. Table VIII now sums to 40

Regenerated from the instance manifest as the reviewer suggested, not patched by hand.
The old table was wrong in most cells, not only in the total (mesh was 7 against a true
4; fat-tree 6 against 9). Corrected margins: linear 4, ring 6, mesh 4, torus 10,
fat-tree 9, hypercube 7. The generator asserts both margins equal 40 before emitting.

We also made the §VII-A forward reference true rather than repointing it (finding F):
Appendix D now contains the promised per-instance xsim wall-clock table. It reconciles
exactly to the §VII-A headline — 2,822 passing runs, 821.5 core-h, 99 s median, 5.51 h
longest, 90.0% consumed by the five largest instances — which is now a machine-checked
property rather than a coincidence.

### 4. Appendix E prose — root cause was a silent LaTeX defect

The reviewer was right that this was one drafting error propagated to two places, but
the mechanism was worse than a copy-paste slip, and worth naming because it is a trap
for any numbers-from-data workflow:

```latex
\newcommand{\TournRho15}{0.95}   % does NOT define \TournRho15
```

TeX macro names cannot contain digits. It parses as `\TournRho` followed by a literal
`15`, so `$\rho \approx \TournRho15$` typeset as "ρ ≈ 15" — with no error, no warning,
and a clean build. The same defect produced "median 15… falling to 30", which is why
the two passages were wrong in exactly the same way: they were not copied from each
other, they were both correct source over a broken macro.

Fixed at the generator (cutoffs are spelled: `\TournRhoFifteen`), and both passages now
read from data: "ρ ≈ 0.95", "a median 20%… 10% at K=30". A percent-form macro was added
so the prose does not restate the table's fraction by hand.

### 5. Property numbering — 5 instances, now immune

The reviewer found 3; there were 5. All hardcoded `Claim~1` / `Property~2` in prose are
now `\ref{}`, so the numbers cannot desynchronise from the environments again. The
section heading is now "Claim 1 and the Fail-Stop Property", which does not carry a
number at all.

### 6. §IV-H credit-counter paragraph — copy-edited

The reviewer's reading was correct: two sentences had been merged, leaving `BUF_DEPTH = 8`
as the grammatical subject of "fixes", and the preceding fragment had no verb. Rewritten
as three sentences. The 2-bit-tally-vs-8-bit-balance distinction is preserved — it is
real and load-bearing — but it is now its own sentence rather than an interpolation.

### 7. Definition 5 cross-reference — fixed

`\ref{def:fbt}` → `\ref{def:leafenum}`. Verified in the rendered PDF: Definition 5 now
reads "…canonical leaf enumeration of Definition 3."

### 8. Appendix D wall-clock reference — see item 3

---

## On the reviewer's closing suggestion

> *ideally a script that greps every number that's stated more than once … and diffs
> them against each other, given that's exactly the category where issues keep surfacing*

Built, and wired into `make check` so the build fails on regression:
`paper_v6/scripts/check_consistency.py`. Four checks:

- **C1** — `\newcommand` names containing digits. This is the defect from item 4, and it
  is a hard failure: a clean LaTeX build does not rule it out.
- **C2** — re-adds the cells of every generated table with a Total row and compares. This
  is the defect from item 3.
- **C3** — any number a generated macro already defines that also appears hardcoded in
  prose, so the two can drift.
- **C4** — suite invariants (40 instances, 39 HW-validated, 2,822 passing runs, 821.5
  core-h) re-derived from the data and diffed against the manuscript.

C3 found two live drift risks beyond what the review caught — the campaign totals
(821.5 core-h, 5.51 h) were typed in two places each — now single-sourced from macros.
The whole §VII-A campaign sentence is generated.

`make check` currently passes with one warning (a literal "256" that is coincidental:
G=256 and SHA-256, not the 256 Mbit figure).

---

## Round-1 items the reviewer listed as still open

- **#5 fat-tree ports** — closed, see item 2. It was a real error, not a wording nit.
- **#4 Property numbering** — closed, see item 5.
- **#16 62% vs 61.5%** — closed. Both now come from one macro, emitted at the table's
  own precision (61.5%). The same fix was applied to the family win-share (53.8%),
  which had the identical latent mismatch.
- **#6 measured ND baseline (L1b)** — **unchanged, and still disclosed as the principal
  open gap.** We have not built one, and we would rather state that than ship an
  analytical proxy. The reason is in §VI-B: our cost model cannot distinguish an FBT
  schedule from recursive doubling, so any analytical baseline we could construct
  returns η̂ ≈ 1.00 on every instance — a number that would look like a result and mean
  nothing. A measured baseline needs a second full fabric implementation with
  non-deterministic reduction order, which is a paper of its own. We accept the risk the
  reviewer identifies in (c).

---

## Summary of changes

| Area | Change |
|---|---|
| Table II (new) | Measured router radix by topology, from emitted testbenches |
| Table III | Rebuilt radix-parametric; fat-tree no longer understated ~16× |
| Table VIII | Regenerated from manifest; sums to 40; assertion-gated |
| Table IX (new) | Per-instance xsim wall-clock; reconciles to §VII-A exactly |
| §IV-A, App. A | `MAX_PORTS = 8` claims removed; radix is per-instance |
| §IV-H | Credit-counter paragraph rewritten |
| Appendix E, §X-L6 | Correct ρ and leakage figures; macro defect fixed at source |
| Definition 5 | Cross-reference corrected |
| Throughout | Claim/Property numbers via `\ref`; campaign totals single-sourced |
| Companion §II-C, §IV | VC bit 64; radix corrected to 66 / 7 bits |
| Build | `scripts/check_consistency.py`, gated in `make check` |

No experiment was re-run and no claim changed. Claim 1 and its 2,822 validated
configurations are untouched.
