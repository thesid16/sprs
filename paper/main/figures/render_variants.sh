#!/usr/bin/env bash
# Render every figure variant to PDF and PNG for the alternates guide.
# Run from the paper root so that data/ and tables/ resolve exactly as in the build.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
OUT=figures/rendered; mkdir -p "$OUT"
ok=0; fail=0
for v in figures/variants/*/[a-d].tex; do
  id="$(basename "$(dirname "$v")")_$(basename "$v" .tex)"
  if pdflatex -interaction=nonstopmode -halt-on-error -jobname "$OUT/$id" \
       "\def\VARIANT{${v%.tex}}\input{figures/_wrap.tex}" >"$OUT/$id.log" 2>&1; then
    pdftoppm -png -r 150 -singlefile "$OUT/$id.pdf" "$OUT/$id" 2>/dev/null
    ok=$((ok+1)); printf '  ok    %s\n' "$id"
  else
    fail=$((fail+1)); printf '  FAIL  %s (see %s.log)\n' "$id" "$OUT/$id"
  fi
done
rm -f "$OUT"/*.aux "$OUT"/*.log.bak 2>/dev/null
echo "rendered $ok, failed $fail"
[ "$fail" -eq 0 ]
