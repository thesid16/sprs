#!/usr/bin/env bash
# One loop iteration. Two invariants:
#  1. ATOMIC: state advances only after a successful git commit, so a kill at any
#     point leaves the tree resumable by simply re-running this script.
#  2. COLD READ: the agent never sees what previous iterations did. It reads only
#     main.tex and the source material. Prior NOTES.md files and loop.log are
#     written for the human record and are explicitly off-limits to the agent, so
#     each pass is an independent judgement rather than a continuation.
set -uo pipefail
M=/home/rohit/sprs-fix/paper_min
cd "$M" || exit 1
GIT="git -c user.email=sp839@snu.edu.in -c user.name=sprs"

IT=$(python3 -c "import json;print(json.load(open('LOOP_STATE.json'))['iteration'])")
# Discard half-finished work from a killed run BEFORE creating this iteration's
# directory -- `git clean -fd` removes untracked dirs, and it used to delete the
# very directory the logs are about to be written into. iterations/ is preserved.
$GIT checkout -- . 2>/dev/null
$GIT clean -qfd -e iterations 2>/dev/null

DN=$(printf %03d "$IT"); D="iterations/$DN"; mkdir -p "$D"

COLD='STRICT: do NOT read anything under iterations/, and do NOT read loop.log or
LOOP_STATE.json. You are a fresh reader with no knowledge of any previous pass. Judge
the paper only as it stands right now. This is deliberate.'

if [ "$IT" = "0" ]; then
PROMPT="You are constructing a MINIMAL research paper from scratch in this directory.

FULL_REFERENCE.tex is the current 35-page manuscript. It is your SOURCE MATERIAL and
must never be edited. Every fact, number, macro and table you use must come from it or
from the data/ and tables/ files it already builds against. Invent nothing.

Write main.tex: the SMALLEST paper that honestly carries this arc, in this order:
  1. problem description
  2. theoretical solution design
  3. the hardware engineering it went into
  4. the software
  5. the major co-run (the evaluation campaign) and its results and analysis
  6. supporting material, stabilised to appendices ONLY where genuinely necessary

CUT AGGRESSIVELY. This is the defining instruction. Remove everything that is not
core. Nothing you cut is lost - it remains in FULL_REFERENCE.tex and can be restored
later if, and only if, a later reader finds its absence to be a defect. The default
is that a cut stays cut. Err on the side of cutting.

Rules:
- Target 8-10 pages.
- The co-run and its analysis must be the LARGEST block. In the 35-page version theory
  outweighs results 887 source lines to 507; correcting that inversion is a main
  purpose of this exercise.
- Write BETTER than the reference, not merely shorter. Where the long version is wordy
  or hedged, say the same thing more directly. Equivalence on substance, improvement
  on prose.
- Reuse the reference preamble, macros and \\input lines so the build works. Prefer
  \\input{tables/...} and existing macros over retyping numbers.
- Do NOT invent numbers. If a claim needs a number you cannot source, omit the claim.
- Keep, as load-bearing and council-settled: Claim 1, Property 2, the cross-topology
  invariance result, the selection rule WITH its held-out interval, the pinned-FBT
  cost WITH its provisional/contention caveat, and the 39-of-40 disclosure.
- It MUST build: run 'make' until 0 undefined refs and 0 undefined control sequences.

Finally write $D/NOTES.md: what you included, and an explicit list of what you cut."
else
PROMPT="You are reviewing a deliberately MINIMAL research paper in this directory.

$COLD

main.tex is the paper. FULL_REFERENCE.tex is a 35-page version of the SAME work: it is
your reference and your source material, and must never be edited. data/ and tables/
hold the generated numbers.

Read main.tex in full, as a referee seeing it for the first time. Then read
FULL_REFERENCE.tex for the material the short version was cut down from.

