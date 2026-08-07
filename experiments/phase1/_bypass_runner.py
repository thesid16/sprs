#!/usr/bin/env python3
"""Run the force-bypass version of TBs through Vivado and write to unified CSV
with ErrorCode='OK_BYPASS' / 'FAIL_BYPASS' / etc. to distinguish from original
protocol rows.

Reads each original TB from results/<inst>/<tb>.sv, rewrites write_route() calls
to direct hierarchical assignments (with plain integer literal for correct bit width),
writes to a per-worker work_dir, runs xvlog+xelab+xsim, parses output, records row.

Output: appends to live_hw_results_p1_unified.csv with bypass marker in ErrorCode.
"""
import os, re, csv, sys, time, json, shutil, subprocess, argparse, threading, signal
from concurrent.futures import ProcessPoolExecutor, as_completed

BASE = "/home/rohit/tournament_p1"   # current baked TBs live here (was tournament_new = stale 2026-05 TBs)
RTL  = f"{BASE}/rtl"
RES  = f"{BASE}/results"
VIVADO_BIN = "/home/rohit/Downloads/2025.2/Vivado/bin"
RTL_FILES = ["noc_pkg.sv","btree_pkg.sv","sync_fifo.sv","link_tx.sv",
             "noc_link.sv","noc_router.sv","noc_ni.sv","fp64_add.sv",
             "btree_fsm_fast.sv","noc_system.sv"]
UNIFIED_COLS = ["Instance","Pipeline","TB_Name","Pass","Cycles",
                "SimTime_s","ErrorCode","Error",
                # appended 2026-07-27; ErrorCode stays at index 6 so the
                # resume scan below is unaffected by the schema change.
                "CyclesGPU0","PerfAllGPUs"]
TB_RE      = re.compile(r"^tb_(\d+[a-z])_(\d+[a-z])_(\w+)$")
WRITE_ROUTE_RE = re.compile(r"^(\s*)write_route\((\d+),(\d+),(\d+)\);\s*$", re.MULTILINE)

def parse_pipeline(tb_name):
    m = TB_RE.match(tb_name)
    if not m: return ""
    s2, s3, s4 = m.group(1), m.group(2), m.group(3)
    return f"{s2}|{s3}" if s4 == "none" else f"{s2}|{s3}|{s4}"

def rewrite_bypass(text):
    def sub(m):
        i,r,d,p = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"{i}u_sys.gen_rtr[{r}].u_rtr.route_table[{d}] = {p};"
    return WRITE_ROUTE_RE.subn(sub, text)

