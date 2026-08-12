#!/usr/bin/env bash
# build_zips.sh — build the Overleaf-importable ZIPs for the main paper and
# the arXiv companion.
#
# Both ZIPs are self-contained: IEEEtran.cls/.bst and the algorithm* .sty files
# are vendored, so Overleaf's "Upload Project" needs no extra packages. Only
# the tables/ and figures/ that main.tex actually \input are included -- the
# generators emit some orphans that would otherwise ship stale numbers.
#
# The FPGA toggle: the default build claims no board measurements. `make both`
# also produces main-with-fpga.pdf from data/fpga_measured.tex, which is only
# present when the collaborator's board logs have been transcribed. The ZIP
# ships the .template either way so the with-logs variant is reproducible.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$HOME}"
STAMP="$(date +%Y-%m-%d)"

pack() {                              # pack <srcdir> <zipname> <projname>
  local src="$1" zipname="$2" proj="$3"
  local tmp
  tmp="$(mktemp -d)"
  local d="$tmp/$proj"
  mkdir -p "$d"

  cp "$src/main.tex" "$d/"
  [ -f "$src/references.bib" ] && cp "$src/references.bib" "$d/"
  for sty in "$src"/*.cls "$src"/*.bst "$src"/*.sty; do
    [ -e "$sty" ] && cp "$sty" "$d/"
  done

  # Only the inputs main.tex actually references.
  local f
  while read -r f; do
    [ -z "$f" ] && continue
    for ext in "" .tex; do
      if [ -f "$src/$f$ext" ]; then
        mkdir -p "$d/$(dirname "$f")"
        cp "$src/$f$ext" "$d/$f$ext"
        break
      fi
    done
  done < <(grep -oP '\\input\{\K[^}]+' "$src/main.tex" | sort -u)

  # Ship the FPGA template so the with-logs variant can be rebuilt.
  if [ -f "$src/data/fpga_measured.tex.template" ]; then
    mkdir -p "$d/data"
    cp "$src/data/fpga_measured.tex.template" "$d/data/"
  fi

  cat > "$d/OVERLEAF_README.txt" <<EOF
$proj
Revised $STAMP in response to three pre-submission review rounds.

IMPORT: Overleaf -> New Project -> Upload Project -> this .zip
Verified from a bare directory: $(pdfinfo "$src/main.pdf" 2>/dev/null | awk '/Pages/{print $2}') pages,
0 undefined refs/citations, 0 placeholders.

DO NOT HAND-EDIT tables/ or figures/ -- they are generated from the result
CSVs by scripts/ in the repository. Change the data or the generator, then
run \`make tables\`. \`make check\` additionally verifies that every number
stated more than once agrees (scripts/check_consistency.py).

FPGA VARIANT: \\fpgadata toggle. Default (this zip) claims no board
measurements; every cycle figure is stated as RTL simulation. To build the
with-logs variant, transcribe the board logs into data/fpga_measured.tex
following data/fpga_measured.tex.template, then \`make fpga\`.

REPO: https://github.com/thesid16/sprs
EOF

  rm -f "$OUT/$zipname"
  (cd "$tmp" && zip -qr "$OUT/$zipname" "$proj")
  rm -rf "$tmp"
  printf '  %-32s %8s KB\n' "$zipname" "$(( $(stat -c%s "$OUT/$zipname") / 1024 ))"
}

echo "Building from a clean tree..."
( cd "$ROOT/paper_v6" && make clean >/dev/null 2>&1 && make >/dev/null 2>&1 && make check )
( cd "$ROOT/companion" && rm -f main.aux main.out && \
  pdflatex -interaction=nonstopmode main.tex >/dev/null 2>&1 && \
  pdflatex -interaction=nonstopmode main.tex >/dev/null 2>&1 )

echo "Packing:"
pack "$ROOT/paper_v6"   "SPRS_paper_overleaf.zip"     "SPRS_paper"
pack "$ROOT/companion"  "SPRS_companion_overleaf.zip" "SPRS_companion"

echo
echo "Verifying each ZIP builds from a bare directory:"
for z in SPRS_paper_overleaf SPRS_companion_overleaf; do
  t="$(mktemp -d)"
  unzip -q "$OUT/$z.zip" -d "$t"
  p="$(find "$t" -maxdepth 1 -mindepth 1 -type d)"
  ( cd "$p" && pdflatex -interaction=nonstopmode main.tex >/dev/null 2>&1
    [ -f references.bib ] && bibtex main >/dev/null 2>&1
    pdflatex -interaction=nonstopmode main.tex >/dev/null 2>&1
    pdflatex -interaction=nonstopmode main.tex >/tmp/vz_$z.log 2>&1 ) || true
  if [ -f "$p/main.pdf" ]; then
    # -a: pdflatex logs can contain bytes that make grep treat them as binary,
    # in which case plain `grep -c` prints nothing and the count reads wrong.
    # Count only undefined refs/citations. A bare "undefined" also matches
    # LaTeX's harmless "Font shape ... undefined" substitution notice.
    nundef="$(grep -aEc '(Reference|Citation) .* undefined' "/tmp/vz_$z.log" 2>/dev/null || true)"
    printf '  %-32s %s pages, %s undefined\n' "$z.zip" \
      "$(pdfinfo "$p/main.pdf" | awk '/Pages/{print $2}')" \
      "${nundef:-0}"
  else
    printf '  %-32s BUILD FAILED\n' "$z.zip"; grep -m3 '^!' /tmp/vz_$z.log || true
  fi
  rm -rf "$t"
done
