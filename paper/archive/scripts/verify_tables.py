#!/usr/bin/env python3
r"""
verify_tables.py -- prove every generated .tex in this tree is what its generator
actually produces.

Why this exists.  Three generated files in this paper had been edited BY HAND
after generation, while still carrying the "% GENERATED - do not edit by hand"
banner:

  tables/perinstance_full.tex  assignment/mapping columns deleted (council T15)
  tables/catalogue.tex         replaced with champion-class membership (T15)
  tables/selection.tex         emitted by a script outside the release entirely

Nothing detected that.  `make tables` therefore silently reinstated two refuted
claims, and `make` after it produced a DIFFERENT paper from the one shipped.
This script copies the paper tree to a scratch directory, runs `make tables`
there, and diffs every generated file against the committed one.  Provenance
header lines (date, absolute source path) are excluded; everything else must
match exactly.

Usage:  python3 scripts/verify_tables.py [--keep]
Exit 0 = every generated file reproduces.  Non-zero = it does not.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
ROOT = os.environ.get("SPRS_ROOT") or os.path.abspath(os.path.join(PAPER, ".."))

# Lines that legitimately differ run-to-run: the generation date and the
# absolute path of the input dataset.  Nothing else may differ.
VOLATILE = re.compile(
    r"^%\s*(date|Generated|source|Inputs)\b|^%\s+/|^%\s+<P1>|^%\s{6,}\S+\.csv")


def body(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return [ln for ln in f if not VOLATILE.match(ln)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="sprs_verify_tables_",
                           dir=os.environ.get("SPRS_SCRATCH") or None)
    work = os.path.join(tmp, "paper")
    shutil.copytree(PAPER, work, symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pdf",
                                                  "*.aux", "*.log", "*.out",
                                                  "*.bbl", "*.blg", "*.bak*"))
    env = dict(os.environ)
    env["SPRS_ROOT"] = ROOT          # the copy is outside the repo
    r = subprocess.run(["make", "tables"], cwd=work, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        sys.stdout.write(r.stdout.decode(errors="replace"))
        print("FAIL: `make tables` itself failed in the scratch copy")
        return 2

    bad, checked = [], 0
    for sub in ("tables", "data", "figures"):
        d = os.path.join(PAPER, sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".tex"):
                continue
            committed, regen = os.path.join(d, fn), os.path.join(work, sub, fn)
            if not os.path.exists(regen):
                continue      # not a generated file (or generator not run here)
            checked += 1
            if body(committed) != body(regen):
                bad.append(os.path.join(sub, fn))

    if bad:
        import difflib
        for f in bad:
            print(f"\n=== {f} : committed file is NOT what the generator produces ===")
            sys.stdout.writelines(difflib.unified_diff(
                body(os.path.join(PAPER, f)), body(os.path.join(work, f)),
                "committed", "regenerated", n=1))
        print(f"\nFAIL: {len(bad)} of {checked} generated file(s) do not reproduce")
        print(f"  scratch copy kept at {work}" if a.keep else "")
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)
        return 1

    print(f"OK: all {checked} generated .tex files reproduce from their generators")
    if a.keep:
        print(f"  scratch copy at {work}")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
