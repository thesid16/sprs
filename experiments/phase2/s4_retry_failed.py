#!/usr/bin/env python3
"""
Retry failed tasks from a completed s4_phase2_setup.py run.
Identifies tasks with GEN_FAILED status in checkpoint and retries with fresh workers.
"""
import copy
import hashlib
import json
import os
import sys
import time
import argparse
import importlib.util
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

BASE = "."
RES = os.path.join(BASE, "results")
TOURN_PATH = os.path.join(BASE, "sprs_tournament (1).py")

def _load_tournament_module():
    if BASE not in sys.path:
        sys.path.insert(0, BASE)
    spec = importlib.util.spec_from_file_location("sprs_tournament_p2", TOURN_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sprs_tournament_p2"] = mod
    spec.loader.exec_module(mod)
    return mod

TOURN = _load_tournament_module()
S3_KEYS = sorted(TOURN.STAGE3_METHODS.keys())
INST_META = {ilabel: (n, g, tname) for (n, g, tname, ilabel) in TOURN.TEST_INSTANCES}
REFINERS = ["4c2", "4j", "4g"]

def _task_key(t):
    s2, s3, s4, n, g, tname, ilabel, st = t
    return f"{ilabel}\t{s2}\t{s3}\t{s4}"

def _load_checkpoint(path):
    ck = {}
    if not path or not os.path.exists(path):
        return ck
    with open(path) as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                ck[data.get("_key")] = data.get("result", {})
            except:
                pass
    return ck

def _s4_full_worker(task):
    """Exact copy from s4_phase2_setup.py."""
    s2, s3, s4, n, g, tname, ilabel, sim_timeout = task
    hw = TOURN.HW
    alu_op = TOURN.ALU_FADD
    t0 = time.time()

    row = dict.fromkeys(TOURN.SW_COLUMNS, '')
    row.update(pipeline=f"{s2}|{s3}|{s4}", s2=s2, s3=s3, s4=s4,
               makespan=-1, valid=False, unique_hw_sim=False)

    TOURN._set_eval_deadline(TOURN.EVAL_TIMEOUT)
    try:
        tree = TOURN.CBTree(n)
        topo = TOURN.build_topology(tname, g)
        ge = min(g, tree.total_nodes)
        ctx = TOURN.get_ctx(tree, topo)

        _, s2f = TOURN.STAGE2_METHODS[s2]
        _, s3f = TOURN.STAGE3_METHODS[s3]
        _, s4f = TOURN.STAGE4_METHODS[s4]

        asgn_base = s2f(tree, ge, topo, hw)
        if not TOURN._validate_assignment(tree, asgn_base, ge):
            return {"error": "S2_bad"}

        asgn = s4f(tree, copy.deepcopy(asgn_base), ge, topo, hw)
        if not TOURN._validate_assignment(tree, asgn, ge):
            asgn = asgn_base

        mapping = s3f(tree, asgn, ge, topo, hw)
        cp = ctx.fast_cp_comm(asgn)
        ml = ctx.fast_max_load(asgn, ge)
        li = ctx.fast_load_imbalance(asgn, ge)
        ec = ctx.fast_edge_cut(asgn)
        conn = TOURN.is_connected_partition(tree, asgn, ge)
        n_used = len(set(asgn[i] if isinstance(asgn, list) else asgn.get(i, 0)
                         for i in range(tree.total_nodes)))
        ahash = TOURN._hash_assignment(asgn, tree.total_nodes)

        sched = TOURN.build_schedule(tree, asgn, mapping, ge, topo, hw, alu_op=alu_op)
        ms_sched = sched.makespan
        ms = ms_sched if ms_sched > 0 else max(cp, ml)

        progs = TOURN.generate_instructions(tree, topo, sched, hw, alu_op=alu_op)
        max_imem = max(len(progs[gpu]) for gpu in progs) if progs else 0

        tb_sv = TOURN.emit_sv_testbench(
            tree, topo, progs, assignment=asgn, addr_alloc=sched.addr_alloc,
            schedule=sched, alu_op=alu_op)
        tb_hash = hashlib.sha256(tb_sv.encode()).hexdigest()

        return {"tb_hash": tb_hash, "tb_code": tb_sv}
    except TOURN.AlgoBypassed as e:
        return {"error": str(e)}
    except TOURN.AlgoTimeout:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:100]}"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="results/_s4_tbgen_checkpoint.jsonl")
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()

    print(f"Loading checkpoint: {args.checkpoint}")
    ck = _load_checkpoint(args.checkpoint)
    print(f"  Total tasks in checkpoint: {len(ck)}")

    # Identify failed tasks: either no tb_hash, or crash/timeout errors
    failed_keys = set()
    for k, v in ck.items():
        if not v.get("tb_hash"):
            failed_keys.add(k)

    # Specifically retry crash and timeout errors (highest priority to recover)
    crash_keys = {k for k, v in ck.items() if "BrokenProcessPool" in v.get("error", "")}
    timeout_keys = {k for k, v in ck.items() if v.get("error") == "timeout"}

    print(f"  Failed tasks (no tb_hash): {len(failed_keys)}")
    print(f"    Crashes: {len(crash_keys)}")
    print(f"    Timeouts: {len(timeout_keys)}")
    print(f"    Other: {len(failed_keys) - len(crash_keys) - len(timeout_keys)}")

    # Rebuild task list and filter to failed ones
    all_tasks = []
    inst_tasks_map = {}

    for inst in sorted(INST_META.keys()):
        n, g, tname = INST_META[inst]
        inst_tasks = []
        for s2 in sorted(TOURN.STAGE2_METHODS.keys()):
            for s4 in REFINERS:
                for s3 in S3_KEYS:
                    t = (s2, s3, s4, n, g, tname, inst, 28800)
                    key = _task_key(t)
                    if key in failed_keys:
                        inst_tasks.append(len(all_tasks))
                        all_tasks.append(t)
        if inst_tasks:
            inst_tasks_map[inst] = inst_tasks

    print(f"  Tasks to retry: {len(all_tasks)}")
    if not all_tasks:
        print("No failed tasks to retry.")
        return

    # Run with workers
    print(f"\nRunning {len(all_tasks)} failed tasks with {args.workers} workers...")
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(_s4_full_worker, t): i for i, t in enumerate(all_tasks)}
        done = 0
        for fut in as_completed(futures):
            done += 1
            if done % 200 == 0 or done == len(all_tasks):
                print(f"  {done}/{len(all_tasks)} done")

            i = futures[fut]
            result = fut.result()
            key = _task_key(all_tasks[i])

            # Append to checkpoint
            with open(args.checkpoint, "a") as f:
                json.dump({"_key": key, "result": result}, f)
                f.write("\n")
                f.flush()

    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s")

    # Recount
    ck_new = _load_checkpoint(args.checkpoint)
    failed_new = {k for k, v in ck_new.items() if not v.get("tb_hash")}
    print(f"\nCheckpoint updated:")
    print(f"  Total tasks: {len(ck_new)}")
    print(f"  Still failed: {len(failed_new)}")
    print(f"  Recovered: {len(failed_keys) - len(failed_new)}")

if __name__ == "__main__":
    main()
