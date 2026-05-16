#!/usr/bin/env python3
"""
sprs_tournament.py — SPRS Tournament v8.0
          Portable edition for Xeon W-2295 workstation

Flow Modes:
  --mode phase1 : Phase 1 Tournament (S2xS3 SW Eval) -> HW Sim for Winners
  --mode phase2 : Phase 2 Tournament (Phase 1 -> S4 Refinement) -> HW Sim for Winners

Features:
  - Global deduplication of testing unique assignments.
  - Testbench (TB) Hashing in Phase 3 to avoid running Vivado for functionally
    identical algorithm results (drastically speeds up HW validation).

Usage:
    python3 sprs_tournament.py --mode phase1          # Full P1 (SW+HW)
    python3 sprs_tournament.py --mode phase2          # Full P2 (SW+HW)
    python3 sprs_tournament.py --mode phase1 --skip-hw  # Phase 1 SW-only
    python3 sprs_tournament.py --resume               # Resume aborted run
"""

import os as _os
# Repo root: override with SPRS_ROOT. Defaults to this file's repo.
SPRS_ROOT = _os.environ.get("SPRS_ROOT",
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import math, time, json, os, sys, argparse, csv, hashlib, statistics, re, subprocess
import multiprocessing, shutil, copy, tempfile, glob, signal
from collections import defaultdict

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

def _free_ram_gb():
    if _HAS_PSUTIL:
        return psutil.virtual_memory().available / (1024**3)
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) / (1024**2)
    except Exception:
        pass
    return float('inf')  # unknown — don't cap

from sprs_core import (
    CBTree, HardwareConfig, HW, build_topology,
    STAGE2_METHODS, STAGE3_METHODS, STAGE4_METHODS,
    TEST_INSTANCES, N_INSTANCES,
    precompute_all_instances, get_ctx, _INSTANCE_CACHE,
    _set_eval_deadline, _check_deadline, AlgoTimeout, AlgoBypassed,
    _validate_assignment, is_connected_partition,
    compute_lower_bound, _estimate_imem,
    build_schedule, generate_instructions, emit_sv_testbench,
    ALU_FADD,
)

# ═══════════════════════════════════════════════════════════════
# PLATFORM
# ═══════════════════════════════════════════════════════════════
IS_WINDOWS = (os.name == 'nt')
VIVADO_EXT = ".bat" if IS_WINDOWS else ""
VIVADO_BIN = r"C:\AMDDesignTools\2025.2\Vivado\bin" if IS_WINDOWS else "" + _os.environ.get("VIVADO_BIN","/opt/Xilinx/2025.2/Vivado/bin") + ""

# Auto-detect Verilator availability at import time
# On MSYS2/Windows the Perl wrapper may be broken; prefer verilator_bin directly.
_VERILATOR_BIN = (shutil.which('verilator_bin') or shutil.which('verilator_bin.exe')
                  or shutil.which('verilator'))
if not _VERILATOR_BIN and IS_WINDOWS:
    _msys = r'C:\msys64\mingw64\bin\verilator_bin.exe'
    if os.path.exists(_msys):
        _VERILATOR_BIN = _msys
HW_BACKEND = 'verilator' if _VERILATOR_BIN else 'xsim'

DEFAULT_SW_WORKERS = max(1, os.cpu_count() or 32)
DEFAULT_HW_WORKERS = max(1, os.cpu_count() or 24)
DEFAULT_HW_RAM_GB = 2.0    # was hardcoded 3 — tune via --hw-ram-gb
DEFAULT_MAX_HW_RETRIES = 2  # per-TB retry on transient HW failures
EVAL_TIMEOUT = 1800
SIM_TIMEOUT = 3600

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RTL_DIR = os.path.join(BASE_DIR, "rtl")
RTL_FILES = [
    "noc_pkg.sv", "btree_pkg.sv", "sync_fifo.sv", "link_tx.sv",
    "noc_link.sv", "noc_router.sv", "noc_ni.sv",
    "fp64_add.sv", "btree_fsm_fast.sv", "noc_system.sv"
]
RESULTS_DIR = os.path.join(BASE_DIR, "results")

SW_COLUMNS = [
    'pipeline', 's2', 's3', 's4', 'makespan', 'makespan_sched', 'cp_comm',
    'max_load', 'edge_cut', 'load_imbalance', 'connected', 'valid',
    'max_imem', 'imem_ok', 'n_gpus_used', 'omega', 'ratio_to_omega',
    'time_s', 'error', 'error_code', 'asgn_hash',
    # Dedup metadata — persisted so --hw-only can reconstruct state
    'tb_hash', 'unique_hw_sim', 'tb_fname',
]

WINNER_COLUMNS = [
    'rank', 'pipeline', 's2', 's3', 's4', 'makespan', 'makespan_sched',
    'cp_comm', 'max_load', 'edge_cut', 'load_imbalance', 'connected',
    'max_imem', 'imem_ok', 'omega', 'ratio_to_omega',
    'asgn_hash', 'tb_hash',
    'hw_pass', 'hw_cycles', 'perf_stall', 'perf_retired',
    'hw_timeout', 'sim_time_s', 'hw_error', 'hw_error_code', 'unique_hw_sim'
]

SUMMARY_COLUMNS = [
    'instance', 'N', 'G', 'topology', 'omega', 'active_bound',
    'best_pipeline', 'best_makespan', 'best_ratio', 'n_sw_valid',
    'n_winners', 'n_unique_sims', 'n_hw_pass', 'best_hw_cycles',
    'sw_time_s', 'hw_time_s'
]


# ═══════════════════════════════════════════════════════════════
# ERROR CODES + LOGGING
# ═══════════════════════════════════════════════════════════════

class ErrorCode:
    """Stable error-code constants for SW + HW failure paths.

    Every result row gets an `error_code` (SW) or `hw_error_code` (HW) field.
    Codes are short stable strings so they can be grepped from logs/CSVs.
    """
    OK             = 'E_OK'
    # ── SW (pipeline evaluation) ──
    S2_BAD         = 'E_S2_BAD'
    BYPASSED       = 'E_BYPASSED'
    S3_BAD         = 'E_S3_BAD'
    S4_BAD         = 'E_S4_BAD'
    EVAL_TIMEOUT   = 'E_EVAL_TIMEOUT'
    IMEM_OVERFLOW  = 'E_IMEM_OF'
    COMPILE        = 'E_COMPILE'
    # ── HW (Vivado xsim) ──
    VIVADO_MISSING = 'E_VIVADO_MISSING'
    XVLOG_FAIL     = 'E_XVLOG_FAIL'
    XELAB_FAIL     = 'E_XELAB_FAIL'
    SIM_TIMEOUT    = 'E_SIM_TIMEOUT'
    SIM_FAIL       = 'E_SIM_FAIL'
    SIM_TB_TIMEOUT = 'E_SIM_TB_TIMEOUT'
    SIM_UNKNOWN    = 'E_SIM_UNKNOWN'
    HW_OTHER       = 'E_HW_OTHER'
    # ── HW-only reconstruction ──
    TB_MISSING     = 'E_TB_MISSING'
    SW_CSV_MISSING = 'E_SW_CSV_MISSING'

    _DESC = {
        OK:             ('OK',
                         ''),
        S2_BAD:         ('S2 assignment failed validation',
                         'Pipeline unsalvageable. Try a different S2 for this instance.'),
        S3_BAD:         ('S3 mapping returned invalid result',
                         'Try a different S3 method.'),
        S4_BAD:         ('S4 refinement invalid; fell back to S2 baseline',
                         'Not fatal — baseline used.'),
        EVAL_TIMEOUT:   ('SW eval exceeded EVAL_TIMEOUT',
                         'Raise EVAL_TIMEOUT (currently {}s) or reduce instance size.'.format(EVAL_TIMEOUT)),
        IMEM_OVERFLOW:  ('Instruction memory exceeded HW capacity',
                         'HW sim will fail for this pipeline. Pick fewer GPUs or smaller N.'),
        COMPILE:        ('Unexpected exception during SW pipeline',
                         'See `error` field in sw_results.csv for traceback.'),
        VIVADO_MISSING: ('Vivado binaries not found at configured path',
                         'Edit VIVADO_BIN in this script to point to your install.'),
        XVLOG_FAIL:     ('xvlog (SV compile) failed',
                         'Inspect work_<tb>/xvlog.log under the instance dir.'),
        XELAB_FAIL:     ('xelab (elaboration) failed',
                         'Inspect work_<tb>/xelab.log; usually missing module / top mismatch.'),
        SIM_TIMEOUT:    ('xsim subprocess exceeded --sim-timeout',
                         'Raise --sim-timeout (currently {}s).'.format(SIM_TIMEOUT)),
        SIM_FAIL:       ('Testbench reported [FAIL]',
                         'Inspect sim_<tb>.log; usually a mismatch or addr collision.'),
        SIM_TB_TIMEOUT: ('TB self-reported TIMEOUT before completion',
                         'Cycle limit reached inside the TB; raise sim_max_cycles.'),
        SIM_UNKNOWN:    ('Sim finished with no PASS/FAIL marker',
                         'Tail of sim output captured in error field; xsim may have crashed.'),
        HW_OTHER:       ('Unexpected exception in HW worker',
                         'See `hw_error` field; likely subprocess or filesystem issue.'),
        TB_MISSING:     ('Expected tb_*.sv file missing on disk',
                         'Re-run SW phase to regenerate testbenches for this instance.'),
        SW_CSV_MISSING: ('sw_results.csv not found for instance',
                         'Run --mode phase1 (without --hw-only) first.'),
    }

    @classmethod
    def describe(cls, code):
        return cls._DESC.get(code, (code, ''))


# Lightweight prefixed logging. Used for state changes, warnings, errors;
# progress-bar updates stay as plain prints so they don't get cluttered.
_LOG_PFX = {
    'INFO':  '  [i] ',
    'OK':    '  [OK] ',
    'WARN':  '  [WARN] ',
    'ERROR': '  [ERR] ',
    'STEP':  '  ',
}

def log(level, msg, flush=True):
    print(_LOG_PFX.get(level, '  ') + msg, flush=flush)

def banner(title, char='='):
    print(char * 80, flush=True)
    print(f"  {title}", flush=True)
    print(char * 80, flush=True)


# ═══════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════

def _fmt_time(s):
    if s < 60: return f"{s:.0f}s"
    if s < 3600: return f"{s/60:.1f}m"
    return f"{s/3600:.1f}h"


def _hash_assignment(asgn, N):
    vals = tuple(asgn[i] if isinstance(asgn, list) else asgn.get(i, 0)
                 for i in range(N))
    return hashlib.sha256(str(vals).encode()).hexdigest()


def _inst_dir(ilabel):
    return os.path.join(RESULTS_DIR, ilabel)


def get_rtl_paths():
    return [os.path.join(RTL_DIR, f) for f in RTL_FILES]


def _safe_name(s):
    """Sanitize any string for use in filenames and SystemVerilog identifiers."""
    if not s: return "none"
    return re.sub(r'[^a-zA-Z0-9_]', '_', str(s))


# ═══════════════════════════════════════════════════════════════
# WORKER INIT
# ═══════════════════════════════════════════════════════════════

_W_INSTANCES = None
_W_BOUNDS = None

def _worker_init(instances, bounds):
    global _W_INSTANCES, _W_BOUNDS
    _W_INSTANCES = instances
    _W_BOUNDS = bounds
    precompute_all_instances(instances)


# ═══════════════════════════════════════════════════════════════
# LOWER BOUNDS
# ═══════════════════════════════════════════════════════════════

def compute_and_save_bounds(instances):
    all_bounds = {}
    for n, g, tname, ilabel in instances:
        tree = CBTree(n); topo = build_topology(tname, g)
        ge = min(g, tree.total_nodes)
        lb = compute_lower_bound(tree, ge, topo, HW)
        lb['instance'] = ilabel; lb['N'] = n; lb['G'] = g; lb['topology'] = tname
        idir = _inst_dir(ilabel)
        os.makedirs(idir, exist_ok=True)
        serial = {k: (v if isinstance(v, (int, float, str, bool)) else str(v))
                  for k, v in lb.items()}
        with open(os.path.join(idir, 'lower_bounds.json'), 'w') as f:
            json.dump(serial, f, indent=2)
        all_bounds[ilabel] = lb
    return all_bounds


# ═══════════════════════════════════════════════════════════════
# SW EVAL WORKER (Unified for Phase 1 and 2)
# ═══════════════════════════════════════════════════════════════

