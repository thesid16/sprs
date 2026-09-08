#!/usr/bin/env python3
"""ABI post-condition validator for the emitted IMEM image.

The paper describes a post-generation pass that verifies the compiler's ABI
obligations "directly on the emitted IMEM"; no such pass existed in the release.
This is that pass.  The checking logic is review theme T04's `abicheck.check`,
adopted verbatim in substance, with the image passed in so that fault injection
is possible (the original recomputed it internally and could not be given a
mutant).

Properties checked, per configuration:

  order_mismatch      the schedule's per-PE append order equals its cycle-sorted
                      order (the code generator relies on this)
  decode_mismatch     every emitted non-NOP word decodes back to exactly the
                      ScheduledOp it was generated from, field for field, and
                      the counts agree
  bind_wrong  (C-bind) each COMPUTE's two source addresses resolve to the two
                      children of its tree node: for a child on the same PE, the
                      most recent earlier local write to that address must be
                      that child; for a remote child, the unique remote writer of
                      that address must be that child.  A missing second child
                      must read the identity slot 0.
  multi_remote_write  no DMEM slot is the target of two different SENDs
  mixed_local_remote  no DMEM slot is written both locally and remotely
  identity_written    slot 0 (the identity element) is never written
  addr_ge_depth       no instruction addresses a DMEM slot at or beyond
                      CN_DMEM, i.e. nothing relies on address truncation
  missing_slot        every COMPUTE operand that should be local has an earlier
                      local writer

`--negative` injects one fault of each class into an otherwise-good image and
requires the corresponding counter to rise.  A checker whose negative control
does not fire exits non-zero, so this file cannot silently become vacuous.

Usage:
  python3 tools/validate_abi.py --smoke      # small config set + negative controls
  python3 tools/validate_abi.py --full       # every TEST_INSTANCE x every stage-2
  python3 tools/validate_abi.py --negative   # only the negative controls
"""
import os
import sys
import copy

