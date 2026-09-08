#!/usr/bin/env bash
# Build both decks. Beamer reuses the paper's TikZ sources as vectors; the PPTX uses
# the rendered PNGs. Any figure variant not yet authored gets a visible placeholder so
# the decks always build and a gap is obvious on the slide rather than a build failure.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
R=../paper_mid/figures/rendered
mkdir -p "$R"

# Placeholder for any PNG the markdown deck references but that does not exist yet.
PH="$R/_pending.png"
[ -f "$PH" ] || convert -size 900x520 xc:'#f4f2ee' -gravity center \
  -pointsize 26 -fill '#8a8580' -annotate 0 'figure not yet authored' "$PH" 2>/dev/null
# Substituted placeholders are recorded and REMOVED at the end. Leaving one behind
# in figures/rendered/ would make gen_guide.py count it as a genuine render and embed
# it in the alternates guide as though the figure existed.
subbed=0; SUBS=()
for img in $(grep -oE '\.\./paper_mid/figures/rendered/[a-z0-9_]+\.png' talk.md | sort -u); do
  [ -f "$img" ] || { cp "$PH" "$img"; SUBS+=("$img"); subbed=$((subbed+1))
                     echo "  placeholder -> $(basename "$img")"; }
done

echo "== beamer =="
pdflatex -interaction=nonstopmode talk.tex >/dev/null 2>&1
pdflatex -interaction=nonstopmode talk.tex >beamer.log 2>&1
if [ -f talk.pdf ]; then
  echo "  talk.pdf: $(pdfinfo talk.pdf | awk '/^Pages/{print $2}') slides"
  echo "  placeholders on slides: $(pdftotext talk.pdf - 2>/dev/null | grep -c 'not yet authored')"
else
  echo "  FAILED (see beamer.log)"
fi

echo "== pptx =="
if pandoc talk.md -o talk.pptx 2>pptx.log; then
  python3 - <<'PY'
import zipfile
z = zipfile.ZipFile('talk.pptx')
print(f"  talk.pptx: {len([x for x in z.namelist() if x.startswith('ppt/slides/slide')])} slides, "
      f"{len([x for x in z.namelist() if x.startswith('ppt/media/')])} images")
PY
else
  echo "  FAILED:"; head -3 pptx.log | sed 's/^/    /'
fi
if [ "$subbed" -gt 0 ]; then
  for img in "${SUBS[@]}"; do rm -f "$img"; done
  echo "note: $subbed figure(s) missing -- placeholder used for the pptx and then removed"
  echo "      (figures/rendered/ left clean so the guide cannot embed a placeholder)"
fi
exit 0
