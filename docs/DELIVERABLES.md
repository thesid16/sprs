# SPRS — deliverables index

Everything below builds from this tree with no network access and no environment
variables set. `make` in any paper directory produces the PDF; `make check` gates it.

## Papers

| directory | pages | what it is |
|---|---|---|
| `paper_mid/` | 20 | **THE SUBMISSION.** The version to send to TPDS. |
| `paper_canonical/` | 35 | The complete archive. Keeps everything the submission cuts; intended to remain available alongside it (arXiv or a companion). |
| `paper_min/` | 13 | An intermediate minimum, produced by cutting to the smallest defensible paper and then testing that cut with five independent cold reads. Kept for provenance, not for publication. |

All three are consistent with each other on every fact. Where the archive says *more*
than the submission that is by design; where they once *disagreed* — the η
explanation — the archive was corrected.

## Figures

- `paper_mid/figures/MANIFEST.json` — the figure programme: 12 figures, 4 variants
  each. Every entry names the figure's purpose, its data source, and the prose it is
  meant to displace.
- `paper_mid/figures/variants/<id>/{a,b,c,d}.tex` — the variant sources. `a` is the
  one the paper uses; `b`, `c`, `d` are alternates that argue the same point a
  different way. All TikZ/PGFPlots, no bitmaps.
- `paper_mid/figures/GUIDE.html` — the alternates guide: all four variants of every
  figure side by side, with the strategy each takes. Self-contained single file.
- `bash paper_mid/figures/render_variants.sh` — renders every variant to PDF and PNG.
- `python3 paper_mid/scripts/gen_guide.py` — rebuilds the guide from the renders.

The same variant file is `\input` by the paper and rendered for the guide, so what
the guide shows is what the paper typesets. There is no second rendering path.

## Presentation

- `presentation/talk.tex` → `talk.pdf` — Beamer, ~20 minute conference talk. It
  `\input`s the paper's own figure sources, so slides carry the same vectors the
  paper prints, and the same generated macros, so no number on a slide can drift
  from the paper.
- `presentation/talk.md` → `talk.pptx` — the same deck as PowerPoint, via pandoc,
  using the rendered PNGs. Editable.
- `bash presentation/build.sh` — builds both.

## Verification and audit trail

- `paper_mid/READINESS.md` — a seven-dimension audit of the submission, with every
  blocker/major finding adversarially verified before it was reported.
- `paper_mid/SUBMISSION_REVIEW.md` — what was judged to threaten acceptance and what
  was done about it.
- `paper_mid/DEPTH_LEDGER.md` — per-section depth decisions for the 20pp version.
- `paper_mid/scripts/verify_tables.py` — asserts every generated `.tex` is actually
  rewritten by `make tables` and reproduces byte-for-byte. Eleven negative controls,
  each demonstrated to fire.
- `paper_mid/data/council/` — the council verdict records the generated macros cite.

## Known open items

Tracked in `paper_mid/READINESS.md`. The one that gates submission is the page count:
the manuscript is 20 formatted pages and IEEE policy for Transactions regular papers
is understood to cap at 18. **Confirm the current limit on the submission portal
before sending** — the audit's reading of the policy PDF has not been independently
re-verified, and everything about the length plan depends on it.

Five bibliography entries still carry `% TODO verify` markers. Each is a field that
could not be resolved from any source on disk or via Crossref; the markers are left
in deliberately rather than filled with a guess.
