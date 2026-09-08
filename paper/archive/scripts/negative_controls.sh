#!/usr/bin/env bash
# negative_controls.sh -- prove that the guards added to `make check` CAN fail.
#
# The recurring defect in this artifact is checking machinery that reports PASS
# no matter what it is fed. Every guard below is therefore given an input it
# MUST reject. A guard that still says OK is itself a bug and is reported as
# "NC FAILED".
#
# Every mutation is made on a scratch COPY of the paper tree, never in place.
set -u
PAPER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${SPRS_ROOT:-$(cd "$PAPER/.." && pwd)}"
SCRATCH="${SPRS_SCRATCH:-${TMPDIR:-/tmp}}"
W=$(mktemp -d "$SCRATCH/sprs_nc_XXXXXX")/paper
rsync -a --exclude '__pycache__' --exclude '*.pdf' --exclude '*.aux' \
      --exclude '*.log' --exclude '*.out' --exclude '*.bbl' --exclude '*.blg' \
      --exclude '.pre-regen-backup' "$PAPER"/ "$W"/
export SPRS_ROOT="$ROOT"
cd "$W" || exit 2

pass=0; fail=0
nc () {  # nc <name> <mutation-cmd> <guard-cmd>
  local name="$1" mut="$2" guard="$3"
  rsync -a --delete --exclude '__pycache__' --exclude '.pre-regen-backup' "$PAPER"/ "$W"/ 2>/dev/null
  # sanity: guard must PASS before the mutation
  if ! ( eval "$guard" ) >/dev/null 2>&1; then
    printf '  NC BROKEN  %-42s guard already fails before mutation\n' "$name"; fail=$((fail+1)); return
  fi
  ( eval "$mut" ) >/dev/null 2>&1
  if ( eval "$guard" ) >/dev/null 2>&1; then
    printf '  NC FAILED  %-42s guard still PASSES on corrupted input\n' "$name"; fail=$((fail+1))
  else
    printf '  NC ok      %-42s guard correctly rejects\n' "$name"; pass=$((pass+1))
  fi
}

echo "negative controls (scratch copy: $W)"

nc "verify_tables: one cycle count altered" \
   "sed -i '0,/^8 & 2 & linear & 44 /s//8 \& 2 \& linear \& 45 /' tables/perinstance_full.tex" \
   "python3 scripts/verify_tables.py"

nc "verify_tables: refuted columns reinstated" \
   "python3 scripts/gen_tournament.py >/dev/null 2>&1; sed -i 's/{@{}rrlrr@{}}/{@{}rrlllrr@{}}/' tables/perinstance_full.tex" \
   "python3 scripts/verify_tables.py"

nc "gen_selection --check: one regret altered" \
   "sed -i 's/38\/39 \& 1.003/38\/39 \& 1.004/' tables/selection.tex" \
   "python3 scripts/gen_selection.py --check"

nc "gen_selection --check: table deleted" \
   "rm -f tables/selection.tex" \
   "python3 scripts/gen_selection.py --check"

nc "catalogue guard: winner-share table reinstated" \
   "python3 scripts/gen_tournament.py >/dev/null 2>&1" \
   "grep -q 'wins' tables/catalogue.tex && exit 1 || exit 0"

nc "input-exists guard: an \\input target removed" \
   "rm -f tables/selection.tex" \
   "bash scripts/check_inputs_exist.sh"


# C5 (unresolved \PENDING) needs its own baseline: main.tex legitimately holds
# five open markers today, so strip those first, confirm the checker then passes,
# and only then inject a sixth.
rsync -a --delete --exclude '__pycache__' --exclude '.pre-regen-backup' "$PAPER"/ "$W"/ 2>/dev/null
sed -i '/^\\PENDING{/,/^}$/d; s/\\PENDING{[^}]*}{[^}]*}//g' main.tex
python3 - <<'PYX'
import re
s=open('main.tex',encoding='utf-8').read()
lines=s.split('\n'); out=[]; skip=False
for ln in lines:
    if ln.lstrip().startswith('\\PENDING') and not ln.lstrip().startswith('\\newcommand'):
        skip=True
    if skip:
        if ln.rstrip().endswith('}'):
            skip=False
        continue
    out.append(ln)
open('main.tex','w',encoding='utf-8').write('\n'.join(out))
PYX
if python3 scripts/check_consistency.py >/dev/null 2>&1; then
  printf '  NC ok      %-42s baseline clean after stripping PENDINGs\n' "C5 baseline"
  pass=$((pass+1))
  printf '\\PENDING{NC}{negative control}\n' >> tables/coverage.tex
  if python3 scripts/check_consistency.py >/dev/null 2>&1; then
    printf '  NC FAILED  %-42s guard still PASSES with an injected PENDING\n' "C5: injected PENDING"
    fail=$((fail+1))
  else
    printf '  NC ok      %-42s guard correctly rejects\n' "C5: injected PENDING"
    pass=$((pass+1))
  fi
else
  printf '  NC BROKEN  %-42s baseline still fails after stripping PENDINGs\n' "C5 baseline"
  fail=$((fail+1))
fi

rsync -a --delete --exclude '__pycache__' --exclude '.pre-regen-backup' "$PAPER"/ "$W"/ 2>/dev/null
echo "  ---- $pass control(s) fired correctly, $fail did not"
rm -rf "$(dirname "$W")"
[ "$fail" -eq 0 ]
