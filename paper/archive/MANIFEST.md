# MANIFEST — canonical paper tree

Built 2026-08-28T04:07:21Z by agent sprs-f-code.

Sources:
  A = /home/rohit/sprs-fix/paper                                   (snapshot manuscript + T17 portability toolchain)
  B = /home/rohit/sprs-review/runs/20260817T230831Z/paper_v7        (v7 manuscript, 7 writer agents; class files)
  W = /home/rohit/sprs-review/runs/20260817T230831Z/council/work    (council records, vendored into data/council/)
  S = /home/rohit/selrule/{build.py,gen_table.py}                   (selection-rule scratch scripts, ported)

Both A and B are left byte-untouched. Verify with the md5 column below.

FILE                                       FROM   MD5                                NOTE
----                                       ----   ---                                ----
algorithmic.sty                            B      793e9d5a71e74e730d97f6bf5d7e2bca   B only / B newer
algorithmicx.sty                           B      ce139c05a983e19ddca355b43e29c395   B only / B newer
algorithm.sty                              B      15763257e50278eef5db1952ccde229c   B only / B newer
algpseudocode.sty                          B      d9077efe6b74c5a094199256af8d7d9a   B only / B newer
data/campaign_macros.tex                   A=B    0d4debfe2f93cede79068930bfbca608   identical in both originals
data/claim_macros.tex                      B      8860f491f8eea2b643493c4c415a006e   B only / B newer
data/council/SELECTION_RULE.json           NEW    b2d45b928452926cbead3a17476272f0   created here
data/council/T01_verify.json               NEW    67a94115cb61745dda8aa21d9852ab02   created here
data/council/T03_verify.json               NEW    a598e9287edfad44d4b15d4ea855071b   created here
data/council/T04_verify.json               NEW    09004354d8dee3904e633f5adad96efb   created here
data/council/T05_verify.json               NEW    90fb116fcdf1e79a3ff5af7a365206d3   created here
data/council/T08_verify.json               NEW    5f0187ed0177c844b5ddc03dfa707947   created here
data/council/T13_verify.json               NEW    6175f996fa846631e6c1608b77ae1a1f   created here
data/council/T15_verify.json               NEW    0af4c93f6ca7593c42a122038e32d407   created here
data/council/T16_verify.json               NEW    a780bfa61b541ff66b88f24afd46b5b5   created here
data/coverage_macros.tex                   B      cc11c92b304b14698bdb56cad92a12da   B only / B newer
data/fabric_macros.tex                     B      fccb9f7f5c3902d213d4c5a8f077ffa8   B only / B newer
data/fpga_measured.tex.template            A      c9029716b38525b28dacf33e7431afd4   A is a strict superset of B (see report E4/E5/E6)
data/mutation_results.json                 A=B    aec2c6c49d35ab426ab7600bf1a11b85   identical in both originals
data/resource_facts.json                   B      5f70b7e43208b9da29b1d60b98d0182e   B only / B newer
data/resource_macros.tex                   B+fix  964b0990e49768bdb7c922755cddcb7b   B content, edited here
data/results_macros.tex                    B      0184b3d81e068f8a546e97c3095151ab   B only / B newer
data/tournament_facts.json                 B      0545a670ea2eff3a09949cdb6d3f1da9   B only / B newer
data/tournament_macros.tex                 B      fdbcf3034d34315cb5bddee067379787   B only / B newer
figures/ng_inflection.tex                  B      81d48cefbb60e85bdf5490540a1147ba   B only / B newer
figures/omega_by_instance.tex              B      efd37ee4f7fb7c1065b2c00116229568   B only / B newer
IEEEtran.bst                               B      7c8250ecf02814ce6ddc0cdbb63df1dd   B only / B newer
IEEEtran.cls                               B      5b2e4fa15b0f7eabb840ebf67df4c0f7   B only / B newer
main.tex                                   B      facb5ea1d47a0dad927a738e04d2cb52   B only / B newer
Makefile                                   B+fix  5fbcf951004505b95c95ca9eb86c0b26   B content, edited here
paper.pdf                                  A=B    f3403a95acb2bda05f19aa12e855dafd   identical in both originals
references.bib                             B      46f3481332157af722a521dc7d74d08e   B only / B newer
scripts/check_consistency.py               A=B    88e87a3a4669367f6545d9ff9cc6cd4d   identical in both originals
scripts/gen_campaign_macros.py             B+fix  960c192d67a624eb7d123986323fcddc   B content, edited here
scripts/gen_catalogue.py                   B+fix  141a63482598559960648d6b2c3d0e29   B content, edited here
scripts/gen_cost_tables.py                 A      a8a135de727bc0626368eef280fb67d5   A is a strict superset of B (see report E4/E5/E6)
scripts/gen_coverage.py                    A=B    d7c64694c069e9ecfc0fc71c6eb33104   identical in both originals
scripts/gen_fabric_macros.py               B+fix  16e48a564aace4d0a7dd8099a489368d   B content, edited here
scripts/gen_figures.py                     A      c8e32f84bd08c5ae5b76319853e74d93   A is a strict superset of B (see report E4/E5/E6)
scripts/gen_ndmodel.py.notused             A=B    6eebe8d6a8d0d2efe7c243ad31faeb31   identical in both originals
scripts/gen_resource.py                    B+fix  a4d0a144cdb7c405b8f3688b5fc11794   B content, edited here
scripts/gen_results_macros.py              B+fix  2eb25c9184e464c8341a95d19cb6c6e7   B content, edited here
scripts/gen_selection.py                   NEW    4d994f92026c2dad752a42013e62d514   created here
scripts/gen_tables.py                      A      bf9f0df4f9f091f3795a003843571e59   A is a strict superset of B (see report E4/E5/E6)
scripts/gen_tournament.py                  A      bb2baf4560ffd1bb753ef68a5fd8b5a5   A is a strict superset of B (see report E4/E5/E6)
scripts/hwdata.py                          A      7262d60164810a06294c6d2261ce920b   A is a strict superset of B (see report E4/E5/E6)
scripts/patch_overhead.py                  A=B    83ec61a687b5c07162b332ad4355cabb   identical in both originals
tables/budget.tex                          B      cd5c4ac34b9541827e2a813298224d81   B only / B newer
tables/catalogue_s2.tex                    B      1c064f3fa260da2e763daa287de747b9   B only / B newer
tables/catalogue_s3.tex                    B      14214a1b09481d70e8d0336a51e74b4e   B only / B newer
tables/catalogue.tex                       B      f1aa0fa549f19dac23eca1087be243b8   B only / B newer
tables/coverage.tex                        B      2d8c18411bfce120995e23b0f179154d   B only / B newer
tables/dedup.tex                           B      394f98ab98ba436dcfb2dbad086b4cfe   B only / B newer
tables/invariance.tex                      B      06aeda938f05dae7d35c7d08c54139ca   B only / B newer
tables/nginflection.tex                    B      63fb0395025d6f852eefddf5ab102929   B only / B newer
tables/omegaratio.tex                      B      93e058ebe88ebf469f0746dcc1587232   B only / B newer
tables/perinstance_full.tex                B      72f7ce893c1924997f37487069c53d6b   B only / B newer
tables/perinstance.tex                     B      7af16422b963668ca6475b7949619100   B only / B newer
tables/radix.tex                           B      db0b11d09d3f3b470cce3e9ba46cef94   B only / B newer
tables/resource.tex                        B      78ceed1c4cbd8f4a8432cfd0c9073ab7   B only / B newer
tables/selbias.tex                         B      5a485b877b77cec66d268c1c517e80bc   B only / B newer
tables/selection.tex                       B      a6e708d2038d20d29a56da97e61e98e7   B only / B newer
tables/suite.tex                           A=B    f41042ddc8e5ff9bbae0db90a012edc4   identical in both originals
tables/walltime.tex                        B      e0bd7f890c891922eb24a6dec49c35d0   B only / B newer
tables/winners_family.tex                  B      31b1ccb775d9055943d0b2a0dddf8304   B only / B newer

