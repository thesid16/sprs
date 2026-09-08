#!/usr/bin/env python3
"""Functional execution of an EMITTED SPRS testbench image.

Why this exists
---------------
tools/smoke_test.sh step 4 used to assert that four emitted testbenches carried
the same `EXPECTED` localparam.  `EXPECTED` is computed inside
emit_sv_testbench from `tree` and `alu_op` alone -- the assignment, the mapping,
the topology, the schedule and the emitted instruction words never enter it.
The assertion was therefore a pure function evaluated four times, and it passed
with every program emptied, NOP-ed, or bit-inverted.

This module supplies the missing half: it reads the EMITTED BYTES of the
testbench -- the `load_instr` words, the `load_gci` payloads, the per-PE
`imem_size` -- and executes them, producing an OBSERVED root that can disagree
with EXPECTED.

Fidelity and scope (stated plainly, because an over-claimed checker is the
defect this replaces)
---------------------------------------------------------------------------
This is a FUNCTIONAL, UNTIMED model of the compute-node ISA:

  * DMEM per PE, `dmem_depth` words, zero at reset; address 0 is the identity
    element and its scoreboard bit is set at reset (rtl/btree_fsm_fast.sv:709).
  * A per-PE scoreboard bit per DMEM address, set by every write, whether from
    GENERATE, COMPUTE or an arriving remote SEND (rtl/btree_fsm_fast.sv:704-720).
  * COMPUTE stalls while either operand's scoreboard bit is clear
    (rtl/btree_fsm_fast.sv:513-521); SEND stalls while its source bit is clear.
  * GENERATE pops the next word from that PE's GCI buffer, in order.
  * DMEM addresses are truncated to DMEM_ADDR_W bits exactly as the RTL does,
    so address aliasing is reproduced rather than hidden.
  * `result` is the value written by the LAST COMPUTE that PE retired
    (rtl/btree_fsm_fast.sv:806/833), which is what the emitted testbench
    compares against EXPECTED.

It does NOT model: cycle timing, NOC routing, credits, VCs, watchdogs, or the
NOP padding the GCI latency requires.  It cannot replace RTL simulation and is
not offered as one.  What it can do is detect a program image that computes the
wrong value or cannot make progress -- which is precisely what step 4 claimed
to be doing and was not.

CLI:
    python3 tools/exec_image.py <tb.sv> [...]      # prints OBSERVED per file
"""
import re
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), 'src')
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

OP_NOP, OP_GENERATE, OP_COMPUTE, OP_SEND = 0x0, 0x1, 0x2, 0x3

_RE_INSTR = re.compile(r"load_instr\((\d+),(\d+),64'h([0-9A-Fa-f]{16})\)")
_RE_GCI = re.compile(r"load_gci\((\d+),(\d+),64'h([0-9A-Fa-f]{16})\)")
_RE_ISIZE = re.compile(r"imem_size\[(\d+)\]\s*=\s*(\d+)\s*;")
_RE_ROOT = re.compile(r"root_gpu=(\d+)\s")
_RE_EXPECTED = re.compile(r"EXPECTED\s*=\s*64'h([0-9A-Fa-f]{16})")
_RE_CN_DMEM = re.compile(r"\.CN_DMEM\((\d+)\)")


class ImageError(RuntimeError):
    pass


def parse_image(tb_text):
    """Pull the loadable image out of an emitted testbench."""
    imem = {}
    for g, a, w in _RE_INSTR.findall(tb_text):
        imem.setdefault(int(g), {})[int(a)] = int(w, 16)
    gci = {}
    for g, a, w in _RE_GCI.findall(tb_text):
        gci.setdefault(int(g), {})[int(a)] = int(w, 16)
    isize = {int(g): int(n) for g, n in _RE_ISIZE.findall(tb_text)}
    m = _RE_ROOT.search(tb_text)
    if not m:
        raise ImageError('no root_gpu marker in testbench')
    root_gpu = int(m.group(1))
    m = _RE_EXPECTED.search(tb_text)
    expected = int(m.group(1), 16) if m else None
    m = _RE_CN_DMEM.search(tb_text)
    dmem_depth = int(m.group(1)) if m else 512
    progs = {}
    for g, words in imem.items():
        n = isize.get(g, max(words) + 1 if words else 0)
        progs[g] = [words.get(i, 0) for i in range(n)]
    gcis = {}
    for g, words in gci.items():
        gcis[g] = [words.get(i, 0) for i in range(max(words) + 1)] if words else []
    return dict(progs=progs, gci=gcis, root_gpu=root_gpu,
                expected=expected, dmem_depth=dmem_depth)


def _decode(w):
    return ((w >> 60) & 0xF, (w >> 56) & 0xF, (w >> 40) & 0xFFFF,
            (w >> 24) & 0xFFFF, (w >> 8) & 0xFFFF)


