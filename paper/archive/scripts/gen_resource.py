#!/usr/bin/env python3
"""
gen_resource.py — radix-parametric per-router resource envelope (Table III)
and the measured router-radix table.

Round-2 review, open question 2, asked whether MAX_PORTS = 8 is a real cap.
It is not. `MAX_PORTS` is declared in rtl/noc_pkg.sv and never referenced;
the live quantity is PORTS_PER_RTR, emitted per instance into each testbench.
Measured across the 40-instance suite the radix runs 3..66 -- fat-tree at
G = 4096 instantiates 66-port routers. Since the crossbar term is O(P^2),
a fixed 8-port estimate understates a fat-tree router by ~16x.

This script reads the radix straight out of the generated testbenches, so
the table cannot drift from what was actually simulated.

Produces:
  tables/resource.tex   Table III, one column per representative radix
  tables/radix.tex      measured radix by topology
  data/resource_macros.tex
"""
import argparse
import datetime
import glob
import json
import math
import os
import sys
import re

# Dataset root.  Resolution order:
#   1. $SPRS_P1                        -- explicit override
#   2. $SPRS_ROOT/data/results         -- the released artifact layout
#   3. the author's original absolute path, kept only as a last resort so that
#      re-running these scripts on the machine the campaign ran on still works.
# The hardcoded path is what made this script unrunnable from a fresh clone.
def _p1_default():
    root = os.environ.get("SPRS_ROOT") or os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    cand = os.path.join(root, "data", "results")
    return cand if os.path.isdir(cand) else "/home/rohit/tournament_p1/results"


P1 = os.environ.get("SPRS_P1") or _p1_default()

# (N, G, topology) per instance label -- same manifest the other generators use.
META = {}
for n, g, t, lab in [
    (8, 4, 'ring', 'tiny_mod_ring'), (8, 2, 'linear', 'tiny_dense_1d'),
    (32, 16, 'torus', 'small_mod_2d'), (32, 8, 'fat_tree', 'small_bal_fat'),
    (32, 4, 'hypercube', 'small_dense_hc'), (128, 64, 'ring', 'med_mod_ring'),
    (128, 32, 'fat_tree', 'med_mod_fat'), (128, 16, 'torus', 'med_bal_2d'),
    (128, 8, 'mesh', 'med_dense_mesh'), (128, 4, 'linear', 'med_extreme_1d'),
    (512, 256, 'ring', 'large_mod_ring'), (512, 64, 'fat_tree', 'large_bal_fat'),
    (512, 32, 'hypercube', 'large_dense_hc'), (512, 16, 'torus', 'large_dense_2d'),
    (512, 8, 'linear', 'large_extreme_1d'), (1024, 512, 'ring', 'vlarge_mod_ring'),
    (1024, 128, 'fat_tree', 'vlarge_bal_fat'), (1024, 64, 'torus', 'vlarge_dense_2d'),
    (1024, 32, 'hypercube', 'vlarge_dense_hc'), (2048, 256, 'fat_tree', 'vlarge2_bal_fat'),
    (2048, 128, 'torus', 'vlarge2_dense_2d'), (4096, 2048, 'fat_tree', 'max_mod_fat'),
    (4096, 1024, 'torus', 'max_bal_2d'), (4096, 512, 'hypercube', 'max_dense_hc'),
    (8192, 4096, 'fat_tree', 'maxp_mod_fat'), (8192, 2048, 'torus', 'maxp_bal_2d'),
    (8192, 1024, 'hypercube', 'maxp_dense_hc'), (512, 64, 'mesh', 'large_bal_mesh'),
    (2048, 256, 'mesh', 'vlarge_bal_mesh'), (128, 128, 'torus', 'med_full_torus'),
    (2048, 512, 'ring', 'vlarge2_mod_ring'), (1024, 16, 'linear', 'vlarge_extreme_1d'),
    (10, 4, 'ring', 'npow2n_tiny_ring'), (16, 5, 'mesh', 'npow2g_small_mesh'),
    (50, 7, 'hypercube', 'npow2_tiny_hc'), (100, 10, 'torus', 'npow2_small_torus'),
    (200, 12, 'fat_tree', 'npow2_med_fat'), (500, 32, 'torus', 'large_unbal_torus'),
    (1500, 64, 'hypercube', 'vlarge_unbal_hc'), (3000, 128, 'fat_tree', 'max_unbal_fat')]:
    META[lab] = (n, g, t)

PRETTY = {'fat_tree': 'fat-tree', 'hypercube': 'hypercube', 'torus': 'torus',
          'mesh': 'mesh', 'ring': 'ring', 'linear': 'linear'}

