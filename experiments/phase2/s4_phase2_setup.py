#!/usr/bin/env python3
"""
s4_phase2_setup.py — SPRS Phase-2 (S4 local-optimization refinement) setup driver.

Builds the S4 SW ledger + HW worklist per the FINAL PLAN in S4_PHASE2_ANALYSIS.md:

    3 refiners {4c2 MCFM, 4j VCycles, 4g SubMig} applied to the Phase-1
    competitive-band solutions, re-mapped with ALL 10 S3 methods, deduped by
    tb_hash. SW covers ALL 40 instances; HW covers only the 39 with Phase-1
    HW data (maxp_mod_fat has no Phase-1 HW baseline, so it is SW-only —
    gated by SW makespan instead of measured cycles — and contributes zero
    HW worklist entries).

Phase-1-style outputs:
  - results/<inst>/s4_results.csv   -- SAME schema as Phase-1's sw_results.csv
    (TOURN.SW_COLUMNS, +1 additive `phase1_cycles` column), one row per feed
    task (s2,s3,s4), full metrics (makespan, cp_comm, max_load, edge_cut,
    load_imbalance, connected, valid, max_imem, imem_ok, n_gpus_used, omega,
    ratio_to_omega, asgn_hash, tb_hash, unique_hw_sim, tb_fname). Matches
    Phase-1 semantics: unique_hw_sim=True only on the TB actually queued for
    HW; duplicate-hash rows (in this run or vs Phase-1) share that leader's
    tb_fname instead of getting their own file.
  - /tmp/s4_hw_worklist.json        -- exact shape _bypass_runner.py consumes
    ([ilabel, tb_fname, n_leaves, n_nodes]), 39-instance scope only.
  - results/<inst>/<tb_fname>.sv    -- only for NEW unique TBs (dedup against
    this run AND against Phase-1's existing tb_hash set).

This script does NOT run Vivado and does NOT touch
results/live_hw_results_p1_unified.csv (the Phase-1 record). Run the emitted
worklist through the existing unchanged runner, into a SEPARATE Phase-2 file
so lineage stays clean:

    python3 _bypass_runner.py --jobs 24 --timeout 28800 \\
        --tb-list-json /tmp/s4_hw_worklist.json \\
        --out-csv results/live_hw_results_p2_unified.csv \\
        > hw_s4.log 2>&1 &

See S4_PHASE2_ANALYSIS.md for the full analysis behind these choices.
"""
import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import os
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

BASE = "."
RES = os.path.join(BASE, "results")
TOURN_PATH = os.path.join(BASE, "sprs_tournament (1).py")
UNIFIED_HW_CSV = os.path.join(RES, "live_hw_results_p1_unified.csv")
DEFAULT_WORKLIST_OUT = "/tmp/s4_hw_worklist.json"

# SW runs on all 40 instances. maxp_mod_fat has no Phase-1 HW baseline (it was
# the single largest instance held out of the 40->39 HW run) so it can never
# get an HW-cycle gate or an HW worklist entry -- SW-only, gated by makespan.
HELD_HW_INSTANCE = "maxp_mod_fat"
GIANTS = ["max_mod_fat", "maxp_bal_2d", "maxp_dense_hc", "max_bal_2d", "max_dense_hc"]
REFINERS = ["4c2", "4j", "4g"]             # MCFM, VCycles, SubMig -- universal top-3, doc S3.5
DEGEN_MULT_DEFAULT = 1.5
GATE_DEFAULT = 2.0
GATE_COMPARE = 3.0


