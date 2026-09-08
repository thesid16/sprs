#!/usr/bin/env bash
# =============================================================================
# smoke_test.sh — prove a fresh clone works, in a few minutes.
#
#   ./tools/smoke_test.sh            software only (no Vivado needed)
#   ./tools/smoke_test.sh --with-hw  additionally elaborate and simulate one
#                                    tiny testbench (needs VIVADO_BIN)
#
# This is the check a reviewer runs first. It must be fast and it must fail
# loudly, so every step prints PASS or FAIL and the script exits non-zero on
# the first real problem.
# =============================================================================
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$(pwd)"
export SPRS_ROOT="$ROOT"
FAILED=0

say  () { printf '\n\033[1m== %s\033[0m\n' "$1"; }
ok   () { printf '  [PASS] %s\n' "$1"; }
bad  () { printf '  [FAIL] %s\n' "$1"; FAILED=1; }

say "1. Python and dependencies"
python3 -c 'import sys; assert sys.version_info>=(3,9)' 2>/dev/null \
  && ok "python >= 3.9" || bad "python >= 3.9 required"
python3 -c 'import numpy' 2>/dev/null && ok "numpy" || echo "  [warn] numpy absent — compiler falls back to pure python (slower)"

say "2. Compiler imports and the C extension builds"
python3 - <<'PY' && ok "sprs_core imports" || bad "sprs_core import failed"
import sys, os
sys.path.insert(0, os.path.join(os.environ["SPRS_ROOT"], "src"))
import sprs_core as sc
print(f"  {len(sc.STAGE2_METHODS)} assignment, {len(sc.STAGE3_METHODS)} mapping, "
      f"{len(sc.STAGE4_METHODS)} refinement methods")
print(f"  C extension: {'yes' if sc._CLIB else 'no (pure-python fallback)'}")
PY

say "3. Compile a small instance end to end"
python3 - <<'PY' && ok "compiled N=32, G=4 hypercube" || bad "compilation failed"
import sys, os
sys.path.insert(0, os.path.join(os.environ["SPRS_ROOT"], "src"))
import sprs_core as sc
tree = sc.CBTree(32); topo = sc.build_topology('hypercube', 4)
_, s2f = sc.STAGE2_METHODS['2b']; _, s3f = sc.STAGE3_METHODS['3a']
asgn = s2f(tree, 4, topo, sc.HW)
assert sc._validate_assignment(tree, asgn, 4), "assignment invalid"
mapping = s3f(tree, asgn, 4, topo, sc.HW)
sched = sc.build_schedule(tree, asgn, mapping, 4, topo, sc.HW, alu_op=sc.ALU_FADD)
progs = sc.generate_instructions(tree, topo, sched, sc.HW, alu_op=sc.ALU_FADD)
tb = sc.emit_sv_testbench(tree, topo, progs, assignment=asgn,
                          addr_alloc=sched.addr_alloc, schedule=sched,
                          alu_op=sc.ALU_FADD)
print(f"  makespan {sched.makespan}, {len(tb)} chars of SystemVerilog emitted")
open(os.path.join(os.environ["SPRS_ROOT"], "smoke_tb.sv"), "w").write(tb)
PY

