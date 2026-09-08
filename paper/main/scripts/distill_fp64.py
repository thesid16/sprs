#!/usr/bin/env python3
r"""
distill_fp64.py -- vendor the fp64_add effective-subtraction repair round into
paper/data/wround/W3_fp64.json.

Run once, on the machine that holds the artifact tree (rtl/, src/, tests/) and
the two Verilator-built evaluators tests/fp64/obj_EVAL/rtl_eval (repaired RTL)
and tests/fp64/obj_EVALPRE/rtl_eval (as-submitted RTL, built from
tests/fp64/fp64_add.PRE.sv, which is byte-identical to the submitted
rtl/fp64_add.sv).  Everything gen_wround_macros.py needs is written into
data/wround/ so that `make tables` -- and verify_tables.py, which copies the
paper tree to scratch -- reproduces every macro without reaching outside the
release.

Five records are captured, each as the verbatim stdout of one command, so that
gen_wround_macros.py can assert exact substrings and fail the build rather than
typeset a stale number:

  accept_post   test_sw_rtl_equiv.py on the repaired RTL + repaired oracle.
                Two properties on one vector set: accuracy against an
                exact-rational IEEE-754 RNE reference, and bit-for-bit
                equality between src/sprs_core.py::_fp64_add_bits and
                rtl/fp64_add.sv.
  accept_pre    the same test on the as-submitted RTL and the as-submitted
                oracle.  This is the negative control: it must fail.
  variants      sweep.py, the three-variant Python model (no fix / borrow only
                / borrow + lzc==2 rescale) against the exact-rational
                reference.  This is what shows the one-line fix is not enough.
  scope         test_no_published_number_moves.py: the leaf generator is
                strictly positive, so no reported FADD takes the repaired path.
  sweep_post,   tests/logs/fp64_{POST,PRE}_sweep.txt, copied verbatim: the
  sweep_pre     Verilator harness (tests/fp64/main.cpp) scoring the RTL
                against the host FPU's correctly-rounded addition over a
                binade sweep, a uniform sample, directed edge cases and a
                same-sign regression arm.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
DEST = os.path.join(PAPER, "data", "wround")
FIX = os.environ.get("SPRS_FIXTREE", "/home/rohit/sprs-fix")
PRE_CORE = os.environ.get(
    "SPRS_CORE_PRE", "/home/rohit/sprs-review/snapshot/src/sprs_core.py")
FP = os.path.join(FIX, "tests", "fp64")
SCRATCH = os.environ.get("TMPDIR", "/tmp")

os.makedirs(DEST, exist_ok=True)


def run(cmd, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    env["SCRATCH"] = SCRATCH
    p = subprocess.run(cmd, cwd=FP, env=env, capture_output=True, text=True)
    return {"cmd": " ".join(cmd),
            "env": env_extra,
            "cwd": FP,
            "returncode": p.returncode,
            "stdout": p.stdout}


def readfile(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


doc = {
    "round": "W3",
    "what": "fp64_add effective-subtraction defect: repair and revalidation",
    "artifact_tree": FIX,
    "pre_fix_oracle": PRE_CORE,
    "pre_fix_rtl": os.path.join(FP, "fp64_add.PRE.sv"),
    "records": {},
}

doc["records"]["accept_post"] = run(
    [sys.executable, "test_sw_rtl_equiv.py"],
    {"N_DE": "1500", "N_UNIF": "15000",
     "SPRS_CORE": os.path.join(FIX, "src", "sprs_core.py"),
     "RTL_EVAL": os.path.join(FP, "obj_EVAL", "rtl_eval")})

doc["records"]["accept_pre"] = run(
    [sys.executable, "test_sw_rtl_equiv.py"],
    {"N_DE": "600", "N_UNIF": "4000",
     "SPRS_CORE": PRE_CORE,
     "RTL_EVAL": os.path.join(FP, "obj_EVALPRE", "rtl_eval")})

doc["records"]["variants"] = run(
    [sys.executable, "sweep.py"], {"N_DE": "4000", "N_UNIF": "20000"})

doc["records"]["scope"] = run(
    [sys.executable, "test_no_published_number_moves.py"],
    {"SPRS_CORE_PRE": PRE_CORE,
     "SPRS_CORE_POST": os.path.join(FIX, "src", "sprs_core.py")})

for tag, name in (("sweep_post", "fp64_POST_sweep.txt"),
                  ("sweep_pre", "fp64_PRE_sweep.txt")):
    src = os.path.join(FIX, "tests", "logs", name)
    doc["records"][tag] = {"cmd": "tests/fp64/build_and_run.sh (captured log)",
                           "source": src,
                           "returncode": 0,
                           "stdout": readfile(src)}

out = os.path.join(DEST, "W3_fp64.json")
with open(out, "w", encoding="utf-8") as fh:
    json.dump(doc, fh, indent=1)
print("wrote %s" % out)
for k, v in doc["records"].items():
    print("  %-12s rc=%s  %d bytes of stdout" % (k, v["returncode"], len(v["stdout"])))
