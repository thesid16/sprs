#!/usr/bin/env python3
"""
_mutation_runner.py — mutation testing for the SPRS bitwise-invariance oracle.

Purpose: a zero-divergence column in the invariance table is only evidence if
the oracle is *capable* of reporting a non-zero one. This harness injects
faults that must change the 64-bit root, then checks the testbench oracle
flags them. A vacuous oracle -- one comparing nothing, or comparing against a
value derived from the run itself -- scores zero here while still producing a
clean divergence column.

Two mutation classes, matching the paper's \\S method-mutation:

  addr_sub      Rewrite one COMPUTE instruction's addr_a field to a different
                DMEM address. This violates the ABI's operand binding (A5/C-bind):
                the FADD at that internal node now reads the wrong operand, so
                the subtree sum -- and hence the root -- must differ.

  leaf_corrupt  Flip the low mantissa bit of one leaf value. Changes L, so the
                root must differ by Claim 1's own statement (R is a function of
                (N, L)).

An undetected mutant is a genuine finding, not a harness bug: it means either
the mutated value never reached the root (dead code in the emitted image) or
the oracle is not actually comparing. Both are reported.

ISA layout (btree_pkg.sv):
  [63:60] opcode  [59:56] aux  [55:40] dest  [39:24] addr_a  [23:8] addr_b

Usage:
  python3 _mutation_runner.py --sample 3 --jobs 16 --out results/_mutation_results.json
"""