def run_one(args):
    ilabel, tb_fname, n_leaves, n_nodes, sim_timeout = args
    idir = f"{RES}/{ilabel}"
    src_tb = f"{idir}/{tb_fname}.sv"
    module_name = f"tb_sprs_{n_leaves}L_{n_nodes}G"
    wd = f"{idir}/work_bypass_{tb_fname}_{int(time.time()*1000)%100000}_{os.getpid()}"
    if os.path.exists(wd): shutil.rmtree(wd, ignore_errors=True)
    os.makedirs(wd, exist_ok=True)

    # Rewrite TB with bypass (retry read: FileNotFoundError under heavy IO is transient)
    src_text = None
    for _attempt in range(5):
        try:
            src_text = open(src_tb).read(); break
        except FileNotFoundError:
            time.sleep(0.3)  # transient under heavy IO (open OR exists() can flake); always retry
    if src_text is None:
        return {"Instance":ilabel,"Pipeline":parse_pipeline(tb_fname),"TB_Name":tb_fname,
                "Pass":False,"Cycles":-1,"SimTime_s":0.0,"ErrorCode":"TB_MISSING","Error":""}
    # Use the ACTUAL top module from the TB (node count != ng for mesh/torus/hc/2d)
    _mm = re.search(r'module\s+(tb_sprs_\w+)', src_text)
    if _mm: module_name = _mm.group(1)
    new_text, n_subs = rewrite_bypass(src_text)
    dst_tb = f"{wd}/{tb_fname}.sv"
    open(dst_tb,"w").write(new_text)

    xvlog = f"{VIVADO_BIN}/xvlog"
    xelab = f"{VIVADO_BIN}/xelab"
    xsim  = f"{VIVADO_BIN}/xsim"
    src_files = [f"{RTL}/{f}" for f in RTL_FILES] + [dst_tb]

    row = {"Instance":ilabel,"Pipeline":parse_pipeline(tb_fname),"TB_Name":tb_fname,
           "Pass":False,"Cycles":-1,"SimTime_s":0.0,"ErrorCode":"","Error":""}
    t0 = time.time()

    def _tail(p, n=500):
        try:
            return open(p, errors="replace").read()[-n:]
        except: return ""

    try:
        # xvlog
        xvlog_log = f"{wd}/xvlog.log"
        with open(xvlog_log,"w") as lf:
            p = subprocess.run([xvlog,"-sv"]+src_files, stdout=lf, stderr=subprocess.STDOUT,
                               cwd=wd, timeout=1800)
        if p.returncode != 0:
            row["ErrorCode"] = "XVLOG_FAIL_BYPASS"
            row["Error"] = _tail(xvlog_log)
            return row
        # xelab (wrap so we can kill grandchildren on timeout)
        snap = f"sim_byp_{tb_fname}"
        xelab_log = f"{wd}/xelab.log"
        with open(xelab_log,"w") as lf:
            # -mt is the elaboration thread count. Default 2 preserves the
            # behaviour every prior campaign ran under; XELAB_MT raises it for
            # the giant instances, where elaboration (not simulation) dominates
            # and the box has far more threads than workers x 2.
            _mt = os.environ.get("XELAB_MT", "2")
            proc = subprocess.Popen([xelab,"-mt",_mt,"-timescale","1ns/1ps","-debug","typical",
                                     "-top",module_name,"-snapshot",snap],
                                    stdout=lf, stderr=subprocess.STDOUT,
                                    cwd=wd, start_new_session=True)
            try: rc = proc.wait(timeout=sim_timeout)
            except subprocess.TimeoutExpired:
                try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except: pass
                row["ErrorCode"] = "XELAB_TIMEOUT_BYPASS"
                row["Error"] = f"xelab >{sim_timeout}s; " + _tail(xelab_log)
                return row
        if rc != 0:
            row["ErrorCode"] = "XELAB_FAIL_BYPASS"
            row["Error"] = _tail(xelab_log)
            return row
        # xsim
        xsim_log = f"{wd}/xsim_output.log"
        with open(xsim_log,"w") as lf:
            proc = subprocess.Popen([xsim, snap, "-R"], stdout=lf, stderr=subprocess.STDOUT,
                                    cwd=wd, start_new_session=True)
            try: proc.wait(timeout=sim_timeout)
            except subprocess.TimeoutExpired:
                try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except: pass
                row["ErrorCode"] = "SIM_WALLCLOCK_TIMEOUT_BYPASS"
                row["Error"] = f">{sim_timeout}s; " + _tail(xsim_log)
                return row
        # Parse xsim_output
        out = open(xsim_log, errors="replace").read()
        if "[PASS]" in out:
            row["Pass"] = True
            row["ErrorCode"] = "OK_BYPASS"
        elif "TIMEOUT" in out:
            row["ErrorCode"] = "SIM_TB_TIMEOUT_BYPASS"
            row["Error"] = "; ".join(l.strip() for l in out.split("\n") if "TIMEOUT" in l)[:500]
        elif "[FAIL]" in out:
            row["ErrorCode"] = "SIM_FAIL_BYPASS"
            row["Error"] = "; ".join(l.strip() for l in out.split("\n") if "[FAIL]" in l or "[ERROR]" in l)[:500]
        else:
            row["ErrorCode"] = "SIM_UNKNOWN_BYPASS"
            row["Error"] = out[-500:]
        # Cycles = system makespan = MAX over all PEs' perf_total.
        #
        # Until 2026-07-27 this used re.search(), which returns the FIRST match
        # -> GPU 0's counter only. When the reduction root lands on a PE other
        # than 0 (common on rings/tori) GPU 0 goes idle early and its counter
        # badly understates the makespan: 140/2822 rows in the p1 campaign
        # recorded a value BELOW the proven lower bound Omega, one as low as
        # 5 cycles against Omega=192. Those numbers are per-PE local work, not
        # end-to-end latency. Take the max, and keep the full per-PE vector so
        # load imbalance is recoverable without re-simulating.
        percpu = [int(x) for x in re.findall(r"perf_total\s*=\s*(\d+)", out)]
        if percpu:
            row["Cycles"] = max(percpu)
            row["CyclesGPU0"] = percpu[0]
            row["PerfAllGPUs"] = " ".join(str(v) for v in percpu)
    except Exception as e:
        row["ErrorCode"] = "EXCEPTION_BYPASS"
        row["Error"] = repr(e)
    finally:
        row["SimTime_s"] = round(time.time()-t0, 2)
        shutil.rmtree(wd, ignore_errors=True)
    return row