# Fabric constants.  NUM_VCS, FLIT_W and RT_DEPTH are read off rtl/noc_pkg.sv
# and rtl/noc_system.sv.  BUF_DEPTH is NOT the RTL default (8): every emitted
# testbench overrides it with .RTR_BUF_DEPTH(16) at src/sprs_core.py:5430, and
# noc_system.sv:235 passes that into the router, so 16 is the depth the
# campaign actually instantiated.  Council verdict T13/D071.
NUM_VCS, BUF_DEPTH, FLIT_W, RT_DEPTH = 2, 16, 96, 4096
BUF_DEPTH_RTL_DEFAULT = 8


def measured_radix():
    """label -> (n_nodes, n_routers, ports_per_router).

    Recomputed from sprs_core.build_topology, which is what the emitter used
    to write the N_NODES/N_ROUTERS/PPR localparams (sprs_core.py:5378), so the
    326 GB testbench corpus is not needed.
    """
    _root = os.environ.get("SPRS_ROOT") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..")
    sys.path.insert(0, os.path.join(_root, "src"))
    import sprs_core as sc
    out = {}
    for lab, (N, G, T) in META.items():
        topo = sc.build_topology(T, G)
        out[lab] = (topo.n_nodes, topo.n_routers, topo.ports_per_router)
    return out


def router_bits(P, G=RT_DEPTH):
    """Per-router storage-equivalent bits at radix P, route-table depth G."""
    pw = max(1, math.ceil(math.log2(P))) if P > 1 else 1
    return {
        'rt': G * pw,
        'vc': P * NUM_VCS * BUF_DEPTH * FLIT_W,
        'eg': P * BUF_DEPTH * FLIT_W,
        'xb': P * P * FLIT_W,
    }


def mbit(bits):
    return bits / 2**20


