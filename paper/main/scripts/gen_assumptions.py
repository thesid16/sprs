#!/usr/bin/env python3
r"""
gen_assumptions.py -- the two tables that name the ABI's obligations and say,
for each, where in the released source it is discharged.

  tables/invariants.tex    the eleven fabric F-* invariants: what each requires,
                           the RTL file and line range that realises it, and
                           what a violation actually produces.
  tables/obligations.tex   the compiler C-* obligations: the pass that discharges
                           each, the line in src/sprs_core.py that does it, and
                           how it is checked.

WHY THE LINE NUMBERS ARE COMPUTED, NOT TYPED.  FULL_REFERENCE.tex cites
`sprs_core.py:5533--5549` for C-leaf and `sprs_core.py:5098` for the identity
slot; neither is right against the source that ships in this tree, because the
files moved under them.  Every citation below is located by searching for a
literal anchor in the file at generation time.  Each anchor must occur EXACTLY
once or this script exits non-zero, so the table cannot drift from the source
and cannot silently degrade into "no line number".  That is the whole point:
run it against a modified RTL and it fails rather than lying.

Sources, all inside the release:
  rtl/*.sv                 the fabric
  src/sprs_core.py         the compiler
  paper/FULL_REFERENCE.tex the prose definitions these one-liners compress
                           (nothing is taken from it that is not also checked
                           against the source)
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_tablestyle as ts

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
ROOT = os.environ.get("SPRS_ROOT") or os.path.abspath(os.path.join(PAPER, ".."))

RTL = os.path.join(ROOT, "rtl")
SRC = os.path.join(ROOT, "src")

_cache = {}


def _lines(path):
    if path not in _cache:
        if not os.path.exists(path):
            sys.exit(f"gen_assumptions.py: required source missing: {path}\n"
                     f"  set $SPRS_ROOT to the release root")
        with open(path, encoding="utf-8", errors="replace") as f:
            _cache[path] = f.read().split("\n")
    return _cache[path]


def at(relpath, *anchors):
    r"""`file:n` or `file:lo--hi` for the given literal anchors.

    Every anchor must appear exactly once in the file.  A missing or duplicated
    anchor is a hard error: a citation that cannot be located is worse than no
    citation, because it reads as if it had been checked.
    """
    path = os.path.join(ROOT, relpath)
    lines = _lines(path)
    hits = []
    for a in anchors:
        found = [i + 1 for i, ln in enumerate(lines) if a in ln]
        if len(found) != 1:
            sys.exit(f"gen_assumptions.py: anchor {a!r} occurs {len(found)} "
                     f"times in {relpath}, expected exactly 1 -- the source "
                     f"moved under this table; re-anchor it.")
        hits.append(found[0])
    base = os.path.basename(relpath).replace("_", r"\_")
    lo, hi = min(hits), max(hits)
    where = f"{lo}" if lo == hi else f"{lo}--{hi}"
    return rf"\sv{{{base}:{where}}}"


def ats(relpath, *anchors):
    r"""`file:a, b` for anchors that sit in two unrelated places."""
    parts = []
    base = None
    for a in anchors:
        cite = at(relpath, a)
        base, ln = cite[len(r"\sv{"):-1].split(":")
        parts.append(ln)
    return rf"\sv{{{base}:{', '.join(parts)}}}"


def count(relpath, needle):
    path = os.path.join(ROOT, relpath)
    return sum(ln.count(needle) for ln in _lines(path))


def hdr(script, note=""):
    s = ("% GENERATED — do not edit by hand.\n"
         f"% script : scripts/{script}\n"
         "% source : rtl/*.sv and src/sprs_core.py (line numbers located by\n"
         "%          literal anchor at generation time; a missing or duplicated\n"
         "%          anchor aborts the script rather than emitting a stale one)\n"
         f"% date   : {datetime.date.today().isoformat()}\n")
    if note:
        s += f"% note   : {note}\n"
    return s


# ------------------------------------------------------------------ invariants
def invariants_table():
    r"""Eleven fabric invariants.

    Seven are safety hypotheses of Claim 1, three (marked $\dagger$ in the
    manuscript) are liveness hypotheses of Property 2, and F-id is the identity
    slot -- realised by the fabric, but unread in the reported workload, which
    is why the manuscript's Claim 1 does not list it.
    """
    ORACLE = ("no fabric-level detector; wrong root, caught only by "
              "comparison against the oracle")
    FAIL = ("absent operand: the PE stalls, \\textsf{F-watchdog} raises "
            "\\texttt{P\\_ERROR}, no root is produced")

    safety = [
        ("F-sb-mono", "Each receive buffer's scoreboard bit goes $0\\to1$ once "
                      "per program, at the unique remote write",
         at("rtl/btree_fsm_fast.sv", "Scoreboard — DMEM Presence Tracking",
            "scoreboard[fsm_dmem_addr] <= 1'b1;"), ORACLE),
        ("F-sb-gate", "\\texttt{COMPUTE} stalls \\textsf{DE}$\\to$\\textsf{EX} "
                      "until both operand bits are $1$; \\texttt{SEND} until "
                      "\\texttt{addr\\_a}'s is",
         at("rtl/btree_fsm_fast.sv", "assign scoreboard_hazard = de_valid && (",
            "assign de_hazard = scoreboard_hazard || gci_data_hazard;"), ORACLE),
        ("F-fw", "A DMEM read at cycle $t$ returns the value committed at "
                 "cycle $\\leq t$, across the adjacent-cycle race",
         at("rtl/btree_fsm_fast.sv",
            "DMEM — Dual read + single write + 2-level forwarding",
            "dmem_wr_en_d2 && dmem_wr_addr_d2 == dmem_rd_addr_b_r"), ORACLE),
        ("F-inorder", "One instruction at a time through "
                      "\\textsf{IF}$\\to$\\textsf{DE}$\\to$\\textsf{EX}; "
                      "operands sampled in \\textsf{DE} before writeback in "
                      "\\textsf{EX}",
         at("rtl/btree_fsm_fast.sv", "assign ex_advance = !ex_stall;",
            "dmem_rd_addr_b = de_valid ? de_addr_b[DMEM_ADDR_W-1:0] : '0;"),
         ORACLE),
        ("F-gci-haz", "From \\sv{gci\\_start} until the GCI agent commits, "
                      "\\textsf{DE} stalls any reader of the pending "
                      "destination",
         at("rtl/btree_fsm_fast.sv", "assign gci_data_hazard = de_valid && (",
            "assign de_hazard = scoreboard_hazard || gci_data_hazard;"), ORACLE),
        ("F-arb", "DMEM write arbitration is strict "
                  "$\\mathrm{PIU}>\\mathrm{GCI}>\\mathrm{FSM}$, with a GCI "
                  "retry latch; no write is dropped",
         ats("rtl/btree_fsm_fast.sv", "end else if (gci_dmem_wr) begin",
             "logic        gci_write_held;"), ORACLE),
        ("F-fadd", "The adder is combinational and stateless: its output is a "
                   "pure function of the two operands sampled at the EX edge",
         at("rtl/fp64_add.sv", "always_comb begin"), ORACLE),
    ]
    liveness = [
        ("F-credit", "Per link and interval, credit returns never exceed "
                     "buffer reads, with a bounded wait "
                     "(counter-serialised pulses)",
         at("rtl/noc_router.sv", "logic [NUM_PORTS-1:0] credit_pulse;",
            "assign credit_out = credit_pulse;"), FAIL),
        ("F-misroute", "A packet whose \\sv{dest\\_gpu\\_id} does not match the "
                       "local PE is dropped, not consumed",
         at("rtl/btree_fsm_fast.sv", "// Misrouted packet"), FAIL),
        ("F-watchdog", "\\sv{WATCHDOG\\_MAX} $=\\WatchdogMax$ non-retiring "
                       "cycles, or a \\sv{TIMEOUT\\_MAX} EX stall, raises "
                       "\\texttt{P\\_ERROR}",
         at("rtl/btree_fsm_fast.sv", "logic [31:0] watchdog;",
            "watchdog <= any_retired ? 32'd0 : watchdog + 32'd1;"),
         "this \\emph{is} the detector: \\sv{error\\_pc} and "
         "\\sv{error\\_state} are recorded and \\sv{all\\_done} never asserts"),
    ]
    identity = [
        ("F-id", "\\texttt{DMEM[0]} holds the ALU identity: DMEM resets to zero "
                 "and \\texttt{scoreboard[0]} is set at reset",
         ats("rtl/btree_fsm_fast.sv", "dmem[i] = 64'd0;",
             "// DMEM[0] = identity element, always valid"),
         "not applicable here: $\\FBT(N)$ has no single-child node, so the "
         "slot is never read in this workload"),
    ]

    nff = count("rtl/fp64_add.sv", "always_ff")
    if nff != 0:
        sys.exit(f"gen_assumptions.py: fp64_add.sv now has {nff} always_ff "
                 f"blocks; F-fadd (stateless adder) no longer holds by "
                 f"inspection and this row must not be emitted.")

    tab = [r"\begin{tabularx}{\textwidth}{@{}l X l X@{}}", r"\toprule",
           ts.band(ts.HEAD) +
           r"\sphd{Invariant} & \sphd{What the fabric must guarantee} & "
           r"\sphd{Realised at} & \sphd{What a violation produces} \\",
           r"\midrule",
           r"\multicolumn{4}{@{}l}{" + ts.band(ts.GOOD) +
           r"\emph{Safety --- hypotheses of Claim~\ref{claim:1}; a violation "
           r"can change the root}} \\"]
    i = 0
    for name, req, site, det in safety:
        tab.append(f"{ts.zebra(i)}\\textsf{{{name}}} & {req} & {site} & "
                   f"{det} \\\\")
        i += 1
    tab += [r"\midrule",
            r"\multicolumn{4}{@{}l}{" + ts.band(ts.WARN) +
            r"\emph{Liveness --- hypotheses of Property~\ref{prop:2}; a "
            r"violation stops the run instead}} \\"]
    i = 0
    for name, req, site, det in liveness:
        tab.append(f"{ts.zebra(i)}\\textsf{{{name}}} & {req} & {site} & "
                   f"{det} \\\\")
        i += 1
    tab += [r"\midrule",
            r"\multicolumn{4}{@{}l}{" + ts.band(ts.ZEBRA) +
            r"\emph{Realised but not load-bearing in the reported workload}} \\"]
    for name, req, site, det in identity:
        tab.append(f"\\textsf{{{name}}} & {req} & {site} & {det} \\\\")
    tab += [r"\bottomrule", r"\end{tabularx}"]

    out = [r"\begin{table*}[!t]",
           r"\caption{The eleven fabric invariants, with the line of released "
           r"RTL that realises each and what a violation of it produces. "
           r"Line ranges are located by literal anchor when this table is "
           r"generated, so a change to \sv{rtl/} that moves them fails the "
           r"build rather than silently mis-citing. The one thing to take from "
           r"it is the split in the last column: the three liveness invariants "
           r"convert a violation into a fail-stop the fabric reports, and the "
           r"seven safety invariants do not --- for those the fabric checks "
           r"presence, not identity, and the only detector is the oracle "
           r"comparison outside it.}",
           r"\label{tab:invariants}", r"\centering", r"\footnotesize",
           r"\renewcommand{\arraystretch}{1.25}"]
    out += ts.wrap(tab)
    out += [r"\end{table*}"]
    return out


# ----------------------------------------------------------------- obligations
def obligations_table():
    r"""Compiler obligations against the pass that discharges each.

    Five are obligations of THIS manuscript.  C-$\alpha$ (compilation
    determinism) and C-conn (partition connectedness) were obligations of an
    earlier version and are listed because the reader of that version will look
    for them; both are explicitly withdrawn in \S\ref{sec:abi-assumptions}, and
    the table says so rather than leaving them unaccounted for.
    """
    AUDIT = (r"static post-condition on the emitted image: \BindComputes{} "
             r"\texttt{COMPUTE} and \BindSends{} \texttt{SEND} over "
             r"\BindConfigs{} configurations, \BindViolations{} violations")

    rows = [
        ("C-sw", "S6", "Every receive buffer on every PE has exactly one "
                       "writer, and that writer is remote",
         at("src/sprs_core.py", "def allocate(self)",
            "return addr_map"),
         "constructed, not assumed: post-order frees a local slot only after "
         "its consumer has read it, and receive slots are allocated in a "
         "separate never-freed pass"),
        ("C-bind", "S1, S6", "Every \\texttt{COMPUTE} for internal node $v$ "
                             "binds $(\\mathrm{left}(v),\\mathrm{right}(v))$",
         at("src/sprs_core.py", "child_addrs.append(addr_map[gpu]"), AUDIT),
        ("C-leaf", "S6", "Every \\texttt{GENERATE} for leaf $k$ delivers "
                         "$L[\\mathrm{idx}(k)]$ into the slot bound to $k$",
         at("src/sprs_core.py", "def make_leaf_val(idx, op)",
            "localparam logic[63:0] EXPECTED"),
         "same audit; and the clean counterexample --- all \\MutLeaf{} "
         "leaf-corruption mutants terminate normally with a wrong root"),
        ("C-mem", "post-cond.", "At most \\sv{DMEM\\_DEPTH} $=\\DmemDepth$ "
                                "distinct DMEM addresses per PE, and every "
                                "router id below the adjacency sentinel",
         at("src/sprs_core.py",
            "dmem_violations = {g: u for g, u in dmem.items() if u > hw.dmem_depth}"),
         "an $O(N)$ read-off of peak occupancy the allocator already "
         "maintains; S5, the enforcement pass, was never invoked"),
        ("C-route", "S6", "Emitted routing tables encode destination-correct, "
                          "loop-free paths on the declared topology",
         at("src/sprs_core.py", "def generate_routing_tables(self)"),
         "by construction per topology family; a violation is converted to a "
         "fail-stop by \\textsf{F-misroute} and \\textsf{F-watchdog}"),
    ]
    withdrawn = [
        ("C-$\\alpha$", "---", "Compilation is a deterministic function of "
                               "its seed",
         "---",
         "\\emph{not an obligation here}: Claim~\\ref{claim:1} quantifies over "
         "every image the compiler can emit, so it does not need the compiler "
         "to be a pure function"),
        ("C-conn", "S2.5", "Each PE's node set is a connected subtree",
         at("src/sprs_core.py", "def repair_connectivity("),
         "\\emph{not an obligation here}: operand binding holds for any "
         "assignment; what disconnection costs is DMEM, which is what "
         "\\textsf{C-mem} bounds. S2.5 was never invoked"),
    ]

    tab = [r"\begin{tabularx}{\textwidth}{@{}l l X l X@{}}", r"\toprule",
           ts.band(ts.HEAD) +
           r"\sphd{Obligation} & \sphd{Pass} & "
           r"\sphd{What the compiler must guarantee} & \sphd{Discharged at} & "
           r"\sphd{How it is checked} \\",
           r"\midrule"]
    for i, (name, stage, req, site, how) in enumerate(rows):
        tab.append(f"{ts.zebra(i)}\\textsf{{{name}}} & {stage} & {req} & "
                   f"{site} & {how} \\\\")
    tab += [r"\midrule",
            r"\multicolumn{5}{@{}l}{" + ts.band(ts.WARN) +
            r"\emph{Named in earlier versions of this ABI and withdrawn "
            r"(\S\ref{sec:abi-assumptions})}} \\"]
    for i, (name, stage, req, site, how) in enumerate(withdrawn):
        tab.append(f"{ts.zebra(i)}\\textsf{{{name}}} & {stage} & {req} & "
                   f"{site} & {how} \\\\")
    tab += [r"\bottomrule", r"\end{tabularx}"]

    out = [r"\begin{table*}[!t]",
           r"\caption{The compiler's obligations, the pass that discharges "
           r"each, and the line of \sv{src/sprs\_core.py} that does it "
           r"(located by anchor at generation time). The one thing to take "
           r"from it: none of the five live obligations is enforced by the "
           r"fabric at run time --- every one is a property of the emitted "
           r"image, which is why they are checkable statically and why the two "
           r"passes that would enforce them dynamically (S2.5, S5) were never "
           r"invoked.}",
           r"\label{tab:obligations}", r"\centering", r"\footnotesize",
           r"\renewcommand{\arraystretch}{1.25}"]
    out += ts.wrap(tab)
    out += [r"\end{table*}"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(PAPER, "tables"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    inv = invariants_table()
    obl = obligations_table()
    with open(os.path.join(a.out, "invariants.tex"), "w", encoding="utf-8") as f:
        f.write(hdr("gen_assumptions.py",
                    "11 fabric invariants: 7 safety, 3 liveness, 1 identity slot")
                + "\n".join(inv) + "\n")
    with open(os.path.join(a.out, "obligations.tex"), "w", encoding="utf-8") as f:
        f.write(hdr("gen_assumptions.py",
                    "5 live compiler obligations + 2 withdrawn in this version")
                + "\n".join(obl) + "\n")
    print(f"  tables/invariants.tex, tables/obligations.tex "
          f"(all source anchors resolved uniquely)")


if __name__ == "__main__":
    main()