def execute(image, fadd=None, max_rounds=None):
    """Run the parsed image to quiescence.

    Returns a dict with 'observed' (the last COMPUTE result on root_gpu, or
    None if that PE never retired a COMPUTE), plus progress diagnostics.
    """
    if fadd is None:
        import sprs_core as _sc
        fadd = _sc._fp64_add_bits
    progs = image['progs']
    gci = image['gci']
    depth = image['dmem_depth']
    amask = depth - 1
    if depth & amask:
        raise ImageError('DMEM depth %d is not a power of two' % depth)

    pes = sorted(progs)
    dmem = {g: [0] * depth for g in pes}
    valid = {g: [False] * depth for g in pes}
    for g in pes:
        valid[g][0] = True                     # DMEM[0] identity, valid at reset
    pc = {g: 0 for g in pes}
    gp = {g: 0 for g in pes}
    last_compute = {g: None for g in pes}
    illegal = {}
    n_compute = n_send = n_generate = 0
    aliased = 0
    gci_overrun = 0

    if max_rounds is None:
        max_rounds = 4 * (sum(len(p) for p in progs.values()) + 16)

    def alu(op_aux, a, b):
        alu_op = (op_aux >> 1) & 0x7
        if alu_op == 0b111:
            return fadd(a, b)
        if alu_op == 0b001:
            sa = a - (1 << 64) if a >> 63 else a
            sb = b - (1 << 64) if b >> 63 else b
            return a if sa > sb else b
        if alu_op == 0b010:
            sa = a - (1 << 64) if a >> 63 else a
            sb = b - (1 << 64) if b >> 63 else b
            return a if sa < sb else b
        if alu_op == 0b011:
            return a & b
        if alu_op == 0b100:
            return a | b
        if alu_op == 0b101:
            return a ^ b
        return (a + b) & 0xFFFFFFFFFFFFFFFF     # ADD and SADD share the adder

    rounds = 0
    while rounds < max_rounds:
        rounds += 1
        progressed = False
        for g in pes:
            if g in illegal:
                continue
            prog = progs[g]
            while pc[g] < len(prog):
                w = prog[pc[g]]
                op, aux, dest, aa, ab = _decode(w)
                d = dest & amask
                if dest > amask:
                    aliased += 1
                if op == OP_NOP:
                    pc[g] += 1
                    progressed = True
                    continue
                if op == OP_GENERATE:
                    buf = gci.get(g, [])
                    if gp[g] >= len(buf):
                        gci_overrun += 1
                        val = 0
                    else:
                        val = buf[gp[g]]
                    gp[g] += 1
                    dmem[g][d] = val
                    valid[g][d] = True
                    n_generate += 1
                    pc[g] += 1
                    progressed = True
                    continue
                if op == OP_COMPUTE:
                    a_i, b_i = aa & amask, ab & amask
                    if aa > amask or ab > amask:
                        aliased += 1
                    if not (valid[g][a_i] and valid[g][b_i]):
                        break                     # scoreboard stall
                    r = alu(aux, dmem[g][a_i], dmem[g][b_i])
                    dmem[g][d] = r
                    valid[g][d] = True
                    last_compute[g] = r
                    n_compute += 1
                    pc[g] += 1
                    progressed = True
                    continue
                if op == OP_SEND:
                    s_i = aa & amask
                    if aa > amask:
                        aliased += 1
                    if not valid[g][s_i]:
                        break                     # source not ready
                    tgt = ab
                    if tgt not in dmem:
                        illegal[g] = (pc[g], 'send-to-unknown-PE-%d' % tgt)
                        break
                    dmem[tgt][d] = dmem[g][s_i]
                    valid[tgt][d] = True
                    n_send += 1
                    pc[g] += 1
                    progressed = True
                    continue
                # Illegal opcode: rtl/btree_fsm_fast.sv:637 falls through to the
                # default arm and the FSM enters P_ERROR (:867), halting that PE.
                illegal[g] = (pc[g], op)
                break
        if not progressed:
            break

    stuck = [g for g in pes if pc[g] < len(progs[g])]
    return dict(observed=last_compute.get(image['root_gpu']),
                stuck=stuck, rounds=rounds, illegal=illegal,
                n_compute=n_compute, n_send=n_send, n_generate=n_generate,
                aliased=aliased, gci_overrun=gci_overrun,
                all_done=(not stuck) and not illegal)


def observed_root(tb_text, fadd=None):
    """Convenience: parse + execute, return (observed, expected, info)."""
    img = parse_image(tb_text)
    info = execute(img, fadd=fadd)
    return info['observed'], img['expected'], info


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    rc = 0
    for path in argv[1:]:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            txt = fh.read()
        obs, exp, info = observed_root(txt)
        so = 'None' if obs is None else '%016X' % obs
        se = 'None' if exp is None else '%016X' % exp
        agree = (obs is not None and obs == exp and info['all_done'])
        print('%s  OBSERVED=0x%s  EXPECTED=0x%s  all_done=%s  compute=%d send=%d gen=%d  %s'
              % (path, so, se, info['all_done'], info['n_compute'], info['n_send'],
                 info['n_generate'], 'OK' if agree else 'MISMATCH'))
        if not agree:
            rc = 1
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv))
