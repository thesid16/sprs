# paper_v6 build
#
#   make            build the default (WITHOUT-LOGS) variant
#   make fpga       build the WITH-LOGS variant (needs data/fpga_measured.tex)
#   make both       build both variants
#   make todo       report remaining \todo{} placeholders, grouped by section
#   make tables     regenerate all generated tables from the CSVs
#   make clean      remove build intermediates

MAIN    := main
LATEX   := pdflatex -interaction=nonstopmode -file-line-error
BIBTEX  := bibtex

.PHONY: all fpga both todo tables clean distclean check

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex references.bib $(wildcard tables/*.tex) $(wildcard figures/*)
	$(LATEX) $(MAIN).tex > /dev/null 2>&1 || true
	$(BIBTEX) $(MAIN)    > /dev/null 2>&1 || true
	$(LATEX) $(MAIN).tex > /dev/null 2>&1 || true
	$(LATEX) $(MAIN).tex > build.log 2>&1 || true
	@test -f $(MAIN).pdf || (echo "BUILD FAILED — see build.log"; grep -E '^.*:[0-9]+: ' build.log | head -20; exit 1)
	@echo "built $(MAIN).pdf ($$(pdfinfo $(MAIN).pdf 2>/dev/null | awk '/^Pages/{print $$2}') pages)"
	@$(MAKE) --no-print-directory warn

# WITH-LOGS variant: FPGA table restored, cycle counts read from data/fpga_measured.tex
fpga: $(MAIN).tex
	@test -f data/fpga_measured.tex || (echo "data/fpga_measured.tex missing — cannot build WITH-LOGS variant"; exit 1)
	$(LATEX) "\def\fpgadata{1}\input{$(MAIN).tex}" > /dev/null 2>&1 || true
	$(BIBTEX) $(MAIN) > /dev/null 2>&1 || true
	$(LATEX) "\def\fpgadata{1}\input{$(MAIN).tex}" > /dev/null 2>&1 || true
	$(LATEX) "\def\fpgadata{1}\input{$(MAIN).tex}" > build-fpga.log 2>&1 || true
	@mv $(MAIN).pdf main-with-fpga.pdf
	@echo "built main-with-fpga.pdf"

both: all fpga

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

tables:
	@python3 scripts/gen_tables.py
	@python3 scripts/gen_cost_tables.py
	@python3 scripts/gen_tournament.py
	@python3 scripts/gen_figures.py

# Fail if anything still unresolved — used before submission
check: all
	@n=$$(grep -o '\\todo{' $(MAIN).tex | wc -l); \
	 if [ "$$n" -ne 0 ]; then echo "FAIL: $$n \\todo{} placeholders remain"; exit 1; fi
	@if grep -qE "Citation .* undefined" build.log; then echo "FAIL: undefined citations"; grep -E "Citation .* undefined" build.log | head; exit 1; fi
	@if grep -qE "Reference .* undefined" build.log; then echo "FAIL: undefined references"; grep -E "Reference .* undefined" build.log | head; exit 1; fi
	@if grep -rl "DEFECTIVE" tables/ >/dev/null 2>&1; then echo "FAIL: tables generated from the defective GPU-0 cycle metric:"; grep -rl "DEFECTIVE" tables/; exit 1; fi
	@echo "PASS: no placeholders, no undefined refs or citations"

clean:
	rm -f *.aux *.bbl *.blg *.log *.out *.toc *.lof *.lot *.synctex.gz build*.log

distclean: clean
	rm -f $(MAIN).pdf main-with-fpga.pdf
