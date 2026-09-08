#!/usr/bin/env python3
r"""
check_consistency.py — cross-check every number the paper states more than once.

Motivated by the Round-2 review, which found (a) a coverage table whose cells
summed to 42 in a 40-instance paper, and (b) prose that printed "15" where a
correlation coefficient belonged. Both were mechanical and both survived a
clean LaTeX build, because neither is a LaTeX error. This script catches that
class directly.

Checks, in order of how badly each has actually bitten us:

  C1  macro names containing digits
      \newcommand{\TournRho15}{0.95} does NOT define \TournRho15. TeX reads
      the name as \TournRho and leaves "15" in the document, so the macro
      silently typesets the wrong number. This is a hard error.

  C2  table arithmetic
      For every generated tabular with a Total row/column, re-add the cells
      and compare.

  C3  duplicated literals
      Any number that a generated macro already defines, but which also
      appears hardcoded in the prose, is a drift risk: report it so it can
      be replaced by the macro.

  C4  suite invariants
      Fixed facts (40 instances, 39 HW-validated, 2822 passing runs, ...)
      re-derived from the data and compared against what the .tex says.

  C5  unresolved placeholders
      \PENDING{...} marks a claim whose supporting work is not finished. A
      manuscript containing one builds cleanly and typesets whatever the
      placeholder body happens to say, so nothing else catches it. Any live
      \PENDING is a HARD failure here, which is what stops a draft from being
      built for submission with an open placeholder. Two escapes exist and are
      deliberate: a commented-out line is ignored (it is not live), and the
      \newcommand that DEFINES \PENDING is ignored (it is the definition, not
      a use). Set SPRS_ALLOW_PENDING=1 to downgrade C5 to a warning while a
      draft is still being written; `make check` must never set it.

Exit status is non-zero if any hard check fails, so `make check` can gate on it.
"""
import glob
import json
import os
import re
import sys

TEX = ["main.tex"] + sorted(glob.glob("tables/*.tex")) + sorted(glob.glob("data/*.tex"))
HARD, SOFT = [], []


def read(p):
    try:
        return open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def strip_comments(s):
    return re.sub(r"(?<!\\)%.*", "", s)


# ---------------------------------------------------------------- C1
def c1_macro_digits():
    bad = []
    for p in TEX:
        for m in re.finditer(r"\\(?:re)?newcommand\s*\{?\s*\\([A-Za-z]*[0-9][A-Za-z0-9]*)",
                             strip_comments(read(p))):
            bad.append((p, m.group(1)))
    for p, name in bad:
        HARD.append(f"C1 {p}: \\newcommand{{\\{name}}} — macro name contains a "
                    f"digit; TeX will not define this name and the digits will "
                    f"typeset as literal text")
    return not bad


# ---------------------------------------------------------------- C2
def _cells(line):
    line = line.strip().rstrip("\\").strip()
    out = []
    for c in line.split("&"):
        c = re.sub(r"\\(textbf|mathbf|sv|texttt|emph|footnotesize|scriptsize)", "", c)
        c = c.replace("$", "").replace("{", "").replace("}", "").replace(",", "")
        c = c.replace("\\%", "").strip()
        out.append(c)
    return out


def c2_table_arithmetic():
    ok = True
    for p in sorted(glob.glob("tables/*.tex")):
        src = strip_comments(read(p))
        rows = [l for l in src.splitlines()
                if "&" in l and not l.lstrip().startswith(("\\toprule", "\\midrule",
                                                           "\\bottomrule", "\\cmidrule"))]
        body, total = [], None
        for l in rows:
            c = _cells(l)
            if c and c[0].lower().startswith("total"):
                total = c
            else:
                body.append(c)
        if total is None or not body:
            continue
        width = len(total)
        for col in range(1, width):
            vals = []
            for c in body:
                if len(c) != width:
                    vals = None
                    break
                v = c[col]
                if v in ("", "-", "$-$", "--"):
                    vals.append(0)
                    continue
                try:
                    vals.append(float(v))
                except ValueError:
                    vals = None
                    break
            if vals is None:
                continue
            try:
                stated = float(total[col])
            except ValueError:
                continue
            got = sum(vals)
            if abs(got - stated) > max(0.15, abs(stated) * 1e-6):
                HARD.append(f"C2 {p}: column {col} cells sum to {got:g} but the "
                            f"Total row states {stated:g}")
                ok = False
    return ok


