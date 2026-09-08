# paper_v6 build
#
#   make            build the PDF
#   make todo       report remaining \todo{} placeholders, grouped by section
#   make tables     regenerate all generated tables from the CSVs
#   make clean      remove build intermediates

MAIN    := main
LATEX   := pdflatex -interaction=nonstopmode -file-line-error
BIBTEX  := bibtex

.PHONY: all todo tables clean distclean check verify-tables

all: $(MAIN).pdf

# data/*.tex was omitted here, so editing any of the eight macro files did not
# trigger a rebuild and `check: all` could validate a stale PDF.
$(MAIN).pdf: $(MAIN).tex references.bib $(wildcard tables/*.tex) $(wildcard data/*.tex) $(wildcard figures/*)
	$(LATEX) $(MAIN).tex > /dev/null 2>&1 || true
	$(BIBTEX) $(MAIN)    > /dev/null 2>&1 || true
	$(LATEX) $(MAIN).tex > /dev/null 2>&1 || true
	$(LATEX) $(MAIN).tex > build.log 2>&1 || true
	@test -f $(MAIN).pdf || (echo "BUILD FAILED — see build.log"; grep -E '^.*:[0-9]+: ' build.log | head -20; exit 1)
	@echo "built $(MAIN).pdf ($$(pdfinfo $(MAIN).pdf 2>/dev/null | awk '/^Pages/{print $$2}') pages)"
	@$(MAKE) --no-print-directory warn

# Remaining placeholder count, grouped by the section each falls in.
todo:
	@n=$$(grep -c '\\todo{' $(MAIN).tex); \
	 printf '=== %s todo placeholders remaining ===\n' "$$n"; \
	 awk '/^\\section\{/{s=$$0; gsub(/\\section\{|\}.*/,"",s)} \
	      /\\todo\{/{c[s]++} END{for (k in c) printf "  %-52s %d\n", k, c[k]}' $(MAIN).tex | sort -k2 -rn
	@echo "--- unresolved values (first 25) ---"
	@grep -n '\\todo{' $(MAIN).tex | head -25 | cut -c1-120

# Warnings worth acting on
warn:
	@u=$$(grep -cE "Reference .* undefined" build.log 2>/dev/null || true); \
	 c=$$(grep -cE "Citation .* undefined" build.log 2>/dev/null || true); \
	 o=$$(grep -cE "^Overfull" build.log 2>/dev/null || true); \
	 printf '  undefined refs: %s   undefined citations: %s   overfull boxes: %s\n' \
	        "$${u:-0}" "$${c:-0}" "$${o:-0}"

# ORDER MATTERS.  Two generator pairs collide on the same output file:
#   tables/catalogue.tex  <- gen_tournament.py (winner shares, REFUTED by T15)
#                         <- gen_catalogue.py  (tie-invariant champion-class
#                                               membership -- what main.tex means)
#   tables/dedup.tex      <- gen_tables.py and gen_results_macros.py
# The authoritative generator therefore runs LAST.  Before this ordering existed,
# `make tables` silently reverted tables/catalogue.tex to the withdrawn
# winner-share table while main.tex still cited it as membership; the `check`
# target below now fails on that, so the mistake cannot recur silently.
#
# gen_claim_macros.py runs LAST for a different reason: it validates its
# reconstruction of the canonical reducer against the roots printed in
# tables/invariance.tex, so gen_tables.py must have written that file first.
# It fails the build if the reconstruction does not reproduce all 16 roots.
# Until it was written, data/claim_macros.tex was the one generated .tex in
# this tree with NO generator anywhere -- `make tables` rewrote 27 of 28 and
# scripts/verify_tables.py still reported all 28 reproducing, because it
# diffed that file against its own scratch copy.
tables:
	@python3 scripts/gen_tablestyle.py
	@python3 scripts/gen_tables.py
	@python3 scripts/gen_cost_tables.py
	@python3 scripts/gen_tournament.py
	@python3 scripts/gen_resource.py
	@python3 scripts/gen_coverage.py
	@python3 scripts/gen_figures.py
	@python3 scripts/gen_campaign_macros.py
	@python3 scripts/gen_catalogue.py
	@python3 scripts/gen_results_macros.py
	@python3 scripts/gen_fabric_macros.py
	@python3 scripts/gen_selection.py
	@python3 scripts/gen_wround_macros.py
	@python3 scripts/gen_ksweep.py
	@python3 scripts/gen_assumptions.py
	@python3 scripts/gen_claim_macros.py

# Regenerate every table in a scratch copy and diff against what is committed.
verify-tables:
	@python3 scripts/verify_tables.py

# Fail if anything still unresolved — used before submission
check: all
	@# Scan main.tex AND every generated file it pulls in. Checking main.tex
	@# alone reported PASS while six rows of the invariance table still held
	@# \todo{--}: the placeholders were in tables/, not in the manuscript.
	@files="$(MAIN).tex $$(ls tables/*.tex figures/*.tex data/*.tex 2>/dev/null)"; \
	 n=$$(cat $$files 2>/dev/null | grep -v '^\s*%' | grep -c '\\todo{' || true); \
	 if [ "$${n:-0}" -ne 0 ]; then \
	   printf 'FAIL: %s live todo placeholder(s) remain\n' "$$n"; \
	   grep -n '\\todo{' $$files 2>/dev/null | grep -v ':\s*%' | head; exit 1; fi
	@# A missing build.log made the two guards below silently pass: `grep -q`
	@# on an absent file is simply false. Require it to exist.
	@test -f build.log || { echo "FAIL: build.log missing — run 'make' first (the undefined-ref guards cannot run without it)"; exit 1; }
	@if grep -qE "Citation .* undefined" build.log; then echo "FAIL: undefined citations"; grep -E "Citation .* undefined" build.log | head; exit 1; fi
	@if grep -qE "Reference .* undefined" build.log; then echo "FAIL: undefined references"; grep -E "Reference .* undefined" build.log | head; exit 1; fi
	@# An undefined MACRO is not an undefined reference and was not caught here.
	@# data/campaign_macros.tex was generated but never \input, so six \Sweep*
	@# and \Repair* uses in the pinned-FBT subsection typeset as EMPTY -- the
	@# sentence read "it holds on of them ()" -- through a clean `make check`.
	@if grep -q "Undefined control sequence" build.log; then \
	  echo "FAIL: undefined control sequence(s) -- a macro typeset as nothing:"; \
	  grep -A1 "Undefined control sequence" build.log | head -20; exit 1; fi
	@if grep -rl "DEFECTIVE" tables/ >/dev/null 2>&1; then echo "FAIL: tables generated from the defective GPU-0 cycle metric:"; grep -rl "DEFECTIVE" tables/; exit 1; fi
	@# The stamp above only fires if the generator writes it. gen_tables.py used
	@# to hardcode the defective CSV and stamp nothing, so the guard could not
	@# see it. Check the provenance header directly as well.
	@if grep -rl "^% source.*live_hw_results_p1_unified" tables/ >/dev/null 2>&1; then \
	  echo "FAIL: tables generated from live_hw_results_p1_unified.csv (defective for cycle-derived numbers):"; \
	  grep -rl "^% source.*live_hw_results_p1_unified" tables/; \
	  echo "  -> the generator must resolve its source via hwdata.select()"; exit 1; fi
	@# Every generated file main.tex \input{}s must actually have a generator in
	@# this tree, and the file on disk must be the one that generator produces.
	@# tables/selection.tex was \input with NO generator in paper/scripts/ at all
	@# (its header pointed at /home/rohit/selrule/, outside the release).
	@bash scripts/check_inputs_exist.sh || exit 1
	@python3 scripts/gen_selection.py --check || exit 1
	@# Every generated .tex must be exactly what its generator produces. Three
	@# of them had been hand-edited under a "do not edit by hand" banner, so
	@# `make tables` silently reinstated two claims the council had refuted.
	@python3 scripts/verify_tables.py || exit 1
	@# tables/catalogue.tex must be the tie-invariant champion-class table, not the
	@# winner-share table T15 refuted.  `make tables` used to overwrite it silently.
	@if grep -q 'wins' tables/catalogue.tex; then \
	   echo "FAIL: tables/catalogue.tex is the REFUTED winner-share table (T15)."; \
	   echo "  -> re-run scripts/gen_catalogue.py; gen_tournament.py must not be the last writer"; \
	   exit 1; fi
	@# Numbers stated more than once must agree. A clean LaTeX build does not
	@# imply this: \newcommand{\Foo15} typesets a literal "15" without error,
	@# and a table whose cells sum to 42 in a 40-instance paper builds fine.
	@python3 scripts/check_consistency.py || exit 1
	@echo "PASS: no placeholders, no undefined refs or citations, numbers consistent"

clean:
	@# Remove the PDF too: leaving it made `make clean && make` a no-op when
	@# the PDF was newer than main.tex, so no build.log was produced.
	rm -f *.aux *.bbl *.blg *.log *.out *.toc *.lof *.lot *.synctex.gz build*.log $(MAIN).pdf $(MAIN)-with-fpga.pdf

distclean: clean
	rm -f $(MAIN).pdf main-with-fpga.pdf
