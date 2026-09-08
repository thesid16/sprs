# CONSOLIDATION REPORT — sprs-f-code

Agent: sprs-f-code (fixer: compiler, tooling, artifact).
Started: (see timestamps below)
Scratch: /home/rohit/expscratch/fcode/
Rule: /home/rohit/sprs-review/snapshot/ is NEVER modified. Every edited file gets a .bak.

STATUS: IN PROGRESS

---

## TASK 1 — SETTLE THE CANONICAL PAPER TREE

### Evidence gathered (all by execution)

Names used below: **A** = `/home/rohit/sprs-fix/paper`, **B** = `/home/rohit/sprs-review/runs/20260817T230831Z/paper_v7`.

**E1. A's `main.tex` is byte-identical to the frozen snapshot; B's is the only newer manuscript in existence.**

```
$ md5sum snapshot/paper/main.tex A/main.tex B/main.tex
dc41d97d3786b2533d51c4a3258c6017  /home/rohit/sprs-review/snapshot/paper/main.tex
dc41d97d3786b2533d51c4a3258c6017  /home/rohit/sprs-fix/paper/main.tex
facb5ea1d47a0dad927a738e04d2cb52  .../paper_v7/main.tex
```
Every other `main.tex` on the machine (`tournament_portable/paper_writing/paper_v6`,
`t17scratch/{fix,clean,regen}/paper`) is also `dc41d97d`. So B's manuscript is unique
and newest (mtime 2026-08-27 04:07). **Manuscript: B wins, no contest.**

**E2. The toolchain is NOT uniformly newer in A. A regressed one published number.**

`diff -u B/scripts/gen_resource.py A/scripts/gen_resource.py` shows A dropped B's
council-verdict fix:
```
-# ... every emitted testbench overrides it with .RTR_BUF_DEPTH(16) at
-# src/sprs_core.py:5430 ... Council verdict T13/D071.
-NUM_VCS, BUF_DEPTH, FLIT_W, RT_DEPTH = 2, 16, 96, 4096
-BUF_DEPTH_RTL_DEFAULT = 8
+NUM_VCS, BUF_DEPTH, FLIT_W, RT_DEPTH = 2, 8, 96, 4096
```
Consequence, `diff B/tables/resource.tex A/tables/resource.tex`:
per-router subtotal **37,728 -> 26,208** (mesh/torus), **78,688 -> 53,344** (hypercube),
**750,976 -> 598,912** (fat-tree); `\RouterBitsLo` 37,728 -> 26,208, `\XbarShareFt`
56% -> 70%, `\AggFtMbit` 3002.3 -> 2394.3, `\AggLoMbit` 147 -> 102, `\RouterBlowup` 20 -> 23.
A also stops emitting `\BufDepthSim`, `\BufDepthRtl`, `\XbarBitsFt`; B's `main.tex`
uses `\BufDepthSim` 3x and `\BufDepthRtl` 2x, so adopting A's file wholesale would
*also* break the build with undefined control sequences.
**Adopting A's `gen_resource.py` wholesale is a Rule-4 violation. Rejected.**

**E3. A's T17 corpus-free `measured_radix()` is numerically exact — proven, not asserted.**
`diff B/tables/radix.tex A/tables/radix.tex` differs ONLY in the two provenance
header lines; every radix number is identical. B's numbers came from scanning the
326 GB TB corpus; A's came from `sprs_core.build_topology`. So the T17 replacement
reproduces the corpus result bit-for-bit and can be adopted safely.

**E4. A's portability layer is a pure superset for five scripts.**
`hwdata.py`, `gen_cost_tables.py`, `gen_figures.py`, `gen_tournament.py` each differ
from B by exactly 696 bytes: the `_p1_default()` env->repo-relative->absolute block
and nothing else (verified by full `diff -u`, single hunk each).
**Adopt A for these four.**

**E5. `gen_tables.py`: A strictly dominates B.** Both trees received the same
`hwdata.select()` fix today, independently. A's version additionally carries the T17
`canonical_roots()` (recomputed from `src/sprs_core.py` instead of scanning the TB
corpus), the `SPRS_MAXP_CSV` override, and the mutation-JSON path fix.
**Adopt A.**

