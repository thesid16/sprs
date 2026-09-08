#!/usr/bin/env bash
# Every \input{tables/..}, \input{data/..}, \input{figures/..} in main.tex must
# name a file that exists. LaTeX itself only warns, and with
# -interaction=nonstopmode it produces a PDF with the block silently missing.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2
rc=0
for f in $(grep -ohE '\\input\{(tables|data|figures)/[a-z_0-9]+\}' main.tex \
           | sed -E 's/.*\{(.*)\}/\1/' | sort -u); do
  if [ ! -f "$f.tex" ]; then
    echo "FAIL: main.tex \\input{$f} but $f.tex does not exist"
    rc=1
  fi
done
exit $rc