_CSV_LOCK = threading.Lock()
def _append_row(csv_path, row):
    with _CSV_LOCK:
        with open(csv_path,"a",newline="") as f:
            csv.DictWriter(f, fieldnames=UNIFIED_COLS).writerow(row)

def _worker_entry(args): return run_one(args)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=14400, help="per-stage wallclock cap (s)")
    ap.add_argument("--tb-list-json", required=True)
    ap.add_argument("--out-csv", default=f"{RES}/live_hw_results_p1_unified.csv")
    a = ap.parse_args()

    tbs = json.load(open(a.tb_list_json))
    # idempotent skip: don't re-run TBs that already have a deterministic settled result
    SETTLED = {'OK_BYPASS','OK_BYPASS_REUSED','SIM_TB_TIMEOUT_BYPASS','SIM_FAIL_BYPASS','SIM_UNKNOWN_BYPASS'}
    done = set()
    if os.path.exists(a.out_csv):
        with open(a.out_csv) as f:
            for row in csv.reader(f):
                if len(row) >= 7 and row[6] in SETTLED:
                    done.add((row[0], row[2]))
    n_all = len(tbs)
    tbs = [t for t in tbs if (t[0], t[1]) not in done]
    work = [(i,t,n,g,a.timeout) for (i,t,n,g) in tbs]
    print(f"[{time.strftime('%H:%M:%S')}] === BYPASS run: {len(work)} TBs "
          f"({n_all-len(work)} already settled -> skipped), {a.jobs} workers, "
          f"per-TB cap {a.timeout}s ===", flush=True)
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        fut_map = {ex.submit(_worker_entry, w): w for w in work}
        for fut in as_completed(fut_map):
            w = fut_map[fut]
            try: row = fut.result()
            except Exception as e:
                row = {"Instance":w[0],"Pipeline":parse_pipeline(w[1]),"TB_Name":w[1],
                       "Pass":False,"Cycles":-1,"SimTime_s":0.0,
                       "ErrorCode":"WORKER_CRASH_BYPASS","Error":repr(e)}
            _append_row(a.out_csv, row)
            print(f"[{time.strftime('%H:%M:%S')}] DONE {row['Instance']}/{row['TB_Name']} "
                  f"pass={row['Pass']} cycles={row['Cycles']} t={row['SimTime_s']}s "
                  f"err={row['ErrorCode']}", flush=True)
    print(f"[{time.strftime('%H:%M:%S')}] === BYPASS run complete ===", flush=True)

if __name__ == "__main__":
    main()