**E6. A's `Makefile` is a strict superset of B's** (adds `fpga`/`both` targets, runs
`gen_campaign_macros.py` in `tables`, adds the `% source ... live_hw_results_p1_unified`
provenance guard to `check`). Caveat recorded: B's `main.tex` deleted the
`\ifdefined\fpgadata` conditional, so `make fpga` is now dead weight — it fails loudly
on the missing `data/fpga_measured.tex`, which is honest, so it is kept.
**Adopt A.**

**E7. Two files are byte-identical in both trees**: `scripts/check_consistency.py`
and `scripts/gen_campaign_macros.py` (+ `data/campaign_macros.tex`). Note that
`check_consistency.py` ALREADY implements check C5 = "fail on any live `\PENDING`"
(`scripts/check_consistency.py:212-241`), i.e. the role file's FIX 5 is already done
in both trees. Verified below by running it.

**E8. NEW DEFECT FOUND — two generator pairs collide on the same output file, and
`make tables` in B silently reverts the manuscript's own tables.**
Writer map (`grep -oE '(data|tables)/[a-z_0-9]+\.tex'` over every generator):

| output | written by |
|---|---|
| `tables/catalogue.tex` | `gen_catalogue.py` (B-only, tie-invariant class membership) **and** `gen_tournament.py` (arrival-order "wins") |
| `tables/dedup.tex` | `gen_results_macros.py` (B-only) **and** `gen_tables.py` |

B's `Makefile` `tables:` target runs `gen_tables.py`, `gen_cost_tables.py`,
`gen_tournament.py`, `gen_resource.py`, `gen_coverage.py`, `gen_figures.py` — it does
**not** run `gen_catalogue.py`, `gen_fabric_macros.py` or `gen_results_macros.py`, yet
`main.tex` `\input`s all four of their outputs. So in B, `make tables` overwrites
`tables/catalogue.tex` with the *withdrawn* winner-share table (T15 refuted it) and
`tables/dedup.tex` with `gen_tables.py`'s version, while `data/{claim,fabric,results}_macros.tex`
and `tables/selection.tex` are never regenerated at all.

**E9. `tables/selection.tex` has NO generator inside either paper tree.** Its header
says `Generator : /home/rohit/selrule/gen_table.py`, outside the artifact.

**E10. Three B-only generators read an absolute path outside the artifact**
(`COUNCIL = "/home/rohit/sprs-review/runs/20260817T230831Z/council/work"` at
`gen_catalogue.py:13`, `gen_fabric_macros.py:25`, `gen_results_macros.py:28`), with no
env override and no repo-relative fallback. `gen_campaign_macros.py:30` does the same
but at least honours `$SPRS_COUNCIL`.

### Decision

**Canonical tree = B's manuscript + B's class files + B-exclusive generators,
overlaid with A's portability/T17 toolchain wherever A is a strict superset,
with `gen_resource.py` merged by hand (B's constants + A's portability + A's
`measured_radix`), plus the E8/E9/E10 defects repaired.**

**Path: `/home/rohit/sprs-fix/paper_canonical/`.** Justified because (a) it must live
inside the artifact root `/home/rohit/sprs-fix/` for the repo-relative resolver
`scripts/../.. -> $ROOT/data/results` to find the released dataset (verified:
`/home/rohit/sprs-fix/data/results/` exists via the `data -> results` symlink and holds
all three campaign CSVs); (b) it is a new path, so both originals stay byte-untouched
as required.

### Build + verification of the canonical tree

Built at **`/home/rohit/sprs-fix/paper_canonical/`**. MANIFEST (per-file provenance +
md5 + rationale): `/home/rohit/sprs-fix/paper_canonical/MANIFEST.md`.

```
$ cd /home/rohit/sprs-fix/paper_canonical
$ env -u SPRS_ROOT -u SPRS_P1 -u SPRS_COUNCIL make
built main.pdf (32 pages)
  undefined refs: 0   undefined citations: 0   overfull boxes: 4
```

**No published number changed.** Proof:
```
$ pdftotext -layout paper_v7/main.pdf B.txt; pdftotext -layout paper_canonical/main.pdf C.txt
$ diff B.txt C.txt   ->   (no output)   PDF TEXT IDENTICAL, 32 pages both
```