def _eval_pipeline(args):
    s2_id, s3_id, s4_cfg, n, g, tname, ilabel = args
    label = f"{s2_id}|{s3_id}" if not s4_cfg else f"{s2_id}|{s3_id}|{s4_cfg}"
    alu_op = ALU_FADD; hw = HW
    omega = _W_BOUNDS.get(ilabel, {}).get('omega', 1)

    row = dict.fromkeys(SW_COLUMNS, '')
    row.update(pipeline=label, s2=s2_id, s3=s3_id, s4=s4_cfg, makespan=-1,
               makespan_sched=-1, cp_comm=-1, max_load=-1, edge_cut=-1,
               load_imbalance=-1, connected=False, valid=False, max_imem=-1,
               imem_ok=False, n_gpus_used=0, omega=omega, ratio_to_omega=-1,
               time_s=0.0, error='', asgn_hash='')

    t0 = time.time()
    _set_eval_deadline(EVAL_TIMEOUT)

    try:
        tree = CBTree(n); topo = build_topology(tname, g)
        ge = min(g, tree.total_nodes); ctx = get_ctx(tree, topo)

        _, s2f = STAGE2_METHODS[s2_id]
        asgn = s2f(tree, ge, topo, hw)
        if not _validate_assignment(tree, asgn, ge):
            row['error'] = 'S2_bad'; row['time_s'] = round(time.time()-t0, 3)
            return row
        _check_deadline("post-S2")

        _, s3f = STAGE3_METHODS[s3_id]
        mapping = s3f(tree, asgn, ge, topo, hw)
        _check_deadline("post-S3")

        if s4_cfg and s4_cfg != '4a':
            if '+' in s4_cfg:
                a_id, b_id = s4_cfg.split('+')
                _, af = STAGE4_METHODS[a_id]; _, bf = STAGE4_METHODS[b_id]
                ref = af(tree, asgn, ge, topo, hw)
                if _validate_assignment(tree, ref, ge):
                    _check_deadline("post-S4a")
                    ref = bf(tree, ref, ge, topo, hw)
                else:
                    ref = asgn
            else:
                _, s4f = STAGE4_METHODS[s4_cfg]
                ref = s4f(tree, asgn, ge, topo, hw)
            if _validate_assignment(tree, ref, ge):
                asgn = ref
            _check_deadline("post-S4")
            mapping = s3f(tree, asgn, ge, topo, hw)
            _check_deadline("post-remap")

        cp = ctx.fast_cp_comm(asgn)
        ml = ctx.fast_max_load(asgn, ge)
        li = ctx.fast_load_imbalance(asgn, ge)
        ec = ctx.fast_edge_cut(asgn)
        conn = is_connected_partition(tree, asgn, ge)
        n_used = len(set(asgn[i] if isinstance(asgn, list) else asgn.get(i, 0)
                         for i in range(tree.total_nodes)))
        ahash = _hash_assignment(asgn, tree.total_nodes)

        sched = build_schedule(tree, asgn, mapping, ge, topo, hw, alu_op=alu_op)
        ms_sched = sched.makespan
        ms = ms_sched if ms_sched > 0 else max(cp, ml)
        ratio = (ms / omega) if (omega > 0 and ms > 0) else -1

        progs = generate_instructions(tree, topo, sched, hw, alu_op=alu_op)
        max_imem_actual = max(len(progs[gpu]) for gpu in progs) if progs else 0
        _check_deadline("post-codegen")

        row.update(
            makespan=ms, makespan_sched=ms_sched, cp_comm=cp, max_load=ml,
            edge_cut=ec, load_imbalance=round(li, 6), connected=conn,
            valid=True, max_imem=max_imem_actual,
            imem_ok=(max_imem_actual <= hw.imem_depth),
            n_gpus_used=n_used,
            ratio_to_omega=round(ratio, 4) if ratio > 0 else -1,
            asgn_hash=ahash)

        if max_imem_actual > hw.imem_depth:
            row['error'] = f'IMEM overflow: {max_imem_actual}/{hw.imem_depth}'

    except AlgoBypassed as e:
        row['error'] = str(e); row['error_code'] = ErrorCode.BYPASSED
    except AlgoTimeout:
        row['error'] = 'timeout'
    except Exception as e:
        row['error'] = str(e)[:200]

    row['time_s'] = round(time.time() - t0, 3)
    row['_ilabel'] = ilabel
    return row


def _eval_greedy_pipeline(args):
    """Greedy Phase 2 Worker: Base -> Single S4 -> Stacked S4 if improved """
    s2_id, s3_id, n, g, tname, ilabel = args
    alu_op = ALU_FADD; hw = HW
    omega = _W_BOUNDS.get(ilabel, {}).get('omega', 1)
    
    t0 = time.time()
    _set_eval_deadline(EVAL_TIMEOUT)
    
    results = []
    def _err(msg, code=ErrorCode.COMPILE):
        r = dict.fromkeys(SW_COLUMNS, '')
        r.update(s2=s2_id, s3=s3_id, pipeline=f"{s2_id}|{s3_id}",
                 valid=False, error=msg[:200], error_code=code, _ilabel=ilabel)
        return r

    try:
        tree = CBTree(n); topo = build_topology(tname, g)
        ge = min(g, tree.total_nodes); ctx = get_ctx(tree, topo)
        _, s2f = STAGE2_METHODS[s2_id]
        _, s3f = STAGE3_METHODS[s3_id]

        # 1. Base Evaluation
        asgn_base = s2f(tree, ge, topo, hw)
        if not _validate_assignment(tree, asgn_base, ge):
            return [_err('S2_bad', ErrorCode.S2_BAD)]
            
        def _get_metrics(s4_cfg, current_asgn):
            pipe_label = f"{s2_id}|{s3_id}" if not s4_cfg else f"{s2_id}|{s3_id}|{s4_cfg}"
            mapping = s3f(tree, current_asgn, ge, topo, hw)
            cp = ctx.fast_cp_comm(current_asgn)
            ml = ctx.fast_max_load(current_asgn, ge)
            li = ctx.fast_load_imbalance(current_asgn, ge)
            ec = ctx.fast_edge_cut(current_asgn)
            conn = is_connected_partition(tree, current_asgn, ge)
            n_used = len(set(current_asgn[i] if isinstance(current_asgn, list) else current_asgn.get(i, 0)
                             for i in range(tree.total_nodes)))
            ahash = _hash_assignment(current_asgn, tree.total_nodes)
            
            sched = build_schedule(tree, current_asgn, mapping, ge, topo, hw, alu_op=alu_op)
            ms_sched = sched.makespan
            ms = ms_sched if ms_sched > 0 else max(cp, ml)
            ratio = (ms / omega) if (omega > 0 and ms > 0) else -1
            
            progs = generate_instructions(tree, topo, sched, hw, alu_op=alu_op)
            max_imem = max(len(progs[gpu]) for gpu in progs) if progs else 0
            
            imem_overflow = max_imem > hw.imem_depth
            row = dict.fromkeys(SW_COLUMNS, '')
            row.update(
                pipeline=pipe_label, s2=s2_id, s3=s3_id, s4=s4_cfg, makespan=ms,
                makespan_sched=ms_sched, cp_comm=cp, max_load=ml, edge_cut=ec,
                load_imbalance=round(li, 6), connected=conn, valid=True,
                max_imem=max_imem, imem_ok=(not imem_overflow),
                n_gpus_used=n_used, omega=omega, asgn_hash=ahash,
                ratio_to_omega=round(ratio, 4) if ratio > 0 else -1,
                _ilabel=ilabel,
                error=f'IMEM overflow: {max_imem}/{hw.imem_depth}' if imem_overflow else '',
                error_code=ErrorCode.IMEM_OVERFLOW if imem_overflow else ErrorCode.OK,
            )
            return ms, row

        _check_deadline("post-S2")
        ms_base, _ = _get_metrics('', asgn_base)
        
        # Level 1 (Single S4)
        ids = [x for x in STAGE4_METHODS.keys() if x != '4a']
        improving_l1 = []
        for s4a in ids:
            _check_deadline("post-L1")
            _, af = STAGE4_METHODS[s4a]
            asgn_L1 = af(tree, copy.deepcopy(asgn_base), ge, topo, hw)
            if not _validate_assignment(tree, asgn_L1, ge):
                continue
            ms_L1, row_L1 = _get_metrics(s4a, asgn_L1)
            
            if ms_L1 < ms_base:
                results.append(row_L1)
                improving_l1.append((s4a, asgn_L1, ms_L1))
                
        # Level 2 (Stacked S4)
        for s4a, asgn_L1, ms_L1 in improving_l1:
            for s4b in ids:
                if s4a == s4b: continue
                _check_deadline("post-L2")
                _, bf = STAGE4_METHODS[s4b]
                asgn_L2 = bf(tree, copy.deepcopy(asgn_L1), ge, topo, hw)
                if not _validate_assignment(tree, asgn_L2, ge):
                    continue
                s4_cfg = f"{s4a}+{s4b}"
                ms_L2, row_L2 = _get_metrics(s4_cfg, asgn_L2)
                if ms_L2 < ms_L1:
                    results.append(row_L2)
                
    except AlgoBypassed as e:
        results.append(_err(str(e), ErrorCode.BYPASSED))
    except AlgoTimeout:
        results.append(_err('timeout', ErrorCode.EVAL_TIMEOUT))
    except Exception as e:
        results.append(_err(str(e), ErrorCode.COMPILE))
        
    avg_t = round((time.time() - t0)/max(1, len(results)), 3)
    for r in results: r['time_s'] = avg_t
    return results