ROOT = os.environ.get('SPRS_ROOT',
                      os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import sprs_core as C            # noqa: E402

COUNTERS = ['order_mismatch', 'decode_mismatch', 'bind_wrong', 'multi_remote_write',
            'mixed_local_remote', 'identity_written', 'addr_ge_depth', 'missing_slot']


def decode(w):
    return ((w >> 60) & 0xF, (w >> 56) & 0xF, (w >> 40) & 0xFFFF,
            (w >> 24) & 0xFFFF, (w >> 8) & 0xFFFF)


def build(tree, asgn, mapping, ge, topo, hw=C.HW, alu=C.ALU_FADD):
    ad = asgn if isinstance(asgn, dict) else {i: asgn[i] for i in range(tree.total_nodes)}
    sched = C.build_schedule(tree, ad, mapping, ge, topo, hw, alu_op=alu)
    progs = C.generate_instructions(tree, topo, sched, hw, alu_op=alu)
    return ad, sched, progs


def check_image(tree, ad, sched, progs, ge, dmem_depth=512):
    """Static ABI check on an already-emitted image.  Returns (counters, detail)."""
    V = {k: 0 for k in COUNTERS}
    V.update({'peak_dmem': 0, 'max_imem': 0, 'n_compute': 0, 'n_send': 0})
    detail = []
    # 0. append order vs cycle-sorted order
    for g in range(ge):
        raw = sched.ops.get(g, [])
        srt = sched.get_gpu_ops(g)
        if [id(o) for o in raw] != [id(o) for o in srt]:
            V['order_mismatch'] += 1
    # 1. decoded program per PE matches the op list
    prog_ops = {}
    for g in range(ge):
        ops = sched.get_gpu_ops(g)
        dec = [decode(w) for w in progs.get(g, []) if ((w >> 60) & 0xF) != 0]
        V['max_imem'] = max(V['max_imem'], len(progs.get(g, [])))
        if len(dec) != len(ops):
            V['decode_mismatch'] += 1
            detail.append(('len', g, len(dec), len(ops)))
        prog_ops[g] = list(zip(ops, dec))
        for o, d in prog_ops[g]:
            op, aux, dest, a, b = d
            if o.op_type == 'generate':
                if op != C.OP_GENERATE or dest != o.dest_addr:
                    V['decode_mismatch'] += 1
            elif o.op_type == 'compute':
                if op != C.OP_COMPUTE or dest != o.dest_addr or a != o.addr_a or b != o.addr_b:
                    V['decode_mismatch'] += 1
            elif o.op_type == 'send':
                if op != C.OP_SEND or dest != o.dest_addr or a != o.addr_a or b != o.dest_gpu:
                    V['decode_mismatch'] += 1
    # 2. writer analysis -- every address below comes from the DECODED IMAGE
    #    word, not from the ScheduledOp, so that a corrupted image is detected.
    #    The ScheduledOp supplies only the tree node the word is meant to serve.
    local_writers = {}
    remote_writers = {}
    for g in range(ge):
        for pos, (o, d) in enumerate(prog_ops[g]):
            i_op, _i_aux, i_dest, i_a, i_b = d
            if i_op in (C.OP_GENERATE, C.OP_COMPUTE):
                local_writers.setdefault((g, i_dest), []).append((pos, o.node))
                if i_dest >= dmem_depth:
                    V['addr_ge_depth'] += 1
                if i_dest == 0:
                    V['identity_written'] += 1
            elif i_op == C.OP_SEND:
                remote_writers.setdefault((i_b, i_dest), []).append((g, o.node))
                if i_dest >= dmem_depth or i_a >= dmem_depth:
                    V['addr_ge_depth'] += 1
                if i_dest == 0:
                    V['identity_written'] += 1
                V['n_send'] += 1
    for k, v in remote_writers.items():
        if len(v) > 1:
            V['multi_remote_write'] += 1
            detail.append(('mrw', k, v[:4]))
        if k in local_writers:
            V['mixed_local_remote'] += 1
            detail.append(('mix', k, local_writers[k][:3], v[:3]))
    allslots = set(a for (g, a) in local_writers) | set(a for (g, a) in remote_writers)
    V['peak_dmem'] = max(allslots) + 1 if allslots else 0
    # 3. C-bind
    for g in range(ge):
        for pos, (o, d) in enumerate(prog_ops[g]):
            if d[0] != C.OP_COMPUTE:
                continue
            V['n_compute'] += 1
            ch = tree.children(o.node)
            exp = [ch[0] if len(ch) > 0 else None, ch[1] if len(ch) > 1 else None]
            got = [d[3], d[4]]        # addr_a, addr_b as EMITTED
            for i in (0, 1):
                e = exp[i]
                addr = got[i]
                if e is None:
                    if addr != 0:
                        V['bind_wrong'] += 1
                        detail.append(('pad', g, o.node, addr))
                    continue
                if ad[e] == g:
                    lw = [(p, n) for (p, n) in local_writers.get((g, addr), []) if p < pos]
                    if not lw:
                        V['missing_slot'] += 1
                        detail.append(('nolw', g, o.node, e, addr))
                        continue
                    last = max(lw)[1]
                    if last != e:
                        V['bind_wrong'] += 1
                        detail.append(('local', g, o.node, 'exp', e, 'got', last, 'addr', addr))
                else:
                    rw = remote_writers.get((g, addr), [])
                    if len(rw) != 1 or rw[0][1] != e:
                        V['bind_wrong'] += 1
                        detail.append(('remote', g, o.node, 'exp', e, 'got', rw[:3], 'addr', addr))
    V['makespan'] = sched.makespan
    return V, detail[:20]


def check(tree, asgn, mapping, ge, topo, hw=C.HW, alu=C.ALU_FADD, dmem_depth=512):
    """Compile then check.  Signature-compatible with T04's abicheck.check."""
    ad, sched, progs = build(tree, asgn, mapping, ge, topo, hw, alu)
    return check_image(tree, ad, sched, progs, ge, dmem_depth)


def violations(V):
    return sum(V[k] for k in COUNTERS)


# ------------------------------------------------------------------ negative
def _mutate(progs, kind):
    """Inject exactly one fault into an emitted image.

    Every mutation edits IMEM WORDS only.  `order_mismatch` is deliberately
    absent: it is a property of the Schedule object rather than of the emitted
    image, so no image edit can provoke it and no control is claimed for it.
    """
    p = {g: list(w) for g, w in progs.items()}

    def words(g):
        return [(i, w, (w >> 60) & 0xF) for i, w in enumerate(p[g])]

    if kind == 'decode_mismatch':
        for g in sorted(p):
            for i, w, op in words(g):
                if op == C.OP_COMPUTE:
                    p[g][i] = w ^ (1 << 40)                        # perturb dest
                    return p
    elif kind == 'identity_written':
        for g in sorted(p):
            for i, w, op in words(g):
                if op in (C.OP_GENERATE, C.OP_COMPUTE):
                    p[g][i] = w & ~(0xFFFF << 40)                  # dest := slot 0
                    return p
    elif kind == 'addr_ge_depth':
        for g in sorted(p):
            for i, w, op in words(g):
                if op == C.OP_COMPUTE:
                    p[g][i] = (w & ~(0xFFFF << 40)) | (4095 << 40)  # dest beyond CN_DMEM
                    return p
    elif kind == 'missing_slot':
        for g in sorted(p):
            for i, w, op in words(g):
                if op == C.OP_COMPUTE:
                    aa = (w >> 24) & 0xFFFF
                    p[g][i] = (w & ~(0xFFFF << 24)) | (((aa + 7) & 0xFFFF) << 24)
                    return p
    elif kind == 'bind_wrong':
        # Repoint one COMPUTE operand at a slot that IS locally written, but by
        # a different tree node -- a live mis-binding, not a dangling read.
        for g in sorted(p):
            written = []
            for i, w, op in words(g):
                if op == C.OP_COMPUTE:
                    aa = (w >> 24) & 0xFFFF
                    ab = (w >> 8) & 0xFFFF
                    alt = [d for d in written if d not in (aa, ab, 0)]
                    if alt:
                        p[g][i] = (w & ~(0xFFFF << 24)) | (alt[-1] << 24)
                        return p
                if op in (C.OP_GENERATE, C.OP_COMPUTE):
                    written.append((w >> 40) & 0xFFFF)
    elif kind == 'multi_remote_write':
        # Aim a second SEND at a slot another SEND already targets on the same PE.
        seen = {}
        for g in sorted(p):
            for i, w, op in words(g):
                if op != C.OP_SEND:
                    continue
                tgt = (w >> 8) & 0xFFFF
                dst = (w >> 40) & 0xFFFF
                if tgt in seen and seen[tgt] != dst:
                    p[g][i] = (w & ~(0xFFFF << 40)) | (seen[tgt] << 40)
                    return p
                seen.setdefault(tgt, dst)
    elif kind == 'mixed_local_remote':
        # Aim a SEND at a slot the receiving PE also writes locally.
        local = {}
        for g in sorted(p):
            for i, w, op in words(g):
                if op in (C.OP_GENERATE, C.OP_COMPUTE):
                    local.setdefault(g, set()).add((w >> 40) & 0xFFFF)
        for g in sorted(p):
            for i, w, op in words(g):
                if op != C.OP_SEND:
                    continue
                tgt = (w >> 8) & 0xFFFF
                cand = sorted(x for x in local.get(tgt, ()) if x != 0)
                if cand:
                    p[g][i] = (w & ~(0xFFFF << 40)) | (cand[0] << 40)
                    return p
    elif kind == 'dropword':
        for g in sorted(p):
            for i, w, op in words(g):
                if op != C.OP_NOP:
                    del p[g][i]
                    return p
    raise RuntimeError('mutation %r could not be applied' % kind)


NEG_KINDS = [('decode_mismatch', 'decode_mismatch'),
             ('identity_written', 'identity_written'),
             ('addr_ge_depth', 'addr_ge_depth'),
             ('missing_slot', 'missing_slot'),
             ('bind_wrong', 'bind_wrong'),
             ('multi_remote_write', 'multi_remote_write'),
             ('mixed_local_remote', 'mixed_local_remote'),
             ('dropword', 'decode_mismatch')]


def negative_control(n=32, g=4, topo_name='hypercube', verbose=True):
    tree = C.CBTree(n)
    topo = C.build_topology(topo_name, g)
    ge = min(g, tree.total_nodes)
    _, f2 = C.STAGE2_METHODS['2b']
    asgn = f2(tree, ge, topo, C.HW)
    mapping = C.map_identity(tree, asgn, ge, topo, C.HW)
    ad, sched, progs = build(tree, asgn, mapping, ge, topo)
    base, _ = check_image(tree, ad, sched, progs, ge)
    ok = violations(base) == 0
    if verbose:
        print('  baseline N=%d G=%d %s: violations=%d (compute=%d send=%d peak_dmem=%d)'
              % (n, g, topo_name, violations(base), base['n_compute'],
                 base['n_send'], base['peak_dmem']))
    if not ok:
        return False
    allfired = True
    for kind, counter in NEG_KINDS:
        mut = _mutate(progs, kind)
        V, _ = check_image(tree, ad, sched, mut, ge)
        fired = V[counter] > base[counter]
        allfired = allfired and fired
        if verbose:
            print('    inject %-18s -> %-18s %s'
                  % (kind, '%s=%d' % (counter, V[counter]),
                     'FIRES' if fired else 'DID NOT FIRE'))
    return allfired


# ------------------------------------------------------------------ sweeps
SMOKE = [(32, 4, 'hypercube'), (128, 8, 'mesh'), (512, 16, 'torus'),
         (1024, 32, 'fat_tree'), (256, 2, 'linear')]
SMOKE_S2 = ['2a', '2b', '2j', '2k']


def run_sweep(configs, s2s, verbose=True, per_deadline=120):
    tot_cfg = tot_cmp = tot_viol = 0
    peak = 0
    for n, g, tname in configs:
        tree = C.CBTree(n)
        topo = C.build_topology(tname, g)
        ge = min(g, tree.total_nodes)
        for s2 in s2s:
            try:
                C._set_deadline(per_deadline)
                _, f2 = C.STAGE2_METHODS[s2]
                asgn = f2(tree, ge, topo, C.HW)
                C._set_deadline(None)
            except (C.AlgoTimeout, C.AlgoBypassed):
                C._set_deadline(None)
                continue
            except Exception as e:                       # noqa: BLE001
                C._set_deadline(None)
                print('  N=%-5d G=%-4d %-10s s2=%-3s SKIP (%s)'
                      % (n, g, tname, s2, type(e).__name__))
                continue
            ad = asgn if isinstance(asgn, dict) else {i: asgn[i] for i in range(tree.total_nodes)}
            mapping = C.map_identity(tree, ad, ge, topo, C.HW)
            V, det = check_image(tree, ad, *build(tree, ad, mapping, ge, topo)[1:], ge=ge)
            v = violations(V)
            tot_cfg += 1
            tot_cmp += V['n_compute']
            tot_viol += v
            peak = max(peak, V['peak_dmem'])
            if verbose and (v or os.environ.get('ABI_VERBOSE')):
                print('  N=%-5d G=%-4d %-10s s2=%-3s violations=%d %s'
                      % (n, g, tname, s2, v, det[:2] if v else ''))
    if verbose:
        print('  configurations checked: %d   COMPUTEs checked: %d   peak DMEM slot: %d'
              % (tot_cfg, tot_cmp, peak))
        print('  ABI violations: %d' % tot_viol)
    return tot_cfg, tot_cmp, tot_viol


def full_configs():
    seen = []
    for entry in C.TEST_INSTANCES:
        n, g, t, lab = entry[0], entry[1], entry[2], entry[3]
        seen.append((n, g, t))
    return seen


def main(argv):
    mode = argv[1] if len(argv) > 1 else '--smoke'
    quiet = '--quiet' in argv
    if mode == '--negative':
        return 0 if negative_control(verbose=not quiet) else 1
    if not quiet:
        print('ABI post-conditions on the emitted IMEM image')
    if mode == '--full':
        cfgs, s2s = full_configs(), sorted(C.STAGE2_METHODS)
    else:
        cfgs, s2s = SMOKE, SMOKE_S2
    ncfg, ncmp, nviol = run_sweep(cfgs, s2s, verbose=not quiet)
    fired = negative_control(verbose=not quiet)
    if nviol:
        print('ABI VIOLATED: %d violation(s) over %d configurations' % (nviol, ncfg))
        return 1
    if ncfg == 0:
        print('ABI CHECK RAN ZERO CONFIGURATIONS -- refusing to report success')
        return 1
    if not fired:
        print('ABI CHECKER IS VACUOUS: a negative control did not fire')
        return 1
    if not quiet:
        print('ABI holds over %d configurations / %d COMPUTEs; all negative controls fire.'
              % (ncfg, ncmp))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