```
$ env -u SPRS_ROOT -u SPRS_P1 -u SPRS_COUNCIL make check
OK: tables/selection.tex reproduces exactly (39 instances, 2822 passing HW rows)
  FAIL  C5 main.tex:192:  unresolved \PENDING marker -- \PENDING{W2}{pinned-FBT ...
  FAIL  C5 main.tex:1977: unresolved \PENDING marker -- \PENDING{W3}{fp64\_add ...
  FAIL  C5 main.tex:2636: unresolved \PENDING marker -- \PENDING{W1/W4/W7}{...
  FAIL  C5 main.tex:3031: unresolved \PENDING marker -- \PENDING{W2}{...
  FAIL  C5 main.tex:3504: unresolved \PENDING marker -- \PENDING{W2}{...
  warn  C3 ... (10 warnings, see TASK 4)
check_consistency: 5 hard failure(s), 10 warning(s)
make: *** [Makefile:106: check] Error 1
```
**`make check` fails on exactly the 5 \PENDING markers and nothing else** — as
required. Every new guard passed. (Role-file FIX 5 turned out to be already
implemented: `scripts/check_consistency.py:212-241` check C5, present and identical
in BOTH original trees; it is what produces the five FAIL lines above.)

### Repairs made while consolidating (each with a failing pre-state)

**R1 — `gen_resource.py` merged, not copied.** Pre-state: copying A's file
regenerates `tables/resource.tex` with per-router subtotals 26,208 / 53,344 /
598,912 instead of the published 37,728 / 78,688 / 750,976, and drops
`\BufDepthSim`/`\BufDepthRtl` which B's main.tex uses 3x/2x -> undefined control
sequence. Post-state: merged script regenerates all three outputs with every number
identical to B, differing only in the two provenance header lines (`diff` shown in
MANIFEST). Verified with **no env vars set** and **without the 326 GB TB corpus**.

**R2 — `tables/selection.tex` had no generator in the artifact.**
Pre-state: `grep -l 'selection.tex' paper*/scripts/*.py` -> nothing; the file's own
header names `/home/rohit/selrule/gen_table.py`, outside the release.
Post-state: `scripts/gen_selection.py` (ported from
`/home/rohit/selrule/{build.py,gen_table.py}`, numpy/scipy dependency removed):
```
$ env -u SPRS_ROOT -u SPRS_P1 python3 scripts/gen_selection.py --check
OK: tables/selection.tex reproduces exactly (39 instances, 2822 passing HW rows)
```
NEGATIVE CONTROL for R2 is in TASK 3 below.

**R3 — `make tables` silently reverted the manuscript's own catalogue table.**
Pre-state (in B, unfixed): `tables/catalogue.tex` holds tie-invariant champion-class
membership from `gen_catalogue.py`; `make tables` runs `gen_tournament.py`, which
overwrites it with the T15-refuted arrival-order winner shares, and `gen_catalogue.py`
is never run. Post-state: ordering fixed in the `tables:` target, plus a `check`
guard that greps `tables/catalogue.tex` for the winner-share header. NEGATIVE
CONTROL in TASK 3.

**R4 — 4 generators hardcoded a council path outside the release.**
`gen_catalogue.py:13`, `gen_fabric_macros.py:25`, `gen_results_macros.py:28` had no
env override at all; `gen_campaign_macros.py:30` honoured `$SPRS_COUNCIL` but had no
repo-relative fallback. Fixed to the standard 3-step resolver; the 9 JSONs they read
are vendored byte-identically into `data/council/`.

### Files NOT carried over, and why

* A's `main.tex` (= frozen snapshot manuscript) — superseded by B.
* A's `gen_resource.py` verbatim — see R1 (would change published numbers).
* A's `\ifdefined\fpgadata` machinery is retained in the Makefile (`make fpga`,
  `make both`) but B's `main.tex` deleted every `\ifdefined\fpgadata` block, so
  those targets now only fail loudly on the missing `data/fpga_measured.tex`.
  Recorded, not silently dropped.
* `paper.pdf` (554,923 B, identical in A and B) is the OLD manuscript. Kept
  (nothing is deleted) but flagged in the MANIFEST as not what this tree builds.

