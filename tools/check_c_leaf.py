#!/usr/bin/env python3
"""C-leaf post-condition checker, run directly on the EMITTED testbench.

C-leaf (paper, Sec. on compiler obligations): the GCI buffer of every PE must
be filled in the order that PE executes its GENERATE instructions, and the word
at local index i must be exactly make_leaf_val(global_index_of(the leaf that PE
generates i-th)).  The hardware pops GCI[gci_rd_ptr++] on each GENERATE, so an
out-of-order or wrong-valued fill silently reduces a different multiset.

This checker is deliberately EXTERNAL to the compiler: it re-derives the
expectation from the schedule and the tree, then reads the emitted testbench
TEXT back and compares.  Nothing is shared with the emitter except CBTree and
the schedule object.

Origin: written by review theme T12 (25 lines, plus a firing negative control);
packaged here with the negative control retained as `--negative`, so the
checker's ability to fail is demonstrated every time it is run under --smoke.

Usage:
  python3 tools/check_c_leaf.py --smoke        # the smoke-test configuration set
  python3 tools/check_c_leaf.py --full         # a wider sweep (slower)
  python3 tools/check_c_leaf.py --negative     # only the negative control
Exit 0 iff every checked binding holds AND the negative control fires.
"""
import os
import re
import sys
import struct

ROOT = os.environ.get('SPRS_ROOT',
                      os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import sprs_core as sc            # noqa: E402

_RE_GCI = re.compile(r"load_gci\((\d+),(\d+),64'h([0-9A-Fa-f]{16})\)")


def make_leaf_val(idx, alu_op=sc.ALU_FADD):
    """Independent restatement of emit_sv_testbench's make_leaf_val."""
    if alu_op == 0b111:
        fv = (idx + 1) * 1000.0 + ((idx * 37 + 13) % 100) / 100.0 + 0.007
        return struct.unpack('<Q', struct.pack('<d', fv))[0]
    if alu_op == 0b110:
        sv = (idx + 1) * 1000
        if idx % 2 == 1:
            sv = -sv
        return sv & 0xFFFFFFFFFFFFFFFF
    return (idx + 1) * 1000


def compile_one(n, g, topo_name, s2='2b', s3='3a', alu_op=sc.ALU_FADD):
    tree = sc.CBTree(n)
    topo = sc.build_topology(topo_name, g)
    _, f2 = sc.STAGE2_METHODS[s2]
    _, f3 = sc.STAGE3_METHODS[s3]
    asgn = f2(tree, g, topo, sc.HW)
    mp = f3(tree, asgn, g, topo, sc.HW)
    sched = sc.build_schedule(tree, asgn, mp, g, topo, sc.HW, alu_op=alu_op)
    progs = sc.generate_instructions(tree, topo, sched, sc.HW, alu_op=alu_op)
    tb = sc.emit_sv_testbench(tree, topo, progs, assignment=asgn,
                              addr_alloc=sched.addr_alloc, schedule=sched,
                              alu_op=alu_op)
    return tree, sched, tb, min(g, tree.total_nodes)


def check_c_leaf(tree, sched, tb, ge, alu_op=sc.ALU_FADD):
    """Return (n_expected, n_emitted, violations)."""
    g_idx = {leaf: i for i, leaf in enumerate(tree.leaves())}
    exp = {}
    for g in range(ge):
        gen = [o.node for o in sched.get_gpu_ops(g) if o.op_type == 'generate']
        for li, node in enumerate(gen):
            exp[(g, li)] = make_leaf_val(g_idx.get(node, 0), alu_op)
    got = {(int(a), int(b)): int(w, 16) for a, b, w in _RE_GCI.findall(tb)}
    bad = sorted(k for k in set(exp) | set(got) if exp.get(k) != got.get(k))
    return len(exp), len(got), bad


SMOKE = [(32, 4, 'hypercube'), (128, 8, 'mesh'), (512, 16, 'torus'),
         (1024, 32, 'fat_tree'), (2048, 8, 'linear')]
FULL = SMOKE + [(64, 2, 'linear'), (64, 16, 'hypercube'), (256, 4, 'mesh'),
                (256, 64, 'torus'), (512, 8, 'fat_tree'), (1024, 4, 'hypercube'),
                (2048, 32, 'mesh'), (4096, 16, 'linear'), (4096, 64, 'fat_tree')]


def run(configs, verbose=True):
    total = 0
    viol = 0
    for n, g, t in configs:
        tree, sched, tb, ge = compile_one(n, g, t)
        ne, ng, bad = check_c_leaf(tree, sched, tb, ge)
        total += ne
        viol += len(bad)
        if verbose:
            print('  N=%-5d G=%-3d %-10s gci_expected=%-6d gci_emitted=%-6d violations=%d'
                  % (n, g, t, ne, ng, len(bad)))
        if bad and verbose:
            for k in bad[:5]:
                print('      PE %d slot %d' % k)
    if verbose:
        print('  total leaf bindings checked: %d   violations: %d' % (total, viol))
    return total, viol


def negative_control(verbose=True):
    """Perturb one emitted load_gci payload by 1 ulp; the checker must fire."""
    tree, sched, tb, ge = compile_one(32, 4, 'hypercube')
    m = _RE_GCI.search(tb)
    tb2 = tb.replace(m.group(0),
                     "load_gci(%s,%s,64'h%016X)"
                     % (m.group(1), m.group(2), int(m.group(3), 16) ^ 1), 1)
    _, _, bad = check_c_leaf(tree, sched, tb2, ge)
    if verbose:
        print('  negative control (one GCI word perturbed by 1 ulp): '
              'violations detected = %d -> checker is %s'
              % (len(bad), 'FAILABLE' if bad else 'VACUOUS'))
    return len(bad) > 0


def main(argv):
    mode = argv[1] if len(argv) > 1 else '--smoke'
    quiet = '--quiet' in argv
    if mode == '--negative':
        return 0 if negative_control(not quiet) else 1
    configs = FULL if mode == '--full' else SMOKE
    if not quiet:
        print('C-leaf post-condition on the emitted GCI image')
    total, viol = run(configs, verbose=not quiet)
    fired = negative_control(verbose=not quiet)
    if viol:
        print('C-LEAF VIOLATED: %d bad bindings' % viol)
        return 1
    if not fired:
        print('C-LEAF CHECKER IS VACUOUS: negative control did not fire')
        return 1
    if not quiet:
        print('C-leaf holds over %d bindings; negative control fires.' % total)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