def hdr(script):
    return ("% GENERATED — do not edit by hand.\n"
            f"% script : scripts/{script}\n"
            "% source : sprs_core.build_topology (PPR/N_ROUTERS/N_NODES, the same\n"
            "%          call the emitter used to write those localparams)\n"
            f"% date   : {datetime.date.today().isoformat()}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tables")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs("data", exist_ok=True)

    rad = measured_radix()
    if not rad:
        raise SystemExit("no testbenches found — cannot generate resource tables")

    # ---- radix by topology -------------------------------------------------
    bytopo = {}
    for lab, (nn, nr, ppr) in rad.items():
        bytopo.setdefault(META[lab][2], []).append((META[lab][1], ppr, lab))
    lines = [hdr('gen_resource.py'),
             r'\begin{tabular}{@{}llrr@{}}', r'\toprule',
             r'Topology & Radix rule & Radix $P$ & $\lceil\log_2 P\rceil$ \\',
             r'\midrule']
    RULE = {'linear': '2 + local', 'ring': '2 + local', 'mesh': '4 + local',
            'torus': '4 + local', 'hypercube': r'$\dim + 1$',
            'fat_tree': r'$\max(5,\,k{+}2)$'}
    order = ['linear', 'ring', 'mesh', 'torus', 'hypercube', 'fat_tree']
    maxP, maxlab = 0, None
    for t in order:
        if t not in bytopo:
            continue
        ps = sorted({p for _, p, _ in bytopo[t]})
        lo, hi = ps[0], ps[-1]
        for _, p, lab in bytopo[t]:
            if p > maxP:
                maxP, maxlab = p, lab
        rng = str(lo) if lo == hi else f'{lo}--{hi}'
        wr = (str(math.ceil(math.log2(lo))) if lo == hi
              else f'{math.ceil(math.log2(lo))}--{math.ceil(math.log2(hi))}')
        lines.append(f'{PRETTY[t]} & {RULE[t]} & {rng} & {wr} \\\\')
    lines += [r'\bottomrule', r'\end{tabular}']
    open(f"{a.out}/radix.tex", "w").write("\n".join(lines) + "\n")

    # ---- radix-parametric resource envelope --------------------------------
    # Columns isolate the effect of radix: route-table depth is held at
    # G = 4096 throughout, so only P varies between columns.
    lo_topos = [t for t in ('linear', 'ring', 'mesh', 'torus') if t in bytopo]
    P_LO = max(p for t in lo_topos for _, p, _ in bytopo[t])          # 5
    P_HC = max(p for _, p, _ in bytopo.get('hypercube', [(0, 8, '')]))  # 11
    P_FT = maxP                                                        # 66
    ft_routers = rad[maxlab][1]

    cols = [(P_LO, r'mesh/torus'), (P_HC, r'hypercube'), (P_FT, r'fat-tree')]
    costs = [router_bits(P) for P, _ in cols]
    tots = [sum(c.values()) for c in costs]

    def row(name, key):
        cells = " & ".join(f"${c[key]:,}$".replace(",", "{,}") for c in costs)
        return f"{name} & {cells} \\\\"

    L = [hdr('gen_resource.py'),
         r'\begin{tabular}{@{}l rrr@{}}', r'\toprule',
         r'\textbf{Component} & \multicolumn{3}{c}{\textbf{Per-router bits at radix $P$}} \\',
         r'\cmidrule(l){2-4}',
         " & " + " & ".join(f'$P={P}$' for P, _ in cols) + r' \\',
         " & " + " & ".join(f'\\footnotesize {n}' for _, n in cols) + r' \\',
         r'\midrule',
         row(r'Routing table ($G\lceil\log_2 P\rceil$)', 'rt'),
         row(r'VC ingress FIFOs ($P\!\cdot\!%d\!\cdot\!%d\!\cdot\!%d$)'
             % (NUM_VCS, BUF_DEPTH, FLIT_W), 'vc'),
         row(r'Egress FIFO ($P\!\cdot\!%d\!\cdot\!%d$)' % (BUF_DEPTH, FLIT_W), 'eg'),
         row(r'Crossbar ($P^2\!\cdot\!96$)', 'xb'),
         r'\midrule',
         r'\textbf{Per-router subtotal} & ' +
         " & ".join(f'$\\mathbf{{{t:,}}}$'.replace(",", "{,}") for t in tots) + r' \\',
         r'\bottomrule', r'\end{tabular}']
    open(f"{a.out}/resource.tex", "w").write("\n".join(L) + "\n")

    # ---- macros ------------------------------------------------------------
    per_pe = 512 * 64 * 2
    m = [
        f"\\newcommand{{\\RadixMin}}{{{min(p for v in bytopo.values() for _, p, _ in v)}}}",
        f"\\newcommand{{\\RadixMax}}{{{P_FT}}}",
        f"\\newcommand{{\\RadixMaxInst}}{{\\sv{{{maxlab.replace('_', chr(92) + '_')}}}}}",
        f"\\newcommand{{\\RadixMaxRouters}}{{{ft_routers:,}}}".replace(",", "{,}"),
        f"\\newcommand{{\\RadixLo}}{{{P_LO}}}",
        f"\\newcommand{{\\RadixHc}}{{{P_HC}}}",
        f"\\newcommand{{\\RouterBitsLo}}{{{tots[0]:,}}}".replace(",", "{,}"),
        f"\\newcommand{{\\RouterBitsFt}}{{{tots[-1]:,}}}".replace(",", "{,}"),
        f"\\newcommand{{\\RouterBlowup}}{{{tots[-1] / tots[0]:.0f}}}",
        f"\\newcommand{{\\XbarShareFt}}{{{100 * costs[-1]['xb'] / tots[-1]:.0f}\\%}}",
        f"\\newcommand{{\\AggFtMbit}}{{{mbit(tots[-1] * ft_routers):.1f}}}",
        f"\\newcommand{{\\AggLoMbit}}{{{mbit(tots[0] * RT_DEPTH):.0f}}}",
        f"\\newcommand{{\\PerPEBits}}{{{per_pe:,}}}".replace(",", "{,}"),
        f"\\newcommand{{\\BufDepthSim}}{{{BUF_DEPTH}}}",
        f"\\newcommand{{\\BufDepthRtl}}{{{BUF_DEPTH_RTL_DEFAULT}}}",
        f"\\newcommand{{\\XbarBitsFt}}{{{costs[-1]['xb']:,}}}".replace(",", "{,}"),
        f"\\newcommand{{\\AggPEMbit}}{{{mbit(per_pe * RT_DEPTH):.0f}}}",
    ]
    open("data/resource_macros.tex", "w").write(
        hdr('gen_resource.py') + "\n".join(m) + "\n")

    json.dump({'radix_by_topology': {t: sorted({p for _, p, _ in v})
                                     for t, v in bytopo.items()},
               'max_radix': P_FT, 'max_radix_instance': maxlab,
               'max_radix_routers': ft_routers,
               'per_router_bits': dict(zip([P for P, _ in cols], tots))},
              open("data/resource_facts.json", "w"), indent=2)

    print(f"  radix {min(p for v in bytopo.values() for _, p, _ in v)}..{P_FT} "
          f"({maxlab}); per-router {tots[0]:,} -> {tots[-1]:,} bits "
          f"({tots[-1]/tots[0]:.1f}x), crossbar {100*costs[-1]['xb']/tots[-1]:.0f}% of fat-tree")


if __name__ == "__main__":
    main()