# ---------------------------------------------------------------- C3
def c3_duplicated_literals():
    macros = {}
    for p in glob.glob("data/*.tex"):
        for m in re.finditer(r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}]*)\}", read(p)):
            val = m.group(2).replace("\\%", "%").replace("{,}", ",").strip()
            if re.fullmatch(r"-?[\d.,]+%?", val) and val not in ("0", "1", "2"):
                macros.setdefault(val, []).append(m.group(1))

    prose = strip_comments(read("main.tex"))
    # Only distinctive values are worth flagging: a bare "11" or "40" occurs
    # for a hundred unrelated reasons, and reporting those buries the real
    # hits. Require >=3 significant digits or a decimal point -- which is
    # exactly the shape of the numbers that have actually drifted (821.5,
    # 61.5, 2822).
    for val, names in sorted(macros.items()):
        bare = val.rstrip("%")
        digits = bare.replace(",", "").replace(".", "")
        if len(digits) < 3 and "." not in bare:
            continue
        pat = re.escape(bare).replace(r"\,", r"(?:\{,\}|,)")
        if val.endswith("%"):
            pat += r"\\?%"
        hits = [m.start() for m in re.finditer(rf"(?<![\d.]){pat}(?![\d.])", prose)]
        if hits:
            SOFT.append(f"C3 main.tex: literal {val!r} appears {len(hits)}x in prose "
                        f"but is also defined as \\{names[0]} — use the macro so the "
                        f"two cannot drift")
    return True


# ---------------------------------------------------------------- C4
def c4_invariants():
    ok = True
    facts = {}
    for f in ("data/tournament_facts.json", "data/resource_facts.json"):
        if os.path.exists(f):
            facts.update(json.load(open(f)))
    prose = strip_comments(read("main.tex"))

    # The passing-run count may be stated as a literal or through \WallTBs.
    # Accepting only the literal made C3 (use the macro) and C4 (state the
    # number) contradict each other, so the macro counts -- but only if the
    # generated definition still carries the expected value.
    walltbs = re.search(r"\\newcommand\{\\WallTBs\}\{(.*)\}\s*$",
                        read("data/coverage_macros.tex"), re.M)
    walltbs_val = re.sub(r"[^0-9]", "", walltbs.group(1)) if walltbs else ""
    pass_pats = [r"2\{,\}822"]
    if walltbs_val == "2822":
        pass_pats.append(r"\\WallTBs")
    expect = [
        ("40-instance suite size", 40,
         [r"\$40\$ instances", r"40-instance", r"the \$40\$ "]),
        ("39 HW-validated instances", 39, [r"\$39\$ of the \$40\$"]),
        ("2,822 passing runs", 2822, pass_pats),
    ]
    for label, val, pats in expect:
        if not any(re.search(p, prose) for p in pats):
            SOFT.append(f"C4: could not locate the stated {label} in main.tex "
                        f"(expected {val}) — check the wording did not drift")

    # coverage table must sum to the suite size
    cov = read("tables/coverage.tex")
    m = re.search(r"Total\s*&([^\\]*)\\\\", cov)
    if m:
        nums = [int(x) for x in re.findall(r"\d+", m.group(1).replace("textbf", ""))]
        if nums and nums[-1] != 40:
            HARD.append(f"C4 tables/coverage.tex: grand total is {nums[-1]}, not 40")
            ok = False

    # walltime table must reconcile to the headline campaign figures
    wt = read("tables/walltime.tex")
    m = re.search(r"\\textbf\{Total\}.*?\\textbf\{(\d+)\}.*?\\textbf\{([\d.]+)\}", wt)
    if m:
        tbs, hrs = int(m.group(1)), float(m.group(2))
        if tbs != 2822:
            HARD.append(f"C4 tables/walltime.tex: {tbs} TBs, expected 2822")
            ok = False
        if abs(hrs - 821.5) > 0.05:
            HARD.append(f"C4 tables/walltime.tex: {hrs} core-h, expected 821.5")
            ok = False
    return ok


# ---------------------------------------------------------------- C5
_PENDING_DEF = re.compile(r"\\(?:re)?newcommand\s*\*?\s*\{?\s*\\PENDING")
_PENDING_USE = re.compile(r"\\PENDING\s*(?=[\{\[])")


def c5_pending():
    r"""Fail on any live \PENDING{...} marker.

    A line whose first non-space character is % is a comment and is skipped;
    so is the \newcommand that defines the macro. Everything else counts.
    """
    hits = []
    for p in TEX:
        raw = read(p)
        if not raw:
            continue
        for lineno, line in enumerate(raw.split("\n"), 1):
            if line.lstrip().startswith("%"):
                continue
            if _PENDING_DEF.search(line):
                continue
            body = strip_comments(line)
            if _PENDING_USE.search(body):
                hits.append((p, lineno, body.strip()[:100]))
    allow = os.environ.get("SPRS_ALLOW_PENDING") == "1"
    for p, lineno, txt in hits:
        msg = f"C5 {p}:{lineno}: unresolved \\PENDING marker -- {txt}"
        (SOFT if allow else HARD).append(msg)
    if hits and allow:
        SOFT.append(f"C5: {len(hits)} \\PENDING marker(s) tolerated because "
                    f"SPRS_ALLOW_PENDING=1; this must not be set for submission")
    return not hits or allow


def main():
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    for fn in (c1_macro_digits, c2_table_arithmetic, c3_duplicated_literals,
               c4_invariants, c5_pending):
        fn()
    for m in HARD:
        print(f"  FAIL  {m}")
    for m in SOFT:
        print(f"  warn  {m}")
    if HARD:
        print(f"\ncheck_consistency: {len(HARD)} hard failure(s), {len(SOFT)} warning(s)")
        return 1
    print(f"check_consistency: OK ({len(SOFT)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
