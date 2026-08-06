#!/usr/bin/env python3
"""
hwdata.py — shared loader and source selection for HW cycle data.

Single place that decides WHICH cycle dataset the paper is allowed to use, so
the table generators cannot disagree with each other.

Two datasets exist:
  live_hw_results_p1_unified.csv   original campaign. Cycles = GPU 0's
                                   perf_total, which understated the makespan
                                   on ~54% of rows (PAPER_V6_PLAN.md §5b).
                                   DEFECTIVE for any cycle-derived claim.
  live_hw_results_p1_maxpe.csv     re-measurement with Cycles = max over PEs.

The re-measured file is used only when it is COMPLETE: at least as many
instances as the original, and at least 95% of its passing rows. A partial
re-measurement is worse than the original for aggregate statistics, because
the phases run in size order -- taking it early silently drops every giant
instance and skews any per-family or per-topology summary.
"""
import csv
import os
import sys

csv.field_size_limit(sys.maxsize)

P1 = "'"+SPRS_ROOT+"/data/results"
MAXPE = f"{P1}/live_hw_results_p1_maxpe.csv"
ORIG = f"{P1}/live_hw_results_p1_unified.csv"
COVERAGE_FRAC = 0.95


def load(path):
    """Passing rows as (instance, tb_name, cycles). Tolerates the embedded
    newlines that NOCTRC traces put in the Error column."""
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, newline='', encoding='utf-8', errors='replace') as f:
        rdr = csv.reader(f)
        first = next(rdr, None)
        if first and first[0] != 'Instance' and len(first) >= 7:
            rows.append(first)
        rows += [r for r in rdr if len(r) >= 7]
    out = []
    for r in rows:
        if r[3] != 'True':
            continue
        try:
            out.append((r[0], r[2], int(r[4])))
        except ValueError:
            pass
    return out


def select(quiet=False):
    """Returns (rows, source_path, trusted). `trusted` False means the caller
    must stamp its output DEFECTIVE; `make check` fails the build on that."""
    orig = load(ORIG)
    new = load(MAXPE)
    oi = {r[0] for r in orig}
    ni = {r[0] for r in new}

    complete = (len(ni) >= len(oi)) and (len(new) >= COVERAGE_FRAC * len(orig))
    if complete:
        if not quiet:
            print(f"  using re-measured max-over-PEs data: {len(new)} rows, "
                  f"{len(ni)} instances")
        return new, MAXPE, True

    if not quiet and new:
        missing = sorted(oi - ni)
        print(f"  re-measurement INCOMPLETE: {len(new)}/{len(orig)} rows, "
              f"{len(ni)}/{len(oi)} instances", file=sys.stderr)
        if missing:
            print(f"    still missing: {', '.join(missing[:6])}"
                  f"{' ...' if len(missing) > 6 else ''}", file=sys.stderr)
        print("    falling back to the DEFECTIVE GPU-0 metric; re-run these "
              "generators when the watchdog finishes.", file=sys.stderr)
    return orig, ORIG, False