### Originals preserved — verified

```
$ find /home/rohit/sprs-fix/paper -newermt '2026-08-28 09:25' -type f      -> (empty)
$ find .../paper_v7               -newermt '2026-08-28 09:25' -type f      -> (empty)
$ python3 /home/rohit/sprs-review/verify_snapshot.py
snapshot 95633cc6c354eee5 intact (171 files)
```

---

## TASK 2 — SELECTION-RULE GENERALIZATION ESTIMATE

(not started)

---

## TASK 3 — ARTIFACT REPRODUCIBILITY FROM A FRESH CHECKOUT

Fresh checkout at **`/home/rohit/expscratch/fcode/fresh/`** — `src/ benchmarks/
results/ tools/ rtl/ analysis/ companion/ docs/ fpga/ logs/ tests/checkers/
README.md requirements.txt MANIFEST.json`, the release's `data -> results`
symlink, and `paper/` = the canonical tree. Every command below was run with
**`env -i`** (no `SPRS_ROOT`, no `SPRS_P1`, no `SPRS_COUNCIL`, no `VIVADO_BIN`,
nothing inherited but `HOME`, `PATH`, `LANG`).

### What a referee actually experiences

| command | result |
|---|---|
| `make tables` | **rc=0** — regenerates all 27 generated `.tex` from the released CSVs |
| `make` | **rc=0** — `built main.pdf (32 pages)`, `undefined refs: 0  undefined citations: 0` |
| `make check` | **rc=2** — fails on the 5 `\PENDING` markers and nothing else |
| `make verify-tables` | **rc=0** — `OK: all 27 generated .tex files reproduce from their generators` |
| `tools/verify_numbers.py` | **rc=0** — `all 13 claims reproduce` |
| `tools/smoke_test.sh` | **rc=0** — `SMOKE TEST PASSED`, steps 1-5 all `[PASS]` |

And the strongest result available: after `make tables` regenerated everything
from scratch in the fresh checkout, `make` produced a PDF whose extracted text is
**byte-identical** to `paper_v7/main.pdf`:
```
$ pdftotext -layout fresh/paper/main.pdf Fresh.txt
$ diff paper_v7.txt Fresh.txt   ->  (no output)
```
So the shipped 32-page manuscript is fully regenerable from the released data.

Logs: `/home/rohit/expscratch/fcode/{fresh_tables.log,fresh_make.log,fresh_check.log}`.

### Defects found, and disposition

| # | defect | fixed? |
|---|---|---|
| D1 | `tables/selection.tex` is `\input` by `main.tex` but **no generator for it exists in the artifact**; its header names `/home/rohit/selrule/gen_table.py`, outside the release. | **FIXED** — ported to `paper/scripts/gen_selection.py`; `--check` proves byte-reproduction |
| D2 | `gen_catalogue.py:13`, `gen_fabric_macros.py:25`, `gen_results_macros.py:28` hardcode `COUNCIL=/home/rohit/sprs-review/runs/.../council/work`, with **no env override and no fallback**; the JSONs they read are not in the release, so these three generators cannot run for anyone but the author. | **FIXED** — 3-step resolver + the 9 JSONs vendored byte-identically to `paper/data/council/` |
| D3 | `gen_campaign_macros.py:30` honours `$SPRS_COUNCIL` but has no repo-relative fallback. | **FIXED** — same resolver |
| D4 | `make tables` **silently reinstated two claims the council refuted**: `gen_tournament.py` overwrote `tables/catalogue.tex` (tie-invariant membership -> arrival-order winner shares, T15) and `tables/perinstance_full.tex` (T15-deleted assignment/mapping columns came back). `gen_catalogue.py`, `gen_results_macros.py`, `gen_fabric_macros.py` were never run by any target although `main.tex` `\input`s all their outputs. | **FIXED** — `tables:` target now runs all generators, authoritative one last; `gen_tournament.py` no longer emits the refuted columns; `make check` gains a guard |
| D5 | Three generated `.tex` had been **hand-edited under their own "GENERATED — do not edit by hand" banner** (`perinstance_full.tex`, `catalogue.tex`, `selection.tex`), and nothing detected it. | **FIXED** — new `scripts/verify_tables.py` regenerates the whole tree in a scratch copy and diffs; wired into `make check` and `make verify-tables` |
| D6 | `tools/smoke_test.sh:105` wrote its log to the fixed world-writable path `/tmp/_vn.log` — a collision and a symlink-follow hazard on a shared machine, and it can read another user's leftover file. | **FIXED** — `mktemp` under `$TMPDIR` |
| D7 | `gen_resource.py` (in the `sprs-fix` copy) had regressed `BUF_DEPTH` 16->8. | **FIXED** — see TASK 1 / R1 |