def _run_sw_phase(phase_name, worker_func, work_items, instances, bounds, nw,
                  csv_filename, expected_per_inst, resume=False):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    if resume:
        complete = set()
        for inst in instances:
            ilabel = inst[3]
            csv_path = os.path.join(_inst_dir(ilabel), csv_filename)
            if os.path.exists(csv_path):
                try:
                    with open(csv_path) as f:
                        n_rows = sum(1 for _ in f) - 1
                    if n_rows >= expected_per_inst:
                        complete.add(ilabel)
                except:
                    pass
        if complete:
            before = len(work_items)
            work_items = [w for w in work_items if w[-1] not in complete]
            print(f"  Resume: {len(complete)} instances complete, "
                  f"{before - len(work_items)} items skipped")

    nr = len(work_items)
    if nr == 0:
        print(f"  All instances already completed.")
        return

    n_inst_todo = len(set(w[-1] for w in work_items))
    print(f"  {nr} items ({n_inst_todo} instances) on {nw} workers")

    inst_rows = defaultdict(list)
    # Live per-instance CSV writers: rows streamed to disk as they arrive
    # (flushed each write, so tail -f works mid-run and a crash loses at most
    # the in-flight row). Final pass re-sorts by makespan for presentation.
    inst_files = {}    # ilabel -> file handle
    inst_writers = {}  # ilabel -> csv.DictWriter

    def _get_writer(ilabel):
        w = inst_writers.get(ilabel)
        if w is not None:
            return w, inst_files[ilabel]
        idir = _inst_dir(ilabel)
        os.makedirs(idir, exist_ok=True)
        csv_path = os.path.join(idir, csv_filename)
        # In resume mode, append to an existing (partial) CSV so we preserve
        # prior rows. Only write the header for a fresh file.
        append = resume and os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
        f = open(csv_path, 'a' if append else 'w', newline='')
        w = csv.DictWriter(f, fieldnames=SW_COLUMNS, extrasaction='ignore')
        if not append:
            w.writeheader()
            f.flush()
        inst_files[ilabel] = f
        inst_writers[ilabel] = w
        return w, f

    ts = time.time(); dc = 0; n_ok = 0

    try:
        pool = multiprocessing.Pool(processes=nw, initializer=_worker_init,
                                    initargs=(instances, bounds))
        for outputs in pool.imap_unordered(worker_func, work_items, chunksize=4):
            if not isinstance(outputs, list):
                outputs = [outputs]
            dc += 1
            for row in outputs:
                ilabel = row.pop('_ilabel', '')
                inst_rows[ilabel].append(row)
                if row.get('valid'):
                    n_ok += 1
    
                w, fh = _get_writer(ilabel)
                w.writerow(row)
                fh.flush()

            step = max(1, nr // 40)
            if dc % step == 0 or dc == nr:
                elapsed = time.time() - ts
                rate = dc / max(elapsed, 0.01)
                eta = (nr - dc) / max(rate, 0.001)
                done_inst = sum(1 for il, rows in inst_rows.items()
                                if len(rows) >= expected_per_inst)
                print(f"    [{dc:>6}/{nr}] {dc*100/nr:5.1f}%  "
                      f"{rate:.1f}/s  ETA={_fmt_time(eta)}  "
                      f"inst={done_inst}/{n_inst_todo}  ok={n_ok}",
                      flush=True)
    finally:
        if 'pool' in locals():
            pool.terminate()
            pool.join()
        for f in inst_files.values():
            try: f.close()
            except Exception: pass

    # Final pass: rewrite each CSV in makespan-sorted order for the report step.
    for ilabel, rows in inst_rows.items():
        idir = _inst_dir(ilabel)
        csv_path = os.path.join(idir, csv_filename)
        rows.sort(key=lambda r: (r.get('makespan', 1e9) if r.get('valid') else 1e9))
        with open(csv_path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=SW_COLUMNS, extrasaction='ignore')
            w.writeheader()
            for row in rows:
                w.writerow(row)

    print(f"\n  {phase_name} done in {_fmt_time(time.time() - ts)}", flush=True)
    print(f"  Valid: {n_ok}/{nr}  |  Instances written: {len(inst_rows)}", flush=True)


# ═══════════════════════════════════════════════════════════════
# SW TOURNAMENT PHASES
# ═══════════════════════════════════════════════════════════════

def run_phase1(instances, bounds, nw, resume=False):
    pipelines = [(s2, s3) for s2 in STAGE2_METHODS for s3 in STAGE3_METHODS]
    work_items = []
    for n, g, tname, ilabel in instances:
        os.makedirs(_inst_dir(ilabel), exist_ok=True)
        for s2, s3 in pipelines:
            work_items.append((s2, s3, '', n, g, tname, ilabel))
    _run_sw_phase('Phase 1 SW Eval', _eval_pipeline, work_items, instances, bounds, nw,
                  'sw_results.csv', len(pipelines), resume)


def enumerate_s4_configs():
    ids = list(STAGE4_METHODS.keys())
    real = [x for x in ids if x != '4a']
    configs = list(ids)
    for a in real:
        for b in real:
            if a != b:
                configs.append(f"{a}+{b}")
    return configs


def run_phase2(unique_pairs, instances, bounds, nw, resume=False):
    pairs = sorted(unique_pairs)
    work_items = []
    for n, g, tname, ilabel in instances:
        os.makedirs(_inst_dir(ilabel), exist_ok=True)
        for s2, s3 in pairs:
            work_items.append((s2, s3, n, g, tname, ilabel))

    _run_sw_phase('Phase 2 SW Refinement', _eval_greedy_pipeline, work_items, instances, bounds, nw,
                  's4_results.csv', 0, resume)


def select_winners(instances, csv_filename, n_tiers=3, max_per=15):
    per_inst = {}
    unique_pairs = set()

    for _, _, _, ilabel in instances:
        csv_path = os.path.join(_inst_dir(ilabel), csv_filename)
        if not os.path.exists(csv_path): continue

        rows = []
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for r in reader:
                try:
                    valid = r.get('valid', '') in ('True', 'true', '1', True)
                    ms = float(r.get('makespan', -1))
                    if valid and ms > 0:
                        s4 = r.get('s4', '')
                        rows.append((ms, r['s2'], r['s3'], s4, r))
                except (ValueError, KeyError):
                    continue

        if not rows: continue

        rows.sort()
        unique_ms = sorted(set(ms for ms, _, _, _, _ in rows))
        threshold = unique_ms[min(n_tiers - 1, len(unique_ms) - 1)]
        selected = [(s2, s3, s4, ms, r)
                     for ms, s2, s3, s4, r in rows if ms <= threshold]
        selected = selected[:max_per]
        per_inst[ilabel] = selected
        for s2, s3, _, _, _ in selected:
            unique_pairs.add((s2, s3))

    return per_inst, unique_pairs


def load_all_valid_pipelines(instances, csv_filename, include_s4=False):
    """Read each instance's SW CSV and return all valid rows shaped for
    run_phase3: {ilabel: [(s2, s3, s4, makespan, row_dict), ...]}.
    include_s4 selects whether the s4 column is preserved (phase 2) or
    blanked out (phase 1).
    """
    per_inst = {}
    for _, _, _, ilabel in instances:
        csv_path = os.path.join(_inst_dir(ilabel), csv_filename)
        if not os.path.exists(csv_path):
            continue
        rows = []
        with open(csv_path) as f:
            for r in csv.DictReader(f):
                try:
                    valid = r.get('valid', '') in ('True', 'true', '1', True)
                    ms = float(r.get('makespan', -1))
                    if valid and ms > 0:
                        s4 = r.get('s4', '') if include_s4 else ''
                        rows.append((r['s2'], r['s3'], s4, ms, r))
                except (ValueError, KeyError):
                    continue
        if rows:
            per_inst[ilabel] = rows
    return per_inst


def load_all_valid_p1_pipelines(instances):
    return load_all_valid_pipelines(instances, 'sw_results.csv',
                                    include_s4=False)


def select_winners_by_hw(instances, hw_results, n_tiers=3, max_per=15):
    """Pick top tiers by HW cycles (vs makespan in select_winners).

    Only hw_pass==True rows with hw_cycles>0 are eligible. Returns the same
    shape as `select_winners`: (per_inst_winners, unique_(s2,s3)_pairs).
    Each winner tuple is (s2, s3, s4, hw_cycles, res_dict) — note field 4
    holds HW cycles here (used downstream purely as a sort key / display).
    """
    per_inst = {}
    unique_pairs = set()
    for _, _, _, ilabel in instances:
        results = hw_results.get(ilabel, [])
        rows = [(int(r['hw_cycles']), r['s2'], r['s3'], r.get('s4', ''), r)
                for r in results
                if r.get('hw_pass') and int(r.get('hw_cycles', -1)) > 0]
        if not rows:
            continue
        rows.sort()
        unique_cyc = sorted(set(c for c, *_ in rows))
        threshold = unique_cyc[min(n_tiers - 1, len(unique_cyc) - 1)]
        selected = [(s2, s3, s4, c, r)
                    for c, s2, s3, s4, r in rows if c <= threshold]
        selected = selected[:max_per]
        per_inst[ilabel] = selected
        for s2, s3, *_ in selected:
            unique_pairs.add((s2, s3))
    return per_inst, unique_pairs


def write_phase_hw_csv(instances, hw_results, filename):
    """Dump per-instance HW results from a run_phase3 invocation."""
    cols = ['s2', 's3', 's4', 'tb_hash', 'unique_hw_sim',
            'hw_pass', 'hw_cycles', 'perf_stall', 'perf_retired',
            'hw_timeout', 'sim_time_s', 'hw_error']
    for _, _, _, ilabel in instances:
        results = hw_results.get(ilabel, [])
        if not results:
            continue
        path = os.path.join(_inst_dir(ilabel), filename)
        with open(path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
            w.writeheader()
            for r in sorted(results,
                            key=lambda x: (not x.get('hw_pass'),
                                           int(x.get('hw_cycles', 10**9)))):
                w.writerow({c: r.get(c, '') for c in cols})


def write_phase_hw_winners_csv(instances, winners, filename):
    """Dump the HW-cycle-ranked winners selected for the next stage."""
    cols = ['rank', 's2', 's3', 's4', 'hw_cycles',
            'tb_hash', 'unique_hw_sim', 'sim_time_s']
    for _, _, _, ilabel in instances:
        sel = winners.get(ilabel, [])
        if not sel:
            continue
        path = os.path.join(_inst_dir(ilabel), filename)
        with open(path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
            w.writeheader()
            for i, (s2, s3, s4, c, r) in enumerate(sel, 1):
                w.writerow({'rank': i, 's2': s2, 's3': s3, 's4': s4,
                            'hw_cycles': c,
                            'tb_hash': r.get('tb_hash', ''),
                            'unique_hw_sim': r.get('unique_hw_sim', False),
                            'sim_time_s': r.get('sim_time_s', 0.0)})


def write_p1_full_report(instances):
    for _, _, _, ilabel in instances:
        idir = _inst_dir(ilabel)
        sw_path = os.path.join(idir, 'sw_results.csv')
        hw_path = os.path.join(idir, 'hw_results.csv')
        out_path = os.path.join(idir, 'p1_full_report.csv')
        
        if not os.path.exists(sw_path): continue
        
        hw_dict = {}
        if os.path.exists(hw_path):
            with open(hw_path) as f:
                for r in csv.DictReader(f):
                    hw_dict[(r['s2'], r['s3'])] = r
                    
        with open(sw_path) as fin, open(out_path, 'w', newline='') as fout:
            reader = csv.DictReader(fin)
            fieldnames = list(reader.fieldnames) + ['hw_pass', 'hw_cycles', 'perf_stall', 'perf_retired', 'hw_timeout', 'sim_time_s', 'hw_error']
            writer = csv.DictWriter(fout, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for r in reader:
                h = hw_dict.get((r['s2'], r['s3']), {})
                r.update(h)
                writer.writerow(r)


# ═══════════════════════════════════════════════════════════════
# PHASE 3: HW SIMULATION WITH TESTBENCH HASHING
# ═══════════════════════════════════════════════════════════════

def _tb_gen_worker(args):
    """Generate TB string + hash for deduplication."""
    s2_id, s3_id, s4_cfg, n, g, tname, ilabel, sim_timeout = args
    alu_op = ALU_FADD; hw = HW

    result = {
        's2': s2_id, 's3': s3_id, 's4': s4_cfg, 'instance': ilabel,
        'sim_timeout': sim_timeout, 'tb_hash': '', 'tb_path': '',
        'hw_pass': False, 'hw_cycles': -1, 'perf_stall': -1,
        'perf_retired': -1, 'hw_timeout': False,
        'sim_time_s': 0.0, 'hw_error': '', 'unique_hw_sim': False
    }

    _set_eval_deadline(EVAL_TIMEOUT)

    try:
        tree = CBTree(n); topo = build_topology(tname, g)
        ge = min(g, tree.total_nodes)

        _, s2f = STAGE2_METHODS[s2_id]
        asgn = s2f(tree, ge, topo, hw)
        if not _validate_assignment(tree, asgn, ge):
            result['hw_error'] = 'S2_bad'; return result

        _, s3f = STAGE3_METHODS[s3_id]
        mapping = s3f(tree, asgn, ge, topo, hw)

        if s4_cfg and s4_cfg != '4a':
            if '+' in s4_cfg:
                a_id, b_id = s4_cfg.split('+')
                _, af = STAGE4_METHODS[a_id]; _, bf = STAGE4_METHODS[b_id]
                ref = af(tree, asgn, ge, topo, hw)
                if _validate_assignment(tree, ref, ge):
                    ref = bf(tree, ref, ge, topo, hw)
                else:
                    ref = asgn
            else:
                _, s4f = STAGE4_METHODS[s4_cfg]
                ref = s4f(tree, asgn, ge, topo, hw)
            if _validate_assignment(tree, ref, ge):
                asgn = ref
            mapping = s3f(tree, asgn, ge, topo, hw)

        sched = build_schedule(tree, asgn, mapping, ge, topo, hw, alu_op=alu_op)
        progs = generate_instructions(tree, topo, sched, hw, alu_op=alu_op)

        tb_sv = emit_sv_testbench(
            tree, topo, progs,
            assignment=asgn, addr_alloc=sched.addr_alloc,
            schedule=sched, alu_op=alu_op)

        result['tb_hash'] = hashlib.sha256(tb_sv.encode()).hexdigest()
        # Write TB to scratch on disk so multi-MB SV text doesn't cross the queue.
        idir = _inst_dir(ilabel)
        os.makedirs(idir, exist_ok=True)
        fd, scratch = tempfile.mkstemp(prefix='_tb_scratch_', suffix='.sv',
                                       dir=idir)
        with os.fdopen(fd, 'w') as f:
            f.write(tb_sv)
        del tb_sv
        result['tb_path'] = scratch

    except AlgoTimeout:
        result['hw_error'] = 'compile_timeout'
    except Exception as e:
        result['hw_error'] = str(e)[:200]

    return result


def _vivado_only_worker(args):
    """Run Vivado on pre-written TB file."""
    ilabel, tb_fname, tb_path, n_leaves, n_nodes, sim_timeout = args
    idir = _inst_dir(ilabel)
    module_name = f"tb_sprs_{n_leaves}L_{n_nodes}G"
    def _cleanup_dir(d):
        for _ in range(5):
            try:
                if os.path.exists(d): shutil.rmtree(d)
                return True
            except:
                time.sleep(0.5)
        return False

    orig_work_dir = os.path.join(idir, f"work_{tb_fname}")
    work_dir = orig_work_dir
    # If directory is locked, use a unique suffix to keep moving
    if not _cleanup_dir(work_dir):
        work_dir = orig_work_dir + f"_{int(time.time()*1000) % 100000}"
        os.makedirs(work_dir, exist_ok=True)
    else:
        os.makedirs(work_dir, exist_ok=True)

    result = {
        'status': 'error', 'pass': False, 'timeout': False,
        'sim_log': '', 'error_msg': '', 'error_code': ErrorCode.HW_OTHER,
        'cycles': -1, 'perf_stall': -1, 'perf_retired': -1, 'sim_time_s': 0.0,
        'ilabel': ilabel, 'tb_fname': tb_fname
    }

    rtl_paths = get_rtl_paths()
    xvlog = os.path.join(VIVADO_BIN, "xvlog" + VIVADO_EXT)
    xelab = os.path.join(VIVADO_BIN, "xelab" + VIVADO_EXT)
    xsim = os.path.join(VIVADO_BIN, "xsim" + VIVADO_EXT)

    if not os.path.exists(xvlog):
        result['error_msg'] = f"Vivado not found at {VIVADO_BIN}"
        result['error_code'] = ErrorCode.VIVADO_MISSING
        return result

    os.makedirs(work_dir, exist_ok=True)
    t_sim = time.time()

    def _tail(path, n=2000):
        try:
            sz = os.path.getsize(path)
            with open(path, errors='replace') as lf:
                if sz > n:
                    lf.seek(sz - n)
                return lf.read()
        except Exception:
            return ''

    try:
        src_files = rtl_paths + [tb_path]
        # Redirect stdout+stderr to disk to avoid pipe-buffer deadlocks on
        # verbose compiles (same reason as xsim below).
        xvlog_log = os.path.join(work_dir, "xvlog.log")
        with open(xvlog_log, 'w') as lf:
            p1 = subprocess.run([xvlog, "-sv"] + src_files,
                                stdout=lf, stderr=subprocess.STDOUT,
                                timeout=1800, cwd=work_dir)
        if p1.returncode != 0:
            result['error_msg'] = "xvlog: " + _tail(xvlog_log)[:500]
            result['error_code'] = ErrorCode.XVLOG_FAIL
            return result

        snap = f"sim_{tb_fname}"
        xelab_log = os.path.join(work_dir, "xelab.log")
        with open(xelab_log, 'w') as lf:
            p2 = subprocess.run([xelab, "-timescale", "1ns/1ps", "-debug", "typical",
                                 "-top", module_name, "-snapshot", snap],
                                stdout=lf, stderr=subprocess.STDOUT,
                                timeout=1800, cwd=work_dir)
        if p2.returncode != 0:
            result['error_msg'] = "xelab: " + _tail(xelab_log)[:500]
            result['error_code'] = ErrorCode.XELAB_FAIL
            return result

        # Stream xsim output to disk to avoid buffering large logs in RAM
        # (and to prevent pipe-buffer deadlocks on verbose TBs).
        # start_new_session=True + killpg on timeout reaps the whole
        # bash→loader→xsim→xsimk descendant tree. subprocess.run(timeout=)
        # only SIGKILLs the immediate child, orphaning xsimk to the launcher.
        xsim_log = os.path.join(work_dir, "xsim_output.log")
        with open(xsim_log, 'w') as lf:
            proc = subprocess.Popen([xsim, snap, "-R"],
                                    stdout=lf, stderr=subprocess.STDOUT,
                                    cwd=work_dir, start_new_session=True)
            try:
                proc.wait(timeout=sim_timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired: pass
                raise
        # Cap in-memory log at 256 KB (tail) — failure triage only needs the end.
        LOG_CAP = 256 * 1024
        log_size = os.path.getsize(xsim_log)
        with open(xsim_log, errors='replace') as lf:
            if log_size > LOG_CAP:
                lf.seek(log_size - LOG_CAP)
                sim_output = "...[truncated]...\n" + lf.read()
            else:
                sim_output = lf.read()
        result['sim_log'] = sim_output

        if "[PASS]" in sim_output:
            result['status'] = 'pass'; result['pass'] = True
            result['error_code'] = ErrorCode.OK
        elif "TIMEOUT" in sim_output:
            result['status'] = 'sim_timeout'; result['timeout'] = True
            result['error_code'] = ErrorCode.SIM_TB_TIMEOUT
        elif "[FAIL]" in sim_output:
            result['status'] = 'fail'
            result['error_code'] = ErrorCode.SIM_FAIL
            for line in sim_output.split('\n'):
                if '[FAIL]' in line or '[ERROR]' in line:
                    result['error_msg'] += line.strip() + '; '
        else:
            result['status'] = 'unknown'
            result['error_code'] = ErrorCode.SIM_UNKNOWN
            result['error_msg'] = sim_output[-500:]

        for pat, key in [('perf_total', 'cycles'), ('perf_stall', 'perf_stall'),
                         ('perf_retired', 'perf_retired')]:
            vals = re.findall(rf'{pat}=(\d+)', sim_output)
            if vals:
                result[key] = max(int(x) for x in vals) if key == 'cycles' else sum(int(x) for x in vals)

    except subprocess.TimeoutExpired:
        result['status'] = 'process_timeout'; result['timeout'] = True
        result['error_msg'] = f"Timed out after {sim_timeout}s"
        result['error_code'] = ErrorCode.SIM_TIMEOUT
    except Exception as e:
        result['error_msg'] = str(e)[:200]
        result['error_code'] = ErrorCode.HW_OTHER

    finally:
        result['sim_time_s'] = round(time.time() - t_sim, 2)
        try: shutil.rmtree(work_dir)
        except: pass

    return result


_HW_TRANSIENT_CODES = (
    ErrorCode.XVLOG_FAIL, ErrorCode.XELAB_FAIL,
    ErrorCode.SIM_TIMEOUT, ErrorCode.HW_OTHER,
)


def _compute_safe_hw_workers(target, ram_per_worker, label='hw_workers'):
    """Return min(target, free_RAM // ram_per_worker). Logs the clamp once."""
    free_gb = _free_ram_gb()
    if free_gb == float('inf'):
        return target, free_gb
    safe = max(1, int(free_gb // ram_per_worker))
    if safe < target:
        log('INFO', f"Capping {label} {target} -> {safe} "
                    f"(free RAM {free_gb:.1f} GB, ~{ram_per_worker:g} GB/worker)")
        return safe, free_gb
    return target, free_gb


def _adaptive_hw_dispatch(vivado_queue, sim_worker, hw_workers, ram_per_worker,
                          max_retries, on_complete, on_progress):
    """Run sim_worker over vivado_queue with:
      - maxtasksperchild=1 (each worker exits after one sim — frees Vivado RAM)
      - per-item retry on transient HW errors (XVLOG/XELAB/SIM_TIMEOUT/HW_OTHER)
      - pool-level crash recovery (BrokenPool / OSError / unexpected exceptions)
      - RAM re-check between retry rounds so we don't restart into an OOM state

    Returns nothing; calls on_complete(sim_result) for each finished item
    (final pass or terminal failure) and on_progress(done, total) for pacing.
    """
    remaining = list(vivado_queue)
    retry = defaultdict(int)
    total = len(vivado_queue)
    done_count = 0
    attempt = 0
    item_key = lambda it: (it[0], it[1])   # (ilabel, tb_fname)

    while remaining:
        attempt += 1
        cur_workers, free_gb = _compute_safe_hw_workers(
            hw_workers, ram_per_worker, label='hw_workers')
        cur_workers = min(cur_workers, len(remaining))
        log('INFO', f"HW round {attempt}: {len(remaining)} item(s) on "
                    f"{cur_workers} workers (free RAM {free_gb:.1f} GB)")

        completed_keys = set()
        next_remaining = []

        pool = multiprocessing.Pool(processes=cur_workers, maxtasksperchild=1)
        try:
            for sim in pool.imap_unordered(sim_worker, remaining, chunksize=1):
                key = (sim.get('ilabel', ''), sim.get('tb_fname', ''))
                completed_keys.add(key)
                ec = sim.get('error_code',
                             ErrorCode.OK if sim.get('pass') else ErrorCode.HW_OTHER)

                if not sim.get('pass') and ec in _HW_TRANSIENT_CODES \
                        and retry[key] < max_retries:
                    retry[key] += 1
                    log('WARN', f"  transient {ec} on {key[0]}/{key[1]} "
                                f"— retry {retry[key]}/{max_retries}")
                    # Find the original work item to re-enqueue
                    for it in remaining:
                        if item_key(it) == key:
                            next_remaining.append(it)
                            break
                else:
                    done_count += 1
                    on_complete(sim, retry[key])
                    on_progress(done_count, total)
            pool.close()
            pool.join()
        except (BaseException,) as e:
            # BrokenProcessPool / OSError / Ctrl-C / etc.
            pool.terminate()
            pool.join()
            if isinstance(e, KeyboardInterrupt):
                raise
            log('ERROR', f"  pool crash ({type(e).__name__}: {e}) — "
                          f"will retry incomplete items")
            for it in remaining:
                if item_key(it) not in completed_keys and item_key(it) not in {item_key(x) for x in next_remaining}:
                    if retry[item_key(it)] < max_retries:
                        retry[item_key(it)] += 1
                        next_remaining.append(it)
                    else:
                        done_count += 1
                        on_complete({
                            'ilabel': it[0], 'tb_fname': it[1],
                            'pass': False, 'cycles': -1,
                            'perf_stall': -1, 'perf_retired': -1,
                            'timeout': False, 'sim_time_s': 0.0,
                            'sim_log': f"pool crash after {max_retries} retries",
                            'error_msg': f"pool crash ({type(e).__name__})",
                            'error_code': ErrorCode.HW_OTHER,
                        }, retry[item_key(it)])

        # Items we couldn't retry → emit terminal-failure placeholder.
        for it in remaining:
            k = item_key(it)
            if k not in completed_keys and it not in next_remaining:
                done_count += 1
                on_complete({
                    'ilabel': it[0], 'tb_fname': it[1],
                    'pass': False, 'cycles': -1,
                    'perf_stall': -1, 'perf_retired': -1,
                    'timeout': False, 'sim_time_s': 0.0,
                    'sim_log': '',
                    'error_msg': f"retries exhausted ({max_retries})",
                    'error_code': ErrorCode.HW_OTHER,
                }, retry[k])

        remaining = next_remaining
        if remaining:
            time.sleep(2)  # let RAM settle before re-evaluating cap


def _load_phase3_done(phase_tag):
    """Parse live_hw_results_{phase_tag}.csv into {(ilabel, tb_fname): row}.

    Allows --resume to skip Vivado sims that already completed in a prior run.
    Only rows with a usable Pass/Cycles value are kept; blank or malformed
    lines fall through and get re-simulated.
    """
    path = os.path.join(RESULTS_DIR, f"live_hw_results_{phase_tag}.csv")
    done = {}
    if not os.path.exists(path):
        return done
    try:
        with open(path) as f:
            for r in csv.DictReader(f):
                ilabel = r.get('Instance'); tb_fname = r.get('TB_Name')
                if not ilabel or not tb_fname:
                    continue
                done[(ilabel, tb_fname)] = r
    except Exception:
        pass
    return done


def run_phase3(instances, final_winners, hw_workers, sim_timeout,
               phase_tag='final', resume=False,
               ram_per_worker=DEFAULT_HW_RAM_GB,
               max_retries=DEFAULT_MAX_HW_RETRIES):
    """HW sim stage: Fast TB generation + hashed Vivado deduplication.

    phase_tag identifies which tournament stage this HW batch belongs to
    ('p1' = HW-rank of all 180 P1 pipelines, 'final' = post-P2 winners).
    Used in log filenames so P1-HW and final-HW don't overwrite each other.
    """
    inst_map = {il: (n, g, tn) for n, g, tn, il in instances}
    work_items = []

    for ilabel, winner_list in final_winners.items():
        n, g, tname = inst_map[ilabel]
        for s2, s3, s4, ms, _ in winner_list:
            work_items.append((s2, s3, s4, n, g, tname, ilabel, sim_timeout))

    nr = len(work_items)
    if nr == 0:
        print("  No winners to simulate."); return {}

    # Memory-based worker cap (configurable via --hw-ram-gb)
    hw_workers, _ = _compute_safe_hw_workers(hw_workers, ram_per_worker)

    # Disk-space guard for Vivado work dirs and logs
    try:
        free_disk_gb = shutil.disk_usage(RESULTS_DIR).free / (1024**3)
        if free_disk_gb < 5:
            print(f"  WARNING: only {free_disk_gb:.1f} GB free on results disk — "
                  f"Vivado may fail. Consider freeing space before continuing.")
    except Exception:
        pass

    print(f"  Step 3A: Generating {nr} testbenches for deduplication...")
    tb_results = []
    
    try:
        pool1 = multiprocessing.Pool(processes=hw_workers, initializer=_worker_init,
                                     initargs=(instances, {}))
        for res in pool1.imap_unordered(_tb_gen_worker, work_items, chunksize=4):
            tb_results.append(res)
    finally:
        if 'pool1' in locals():
            pool1.terminate()
            pool1.join()
            
    print("  Step 3B: Deduplicating and running Vivado...")
    vivado_queue = []
    leader_map = {} # hash -> leader_res
    follower_map = defaultdict(list) # hash -> [follower_res, ...]
    
    # Identify unique testbenches per instance
    inst_hashes = defaultdict(list)
    for res in tb_results:
        h = res.get('tb_hash')
        scratch = res.pop('tb_path', '') or ''
        if not h:
            if scratch and os.path.exists(scratch):
                try: os.unlink(scratch)
                except OSError: pass
            continue # compilation error occurred
        key = (res['instance'], h)
        if key not in leader_map:
            res['unique_hw_sim'] = True
            leader_map[key] = res
            inst_hashes[res['instance']].append(h)

            s2_safe = _safe_name(res['s2'])
            s3_safe = _safe_name(res['s3'])
            s4_safe = _safe_name(res.get('s4', ''))
            tb_fname = f"tb_{s2_safe}_{s3_safe}_{s4_safe}"
            res['tb_fname'] = tb_fname

            idir = _inst_dir(res['instance'])
            tb_path = os.path.join(idir, f"{tb_fname}.sv")
            # Atomic rename — no SV string ever read into main.
            if scratch and os.path.exists(scratch):
                os.replace(scratch, tb_path)

            n, g, tname = inst_map[res['instance']]
            topo = build_topology(tname, g)
            vivado_queue.append((res['instance'], tb_fname, tb_path, n, topo.n_nodes, sim_timeout))
        else:
            res['unique_hw_sim'] = False
            if scratch and os.path.exists(scratch):
                try: os.unlink(scratch)
                except OSError: pass
            follower_map[key].append(res)
            
    n_unique = len(vivado_queue)
    if nr > 0:
        print(f"  Unique behaviors found: {n_unique} / {nr} "
              f"({(nr-n_unique)*100.0/nr:.1f}% simulations skipped)")

    # Resume: skip Vivado sims already recorded in live_hw_results_{tag}.csv
    if resume:
        done = _load_phase3_done(phase_tag)
        if done:
            remaining = []; n_reused = 0; n_reused_fail = 0
            for item in vivado_queue:
                ilabel, tb_fname, _, _, _, _ = item
                cached = done.get((ilabel, tb_fname))
                if cached is None:
                    remaining.append(item); continue
                try:
                    cycles = int(cached.get('Cycles', -1))
                except (TypeError, ValueError):
                    cycles = -1
                passed = str(cached.get('Pass', '')).strip().lower() in ('true', '1', 'pass')
                try:
                    sim_t = float(cached.get('SimTime_s', 0) or 0)
                except (TypeError, ValueError):
                    sim_t = 0.0
                # Locate the leader for this tb_fname and propagate to followers
                leader_key = None
                for h in inst_hashes[ilabel]:
                    if leader_map[(ilabel, h)].get('tb_fname') == tb_fname:
                        leader_key = (ilabel, h); break
                if leader_key is None:
                    remaining.append(item); continue
                leader = leader_map[leader_key]
                cached_ec = (cached.get('ErrorCode') or '').strip() or (
                    ErrorCode.OK if passed else ErrorCode.HW_OTHER)
                for dest in [leader] + follower_map[leader_key]:
                    dest['hw_pass'] = passed
                    dest['hw_cycles'] = cycles
                    dest['sim_time_s'] = sim_t
                    dest['hw_timeout'] = False
                    dest['perf_stall'] = dest.get('perf_stall', -1)
                    dest['perf_retired'] = dest.get('perf_retired', -1)
                    dest['hw_error_code'] = cached_ec
                    if not passed:
                        dest['hw_error'] = (cached.get('Error', '') or '')[:200]
                n_reused += 1
                if not passed:
                    n_reused_fail += 1
            if n_reused:
                log('INFO', f"Resume: reused {n_reused} cached sims "
                            f"({n_reused_fail} failures, {len(remaining)} remaining)")
                if n_reused_fail:
                    log('INFO', "    delete failed rows from "
                                f"live_hw_results_{phase_tag}.csv to retry them")
            vivado_queue = remaining
            n_unique = len(vivado_queue)  # progress loop uses this for ETA

    hw_results = defaultdict(list)
    ts = time.time(); n_pass_box = [0]

    def _commit(sim, attempts_used):
        ilabel = sim.get('ilabel', ''); tb_fname = sim.get('tb_fname', '')
        leader_key = None
        for h in inst_hashes[ilabel]:
            if leader_map[(ilabel, h)].get('tb_fname') == tb_fname:
                leader_key = (ilabel, h); break
        if not leader_key:
            return
        leader = leader_map[leader_key]
        ec = sim.get('error_code',
                     ErrorCode.OK if sim.get('pass') else ErrorCode.HW_OTHER)
        for dest in [leader] + follower_map[leader_key]:
            dest['hw_pass'] = sim.get('pass', False)
            dest['hw_cycles'] = sim.get('cycles', -1)
            dest['perf_stall'] = sim.get('perf_stall', -1)
            dest['perf_retired'] = sim.get('perf_retired', -1)
            dest['hw_timeout'] = sim.get('timeout', False)
            dest['sim_time_s'] = sim.get('sim_time_s', 0.0)
            dest['hw_error_code'] = ec
            if not sim.get('pass') and sim.get('error_msg'):
                dest['hw_error'] = sim['error_msg'][:200]

        idir = _inst_dir(ilabel)
        if not sim.get('pass'):
            log_path = os.path.join(idir, f"sim_{tb_fname.replace('tb_', '')}.log")
            with open(log_path, 'w') as f:
                f.write(sim.get('sim_log', '')); f.flush()
            pipe_dbg = f"{leader['s2']}|{leader['s3']}"
            if leader.get('s4', ''):
                pipe_dbg += f"|{leader['s4']}"
            retry_tag = f" (retries={attempts_used})" if attempts_used else ""
            log('ERROR', f"{ilabel}  {pipe_dbg}  {ec}{retry_tag}  → {log_path}")

        live_log = os.path.join(RESULTS_DIR, f"live_hw_results_{phase_tag}.csv")
        try:
            is_new = not os.path.exists(live_log)
            with open(live_log, 'a') as f:
                if is_new:
                    f.write("Instance,Pipeline,TB_Name,Pass,Cycles,SimTime_s,ErrorCode,Error\n")
                f.write(f"{ilabel},{leader['s2']}|{leader['s3']},{tb_fname},"
                        f"{sim.get('pass', False)},{sim.get('cycles',-1)},"
                        f"{sim.get('sim_time_s',0.0)},{ec},"
                        f"{sim.get('error_msg','')[:50].replace(',', ';')}\n")
        except Exception:
            pass

        if sim.get('pass'):
            n_pass_box[0] += 1

    def _progress(done, total):
        step = max(1, total // 20)
        if done % step == 0 or done == total:
            elapsed = time.time() - ts
            rate = done / max(elapsed, 0.01)
            eta = (total - done) / max(rate, 0.001)
            print(f"    [{done:>6}/{total}] {done*100/total:5.1f}%  "
                  f"ETA={_fmt_time(eta)}  pass={n_pass_box[0]}", flush=True)

    _adaptive_hw_dispatch(vivado_queue, _vivado_only_worker, hw_workers,
                          ram_per_worker, max_retries, _commit, _progress)

    print(f"\n  Phase 3 Vivado done in {_fmt_time(time.time() - ts)}")
    
    for res in tb_results:
        hw_results[res['instance']].append(res)
        
    return dict(hw_results)


# ═══════════════════════════════════════════════════════════════
# COMBINED REPORTS
# ═══════════════════════════════════════════════════════════════

def generate_reports(instances, final_winners, hw_results, bounds, mode):
    inst_map = {il: (n, g, tn) for n, g, tn, il in instances}
    summary_rows = []

    for _, _, _, ilabel in instances:
        n, g, tname = inst_map[ilabel]
        idir = _inst_dir(ilabel)
        lb = bounds.get(ilabel, {})
        omega = lb.get('omega', 1)
        active = lb.get('active_bound', '?')

        winner_list = final_winners.get(ilabel, [])
        hw_map = {}
        for res in hw_results.get(ilabel, []):
            hw_map[(res['s2'], res['s3'], res.get('s4', ''))] = res

        w_csv = os.path.join(idir, 'winners.csv')
        with open(w_csv, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=WINNER_COLUMNS, extrasaction='ignore')
            w.writeheader()
            for rank, (s2, s3, s4, ms, sw) in enumerate(winner_list, 1):
                hw = hw_map.get((s2, s3, s4), {})
                pipe = f"{s2}|{s3}" if not s4 else f"{s2}|{s3}|{s4}"
                row = {
                    'rank': rank, 'pipeline': pipe, 's2': s2, 's3': s3, 's4': s4,
                    'makespan': ms,
                    'makespan_sched': sw.get('makespan_sched', ''),
                    'cp_comm': sw.get('cp_comm', ''),
                    'max_load': sw.get('max_load', ''),
                    'edge_cut': sw.get('edge_cut', ''),
                    'load_imbalance': sw.get('load_imbalance', ''),
                    'connected': sw.get('connected', ''),
                    'max_imem': sw.get('max_imem', ''),
                    'imem_ok': sw.get('imem_ok', ''),
                    'omega': omega,
                    'ratio_to_omega': sw.get('ratio_to_omega', ''),
                    'asgn_hash': sw.get('asgn_hash', ''),
                    'tb_hash': hw.get('tb_hash', ''),
                    'hw_pass': hw.get('hw_pass', ''),
                    'hw_cycles': hw.get('hw_cycles', ''),
                    'perf_stall': hw.get('perf_stall', ''),
                    'perf_retired': hw.get('perf_retired', ''),
                    'hw_timeout': hw.get('hw_timeout', ''),
                    'sim_time_s': hw.get('sim_time_s', ''),
                    'hw_error': hw.get('hw_error', ''),
                    'unique_hw_sim': hw.get('unique_hw_sim', '')
                }
                w.writerow(row)

        sw_csv_name = 'sw_results.csv' if mode == 'phase1' else 's4_results.csv'
        n_sw_valid = _count_valid(os.path.join(idir, sw_csv_name))

        best_ms = winner_list[0][3] if winner_list else -1
        s2b, s3b, s4b = (winner_list[0][0], winner_list[0][1],
                          winner_list[0][2]) if winner_list else ('', '', '')
        best_pipe = f"{s2b}|{s3b}" if not s4b else f"{s2b}|{s3b}|{s4b}"
        best_ratio = round(best_ms / omega, 4) if (omega > 0 and best_ms > 0) else -1
        
        n_hw_pass = sum(1 for r in hw_results.get(ilabel, []) if r.get('unique_hw_sim') and r.get('hw_pass'))
        n_unique_sims = sum(1 for r in hw_results.get(ilabel, []) if r.get('unique_hw_sim'))
        
        best_hw = -1
        for r in hw_results.get(ilabel, []):
            if r.get('hw_pass') and r.get('hw_cycles', -1) > 0:
                if best_hw < 0 or r['hw_cycles'] < best_hw:
                    best_hw = r['hw_cycles']

        sw_time = _sum_time(os.path.join(idir, 'sw_results.csv'))
        if mode == 'phase2':
            sw_time += _sum_time(os.path.join(idir, 's4_results.csv'))
        # Only sum sim times for unique hardware sims
        hw_time = sum(r.get('sim_time_s', 0) for r in hw_results.get(ilabel, []) if r.get('unique_hw_sim'))

        summary_rows.append({
            'instance': ilabel, 'N': n, 'G': g, 'topology': tname,
            'omega': omega, 'active_bound': active,
            'best_pipeline': best_pipe, 'best_makespan': best_ms,
            'best_ratio': best_ratio, 'n_sw_valid': n_sw_valid,
            'n_winners': len(winner_list), 'n_unique_sims': n_unique_sims,
            'n_hw_pass': n_hw_pass, 'best_hw_cycles': best_hw,
            'sw_time_s': round(sw_time, 2), 'hw_time_s': round(hw_time, 2)
        })

    summary_csv = os.path.join(RESULTS_DIR, 'summary.csv')
    with open(summary_csv, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        w.writeheader()
        for row in summary_rows:
            w.writerow(row)
    return summary_rows


def _count_valid(csv_path):
    if not os.path.exists(csv_path): return 0
    try:
        with open(csv_path) as f:
            return sum(1 for r in csv.DictReader(f)
                       if r.get('valid', '') in ('True', 'true', '1'))
    except:
        return 0


def _sum_time(csv_path):
    if not os.path.exists(csv_path): return 0
    try:
        with open(csv_path) as f:
            return sum(float(r.get('time_s', 0)) for r in csv.DictReader(f))
    except:
        return 0


def _print_summary(instances, bounds, winners, hw_results=None):
    if hw_results is None: hw_results = {}
    print(f'\n{"="*80}')
    print(f'  RESULTS')
    print(f'{"="*80}')
    print(f'  {"Instance":24s}  {"Best Pipeline":24s}  {"MS":>6}  {"Om":>6}  '
          f'{"Ratio":>6}  {"HW":>3}')
    print(f'  {"-"*78}')
    for _, _, _, ilabel in instances:
        wl = winners.get(ilabel, [])
        lb = bounds.get(ilabel, {})
        omega = lb.get('omega', 1)
        if wl:
            s2, s3, s4, ms, _ = wl[0]
            pipe = f"{s2}|{s3}" if not s4 else f"{s2}|{s3}|{s4}"
            ratio = f"{ms/omega:.2f}" if omega > 0 and ms > 0 else 'N/A'
            n_hw = sum(1 for r in hw_results.get(ilabel, []) if r.get('unique_hw_sim') and r.get('hw_pass'))
            hw_str = str(n_hw) if n_hw > 0 else '-'
        else:
            pipe = '-'; ms = -1; ratio = 'N/A'; hw_str = '-'
        print(f"  {ilabel:24s}  {pipe:24s}  {ms:>6.0f}  {omega:>6.0f}  "
              f"{ratio:>6}  {hw_str:>3}")

    print(f'\n  Output: {RESULTS_DIR}/')
    print(f'  Summary: {os.path.join(RESULTS_DIR, "summary.csv")}')
    for _, _, _, ilabel in instances[:3]:
        idir = _inst_dir(ilabel)
        files = sorted(os.listdir(idir)) if os.path.exists(idir) else []
        print(f'  {ilabel}/: {", ".join(files)}')
    if len(instances) > 3:
        print(f'  ... +{len(instances)-3} more')
    print(f'{"="*80}\n')


def _print_error_summary(rows_by_inst):
    """Aggregate SW + HW error codes and print a triage table.

    Reads `error_code` (SW failures) and `hw_error_code` (HW failures) from every
    row in rows_by_inst (typically the hw_results_map). Prints nothing if no
    non-OK codes appear.
    """
    counts = defaultdict(int)
    sample = {}        # code -> first ilabel seen (pointer for log triage)
    pipe_sample = {}   # code -> sample "s2|s3[|s4]" for context
    n_rows = 0
    for ilabel, rows in (rows_by_inst or {}).items():
        for r in rows:
            n_rows += 1
            for field in ('error_code', 'hw_error_code'):
                ec = (r.get(field) or '').strip()
                if not ec or ec == ErrorCode.OK:
                    continue
                counts[ec] += 1
                sample.setdefault(ec, ilabel)
                if ec not in pipe_sample:
                    s2 = r.get('s2', '?'); s3 = r.get('s3', '?'); s4 = r.get('s4', '')
                    pipe_sample[ec] = f"{s2}|{s3}" + (f"|{s4}" if s4 else "")

    if n_rows == 0:
        # Bailed before producing any rows — caller already surfaced the reason.
        return
    if not counts:
        log('OK', 'No errors detected across SW + HW.')
        return

    print()
    print('=' * 80)
    print('  TROUBLESHOOTING — error code summary')
    print('=' * 80)
    print(f'  {"Code":<18} {"Count":>6}  Description')
    print(f'  {"-"*18} {"-"*6}  {"-"*54}')
    for code in sorted(counts.keys()):
        desc, hint = ErrorCode.describe(code)
        print(f'  {code:<18} {counts[code]:>6}  {desc}')
        if hint:
            print(f'  {"":<18} {"":>6}  -> {hint}')
        s = sample.get(code, '')
        p = pipe_sample.get(code, '')
        if s:
            print(f'  {"":<18} {"":>6}  e.g. results/{s}/ ({p})')
    print('=' * 80)
    print()


# ═══════════════════════════════════════════════════════════════
# UNIFIED PHASE 1:  SW eval + TB gen in one pass, then HW sim
# ═══════════════════════════════════════════════════════════════

UNIFIED_COLUMNS = SW_COLUMNS + [
    'hw_pass', 'hw_cycles', 'perf_stall', 'perf_retired',
    'hw_timeout', 'sim_time_s', 'hw_error', 'hw_error_code',
]


def _unified_p1_worker(args):
    """Single-pass worker: run SW pipeline AND generate TB + hash.

    Returns a dict with all SW_COLUMNS plus tb_hash and tb_sv.
    Invalid pipelines return with empty tb_hash (no TB generated).
    """
    s2_id, s3_id, n, g, tname, ilabel = args
    label = f"{s2_id}|{s3_id}"
    alu_op = ALU_FADD; hw = HW
    omega = _W_BOUNDS.get(ilabel, {}).get('omega', 1)

    row = dict.fromkeys(SW_COLUMNS, '')
    row.update(pipeline=label, s2=s2_id, s3=s3_id, s4='', makespan=-1,
               makespan_sched=-1, cp_comm=-1, max_load=-1, edge_cut=-1,
               load_imbalance=-1, connected=False, valid=False, max_imem=-1,
               imem_ok=False, n_gpus_used=0, omega=omega, ratio_to_omega=-1,
               time_s=0.0, error='', error_code=ErrorCode.OK, asgn_hash='',
               tb_hash='', tb_path='')

    t0 = time.time()
    _set_eval_deadline(EVAL_TIMEOUT)

    try:
        tree = CBTree(n); topo = build_topology(tname, g)
        ge = min(g, tree.total_nodes); ctx = get_ctx(tree, topo)

        _, s2f = STAGE2_METHODS[s2_id]
        asgn = s2f(tree, ge, topo, hw)
        if not _validate_assignment(tree, asgn, ge):
            row['error'] = 'S2_bad'; row['error_code'] = ErrorCode.S2_BAD
            row['time_s'] = round(time.time()-t0, 3)
            row['_ilabel'] = ilabel
            return row
        _check_deadline("post-S2")

        _, s3f = STAGE3_METHODS[s3_id]
        mapping = s3f(tree, asgn, ge, topo, hw)
        _check_deadline("post-S3")

        cp = ctx.fast_cp_comm(asgn)
        ml = ctx.fast_max_load(asgn, ge)
        li = ctx.fast_load_imbalance(asgn, ge)
        ec = ctx.fast_edge_cut(asgn)
        conn = is_connected_partition(tree, asgn, ge)
        n_used = len(set(asgn[i] if isinstance(asgn, list) else asgn.get(i, 0)
                         for i in range(tree.total_nodes)))
        ahash = _hash_assignment(asgn, tree.total_nodes)

        sched = build_schedule(tree, asgn, mapping, ge, topo, hw, alu_op=alu_op)
        ms_sched = sched.makespan
        ms = ms_sched if ms_sched > 0 else max(cp, ml)
        ratio = (ms / omega) if (omega > 0 and ms > 0) else -1

        progs = generate_instructions(tree, topo, sched, hw, alu_op=alu_op)
        max_imem_actual = max(len(progs[gpu]) for gpu in progs) if progs else 0
        _check_deadline("post-codegen")

        row.update(
            makespan=ms, makespan_sched=ms_sched, cp_comm=cp, max_load=ml,
            edge_cut=ec, load_imbalance=round(li, 6), connected=conn,
            valid=True, max_imem=max_imem_actual,
            imem_ok=(max_imem_actual <= hw.imem_depth),
            n_gpus_used=n_used,
            ratio_to_omega=round(ratio, 4) if ratio > 0 else -1,
            asgn_hash=ahash)

        if max_imem_actual > hw.imem_depth:
            row['error'] = f'IMEM overflow: {max_imem_actual}/{hw.imem_depth}'
            row['error_code'] = ErrorCode.IMEM_OVERFLOW

        # ── TB generation: write to scratch file, return path (not string)
        # so multi-MB SV text never crosses the multiprocessing queue.
        tb_sv = emit_sv_testbench(
            tree, topo, progs,
            assignment=asgn, addr_alloc=sched.addr_alloc,
            schedule=sched, alu_op=alu_op)
        row['tb_hash'] = hashlib.sha256(tb_sv.encode()).hexdigest()
        idir = _inst_dir(ilabel)
        fd, scratch = tempfile.mkstemp(prefix='_tb_scratch_', suffix='.sv',
                                       dir=idir)
        with os.fdopen(fd, 'w') as f:
            f.write(tb_sv)
        del tb_sv
        row['tb_path'] = scratch

    except AlgoBypassed as e:
        row['error'] = str(e)
        row['error_code'] = ErrorCode.BYPASSED
    except AlgoTimeout:
        row['error'] = 'timeout'
        row['error_code'] = ErrorCode.EVAL_TIMEOUT
    except Exception as e:
        row['error'] = str(e)[:200]
        row['error_code'] = ErrorCode.COMPILE

    row['time_s'] = round(time.time() - t0, 3)
    row['_ilabel'] = ilabel
    return row


def _verilator_env():
    """Build an env dict with MSYS2 toolchain on PATH + VERILATOR_ROOT (Windows)."""
    env = os.environ.copy()
    if IS_WINDOWS:
        msys_dirs = [r'C:\msys64\mingw64\bin', r'C:\msys64\usr\bin']
        existing = env.get('PATH', '')
        prepend = os.pathsep.join(d for d in msys_dirs if os.path.isdir(d))
        if prepend:
            env['PATH'] = prepend + os.pathsep + existing
        # Verilator needs VERILATOR_ROOT to find its include/ and bin/ dirs
        vlt_root = r'C:\msys64\mingw64\share\verilator'
        if os.path.isdir(vlt_root):
            env['VERILATOR_ROOT'] = vlt_root
    return env

_VLT_ENV = None  # lazy-init per worker process


def _verilator_sim_worker(args):
    """Compile + simulate one unique TB using Verilator."""
    global _VLT_ENV
    if _VLT_ENV is None:
        _VLT_ENV = _verilator_env()

    ilabel, tb_fname, tb_path, n_leaves, n_nodes, sim_timeout = args
    idir = _inst_dir(ilabel)
    module_name = f"tb_sprs_{n_leaves}L_{n_nodes}G"

    work_dir = os.path.join(idir, f"vlt_{tb_fname}")
    os.makedirs(work_dir, exist_ok=True)

    result = {
        'status': 'error', 'pass': False, 'timeout': False,
        'sim_log': '', 'error_msg': '', 'cycles': -1,
        'perf_stall': -1, 'perf_retired': -1, 'sim_time_s': 0.0,
        'ilabel': ilabel, 'tb_fname': tb_fname
    }

    rtl_paths = get_rtl_paths()
    t_sim = time.time()

    try:
        # ── Compile ──
        obj_dir = os.path.join(work_dir, 'obj_dir')
        compile_log = os.path.join(work_dir, 'verilator_compile.log')
        compile_cmd = [
            _VERILATOR_BIN, '--sv', '--binary', '--timing', '-O3',
            '-j', '1',  # single-threaded compile per worker (parallelism at pool level)
            '--top-module', module_name,
            '-o', 'sim_bin',
            '--Mdir', obj_dir,
            '-Wno-fatal',  # don't abort on warnings
        ] + rtl_paths + [tb_path]

        with open(compile_log, 'w') as lf:
            pc = subprocess.run(compile_cmd, stdout=lf, stderr=subprocess.STDOUT,
                                timeout=1800, cwd=work_dir, env=_VLT_ENV)
        if pc.returncode != 0:
            with open(compile_log, errors='replace') as lf:
                result['error_msg'] = "verilator compile: " + lf.read()[-500:]
            return result

        # ── Simulate ──
        sim_bin = os.path.join(obj_dir, 'sim_bin')
        if IS_WINDOWS:
            sim_bin += '.exe'
        if not os.path.exists(sim_bin):
            result['error_msg'] = f"sim binary not found at {sim_bin}"
            return result

        sim_log_path = os.path.join(work_dir, 'sim_output.log')
        with open(sim_log_path, 'w') as lf:
            subprocess.run([sim_bin], stdout=lf, stderr=subprocess.STDOUT,
                           timeout=sim_timeout, cwd=work_dir, env=_VLT_ENV)

        LOG_CAP = 256 * 1024
        log_size = os.path.getsize(sim_log_path)
        with open(sim_log_path, errors='replace') as lf:
            if log_size > LOG_CAP:
                lf.seek(log_size - LOG_CAP)
                sim_output = "...[truncated]...\n" + lf.read()
            else:
                sim_output = lf.read()
        result['sim_log'] = sim_output

        if "[PASS]" in sim_output:
            result['status'] = 'pass'; result['pass'] = True
        elif "TIMEOUT" in sim_output:
            result['status'] = 'sim_timeout'; result['timeout'] = True
        elif "[FAIL]" in sim_output:
            result['status'] = 'fail'
            for line in sim_output.split('\n'):
                if '[FAIL]' in line or '[ERROR]' in line:
                    result['error_msg'] += line.strip() + '; '
        else:
            result['status'] = 'unknown'; result['error_msg'] = sim_output[-500:]

        for pat, key in [('perf_total', 'cycles'), ('perf_stall', 'perf_stall'),
                         ('perf_retired', 'perf_retired')]:
            vals = re.findall(rf'{pat}=(\d+)', sim_output)
            if vals:
                result[key] = max(int(x) for x in vals) if key == 'cycles' else sum(int(x) for x in vals)

    except subprocess.TimeoutExpired:
        result['status'] = 'process_timeout'; result['timeout'] = True
        result['error_msg'] = f"Timed out after {sim_timeout}s"
    except Exception as e:
        result['error_msg'] = str(e)[:200]
    finally:
        result['sim_time_s'] = round(time.time() - t_sim, 2)
        try: shutil.rmtree(work_dir)
        except: pass

    return result


def _load_hw_only_state(instances, sim_timeout):
    """Rebuild Step-1+2 state (leaders/followers/vivado_queue) from disk.

    Used by --hw-only: skip SW eval entirely and run Step 3 against the
    testbench files already written by a previous --skip-hw or --mode phase1 run.

    Returns (inst_results, leader_map, follower_map, vivado_queue, issues,
    n_total_valid). `issues` is a list of (ilabel, ErrorCode, detail) for
    missing artifacts; bail to the caller for display.
    """
    inst_map = {il: (n, g, tn) for n, g, tn, il in instances}
    inst_results = defaultdict(list)
    leader_map = {}                  # (ilabel, tb_hash) -> row
    follower_map = defaultdict(list) # (ilabel, tb_hash) -> [row, ...]
    vivado_queue = []
    issues = []                      # [(ilabel, ErrorCode, detail), ...]
    n_total_valid = 0

    int_fields = ('makespan', 'makespan_sched', 'cp_comm', 'max_load',
                  'edge_cut', 'max_imem', 'n_gpus_used', 'omega')
    float_fields = ('ratio_to_omega', 'load_imbalance', 'time_s')
    bool_fields = ('valid', 'connected', 'imem_ok')

    def _coerce(r):
        for k in int_fields:
            try: r[k] = int(r.get(k, -1))
            except (TypeError, ValueError): r[k] = -1
        for k in float_fields:
            try: r[k] = float(r.get(k, 0))
            except (TypeError, ValueError): r[k] = -1.0
        for k in bool_fields:
            r[k] = str(r.get(k, '')).strip().lower() == 'true'
        return r

    for ilabel, (n, g, tname) in inst_map.items():
        idir = _inst_dir(ilabel)
        csv_path = os.path.join(idir, 'sw_results.csv')
        if not os.path.exists(csv_path):
            issues.append((ilabel, ErrorCode.SW_CSV_MISSING, csv_path))
            continue

        with open(csv_path) as f:
            rows = [_coerce(dict(r)) for r in csv.DictReader(f)]
        inst_results[ilabel] = rows

        topo = build_topology(tname, g)
        tree = CBTree(n)
        n_leaves, n_nodes = tree.n_leaves, topo.n_nodes

        # First pass: install leaders (rows flagged unique_hw_sim=True).
        for r in rows:
            h = r.get('tb_hash', '') or ''
            if not h:
                continue
            is_leader = (str(r.get('unique_hw_sim', '')).strip().lower() == 'true')
            key = (ilabel, h)
            if is_leader and key not in leader_map:
                tb_fname = r.get('tb_fname') or \
                    f"tb_{_safe_name(r['s2'])}_{_safe_name(r['s3'])}_none"
                tb_path = os.path.join(idir, f"{tb_fname}.sv")
                if not os.path.exists(tb_path):
                    issues.append((ilabel, ErrorCode.TB_MISSING, tb_path))
                    r['error_code'] = ErrorCode.TB_MISSING
                    continue
                r['tb_fname'] = tb_fname
                r['unique_hw_sim'] = True
                leader_map[key] = r
                vivado_queue.append((ilabel, tb_fname, tb_path,
                                     n_leaves, n_nodes, sim_timeout))

        # Second pass: attach followers to whichever leader claimed the hash.
        for r in rows:
            h = r.get('tb_hash', '') or ''
            if not h:
                continue
            n_total_valid += 1
            key = (ilabel, h)
            if key in leader_map and leader_map[key] is not r:
                r['unique_hw_sim'] = False
                follower_map[key].append(r)

    return inst_results, leader_map, follower_map, vivado_queue, issues, n_total_valid


def run_phase1_unified(instances, bounds, nw, hw_workers, sim_timeout,
                       n_tiers=3, max_per=15, resume=False, skip_hw=False,
                       hw_only=False, ram_per_worker=DEFAULT_HW_RAM_GB,
                       max_retries=DEFAULT_MAX_HW_RETRIES):
    """Single-pass Phase 1: SW eval + TB gen → dedup → HW sim → winners.

    With hw_only=True: skip Step 1+2 entirely, load existing TBs and dedup
    state from disk, then run Step 3. Compose with resume=True to also skip
    sims already recorded in live_hw_results_p1_unified.csv.

    Returns (final_winners, hw_results, unique_pairs).
    final_winners is HW-ranked when HW runs, SW-ranked when --skip-hw.
    """
    inst_map = {il: (n, g, tn) for n, g, tn, il in instances}
    pipelines = [(s2, s3) for s2 in STAGE2_METHODS for s3 in STAGE3_METHODS]
    n_inst = len(instances)

    if hw_only:
        if skip_hw:
            log('WARN', '--skip-hw + --hw-only is a no-op; ignoring --skip-hw')
            skip_hw = False
        log('INFO', 'PHASE 1 (HW-only): rebuilding dedup state from disk')
        inst_results, leader_map, follower_map, vivado_queue, issues, n_total_valid = \
            _load_hw_only_state(instances, sim_timeout)
        for ilabel, code, detail in issues:
            log('ERROR', f"{ilabel}  {code}  {detail}")
        n_unique = len(vivado_queue)
        if not vivado_queue:
            log('ERROR', "Nothing to simulate — re-run SW phase to regenerate "
                          "testbenches.")
            return {}, {}, set()
        log('OK', f"Reconstructed: {len(inst_results)} instances, "
                  f"{n_unique} unique TBs, {n_total_valid} valid SW rows")
    else:
        # ── State init (populated incrementally + from disk on resume) ──
        inst_results = defaultdict(list)        # ilabel -> [row, ...]
        inst_pipeline_count = defaultdict(int)  # ilabel -> rows received
        total_per_inst = len(pipelines)
        leader_map = {}                         # (ilabel, tb_hash) -> row
        follower_map = defaultdict(list)        # (ilabel, tb_hash) -> [row, ...]
        vivado_queue = []
        n_total_valid = 0
        n_ok = 0

        # ── SW-resume: load fully-completed instances from disk ──
        resumed_labels = set()
        if resume:
            resume_instances = []
            for n, g, tname, ilabel in instances:
                csv_path = os.path.join(_inst_dir(ilabel), 'sw_results.csv')
                if not os.path.exists(csv_path):
                    continue
                # Verify completeness — only resume if all 180 rows are present
                try:
                    with open(csv_path) as f:
                        n_rows = sum(1 for _ in csv.DictReader(f))
                    if n_rows == total_per_inst:
                        resume_instances.append((n, g, tname, ilabel))
                except Exception as e:
                    log('WARN', f"resume {ilabel}: could not read {csv_path}: {e}")
            if resume_instances:
                pre_results, pre_leaders, pre_followers, pre_queue, pre_issues, pre_valid = \
                    _load_hw_only_state(resume_instances, sim_timeout)
                for ilabel, rows in pre_results.items():
                    inst_results[ilabel] = rows
                    inst_pipeline_count[ilabel] = total_per_inst
                    resumed_labels.add(ilabel)
                    n_ok += sum(1 for r in rows if r.get('valid'))
                leader_map.update(pre_leaders)
                for k, v in pre_followers.items():
                    follower_map[k].extend(v)
                vivado_queue.extend(pre_queue)
                n_total_valid += pre_valid
                for ilabel, code, detail in pre_issues:
                    log('WARN', f"resume {ilabel}  {code}  {detail}")
                log('INFO', f"PHASE 1 SW-resume: loaded {len(resumed_labels)} "
                            f"instance(s) from disk ({pre_valid} rows, "
                            f"{len(pre_queue)} unique TBs)")

        # ── Build work items (skip resumed instances) ──
        work_items = []
        n_scratch_swept = 0
        for n, g, tname, ilabel in instances:
            idir = _inst_dir(ilabel)
            os.makedirs(idir, exist_ok=True)
            # Sweep orphaned scratch TBs from prior crashed runs.
            for stale in glob.glob(os.path.join(idir, '_tb_scratch_*.sv')):
                try:
                    os.unlink(stale); n_scratch_swept += 1
                except OSError:
                    pass
            if ilabel in resumed_labels:
                continue
            for s2, s3 in pipelines:
                work_items.append((s2, s3, n, g, tname, ilabel))
        if n_scratch_swept:
            log('INFO', f"Cleaned {n_scratch_swept} orphan scratch TB(s) from prior runs")

        nr = len(work_items)
        if nr == 0:
            print(f"  All {n_inst} instances already complete — skipping SW pass")
        else:
            print(f"  {nr} items ({n_inst - len(resumed_labels)} instances "
                  f"to run, {len(resumed_labels)} resumed) on {nw} workers")

            # ── SW+TB pass ──
            print(f'\n  Step 1: SW eval + TB gen + per-instance dedup (streaming)')
            ts = time.time(); dc = 0

            pool = multiprocessing.Pool(processes=nw, initializer=_worker_init,
                                        initargs=(instances, bounds))
            try:
                for row in pool.imap_unordered(_unified_p1_worker, work_items, chunksize=4):
                    dc += 1
                    ilabel = row.pop('_ilabel', '')
                    inst_results[ilabel].append(row)
                    inst_pipeline_count[ilabel] += 1
                    if row.get('valid'):
                        n_ok += 1

                    # ── Per-instance trigger: dedup + emit .sv when all pipelines arrive ──
                    if inst_pipeline_count[ilabel] == total_per_inst:
                        n, g, tname = inst_map[ilabel]
                        topo = build_topology(tname, g)
                        tree = CBTree(n)
                        n_leaves, n_nodes = tree.n_leaves, topo.n_nodes
                        idir = _inst_dir(ilabel)
                        n_valid_this = n_unique_this = 0
                        for r in inst_results[ilabel]:
                            h = r.get('tb_hash', '')
                            scratch = r.pop('tb_path', '') or ''
                            if not h:
                                # invalid pipeline — clean up any scratch left behind
                                if scratch and os.path.exists(scratch):
                                    try: os.unlink(scratch)
                                    except OSError: pass
                                continue
                            n_valid_this += 1
                            key = (ilabel, h)
                            if key not in leader_map:
                                r['unique_hw_sim'] = True
                                leader_map[key] = r
                                s2_safe = _safe_name(r['s2'])
                                s3_safe = _safe_name(r['s3'])
                                tb_fname = f"tb_{s2_safe}_{s3_safe}_none"
                                r['tb_fname'] = tb_fname
                                tb_path = os.path.join(idir, f"{tb_fname}.sv")
                                # Atomic rename — no SV string read into main.
                                if scratch and os.path.exists(scratch):
                                    os.replace(scratch, tb_path)
                                vivado_queue.append((ilabel, tb_fname, tb_path,
                                                     n_leaves, n_nodes, sim_timeout))
                                n_unique_this += 1
                            else:
                                r['unique_hw_sim'] = False
                                if scratch and os.path.exists(scratch):
                                    try: os.unlink(scratch)
                                    except OSError: pass
                                follower_map[key].append(r)
                        n_total_valid += n_valid_this
                        if n_valid_this > 0:
                            dpct = (n_valid_this - n_unique_this) * 100.0 / n_valid_this
                            print(f"    [dedup {ilabel}] {n_unique_this}/{n_valid_this} "
                                  f"unique ({dpct:.1f}% dedup)", flush=True)

                        # ── Persist this instance's CSV immediately (crash-safe) ──
                        csv_path = os.path.join(idir, 'sw_results.csv')
                        inst_results[ilabel].sort(
                            key=lambda r: (r.get('makespan', 1e9)
                                           if r.get('valid') else 1e9))
                        with open(csv_path, 'w', newline='') as f:
                            w = csv.DictWriter(f, fieldnames=SW_COLUMNS,
                                               extrasaction='ignore')
                            w.writeheader()
                            for row_w in inst_results[ilabel]:
                                w.writerow(row_w)

                    step = max(1, nr // 40)
                    if dc % step == 0 or dc == nr:
                        elapsed = time.time() - ts
                        rate = dc / max(elapsed, 0.01)
                        eta = (nr - dc) / max(rate, 0.001)
                        done_inst = sum(1 for il, rs in inst_results.items()
                                        if len(rs) >= total_per_inst)
                        print(f"    [{dc:>6}/{nr}] {dc*100/nr:5.1f}%  "
                              f"{rate:.1f}/s  ETA={_fmt_time(eta)}  "
                              f"inst={done_inst}/{n_inst}  ok={n_ok}",
                              flush=True)
                pool.close(); pool.join()
            except BaseException:
                pool.terminate(); pool.join(); raise

            print(f"\n  Step 1 done in {_fmt_time(time.time() - ts)}")

        n_unique = len(vivado_queue)
        print(f"  Valid: {n_ok}  |  Instances: {len(inst_results)}", flush=True)
        if n_total_valid > 0:
            print(f"  Unique TBs: {n_unique} / {n_total_valid} "
                  f"({(n_total_valid - n_unique)*100.0/n_total_valid:.1f}% dedup)")

    # ── HW simulation ──
    hw_results_map = defaultdict(list)  # ilabel -> [row, ...]

    if skip_hw or n_unique == 0:
        if skip_hw:
            print('\n  Step 3: SKIPPED (--skip-hw)')
        # Collect all valid rows without HW data
        for ilabel, rows in inst_results.items():
            for row in rows:
                row.setdefault('hw_pass', False)
                row.setdefault('hw_cycles', -1)
                hw_results_map[ilabel].append(row)
    else:
        # Memory-based worker cap (verilator is lighter — halve the budget).
        eff_ram = ram_per_worker * 0.5 if HW_BACKEND == 'verilator' else ram_per_worker
        hw_workers, _ = _compute_safe_hw_workers(hw_workers, eff_ram)

        # Disk-space guard
        try:
            free_disk_gb = shutil.disk_usage(RESULTS_DIR).free / (1024**3)
            if free_disk_gb < 5:
                print(f"  WARNING: only {free_disk_gb:.1f} GB free on results disk")
        except Exception:
            pass

        # Resume: skip sims already in live log (pass OR fail — delete the row
        # from live_hw_results_*.csv if you want to retry a specific failure).
        phase_tag = 'p1_unified'
        if resume:
            done = _load_phase3_done(phase_tag)
            if done:
                remaining = []; n_reused = 0; n_reused_fail = 0
                for item in vivado_queue:
                    il, tb_fn, *_ = item
                    cached = done.get((il, tb_fn))
                    if cached is None:
                        remaining.append(item); continue
                    try: cycles = int(cached.get('Cycles', -1))
                    except (TypeError, ValueError): cycles = -1
                    passed = str(cached.get('Pass', '')).strip().lower() in ('true', '1', 'pass')
                    try: sim_t = float(cached.get('SimTime_s', 0) or 0)
                    except (TypeError, ValueError): sim_t = 0.0
                    cached_ec = (cached.get('ErrorCode') or '').strip() or (
                        ErrorCode.OK if passed else ErrorCode.HW_OTHER)
                    lk = None
                    for (ki, kh), lr in leader_map.items():
                        if ki == il and lr.get('tb_fname') == tb_fn:
                            lk = (ki, kh); break
                    if lk is None:
                        remaining.append(item); continue
                    for dest in [leader_map[lk]] + follower_map[lk]:
                        dest['hw_pass'] = passed; dest['hw_cycles'] = cycles
                        dest['sim_time_s'] = sim_t; dest['hw_timeout'] = False
                        dest['hw_error_code'] = cached_ec
                    n_reused += 1
                    if not passed:
                        n_reused_fail += 1
                if n_reused:
                    log('INFO', f"Resume: reused {n_reused} cached sims "
                                f"({n_reused_fail} failures, {len(remaining)} remaining)")
                    if n_reused_fail:
                        log('INFO', "    delete failed rows from "
                                    f"live_hw_results_{phase_tag}.csv to retry them")
                vivado_queue = remaining
                n_unique = len(vivado_queue)

        if n_unique > 0:
            backend = HW_BACKEND
            sim_worker = _verilator_sim_worker if backend == 'verilator' else _vivado_only_worker
            print(f'\n  Step 3: HW simulation ({backend}, {n_unique} unique TBs, '
                  f'{hw_workers} workers; retry={max_retries})')

            ts_hw = time.time(); n_pass_box = [0]

            def _commit(sim, attempts_used):
                il = sim.get('ilabel', ''); tb_fn = sim.get('tb_fname', '')
                lk = None
                for (ki, kh), lr in leader_map.items():
                    if ki == il and lr.get('tb_fname') == tb_fn:
                        lk = (ki, kh); break
                if not lk:
                    return
                leader = leader_map[lk]
                ec = sim.get('error_code',
                             ErrorCode.OK if sim.get('pass') else ErrorCode.HW_OTHER)
                for dest in [leader] + follower_map[lk]:
                    dest['hw_pass'] = sim.get('pass', False)
                    dest['hw_cycles'] = sim.get('cycles', -1)
                    dest['perf_stall'] = sim.get('perf_stall', -1)
                    dest['perf_retired'] = sim.get('perf_retired', -1)
                    dest['hw_timeout'] = sim.get('timeout', False)
                    dest['sim_time_s'] = sim.get('sim_time_s', 0.0)
                    dest['hw_error_code'] = ec
                    if not sim.get('pass') and sim.get('error_msg'):
                        dest['hw_error'] = sim['error_msg'][:200]

                if not sim.get('pass'):
                    idir = _inst_dir(il)
                    log_path = os.path.join(idir, f"sim_{tb_fn.replace('tb_', '')}.log")
                    with open(log_path, 'w') as f:
                        f.write(sim.get('sim_log', '')); f.flush()
                    retry_tag = f" (retries={attempts_used})" if attempts_used else ""
                    log('ERROR', f"{il}  {leader['s2']}|{leader['s3']}  "
                                 f"{ec}{retry_tag}  → {log_path}")

                live_log_path = os.path.join(
                    RESULTS_DIR, f"live_hw_results_{phase_tag}.csv")
                try:
                    is_new = not os.path.exists(live_log_path)
                    with open(live_log_path, 'a') as f:
                        if is_new:
                            f.write("Instance,Pipeline,TB_Name,Pass,Cycles,SimTime_s,ErrorCode,Error\n")
                        f.write(f"{il},{leader['s2']}|{leader['s3']},{tb_fn},"
                                f"{sim.get('pass', False)},{sim.get('cycles',-1)},"
                                f"{sim.get('sim_time_s',0.0)},{ec},"
                                f"{sim.get('error_msg','')[:50].replace(',', ';')}\n")
                except Exception:
                    pass

                if sim.get('pass'):
                    n_pass_box[0] += 1

            def _progress(done, total):
                step = max(1, total // 20)
                if done % step == 0 or done == total:
                    elapsed = time.time() - ts_hw
                    rate = done / max(elapsed, 0.01)
                    eta = (total - done) / max(rate, 0.001)
                    print(f"    [{done:>6}/{total}] {done*100/total:5.1f}%  "
                          f"ETA={_fmt_time(eta)}  pass={n_pass_box[0]}", flush=True)

            _adaptive_hw_dispatch(vivado_queue, sim_worker, hw_workers,
                                  eff_ram, max_retries, _commit, _progress)

            print(f"\n  Step 3 done in {_fmt_time(time.time() - ts_hw)}")

        # Collect all results with HW data propagated
        for ilabel, rows in inst_results.items():
            for row in rows:
                row.setdefault('hw_pass', False)
                row.setdefault('hw_cycles', -1)
                row.setdefault('sim_time_s', 0.0)
                row.setdefault('hw_error_code', '')
                hw_results_map[ilabel].append(row)

    # ── Write unified results CSV ──
    for ilabel in inst_results:
        idir = _inst_dir(ilabel)
        csv_path = os.path.join(idir, 'unified_results.csv')
        rows = sorted(hw_results_map.get(ilabel, []),
                       key=lambda r: (not r.get('hw_pass', False),
                                      int(r.get('hw_cycles', 10**9)),
                                      r.get('makespan', 1e9) if r.get('valid') else 1e9))
        with open(csv_path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=UNIFIED_COLUMNS, extrasaction='ignore')
            w.writeheader()
            for row in rows:
                w.writerow(row)

    # Also write hw_results.csv (compatible with existing report generation)
    if not skip_hw:
        write_phase_hw_csv(instances, dict(hw_results_map), 'hw_results.csv')

    # ── Select winners ──
    print(f'\n  Selecting winners (tiers={n_tiers}, max={max_per})')

    sw_winners, sw_unique = select_winners(instances, 'sw_results.csv',
                                           n_tiers=n_tiers, max_per=max_per)
    total_sw = sum(len(w) for w in sw_winners.values())
    print(f"  SW winners: {total_sw} across {len(sw_winners)} instances")
    print(f"  Unique (S2,S3) pairs: {len(sw_unique)}")
    write_phase_hw_winners_csv(instances, sw_winners, 'p1_sw_winners.csv')

    if skip_hw:
        return sw_winners, {}, sw_unique

    hw_winners, hw_unique = select_winners_by_hw(instances, dict(hw_results_map),
                                                  n_tiers=n_tiers, max_per=max_per)
    total_hw = sum(len(w) for w in hw_winners.values())
    print(f"  HW winners: {total_hw} across {len(hw_winners)} instances")
    write_phase_hw_winners_csv(instances, hw_winners, 'p1_hw_winners.csv')

    # Write full report (SW+HW joined)
    write_p1_full_report(instances)

    return hw_winners, dict(hw_results_map), hw_unique


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    # Unbuffered stdout/stderr so progress streams live when piped to a log
    # file (python -u equivalent; harmless if already a TTY).
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass
    parser = argparse.ArgumentParser(description='SPRS Tournament v8.0')
    parser.add_argument('--mode', choices=['phase1', 'phase2'], required=True,
                        help='Choose tournament mode (both feature HW sim)')
    parser.add_argument('--workers', type=int, default=DEFAULT_SW_WORKERS,
                        help=f'SW workers (default: {DEFAULT_SW_WORKERS})')
    parser.add_argument('--hw-workers', type=int, default=DEFAULT_HW_WORKERS,
                        help=f'HW sim workers (default: {DEFAULT_HW_WORKERS})')
    parser.add_argument('--resume', action='store_true',
                        help='Skip pipelines / sims already recorded on disk')
    parser.add_argument('--skip-hw', action='store_true',
                        help='Skip Phase 3 (Vivado HW Sim); TBs still emitted')
    parser.add_argument('--hw-only', action='store_true',
                        help='Skip SW eval; load TBs + dedup state from disk '
                             'and run only Vivado. Compose with --resume to '
                             'also skip sims already in live_hw_results_*.csv')
    parser.add_argument('--n-tiers', type=int, default=3)
    parser.add_argument('--max-per-instance', type=int, default=15)
    parser.add_argument('--sim-timeout', type=int, default=SIM_TIMEOUT)
    parser.add_argument('--hw-ram-gb', type=float, default=DEFAULT_HW_RAM_GB,
                        help=f'RAM budget per HW worker in GB '
                             f'(default: {DEFAULT_HW_RAM_GB}; lower = more '
                             f'workers, higher OOM risk)')
    parser.add_argument('--max-hw-retries', type=int,
                        default=DEFAULT_MAX_HW_RETRIES,
                        help=f'Per-TB retry count on transient HW failures '
                             f'(default: {DEFAULT_MAX_HW_RETRIES})')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--smoke-instance', type=str, default='small_dense_hc')
    args = parser.parse_args()

    nw = args.workers
    instances = list(TEST_INSTANCES)
    n_inst = len(instances)

    if args.smoke:
        smoke = None
        for inst in instances:
            if inst[3] == args.smoke_instance:
                smoke = inst; break
        if not smoke:
            print(f"ERROR: '{args.smoke_instance}' not found")
            return
        instances = [smoke]; n_inst = 1

    p1_pipes = [(s2, s3) for s2 in STAGE2_METHODS for s3 in STAGE3_METHODS]
    s4_cfgs = enumerate_s4_configs()

    mode_label = args.mode.upper()
    if args.hw_only:
        mode_label += ' (HW-ONLY)'
    elif args.skip_hw:
        mode_label += ' (SW-ONLY)'
    if args.resume:
        mode_label += ' [resume]'
    banner(f'SPRS Tournament v8.0 — Mode: {mode_label}', char='=')
    print(f'  Instances:   {n_inst}')

    if args.mode == 'phase1':
        if args.hw_only:
            print(f'  Phase 1:     HW-only (reloading {n_inst} inst from disk)')
        else:
            print(f'  Phase 1:     {len(p1_pipes)} S2xS3 x {n_inst} inst = '
                  f'{len(p1_pipes)*n_inst} items')
    elif args.mode == 'phase2':
        if args.hw_only:
            print(f'  Phase 1:     HW-only (skipped — reading p1/p2 caches)')
            print(f'  Phase 2:     HW-only (reloading winners from s4_results.csv)')
        else:
            print(f'  Phase 1:     (Required for pre-computation) {len(p1_pipes)*n_inst} items')
            print(f'  Phase 2:     P1 winners x {len(s4_cfgs)} S4 configs x {n_inst} inst')

    if args.skip_hw:
        print(f'  HW Sim:      SKIPPED (--skip-hw)')
    else:
        print(f'  HW Backend:  {HW_BACKEND} (workers: {args.hw_workers}, '
              f'~{args.hw_ram_gb:g} GB/worker, retry={args.max_hw_retries})')

    print(f'  Eval timeout: {EVAL_TIMEOUT}s  |  Sim timeout: {args.sim_timeout}s')
    print(f'  Winner tiers: {args.n_tiers} (Max {args.max_per_instance})  |  ALU: FADD')
    print(f'  Output:      {RESULTS_DIR}/')
    print()

    if args.dry_run:
        log('INFO', 'DRY RUN — exiting without doing anything.')
        return

    # Precompute (cheap; needed by both SW worker init and HW-only state load)
    print('  Precomputing...')
    t0 = time.time()
    precompute_all_instances(instances)
    print(f'  Done in {time.time()-t0:.1f}s')
    bounds = compute_and_save_bounds(instances)
    print(f'  Lower bounds: {len(bounds)} instances\n')

    if args.mode == 'phase1':
        # ── UNIFIED PHASE 1: SW + TB gen → dedup → HW sim ──
        print('-' * 80)
        print('  PHASE 1: Unified SW eval + TB gen + HW sim (single pass)')
        print('-' * 80)

        final_winners, p1_hw_results, p1_unique = run_phase1_unified(
            instances, bounds, nw, args.hw_workers, args.sim_timeout,
            n_tiers=args.n_tiers, max_per=args.max_per_instance,
            resume=args.resume, skip_hw=args.skip_hw,
            hw_only=args.hw_only,
            ram_per_worker=args.hw_ram_gb,
            max_retries=args.max_hw_retries)

        # ── REPORTS ──
        print('\n' + '-' * 80)
        print('  GENERATING REPORTS')
        print('-' * 80)
        generate_reports(instances, final_winners, p1_hw_results, bounds,
                         mode='phase1')
        _print_summary(instances, bounds, final_winners, p1_hw_results)
        _print_error_summary(p1_hw_results)

    elif args.mode == 'phase2':
        # Phase 2 = (Phase 1 SW → select → Phase 2 SW → HW) two-pass flow.
        # --hw-only short-circuits both SW passes and drives run_phase3 from
        # cached s4_results.csv files.

        p2_hw_results = None

        if args.hw_only:
            if args.skip_hw:
                log('WARN', '--skip-hw + --hw-only is a no-op; ignoring --skip-hw')
                args.skip_hw = False
            banner('PHASE 2 (HW-only): reloading winners from disk', char='-')
            p2_all = load_all_valid_pipelines(
                instances, 's4_results.csv', include_s4=True)
            missing = [il for _, _, _, il in instances if il not in p2_all]
            for il in missing:
                csv_path = os.path.join(_inst_dir(il), 's4_results.csv')
                log('ERROR', f"{il}  {ErrorCode.SW_CSV_MISSING}  {csv_path}")
            if not p2_all:
                log('ERROR', "Nothing to simulate — run phase2 SW first "
                              "(or run without --hw-only).")
                return
            n_p2_total = sum(len(v) for v in p2_all.values())
            log('OK', f"Reconstructed: {len(p2_all)} instances, "
                      f"{n_p2_total} valid SW rows")

            banner(f'PHASE 2 HW sim (dedup by TB hash) — phase_tag=p2', char='-')
            log('INFO', f'Candidates: {n_p2_total} (will dedup via TB hash)')
            p2_hw_results = run_phase3(
                instances, p2_all, args.hw_workers, args.sim_timeout,
                phase_tag='p2', resume=args.resume,
                ram_per_worker=args.hw_ram_gb,
                max_retries=args.max_hw_retries)
            write_phase_hw_csv(instances, p2_hw_results, 'hw_results.csv')

            banner(f'PHASE 2 WINNERS (by HW cycles, tiers={args.n_tiers})',
                   char='-')
            p2_winners, _ = select_winners_by_hw(
                instances, p2_hw_results,
                n_tiers=args.n_tiers, max_per=args.max_per_instance)
            write_phase_hw_winners_csv(instances, p2_winners, 'p2_hw_winners.csv')
            if not any(p2_winners.values()):
                log('WARN', 'No HW-passing P2 pipelines — falling back to SW')
                p2_winners, _ = select_winners(
                    instances, 's4_results.csv',
                    n_tiers=args.n_tiers, max_per=args.max_per_instance)
        else:
            # ── Phase 1 prerequisite ──
            banner('PHASE 1: SW eval (prerequisite for Phase 2)', char='-')
            run_phase1(instances, bounds, nw, resume=args.resume)

            p1_winners, p1_unique = select_winners(
                instances, 'sw_results.csv',
                n_tiers=args.n_tiers, max_per=args.max_per_instance)

            if not args.skip_hw:
                banner('Loading HW-proven base pipelines from phase 1',
                       char='-')
                hw_unique_pairs = set()
                found = 0
                for _, _, _, ilabel in instances:
                    path = os.path.join(_inst_dir(ilabel), 'p1_hw_winners.csv')
                    if os.path.exists(path):
                        with open(path) as f:
                            for row in csv.DictReader(f):
                                hw_unique_pairs.add((row['s2'], row['s3']))
                                found += 1
                if not hw_unique_pairs:
                    log('ERROR', 'No p1_hw_winners.csv — run --mode phase1 first.')
                    sys.exit(1)
                log('OK', f"Loaded {found} entries → "
                          f"{len(hw_unique_pairs)} unique base pipelines.")
                p1_unique = hw_unique_pairs

            # ── Phase 2: S4 Refinement ──
            banner('PHASE 2: Greedy S4 Refinement (Software)', char='-')
            run_phase2(p1_unique, instances, bounds, nw, resume=args.resume)

            if not args.skip_hw:
                banner('PHASE 2 HW sim (dedup by TB hash)', char='-')
                p2_all = load_all_valid_pipelines(
                    instances, 's4_results.csv', include_s4=True)
                n_p2_total = sum(len(v) for v in p2_all.values())
                log('INFO', f'Candidates: {n_p2_total} (will dedup via TB hash)')
                p2_hw_results = run_phase3(
                    instances, p2_all, args.hw_workers, args.sim_timeout,
                    phase_tag='p2', resume=args.resume,
                    ram_per_worker=args.hw_ram_gb,
                    max_retries=args.max_hw_retries)
                write_phase_hw_csv(instances, p2_hw_results, 'hw_results.csv')

                banner(f'PHASE 2 WINNERS (by HW cycles, tiers={args.n_tiers})',
                       char='-')
                p2_winners, _ = select_winners_by_hw(
                    instances, p2_hw_results,
                    n_tiers=args.n_tiers, max_per=args.max_per_instance)
                write_phase_hw_winners_csv(instances, p2_winners, 'p2_hw_winners.csv')
                if not any(p2_winners.values()):
                    log('WARN', 'No HW-passing P2 pipelines — falling back to SW')
                    p2_winners, _ = select_winners(
                        instances, 's4_results.csv',
                        n_tiers=args.n_tiers, max_per=args.max_per_instance)
            else:
                p2_winners, _ = select_winners(
                    instances, 's4_results.csv',
                    n_tiers=args.n_tiers, max_per=args.max_per_instance)

        total_p2w = sum(len(w) for w in p2_winners.values())
        log('INFO', f'Total P2 winners: {total_p2w} across '
                    f'{len(p2_winners)} instances')
        final_winners = p2_winners

        hw_results = p2_hw_results if p2_hw_results else {}

        # ── REPORTS ──
        banner('GENERATING REPORTS', char='-')
        generate_reports(instances, final_winners, hw_results, bounds,
                         mode='phase2')
        _print_summary(instances, bounds, final_winners, hw_results)
        _print_error_summary(hw_results)


if __name__ == '__main__':
    main()