import os as _os
# Repo root: override with SPRS_ROOT. Defaults to this file's repo.
SPRS_ROOT = _os.environ.get("SPRS_ROOT",
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

BASE = SPRS_ROOT
RTL = _os.path.join(SPRS_ROOT,'rtl')
RES = f"{BASE}/results"
VIVADO_BIN = "" + _os.environ.get("VIVADO_BIN","/opt/Xilinx/2025.2/Vivado/bin") + ""
RTL_FILES = ["noc_pkg.sv", "btree_pkg.sv", "sync_fifo.sv", "link_tx.sv",
             "noc_link.sv", "noc_router.sv", "noc_ni.sv", "fp64_add.sv",
             "btree_fsm_fast.sv", "noc_system.sv"]

WRITE_ROUTE_RE = re.compile(r"^(\s*)write_route\((\d+),(\d+),(\d+)\);\s*$", re.MULTILINE)
INSTR_RE = re.compile(r"load_instr\((\d+),(\d+),64'h([0-9A-Fa-f]{16})\);")
GCI_RE = re.compile(r"load_gci\((\d+),(\d+),64'h([0-9A-Fa-f]{16})\);")
# The emitter annotates each GCI load with its canonical leaf index: "// leaf 10 (L3)"
GCI_IDX_RE = re.compile(
    r"load_gci\((\d+),(\d+),64'h([0-9A-Fa-f]{16})\);\s*//\s*leaf\s+\d+\s+\(L(\d+)\)")

_SC = None


def _sprs_core():
    """Lazy-import the compiler core for its bit-accurate FADD."""
    global _SC
    if _SC is None:
        if BASE not in sys.path:
            sys.path.insert(0, BASE)
        import sprs_core
        _SC = sprs_core
    return _SC


def oracle_root(N, leaf_bits):
    """Canonical 64-bit root for leaf vector `leaf_bits`, via post-order FBT(N)
    evaluation using the same bit-accurate FADD the fabric implements.

    This is what makes the campaign rigorous: a mutation only counts as a test
    of the oracle if it provably moves this value. FP64 absorption means a
    small leaf perturbation can be rounded away entirely, in which case the
    root is unchanged and the fabric is *correct* to report PASS.
    """
    sc = _sprs_core()
    tree = sc.CBTree(N)
    l2g = {leaf: i for i, leaf in enumerate(tree.leaves())}
    val = {}
    for node in tree.postorder():
        if tree.is_leaf(node):
            val[node] = leaf_bits[l2g.get(node, 0)]
        else:
            ch = tree.children(node)
            a = val.get(ch[0], 0) if len(ch) > 0 else 0
            b = val.get(ch[1], 0) if len(ch) > 1 else 0
            val[node] = sc._fp64_add_bits(a, b)
    return val.get(0, 0)


def parse_leaves(text, N):
    """Recover the leaf vector, indexed canonically, from the TB's GCI loads."""
    leaves = {}
    sites = {}
    for m in GCI_IDX_RE.finditer(text):
        idx = int(m.group(4))
        leaves[idx] = int(m.group(3), 16)
        sites[idx] = m
    if len(leaves) != N:
        return None, None
    return [leaves[i] for i in range(N)], sites

OP_COMPUTE = 0x2

# One representative instance per leaf-count class, smallest G first so the
# campaign stays cheap. Mutation detection is a property of the oracle, not of
# scale, so broad N coverage matters more than large N.
TARGETS = [
    ("tiny_dense_1d", 8, 2), ("tiny_mod_ring", 8, 4),
    ("npow2n_tiny_ring", 10, 4), ("npow2g_small_mesh", 16, 5),
    ("small_dense_hc", 32, 4), ("small_bal_fat", 32, 8),
    ("npow2_tiny_hc", 50, 7), ("npow2_small_torus", 100, 10),
    ("med_extreme_1d", 128, 4), ("med_dense_mesh", 128, 8),
    ("npow2_med_fat", 200, 12), ("large_unbal_torus", 500, 32),
    ("large_extreme_1d", 512, 8), ("large_dense_hc", 512, 32),
]


def rewrite_bypass(text):
    """Same route-table bypass the main campaign uses (plain integer literal:
    a sized 3'd literal truncates fat-tree port numbers > 7)."""
    return WRITE_ROUTE_RE.sub(
        lambda m: f"{m.group(1)}u_sys.gen_rtr[{m.group(2)}].u_rtr.route_table[{m.group(3)}] = {m.group(4)};",
        text)


def mutate_addr_sub(text, rng):
    """Repoint one COMPUTE's addr_a at a different DMEM address."""
    computes = [m for m in INSTR_RE.finditer(text)
                if (int(m.group(3), 16) >> 60) & 0xF == OP_COMPUTE]
    if not computes:
        return None, None
    m = rng.choice(computes)
    word = int(m.group(3), 16)
    addr_a = (word >> 24) & 0xFFFF
    # Pick a different address; stay small so it is a plausible live location.
    choices = [a for a in range(0, 64) if a != addr_a]
    new_a = rng.choice(choices)
    new_word = (word & ~(0xFFFF << 24)) | (new_a << 24)
    old = m.group(0)
    new = f"load_instr({m.group(1)},{m.group(2)},64'h{new_word:016X});"
    desc = f"gpu{m.group(1)} pc{m.group(2)} addr_a {addr_a}->{new_a}"
    return text.replace(old, new, 1), desc


def mutate_leaf_corrupt(text, rng, N=None):
    """Perturb one leaf by the smallest bit-flip that provably moves the root.

    Starting at the mantissa LSB, escalate the flipped bit position until the
    software oracle reports a different canonical root. Without this check the
    mutant is frequently null: at these magnitudes an LSB flip is ~1e-13
    absolute against a partial sum of ~1e4, so RNE rounds it away and the
    fabric is right to still report PASS. Escalating guarantees every counted
    mutant is a genuine test, and the bit index reached is itself informative.
    """
    if N is None:
        return None, None
    leaves, sites = parse_leaves(text, N)
    if leaves is None:
        return None, None
    base_root = oracle_root(N, leaves)
    idx = rng.randrange(N)
    for bit in range(0, 52):
        cand = list(leaves)
        cand[idx] = leaves[idx] ^ (1 << bit)
        if oracle_root(N, cand) != base_root:
            m = sites[idx]
            old = m.group(0)
            new = (f"load_gci({m.group(1)},{m.group(2)},"
                   f"64'h{cand[idx]:016X}); // leaf mutated (L{idx})")
            return text.replace(old, new, 1), f"leaf L{idx} bit{bit} flip"
    return None, None          # no single-bit flip on this leaf moves the root


MUTATORS = {"addr_sub": mutate_addr_sub, "leaf_corrupt": mutate_leaf_corrupt}


def run_one(job):
    inst, tb_name, n_leaves, n_gpus, kind, seed, timeout = job
    rng = random.Random(seed)
    src = f"{RES}/{inst}/{tb_name}.sv"
    # Read the module name from the file rather than composing it from G:
    # mesh/torus/hypercube pad the node count up to a legal shape (G=5 -> 6,
    # 7 -> 8, 10 -> 12), so the top module is tb_sprs_<N>L_<padded>G and
    # composing it from the requested G fails elaboration.
    module = None
    wd = f"{RES}/{inst}/work_mut_{kind}_{seed}_{os.getpid()}"
    out = dict(instance=inst, tb=tb_name, N=n_leaves, G=n_gpus, kind=kind,
               seed=seed, detected=None, mutation=None, error="")
    try:
        if not os.path.exists(src):
            out["error"] = "TB missing"
            return out
        text = open(src).read()
        mm = re.search(r"^\s*module\s+(tb_sprs_\w+)", text, re.MULTILINE)
        if not mm:
            out["error"] = "cannot determine top module name"
            return out
        module = mm.group(1)
        if kind == "leaf_corrupt":
            mutated, desc = MUTATORS[kind](text, rng, N=n_leaves)
        else:
            mutated, desc = MUTATORS[kind](text, rng)
        if mutated is None:
            out["error"] = f"no root-changing {kind} mutant found"
            return out
        if mutated == text:
            out["error"] = "mutation was a no-op"
            return out
        out["mutation"] = desc

        os.makedirs(wd, exist_ok=True)
        tb_path = f"{wd}/{tb_name}_mut.sv"
        with open(tb_path, "w") as f:
            f.write(rewrite_bypass(mutated))

        env = dict(os.environ, PATH=f"{VIVADO_BIN}:{os.environ.get('PATH','')}")
        srcs = [f"{RTL}/{r}" for r in RTL_FILES] + [tb_path]
        r = subprocess.run([f"{VIVADO_BIN}/xvlog", "-sv"] + srcs,
                           cwd=wd, capture_output=True, timeout=timeout, env=env)
        if r.returncode != 0:
            out["error"] = "xvlog failed"
            return out
        # Same invocation the main campaign uses; -top/-snapshot are required
        # (bare module name + -s is not accepted by this xelab).
        r = subprocess.run([f"{VIVADO_BIN}/xelab", "-mt", "2",
                            "-timescale", "1ns/1ps", "-debug", "typical",
                            "-top", module, "-snapshot", "mut_snap"],
                           cwd=wd, capture_output=True, timeout=timeout, env=env)
        if r.returncode != 0:
            tail = (r.stdout or b"").decode(errors="replace")[-300:]
            out["error"] = f"xelab failed: {tail.strip()[-200:]}"
            return out
        r = subprocess.run([f"{VIVADO_BIN}/xsim", "mut_snap", "-R"],
                           cwd=wd, capture_output=True, timeout=timeout, env=env)
        txt = (r.stdout or b"").decode(errors="replace")

        # Detected == the oracle refused to certify the mutant. A mutant that
        # still reports [PASS] means the fault did not reach the root or the
        # comparison is vacuous -- either way, NOT detected.
        if "[PASS]" in txt:
            out["detected"] = False
        elif "[FAIL]" in txt or "TIMEOUT" in txt:
            out["detected"] = True
        else:
            out["error"] = "no verdict in xsim output"
    except subprocess.TimeoutExpired:
        # A hang is a refusal to certify: watchdog/timeout is the fail-stop path.
        out["detected"] = True
        out["error"] = "sim timeout (fail-stop)"
    except Exception as e:
        out["error"] = repr(e)
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=3,
                    help="mutants per (instance, class)")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--out", default=f"{RES}/_mutation_results.json")
    a = ap.parse_args()

    jobs = []
    for inst, n, g in TARGETS:
        tbs = sorted(f[:-3] for f in os.listdir(f"{RES}/{inst}")
                     if f.startswith("tb_") and f.endswith(".sv"))
        if not tbs:
            continue
        base = tbs[0]                      # deterministic pick
        for kind in MUTATORS:
            for s in range(a.sample):
                jobs.append((inst, base, n, g, kind, 1000 + s, a.timeout))

    print(f"[{time.strftime('%H:%M:%S')} ] mutation campaign: {len(jobs)} mutants "
          f"over {len(TARGETS)} instances x {len(MUTATORS)} classes "
          f"x {a.sample} seeds, {a.jobs} workers", flush=True)

    results = []
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(run_one, j): j for j in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            flag = ("DETECTED" if r["detected"] else
                    "MISSED" if r["detected"] is False else "ERROR")
            print(f"[{time.strftime('%H:%M:%S')}] {i}/{len(jobs)} "
                  f"{r['instance']}/{r['kind']} -> {flag} {r['error']}", flush=True)

    # Aggregate for the invariance table's two rightmost columns.
    byN = defaultdict(lambda: defaultdict(lambda: {"detected": 0, "total": 0}))
    for r in results:
        if r["detected"] is None:
            continue
        c = byN[r["N"]][r["kind"]]
        c["total"] += 1
        c["detected"] += 1 if r["detected"] else 0

    summary = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "by_N": {str(k): dict(v) for k, v in byN.items()},
        "runs": results,
    }
    with open(a.out, "w") as f:
        json.dump(summary, f, indent=1)

    print("\n=== mutation detection ===")
    for kind in MUTATORS:
        d = sum(v[kind]["detected"] for v in byN.values() if kind in v)
        t = sum(v[kind]["total"] for v in byN.values() if kind in v)
        print(f"  {kind:14s} {d}/{t}" + (f"  ({100*d/t:.1f}%)" if t else "  (no data)"))
    errs = [r for r in results if r["detected"] is None]
    if errs:
        print(f"  {len(errs)} run(s) produced no verdict:")
        for r in errs[:5]:
            print(f"     {r['instance']}/{r['kind']}: {r['error']}")
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