say "4. The ABI holds: same N, different G and topology, same OBSERVED root"
# The root compared here is OBSERVED: tools/exec_image.py parses the emitted
# testbench's own load_instr / load_gci words and executes them against a
# functional model of the compute-node ISA.  It is NOT the EXPECTED localparam,
# which emit_sv_testbench computes from (tree, alu_op) alone and which therefore
# agreed across configurations even when the program image was empty, NOP-ed or
# bit-inverted.  tests/checkers/test_smoke4_negative_control.py is the standing
# proof that this step can now fail.
python3 - <<'PY' && ok "bitwise invariance reproduced (observed roots)" || bad "INVARIANCE VIOLATED"
import sys, os
ROOT = os.environ["SPRS_ROOT"]
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import sprs_core as sc
import exec_image as ex
roots = {}
problems = []
for g, t in [(4,'hypercube'), (8,'fat_tree'), (16,'torus'), (2,'linear')]:
    tree = sc.CBTree(32); topo = sc.build_topology(t, g)
    _, s2f = sc.STAGE2_METHODS['2b']; _, s3f = sc.STAGE3_METHODS['3a']
    asgn = s2f(tree, g, topo, sc.HW)
    mapping = s3f(tree, asgn, g, topo, sc.HW)
    sched = sc.build_schedule(tree, asgn, mapping, g, topo, sc.HW, alu_op=sc.ALU_FADD)
    progs = sc.generate_instructions(tree, topo, sched, sc.HW, alu_op=sc.ALU_FADD)
    tb = sc.emit_sv_testbench(tree, topo, progs, assignment=asgn,
                              addr_alloc=sched.addr_alloc, schedule=sched,
                              alu_op=sc.ALU_FADD)
    obs, exp, info = ex.observed_root(tb)
    key = f"G={g} {t}"
    so = "----------------" if obs is None else f"{obs:016X}"
    print(f"  {key:<18} observed 0x{so}  expected 0x{exp:016X}  "
          f"compute={info['n_compute']} send={info['n_send']} gen={info['n_generate']}")
    if not info["all_done"]:
        problems.append(f"{key}: image did not run to completion "
                        f"(stuck {info['stuck'][:4]}, illegal {list(info['illegal'])[:4]})")
    elif obs is None:
        problems.append(f"{key}: root PE retired no COMPUTE")
    elif obs != exp:
        problems.append(f"{key}: observed 0x{obs:016X} != expected 0x{exp:016X}")
    else:
        roots[key] = obs
assert not problems, "; ".join(problems)
assert len(roots) == 4, f"only {len(roots)} configurations produced a root"
assert len(set(roots.values())) == 1, f"DIVERGENCE: {set(roots.values())}"
PY

say "4b. Compiler post-conditions on the emitted image"
python3 "$ROOT/tools/check_c_leaf.py" --smoke && ok "C-leaf holds on the emitted GCI image" \
  || bad "C-leaf violated"
python3 "$ROOT/tools/validate_abi.py" --smoke && ok "ABI post-conditions hold" \
  || bad "ABI post-condition violated"

say "5. Every published claim re-derives from the released data"
# Log to a private temp file, not a fixed name in /tmp: a world-writable
# /tmp/_vn.log is both a collision and a symlink-follow hazard, and on a shared
# machine another user's leftover file makes this step read someone else's run.
VNLOG=$(mktemp "${TMPDIR:-/tmp}/sprs_verify_numbers.XXXXXX")
python3 tools/verify_numbers.py >"$VNLOG" 2>&1 \
  && ok "$(grep -c '\[OK ' "$VNLOG") claims reproduce" \
  || { bad "claims did not reproduce"; grep -E '\[FAIL|\[MISSING' "$VNLOG" | head; }
rm -f "$VNLOG"

if [ "${1:-}" = "--with-hw" ]; then
  say "6. Hardware simulation of one testbench"
  VB="${VIVADO_BIN:-/opt/Xilinx/2025.2/Vivado/bin}"
  if [ ! -x "$VB/xvlog" ]; then
    echo "  [skip] VIVADO_BIN not found at $VB"
  else
    WD=$(mktemp -d); cp smoke_tb.sv "$WD/"
    MOD=$(grep -m1 -oE '^\s*module\s+tb_sprs_\w+' smoke_tb.sv | awk '{print $2}')
    RTL=$(grep -v '^#' "$ROOT/rtl/filelist.f" | sed "s|^|$ROOT/rtl/|" | tr '\n' ' ')
    ( cd "$WD" && "$VB/xvlog" -sv $RTL smoke_tb.sv >xv.log 2>&1 \
      && "$VB/xelab" -timescale 1ns/1ps -top "$MOD" -snapshot smoke >/dev/null 2>&1 \
      && "$VB/xsim" smoke -R 2>&1 | grep -q '\[PASS\]' ) \
      && ok "RTL simulation passed" \
      || { bad "RTL simulation did not pass"; tail -5 "$WD"/xv.log 2>/dev/null | sed 's/^/    /'; }
    rm -rf "$WD"
  fi
fi

rm -f smoke_tb.sv
echo
if [ "$FAILED" -eq 0 ]; then
  printf '\033[1mSMOKE TEST PASSED\033[0m\n'; exit 0
else
  printf '\033[1mSMOKE TEST FAILED\033[0m\n'; exit 1
fi