### Already fixed by earlier agents — verified here by execution, not assumed

* **`P1` / `MAXP_CSV` hardcoding (role FIX 3).** `grep -rn '/home/rohit' src tools rtl analysis companion fpga benchmarks` over the fresh checkout returns **nothing**. The only remaining absolute defaults are `VIVADO_BIN` fallbacks (`tools/smoke_test.sh:121`, `src/sprs_tournament.py:66`), both already `${VIVADO_BIN:-...}` / `os.environ.get("VIVADO_BIN", ...)`.
* **`BASE_DIR = SPRS_ROOT` (`src/sprs_tournament.py:85`)** — present, with the explanatory comment.
* **`verify_numbers.py` silently dropping to 10 checks (role FIX 2).** NEGATIVE CONTROL run here: hide `data/mutation` and it now prints
  `REQUIRED INPUT MISSING -- refusing to report on partial data: ... 2 required input(s) missing; 0 of 13 claims checked.` and exits 2. It can fail.
* **`smoke_test.sh` step 4 (role FIX 2).** Now prints an OBSERVED root next to the EXPECTED one, from `tools/exec_image.py` executing the emitted image:
  `G=4 hypercube observed 0x41201D1FCED91687 expected 0x41201D1FCED91687 compute=31 send=3 gen=32` — four configurations, one root. Standing negative control cited at `tools/smoke_test.sh:63`.
* **`validate_abi.py` and the C-leaf checker (role FIX 4).** Both present and both self-negative-controlling: `ABI holds over 20 configurations / 7788 COMPUTEs; all negative controls fire.` and `C-leaf holds over 3744 bindings; negative control fires.`

### Residual, NOT fixed

* If the dataset is genuinely absent, `_p1_default()` falls back to the author's
  absolute path. On this machine that path exists, so the fallback can mask a
  missing dataset *here*; on a referee's machine it does not exist and the
  generators die loudly and immediately —
  `SPRS_P1=/nonexistent make tables` -> `FileNotFoundError: .../live_hw_results_p1_maxpe.csv`, rc=2.
  Acceptable, but it is a fallback that behaves differently on the author's machine.
* `tools/smoke_test.sh` step 3 writes `smoke_tb.sv` into the repo root and does
  not clean it up. Cosmetic; left alone.
* `paper/paper.pdf` ships the OLD manuscript. Flagged in the MANIFEST, not deleted.

### Negative controls for every guard added in TASKS 1 and 3

`/home/rohit/sprs-fix/paper_canonical/scripts/negative_controls.sh`
(log: `/home/rohit/expscratch/fcode/negative_controls.log`). Each guard is first
required to PASS on the clean tree, then fed input it must reject:

```
  NC ok      verify_tables: one cycle count altered     guard correctly rejects
  NC ok      verify_tables: refuted columns reinstated  guard correctly rejects
  NC ok      gen_selection --check: one regret altered  guard correctly rejects
  NC ok      gen_selection --check: table deleted       guard correctly rejects
  NC ok      catalogue guard: winner-share table reinstated guard correctly rejects
  NC ok      input-exists guard: an \input target removed guard correctly rejects
  NC ok      C5 baseline                                baseline clean after stripping PENDINGs
  NC ok      C5: injected PENDING                       guard correctly rejects
  ---- 8 control(s) fired correctly, 0 did not
```
The "C5 baseline" line is also the POSITIVE control for TASK 1's requirement:
with the five `\PENDING` markers stripped, `check_consistency.py` exits 0, i.e.
they really are the only hard failures left.

---

## TASK 4 — MECHANICAL HYGIENE

(not started)

---

## LAUNCHED JOBS / STATUS FILES

(none yet)