YOUR TEST, and the only one: on the things that matter most, is main.tex EQUIVALENT to
FULL_REFERENCE.tex? The short paper is meant to say what the long one says about the
important claims, at much smaller size and better written. It was produced by cutting
aggressively, and THE DEFAULT IS THAT A CUT STAYS CUT.

So do not ask 'what would improve this paper'. Ask: 'is anything important in the long
version MISSING or MATERIALLY WEAKER in the short one, such that a competent referee
would call its absence a defect?'

If yes: restore exactly ONE thing - the single most necessary - and restore it
MINIMALLY and BETTER WRITTEN than the original. Do not paste from the reference;
re-express it more compactly.

If no: add NOTHING and say so plainly. That is the expected outcome and a good one.
Most passes should conclude this. Do not pad, do not restore something merely because
it is interesting, and do not restore something just to have acted.

Size guidance, not a limit: the short paper should end up around half the reference or
less. The larger main.tex already is, the higher the bar for restoring anything.

Rules:
- Invent nothing. Every number from FULL_REFERENCE.tex, data/ or tables/.
- It must still build: 0 undefined refs, 0 undefined control sequences.

Finally write $D/NOTES.md: state clearly whether you added anything; if so what and why
its absence was a defect; if not, say the paper is equivalent on what matters and
nothing further is necessary. Give the page count."
fi

echo "=== iteration $IT $(date -Is) ===" >> loop.log
timeout 3600 claude -p "$PROMPT" --model opus \
  --permission-mode acceptEdits \
  --allowedTools "Read Write Edit Grep Glob Bash(make*) Bash(python3*) Bash(pdflatex*) Bash(bibtex*) Bash(ls*) Bash(cat*) Bash(grep*) Bash(sed*)" \
  --disallowedTools "Bash(rm*) Bash(git*)" \
  > "$D/agent.log" 2>&1
RC=$?
echo "  claude rc=$RC" >> loop.log

# A rate-limited pass must NOT consume an iteration. If the agent was cut off by
# quota, revert anything half-done and exit 75; the outer loop sleeps and retries
# this same iteration. Without this the cursor advances on a pass that did no work.
if grep -qiE "session limit|usage limit|rate.?limit|429" "$D/agent.log" 2>/dev/null; then
  if ! $GIT diff --quiet -- main.tex 2>/dev/null; then
    echo "  rate-limited but main.tex changed; keeping the work" >> loop.log
  else
    echo "  RATE-LIMITED with no change; reverting and retrying iteration $IT" >> loop.log
    $GIT checkout -- . 2>/dev/null
    exit 75
  fi
fi

make > "$D/build.log" 2>&1
PAGES=$(pdfinfo main.pdf 2>/dev/null | awk '/^Pages/{print $2}')
[ -z "$PAGES" ] && PAGES=null
echo "  pages=$PAGES" >> loop.log

$GIT add -A >/dev/null 2>&1
$GIT commit -qm "iteration $IT: pages=$PAGES rc=$RC" >/dev/null 2>&1 || true

python3 - "$IT" "$PAGES" "$RC" <<'PY'
import json,sys,datetime
it,pages,rc=int(sys.argv[1]),sys.argv[2],sys.argv[3]
s=json.load(open('LOOP_STATE.json'))
s['history'].append({"iteration":it,"pages":pages,"rc":rc,
                     "utc":datetime.datetime.now(datetime.timezone.utc).isoformat()})
s['iteration']=it+1; s['pages']=pages; s['phase']="REFINE"
s['last_action']=f"iteration {it} complete (pages={pages}, rc={rc})"
s['next_action']=f"iteration {it+1}: cold read, add the single most necessary missing thing"
json.dump(s,open('LOOP_STATE.json','w'),indent=1)
PY
$GIT add LOOP_STATE.json >/dev/null 2>&1
$GIT commit -qm "state -> iteration $((IT+1))" >/dev/null 2>&1 || true
echo "iteration $IT done: pages=$PAGES"