## Why each edited / new file is what it is

**scripts/gen_resource.py  (B content + A portability + A measured_radix)**
A's copy silently reverted the council T13/D071 constant `BUF_DEPTH 16 -> 8`,
which would have changed six published resource numbers (per-router subtotal
750,976 -> 598,912 bits for fat-tree, etc.) and dropped the `\BufDepthSim`,
`\BufDepthRtl`, `\XbarBitsFt` macros that B's main.tex uses. B's constants are
therefore kept verbatim. A's two genuine improvements are taken: the
`$SPRS_P1 -> $SPRS_ROOT/data/results -> absolute` resolver, and `measured_radix()`
recomputed from `sprs_core.build_topology` instead of scanning the 326 GB TB
corpus. PROOF the swap is exact: regenerating with the merged script reproduces
B's tables/radix.tex, tables/resource.tex and data/resource_macros.tex with every
number identical; only the two provenance header lines differ.

**data/resource_macros.tex  (regenerated by the merged script)**
Numbers identical to B's; provenance header now names `sprs_core.build_topology`
instead of the unreleased TB corpus.

**Makefile  (A content + two repairs)**
A's version is a strict superset of B's. Added here: the `tables:` target now
also runs `gen_catalogue.py`, `gen_results_macros.py`, `gen_fabric_macros.py`
and `gen_selection.py` (B's Makefile ran none of them although main.tex \input's
all four of their outputs) and runs them LAST, because `gen_tournament.py` and
`gen_catalogue.py` both write `tables/catalogue.tex`. Added to `check:`: every
`\input`ed generated file must exist; `gen_selection.py --check` must reproduce;
`tables/catalogue.tex` must not be the T15-refuted winner-share table.

**scripts/{gen_catalogue,gen_fabric_macros,gen_results_macros,gen_campaign_macros}.py**
Only change: `COUNCIL` now resolves `$SPRS_COUNCIL -> <paper>/data/council ->
author absolute` instead of hardcoding a path outside the release.

**data/council/*.json  (vendored, byte-identical copies from W)**
The nine council records the four generators above read. Copied unmodified;
md5s match W. Without these a referee cannot run those generators at all.

**scripts/gen_selection.py  (NEW; port of /home/rohit/selrule/{build.py,gen_table.py})**
`main.tex` \input's `tables/selection.tex`, whose header named a generator
outside the release. Ported in, with the standard path resolution and without
the numpy/scipy dependency. `python3 scripts/gen_selection.py --check` proves the
committed table reproduces exactly from the released CSVs.

**paper.pdf**
Stale: it is the OLD (snapshot) manuscript, byte-identical in A and B. Kept
because nothing is deleted, but it is NOT the paper this tree builds. The
built artifact is main.pdf.