def _load_tournament_module():
    """Import sprs_tournament (1).py by path (filename isn't a valid module
    name). No import-time side effects fire (CLI is behind __main__ guard).
    Loaded ONCE in the parent; ProcessPoolExecutor uses fork on this box, so
    workers inherit this exact module object via COW -- no re-import, no
    pickling of the module itself."""
    if BASE not in sys.path:
        sys.path.insert(0, BASE)
    spec = importlib.util.spec_from_file_location("sprs_tournament_p2", TOURN_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sprs_tournament_p2"] = mod
    spec.loader.exec_module(mod)
    return mod


TOURN = _load_tournament_module()
S3_KEYS = sorted(TOURN.STAGE3_METHODS.keys())         # ['3a', ..., '3j'] -- all 10
S2_KEYS = sorted(TOURN.STAGE2_METHODS.keys())         # all S2 methods -- used for --all-s2
INST_META = {ilabel: (n, g, tname) for (n, g, tname, ilabel) in TOURN.TEST_INSTANCES}
# Phase-1-style schema + exactly one additive column (informational only: the
# already-known Phase-1 cycle count when this row's hash matches one).
S4_SW_COLUMNS = list(TOURN.SW_COLUMNS) + ["phase1_cycles"]


# ═══════════════════════════════════════════════════════════════
# Worker: full Phase-1-schema metrics + TB emission + hash, for one
# (s2, s3, s4) task. Fuses _get_metrics()'s metric computation (from
# _eval_greedy_pipeline) with _tb_gen_worker's TB emission, so output rows
# are schema-identical to Phase-1's sw_results.csv AND tb_hash is
# byte-comparable to Phase-1 hashes (both call the same STAGE*_METHODS /
# build_schedule / generate_instructions / emit_sv_testbench).
# ═══════════════════════════════════════════════════════════════

def _s4_full_worker(task):
    s2, s3, s4, n, g, tname, ilabel, sim_timeout = task
    hw = TOURN.HW
    alu_op = TOURN.ALU_FADD
    t0 = time.time()

    row = dict.fromkeys(S4_SW_COLUMNS, '')
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
            row['error'] = 'S2_bad'
            row['error_code'] = TOURN.ErrorCode.S2_BAD
            row['time_s'] = round(time.time() - t0, 3)
            return row

        # Apply the chosen refiner to the S2 baseline (single refiner, no
        # chaining -- the plan's feed is one refiner per task, all 10 S3
        # remaps per refiner output). If the refiner produces an invalid
        # assignment, fall back to the S2 baseline (mirrors the tournament's
        # own "kept prior on invalid output" behavior in refine_phased).
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
        imem_overflow = max_imem > hw.imem_depth

        tb_sv = TOURN.emit_sv_testbench(
            tree, topo, progs, assignment=asgn, addr_alloc=sched.addr_alloc,
            schedule=sched, alu_op=alu_op)
        tb_hash = hashlib.sha256(tb_sv.encode()).hexdigest()

        idir = TOURN._inst_dir(ilabel)
        os.makedirs(idir, exist_ok=True)
        fd, tb_scratch = tempfile.mkstemp(prefix='_s4_tb_scratch_', suffix='.sv', dir=idir)
        with os.fdopen(fd, 'w') as f:
            f.write(tb_sv)

        row.update(
            makespan=ms, makespan_sched=ms_sched, cp_comm=cp, max_load=ml,
            edge_cut=ec, load_imbalance=round(li, 6), connected=conn, valid=True,
            max_imem=max_imem, imem_ok=(not imem_overflow), n_gpus_used=n_used,
            asgn_hash=ahash, tb_hash=tb_hash,
            error=(f'IMEM overflow: {max_imem}/{hw.imem_depth}' if imem_overflow else ''),
            error_code=(TOURN.ErrorCode.IMEM_OVERFLOW if imem_overflow else TOURN.ErrorCode.OK),
        )
        row['_tb_scratch'] = tb_scratch  # internal only -- stripped before CSV write
    except TOURN.AlgoBypassed as e:
        row['error'] = str(e)
        row['error_code'] = TOURN.ErrorCode.BYPASSED
    except TOURN.AlgoTimeout:
        row['error'] = 'timeout'
        row['error_code'] = TOURN.ErrorCode.EVAL_TIMEOUT
    except Exception as e:
        row['error'] = str(e)[:200]
        row['error_code'] = TOURN.ErrorCode.COMPILE
    row['time_s'] = round(time.time() - t0, 3)
    return row


# ═══════════════════════════════════════════════════════════════
# Fidelity self-check -- validates THIS script's worker (not the old
# _tb_gen_worker) reproduces Phase-1 tb_hash exactly, using refiner '4a'
# (None -- refine_none returns the assignment unchanged) so the result is
# byte-identical to a genuine Phase-1 baseline (s2,s3,'') row.
# ═══════════════════════════════════════════════════════════════

def run_fidelity_selfcheck(probe_inst="small_dense_hc"):
    sw_path = os.path.join(RES, probe_inst, "sw_results.csv")
    rows = list(csv.DictReader(open(sw_path, newline="")))
    probe_row = next((r for r in rows if r.get("tb_hash") and r.get("valid") == "True"), None)
    if probe_row is None:
        return {"ok": False, "reason": f"no valid+hashed row found in {sw_path}"}

    s2, s3 = probe_row["s2"], probe_row["s3"]
    n, g, tname = INST_META[probe_inst]
    recorded_hash = probe_row["tb_hash"]

    result = _s4_full_worker((s2, s3, "4a", n, g, tname, probe_inst, 600))
    got_hash = result.get("tb_hash", "")
    scratch = result.get("_tb_scratch", "")
    if scratch and os.path.exists(scratch):
        os.unlink(scratch)  # self-check only -- never part of a real feed

    return {
        "ok": bool(got_hash) and got_hash == recorded_hash,
        "instance": probe_inst, "s2": s2, "s3": s3,
        "recorded_hash": recorded_hash, "recomputed_hash": got_hash,
        "recomputed_makespan": result.get("makespan"),
        "recorded_makespan": probe_row.get("makespan"),
        "error": result.get("error", ""),
    }


# ═══════════════════════════════════════════════════════════════
# Phase-1 data loading
# ═══════════════════════════════════════════════════════════════

def load_hw_cycles():
    """live_hw_results_p1_unified.csv is headerless:
    Instance,Pipeline,TB_Name,Pass,Cycles,SimTime_s,ErrorCode,Error
    Re-read fresh on every invocation of this script -- so once the 2
    in-flight giant re-runs land, the very next run of this script picks
    them up automatically. This is what "the 2 running TBs must not be left
    out" reduces to at the code level; see detect_inflight() below for the
    complementary guard against running BEFORE they land."""
    hw_cyc = defaultdict(dict)
    hw_simtime = defaultdict(list)
    with open(UNIFIED_HW_CSV, newline="") as f:
        for row in csv.reader(f):
            if len(row) < 8:
                continue
            inst, _pipe, tb, _pas, cyc, st, ec, err = row[:8]
            if ec not in ("OK_BYPASS", "OK_BYPASS_REUSED"):
                continue
            try:
                c = int(cyc)
            except ValueError:
                continue
            if c <= 0:
                continue
            if tb not in hw_cyc[inst] or c < hw_cyc[inst][tb]:
                hw_cyc[inst][tb] = c
            if not (err or "").startswith("REUSED"):
                try:
                    hw_simtime[inst].append(float(st))
                except ValueError:
                    pass
    return hw_cyc, hw_simtime


def load_sw_rows(inst):
    path = os.path.join(RES, inst, "sw_results.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def build_existing_hash_maps(sw_rows):
    """existing_hashes: every non-empty tb_hash already in this instance's
    Phase-1 SW grid (leader AND follower rows share the leader's hash).
    hash_to_leader_tbfname: hash -> the Phase-1 leader's tb_fname (only
    leader rows carry tb_fname) -- used both for REUSE cycle lookup and so
    REUSE rows in s4_results.csv point at the SAME file Phase-1 already has,
    matching Phase-1's own leader/follower tb_fname-sharing convention."""
    existing_hashes = set()
    hash_to_leader_tbfname = {}
    for r in sw_rows:
        h = r.get("tb_hash") or ""
        if not h:
            continue
        existing_hashes.add(h)
        tbf = r.get("tb_fname") or ""
        if tbf:
            hash_to_leader_tbfname[h] = tbf
    return existing_hashes, hash_to_leader_tbfname


def instance_omega(sw_rows):
    """omega is a per-INSTANCE lower bound (constant across all pipelines of
    that instance -- confirmed against sw_results.csv: e.g. every row of
    med_bal_2d has omega=48). Look it up rather than recomputing bounds."""
    for r in sw_rows:
        try:
            om = float(r.get("omega", ""))
            if om > 0:
                return om
        except (TypeError, ValueError):
            continue
    return 1.0


def build_pool_hw(inst, sw_rows, hw_cyc):
    """Competitiveness pool for an HW-bearing instance: metric = measured HW
    cycles. Only Phase-1 leader TBs (tb_fname set) with a valid baseline
    makespan AND a landed HW cycle count are eligible."""
    pool = []
    for r in sw_rows:
        tbf = r.get("tb_fname") or ""
        if not tbf:
            continue
        try:
            ms = float(r["makespan"])
        except (KeyError, ValueError):
            continue
        if ms <= 0:
            continue
        c = hw_cyc.get(inst, {}).get(tbf)
        if c is None:
            continue
        pool.append({"s2": r["s2"], "makespan": ms, "metric": c})
    return pool


def build_pool_sw_fallback(sw_rows):
    """Competitiveness pool for the HW-less instance (maxp_mod_fat): no HW
    ground truth exists, so metric = baseline SW makespan itself. This is a
    documented fallback (doc has no HW-cycle data to anchor on for this
    instance) -- degenerate-collapse exclusion is a non-issue here since
    metric IS makespan (no independent axis to collapse against)."""
    pool = []
    for r in sw_rows:
        try:
            ms = float(r["makespan"])
        except (KeyError, ValueError):
            continue
        if ms <= 0 or r.get("valid") != "True":
            continue
        pool.append({"s2": r["s2"], "makespan": ms, "metric": ms})
    return pool


def champion_and_plaus(pool, degen_mult):
    """champion = min metric over the plausible (non-degenerate) subset:
    TBs whose baseline makespan <= degen_mult * (pool's own min makespan).
    Excludes collapsed ~1-GPU mappings that report tiny HW cycles at huge
    makespan (doc S3.3). Champion AND gating both computed over this same
    cleaned population."""
    if not pool:
        return None, []
    msmin = min(p["makespan"] for p in pool)
    plaus = [p for p in pool if p["makespan"] <= degen_mult * msmin]
    if not plaus:
        return None, []
    champion = min(p["metric"] for p in plaus)
    return champion, plaus


def gated_s2_for_M(plaus, champion, M):
    return {p["s2"] for p in plaus if p["metric"] <= M * champion}


# ═══════════════════════════════════════════════════════════════
# In-flight-sim guard -- "the 2 running TBs should not be left out"
# ═══════════════════════════════════════════════════════════════

def detect_inflight(instances):
    """A work_bypass_<tb>_<pid>_<ts> directory under results/<inst>/ means a
    Vivado run for that instance hasn't completed (and therefore isn't yet
    reflected in live_hw_results_p1_unified.csv). Building a champion/gate
    for such an instance right now would risk locking in a stale champion
    that changes the moment the in-flight sim lands. Detected instances are
    excluded from this run (both SW task-gen and HW worklist) unless
    --include-inflight is passed; re-running this script after they land
    picks them up automatically (load_hw_cycles() always re-reads the live
    CSV fresh)."""
    inflight = {}
    for inst in instances:
        idir = os.path.join(RES, inst)
        if not os.path.isdir(idir):
            continue
        wd = sorted(d for d in os.listdir(idir) if d.startswith("work_bypass_"))
        if wd:
            inflight[inst] = wd
    return inflight


# ═══════════════════════════════════════════════════════════════
# Feed / TB-gen / dedup
# ═══════════════════════════════════════════════════════════════

def build_tasks(s2_set, n, g, tname, ilabel, sim_timeout):
    """Nesting matches the plan exactly: gated s2 (outer) x refiner (middle)
    x all 10 S3 methods (inner)."""
    tasks = []
    for s2 in sorted(s2_set):
        for s4 in REFINERS:
            for s3 in S3_KEYS:
                tasks.append((s2, s3, s4, n, g, tname, ilabel, sim_timeout))
    return tasks


def _task_key(t):
    s2, s3, s4, n, g, tname, ilabel, st = t
    return f"{ilabel}\t{s2}\t{s3}\t{s4}"


def _load_checkpoint(path):
    """Returns {task_key: result_dict}. Corrupt/partial trailing lines (from
    a kill mid-write) are skipped, not fatal -- checkpointing is best-effort
    crash recovery, not a transactional log."""
    ck = {}
    if not path or not os.path.exists(path):
        return ck
    n_bad = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                ck[obj["_key"]] = obj["result"]
            except Exception:
                n_bad += 1
    if n_bad:
        TOURN.log("WARN", f"  checkpoint: skipped {n_bad} corrupt/partial line(s)")
    return ck


def run_tb_gen(tasks, workers, checkpoint_path=None):
    """Results aligned back to `tasks` by original (submission) index, NOT
    completion order, so leader-selection downstream is deterministic
    regardless of process-pool scheduling.

    Crash/reboot-safe: each completed task's result is appended to
    `checkpoint_path` as one JSON line (flushed + fsynced) as soon as it's
    done. On a fresh invocation, any task whose key is already in the
    checkpoint file is skipped (not resubmitted to the pool) and its
    recorded result reused verbatim -- including its `_tb_scratch` path,
    which is validated to still exist on disk (scratch files are plain
    files in results/<inst>/, so they survive a reboot; if one is missing
    the task is treated as not-done and recomputed)."""
    results = [None] * len(tasks)
    if not tasks:
        return results

    prior = _load_checkpoint(checkpoint_path) if checkpoint_path else {}
    todo_idx = []
    n_resumed = 0
    for i, t in enumerate(tasks):
        key = _task_key(t)
        cached = prior.get(key)
        if cached is not None:
            scratch = cached.get("_tb_scratch", "")
            if scratch and not os.path.exists(scratch):
                # scratch was lost (e.g. /tmp cleared) -- must recompute
                todo_idx.append(i)
                continue
            results[i] = cached
            n_resumed += 1
        else:
            todo_idx.append(i)

    if n_resumed:
        TOURN.log("INFO", f"  resumed {n_resumed}/{len(tasks)} tasks from checkpoint "
                          f"({checkpoint_path})")

    ckf = None
    if checkpoint_path and todo_idx:
        ckf = open(checkpoint_path, "a")

    try:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            fut_to_idx = {ex.submit(_s4_full_worker, tasks[i]): i for i in todo_idx}
            done = 0
            for fut in as_completed(fut_to_idx):
                i = fut_to_idx[fut]
                try:
                    r = fut.result()
                except Exception as e:
                    s2, s3, s4, n, g, tname, ilabel, st = tasks[i]
                    r = {"pipeline": f"{s2}|{s3}|{s4}", "s2": s2, "s3": s3, "s4": s4,
                         "valid": False, "tb_hash": "", "_tb_scratch": "",
                         "error": f"WORKER_EXC:{e!r}", "error_code": TOURN.ErrorCode.COMPILE,
                         "time_s": 0.0}
                results[i] = r
                if ckf:
                    ckf.write(json.dumps({"_key": _task_key(tasks[i]), "result": r}) + "\n")
                    ckf.flush()
                    os.fsync(ckf.fileno())
                done += 1
                if done % 200 == 0 or done == len(todo_idx):
                    TOURN.log("INFO", f"    ... tb-gen {done}/{len(todo_idx)} "
                                      f"(+{n_resumed} resumed = {done + n_resumed}/{len(tasks)})")
    finally:
        if ckf:
            ckf.close()
    return results


def dedup_scope(indices, tasks, gen_results, existing_hashes):
    """Classify each task index into NEW / DUP_IN_NEWSET / REUSE_PHASE1 /
    GEN_FAILED. `indices` must be given in a fixed canonical order (task
    build order) so "first-seen wins as leader" is deterministic."""
    status = {}
    leader_of = {}
    leader_for_hash = {}
    for idx in indices:
        s2, s3, s4, n, g, tname, ilabel, st = tasks[idx]
        r = gen_results[idx] or {}
        h = r.get("tb_hash") or ""
        if not h:
            status[idx] = "GEN_FAILED"
            continue
        if h in existing_hashes.get(ilabel, ()):
            status[idx] = "REUSE_PHASE1"
            continue
        key = (ilabel, h)
        if key not in leader_for_hash:
            leader_for_hash[key] = idx
            status[idx] = "NEW"
            leader_of[idx] = idx
        else:
            status[idx] = "DUP_IN_NEWSET"
            leader_of[idx] = leader_for_hash[key]
    return status, leader_of


# ═══════════════════════════════════════════════════════════════
# Main driver
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gate", type=float, default=GATE_DEFAULT,
                    help="competitiveness gate multiplier M: feed = s2 with >=1 solution "
                         "metric <= M*champion (HW cycles for 39 instances, SW makespan "
                         "fallback for maxp_mod_fat). Default 2.0")
    ap.add_argument("--workers", type=int, default=8,
                    help="ProcessPoolExecutor worker count (box is shared -- default modest)")
    ap.add_argument("--only", type=str, default=None, help="restrict to a single instance label")
    ap.add_argument("--smoke", action="store_true", help="alias for --only small_dense_hc")
    ap.add_argument("--sim-timeout", type=int, default=3600,
                    help="sim_timeout field stored on each task (informational only -- "
                         "the real per-TB cap is a _bypass_runner.py --timeout arg)")
    ap.add_argument("--degen-mult", type=float, default=DEGEN_MULT_DEFAULT,
                    help="degenerate-TB makespan exclusion multiplier (default 1.5)")
    ap.add_argument("--worklist-out", type=str, default=DEFAULT_WORKLIST_OUT)
    ap.add_argument("--checkpoint", type=str,
                    default=os.path.join(RES, "_s4_tbgen_checkpoint.jsonl"),
                    help="crash/reboot-safe checkpoint file for STEP 3 (TB-gen). "
                         "Completed tasks are appended here as they finish; a fresh "
                         "invocation resumes from it automatically. Pass '' to disable.")
    ap.add_argument("--fresh", action="store_true",
                    help="ignore and truncate any existing --checkpoint file (start clean)")
    ap.add_argument("--include-inflight", action="store_true",
                    help="DANGEROUS -- proceed even if an instance has an in-flight "
                         "(not-yet-landed) HW sim. Default: exclude such instances.")
    ap.add_argument("--skip-selfcheck", action="store_true",
                    help="DANGEROUS/debug only -- the fidelity self-check is required")
    ap.add_argument("--all-s2", action="store_true",
                    help="bypass the competitiveness gate entirely -- use ALL unique S2 "
                         "assignments per instance (all STAGE2_METHODS) as the refine universe, "
                         "not just the gated/competitive subset")
    args = ap.parse_args()

    if args.smoke and not args.only:
        args.only = "small_dense_hc"

    TOURN.banner("SPRS Phase-2 (S4 refinement) setup -- STEP 0: fidelity self-check")
    if args.skip_selfcheck:
        TOURN.log("WARN", "SKIPPED (--skip-selfcheck) -- NOT a valid production run.")
    else:
        chk = run_fidelity_selfcheck()
        if not chk.get("ok"):
            TOURN.log("ERROR", f"FAIL: {chk}")
            TOURN.log("ERROR", "The emit path differs from Phase-1's -- stopping.")
            sys.exit(2)
        TOURN.log("INFO", f"PASS  instance={chk['instance']} pipeline={chk['s2']}|{chk['s3']}|4a")
        TOURN.log("INFO", f"      recorded_hash   = {chk['recorded_hash']}")
        TOURN.log("INFO", f"      recomputed_hash = {chk['recomputed_hash']}")
        TOURN.log("INFO", f"      makespan recorded={chk['recorded_makespan']} "
                          f"recomputed={chk['recomputed_makespan']}")

    # ---- instance scope: SW = all 40, HW = 39 (HELD_HW_INSTANCE excluded) ----
    all_instances = sorted(INST_META)
    if args.only:
        if args.only not in INST_META:
            print(f"\nUnknown instance '{args.only}'. Known: {all_instances}")
            sys.exit(2)
        scope = [args.only]
    else:
        scope = all_instances
    TOURN.log("INFO", f"SW scope: {len(scope)} instance(s)"
                      + (f" ({scope[0]})" if len(scope) == 1 else
                         f"  (HW will additionally exclude: {HELD_HW_INSTANCE})"))

    # ---- in-flight guard ----
    inflight = detect_inflight(scope)
    if inflight and not args.include_inflight:
        TOURN.banner("IN-FLIGHT HW SIM DETECTED -- excluding affected instance(s) this run", "!")
        for inst, dirs in inflight.items():
            TOURN.log("WARN", f"  {inst}: {dirs} -- not yet in {os.path.basename(UNIFIED_HW_CSV)}")
        TOURN.log("WARN", "  Champion/gate for these would be computed on INCOMPLETE HW data "
                          "and could change once the in-flight sim lands.")
        TOURN.log("WARN", "  Excluded from this run. Re-run this script after they finish -- "
                          "load_hw_cycles() re-reads the CSV fresh, so they'll be included "
                          "automatically once landed. (Override with --include-inflight.)")
        scope = [i for i in scope if i not in inflight]
        if not scope:
            TOURN.log("ERROR", "Nothing left in scope after excluding in-flight instances. Exiting.")
            sys.exit(3)

    # ---- load Phase-1 data ----
    TOURN.log("INFO", "Loading Phase-1 HW results (live_hw_results_p1_unified.csv, read-only)...")
    hw_cyc, hw_simtime = load_hw_cycles()
    global_mean_simtime = statistics.median(
        [statistics.mean(v) for v in hw_simtime.values() if v]) if hw_simtime else 0.0

    sw_rows_by_inst, existing_hashes, hash_to_leader, omega_by_inst = {}, {}, {}, {}
    champion, plaus_by_inst, gate_source = {}, {}, {}
    gated = {}   # inst -> {M: set(s2)}
    skipped_no_data = []

    gate_report_values = sorted({GATE_DEFAULT, GATE_COMPARE, args.gate})

    TOURN.banner("STEP 1: champion + gated-S2 per instance (all cheap, CSV-only)")
    print(f"{'instance':<20}{'source':<16}{'champion':>10}{'#plaus':>8}"
          + "".join(f"{'gated@'+str(M):>12}" for M in gate_report_values))
    for inst in scope:
        rows = load_sw_rows(inst)
        sw_rows_by_inst[inst] = rows
        eh, h2l = build_existing_hash_maps(rows)
        existing_hashes[inst] = eh
        hash_to_leader[inst] = h2l
        omega_by_inst[inst] = instance_omega(rows)

        if inst == HELD_HW_INSTANCE:
            pool = build_pool_sw_fallback(rows)
            gate_source[inst] = "SW-makespan"
        elif hw_cyc.get(inst):
            pool = build_pool_hw(inst, rows, hw_cyc)
            gate_source[inst] = "HW-cycles"
        else:
            TOURN.log("WARN", f"  {inst}: no Phase-1 HW rows and not the designated "
                              f"HW-less instance -- skipping (unexpected data state).")
            skipped_no_data.append(inst)
            continue

        champ, plaus = champion_and_plaus(pool, args.degen_mult)
        if champ is None:
            skipped_no_data.append(inst)
            continue
        champion[inst] = champ
        plaus_by_inst[inst] = plaus
        gated[inst] = {M: gated_s2_for_M(plaus, champ, M) for M in gate_report_values}
        row_str = f"{inst:<20}{gate_source[inst]:<16}{champ:>10.4g}{len(plaus):>8}"
        row_str += "".join(f"{len(gated[inst][M]):>12}" for M in gate_report_values)
        print(row_str)

    if skipped_no_data:
        TOURN.log("WARN", f"SKIPPED (no usable data): {skipped_no_data}")

    active = [i for i in scope if i in champion]
    active_hw = [i for i in active if i != HELD_HW_INSTANCE]
    if not active:
        TOURN.log("ERROR", "No instances with usable data in scope. Nothing to do.")
        sys.exit(1)

    # ---- feed-size summary (cheap) at each reported gate ----
    TOURN.banner("STEP 2: gated-feed size (tasks = #gated_s2 x 3 refiners x 10 S3)")
    for M in gate_report_values:
        n_s2 = sum(len(gated[i][M]) for i in active)
        n_tasks = n_s2 * len(REFINERS) * len(S3_KEYS)
        tag = "  <- ACTUAL FEED (this run's --gate)" if (M == args.gate and not args.all_s2) else ""
        print(f"  M={M:<4} distinct gated s2 (summed over {len(active)} instances)={n_s2:<6} "
              f"feed tasks={n_tasks}{tag}")
    if args.all_s2:
        n_s2_all = len(S2_KEYS) * len(active)
        n_tasks_all = n_s2_all * len(REFINERS) * len(S3_KEYS)
        print(f"  ALL-S2  every S2 method per instance (summed over {len(active)} instances)="
              f"{n_s2_all:<6} feed tasks={n_tasks_all}  <- ACTUAL FEED (--all-s2, gate bypassed)")

    # ---- build universe tasks (superset covering every reported M) ----
    tasks = []
    inst_task_idx = defaultdict(list)
    M_super = max(gate_report_values)
    for inst in active:
        n, g, tname = INST_META[inst]
        s2_universe = S2_KEYS if args.all_s2 else gated[inst][M_super]
        inst_tasks = build_tasks(s2_universe, n, g, tname, inst, args.sim_timeout)
        for t in inst_tasks:
            inst_task_idx[inst].append(len(tasks))
            tasks.append(t)

    TOURN.banner(f"STEP 3: generating {len(tasks)} candidate TBs via _s4_full_worker "
                 f"({args.workers} workers)")
    t0 = time.time()
    if args.fresh and args.checkpoint and os.path.exists(args.checkpoint):
        os.unlink(args.checkpoint)
        TOURN.log("INFO", f"  --fresh: removed existing checkpoint {args.checkpoint}")
    gen_results = run_tb_gen(tasks, args.workers, checkpoint_path=(args.checkpoint or None))
    TOURN.log("INFO", f"  done in {time.time()-t0:.1f}s")

    n_gen_failed = sum(1 for r in gen_results if not (r or {}).get("tb_hash"))
    if n_gen_failed:
        TOURN.log("WARN", f"  {n_gen_failed}/{len(tasks)} tasks failed to generate a TB "
                          f"(see GEN_FAILED rows / error field)")

    # ---- scoped dedup: comparison counts at every reported M ----
    TOURN.banner("STEP 4: dedup (NEW vs DUP_IN_NEWSET vs REUSE_PHASE1) at each reported gate")
    idx_by_M = {}
    status_by_M = {}
    for M in gate_report_values:
        idxs = [idx for inst in active for idx in inst_task_idx[inst]
                if tasks[idx][0] in gated[inst][M]]
        idx_by_M[M] = idxs
        status, _leader = dedup_scope(idxs, tasks, gen_results, existing_hashes)
        status_by_M[M] = status
        cnt = defaultdict(int)
        for s in status.values():
            cnt[s] += 1
        tag = "  <- ACTUAL FEED" if (M == args.gate and not args.all_s2) else "  (comparison only, not persisted)"
        print(f"  M={M:<4} tasks={len(idxs):<6} NEW={cnt['NEW']:<6} "
              f"DUP_IN_NEWSET={cnt['DUP_IN_NEWSET']:<6} REUSE_PHASE1={cnt['REUSE_PHASE1']:<6} "
              f"GEN_FAILED={cnt['GEN_FAILED']:<4}{tag}")

    if args.all_s2:
        all_idxs = list(range(len(tasks)))
        all_status, _leader = dedup_scope(all_idxs, tasks, gen_results, existing_hashes)
        idx_by_M["ALL"] = all_idxs
        status_by_M["ALL"] = all_status
        cnt = defaultdict(int)
        for s in all_status.values():
            cnt[s] += 1
        print(f"  ALL-S2 tasks={len(all_idxs):<6} NEW={cnt['NEW']:<6} "
              f"DUP_IN_NEWSET={cnt['DUP_IN_NEWSET']:<6} REUSE_PHASE1={cnt['REUSE_PHASE1']:<6} "
              f"GEN_FAILED={cnt['GEN_FAILED']:<4}  <- ACTUAL FEED (--all-s2, gate bypassed)")

    # ---- projected HW core-h at each reported M (39-instance HW scope only) ----
    TOURN.banner("STEP 5: projected HW core-h = sum(NEW_tbs_per_instance x mean SimTime)  "
                 "[HW scope: 39 instances, excludes maxp_mod_fat]")
    report_keys = list(gate_report_values) + (["ALL"] if args.all_s2 else [])
    for M in report_keys:
        idxs = idx_by_M[M]
        status = status_by_M[M]
        new_by_inst = defaultdict(int)
        for idx in idxs:
            ilabel = tasks[idx][6]
            if status[idx] == "NEW" and ilabel != HELD_HW_INSTANCE:
                new_by_inst[ilabel] += 1
        total_h = 0.0
        giant_h = 0.0
        giant_new = 0
        for inst, cnt in new_by_inst.items():
            mst = statistics.mean(hw_simtime[inst]) if hw_simtime.get(inst) else global_mean_simtime
            h = cnt * mst / 3600.0
            total_h += h
            if inst in GIANTS:
                giant_h += h
                giant_new += cnt
        mlabel = "ALL-S2" if M == "ALL" else f"M={M}"
        print(f"  {mlabel:<7} NEW HW TBs total={sum(new_by_inst.values()):<6} "
              f"projected={total_h:6.1f} core-h   (giants: {giant_new} TBs, {giant_h:6.1f} core-h)")
        if (M == args.gate and not args.all_s2) or M == "ALL":
            for g in GIANTS:
                if g in new_by_inst:
                    mst = statistics.mean(hw_simtime[g]) if hw_simtime.get(g) else global_mean_simtime
                    print(f"           {g:<18} NEW={new_by_inst[g]:<5} "
                          f"~{new_by_inst[g]*mst/3600:6.1f} core-h")
    actual_key = "ALL" if args.all_s2 else args.gate
    n_new_sw_only = sum(1 for idx in idx_by_M[actual_key]
                        if status_by_M[actual_key][idx] == "NEW" and tasks[idx][6] == HELD_HW_INSTANCE)
    if n_new_sw_only:
        print(f"  ({n_new_sw_only} NEW unique TBs on {HELD_HW_INSTANCE} -- SW/ledger only, "
              f"NEVER queued for HW)")

    # ---- persist: only the ACTUAL requested feed ----
    TOURN.banner(f"STEP 6: writing Phase-1-style outputs for the ACTUAL feed "
                 f"({'--all-s2' if args.all_s2 else f'gate M={args.gate}'})")
    req_idxs = idx_by_M[actual_key]
    req_status = status_by_M[actual_key]
    req_idx_set = set(req_idxs)

    worklist_by_inst = defaultdict(list)
    s4_rows_by_inst = defaultdict(list)
    n_new_written = n_new_hw_queued = n_dup_cleaned = n_reuse = n_reuse_cycles_found = 0
    hash_to_new_tbfname = {}   # (ilabel, hash) -> tb_fname, filled as NEW leaders are seen

    for idx, t in enumerate(tasks):
        s2, s3, s4, n, g, tname, ilabel, st = t
        r = gen_results[idx] or {}
        scratch = r.get("_tb_scratch", "")

        if idx not in req_idx_set:
            # comparison-only (extra M beyond the requested feed): never persisted.
            if scratch and os.path.exists(scratch):
                os.unlink(scratch)
            continue

        status = req_status[idx]
        h = r.get("tb_hash", "")
        row = {k: r.get(k, '') for k in S4_SW_COLUMNS}   # drop _tb_scratch + any stray keys
        row["omega"] = omega_by_inst[ilabel]
        if row.get("valid") and row.get("makespan", -1) not in ("", -1) and row["omega"] > 0:
            try:
                row["ratio_to_omega"] = round(float(row["makespan"]) / row["omega"], 4)
            except (TypeError, ValueError):
                row["ratio_to_omega"] = -1
        else:
            row["ratio_to_omega"] = -1

        if status == "NEW":
            tb_fname = f"tb_{TOURN._safe_name(s2)}_{TOURN._safe_name(s3)}_{TOURN._safe_name(s4)}"
            dest = os.path.join(TOURN._inst_dir(ilabel), f"{tb_fname}.sv")
            if scratch and os.path.exists(scratch):
                os.replace(scratch, dest)
            row["tb_fname"] = tb_fname
            row["unique_hw_sim"] = (ilabel != HELD_HW_INSTANCE)
            hash_to_new_tbfname[(ilabel, h)] = tb_fname
            n_new_written += 1
            if ilabel != HELD_HW_INSTANCE:
                n_nodes = TOURN.build_topology(tname, g).n_nodes
                worklist_by_inst[ilabel].append([ilabel, tb_fname, n, n_nodes])
                n_new_hw_queued += 1
        elif status == "DUP_IN_NEWSET":
            if scratch and os.path.exists(scratch):
                os.unlink(scratch)
            # Share the leader's tb_fname (matches Phase-1's own
            # leader/follower propagation convention) -- leader is guaranteed
            # already processed since dedup_scope's "first-seen" iterates
            # this same task order.
            row["tb_fname"] = hash_to_new_tbfname.get((ilabel, h), "")
            row["unique_hw_sim"] = False
            n_dup_cleaned += 1
        elif status == "REUSE_PHASE1":
            if scratch and os.path.exists(scratch):
                os.unlink(scratch)
            leader_tbf = hash_to_leader.get(ilabel, {}).get(h, "")
            row["tb_fname"] = leader_tbf
            row["unique_hw_sim"] = False
            p1c = hw_cyc.get(ilabel, {}).get(leader_tbf)
            if p1c is not None:
                row["phase1_cycles"] = p1c
                n_reuse_cycles_found += 1
            n_reuse += 1
        else:  # GEN_FAILED
            if scratch and os.path.exists(scratch):
                os.unlink(scratch)
            row["tb_fname"] = ""
            row["unique_hw_sim"] = False

        s4_rows_by_inst[ilabel].append(row)

    print(f"  NEW unique TBs written to disk        : {n_new_written}  "
          f"(of which queued for HW: {n_new_hw_queued}; "
          f"SW/ledger-only on {HELD_HW_INSTANCE}: {n_new_written - n_new_hw_queued})")
    print(f"  DUP_IN_NEWSET (scratch cleaned)        : {n_dup_cleaned}")
    print(f"  REUSE_PHASE1 (no re-sim needed)         : {n_reuse}  "
          f"({n_reuse_cycles_found} with a resolvable Phase-1 cycle count)")

    # ---- results/<inst>/s4_results.csv, Phase-1 style (header + full schema) ----
    for inst, rows in s4_rows_by_inst.items():
        path = os.path.join(RES, inst, "s4_results.csv")
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=S4_SW_COLUMNS)
            w.writeheader()
            for row in rows:
                w.writerow(row)
    print(f"  wrote results/<inst>/s4_results.csv for {len(s4_rows_by_inst)} instance(s)")

    # ---- HW worklist json (merge-by-instance, idempotent re-runs) ----
    def _merge_write_json(path, new_by_inst):
        existing = []
        if os.path.exists(path):
            try:
                existing = json.load(open(path))
            except Exception:
                existing = []
        touched = set(new_by_inst.keys())
        kept = [e for e in existing if e[0] not in touched]
        allrows = kept + [e for inst in sorted(new_by_inst) for e in new_by_inst[inst]]
        with open(path, "w") as f:
            json.dump(allrows, f, indent=1)
        return len(allrows)

    n_wl = _merge_write_json(args.worklist_out, worklist_by_inst)
    print(f"  wrote {args.worklist_out}  ({n_wl} total entries after merge-by-instance, "
          f"39-instance HW scope)")

    TOURN.banner("Done. Next step (run yourself -- this script does not invoke Vivado):")
    print(f"  python3 _bypass_runner.py --jobs 24 --timeout 28800 \\\n"
          f"      --tb-list-json {args.worklist_out} \\\n"
          f"      --out-csv {RES}/live_hw_results_p2_unified.csv \\\n"
          f"      > hw_s4.log 2>&1 &")


if __name__ == "__main__":
    main()
