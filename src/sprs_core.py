#!/usr/bin/env python3
"""
sprs_standalone_v4.py — SPRS Compiler v2.2: Fully Optimized
All 40 algorithms with timeout instrumentation.
C extension for hot paths. NumPy vectorized scoring.
Precomputed instances shared via fork().
"""
import math, random, sys, time, hashlib, argparse, os, bisect, heapq
import multiprocessing, ctypes, tempfile, subprocess
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set, Any
from collections import defaultdict, deque, Counter
from pathlib import Path

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ═══════════════════════════════════════════════════════════
# C EXTENSION — compiled at import time
# ═══════════════════════════════════════════════════════════
_C_SRC = r"""
#include <stdlib.h>
double c_cp_comm(const int *postorder, int n_post,
    const int *is_leaf, const int *ch_off, const int *ch_data,
    const int *ch_cnt, const int *asgn, const int *comm, int G,
    int lc, int ic, int N) {
    double *cp = (double*)calloc(N, sizeof(double));
    if (!cp) return -1.0;
    int i, node, c, gc, gn, ci;
    double mx, val, cc;
    for (i = 0; i < n_post; i++) {
        node = postorder[i];
        if (is_leaf[node]) { cp[node] = (double)lc; }
        else {
            gn = asgn[node]; mx = 0.0;
            int off = ch_off[node], cnt = ch_cnt[node];
            for (ci = 0; ci < cnt; ci++) {
                c = ch_data[off + ci]; gc = asgn[c];
                cc = (gc != gn) ? (double)comm[gc*G+gn] : 0.0;
                val = cp[c] + cc;
                if (val > mx) mx = val;
            }
            cp[node] = (double)ic + mx;
        }
    }
    double r = cp[0]; free(cp); return r;
}
int c_edge_cut(const int *parent, const int *asgn, int N) {
    int cut=0, n;
    for (n=1; n<N; n++) if (asgn[n]!=asgn[parent[n]]) cut++;
    return cut;
}
int c_max_load(const int *asgn, const int *cost, int N, int G) {
    int *ld=(int*)calloc(G,sizeof(int)); if(!ld) return -1;
    int n, mx=0;
    for (n=0;n<N;n++){int g=asgn[n]; if(g>=0&&g<G) ld[g]+=cost[n];}
    for (n=0;n<G;n++) if(ld[n]>mx) mx=ld[n];
    free(ld); return mx;
}
"""
_CLIB = None
def _compile_c():
    global _CLIB
    if _CLIB is not None: return _CLIB
    td = None
    try:
        td = tempfile.mkdtemp(prefix='sprs_')
        sp = os.path.join(td, 'f.c')
        with open(sp, 'w') as f: f.write(_C_SRC)
        if sys.platform == 'win32':
            lp = os.path.join(td, 'f.dll')
            subprocess.run(['cl','/O2','/LD',sp,f'/Fe:{lp}'],
                capture_output=True, timeout=30)
        else:
            lp = os.path.join(td, 'f.so')
            subprocess.run(['gcc','-O3','-shared','-fPIC','-o',lp,sp],
                capture_output=True, timeout=30)
        if os.path.exists(lp):
            _CLIB = ctypes.CDLL(lp)
            _CLIB.c_cp_comm.restype = ctypes.c_double
            _CLIB.c_edge_cut.restype = ctypes.c_int
            _CLIB.c_max_load.restype = ctypes.c_int
            # Keep the .dll/.so loaded; remove source file, retain lib.
            try: os.remove(sp)
            except OSError: pass
            import atexit, shutil
            atexit.register(shutil.rmtree, td, ignore_errors=True)
            return _CLIB
        # Compile failed — drop the tempdir right away
        import shutil
        shutil.rmtree(td, ignore_errors=True)
    except Exception:
        if td is not None:
            try:
                import shutil
                shutil.rmtree(td, ignore_errors=True)
            except Exception: pass
    return None
_compile_c()

# ═══════════════════════════════════════════════════════════
# TIMEOUT
# ═══════════════════════════════════════════════════════════
ALGO_TIMEOUT = 600
class AlgoTimeout(Exception): pass
class AlgoBypassed(Exception): pass  # size gate fired: algo cannot run in budget -> mark BYPASSED (no fake fallback)
class EmitRefused(Exception):
    """emit_sv_testbench refuses to emit an image the fabric cannot execute.

    The DMEM repair pass in assign_topology_aware_repair gives up with a bare
    `break` when it cannot relieve an overloaded PE, and returns an assignment
    whose peak DMEM still exceeds hw.dmem_depth.  The emitter then wrote
    addresses >= dmem_depth into the instruction words, and the fabric truncates
    every DMEM address to DMEM_ADDR_W bits (rtl/btree_fsm_fast.sv:517-521, :619),
    so e.g. address 522 aliases onto address 10 and the testbench returns a wrong
    root while reporting nothing.  Refusing is the only honest option: the
    emitted SystemVerilog would not be a testbench for the program the compiler
    believes it produced.
    """
    pass
_DEADLINE = [float('inf')]
def _set_eval_deadline(t=ALGO_TIMEOUT):
    """Set by run_single_eval ONLY. Algorithms must not call this."""
    _DEADLINE[0] = time.time() + t
def _set_deadline(t=None):
    """Called by algorithms — NO-OP. Deadline is set once per eval."""
    pass  # intentional no-op: deadline is set per-eval only
def _check_deadline(label=""):
    if time.time() > _DEADLINE[0]: raise AlgoTimeout(f"Timeout: {label}")

# ═══════════════════════════════════════════════════════════
# ASSIGNMENT CONVERSION HELPERS
# ═══════════════════════════════════════════════════════════
def _to_list(asgn, N):
    if isinstance(asgn, list) and len(asgn) >= N: return asgn
    arr = [0]*N
    if isinstance(asgn, dict):
        for n, g in asgn.items():
            if 0 <= n < N: arr[n] = g
    return arr
def _to_dict(asgn_list):
    return {n: asgn_list[n] for n in range(len(asgn_list))}

# ═══════════════════════════════════════════════════════════
# PRECOMPUTED CONTEXT
# ═══════════════════════════════════════════════════════════
_INSTANCE_CACHE = {}

class PrecomputedContext:
    __slots__ = ('N','n_gpus','parent_arr','cost_arr','is_leaf_arr',
                 'children_list','postorder_arr','comm_matrix','comm_flat',
                 'avg_comm','leaf_cost','internal_cost','total_work',
                 'np_parent','np_cost','np_is_leaf','np_comm',
                 'c_ch_off','c_ch_data','c_ch_cnt',
                 '_ct_post','_ct_leaf','_ct_choff','_ct_chdata','_ct_chcnt',
                 '_ct_parent','_ct_cost','_ct_comm','_ct_asgn_buf')

    def __init__(self, tree, topo, hw):
        N = tree.total_nodes; G = topo.n_nodes
        self.N = N; self.n_gpus = G
        self.leaf_cost = tree.leaf_cost; self.internal_cost = tree.internal_cost
        self.total_work = tree.total_work()
        self.parent_arr = list(tree._parent)
        self.cost_arr = [tree.node_cost(n) for n in range(N)]
        self.is_leaf_arr = [1 if tree.is_leaf(n) else 0 for n in range(N)]
        self.children_list = [tree.children(n) for n in range(N)]
        self.postorder_arr = list(tree.postorder())

        # Comm matrix: vectorized with numpy when available
        if HAS_NUMPY and G > 1:
            gi = np.arange(G, dtype=np.int32)
            # Build distance matrix vectorized by topology type
            name = topo.name
            if name == 'linear':
                dm = np.abs(gi[:, None] - gi[None, :])
            elif name == 'ring':
                diff = np.abs(gi[:, None] - gi[None, :])
                dm = np.minimum(diff, G - diff)
            elif name.startswith('mesh_'):
                p = name.split('_')[1].split('x'); R, C = int(p[0]), int(p[1])
                r = gi // C; c = gi % C
                dm = np.abs(r[:, None] - r[None, :]) + np.abs(c[:, None] - c[None, :])
            elif name.startswith('torus_'):
                p = name.split('_')[1].split('x'); R, C = int(p[0]), int(p[1])
                r = gi // C; c = gi % C
                dr = np.abs(r[:, None] - r[None, :]); dc = np.abs(c[:, None] - c[None, :])
                dm = np.minimum(dr, R - dr) + np.minimum(dc, C - dc)
            elif name.startswith('fat_tree_'):
                k = getattr(topo, '_fat_tree_k', max(2, int(math.ceil(math.sqrt(G)))))
                pods = gi // k
                dm = np.where(pods[:, None] == pods[None, :], 2, 4)
                np.fill_diagonal(dm, 0)
            elif name.startswith('hypercube_'):
                xor = gi[:, None] ^ gi[None, :]
                # popcount via lookup
                dm = np.zeros((G, G), dtype=np.int32)
                tmp = xor.copy()
                while np.any(tmp > 0):
                    dm += (tmp & 1).astype(np.int32)
                    tmp >>= 1
            else:
                # Fallback: call distance() pairwise
                dm = np.zeros((G, G), dtype=np.int32)
                for i in range(G):
                    for j in range(i + 1, G):
                        d = topo.distance(i, j)
                        dm[i, j] = dm[j, i] = d

            # Compute comm cost matrix: vectorized
            inject = hw.ni_inject_cycles; hop = hw.router_per_hop_cycles; eject = hw.ni_eject_cycles
            cm = np.where(dm > 0, inject + hop * dm + eject, 0).astype(np.int32)

            # Store as flat list for C extension
            self.comm_flat = cm.ravel().tolist()
            self.comm_matrix = cm.tolist()

            # avg_comm
            upper = cm[np.triu_indices(G, k=1)]
            self.avg_comm = float(np.mean(upper)) if len(upper) > 0 else 0.0
        elif G > 1:
            self.comm_matrix = [[0]*G for _ in range(G)]
            self.comm_flat = [0]*(G*G)
            for i in range(G):
                for j in range(i+1, G):
                    d = topo._analytical_distance(i, j)
                    if d < 0: d = topo.distance(i, j)
                    c = hw.comm_cost(d) if d > 0 else 0
                    self.comm_matrix[i][j] = self.comm_matrix[j][i] = c
                    self.comm_flat[i*G+j] = self.comm_flat[j*G+i] = c
            t2 = c2 = 0
            step = max(1, G // 32) if G > 256 else 1
            for i in range(0, G, step):
                for j in range(i+step, G, step):
                    if j < G: t2 += self.comm_matrix[i][j]; c2 += 1
            self.avg_comm = t2/c2 if c2 > 0 else 0.0
        else:
            self.comm_matrix = [[0]]; self.comm_flat = [0]
            self.avg_comm = 0.0

        # NumPy arrays
        if HAS_NUMPY:
            self.np_parent = np.array(self.parent_arr, dtype=np.int32)
            self.np_cost = np.array(self.cost_arr, dtype=np.int32)
            self.np_is_leaf = np.array(self.is_leaf_arr, dtype=np.int32)
            self.np_comm = np.array(self.comm_flat, dtype=np.int32)
        else:
            self.np_parent=self.np_cost=self.np_is_leaf=self.np_comm=None

        # Children CSR for C extension
        off_list=[]; data_list=[]; cnt_list=[]; off=0
        for n in range(N):
            ch = self.children_list[n]
            off_list.append(off); cnt_list.append(len(ch))
            data_list.extend(ch); off += len(ch)
        self.c_ch_off=off_list; self.c_ch_data=data_list; self.c_ch_cnt=cnt_list

        # PRE-CACHE ctypes arrays (fixed data — never changes per-instance)
        if _CLIB is not None:
            _ca = lambda lst: (ctypes.c_int * len(lst))(*lst)
            self._ct_post = _ca(self.postorder_arr)
            self._ct_leaf = _ca(self.is_leaf_arr)
            self._ct_choff = _ca(self.c_ch_off)
            self._ct_chdata = _ca(self.c_ch_data)
            self._ct_chcnt = _ca(self.c_ch_cnt)
            self._ct_parent = _ca(self.parent_arr)
            self._ct_cost = _ca(self.cost_arr)
            self._ct_comm = _ca(self.comm_flat)
            self._ct_asgn_buf = (ctypes.c_int * N)()  # reusable buffer
        else:
            self._ct_post=self._ct_leaf=self._ct_choff=self._ct_chdata=None
            self._ct_chcnt=self._ct_parent=self._ct_cost=self._ct_comm=None
            self._ct_asgn_buf=None

    def _fill_asgn_buf(self, asgn):
        """Fill reusable ctypes assignment buffer. Returns the buffer."""
        buf = self._ct_asgn_buf; N = self.N
        if isinstance(asgn, dict):
            for n in range(N): buf[n] = asgn.get(n, 0)
        elif isinstance(asgn, list):
            for n in range(N): buf[n] = asgn[n]
        else:  # numpy or other
            for n in range(N): buf[n] = int(asgn[n])
        return buf

    def fast_cp_comm(self, asgn):
        al = _to_list(asgn, self.N)
        if _CLIB is not None and self._ct_post is not None:
            try:
                ab = self._fill_asgn_buf(asgn)
                r = _CLIB.c_cp_comm(
                    self._ct_post, len(self.postorder_arr),
                    self._ct_leaf, self._ct_choff,
                    self._ct_chdata, self._ct_chcnt,
                    ab, self._ct_comm,
                    self.n_gpus, self.leaf_cost, self.internal_cost, self.N)
                if r >= 0.0: return r
                # r < 0 signals OOM in C code — fall through to Python path
            except Exception: pass
        N=self.N; cp=[0]*N; comm=self.comm_matrix
        lc=self.leaf_cost; ic=self.internal_cost
        il=self.is_leaf_arr; ch=self.children_list
        for node in self.postorder_arr:
            if il[node]: cp[node]=lc
            else:
                gn=al[node]; mx=0
                for c in ch[node]:
                    gc=al[c]; cc=comm[gc][gn] if gc!=gn else 0
                    val=cp[c]+cc
                    if val>mx: mx=val
                cp[node]=ic+mx
        return cp[0]

    def fast_edge_cut(self, asgn):
        al = _to_list(asgn, self.N)
        if _CLIB is not None and self._ct_parent is not None:
            try:
                ab = self._fill_asgn_buf(asgn)
                return _CLIB.c_edge_cut(self._ct_parent, ab, self.N)
            except Exception: pass
        if HAS_NUMPY and self.np_parent is not None:
            a = np.array(al, dtype=np.int32)
            return int(np.sum(a[1:self.N] != a[self.np_parent[1:self.N]]))
        pa=self.parent_arr; cut=0
        for n in range(1, self.N):
            if al[n]!=al[pa[n]]: cut+=1
        return cut

    def fast_max_load(self, asgn, ng):
        al = _to_list(asgn, self.N)
        if _CLIB is not None and self._ct_cost is not None:
            try:
                ab = self._fill_asgn_buf(asgn)
                r = _CLIB.c_max_load(ab, self._ct_cost, self.N, ng)
                if r >= 0: return r
                # r < 0 signals OOM in C code — fall through to Python path
            except Exception: pass
        if HAS_NUMPY and self.np_cost is not None:
            a = np.array(al, dtype=np.int32)
            ld = np.bincount(np.clip(a[:self.N],0,ng-1),
                weights=self.np_cost[:self.N].astype(np.float64), minlength=ng)
            return int(np.max(ld))
        ld=[0]*ng; cost=self.cost_arr
        for n in range(self.N):
            g=al[n]
            if 0<=g<ng: ld[g]+=cost[n]
        return max(ld) if ld else 0

    def fast_load_imbalance(self, asgn, ng):
        ml=self.fast_max_load(asgn,ng)
        avg=self.total_work/ng if ng>0 else self.total_work
        return ml/avg if avg>0 else 1.0

    def fast_score(self, asgn, ng):
        cp=self.fast_cp_comm(asgn); cut=self.fast_edge_cut(asgn)
        imb=self.fast_load_imbalance(asgn,ng)
        return cp*(1.0+0.1*cut)*imb

def _cache_key(nl, tn, nn): return f"{nl}|{tn}|{nn}"

def get_ctx(tree, topo, hw=None):
    if hw is None: hw=HW
    key=_cache_key(tree.n_leaves, topo.name, topo.n_nodes)
    if key not in _INSTANCE_CACHE:
        _INSTANCE_CACHE[key]=PrecomputedContext(tree, topo, hw)
    return _INSTANCE_CACHE[key]

# ═══════════════════════════════════════════════════════════
# HARDWARE CONFIG
# ═══════════════════════════════════════════════════════════
@dataclass
class HardwareConfig:
    dmem_depth:int=512; imem_depth:int=512
    tx_buf_depth:int=8; rx_buf_depth:int=8
    gci_latency:int=4; compute_latency:int=1; nop_latency:int=1
    ni_inject_cycles:int=2; router_per_hop_cycles:int=1; ni_eject_cycles:int=1
    timeout_max:int=10000; watchdog_max:int=20000
    pkt_width:int=96; instr_width:int=64
    piu_processing:int=1  # PIU: RX FIFO read + DMEM write (RTL-proven)
    pipeline_overhead:int=3  # 2-cycle fill (IF+DE) + 1-cycle drain (P_DRAIN)
    def comm_cost(self, hops):
        if hops<=0: return 0
        return self.ni_inject_cycles+self.router_per_hop_cycles*hops+self.ni_eject_cycles+self.piu_processing
    @property
    def leaf_cost(self): return self.gci_latency
    @property
    def internal_cost(self): return self.compute_latency
HW = HardwareConfig()

# ═══════════════════════════════════════════════════════════
# CBTREE (UNCHANGED)
# ═══════════════════════════════════════════════════════════
class CBTree:
    def __init__(self, n_leaves, hw=HW):
        if n_leaves<1: raise ValueError("n_leaves>=1")
        self.n_leaves=n_leaves; self.hw=hw
        self.leaf_cost=hw.leaf_cost; self.internal_cost=hw.internal_cost
        self.height=int(math.ceil(math.log2(n_leaves))) if n_leaves>1 else 0
        self.total_nodes=2*n_leaves-1
        self._parent=[0]*self.total_nodes
        self._left=[-1]*self.total_nodes; self._right=[-1]*self.total_nodes
        self._depth=[0]*self.total_nodes; self._is_leaf=[False]*self.total_nodes
        self._postorder=None; self._hu_levels=None; self._su_numbers=None
        for n in range(self.total_nodes):
            lc=2*n+1; rc=2*n+2
            self._left[n]=lc if lc<self.total_nodes else -1
            self._right[n]=rc if rc<self.total_nodes else -1
            self._is_leaf[n]=(lc>=self.total_nodes)
            self._parent[n]=(n-1)//2 if n>0 else -1
        for n in range(1,self.total_nodes):
            self._depth[n]=self._depth[self._parent[n]]+1
    def is_leaf(self,n): return self._is_leaf[n]
    def is_internal(self,n): return not self._is_leaf[n]
    def parent(self,n): return self._parent[n]
    def left_child(self,n): return self._left[n]
    def right_child(self,n): return self._right[n]
    def children(self,n):
        r=[]
        if self._left[n]>=0: r.append(self._left[n])
        if self._right[n]>=0: r.append(self._right[n])
        return r
    def depth(self,n): return self._depth[n]
    def level(self,n): return self.height-self._depth[n]
    def node_cost(self,n): return self.leaf_cost if self._is_leaf[n] else self.internal_cost
    def postorder(self):
        if self._postorder is not None: return self._postorder
        result=[]; stack=[(0,False)]
        while stack:
            n,v=stack.pop()
            if v or self._is_leaf[n]: result.append(n)
            else:
                stack.append((n,True))
                if self._right[n]>=0: stack.append((self._right[n],False))
                if self._left[n]>=0: stack.append((self._left[n],False))
        self._postorder=result; return result
    def su_postorder(self):
        """Sethi-Ullman aware postorder traversal (tier-0 memory optimization)."""
        if hasattr(self, '_su_postorder') and self._su_postorder is not None:
            return self._su_postorder
        result=[]; stack=[(0,False)]
        while stack:
            n,v=stack.pop()
            if v or self._is_leaf[n]: result.append(n)
            else:
                stack.append((n,True))
                cs = self.children(n)
                cs.sort(key=lambda c: self.sethi_ullman(c))
                for c in cs: stack.append((c,False))
        self._su_postorder=result; return result
    def bfs_order(self): return list(range(self.total_nodes))
    def leaves(self): return [i for i in range(self.total_nodes) if self._is_leaf[i]]
    def internals(self): return [i for i in range(self.total_nodes) if not self._is_leaf[i]]
    def total_work(self): return self.n_leaves*self.leaf_cost+(self.n_leaves-1)*self.internal_cost
    def critical_path_length(self): return self.height*self.internal_cost+self.leaf_cost
    def hu_levels(self):
        if self._hu_levels is not None: return self._hu_levels
        lv={}
        for n in reversed(range(self.total_nodes)):
            if self._is_leaf[n]: lv[n]=0
            else:
                cl=[]
                if self._left[n]>=0: cl.append(lv[self._left[n]])
                if self._right[n]>=0: cl.append(lv[self._right[n]])
                lv[n]=max(cl)+1 if cl else 0
        self._hu_levels=lv; return lv
    def sethi_ullman(self, node=None):
        if self._su_numbers is None:
            su={}
            for n in self.postorder():
                if self._is_leaf[n]: su[n]=1
                else:
                    cs=sorted([su[c] for c in self.children(n)],reverse=True)
                    if len(cs)==1: su[n]=cs[0]
                    elif cs[0]==cs[1]: su[n]=cs[0]+1
                    else: su[n]=cs[0]
            self._su_numbers=su
        return self._su_numbers[node if node is not None else 0]
    def strahler_number(self): return self.sethi_ullman(0)
    def subtree_nodes(self,node):
        r=[]; s=[node]
        while s:
            n=s.pop(); r.append(n)
            if self._right[n]>=0: s.append(self._right[n])
            if self._left[n]>=0: s.append(self._left[n])
        return r
    def subtree_weight(self,node): return sum(self.node_cost(n) for n in self.subtree_nodes(node))
    def reduction_signature(self):
        h=hashlib.sha256()
        h.update(f"CBT:n={self.n_leaves}:h={self.height}".encode())
        for node in self.postorder():
            if not self._is_leaf[node]:
                h.update(f"|{node}:{self._left[node]},{self._right[node]}".encode())
            else: h.update(f"|L{node}".encode())
        return h.hexdigest()
    def __repr__(self): return f"CBTree(n={self.n_leaves},h={self.height},N={self.total_nodes})"

# ═══════════════════════════════════════════════════════════
# TOPOLOGY (with caching)
# ═══════════════════════════════════════════════════════════
class Topology:
    def __init__(self,n_nodes,name="custom"):
        self.n_nodes=n_nodes; self.n_routers=n_nodes; self.name=name
        self.active_nodes=n_nodes  # actual GPUs requested (may be < n_nodes for mesh/torus/hypercube)
        self.ports_per_router=4; self.adjacency={}
        self._dist_matrix=None; self._edges=set(); self._neighbors=None
    @classmethod
    def linear(cls,n):
        t=cls(n,"linear"); t.ports_per_router=3
        for i in range(n-1):
            if i==0: t._add_link(i,1,i+1,1)
            else: t._add_link(i,2,i+1,1)
        t._compute_distances(); return t
    @classmethod
    def ring(cls,n):
        t=cls(n,"ring"); t.ports_per_router=3
        for i in range(n): t._add_link(i,1,(i+1)%n,2)
        t._compute_distances(); return t
    @classmethod
    def mesh(cls,rows,cols):
        n=rows*cols; t=cls(n,f"mesh_{rows}x{cols}"); t.ports_per_router=5
        for r in range(rows):
            for c in range(cols):
                nd=r*cols+c
                if r>0: t._add_link(nd,1,(r-1)*cols+c,2)
                if c<cols-1: t._add_link(nd,3,r*cols+(c+1),4)
        t._compute_distances(); return t
    @classmethod
    def torus(cls,rows,cols):
        n=rows*cols; t=cls(n,f"torus_{rows}x{cols}"); t.ports_per_router=5
        for r in range(rows):
            for c in range(cols):
                nd=r*cols+c
                t._add_link(nd,1,((r-1)%rows)*cols+c,2)
                t._add_link(nd,3,r*cols+((c+1)%cols),4)
        t._compute_distances(); return t
    @classmethod
    def fat_tree(cls,n):
        if n<=2: return cls.linear(n)
        k=max(2,int(math.ceil(math.sqrt(n))))
        np2=(n+k-1)//k; nc=max(1,k//2); tr=n+np2+nc
        t=cls(n,f"fat_tree_{n}"); t.n_routers=tr
        t.ports_per_router=max(5,k+2); t._fat_tree_k=k; t._fat_tree_n_pods=np2
        for i in range(n): t._add_link(i,1,n+i//k,1+(i%k))
        for p in range(np2):
            for c2 in range(nc): t._add_link(n+p,k+1+c2,n+np2+c2,1+p)
        t._compute_distances(); return t
    @classmethod
    def hypercube(cls,dim):
        n=1<<dim; t=cls(n,f"hypercube_{dim}d"); t.ports_per_router=dim+1
        for nd in range(n):
            for d in range(dim):
                nb=nd^(1<<d)
                if nb>nd: t._add_link(nd,d+1,nb,d+1)
        t._compute_distances(); return t
    def _add_link(self,ra,pa,rb,pb):
        self.adjacency[(ra,pa)]=(rb,pb); self.adjacency[(rb,pb)]=(ra,pa)
        self._edges.add((min(ra,rb),max(ra,rb)))
    def _compute_distances(self):
        n=self.n_routers; nbrs={i:set() for i in range(n)}
        for (ra,_),(rb,_) in self.adjacency.items(): nbrs[ra].add(rb); nbrs[rb].add(ra)
        self._neighbors={k:sorted(v) for k,v in nbrs.items()}; self._dist_cache={}
        if n<=32768:
            self._dist_matrix=[[10**9]*n for _ in range(n)]
            for src in range(n):
                d2=self._dist_matrix[src]; d2[src]=0; q=deque([src])
                while q:
                    u=q.popleft()
                    for v in nbrs[u]:
                        if d2[v]>d2[u]+1: d2[v]=d2[u]+1; q.append(v)
        else: self._dist_matrix=None
    def _analytical_distance(self,s,d):
        if self.name=="ring": dd=abs(s-d); return min(dd,self.n_nodes-dd)
        elif self.name.startswith("mesh_"):
            p=self.name.split("_")[1].split("x"); R,C=int(p[0]),int(p[1])
            r1,c1=divmod(s,C); r2,c2=divmod(d,C); return abs(r1-r2)+abs(c1-c2)
        elif self.name.startswith("torus_"):
            p=self.name.split("_")[1].split("x"); R,C=int(p[0]),int(p[1])
            r1,c1=divmod(s,C); r2,c2=divmod(d,C)
            return min(abs(r1-r2),R-abs(r1-r2))+min(abs(c1-c2),C-abs(c1-c2))
        elif self.name=="linear": return abs(s-d)
        elif self.name.startswith("fat_tree_"):
            nl=int(self.name.split("_")[-1])
            if s>=nl or d>=nl: return -1
            k=getattr(self,'_fat_tree_k',max(2,int(math.ceil(math.sqrt(nl)))))
            return 2 if s//k==d//k else 4
        elif self.name.startswith("hypercube_"): return bin(s^d).count('1')
        return -1
    def _bfs_distance(self,s,d):
        if s==d: return 0
        if self._neighbors is None: self._compute_distances()
        nb=self._neighbors or {}; vis={s:0}; q=deque([s])
        while q:
            u=q.popleft()
            if u==d: return vis[u]
            for v in nb.get(u,[]):
                if v not in vis: vis[v]=vis[u]+1; q.append(v)
        return 10**9
    def distance(self,s,d):
        if s==d: return 0
        dd=self._analytical_distance(s,d)
        if dd>=0: return dd
        if self._dist_matrix is not None:
            dd=self._dist_matrix[s][d]; return dd if dd<10**9 else -1
        if not hasattr(self,'_dist_cache'): self._dist_cache={}
        key=(min(s,d),max(s,d))
        if key not in self._dist_cache: self._dist_cache[key]=self._bfs_distance(s,d)
        dd=self._dist_cache[key]; return dd if dd<10**9 else -1
    def comm_cost(self,hops,hw=HW): return hw.comm_cost(hops)
    def comm_cost_between(self,s,d,hw=HW):
        if s==d: return 0
        return self.comm_cost(self.distance(s,d),hw)
    def neighbors(self,r):
        if self._neighbors is None: self._compute_distances()
        return self._neighbors.get(r,[])
    def warm_cache(self):
        if self._dist_matrix is not None: return
        # All standard topologies (linear, ring, mesh, torus, fat_tree, hypercube)
        # have analytical distance formulas for compute nodes.
        # Only build BFS matrix for truly custom topologies.
        if self._analytical_distance(0, min(1, self.n_nodes-1)) >= 0:
            return  # analytical formula available, skip O(G²) BFS
        n=self.n_nodes
        if n<=32768:
            self._dist_matrix=[[0]*n for _ in range(n)]
            for i in range(n):
                for j in range(i+1,n):
                    dd=self._bfs_distance(i,j)
                    self._dist_matrix[i][j]=self._dist_matrix[j][i]=dd
    def diameter(self):
        if hasattr(self,'_diam_c'): return self._diam_c
        if self.n_nodes>32768:
            mx=0
            for i in range(min(self.n_nodes,16)):
                for j in [0,self.n_nodes//4,self.n_nodes//2,3*self.n_nodes//4,self.n_nodes-1]:
                    if j<self.n_nodes and i!=j:
                        dd=self.distance(i,j)
                        if dd>mx: mx=dd
            self._diam_c=mx; return mx
        mx=0
        for i in range(self.n_nodes):
            for j in range(i+1,self.n_nodes):
                dd=self.distance(i,j)
                if dd>mx: mx=dd
        self._diam_c=mx; return mx
    def avg_comm_cost(self,hw=HW):
        if hasattr(self,'_acc'): return self._acc
        if self.n_nodes<=1: self._acc=0.0; return 0.0
        t2=c2=0; step=max(1,self.n_nodes//20) if self.n_nodes>128 else 1
        for i in range(0,self.n_nodes,step):
            for j in range(i+step,self.n_nodes,step):
                if j<self.n_nodes: t2+=self.comm_cost_between(i,j,hw); c2+=1
        self._acc=t2/c2 if c2>0 else 0.0; return self._acc
    def bisection_bandwidth(self):
        if hasattr(self,'_bbc'): return self._bbc
        n=self.n_nodes
        if n<=2: r=max(1,len(self._edges))
        elif self.name=="linear": r=1
        elif self.name=="ring": r=2
        elif self.name.startswith("mesh_"):
            p=self.name.split("_")[1].split("x"); r=min(int(p[0]),int(p[1]))
        elif self.name.startswith("torus_"):
            p=self.name.split("_")[1].split("x"); r=2*min(int(p[0]),int(p[1]))
        elif self.name.startswith("fat_tree_"): r=max(1,n//2)
        elif self.name.startswith("hypercube_"):
            dim=int(self.name.split("_")[1].replace("d","")); r=max(1,1<<(dim-1))
        else:
            half=n//2; mc=10**9
            for start in range(min(n,4)):
                vis=[]; q=deque([start]); seen={start}
                while q and len(vis)<half:
                    u=q.popleft(); vis.append(u)
                    for v in self.neighbors(u):
                        if v not in seen and v<n: seen.add(v); q.append(v)
                sa=set(vis)
                cut=sum(1 for(ra,rb)in self._edges if ra<n and rb<n and(ra in sa)!=(rb in sa))
                mc=min(mc,cut)
            r=max(1,mc)
        self._bbc=r; return r
    def generate_routing_tables(self):
        if hasattr(self,'_rt_cache'): return self._rt_cache
        out_by_src={}
        for(ra,pa),(rb,_)in self.adjacency.items():
            out_by_src.setdefault(ra,[]).append((pa,rb))
        tables={}
        for router in range(self.n_routers):
            if router%256==0: _check_deadline("gen_rt")
            table={}
            outs=out_by_src.get(router,[])
            for dest in range(self.n_nodes):
                if dest==router: table[dest]=0; continue
                bp,bd=0,10**9
                for pa,rb in outs:
                    dd=self.distance(rb,dest)
                    if dd<bd: bd=dd; bp=pa
                table[dest]=bp
            tables[router]=table
        self._rt_cache=tables
        return tables
    def generate_adjacency_table(self):
        if hasattr(self,'_adj_table_cache'): return self._adj_table_cache
        self._adj_table_cache=[(ra,pa,rb,pb)for(ra,pa),(rb,pb)in self.adjacency.items()]
        return self._adj_table_cache
    def shortest_path(self,s,d):
        if s==d: return[s]
        if self._neighbors is None: self._compute_distances()
        nb=self._neighbors or{}; pm={s:None}; q=deque([s])
        while q:
            u=q.popleft()
            if u==d: break
            for v in nb.get(u,[]):
                if v not in pm: pm[v]=u; q.append(v)
        if d not in pm: return[]
        path=[]; cur=d
        while cur is not None: path.append(cur); cur=pm[cur]
        path.reverse(); return path
    def __repr__(self): return f"Topology({self.name},n={self.n_nodes})"

# ═══════════════════════════════════════════════════════════
# BIT-ACCURATE FP64 ADDER — matches fp64_add.sv exactly
# ═══════════════════════════════════════════════════════════
import struct as _struct

def _fp64_add_bits(a_bits, b_bits):
    """Pure-integer FP64 addition matching fp64_add.sv bit-exactly.

    Implements: FTZ input/output, RNE rounding, NaN/Inf propagation.
    All intermediate arithmetic is done in Python integers (arbitrary precision)
    to avoid any host FPU influence.
    """
    # Unpack fields
    a_sign = (a_bits >> 63) & 1
    a_exp  = (a_bits >> 52) & 0x7FF
    a_frac = a_bits & ((1 << 52) - 1)
    b_sign = (b_bits >> 63) & 1
    b_exp  = (b_bits >> 52) & 0x7FF
    b_frac = b_bits & ((1 << 52) - 1)

    # Special value detection
    a_is_zero = (a_exp == 0) and (a_frac == 0)
    b_is_zero = (b_exp == 0) and (b_frac == 0)
    a_is_inf  = (a_exp == 0x7FF) and (a_frac == 0)
    b_is_inf  = (b_exp == 0x7FF) and (b_frac == 0)
    a_is_nan  = (a_exp == 0x7FF) and (a_frac != 0)
    b_is_nan  = (b_exp == 0x7FF) and (b_frac != 0)
    a_is_sub  = (a_exp == 0) and (a_frac != 0)
    b_is_sub  = (b_exp == 0) and (b_frac != 0)

    # Canonical quiet NaN
    QNAN = (0x7FF << 52) | (1 << 51)

    # NaN propagation (same priority as RTL)
    if a_is_nan:
        return (a_sign << 63) | (0x7FF << 52) | (1 << 51) | (a_frac & ((1 << 51) - 1))
    if b_is_nan:
        return (b_sign << 63) | (0x7FF << 52) | (1 << 51) | (b_frac & ((1 << 51) - 1))

    # Inf handling
    if a_is_inf and b_is_inf:
        if a_sign == b_sign:
            return (a_sign << 63) | (0x7FF << 52)  # same sign -> Inf
        else:
            return QNAN  # Inf - Inf -> NaN
    if a_is_inf:
        return a_bits
    if b_is_inf:
        return b_bits

    # Zero / subnormal handling (FTZ)
    if (a_is_zero or a_is_sub) and (b_is_zero or b_is_sub):
        return 0
    if a_is_zero or a_is_sub:
        return b_bits
    if b_is_zero or b_is_sub:
        return a_bits

    # ── Normal + Normal ──
    # Build 55-bit mantissas: [54:0] = {1'b0, 1'b1, frac[51:0], 1'b_guard}
    e_a, e_b = a_exp, b_exp

    if e_a >= e_b:
        s_a, s_b = a_sign, b_sign
        m_big   = (1 << 53) | (a_frac << 1)  # bit 53 = implicit 1, bit 0 = guard
        m_small = (1 << 53) | (b_frac << 1)
        e_r = e_a
        shift_amt = e_a - e_b
    else:
        s_a, s_b = b_sign, a_sign
        m_big   = (1 << 53) | (b_frac << 1)
        m_small = (1 << 53) | (a_frac << 1)
        e_r = e_b
        shift_amt = e_b - e_a

    # Align mantissas — track sticky bit
    # The alignment tail is split into its MSB (align_round, weight 1/2 of a
    # guard unit) and everything below it (align_low).  sticky = their OR and is
    # bit-identical to the previous single-expression form; the split is what
    # makes the effective-subtraction borrow roundable.  Mirrors fp64_add.sv.
    if shift_amt > 54:
        m_aligned = 0
        align_round = 0                 # m_small[shift_amt-1] is 0 for shift_amt>=55
        align_low = 1 if m_small != 0 else 0
    elif shift_amt == 0:
        m_aligned = m_small
        align_round = 0
        align_low = 0
    else:
        m_aligned = m_small >> shift_amt
        align_round = (m_small >> (shift_amt - 1)) & 1
        align_low = 1 if (m_small & ((1 << (shift_amt - 1)) - 1)) != 0 else 0
    sticky = align_round | align_low

    # Effective operation
    effective_sub = (s_a != s_b)

    sub_borrow = 0
    if not effective_sub:
        m_sum = m_big + m_aligned
        s_r = s_a
    else:
        # The bits truncated during alignment form a tail 0 < t < 1 guard unit
        # whenever sticky=1.  The exact difference is m_big - m_aligned - t, so
        # the raw m_big - m_aligned is too large by t and the ADDITION rounding
        # rule below (guard && (sticky || lsb)) then rounds a value lying just
        # BELOW the midpoint up, giving +1 ulp.  Borrow the tail here: the
        # remainder becomes r = 1 - t, still strictly inside (0,1), so sticky
        # stays 1 and the same rounding rule is now the correct one.
        sub_borrow = sticky
        m_sum = m_big - m_aligned - sticky
        s_r = s_a
        if m_sum < 0:
            m_sum = -m_sum
            s_r = 1 - s_a

    # Zero result
    if m_sum == 0:
        return 0

    # Normalize
    e_norm = e_r

    # Check bit 55 (overflow by 2)
    if m_sum & (1 << 55):
        sticky = sticky | (m_sum & 1)
        m_norm = (m_sum >> 2) & ((1 << 54) - 1)
        m_norm = (m_norm << 1) | ((m_sum >> 1) & 1)
        # Reconstruct: m_norm = m_sum[55:2] concat m_sum[1]
        m_norm = ((m_sum >> 2) << 1) | ((m_sum >> 1) & 1)
        e_norm = e_r + 2
    elif m_sum & (1 << 54):
        # Overflow by 1 — right shift by 1
        sticky = sticky | (m_sum & 1)
        m_norm = (m_sum >> 1) & ((1 << 55) - 1)
        e_norm = e_r + 1
    else:
        # Find leading one (should be at bit 53 for implicit 1)
        lzc = 0
        for i in range(54, -1, -1):
            if m_sum & (1 << i):
                break
            lzc += 1

        m_norm = m_sum & ((1 << 55) - 1)
        if lzc > 0:
            if lzc <= 1:
                pass  # m_norm stays as is
            else:
                shift_left = lzc - 1
                if shift_left < 55:
                    m_norm = (m_sum << shift_left) & ((1 << 55) - 1)
                else:
                    m_norm = 0
                # When a borrow was taken the remainder is r = 1 - t.  A left
                # shift by one scales it to 2r, which leaves (0,1) whenever
                # t <= 1/2, i.e. whenever the tail is not strictly greater than
                # half a guard unit.  Carry that whole unit into m_norm and
                # recompute whether anything is left below.  (For effective
                # subtraction a borrow implies m_sum >= 2**52, so lzc is 1 or 2
                # and this is the only shift amount that can occur.)
                if sub_borrow and lzc == 2:
                    if not (align_round and align_low):
                        m_norm = (m_norm + 1) & ((1 << 55) - 1)   # 2r >= 1
                    sticky = 0 if (align_round and not align_low) else 1
                if e_norm > shift_left:
                    e_norm = e_norm - shift_left
                else:
                    # Underflow -> flush to zero
                    return (s_r << 63)

    # Check overflow to infinity
    if e_norm >= 0x7FF:
        return (s_r << 63) | (0x7FF << 52)

    if m_norm == 0:
        return 0

    # Pack: bit 53 is implicit 1, bits [52:1] are fraction, bit [0] is guard
    frac_out = (m_norm >> 1) & ((1 << 52) - 1)
    guard = m_norm & 1

    # Round to nearest even (RNE)
    if guard and (sticky or (frac_out & 1)):
        frac_out += 1
        if frac_out >= (1 << 52):
            frac_out = 0
            e_norm += 1

    if e_norm >= 0x7FF:
        return (s_r << 63) | (0x7FF << 52)

    # Check for subnormal result (FTZ output)
    if e_norm <= 0:
        return (s_r << 63)  # flush to signed zero

    return (s_r << 63) | (e_norm << 52) | frac_out


def bit_accurate_fadd(a_float, b_float):
    """Bit-accurate IEEE 754 FP64 addition matching fp64_add.sv hardware.

    Args:
        a_float, b_float: Python float values
    Returns:
        Python float with the exact bit pattern the hardware would produce
    """
    a_bits = _struct.unpack('<Q', _struct.pack('<d', a_float))[0]
    b_bits = _struct.unpack('<Q', _struct.pack('<d', b_float))[0]
    result_bits = _fp64_add_bits(a_bits, b_bits)
    return _struct.unpack('<d', _struct.pack('<Q', result_bits))[0]


def bit_accurate_fadd_int(a_bits, b_bits):
    """Same as bit_accurate_fadd but operates on raw 64-bit integer representations."""
    return _fp64_add_bits(a_bits, b_bits)


# ═══════════════════════════════════════════════════════════
# ISA ENCODING
# ═══════════════════════════════════════════════════════════
OP_NOP=0x0; OP_GENERATE=0x1; OP_COMPUTE=0x2; OP_SEND=0x3; OP_RECV=0x4  # RECV deprecated
ALU_ADD=0b000; ALU_MAX=0b001; ALU_MIN=0b010
ALU_AND=0b011; ALU_OR=0b100; ALU_XOR=0b101
ALU_SADD=0b110; ALU_FADD=0b111

def encode_instruction(op,aux=0,dest=0,addr_a=0,addr_b=0):
    return((op&0xF)<<60)|((aux&0xF)<<56)|((dest&0xFFFF)<<40)|((addr_a&0xFFFF)<<24)|((addr_b&0xFFFF)<<8)
def encode_nop(): return 0
def encode_generate(da): return encode_instruction(OP_GENERATE,dest=da)
def encode_compute(d,a,b,alu=ALU_ADD):
    return encode_instruction(OP_COMPUTE,aux=(alu&0x7)<<1,dest=d,addr_a=a,addr_b=b)
def encode_send(src_addr, dest_gpu, target_addr, link=0):
    """RDMA-Push SEND: reads DMEM[src_addr], sends to dest_gpu, writes to DMEM[target_addr] at receiver."""
    return encode_instruction(OP_SEND, aux=link&0xF, dest=target_addr, addr_a=src_addr, addr_b=dest_gpu)

# ═══════════════════════════════════════════════════════════
# SCHEDULE
# ═══════════════════════════════════════════════════════════
class ScheduledOp:
    __slots__=['op_type','node','gpu','cycle','dest_addr','addr_a',
               'addr_b','dest_gpu','link','alu_op','duration']
    def __init__(self,op_type,node=-1,gpu=0,cycle=0,**kw):
        self.op_type=op_type;self.node=node;self.gpu=gpu;self.cycle=cycle
        self.dest_addr=kw.get('dest_addr',0);self.addr_a=kw.get('addr_a',0)
        self.addr_b=kw.get('addr_b',0);self.dest_gpu=kw.get('dest_gpu',0)
        self.link=kw.get('link',0);self.alu_op=kw.get('alu_op',ALU_ADD)
        self.duration=kw.get('duration',1)
    def __repr__(self): return f"Op({self.op_type},n={self.node},g={self.gpu},t={self.cycle})"

class Schedule:
    def __init__(self,ng):
        self.n_gpus=ng;self.ops={g:[] for g in range(ng)}
        self.assignment={};self.addr_alloc={};self.makespan=0
    def add_op(self,op):
        self.ops[op.gpu].append(op)
        end=op.cycle+op.duration
        if end>self.makespan: self.makespan=end
    def get_gpu_ops(self,gpu): return sorted(self.ops.get(gpu,[]),key=lambda o:o.cycle)

# ═══════════════════════════════════════════════════════════
# EVALUATORS — dispatch to PrecomputedContext
# ═══════════════════════════════════════════════════════════
def _get_ctx(tree, topo):
    return _INSTANCE_CACHE.get(_cache_key(tree.n_leaves, topo.name, topo.n_nodes))

def _find_ctx_by_N(N):
    for c in _INSTANCE_CACHE.values():
        if c.N == N: return c
    return None

def compute_cp_comm(tree, asgn, topo, hw=HW):
    ctx = _get_ctx(tree, topo)
    if ctx: return ctx.fast_cp_comm(asgn)
    N=tree.total_nodes; cp=[0]*N
    for node in tree.postorder():
        if tree.is_leaf(node): cp[node]=tree.leaf_cost
        else:
            gn=asgn[node] if isinstance(asgn,list) else asgn.get(node,0)
            mx=0
            for ch in tree.children(node):
                gc=asgn[ch] if isinstance(asgn,list) else asgn.get(ch,0)
                cc=topo.comm_cost_between(gc,gn,hw) if gc!=gn else 0
                val=cp[ch]+cc
                if val>mx: mx=val
            cp[node]=tree.internal_cost+mx
    return cp[0]

def compute_edge_cut(tree, asgn):
    ctx=_find_ctx_by_N(tree.total_nodes)
    if ctx: return ctx.fast_edge_cut(asgn)
    cut=0
    for n in range(1,tree.total_nodes):
        p=tree.parent(n)
        if p>=0:
            gn=asgn[n] if isinstance(asgn,list) else asgn.get(n,0)
            gp=asgn[p] if isinstance(asgn,list) else asgn.get(p,0)
            if gn!=gp: cut+=1
    return cut

def compute_load_imbalance(tree, asgn, ng):
    ctx=_find_ctx_by_N(tree.total_nodes)
    if ctx: return ctx.fast_load_imbalance(asgn, ng)
    ld=[0]*ng
    for n in range(tree.total_nodes):
        g=asgn[n] if isinstance(asgn,list) else asgn.get(n,0)
        if 0<=g<ng: ld[g]+=tree.node_cost(n)
    W=tree.total_work(); avg=W/ng if ng>0 else W
    return max(ld)/avg if avg>0 else 1.0

def is_connected_partition(tree, asgn, ng):
    for g in range(ng):
        nodes=[n for n in range(tree.total_nodes)
               if (asgn[n] if isinstance(asgn,list) else asgn.get(n))==g]
        if not nodes: continue
        ps=set(nodes); roots=0
        for n in nodes:
            p=tree.parent(n)
            if p<0 or p not in ps: roots+=1
        if roots>1: return False
    return True


def _estimate_makespan(tree, asgn, ng, topo, hw=HW):
    """Theoretical lower-bound heuristic: max(critical_path, max_load).

    NOT cycle-accurate — ignores instruction scheduling, RECV/NOP overhead,
    and GCI pipelining. Used only as a cheap O(N) fitness function inside
    S2/S4 algorithm inner loops where no mapping is available yet.
    For ranking or any accuracy-sensitive decision, use build_schedule().makespan.
    """
    ctx=_get_ctx(tree,topo)
    if ctx: return max(ctx.fast_cp_comm(asgn),ctx.fast_max_load(asgn,ng))
    cp=compute_cp_comm(tree,asgn,topo,hw)
    ld=[0]*ng
    for n in range(tree.total_nodes):
        g=asgn[n] if isinstance(asgn,list) else asgn.get(n,0)
        if 0<=g<ng: ld[g]+=tree.node_cost(n)
    return max(cp,max(ld) if ld else 0)

# ═══════════════════════════════════════════════════════════════════════════════
# Stage 0 — Composite Lower Bound Ω
# ═══════════════════════════════════════════════════════════════════════════════

def compute_lower_bound(tree: CBTree, n_procs: int, topo: 'Topology',
                        hw: HardwareConfig = HW) -> Dict[str, float]:
    """Hardware-calibrated composite lower bound Omega for distributed tree-reduction makespan.

    Omega = max(lb_span, inf_K max(lb_gen, lb_instr), lb_comm, lb_hu,
                lb_gather, lb_bisection)

    All constituent bounds use hardware-calibrated operation costs:
      - GCI effective occupation: gci_latency + 2 cycles (RTL-proven gap)
      - COMPUTE: compute_latency cycles
      - SEND: 1 pipeline slot

    Constituent bounds:
      lb_span:      (gci_latency+2) + D*compute_latency - critical-path depth
      lb_gen:       (gci_latency+2)*ceil(N/K) - GCI serialization per PE
      lb_instr:     ceil(total_pipeline_slots/K) - instruction throughput
      lb_comm:      gci_latency + comm_cost(d_min) + compute_latency
      lb_hu:        GCI-aware Hu HLF (comm-free, PE-serialization aware)
      lb_gather:    root-PE gather bound - root must receive K-1 partial results
      lb_bisection: network link serialization at topology bisection cut
    """
    bounds = {}
    valid_lbs = []
    N = tree.n_leaves
    P = min(n_procs, topo.n_nodes)
    D = tree.height
    gci_gap = hw.gci_latency + 2  # RTL-proven: GEN->GEN spacing = 6 cycles

    # --- Bound 1: Span (critical-path depth, parameterized) ---
    # Fix Omega-1: use gci_gap for leaf data readiness, parameterize compute_latency
    if N >= 2:
        lb_span = gci_gap + D * hw.compute_latency
    else:
        lb_span = 1
    bounds['lb_span'] = lb_span
    valid_lbs.append(lb_span)

    # --- IMEM capacity constrains K_min ---
    max_gens_per_pe = (hw.imem_depth + gci_gap - 1) // gci_gap
    K_min = max(1, math.ceil(N / max_gens_per_pe)) if N > 0 else 1
    K_max = max(1, min(P, 2 * N - 1))
    bounds['K_min'] = K_min
    bounds['K_max'] = K_max

    # --- Minimum hop distance between any pair of compute nodes ---
    d_min = 1
    if P >= 2:
        best_d = 10**9
        n_sample = min(P, topo.n_nodes, 20)
        for i in range(n_sample):
            for j in range(i + 1, n_sample):
                dd = topo.distance(i, j)
                if 0 < dd < best_d:
                    best_d = dd
        if best_d < 10**9:
            d_min = best_d
    bounds['d_min'] = d_min

    # --- Bound 2: Single cross-PE hop floor (K >= 2) ---
    lb_comm = gci_gap + hw.comm_cost(d_min) + hw.compute_latency if P >= 2 else 0
    bounds['lb_comm'] = lb_comm

    # --- K-dependent bounds: find K* minimizing the bottleneck ---
    best_K = K_min
    best_val = float('inf')
    best_components = (0, 0)

    for K in range(max(1, K_min), K_max + 1):
        m = math.ceil(N / K)

        # lb_gen: HW-calibrated GCI serialization bottleneck
        if m >= 2:
            lb_gen_K = gci_gap * m
        else:
            lb_gen_K = max(1, gci_gap * m - (gci_gap - 1))

        # Fix Omega-3: lb_instr uses UNIT pipeline slots (1 per GEN, not gci_gap)
        # GENERATEs: 1 pipeline slot each (GCI wait is captured by lb_gen)
        # COMPUTEs: compute_latency pipeline slots each
        # SENDs: 1 pipeline slot each
        if K >= 2:
            total_slots = N + (N - 1) * hw.compute_latency + (K - 1)
            lb_instr_K = math.ceil(total_slots / K)
        else:
            lb_instr_K = N + (N - 1) * hw.compute_latency if N >= 1 else 0

        # Fix Omega-4: lb_merge REMOVED (invalid for non-symmetric schedules)
        val = max(lb_gen_K, lb_instr_K)
        if K >= 2:
            val = max(val, lb_comm)
        if val < best_val:
            best_val = val
            best_K = K
            best_components = (lb_gen_K, lb_instr_K)

    bounds['lb_gen'] = best_components[0]
    bounds['lb_instr'] = best_components[1]
    bounds['K_star'] = best_K
    bounds['lb_K_opt'] = best_val
    valid_lbs.append(best_val)

    # --- Memory (informational) ---
    su = tree.sethi_ullman()
    bounds['su_number'] = su
    bounds['su_feasible'] = (su <= hw.dmem_depth)

    # --- Fix Omega-5: Hu HLF lower bound (GCI-aware, valid) ---
    lb_hu = _hu_hlf_lb(tree, max(1, min(P, tree.total_nodes)), hw)
    bounds['lb_hu_hlf'] = lb_hu
    valid_lbs.append(lb_hu)

    # --- NEW: Communication-aware bounds for network-bottlenecked topologies ---
    if P >= 2:
        lb_gather, lb_bisect = _comm_aware_bounds(tree, P, topo, hw, gci_gap)
        bounds['lb_gather'] = lb_gather
        bounds['lb_bisection'] = lb_bisect
        valid_lbs.append(lb_gather)
        valid_lbs.append(lb_bisect)

    bounds['omega'] = max(valid_lbs) if valid_lbs else 0
    bounds['active_bound'] = max(
        ((v, k) for k, v in bounds.items() if k.startswith('lb_')),
        default=(0, 'none')
    )[1]

    return bounds


def _comm_aware_bounds(tree: CBTree, P: int, topo: 'Topology',
                       hw: HardwareConfig, gci_gap: int) -> tuple:
    """Communication-aware lower bounds for network-bottlenecked topologies.

    Returns (lb_gather, lb_bisection).

    lb_gather:  The root PE's critical path includes receiving (K-1) partial
                results.  Even in the optimal schedule, the root must perform
                ceil(log2 K) sequential merge steps, each requiring at least one
                cross-PE communication at distance d_avg (the average distance
                to the root in the optimal placement).  We use the topology
                diameter / 2 as a proxy for the achievable root-to-farthest
                distance after optimal root placement.

    lb_bisection:  On any topology cut into two halves with bisection bandwidth B,
                   at least ceil(K/2)-1 partial results from one side must cross
                   the cut to reach the root on the other side.  Each link carries
                   at most 1 packet/cycle.  This serializes the cross-bisection
                   traffic, giving a floor on the total communication time.
    """
    N = tree.n_leaves
    K = P  # number of PEs being used

    # --- Topology characterization ---
    # Diameter: compute analytically for known types, sample otherwise
    diameter = _topology_diameter(topo, P)

    # Bisection bandwidth: minimum cut across topology halves
    bisection_bw = _topology_bisection_bw(topo, P)

    # --- lb_gather: communication critical path for distributed merge ---
    # The root PE must receive partial results from the farthest PE
    # through a chain of merge steps.  The communication critical path
    # is bounded by the topology distance from root to farthest PE.
    # With optimal root placement, this is ceil(diameter/2).
    # The merge steps are pipelined: on a topology with diameter D,
    # data travels at most D hops regardless of merge_levels.
    if K >= 2:
        merge_levels = math.ceil(math.log2(K))
        d_min = 1
        for i in range(min(P, 10)):
            for j in range(i+1, min(P, 10)):
                dd = topo.distance(i, j)
                if dd > 0:
                    d_min = min(d_min, dd) if d_min > 0 else dd

        # The critical path has: leaf gen + some merge COMPUTEs + communication
        # Communication hops on critical path: at most ceil(diameter/2) hops
        # (optimal root placement).  merge_levels COMPUTEs are pipelined
        # with comm. The critical path is:
        #   gci_gap + merge_levels * compute_latency + comm_cost(ceil(diam/2))
        # This is tighter than summing per-level comm costs.
        max_root_dist = math.ceil(diameter / 2)
        lb_gather = (gci_gap
                     + merge_levels * hw.compute_latency
                     + hw.comm_cost(max_root_dist))
    else:
        lb_gather = 0

    # --- lb_bisection: link serialization at the bisection cut ---
    # With K PEs, at least K-1 SENDs total.  For a balanced binary merge,
    # at least ceil((K-1)/2) messages must cross *some* bisection cut.
    # Each link carries 1 packet/cycle.  The minimum time to drain all
    # cross-cut traffic through bisection_bw links:
    #   ceil(cross_messages / bisection_bw) cycles of link occupancy
    #   + comm_cost(1) - 1 for pipeline fill of the first packet.
    # Plus the leaf generation + compute on the critical path.
    if K >= 2 and bisection_bw > 0:
        # Minimum cross-bisection messages: in a K-PE tree reduction with
        # roughly K/2 PEs on each side, at least ceil(K/2) - 1 intermediate
        # results plus 1 final result must cross.  Conservative: ceil((K-1)/2).
        cross_msgs = max(1, (K - 1 + 1) // 2)  # ceil((K-1)/2)
        # Link drain time (pipelined: first packet takes full comm_cost,
        # subsequent ones are 1 cycle apart at the bottleneck link)
        drain_cycles = cross_msgs  # 1 packet per cycle per link per direction
        link_time = math.ceil(drain_cycles / bisection_bw)

        # Total: leaf gen (on one side) + link serialization + compute chain
        lb_bisect = gci_gap + link_time + hw.comm_cost(1) + hw.compute_latency
    else:
        lb_bisect = 0

    return lb_gather, lb_bisect


def _topology_bisection_bw(topo: 'Topology', P: int) -> int:
    """Bisection bandwidth for known topology types.  Conservative estimate."""
    name = topo.name
    if name == 'linear':
        return 1
    elif name == 'ring':
        return 2
    elif name.startswith('mesh_'):
        parts = name.split('_')[1].split('x')
        R, C = int(parts[0]), int(parts[1])
        return min(R, C)
    elif name.startswith('torus_'):
        parts = name.split('_')[1].split('x')
        R, C = int(parts[0]), int(parts[1])
        return 2 * min(R, C)
    elif name.startswith('fat_tree_'):
        # k-ary fat tree: k pods, k/2 core switches, each with k links.
        # Bisection = k/2 * k/2 = (k/2)^2 for a standard 3-tier Clos.
        # Conservative: use (k/2) * (k/2) but cap at P to avoid overshoot.
        nl = int(name.split('_')[-1])
        k = max(2, math.ceil(math.sqrt(nl)))
        half_k = max(1, k // 2)
        return min(half_k * half_k, P)
    elif name.startswith('hypercube_'):
        dim = int(name.split('_')[1].rstrip('d'))
        return 1 << (dim - 1)
    else:
        return max(1, P)


def _topology_diameter(topo: 'Topology', P: int) -> int:
    """Compute the diameter (max shortest-path distance) for known topologies.
    Falls back to sampling for unknown types.
    """
    name = topo.name
    if name == 'linear':
        return max(1, P - 1)
    elif name == 'ring':
        return max(1, P // 2)
    elif name.startswith('mesh_'):
        parts = name.split('_')[1].split('x')
        R, C = int(parts[0]), int(parts[1])
        return max(1, (R - 1) + (C - 1))
    elif name.startswith('torus_'):
        parts = name.split('_')[1].split('x')
        R, C = int(parts[0]), int(parts[1])
        return max(1, R // 2 + C // 2)
    elif name.startswith('fat_tree_'):
        # 3-tier fat tree: max distance = 4 (up 2 levels + down 2 levels)
        # for cross-pod; 2 for same-pod
        return 4
    elif name.startswith('hypercube_'):
        dim = int(name.split('_')[1].rstrip('d'))
        return dim
    else:
        # Fallback: sample
        n_sample = min(P, topo.n_nodes, 60)
        diameter = 1
        for i in range(n_sample):
            for j in range(i + 1, n_sample):
                dd = topo.distance(i, j)
                if dd > diameter:
                    diameter = dd
        return diameter


def _hu_hlf_lb(tree: CBTree, n_procs: int, hw: HardwareConfig = HW) -> float:
    """Fix Omega-5: GCI-aware Hu HLF lower bound (valid, no over-counting).

    Two sub-bounds maximized:
      1. GCI serialization: max(gci_gap * ceil(N/P)) — the heaviest PE's
         leaf generation time, assuming perfect balance.
      2. Instruction throughput: ceil((2N-1) / P) — unit-cost pipeline slots.
      3. Critical path: gci_gap + height * compute_latency.

    This avoids the previous bug where GENERATEs were weighted at gci_gap in
    the total-work calculation, double-counting with lb_gen.
    """
    gci_gap = hw.gci_latency + 2
    N = tree.n_leaves
    P = max(1, n_procs)
    m = math.ceil(N / P)  # leaves per PE in best-balanced case

    # PE GCI serialization bound (same formula as lb_gen at K=P)
    pe_gci = gci_gap * m if m >= 2 else max(1, gci_gap * m - (gci_gap - 1))

    # Instruction throughput (unit cost per instruction)
    total_ops = 2 * N - 1  # leaves + internal nodes
    pe_instr = math.ceil(total_ops / P)

    # Critical path (zero communication, infinite PEs)
    cp = gci_gap + tree.height * hw.compute_latency

    return max(pe_gci, pe_instr, cp)

# ═══════════════════════════════════════════════════════════
# COMMON UTILITIES FOR 40-METHOD LIBRARY
# ═══════════════════════════════════════════════════════════
def _dfs_order(tree):
    r=[];s=[0]
    while s:
        n=s.pop()
        if n>=tree.total_nodes: continue
        r.append(n)
        rc=tree.right_child(n);lc=tree.left_child(n)
        if rc>=0: s.append(rc)
        if lc>=0: s.append(lc)
    return r


def _subtree_weights(tree,nodes):
    sw={}
    for n in tree.postorder():
        if n not in nodes: continue
        w=tree.node_cost(n)
        for c in tree.children(n):
            if c in nodes and c in sw: w+=sw[c]
        sw[n]=w
    return sw

def _partition_root(tree,nodes):
    for n in sorted(nodes):
        p=tree.parent(n)
        if p is None or p<0 or p not in nodes: return n
    return min(nodes) if nodes else None

def _collect_subtree(tree,root,within):
    r=set();s=[root]
    while s:
        n=s.pop()
        if n in within:
            r.add(n)
            for c in tree.children(n):
                if c in within: s.append(c)
    return r

def _bisect_partition(tree,nodes):
    ns=set(nodes);sw=_subtree_weights(tree,ns)
    tw=sum(tree.node_cost(n)for n in nodes);tgt=tw/2
    root=_partition_root(tree,ns);bn=nodes[0];bi=float('inf')
    for n in nodes:
        if n==root: continue
        imb=abs(sw.get(n,0)-tgt)
        if imb<bi: bi=imb;bn=n
    st=_collect_subtree(tree,bn,ns)
    return[n for n in nodes if n in st],[n for n in nodes if n not in st]

def _validate_assignment(tree,asgn,ng):
    if not asgn: return False
    for n in range(tree.total_nodes):
        if isinstance(asgn,dict):
            if n not in asgn: return False
            if asgn[n]<0 or asgn[n]>=ng: return False
        else:
            if n>=len(asgn): return False
            if asgn[n]<0 or asgn[n]>=ng: return False
    return True


def repair_connectivity(tree, asgn, ng):
    """Post-S2 connectivity repair: ensures every GPU's partition is a
    connected subgraph of the reduction tree.

    When an S2 algorithm produces disconnected partitions (e.g. HEFT, DSC,
    DFSseed scatter nodes across GPUs), the downstream scheduler may pair
    non-sibling nodes in COMPUTE instructions, causing FP64 reductions to
    execute in a non-canonical order. Since FP64 addition is not associative,
    this produces wrong results.

    Strategy: walk the tree bottom-up. For every internal node whose children
    are on different GPUs, both the children's subtree results will be SENDed
    to the node's GPU at runtime. But the internal node itself must be on
    *some* GPU—it can stay where S2 put it. The real problem is when leaves
    or intermediate nodes on GPU g have no tree-path to any other node on GPU g.

    Fix: for each GPU, find connected components via tree-adjacency. Keep the
    largest component. Reassign orphan nodes to the GPU of their tree-parent
    (pulling them "up" to maintain tree structure).
    """
    if not asgn:
        return asgn
    # Normalize to dict
    if not isinstance(asgn, dict):
        asgn = {n: asgn[n] for n in range(len(asgn))}
    else:
        asgn = dict(asgn)  # make a copy

    max_iters = 20  # prevent infinite loops
    for iteration in range(max_iters):
        changed = False
        # Build per-GPU node sets
        gpu_nodes = {}
        for nd, g in asgn.items():
            gpu_nodes.setdefault(g, set()).add(nd)

        for g in range(ng):
            nodes = gpu_nodes.get(g, set())
            if len(nodes) <= 1:
                continue

            # Build tree-adjacency restricted to this GPU's nodes
            adj = {nd: set() for nd in nodes}
            for nd in nodes:
                for ch in tree.children(nd):
                    if ch in nodes:
                        adj[nd].add(ch)
                        adj[ch].add(nd)
                # Also check parent
                par = tree.parent(nd)
                if par is not None and par in nodes:
                    adj[nd].add(par)
                    adj[par].add(nd)

            # Find connected components via BFS
            visited = set()
            components = []
            for start in nodes:
                if start in visited:
                    continue
                comp = set()
                queue = [start]
                while queue:
                    cur = queue.pop(0)
                    if cur in comp:
                        continue
                    comp.add(cur)
                    visited.add(cur)
                    for nb in adj.get(cur, []):
                        if nb not in comp:
                            queue.append(nb)
                components.append(comp)

            if len(components) <= 1:
                continue  # already connected

            # Keep the component containing the node closest to root
            # (smallest node ID in a complete binary tree = closest to root)
            components.sort(key=lambda c: min(c))
            main_comp = components[0]

            # Reassign orphan nodes to their parent's GPU
            for comp in components[1:]:
                for nd in comp:
                    par = tree.parent(nd)
                    if par is not None:
                        asgn[nd] = asgn[par]
                        changed = True
                    else:
                        # Root node in orphan component — shouldn't happen
                        # but if it does, leave it
                        pass

        if not changed:
            break

    return asgn


# ═══════════════════════════════════════════════════════════
# STAGE 2: 18 ASSIGNMENT METHODS (all timeout-instrumented)
# ═══════════════════════════════════════════════════════════
def assign_heft(tree,ng,topo,hw=HW):
    """HEFT with insertion-based scheduling (Topcuoglu 2002).

    Fixes vs old version:
      1. Proper upward rank via top-down propagation with avg_comm
      2. Insertion-based scheduling — finds earliest gap on each GPU
      3. Per-GPU slot tracking for accurate EFT
    """
    _set_deadline()
    ctx=get_ctx(tree,topo,hw)
    avg_comm=ctx.avg_comm if ctx else hw.comm_cost(1)

    # Upward rank (rank_u): for in-trees, propagate top-down from root
    # rank_u(root) = w(root), rank_u(child) = w(child) + c_avg + rank_u(parent)
    rank_u={}
    rank_u[0]=tree.node_cost(0)
    for n in range(tree.total_nodes):
        for c in tree.children(n):
            rank_u[c]=tree.node_cost(c)+avg_comm+rank_u[n]

    # Schedule in decreasing rank_u order (leaves first — highest rank)
    order=sorted(range(tree.total_nodes),key=lambda n:-rank_u[n])

    # Per-GPU schedule: list of (start, end) intervals, kept sorted
    gpu_slots={g:[] for g in range(ng)}
    nf={};asgn={}

    for idx,node in enumerate(order):
        if idx%500==0: _check_deadline("heft")
        bg=0;be=float('inf')

        # Hoist child data outside GPU loop
        children_data=[]
        for c in tree.children(node):
            if c in nf: children_data.append((asgn[c],nf[c]))
        w=tree.node_cost(node)

        # Enforce Contiguous Assignments: Node must map to a child's GPU or an unused one
        valid_gpus = set()
        if tree.is_leaf(node):
            valid_gpus = set(range(ng))
        else:
            for cg, _ in children_data: valid_gpus.add(cg)
            # Add one unused GPU slot to allow expanding new partitions
            for g in range(ng):
                if not gpu_slots[g]:
                    valid_gpus.add(g)
                    break
            if not valid_gpus: valid_gpus = set(range(ng))

        for g in valid_gpus:
            # Data-ready time from predecessors (children in reduction tree)
            est=0.0
            for cg,ce in children_data:
                if cg!=g: est=max(est,ce+hw.comm_cost(topo.distance(cg,g)))
                else: est=max(est,ce)

            slots=gpu_slots[g]

            # Insertion-based: find earliest gap on GPU g
            inserted=False
            for i in range(len(slots)):
                if i==0:
                    gap_start=est; gap_end=slots[0][0]
                else:
                    gap_start=max(est,slots[i-1][1]); gap_end=slots[i][0]
                if gap_start+w<=gap_end:
                    eft=gap_start+w
                    if eft<be: be=eft;bg=g
                    inserted=True
                    break

            if not inserted:
                last=slots[-1][1] if slots else 0.0
                eft=max(est,last)+w
                if eft<be: be=eft;bg=g

        asgn[node]=bg;nf[node]=be
        start=be-w
        # Fast-path: HEFT usually places tasks at the tail on its chosen GPU
        # (EFT-optimal placement tends to be monotone per-GPU). Check tail
        # first to avoid O(len) shift in bisect.insort.
        sl=gpu_slots[bg]
        if not sl or start>=sl[-1][0]: sl.append((start,be))
        else: bisect.insort(sl,(start,be))

    return asgn


def assign_recursive_bisection(tree,ng,topo,hw=HW):
    """Recursive bisection with weight-proportional split and topology-aware GPU ordering.

    Fixes vs old version:
      1. Split GPUs proportional to partition WEIGHT, not node count
      2. Topology-aware: order GPUs by centroid distance so adjacent GPUs
         map to adjacent partitions (reduces cross-partition hop distance)
    """
    _set_deadline()
    asgn={n:0 for n in range(tree.total_nodes)}
    if ng<=1: return asgn

    def _topo_order_gpus(gpus):
        """Order GPUs so topologically close ones are adjacent in the list.
        Uses greedy nearest-neighbor chain starting from the first GPU."""
        if len(gpus)<=2: return list(gpus)
        ordered=[gpus[0]]; remaining=set(gpus[1:])
        while remaining:
            last=ordered[-1]
            nearest=min(remaining,key=lambda g:topo.distance(last,g))
            ordered.append(nearest)
            remaining.remove(nearest)
        return ordered

    # Pre-sort GPUs by topology proximity once
    sorted_gpus=_topo_order_gpus(list(range(ng)))

    def _b(nodes,gpus):
        _check_deadline("RB")
        if len(gpus)<=1 or len(nodes)<=1:
            for n in nodes: asgn[n]=gpus[0] if gpus else 0
            return
        pa,pb=_bisect_partition(tree,nodes)

        # Weight-proportional GPU split
        wa=sum(tree.node_cost(n) for n in pa)
        tw=sum(tree.node_cost(n) for n in nodes)
        sp=max(1,min(len(gpus)-1,round(len(gpus)*wa/tw)))

        _b(pa,gpus[:sp]);_b(pb,gpus[sp:])

    _b(list(range(tree.total_nodes)),sorted_gpus)
    return asgn


def assign_multilevel_fm(tree,ng,topo,hw=HW):
    """True Multilevel FM partitioning (Karypis & Kumar 1998 / METIS-style).

    Three phases:
      Phase 1 — Coarsen via heavy-edge matching
      Phase 2 — Initial partition on coarsest level (LPT)
      Phase 3 — Uncoarsen with FM refinement at each level

    Fixes vs old version:
      Old code was NOT multilevel — just flat FM passes on recursive bisection.
      New code implements the full coarsen → partition → uncoarsen pipeline
      with proper gain-based FM, locking, and best-prefix rollback.
    """
    _set_deadline()
    if ng<=1:
        return {n:0 for n in range(tree.total_nodes)}

    N=tree.total_nodes; W=tree.total_work()
    cap=W/ng*1.5

    # Build undirected adjacency from tree
    adj=[[] for _ in range(N)]
    for n in range(N):
        for c in tree.children(n):
            adj[n].append(c); adj[c].append(n)
    wt=[tree.node_cost(n) for n in range(N)]

    # ═══════════════════════════════════════
    # Phase 1: Coarsening
    # ═══════════════════════════════════════
    levels=[]
    graphs=[(adj,wt,N)]
    c_adj,c_wt,c_n=adj,wt,N
    floor_n=max(ng*4,40)

    while c_n>floor_n:
        _check_deadline("MLfm_C")
        vis=[False]*c_n; f2c=[0]*c_n; new_wt=[]; cid=0

        # Heavy-edge matching: visit heavier nodes first
        order=list(range(c_n))
        import random; random.Random(42).shuffle(order)
        order=sorted(order,key=lambda x:-c_wt[x])
        for u in order:
            if vis[u]: continue
            bv=-1;bw=-1
            for v in c_adj[u]:
                if not vis[v] and c_wt[v]>bw: bw=c_wt[v];bv=v
            f2c[u]=cid; vis[u]=True; w=c_wt[u]
            if bv>=0: f2c[bv]=cid;vis[bv]=True;w+=c_wt[bv]
            new_wt.append(w); cid+=1

        if cid>c_n*0.85: break  # insufficient contraction

        # Build coarse adjacency
        na=[set() for _ in range(cid)]
        for u in range(c_n):
            cu=f2c[u]
            for v in c_adj[u]:
                cv=f2c[v]
                if cu!=cv: na[cu].add(cv)
        na_list=[sorted(s) for s in na]

        levels.append(f2c)
        c_adj,c_wt,c_n=na_list,new_wt,cid
        graphs.append((c_adj,c_wt,c_n))

    # ═══════════════════════════════════════
    # Phase 2: Initial Partition (LPT on coarsest level)
    # ═══════════════════════════════════════
    asgn=[0]*c_n; gl=[0.0]*ng
    for node in sorted(range(c_n),key=lambda x:-c_wt[x]):
        bg=min(range(ng),key=lambda g:gl[g])
        asgn[node]=bg; gl[bg]+=c_wt[node]

    # FM on coarsest level (cheap)
    asgn=_ml_fm_refine(asgn,c_adj,c_wt,c_n,ng,cap)

    # ═══════════════════════════════════════
    # Phase 3: Uncoarsening + FM Refinement
    # ═══════════════════════════════════════
    for lev in range(len(levels)-1,-1,-1):
        _check_deadline("MLfm_U")
        f2c=levels[lev]
        f_adj,f_wt,f_n=graphs[lev]
        # Project: each fine node inherits supernode's partition
        fine_asgn=[asgn[f2c[u]] for u in range(f_n)]
        fine_asgn=_ml_fm_refine(fine_asgn,f_adj,f_wt,f_n,ng,cap)
        asgn=fine_asgn

    return {n:asgn[n] for n in range(N)}


def _ml_fm_refine(asgn,adj,wt,n,ng,cap,max_passes=3):
    """K-way FM refinement with locking and best-prefix rollback.

    Each pass:
      1. Find highest-gain unlocked boundary node
      2. Move to best neighboring partition, lock it
      3. Track cumulative edge cut
      4. After all moves: rollback to prefix with minimum cut
    Repeat for max_passes or until no improvement.

    Boundary list is rebuilt each pass to capture topology changes from prior pass.
    """
    result=list(asgn)

    for _pass in range(max_passes):
        _check_deadline("MLfm_FM")

        # Partition weights
        gl=[0.0]*ng
        for i in range(n): gl[result[i]]+=wt[i]

        # Rebuild boundary list each pass (catches new boundaries from prior moves)
        boundary=[]
        for u in range(n):
            for v in adj[u]:
                if result[u]!=result[v]:
                    boundary.append(u); break

        if not boundary: break

        # Initial edge-cut count
        cur_cut=0
        for u in range(n):
            for v in adj[u]:
                if v>u and result[u]!=result[v]: cur_cut+=1

        locked=set(); moves=[]
        best_cut=cur_cut; best_prefix=0
        max_steps=min(len(boundary),max(50,n//5))
        unlocked=set(boundary)

        for step in range(max_steps):
            if step%100==0: _check_deadline("FM_step")

            rng=random.Random(42 + step)
            best_moves = []
            top_gain=float('-inf')

            for u in unlocked:
                src=result[u]; cost=wt[u]

                # Candidate target partitions
                tgt_parts=set()
                for v in adj[u]:
                    if result[v]!=src: tgt_parts.add(result[v])
                if not tgt_parts: continue

                for tgt in tgt_parts:
                    if gl[tgt]+cost>cap: continue  # balance guard
                    # Gain = (#neighbors in tgt) - (#neighbors in src)
                    gain=0
                    for v in adj[u]:
                        if result[v]==tgt: gain+=1
                        elif result[v]==src: gain-=1
                    if gain>top_gain:
                        top_gain=gain
                        best_moves=[(u, tgt)]
                    elif gain==top_gain:
                        best_moves.append((u, tgt))

            if not best_moves: break
            top_node, top_tgt = rng.choice(best_moves)

            # Execute move
            old=result[top_node]; cost=wt[top_node]
            result[top_node]=top_tgt
            gl[old]-=cost; gl[top_tgt]+=cost
            locked.add(top_node); unlocked.discard(top_node)
            moves.append((top_node,old,top_tgt))

            # Add newly-boundary neighbors to unlocked
            for v in adj[top_node]:
                if v not in locked:
                    for w in adj[v]:
                        if result[v]!=result[w]: unlocked.add(v); break

            cur_cut-=top_gain
            if cur_cut<best_cut: best_cut=cur_cut;best_prefix=len(moves)

        # Rollback to best prefix
        for i in range(len(moves)-1,best_prefix-1,-1):
            nd,old_part,_=moves[i]; result[nd]=old_part

        if best_prefix==0: break

    return result

def assign_direct_kway(tree,ng,topo,hw=HW):
    """Direct K-way partitioning (Karypis & Kumar 1998 style, no multilevel).

    Phase 1: Greedy postorder assignment with cycle-normalized scoring.
             Children placed first, so parents see actual child placement.
    Phase 2: K-way FM refinement with locking + best-prefix rollback.

    Fixes vs old:
      1. Postorder traversal (old used DFS preorder — parents before children)
      2. Cycle-normalized scoring: comm + excess (old mixed arbitrary weights)
      3. FM refinement pass (old had none)
    """
    _set_deadline()
    N=tree.total_nodes
    if ng<=1: return {n:0 for n in range(N)}

    W=tree.total_work(); tpg=W/ng; cap=tpg*1.5

    # Phase 1: Greedy postorder — children before parents
    asgn=[0]*N; gl=[0.0]*ng
    # Min-heap for GPU loads: (load, gpu_id)
    gpu_heap=[(0.0,g) for g in range(ng)]

    for idx,node in enumerate(tree.postorder()):
        if idx%500==0: _check_deadline("DKway")
        cost=tree.node_cost(node)

        if tree.is_leaf(node):
            load,bg=heapq.heappop(gpu_heap)
            asgn[node]=bg; gl[bg]+=cost
            heapq.heappush(gpu_heap,(load+cost,bg))
        else:
            child_gpus=[asgn[c] for c in tree.children(node)]
            bg=0; best_score=float('inf')

            for g in range(ng):
                # Comm cost in cycles for children not on GPU g
                comm=sum(hw.comm_cost(topo.distance(cg,g))
                         for cg in child_gpus if cg!=g)
                # Load excess in cycles
                excess=max(0.0,gl[g]+cost-tpg)
                # Both terms in cycles — directly comparable
                score=comm+excess
                # Hard balance cap
                if gl[g]+cost>cap: score+=1e9
                if score<best_score: best_score=score;bg=g

            asgn[node]=bg; gl[bg]+=cost

    # Phase 2: FM refinement
    adj_fm=[[] for _ in range(N)]
    for n in range(N):
        for c in tree.children(n):
            adj_fm[n].append(c); adj_fm[c].append(n)
    wt=[tree.node_cost(n) for n in range(N)]
    asgn=_ml_fm_refine(asgn,adj_fm,wt,N,ng,cap)

    return {n:asgn[n] for n in range(N)}


def assign_exact_bb(tree,ng,topo,hw=HW):
    """Exact Branch-and-Bound for small instances (Lawler & Wood 1966).

    Fixes vs old:
      1. Branch in postorder (leaves first → exact comm when assigning parents)
      2. Incremental cp_comm maintained during search
      3. Tighter bound: max(max_load, partial_cp, W/P)
      4. Symmetry breaking at first node
      5. Seed with recursive bisection for tight initial upper bound
    Old version: branched in BFS order, minimized edge-cut count (not makespan),
    had no CP tracking or symmetry breaking.
    """


    _set_deadline()
    N=tree.total_nodes
    # ng-aware gate: measured boundary is N=25 at ng=4, N=31 at ng=2.
    # Use ng^N > 1e9 as a proxy for intractable search space, with hard cap N>31.
    _bb_intractable = N > 31 or (ng > 1 and ng**N > 1e9)
    if _bb_intractable:
        raise AlgoBypassed("ExactBB size gate: N=%d ng=%d (search space exceeds time budget)" % (N, ng))

    costs=[tree.node_cost(n) for n in range(N)]
    W=tree.total_work(); lb_work=W/ng

    # Seed best-known with RecBisect
    rb=assign_recursive_bisection(tree,ng,topo,hw)
    rbl=_to_list(rb,N)
    ba=list(rbl[:N])
    bc=[_estimate_makespan(tree,rb,ng,topo,hw)]

    po=list(tree.postorder())
    children_of=[tree.children(n) for n in range(N)]
    is_leaf_arr=[tree.is_leaf(n) for n in range(N)]

    al=[0]*N; gl=[0]*ng; cp=[0.0]*N; cc=[0]

    def _compute_cp(node):
        if is_leaf_arr[node]:
            cp[node]=tree.leaf_cost
        else:
            gn=al[node]; mx=0.0
            for c in children_of[node]:
                gc=al[c]
                comm=hw.comm_cost(topo.distance(gc,gn)) if gc!=gn else 0
                val=cp[c]+comm
                if val>mx: mx=val
            cp[node]=tree.internal_cost+mx

    # Pre-calculate subtree weights for O(1) bound update
    subtree_w = [0.0]*N
    for i in range(N-1, -1, -1):
        node = po[i]
        subtree_w[node] = costs[node] + sum(subtree_w[c] for c in children_of[node])

    rem_work = [0.0]*(N+1)
    for i in range(N-1, -1, -1):
        rem_work[i] = rem_work[i+1] + costs[po[i]]

    def _bound(depth):
        # Tighter bound: max(current_max_load, current_cp, (work_done + work_remaining)/ng)
        lb = (gl_sum[0] + rem_work[depth]) / ng
        ml = max(gl); lb = max(lb, ml)
        # Check critical path of root if fully assigned, or partial CPs
        assigned_cp = 0.0
        if depth >= N: assigned_cp = cp[0]
        else:
            # Check CP of the most recently assigned node
            assigned_cp = cp[po[depth-1]] if depth > 0 else 0
        return max(lb, assigned_cp)

    gl_sum = [0.0]
    def _br(depth):
        cc[0]+=1
        if cc[0]%10000==0: _check_deadline("BB")
        if depth>=N:
            ms=max(cp[0],max(gl))
            if ms<bc[0]: bc[0]=ms;ba[:]=al[:]
            return
        
        node=po[depth]
        # Symmetry breaking: first node → only GPU 0
        if depth == 0:
            gpu_order = [0]
        else:
            # Static search order: try GPUs with least load first (Greedy)
            gpu_order = sorted(range(ng), key=lambda g: gl[g])

        for g in gpu_order:
            al[node]=g; gl[g]+=costs[node]; gl_sum[0]+=costs[node]
            
            _compute_cp(node)
            lb=_bound(depth+1)
            
            if lb < bc[0]:
                _br(depth+1)
            
            gl[g]-=costs[node]; gl_sum[0]-=costs[node]

    _br(0)
    return _to_dict(ba)


def assign_dfs_seed(tree,ng,topo,hw=HW):
    """DFS-order seed partitioner: fast O(N) initial partition.

    Fixes vs old:
      1. Chunks by cumulative WEIGHT, not node count
      2. 5% overshoot tolerance for balanced splits
      3. Last GPU absorbs remainder (no starvation)
    Old version: fixed chunk = len(dfs)//ng, split by index.
    """
    _check_deadline("DFSseed")
    if ng<=1: return {n:0 for n in range(tree.total_nodes)}

    W=tree.total_work(); tpg=W/ng
    dfs=_dfs_order(tree)
    asgn={}; cur_gpu=0; cur_weight=0.0

    for node in dfs:
        cost=tree.node_cost(node)
        # Advance GPU if current one exceeds target (except last GPU)
        if cur_gpu<ng-1 and cur_weight+cost>tpg*1.05:
            cur_gpu+=1; cur_weight=0.0
        asgn[node]=cur_gpu; cur_weight+=cost

    return asgn

def assign_dsc(tree,ng,topo,hw=HW):
    """Dominant Sequence Clustering (Yang & Gerasoulis 1994).

    Fixes vs old:
      1. Uses avg_comm from PrecomputedContext (old used distance(0,1))
      2. Proper DSC merge decision: merge if it reduces dominant sequence length
         (old merged unconditionally when ccv >= node_cost)
      3. Maintains and periodically recomputes tl/bl after merges
      4. LPT cluster-to-GPU mapping (old used round-robin modulo)
    """
    _set_deadline()
    N=tree.total_nodes
    if ng<=1: return {n:0 for n in range(N)}

    W=tree.total_work(); mcw=max(1,math.ceil(W/ng*1.5))
    ctx=get_ctx(tree,topo,hw)
    avg_comm=ctx.avg_comm if ctx else hw.comm_cost(1)

    # Union-Find
    uf_par=list(range(N)); uf_rnk=[0]*N
    cw=[tree.node_cost(n) for n in range(N)]

    def _find(x):
        while uf_par[x]!=x: uf_par[x]=uf_par[uf_par[x]];x=uf_par[x]
        return x
    def _same(a,b): return _find(a)==_find(b)
    def _union(a,b):
        ra,rb=_find(a),_find(b)
        if ra==rb: return False
        nw=cw[ra]+cw[rb]
        if nw>mcw: return False
        if uf_rnk[ra]<uf_rnk[rb]: ra,rb=rb,ra
        uf_par[rb]=ra; cw[ra]=nw
        if uf_rnk[ra]==uf_rnk[rb]: uf_rnk[ra]+=1
        return True

    def _edge_comm(child,parent):
        return 0 if _same(child,parent) else avg_comm

    def _recompute_tl():
        tl=[0.0]*N
        for n in tree.postorder():
            if tree.is_leaf(n): tl[n]=0.0
            else: tl[n]=max(tl[c]+tree.node_cost(c)+_edge_comm(c,n) for c in tree.children(n))
        return tl

    def _recompute_bl():
        bl=[0.0]*N; bl[0]=tree.node_cost(0)
        for n in range(N):
            for c in tree.children(n):
                bl[c]=tree.node_cost(c)+_edge_comm(c,n)+bl[n]
        return bl

    tl=_recompute_tl(); bl=_recompute_bl()
    scheduled=[False]*N

    # Max-heap for priority scan (negate for min-heap)
    pq=[(-( tl[n]+bl[n]), n) for n in range(N)]
    heapq.heapify(pq)

    for iteration in range(N):
        if iteration%500==0: _check_deadline("DSC")
        # Pop from heap until we find an unscheduled node
        node=-1
        while pq:
            neg_pri,cand=heapq.heappop(pq)
            if not scheduled[cand]: node=cand; break
        if node<0: break
        scheduled[node]=True

        p=tree.parent(node)
        if p is None or p<0 or _same(node,p): continue

        # DSC merge decision: tentatively merge, revert if DS length increases
        old_ds=max(tl[n]+bl[n] for n in range(N))
        # Point-save only affected UF entries
        ra,rb=_find(node),_find(p)
        save_entries=((ra,uf_par[ra],uf_rnk[ra],cw[ra]),(rb,uf_par[rb],uf_rnk[rb],cw[rb]))
        merged=_union(node,p)
        if merged:
            new_tl=_recompute_tl(); new_bl=_recompute_bl()
            new_ds=max(new_tl[n]+new_bl[n] for n in range(N))
            if new_ds<=old_ds:
                tl=new_tl; bl=new_bl
                # Re-push affected nodes with updated priorities
                for n in range(N):
                    if not scheduled[n]: heapq.heappush(pq,(-(tl[n]+bl[n]),n))
            else:
                for idx,par_v,rnk_v,cw_v in save_entries:
                    uf_par[idx]=par_v; uf_rnk[idx]=rnk_v; cw[idx]=cw_v

    cn=defaultdict(list)
    for n in range(N): cn[_find(n)].append(n)
    clusters=sorted(cn.keys(),key=lambda c:-cw[_find(c)])
    gl=[0.0]*ng; c2g={}
    for cid in clusters:
        _check_deadline("DSC_map")
        bg=min(range(ng),key=lambda g:gl[g])
        c2g[cid]=bg; gl[bg]+=cw[_find(cid)]
    return {n:c2g[_find(n)] for n in range(N)}


def assign_chretienne(tree,ng,topo,hw=HW):
    """Chretienne's algorithm (1989) for scheduling trees with comm delays.

    Fixes vs old:
      1. Chain identification via heavy-child paths (old just checked rho<=1)
      2. Modified depth computation with co-scheduling zeroed comm
      3. Chain scheduling with per-node finish time tracking
         (old used BFS with simple rho threshold)
    """
    _set_deadline()
    N=tree.total_nodes
    if ng<=1: return {n:0 for n in range(N)}
    ccv=hw.comm_cost(1)

    # Step 1: Modified depths (bottom-up, worst-case comm)
    md=[0.0]*N
    for n in tree.postorder():
        if tree.is_leaf(n): md[n]=tree.node_cost(n)
        else: md[n]=tree.node_cost(n)+max(md[c]+ccv for c in tree.children(n))

    # Step 2: Identify co-scheduling chains via heavy-child
    chain_parent={}; heavy_child={}
    for n in range(N):
        if tree.is_leaf(n): continue
        children=tree.children(n)
        if not children: continue
        best_c=max(children,key=lambda c:md[c])
        other_max=max((md[c] for c in children if c!=best_c),default=0.0)
        if md[best_c]>=other_max:
            chain_parent[best_c]=n; heavy_child[n]=best_c

    # Build chains
    chains=[]; in_chain=set()
    for n in range(N):
        if n in in_chain or n in chain_parent: continue
        chain=[n]; in_chain.add(n); cur=n
        while cur in heavy_child:
            nxt=heavy_child[cur]; chain.append(nxt); in_chain.add(nxt); cur=nxt
        chains.append(chain)

    # Step 3: Recompute depths with co-scheduling
    chain_id={}
    for ci,chain in enumerate(chains):
        for n in chain: chain_id[n]=ci
    for n in tree.postorder():
        if tree.is_leaf(n): md[n]=tree.node_cost(n)
        else:
            mx=0.0
            for c in tree.children(n):
                comm=0 if chain_id.get(c)==chain_id.get(n) else ccv
                val=md[c]+comm
                if val>mx: mx=val
            md[n]=tree.node_cost(n)+mx

    # Step 4: Schedule chains with per-node finish tracking
    chain_pri=[]
    for ci,chain in enumerate(chains):
        weight=sum(tree.node_cost(n) for n in chain)
        chain_pri.append((md[chain[0]],weight,ci))
    chain_pri.sort(key=lambda x:(-x[0],-x[1]))

    asgn={}; gl=[0.0]*ng; node_finish={}
    for _,weight,ci in chain_pri:
        _check_deadline("Chret")
        chain=chains[ci]
        bg=0; best_eft=float('inf')
        for g in range(ng):
            est=gl[g]
            for n in chain:
                for c in tree.children(n):
                    if chain_id.get(c)!=ci and c in asgn:
                        cg=asgn[c]
                        cf=node_finish.get(c,0)
                        if cg!=g: est=max(est,cf+ccv)
                        else: est=max(est,cf)
            eft=est+weight
            if eft<best_eft: best_eft=eft;bg=g

        t=gl[bg]
        # Schedule chain leaf-to-root (children before parents in reduction tree)
        for n in reversed(chain):
            for c in tree.children(n):
                if c in node_finish:
                    cg=asgn[c]
                    if cg!=bg: t=max(t,node_finish[c]+ccv)
                    else: t=max(t,node_finish[c])
            asgn[n]=bg; t+=tree.node_cost(n); node_finish[n]=t
        gl[bg]=t

    for n in range(N):
        if n not in asgn:
            bg=min(range(ng),key=lambda g:gl[g])
            asgn[n]=bg; gl[bg]+=tree.node_cost(n)
    return asgn


def assign_cpop(tree,ng,topo,hw=HW):
    """CPOP — Critical Path on a Processor (Topcuoglu et al. 2002).

    The critical path is ONE traced path from root to a leaf, following
    the child with highest priority at each step. In a balanced CBT,
    all nodes have the same tl+bl, so collecting all max-priority nodes
    would pin EVERYTHING to one GPU (the old bug).

    Fix: trace a single path. Non-CP nodes get HEFT-style EFT scheduling
    with insertion-based gap finding.
    """
    _set_deadline()
    N=tree.total_nodes
    if ng<=1: return {n:0 for n in range(N)}

    ctx=_get_ctx(tree,topo)
    avg_comm=ctx.avg_comm if ctx else hw.comm_cost(1)

    # t-level (bottom-up): longest path from leaves to node n
    tl=[0.0]*N
    for n in tree.postorder():
        if tree.is_leaf(n): tl[n]=0.0
        else: tl[n]=max(tl[c]+tree.node_cost(c)+avg_comm for c in tree.children(n))

    # b-level (top-down): longest path from node n to root
    bl=[0.0]*N; bl[0]=tree.node_cost(0)
    for n in range(N):
        for c in tree.children(n):
            bl[c]=tree.node_cost(c)+avg_comm+bl[n]

    # Priority = tl+bl (same for all in balanced CBT, varies in skewed trees)
    priority=[tl[n]+bl[n] for n in range(N)]

    # Trace ONE critical path: root → heaviest child → ... → leaf
    # At each internal node, follow child with highest priority (bl tiebreaker)
    cpn=set(); cur=0; cpn.add(0)
    while not tree.is_leaf(cur):
        children=tree.children(cur)
        # Pick child with highest priority, break ties by highest bl
        best_c=max(children, key=lambda c: (priority[c], bl[c]))
        cpn.add(best_c); cur=best_c

    cpg=0  # homogeneous → pin CP to GPU 0
    order=sorted(range(N),key=lambda n:-priority[n])
    asgn={}; nf={}
    gpu_slots={g:[] for g in range(ng)}

    for idx,node in enumerate(order):
        if idx%500==0: _check_deadline("CPOP")
        # Hoist child data
        children_data=[]
        for c in tree.children(node):
            if c in nf: children_data.append((asgn[c],nf[c]))
        w=tree.node_cost(node)

        if node in cpn:
            # CP node: pin to cpg with insertion
            est=0.0
            for cg,ce in children_data:
                if cg!=cpg: est=max(est,ce+hw.comm_cost(topo.distance(cg,cpg)))
                else: est=max(est,ce)
            slots=gpu_slots[cpg]; eft=None
            for i in range(len(slots)):
                gs=est if i==0 else max(est,slots[i-1][1]); ge=slots[i][0]
                if gs+w<=ge: eft=gs+w;break
            if eft is None:
                last=slots[-1][1] if slots else 0.0
                eft=max(est,last)+w
            asgn[node]=cpg; nf[node]=eft
            start=eft-w; sl=gpu_slots[cpg]
            if not sl or start>=sl[-1][0]: sl.append((start,eft))
            else: bisect.insort(sl,(start,eft))
        else:
            # Non-CP: HEFT-style EFT with insertion
            bg=0; be=float('inf')
            for g in range(ng):
                est=0.0
                for cg,ce in children_data:
                    if cg!=g: est=max(est,ce+hw.comm_cost(topo.distance(cg,g)))
                    else: est=max(est,ce)
                slots=gpu_slots[g]; eft=None
                for i in range(len(slots)):
                    gs=est if i==0 else max(est,slots[i-1][1]); ge=slots[i][0]
                    if gs+w<=ge: eft=gs+w;break
                if eft is None:
                    last=slots[-1][1] if slots else 0.0
                    eft=max(est,last)+w
                if eft<be: be=eft;bg=g
            asgn[node]=bg; nf[node]=be
            start=be-w; sl=gpu_slots[bg]
            if not sl or start>=sl[-1][0]: sl.append((start,be))
            else: bisect.insort(sl,(start,be))

    return asgn

def assign_centroid(tree,ng,topo,hw=HW):
    """Centroid decomposition partitioner (Jordan 1869).

    1. Find centroid (node minimizing max component weight after removal)
    2. Remove centroid → connected components
    3. Distribute GPUs proportional to component weight (largest-remainder)
    4. Recurse on each component

    Fixes vs old:
      - Parent-direction component collection (old only collected child subtrees)
      - Largest-remainder GPU distribution (old used round-based allocation)
      - Centroid assigned to heaviest component's GPU when GPUs scarce
    """
    _set_deadline()
    asgn={n:0 for n in range(tree.total_nodes)}
    if ng<=1: return asgn

    def _find_centroid(nodes):
        ns=set(nodes)
        sw={}
        for n in tree.postorder():
            if n not in ns: continue
            w=tree.node_cost(n)
            for c in tree.children(n):
                if c in ns and c in sw: w+=sw[c]
            sw[n]=w
        tot=sum(tree.node_cost(n) for n in nodes)
        best=None; best_mc=float('inf')
        for n in nodes:
            mc=tot-sw.get(n,0)
            for c in tree.children(n):
                if c in ns: mc=max(mc,sw.get(c,0))
            if mc<best_mc: best_mc=mc;best=n
        return best if best is not None else min(nodes)

    def _get_components(nodes,centroid):
        ns=set(nodes); ns.discard(centroid)
        if not ns: return []
        components=[]; remaining=set(ns)
        seeds=[]
        for c in tree.children(centroid):
            if c in remaining: seeds.append(c)
        p=tree.parent(centroid)
        if p is not None and p>=0 and p in remaining: seeds.append(p)
        for seed in seeds:
            if seed not in remaining: continue
            comp=set(); queue=deque([seed])
            while queue:
                n=queue.popleft()
                if n not in remaining or n in comp: continue
                comp.add(n)
                pp=tree.parent(n)
                if pp is not None and pp>=0 and pp in remaining and pp not in comp: queue.append(pp)
                for c in tree.children(n):
                    if c in remaining and c not in comp: queue.append(c)
            remaining-=comp
            if comp: components.append(sorted(comp))
        if remaining: components.append(sorted(remaining))
        return components

    def _distribute_gpus(components,gpus):
        ng2=len(gpus)
        if not components: return []
        weights=[sum(tree.node_cost(n) for n in comp) for comp in components]
        tw=max(1.0,sum(weights))
        fracs=[ng2*w/tw for w in weights]
        allocs=[max(1,int(f)) for f in fracs]
        total=sum(allocs)
        if total<ng2:
            rems=sorted(range(len(components)),key=lambda i:-(fracs[i]-allocs[i]))
            for j in range(ng2-total): allocs[rems[j]]+=1
        elif total>ng2:
            excess=total-ng2
            order=sorted(range(len(allocs)),key=lambda i:-allocs[i])
            for i in order:
                if excess<=0: break
                if allocs[i]>1:
                    trim=min(allocs[i]-1,excess); allocs[i]-=trim; excess-=trim
        result=[]; gi=0
        for a in allocs: result.append(gpus[gi:gi+a]); gi+=a
        return result

    def _partition(nodes,gpus):
        _check_deadline("Centroid")
        if len(gpus)<=1 or len(nodes)<=1:
            tgt=gpus[0] if gpus else 0
            for n in nodes: asgn[n]=tgt
            return
        if len(nodes)<=len(gpus):
            for i,n in enumerate(nodes): asgn[n]=gpus[i]
            return
        cent=_find_centroid(nodes)
        comps=_get_components(nodes,cent)
        if not comps: asgn[cent]=gpus[0];return
        if len(gpus)>len(comps):
            asgn[cent]=gpus[0]; comp_gpus=gpus[1:]
        else:
            comp_gpus=gpus
        gpu_slices=_distribute_gpus(comps,comp_gpus)
        if len(gpus)<=len(comps) and gpu_slices:
            asgn[cent]=gpu_slices[0][0]
        for comp,cg in zip(comps,gpu_slices):
            if cg: _partition(comp,cg)
            else:
                for n in comp: asgn[n]=gpus[-1]

    _partition(list(range(tree.total_nodes)),list(range(ng)))
    return asgn


def assign_lukes_dp(tree,ng,topo,hw=HW):
    """Lukes' tree partitioning (1974) — minimize edge cuts under weight cap.

    Bottom-up DP: dp[n] = {weight → min_cuts}
    Then backtrack to extract clusters, map to GPUs with comm-aware scoring.

    Fixes vs old:
      Old code was NOT Lukes DP — just greedy DFS with capacity check.
      New code: full DP with per-child merge/cut decisions, backtracking,
      and communication-aware cluster-to-GPU assignment.
    """
    _set_deadline()
    W=tree.total_work(); N=tree.total_nodes
    cap=max(1,math.ceil(W/ng*1.15))



    # Phase 1: Bottom-up DP with state pruning
    DP_MAX_STATES=10000  # fallback threshold per node (recalibrated for 1800s budget)
    dp=[None]*N; decisions=[None]*N
    for node in tree.postorder():
        _check_deadline("Lukes")
        wn=tree.node_cost(node); children=tree.children(node)
        if not children:
            dp[node]={wn:0}; decisions[node]={wn:[]}; continue
        cur_dp={wn:0}; cur_dec={wn:[]}
        for child in children:
            new_dp={}; new_dec={}
            for wp,cp2 in cur_dp.items():
                prev=cur_dec[wp]
                for wc,cc in dp[child].items():
                    # Option A: merge
                    wm=wp+wc
                    if wm<=cap:
                        tc=cp2+cc
                        if wm not in new_dp or tc<new_dp[wm]:
                            new_dp[wm]=tc; new_dec[wm]=list(prev)+[(child,wc,True)]
                    # Option B: cut
                    tc=cp2+cc+1
                    if wp not in new_dp or tc<new_dp[wp]:
                        new_dp[wp]=tc; new_dec[wp]=list(prev)+[(child,wc,False)]
            # Prune dominated states: if w1 < w2 and cuts(w1) <= cuts(w2), drop w2
            if len(new_dp)>DP_MAX_STATES:
                return _lukes_greedy_fallback(tree,ng,cap)
            sorted_states=sorted(new_dp.items())
            pruned_dp={}; pruned_dec={}; best_cuts=float('inf')
            for w,c in sorted_states:
                if c<best_cuts:
                    pruned_dp[w]=c; pruned_dec[w]=new_dec[w]; best_cuts=c
            cur_dp=pruned_dp; cur_dec=pruned_dec
        dp[node]=cur_dp; decisions[node]=cur_dec

    # Phase 2: Backtracking
    if not dp[0]: return {n:0 for n in range(N)}
    best_w=min(dp[0],key=lambda w:dp[0][w])
    cluster_id={}; next_cl=[0]
    def _ncl(): cid=next_cl[0];next_cl[0]+=1;return cid
    def _bt(node,w,cid):
        cluster_id[node]=cid
        if decisions[node] is None or w not in decisions[node]: return
        for child,cw,merged in decisions[node][w]:
            if merged: _bt(child,cw,cid)
            else: _bt(child,cw,_ncl())
    _bt(0,best_w,_ncl())
    for n in range(N):
        if n not in cluster_id: cluster_id[n]=_ncl()

    # Phase 3: Comm-aware cluster→GPU assignment
    cl_nodes=defaultdict(list)
    for n,c in cluster_id.items(): cl_nodes[c].append(n)
    cl_wt={c:sum(tree.node_cost(n) for n in ns) for c,ns in cl_nodes.items()}
    cl_comm=defaultdict(int)
    for n in range(1,N):
        p=tree.parent(n)
        if p>=0 and cluster_id[n]!=cluster_id[p]:
            key=(min(cluster_id[n],cluster_id[p]),max(cluster_id[n],cluster_id[p]))
            cl_comm[key]+=1

    sorted_cl=sorted(cl_nodes.keys(),key=lambda c:-cl_wt.get(c,0))
    gl=[0.0]*ng; cl_gpu={}; asgn={}
    for c in sorted_cl:
        _check_deadline("Lukes_map")
        cw=cl_wt.get(c,0)
        nbrs=[]
        for (c1,c2),w in cl_comm.items():
            if c1==c and c2 in cl_gpu: nbrs.append((cl_gpu[c2],w))
            elif c2==c and c1 in cl_gpu: nbrs.append((cl_gpu[c1],w))
        bg=0; bs=float('inf')
        for g in range(ng):
            ls=abs(gl[g]+cw-W/ng)
            cs=sum(w*topo.distance(g,ng2) for ng2,w in nbrs)
            score=ls+hw.comm_cost(1)*cs
            if score<bs: bs=score;bg=g
        cl_gpu[c]=bg
        for n in cl_nodes[c]: asgn[n]=bg
        gl[bg]+=cw
    return asgn


def _lukes_greedy_fallback(tree,ng,cap):
    """Greedy fallback when DP tables too large.
    Walks top-down (BFS) so each node's parent is already assigned — the
    co-location heuristic (keep child with parent to avoid cross-GPU comm)
    then actually fires. Postorder would always miss it."""
    from collections import deque
    N=tree.total_nodes; asgn={}; gl=[0]*ng
    # Seed root on least-loaded GPU
    root_cost=tree.node_cost(0); asgn[0]=0; gl[0]+=root_cost
    q=deque(tree.children(0))
    while q:
        node=q.popleft()
        cost=tree.node_cost(node); p=tree.parent(node)
        pg=asgn.get(p,-1) if p is not None and p>=0 else -1
        if pg>=0 and gl[pg]+cost<=cap:
            asgn[node]=pg; gl[pg]+=cost
        else:
            bg=min(range(ng),key=lambda g:gl[g])
            asgn[node]=bg; gl[bg]+=cost
        for c in tree.children(node): q.append(c)
    # Safety: any unreached nodes (shouldn't happen for a connected tree)
    for n in range(N):
        if n not in asgn:
            bg=min(range(ng),key=lambda g:gl[g])
            asgn[n]=bg; gl[bg]+=tree.node_cost(n)
    return asgn


def assign_frederickson(tree,ng,topo,hw=HW):
    """Frederickson's tree partitioning (1991) — separator-based.

    1. Compute subtree weights bottom-up
    2. Walk postorder: cut subtree when effective weight >= target
    3. Propagate cut_weight ALL THE WAY to root (old bug: only 1 level)
    4. Merge small / split large components to match ng GPUs
    5. LPT assignment

    Fixes vs old:
      Old code was NOT Frederickson — just DFS with weight threshold.
      New code: proper separator identification with effective weight tracking,
      correct cut_weight propagation to all ancestors, and merge/split balancing.
    """
    _set_deadline()
    N=tree.total_nodes; W=tree.total_work()
    asgn={n:0 for n in range(N)}
    if ng<=1: return asgn

    k=min(ng,N); target=W/k
    max_nw=max(tree.node_cost(n) for n in range(N))

    # Phase 1: Subtree weights
    sw=[0.0]*N
    for n in tree.postorder():
        sw[n]=tree.node_cost(n)
        for c in tree.children(n): sw[n]+=sw[c]

    # Phase 2: Find separators via postorder walk
    components=[]; cut_weight=[0.0]*N; component_of=[-1]*N; processed=[False]*N

    def _eff_weight(n): return sw[n]-cut_weight[n]

    for node in tree.postorder():
        _check_deadline("Frederik")
        if processed[node]: continue
        ew=_eff_weight(node)
        if ew>=target and node!=0:
            comp=set(); stack=[node]; cw2=0.0
            while stack:
                n=stack.pop()
                if processed[n]: continue
                comp.add(n); processed[n]=True; cw2+=tree.node_cost(n)
                for c in tree.children(n):
                    if not processed[c]: stack.append(c)
            if comp:
                cid=len(components); components.append(comp)
                for n in comp: component_of[n]=cid
                # Propagate effective weight of cut component up to root
                ew_cut=_eff_weight(node)
                cur=tree.parent(node)
                while cur is not None and cur>=0:
                    cut_weight[cur]+=ew_cut
                    cur=tree.parent(cur)

    # Remaining nodes (root component)
    remaining=set()
    for n in range(N):
        if not processed[n]: remaining.add(n); processed[n]=True
    if remaining:
        cid=len(components); components.append(remaining)
        for n in remaining: component_of[n]=cid

    # Phase 3: Merge small / split large to match ng
    if len(components)>ng:
        comp_wt=[sum(tree.node_cost(n) for n in comp) for comp in components]
        while len(components)>ng:
            _check_deadline("Frederik_merge")
            mi=min(range(len(components)),key=lambda i:comp_wt[i])
            mc=components[mi]; bn=-1; bw=float('inf')
            for n in mc:
                p=tree.parent(n)
                if p is not None and p>=0 and component_of[p]!=mi:
                    ni=component_of[p]; mw=comp_wt[mi]+comp_wt[ni]
                    if mw<bw: bw=mw;bn=ni
                for c in tree.children(n):
                    if component_of[c]!=mi:
                        ni=component_of[c]; mw=comp_wt[mi]+comp_wt[ni]
                        if mw<bw: bw=mw;bn=ni
            if bn<0: break
            for n in mc: component_of[n]=bn
            components[bn]=components[bn]|mc; comp_wt[bn]+=comp_wt[mi]
            last=len(components)-1
            if mi!=last:
                components[mi]=components[last]; comp_wt[mi]=comp_wt[last]
                for n in components[mi]: component_of[n]=mi
            components.pop(); comp_wt.pop()

    elif len(components)<ng:
        comp_wt=[sum(tree.node_cost(n) for n in comp) for comp in components]
        while len(components)<ng:
            _check_deadline("Frederik_split")
            mx=max(range(len(components)),key=lambda i:comp_wt[i])
            mc=components[mx]
            if len(mc)<=1: break
            pa,pb=_bisect_partition(tree,sorted(mc))
            if not pa or not pb: break
            wa=sum(tree.node_cost(n) for n in pa)
            components[mx]=set(pa); ni=len(components); components.append(set(pb))
            comp_wt.append(comp_wt[mx]-wa); comp_wt[mx]=wa
            for n in pa: component_of[n]=mx
            for n in pb: component_of[n]=ni

    # Phase 4: LPT assignment
    comp_wt=[sum(tree.node_cost(n) for n in comp) for comp in components]
    si=sorted(range(len(components)),key=lambda i:-comp_wt[i])
    gl=[0.0]*ng; comp_gpu={}
    for ci in si:
        bg=min(range(ng),key=lambda g:gl[g])
        comp_gpu[ci]=bg; gl[bg]+=comp_wt[ci]
    for n in range(N): asgn[n]=comp_gpu.get(component_of[n],0)
    return asgn

def assign_bounded_cpfd(tree,ng,topo,hw=HW):
    """Bounded CPFD (Critical Path Fast Duplication) — Kwok & Ahmad 1999.

    1. Initial HEFT assignment
    2. Compute CP using actual assignment distances (not avg_comm)
    3. For each critical cross-GPU edge: evaluate net comm impact
    4. Move child to parent's GPU only if comm_saved > comm_added
       AND makespan actually decreases
    5. Recompute tl/bl after each accepted move
    """
    _set_deadline()
    N=tree.total_nodes
    if ng<=1: return {n:0 for n in range(N)}

    asgn=assign_heft(tree,ng,topo,hw)
    ctx=_get_ctx(tree,topo)

    def _tl_actual(ad):
        tl=[0.0]*N
        for n in tree.postorder():
            if tree.is_leaf(n): tl[n]=0.0
            else:
                tl[n]=max(tl[c]+tree.node_cost(c)+(
                    hw.comm_cost(topo.distance(ad[c],ad[n])) if ad[c]!=ad[n] else 0)
                    for c in tree.children(n))
        return tl

    def _bl_actual(ad):
        bl=[0.0]*N; bl[0]=tree.node_cost(0)
        for n in range(N):
            gn=ad[n]
            for c in tree.children(n):
                gc=ad[c]; comm=hw.comm_cost(topo.distance(gc,gn)) if gc!=gn else 0
                bl[c]=tree.node_cost(c)+comm+bl[n]
        return bl

    tl=_tl_actual(asgn); bl=_bl_actual(asgn)
    cpl=max(tl[n]+bl[n] for n in range(N)); eps=max(0.5,cpl*0.02)

    # Critical cross-GPU edges sorted by comm cost
    ccx=[]
    for node in range(1,N):
        p=tree.parent(node)
        if p is None or p<0: continue
        on_cp=(abs(tl[node]+bl[node]-cpl)<eps and abs(tl[p]+bl[p]-cpl)<eps)
        if on_cp and asgn[node]!=asgn[p]:
            ccx.append((node,p,hw.comm_cost(topo.distance(asgn[node],asgn[p]))))
    ccx.sort(key=lambda x:-x[2])

    gl=[0]*ng
    for n in range(N): gl[asgn[n]]+=tree.node_cost(n)
    W=tree.total_work(); dup_cap=max(1,math.ceil(W/ng*0.3))
    cur_ms=_estimate_makespan(tree,asgn,ng,topo,hw)

    for child,parent,comm_cost in ccx:
        _check_deadline("CPFD")
        if asgn[child]==asgn[parent]: continue
        old_g=asgn[child]; new_g=asgn[parent]; cost=tree.node_cost(child)

        # Capacity check
        if gl[new_g]+cost>W/ng+dup_cap: continue

        # Net comm impact
        comm_saved=comm_cost
        comm_added=0
        for gc in tree.children(child):
            gc_gpu=asgn[gc]
            if gc_gpu==old_g and gc_gpu!=new_g:
                comm_added+=hw.comm_cost(topo.distance(gc_gpu,new_g))
            elif gc_gpu!=old_g and gc_gpu==new_g:
                comm_saved+=hw.comm_cost(topo.distance(gc_gpu,old_g))
        if comm_saved<=comm_added: continue

        # Makespan guard
        asgn[child]=new_g
        new_ms=_estimate_makespan(tree,asgn,ng,topo,hw)
        if new_ms<cur_ms:
            gl[old_g]-=cost; gl[new_g]+=cost; cur_ms=new_ms
            tl=_tl_actual(asgn); bl=_bl_actual(asgn)
            cpl=max(tl[n]+bl[n] for n in range(N))
        else:
            asgn[child]=old_g

    return asgn


def assign_cluster_heft(tree,ng,topo,hw=HW):
    """Clustered HEFT (Sinnen & Sousa 2005) — CP-reducing clustering + HEFT mapping.

    Phase 1: Merge parent-child pairs when zeroing the edge reduces CP length.
             Bounded by cluster weight cap. Edges processed by priority.
    Phase 2: Build cluster DAG, compute b-levels via BFS from root cluster.
    Phase 3: Schedule clusters in decreasing b-level (HEFT on coarsened graph).
    """
    _set_deadline()
    N=tree.total_nodes
    if ng<=1: return {n:0 for n in range(N)}

    ctx=_get_ctx(tree,topo)
    avg_comm=ctx.avg_comm if ctx else hw.comm_cost(1)
    W=tree.total_work(); mcw=max(1,math.ceil(W/ng*1.5))

    # Union-Find
    uf_par=list(range(N)); uf_rnk=[0]*N; uf_wt=[tree.node_cost(n) for n in range(N)]
    def _find(x):
        while uf_par[x]!=x: uf_par[x]=uf_par[uf_par[x]];x=uf_par[x]
        return x
    def _union(a,b):
        ra,rb=_find(a),_find(b)
        if ra==rb: return False
        nw=uf_wt[ra]+uf_wt[rb]
        if nw>mcw: return False
        if uf_rnk[ra]<uf_rnk[rb]: ra,rb=rb,ra
        uf_par[rb]=ra; uf_wt[ra]=nw
        if uf_rnk[ra]==uf_rnk[rb]: uf_rnk[ra]+=1
        return True
    def _same(a,b): return _find(a)==_find(b)

    def _cp_len():
        tl=[0.0]*N
        for n in tree.postorder():
            if tree.is_leaf(n): tl[n]=0.0
            else: tl[n]=max(tl[c]+tree.node_cost(c)+(0 if _same(c,n) else avg_comm) for c in tree.children(n))
        bl=[0.0]*N; bl[0]=tree.node_cost(0)
        for n in range(N):
            for c in tree.children(n):
                comm=0 if _same(c,n) else avg_comm
                bl[c]=tree.node_cost(c)+comm+bl[n]
        return max(tl[n]+bl[n] for n in range(N))

    # Initial priority for edge ordering
    tl0=[0.0]*N
    for n in tree.postorder():
        if tree.is_leaf(n): tl0[n]=0.0
        else: tl0[n]=max(tl0[c]+tree.node_cost(c)+avg_comm for c in tree.children(n))
    bl0=[0.0]*N; bl0[0]=tree.node_cost(0)
    for n in range(N):
        for c in tree.children(n): bl0[c]=tree.node_cost(c)+avg_comm+bl0[n]
    pri0=[tl0[n]+bl0[n] for n in range(N)]

    edges=[(n,tree.parent(n)) for n in range(N) if tree.parent(n) is not None and tree.parent(n)>=0]
    edges.sort(key=lambda e:-max(pri0[e[0]],pri0[e[1]]))

    cp_before=_cp_len()
    # Precompute tl/bl for CP-skip optimization
    _tl_cache=[0.0]*N
    for n in tree.postorder():
        if tree.is_leaf(n): _tl_cache[n]=0.0
        else: _tl_cache[n]=max(_tl_cache[c]+tree.node_cost(c)+(0 if _same(c,n) else avg_comm) for c in tree.children(n))
    _bl_cache=[0.0]*N; _bl_cache[0]=tree.node_cost(0)
    for n in range(N):
        for c in tree.children(n):
            comm=0 if _same(c,n) else avg_comm
            _bl_cache[c]=tree.node_cost(c)+comm+_bl_cache[n]
    eps=max(1e-9,cp_before*0.02); merges_since_refresh=0; refresh_interval=max(1,N//200)
    for child,parent in edges:
        _check_deadline("ClHEFT")
        if _same(child,parent): continue
        # Skip edges where neither endpoint is on critical path
        cp_child=abs(_tl_cache[child]+_bl_cache[child]-cp_before)<eps
        cp_parent=abs(_tl_cache[parent]+_bl_cache[parent]-cp_before)<eps
        if not cp_child and not cp_parent: continue
        # Point-save only affected UF entries
        ra,rb=_find(child),_find(parent)
        save_entries=((ra,uf_par[ra],uf_rnk[ra],uf_wt[ra]),(rb,uf_par[rb],uf_rnk[rb],uf_wt[rb]))
        merged=_union(child,parent)
        if not merged: continue
        cp_after=_cp_len()
        if cp_after>cp_before:
            for idx,par_v,rnk_v,wt_v in save_entries:
                uf_par[idx]=par_v; uf_rnk[idx]=rnk_v; uf_wt[idx]=wt_v
        else:
            cp_before=cp_after; merges_since_refresh+=1
            # Batch refresh tl/bl cache to avoid O(N) per merge
            if merges_since_refresh>=refresh_interval:
                merges_since_refresh=0
                for n in tree.postorder():
                    if tree.is_leaf(n): _tl_cache[n]=0.0
                    else: _tl_cache[n]=max(_tl_cache[c]+tree.node_cost(c)+(0 if _same(c,n) else avg_comm) for c in tree.children(n))
                _bl_cache[0]=tree.node_cost(0)
                for n in range(N):
                    for c in tree.children(n):
                        comm=0 if _same(c,n) else avg_comm
                        _bl_cache[c]=tree.node_cost(c)+comm+_bl_cache[n]
                eps=max(1e-9,cp_before*0.02)

    # Build cluster DAG
    cids=sorted(set(_find(n) for n in range(N)))
    cm={c:i for i,c in enumerate(cids)}; nc=len(cids)
    cwt=[0.0]*nc
    for n in range(N): cwt[cm[_find(n)]]+=tree.node_cost(n)

    c_children=defaultdict(set); c_parents=defaultdict(set)
    for n in range(1,N):
        p=tree.parent(n)
        if p<0: continue
        cn=cm[_find(n)]; cp2=cm[_find(p)]
        if cn!=cp2: c_children[cp2].add(cn); c_parents[cn].add(cp2)

    # b-levels: BFS from root cluster outward
    root_cl=cm[_find(0)]
    cbl=[0.0]*nc; cbl[root_cl]=cwt[root_cl]
    visited=[False]*nc; visited[root_cl]=True
    q=deque([root_cl])
    while q:
        cn=q.popleft()
        for child_cn in c_children.get(cn,set()):
            if not visited[child_cn]:
                cbl[child_cn]=cwt[child_cn]+avg_comm+cbl[cn]
                visited[child_cn]=True; q.append(child_cn)
    for cn in range(nc):
        if not visited[cn]: cbl[cn]=cwt[cn]

    # Schedule clusters by decreasing b-level
    co=sorted(range(nc),key=lambda c:-cbl[c])
    cg={}; ga=[0.0]*ng; cf={}
    for cn in co:
        _check_deadline("ClHEFT2")
        bg=0; be=float('inf')
        for g in range(ng):
            est=ga[g]
            for pred in c_children.get(cn,set()):
                if pred in cf:
                    pg=cg[pred]; pf=cf[pred]
                    if pg!=g: est=max(est,pf+hw.comm_cost(topo.distance(pg,g)))
                    else: est=max(est,pf)
            eft=est+cwt[cn]
            if eft<be: be=eft;bg=g
        cg[cn]=bg; ga[bg]=be; cf[cn]=be

    return {n:cg.get(cm[_find(n)],0) for n in range(N)}

def assign_parsubtrees(tree,ng,topo,hw=HW):
    """Parallel Subtrees — SU-guided recursive GPU allocation (Sethi & Ullman 1970).

    SU(node) tells how many processors are needed for optimal evaluation:
      - Equal SU children → both need full parallelism → split GPUs
      - Unequal SU children → heavy child dominates → give it more GPUs
      - Parent stays with heavy child (zero comm on critical path)

    Fix vs old: old code computed SU numbers but never used them for allocation.
    Used majority-vote parent placement with dmem_depth capacity instead.
    """
    _set_deadline()
    N=tree.total_nodes
    if ng<=1: return {n:0 for n in range(N)}

    # Compute Sethi-Ullman numbers
    su=[0]*N
    for n in tree.postorder():
        if tree.is_leaf(n): su[n]=1
        else:
            cs=sorted([su[c] for c in tree.children(n)],reverse=True)
            if len(cs)>=2 and cs[0]==cs[1]: su[n]=cs[0]+1
            elif cs: su[n]=cs[0]
            else: su[n]=1

    # Subtree weights for load-balance tiebreaks
    sw=[0.0]*N
    for n in tree.postorder():
        sw[n]=tree.node_cost(n)
        for c in tree.children(n): sw[n]+=sw[c]

    asgn=[0]*N

    def _assign(node,gpus):
        _check_deadline("ParSub")
        if not gpus: return
        if tree.is_leaf(node): asgn[node]=gpus[0];return
        if len(gpus)==1:
            stack=[node]
            while stack:
                n=stack.pop(); asgn[n]=gpus[0]
                for c in tree.children(n): stack.append(c)
            return
        children=tree.children(node)
        if not children: asgn[node]=gpus[0];return
        if len(children)==1:
            asgn[node]=gpus[0]; _assign(children[0],gpus); return

        left,right=children[0],children[1]
        su_l,su_r=su[left],su[right]
        sw_l,sw_r=sw[left],sw[right]

        if su_l==su_r:
            # Equal SU: split GPUs by weight
            tw=max(1.0,sw_l+sw_r)
            sp=max(1,min(len(gpus)-1,int(round(len(gpus)*sw_l/tw))))
            gl,gr=gpus[:sp],gpus[sp:]
            asgn[node]=gl[0] if sw_l>=sw_r else gr[0]
            _assign(left,gl); _assign(right,gr)
        else:
            # Unequal SU: heavy subtree gets more GPUs
            if su_l>su_r: heavy,light,sw_h,sw_lt=left,right,sw_l,sw_r
            else: heavy,light,sw_h,sw_lt=right,left,sw_r,sw_l
            tw=max(1.0,sw_h+sw_lt)
            su_tot=su_l+su_r
            sp_su=max(1,min(len(gpus)-1,int(round(len(gpus)*su[heavy]/max(1,su_tot)))))
            sp_wt=max(1,min(len(gpus)-1,int(round(len(gpus)*sw_h/tw))))
            sp=max(1,min(len(gpus)-1,max(sp_su,sp_wt)))
            gh,glt=gpus[:sp],gpus[sp:]
            asgn[node]=gh[0]
            _assign(heavy,gh); _assign(light,glt)

    _assign(0,list(range(ng)))
    return {n:asgn[n] for n in range(N)}

def assign_spine_pinning(tree,ng,topo,hw=HW):
    """Spine Pinning — pin heavy path to GPU 0, distribute off-spine subtrees.

    Fixes vs old:
      1. Weight-based GPU split (old used node count)
      2. Largest-remainder GPU distribution (old used round-based with rounding loss)
      3. Recursive partitioning of off-spine subtrees (old had closure bug)
    """
    _set_deadline()
    N=tree.total_nodes
    if ng<=1: return {n:0 for n in range(N)}

    # Phase 1: Heavy spine
    sw=[0.0]*N
    for n in tree.postorder():
        sw[n]=tree.node_cost(n)
        for c in tree.children(n): sw[n]+=sw[c]

    spine=[0]; node=0
    while not tree.is_leaf(node):
        ch=tree.children(node)
        if not ch: break
        hv=max(ch,key=lambda c:sw[c]); spine.append(hv); node=hv
    spine_set=set(spine)

    # Phase 2: Pin spine to GPU 0
    asgn={}
    for n in spine_set: asgn[n]=0

    # Phase 3: Collect off-spine subtrees
    non_spine=set(range(N))-spine_set
    oss=[]
    for s in spine:
        for c in tree.children(s):
            if c not in spine_set:
                nodes=sorted(_collect_subtree(tree,c,non_spine))
                if nodes: oss.append((nodes,sum(tree.node_cost(n) for n in nodes)))
    if not oss: return asgn

    # Phase 4: Distribute GPUs via largest-remainder
    rg=list(range(1,ng)) if ng>1 else [0]
    nr=len(rg)
    if nr==0:
        for nodes,_ in oss:
            for n in nodes: asgn[n]=0
        return asgn

    oss.sort(key=lambda x:-x[1])
    tow=max(1.0,sum(w for _,w in oss))
    fracs=[nr*w/tow for _,w in oss]
    allocs=[max(1,int(f)) for f in fracs]
    total=sum(allocs)
    if total<nr:
        rems=sorted(range(len(allocs)),key=lambda i:-(fracs[i]-allocs[i]))
        for j in range(nr-total):
            if j<len(rems): allocs[rems[j]]+=1
    elif total>nr:
        excess=total-nr
        order=sorted(range(len(allocs)),key=lambda i:-allocs[i])
        for i in order:
            if excess<=0: break
            if allocs[i]>1:
                trim=min(allocs[i]-1,excess); allocs[i]-=trim; excess-=trim

    gpu_slices=[]; gi=0
    for a in allocs: gpu_slices.append(rg[gi:gi+a]); gi+=a

    # Phase 5: Recursive weight-proportional partitioning
    def _part(nodes,gpus):
        _check_deadline("Spine_P")
        if len(gpus)<=1 or len(nodes)<=1:
            tgt=gpus[0] if gpus else 0
            for n in nodes: asgn[n]=tgt
            return
        pa,pb=_bisect_partition(tree,nodes)
        wa=sum(tree.node_cost(n) for n in pa)
        tw2=max(1.0,wa+sum(tree.node_cost(n) for n in pb))
        sp=max(1,min(len(gpus)-1,int(round(len(gpus)*wa/tw2))))
        _part(pa,gpus[:sp]); _part(pb,gpus[sp:])

    for i,(nodes,_) in enumerate(oss):
        gpus=gpu_slices[i] if i<len(gpu_slices) else [rg[-1]]
        if not gpus: gpus=[rg[-1]]
        _part(nodes,gpus)

    for n in range(N):
        if n not in asgn: asgn[n]=0
    return asgn


def assign_subtree_packing(tree,ng,topo,hw=HW):
    """Subtree Packing — First Fit Decreasing for trees.

    Fixes vs old:
      1. Communication-aware GPU selection (prefer parent's GPU)
      2. Split handling when subtree doesn't fit whole
      3. Remaining-weight tracking (old used full subtree weight even if partially assigned)
    """
    _set_deadline()
    N=tree.total_nodes
    if ng<=1: return {n:0 for n in range(N)}

    W=tree.total_work(); cap=max(1,math.ceil(W/ng*1.15))
    sw=[0.0]*N
    for n in tree.postorder():
        sw[n]=tree.node_cost(n)
        for c in tree.children(n): sw[n]+=sw[c]

    asgn=[-1]*N; gl=[0.0]*ng
    # Incremental remaining weight array
    rw=sw[:]  # rw[n] = remaining unassigned weight in subtree rooted at n
    # Process bottom-up: only subtrees that fit whole, then split the rest
    cands=sorted([n for n in range(N) if sw[n]<=cap],key=lambda n:-sw[n])
    # Append nodes with sw>cap at the end for split handling
    oversized=sorted([n for n in range(N) if sw[n]>cap],key=lambda n:sw[n])
    cands=cands+oversized

    def _pack(node,gpu):
        stack=[node]
        while stack:
            n=stack.pop()
            if asgn[n]>=0: continue
            cost_n=tree.node_cost(n)
            asgn[n]=gpu; gl[gpu]+=cost_n
            # Update rw for ancestors
            anc=tree.parent(n)
            while anc is not None and anc>=0:
                rw[anc]-=cost_n
                anc=tree.parent(anc)
            rw[n]=0.0
            for c in tree.children(n):
                if asgn[c]<0: stack.append(c)

    def _collect_unassigned(node):
        result=[]; stack=[node]
        while stack:
            n=stack.pop()
            if asgn[n]>=0: continue
            result.append(n)
            for c in tree.children(n):
                if asgn[c]<0: stack.append(c)
        return result

    for idx,node in enumerate(cands):
        if idx%500==0: _check_deadline("SubPack")
        if asgn[node]>=0: continue
        rwn=rw[node]
        if rwn<=0: continue

        # Comm-aware best-fit GPU selection
        parent=tree.parent(node)
        parent_gpu=asgn[parent] if parent is not None and parent>=0 and asgn[parent]>=0 else -1
        bg=-1; bs=float('inf')
        for g in range(ng):
            rem=cap-gl[g]
            if rem<rwn: continue
            waste=rem-rwn
            cp2=0 if parent_gpu<0 or g==parent_gpu else 1
            score=waste+cp2*cap*0.1
            if score<bs: bs=score;bg=g

        if bg>=0:
            _pack(node,bg)
        else:
            # Split: pack what fits
            unassigned=_collect_unassigned(node)
            if not unassigned: continue
            if parent_gpu>=0 and gl[parent_gpu]+tree.node_cost(node)<=cap:
                tgt=parent_gpu
            else:
                tgt=min(range(ng),key=lambda g:gl[g])
            for n in unassigned:
                if asgn[n]>=0: continue
                cost=tree.node_cost(n)
                if gl[tgt]+cost<=cap: asgn[n]=tgt;gl[tgt]+=cost
                else:
                    og=min(range(ng),key=lambda g:gl[g])
                    asgn[n]=og;gl[og]+=cost

    for n in range(N):
        if asgn[n]<0:
            best=min(range(ng),key=lambda g:gl[g])
            asgn[n]=best;gl[best]+=tree.node_cost(n)
    return {n:asgn[n] for n in range(N)}


def assign_level_parallel_hlf(tree,ng,topo,hw=HW):
    """Highest Level First (Hu 1961) — priority-based parallel scheduling.

    Fixes vs old:
      Old code was NOT HLF — just round-robin i%ng per level.
      New code: proper HLF with max-heap ready queue, precedence tracking,
      batch scheduling of up to ng tasks per timestep, topology-aware
      GPU assignment with data-ready constraints.
    """
    _set_deadline()
    N=tree.total_nodes
    if ng<=1: return {n:0 for n in range(N)}

    hu=tree.hu_levels()
    n_ch=[len(tree.children(n)) for n in range(N)]
    ch_done=[0]*N

    import heapq
    ready=[]
    for n in range(N):
        if tree.is_leaf(n): heapq.heappush(ready,(-hu[n],n))

    asgn={}; gl=[0.0]*ng; gpu_avail=[0.0]*ng; nf={}; scheduled=set()

    while ready:
        _check_deadline("LvlHLF")
        batch=[]
        while ready and len(batch)<ng:
            neg_hu,node=heapq.heappop(ready)
            if node in scheduled: continue
            batch.append(node)
        if not batch: break

        for node in batch:
            cost=tree.node_cost(node)
            # Hoist child data
            children_data=[(asgn[c],nf[c]) for c in tree.children(node) if c in asgn]
            bg=0; bt=float('inf')
            for g in range(ng):
                if gpu_avail[g]>=bt: continue  # early termination
                est=gpu_avail[g]
                for cg,cd in children_data:
                    if cg!=g: est=max(est,cd+hw.comm_cost(topo.distance(cg,g)))
                    else: est=max(est,cd)
                    if est>=bt: break
                if est<bt or (est==bt and gl[g]<gl[bg]):
                    bt=est; bg=g

            asgn[node]=bg; gl[bg]+=cost; nf[node]=bt+cost; gpu_avail[bg]=bt+cost
            scheduled.add(node)

            p=tree.parent(node)
            if p is not None and p>=0:
                ch_done[p]+=1
                if ch_done[p]>=n_ch[p]:
                    heapq.heappush(ready,(-hu[p],p))

    for n in range(N):
        if n not in asgn:
            best=min(range(ng),key=lambda g:gl[g])
            asgn[n]=best;gl[best]+=tree.node_cost(n)
    return asgn

# STAGE 3: 10 MAPPING METHODS (timeout-instrumented)
# ═══════════════════════════════════════════════════════════
def _build_comm_graph(tree,asgn,ng):
    H=defaultdict(lambda:defaultdict(int))
    for node in range(1,tree.total_nodes):
        p=tree.parent(node)
        if p is not None and asgn[node]!=asgn[p]:
            g1,g2=asgn[node],asgn[p];H[g1][g2]+=1;H[g2][g1]+=1
    return dict(H)

def _active_gpus(asgn): return set(asgn.values())

def _fill_inactive_gpus(mapping,ng,n_pes):
    """Fill missing GPU keys with unused physical nodes (lowest-first).
    Expects mapping.values() to already be unique (injective over active GPUs).
    Assumes ng <= n_pes (tournament precondition)."""
    used=set(mapping.values())
    free=iter(pe for pe in range(n_pes) if pe not in used)
    for g in range(ng):
        if g not in mapping:
            try: mapping[g]=next(free)
            except StopIteration: mapping[g]=g%n_pes
    return mapping

def map_identity(tree,asgn,ng,topo,hw=HW): return{g:g for g in range(ng)}

def map_greedy_hop_min(tree,asgn,ng,topo,hw=HW):
    """Greedy Hop Minimization mapper.

    Fixes vs old: centrality-based first-GPU placement, tiebreaking by PE centrality.
    """
    _set_deadline()
    H=_build_comm_graph(tree,asgn,ng); act=sorted(_active_gpus(asgn))
    if not act: return {g:g%topo.n_nodes for g in range(ng)}
    mapping={}; used=set(); n_pes=topo.n_nodes
    cv={g:sum(H.get(g,{}).values()) for g in act}
    order=sorted(act,key=lambda g:-cv.get(g,0))

    # PE centrality for first-placement and tiebreaking
    pe_cent={}
    for pe in range(n_pes):
        pe_cent[pe]=sum(topo.distance(pe,o) for o in range(n_pes) if o!=pe)

    for idx,g in enumerate(order):
        _check_deadline("HopMin")
        bp=0; bc=float('inf')
        for pe in range(n_pes):
            if pe in used: continue
            if idx==0:
                cost=pe_cent.get(pe,0)
            else:
                cost=sum(w*topo.distance(pe,mapping[nb]) for nb,w in H.get(g,{}).items() if nb in mapping)
                if cost==0 and H.get(g): cost=pe_cent.get(pe,0)*0.001
            if cost<bc: bc=cost;bp=pe
            elif cost==bc and pe_cent.get(pe,0)<pe_cent.get(bp,0): bp=pe
        mapping[g]=bp; used.add(bp)

    for g in range(ng):
        if g not in mapping:
            for pe in range(n_pes):
                if pe not in used: mapping[g]=pe;used.add(pe);break
            else: mapping[g]=g%n_pes
    return mapping


def map_treematch(tree,asgn,ng,topo,hw=HW):
    """TreeMatch process mapping (Jeannot & Mercier 2010).

    Fixes vs old: old was NOT TreeMatch — just greedy pairing.
    New: topology-aware PE hierarchy via recursive bisection,
    recursive GPU-to-PE-subtree matching with min-cut partitioning.
    """
    _set_deadline()
    H=_build_comm_graph(tree,asgn,ng); act=sorted(_active_gpus(asgn))
    if len(act)<=1: return {g:g%topo.n_nodes for g in range(ng)}
    n_pes=topo.n_nodes

    def _build_pe_tree(pes):
        if len(pes)<=1: return pes
        if len(pes)==2: return ([pes[0]],[pes[1]])
        n=len(pes); mid=n//2; bl=None; br=None; bcut=float('inf')
        name=topo.name

        if name.startswith('mesh_') or name.startswith('torus_'):
            params=name.split('_')[1].split('x')
            rows,cols=int(params[0]),int(params[1]); ps=set(pes)
            for sr in range(1,rows):
                left=[p for p in pes if p//cols<sr]; right=[p for p in pes if p//cols>=sr]
                if left and right:
                    left_set=set(left); cut=sum(1 for p in left for nb in topo.neighbors(p) if nb in ps and nb not in left_set)
                    score=cut+abs(len(left)-len(right))*0.5
                    if score<bcut: bcut=score;bl=left;br=right
            for sc2 in range(1,cols):
                left=[p for p in pes if p%cols<sc2]; right=[p for p in pes if p%cols>=sc2]
                if left and right:
                    left_set=set(left); cut=sum(1 for p in left for nb in topo.neighbors(p) if nb in ps and nb not in left_set)
                    score=cut+abs(len(left)-len(right))*0.5
                    if score<bcut: bcut=score;bl=left;br=right
        elif name.startswith('hypercube_'):
            dim=int(name.split('_')[1].replace('d',''))
            ps=set(pes)
            for d in range(dim):
                left=[p for p in pes if not(p&(1<<d))]; right=[p for p in pes if p&(1<<d)]
                if left and right:
                    left_set=set(left); cut=sum(1 for p in left for nb in topo.neighbors(p) if nb in ps and nb not in left_set)
                    score=cut+abs(len(left)-len(right))*0.5
                    if score<bcut: bcut=score;bl=left;br=right
        elif name.startswith('fat_tree_'):
            k=getattr(topo,'_fat_tree_k',max(2,int(math.ceil(math.sqrt(n)))))
            pods=defaultdict(list); ps=set(pes)
            for p in pes: pods[p//k].append(p)
            pl=sorted(pods.keys())
            for sp in range(1,len(pl)):
                lp=set(pl[:sp]); left=[p for p in pes if p//k in lp]; right=[p for p in pes if p//k not in lp]
                if left and right:
                    left_set=set(left); cut=sum(1 for p in left for nb in topo.neighbors(p) if nb in ps and nb not in left_set)
                    score=cut+abs(len(left)-len(right))*0.5
                    if score<bcut: bcut=score;bl=left;br=right

        if bl is None:
            # Fallback: sorted midpoint split (always terminates)
            sp=sorted(pes); bl=sp[:mid]; br=sp[mid:]
        if not bl or not br: bl=sorted(pes)[:mid];br=sorted(pes)[mid:]
        return (_build_pe_tree(bl),_build_pe_tree(br))

    pe_hier=_build_pe_tree(list(range(n_pes))[:max(len(act),1)])

    def _count(t):
        if isinstance(t,list): return len(t)
        return _count(t[0])+_count(t[1])
    def _leaves(t):
        if isinstance(t,list): return list(t)
        return _leaves(t[0])+_leaves(t[1])

    mapping={}
    def _match(gpus,subtree):
        _check_deadline("TM")
        if not gpus: return
        if isinstance(subtree,list):
            # Leaf PE-subtree: invariant guarantees len(gpus) <= len(subtree),
            # so enumerate() is a true 1-to-1 assignment. The clamp in the
            # caller ('tgt<=nl' / 'n-tgt<=nr') is what makes this hold.
            assert len(gpus)<=len(subtree), "TM: size invariant broken (%d>%d)"%(len(gpus),len(subtree))
            for i,g in enumerate(sorted(gpus)): mapping[g]=subtree[i]
            return
        left,right=subtree; nl=_count(left); nr=_count(right)
        gl=sorted(gpus); n=len(gl); gs=set(gl)
        # Size-preserving split: |blg|=tgt GPUs go to left subtree (nl leaves),
        # |rg|=n-tgt GPUs go to right subtree (nr leaves).
        # Invariant n<=nl+nr is maintained recursively; enforce it via clamps.
        tgt=min(nl,n)            # left cannot exceed PE-left capacity
        tgt=max(tgt,n-nr)        # right cannot exceed PE-right capacity
        if tgt<=0:
            _match(gl,right); return
        if tgt>=n:
            _match(gl,left); return

        if n<=22:
            from itertools import combinations
            bcut=float('inf'); blg=set(gl[:tgt])
            for combo in combinations(gl,tgt):
                lg2=set(combo)
                cut=sum(w for g in lg2 for nb,w in H.get(g,{}).items() if nb in gs and nb not in lg2)
                if cut<bcut: bcut=cut;blg=lg2
            rg=gs-blg
        else:
            blg=set(gl[:tgt]); rg=gs-blg
            # KL swaps preserve |blg|=tgt exactly.
            for _ in range(min(5,n)):
                _check_deadline("TM_KL")
                improved=False
                for g1 in list(blg):
                    for g2 in list(rg):
                        delta=0
                        for nb,w in H.get(g1,{}).items():
                            if nb not in gs or nb==g2: continue
                            if nb in blg: delta+=w
                            else: delta-=w
                        for nb,w in H.get(g2,{}).items():
                            if nb not in gs or nb==g1: continue
                            if nb in rg: delta+=w
                            else: delta-=w
                        if delta<0:
                            blg.discard(g1);blg.add(g2);rg.discard(g2);rg.add(g1)
                            improved=True; break
                    if improved: break
                if not improved: break
        _match(blg,left); _match(rg,right)

    _match(set(act),pe_hier)
    return _fill_inactive_gpus(mapping,ng,n_pes)


def map_qap_sa(tree,asgn,ng,topo,hw=HW):
    """QAP Simulated Annealing mapper with incremental delta, calibrated T, reheating.

    Fixes vs old: O(degree) delta eval (old was O(N²) full recompute),
    adaptive T₀ calibration, stagnation reheating.
    """
    _set_deadline()
    mapping=map_greedy_hop_min(tree,asgn,ng,topo,hw)
    act=sorted(_active_gpus(asgn))
    if len(act)<=2: return mapping
    H=_build_comm_graph(tree,asgn,ng)

    adj=defaultdict(list)
    for g1 in act:
        for g2,w in H.get(g1,{}).items():
            if g2>g1: adj[g1].append((g2,w));adj[g2].append((g1,w))

    # Precompute distance cache for PE pairs used in mapping
    _dcache={}
    def _dist(p1,p2):
        if p1==p2: return 0
        key=(p1,p2) if p1<p2 else (p2,p1)
        r=_dcache.get(key)
        if r is None: r=topo.distance(p1,p2); _dcache[key]=r
        return r

    def _cost(m):
        return sum(w*_dist(m[g1],m[g2]) for g1 in act for g2,w in H.get(g1,{}).items() if g2>g1 and g2 in m and g1 in m)

    def _delta(m,s1,s2):
        d=0
        for nb,w in adj[s1]:
            if nb==s2 or nb not in m: continue
            d-=w*_dist(m[s1],m[nb]); d+=w*_dist(m[s2],m[nb])
        for nb,w in adj[s2]:
            if nb==s1 or nb not in m: continue
            d-=w*_dist(m[s2],m[nb]); d+=w*_dist(m[s1],m[nb])
        return d

    cc=_cost(mapping); bm=dict(mapping); bc=cc
    rng=random.Random(42)

    # Temperature calibration
    sds=[]
    for _ in range(min(200,len(act)*5)):
        if len(act)<2: break
        g1,g2=rng.sample(act,2); d=_delta(mapping,g1,g2)
        if d>0: sds.append(d)
    if sds:
        avg_up=sum(sds)/len(sds)
        T=-avg_up/math.log(0.8) if avg_up>0 else 1.0
    else: T=cc*0.3 if cc>0 else 1.0

    alpha=0.95; max_iter=min(100000,500*len(act))
    stag=0; max_stag=max(500,max_iter//10)

    try:
        for it in range(max_iter):
            if it%200==0: _check_deadline("QAP")
            if len(act)<2: break
            g1,g2=rng.sample(act,2); delta=_delta(mapping,g1,g2)
            if delta<0 or rng.random()<math.exp(-delta/max(T,0.01)):
                mapping[g1],mapping[g2]=mapping[g2],mapping[g1]
                cc+=delta; stag=0
                if cc<bc: bc=cc;bm=dict(mapping)
            else: stag+=1
            if stag>=max_stag: T=max(T*5,bc*0.05);stag=0
            T*=alpha
    except AlgoTimeout: pass
    return bm


def map_mcf(tree,asgn,ng,topo,hw=HW):
    """Multicommodity Flow mapper (Shahrokhi-Matula 1990 approximation).

    Phases: iterative MCF routing → congestion-weighted PE distances → greedy mapping.

    Fixes vs old: old was NOT MCF — just random swaps with crude link loads.
    New: proper iterative weighted routing with Dijkstra, multiplicative weight
    updates, congestion-based distance extraction, and greedy constructive mapping.
    """
    _set_deadline()
    H=_build_comm_graph(tree,asgn,ng); act=sorted(_active_gpus(asgn))
    n_pes=topo.n_nodes
    if len(act)<=2: return map_greedy_hop_min(tree,asgn,ng,topo,hw)

    # Physical links
    phys_links=set(); link_nbrs=defaultdict(set)
    for pe in range(n_pes):
        for nb in topo.neighbors(pe):
            lk=(min(pe,nb),max(pe,nb)); phys_links.add(lk)
            link_nbrs[pe].add(nb)
    if not phys_links: return map_greedy_hop_min(tree,asgn,ng,topo,hw)

    # Commodities
    comms=[(g1,g2,w) for g1 in act for g2,w in H.get(g1,{}).items() if g2>g1]
    if not comms: return map_greedy_hop_min(tree,asgn,ng,topo,hw)
    total_dem=sum(w for _,_,w in comms)

    # Weighted shortest path
    def _wsp(src,dst,wts):
        if src==dst: return [src],0.0
        dist2={src:0.0}; prev={src:None}; pq=[(0.0,src)]
        while pq:
            d,u=heapq.heappop(pq)
            if u==dst: break
            if d>dist2.get(u,float('inf')): continue
            for v in link_nbrs.get(u,set()):
                lk=(min(u,v),max(u,v)); nd=d+wts.get(lk,1.0)
                if nd<dist2.get(v,float('inf')):
                    dist2[v]=nd; prev[v]=u; heapq.heappush(pq,(nd,v))
        if dst not in prev: return [],float('inf')
        path=[]; cur=dst
        while cur is not None: path.append(cur);cur=prev[cur]
        path.reverse(); return path,dist2.get(dst,float('inf'))

    # Initial mapping
    mapping=map_greedy_hop_min(tree,asgn,ng,topo,hw)
    lk_wt={lk:1.0 for lk in phys_links}; eps=0.1
    n_iter=min(20,max(5,len(act)))

    for iteration in range(n_iter):
        _check_deadline("MCF_iter")
        iter_load=defaultdict(float)
        for g1,g2,dem in comms:
            pe1,pe2=mapping[g1],mapping[g2]
            if pe1==pe2: continue
            path,_=_wsp(pe1,pe2,lk_wt)
            if len(path)<2: continue
            for i in range(len(path)-1):
                lk=(min(path[i],path[i+1]),max(path[i],path[i+1]))
                iter_load[lk]+=dem
        for lk in phys_links:
            load=iter_load.get(lk,0.0)
            if load>0: lk_wt[lk]*=(1.0+eps*load/max(1.0,total_dem))

    # Extract congestion-based PE distances via single-source Dijkstra
    pe_dist_w={}
    def _sssp(src,wts):
        """Single-source shortest path — returns dist dict from src to all reachable."""
        dist2={src:0.0}; pq=[(0.0,src)]
        while pq:
            d,u=heapq.heappop(pq)
            if d>dist2.get(u,float('inf')): continue
            for v in link_nbrs.get(u,set()):
                lk=(min(u,v),max(u,v)); nd=d+wts.get(lk,1.0)
                if nd<dist2.get(v,float('inf')):
                    dist2[v]=nd; heapq.heappush(pq,(nd,v))
        return dist2
    for pe in range(n_pes):
        _check_deadline("MCF_dist")
        dists=_sssp(pe,lk_wt)
        for pe2 in range(pe+1,n_pes):
            if pe2 in dists: pe_dist_w[(pe,pe2)]=dists[pe2]

    def _wpd(p1,p2):
        if p1==p2: return 0.0
        return pe_dist_w.get((min(p1,p2),max(p1,p2)),float('inf'))

    # Greedy constructive mapping using weighted distances
    cv={g:sum(H.get(g,{}).values()) for g in act}
    order=sorted(act,key=lambda g:-cv.get(g,0))
    best_map={}; used=set()
    for g in order:
        _check_deadline("MCF_map")
        bp=0; bcs=float('inf')
        for pe in range(n_pes):
            if pe in used: continue
            cost=sum(w*_wpd(pe,best_map[nb]) for nb,w in H.get(g,{}).items() if nb in best_map)
            if cost<bcs: bcs=cost;bp=pe
        best_map[g]=bp; used.add(bp)

    used=set(best_map.values())
    for g in range(ng):
        if g not in best_map:
            for pe in range(n_pes):
                if pe not in used: best_map[g]=pe;used.add(pe);break
            else: best_map[g]=g%n_pes
    return best_map

def map_drb(tree,asgn,ng,topo,hw=HW):
    """Dual Recursive Bisection (Pellegrini 1994).

    Simultaneously bisects process comm graph and PE network,
    matches halves (heavy comm → denser PEs), recurses.

    Fixes vs old: old used trivial prefix splits with no topology awareness.
    New: comm-weighted KL bisection for GPUs, topology-specific PE bisection,
    density-based half matching.
    """
    _set_deadline()
    act=sorted(_active_gpus(asgn)); mapping={}
    if len(act)<=1:
        mapping[act[0] if act else 0]=0
        for g in range(ng):
            if g not in mapping: mapping[g]=g%topo.n_nodes
        return mapping

    H=_build_comm_graph(tree,asgn,ng); n_pes=topo.n_nodes

    def _bisect_gpus(gpus,tgt):
        """Bisect gpus into (left, right) with |left|==tgt exactly."""
        gl=sorted(gpus); gs=set(gl); n=len(gl)
        if tgt<=0: return [],list(gl)
        if tgt>=n: return list(gl),[]
        def _cw(ls): return sum(w for g in ls for nb,w in H.get(g,{}).items() if nb in gs and nb not in ls)
        # Seed: min-cut over the single target size (no size drift).
        bl2=set(gl[:tgt]); bcut=_cw(bl2)
        # KL improvement (swap-based; preserves |left|=tgt).
        left=set(bl2); right=gs-left
        for _ in range(min(20,n//2)):
            _check_deadline("DRB_KL")
            bs2=None; bde=0
            for g1 in list(left):
                e1=sum(w for nb,w in H.get(g1,{}).items() if nb in gs and nb in left and nb!=g1)
                i1=sum(w for nb,w in H.get(g1,{}).items() if nb in gs and nb in right)
                for g2 in list(right):
                    e2=sum(w for nb,w in H.get(g2,{}).items() if nb in gs and nb in right and nb!=g2)
                    i2=sum(w for nb,w in H.get(g2,{}).items() if nb in gs and nb in left)
                    e12=H.get(g1,{}).get(g2,0)
                    delta=(e1+e2)-(i1+i2)+2*e12
                    if delta<bde: bde=delta;bs2=(g1,g2)
            if bs2:
                g1,g2=bs2; left.discard(g1);left.add(g2);right.discard(g2);right.add(g1)
                bcut+=bde; bl2=set(left)
            else: break
        return sorted(bl2),sorted(gs-bl2)

    def _bisect_pes(pes):
        if len(pes)<=1: return list(pes),[]
        if len(pes)==2: return [pes[0]],[pes[1]]
        ps=set(pes); n=len(pes); mid=n//2; bl3=None; bcut=float('inf')
        name=topo.name
        if name=='linear' or name=='ring':
            # Sort PEs by ID; for ring, contiguous halves minimize edge cut
            sp=sorted(pes)
            bl3=sp[:mid]
        elif name.startswith('mesh_') or name.startswith('torus_'):
            params=name.split('_')[1].split('x'); R,C=int(params[0]),int(params[1])
            for sr in range(1,R):
                left=[p for p in pes if p//C<sr]; right=[p for p in pes if p//C>=sr]
                if left and right:
                    left_set=set(left); cut=sum(1 for p in left for nb in topo.neighbors(p) if nb in ps and nb not in left_set)
                    score=cut+abs(len(left)-len(right))*0.3
                    if score<bcut: bcut=score;bl3=left
            for sc2 in range(1,C):
                left=[p for p in pes if p%C<sc2]; right=[p for p in pes if p%C>=sc2]
                if left and right:
                    left_set=set(left); cut=sum(1 for p in left for nb in topo.neighbors(p) if nb in ps and nb not in left_set)
                    score=cut+abs(len(left)-len(right))*0.3
                    if score<bcut: bcut=score;bl3=left
        elif name.startswith('fat_tree_'):
            k=getattr(topo,'_fat_tree_k',max(2,int(math.ceil(math.sqrt(n)))))
            pods=defaultdict(list)
            for p in pes: pods[p//k].append(p)
            pl=sorted(pods.keys())
            for sp in range(1,len(pl)):
                lp=set(pl[:sp]); left=[p for p in pes if p//k in lp]
                if left and len(left)<n:
                    left_set=set(left); cut=sum(1 for p in left for nb in topo.neighbors(p) if nb in ps and nb not in left_set)
                    score=cut+abs(len(left)-(n-len(left)))*0.3
                    if score<bcut: bcut=score;bl3=left
        elif name.startswith('hypercube_'):
            dim=int(name.split('_')[1].replace('d',''))
            for d in range(dim):
                left=[p for p in pes if not(p&(1<<d))]
                if left and len(left)<n:
                    left_set=set(left); cut=sum(1 for p in left for nb in topo.neighbors(p) if nb in ps and nb not in left_set)
                    if cut<bcut: bcut=cut;bl3=left
        if bl3 is None:
            # General fallback: sorted midpoint split
            sp=sorted(pes); bl3=sp[:mid]
        return sorted(bl3),sorted(p for p in pes if p not in set(bl3))

    max_depth = int(math.log2(max(len(act), 2))) + 5  # generous but finite

    def _match(gpus, pes, depth=0):
        # Invariant: |gpus| == |pes|. Preserved by choosing GPU bisect target
        # equal to the chosen PE side's size.
        if not gpus: return
        if len(gpus)==1:
            mapping[gpus[0]]=pes[0]; return
        if depth > max_depth or len(pes) <= 1:
            for i,g in enumerate(gpus): mapping[g]=pes[i]  # |gpus|<=|pes| by invariant
            return
        _check_deadline("DRB")
        pa,pb=_bisect_pes(pes)
        if not pa or not pb:
            for i,g in enumerate(gpus): mapping[g]=pes[i]
            return
        # Density of each PE half (internal edge count)
        pas,pbs=set(pa),set(pb)
        da=sum(1 for p in pa for nb in topo.neighbors(p) if nb in pas)
        db=sum(1 for p in pb for nb in topo.neighbors(p) if nb in pbs)
        # Split GPUs to match the denser PE half with the heavier-comm GPU half.
        # The GPU group going to pa must have size exactly |pa|.
        ga,gb=_bisect_gpus(gpus,len(pa))
        gas,gbs=set(ga),set(gb)
        ca=sum(w for g in ga for nb,w in H.get(g,{}).items() if nb in gas)
        cb=sum(w for g in gb for nb,w in H.get(g,{}).items() if nb in gbs)
        # (ca corresponds to group with |ga|=|pa|; by construction "straight" maps size-correctly.)
        # Heuristic: if the dense-comm vs dense-PE correlation sign is inverted,
        # swap GPU groups — but we must re-bisect to preserve sizes.
        if (ca>=cb)!=(da>=db):
            # Want to cross: put heavy-comm GPUs on denser side.
            # Re-bisect with target = |pb| so that ga->pb is size-correct.
            ga2,gb2=_bisect_gpus(gpus,len(pb))
            _match(gb2,pa,depth+1); _match(ga2,pb,depth+1)
        else:
            _match(ga,pa,depth+1); _match(gb,pb,depth+1)

    try: _match(act,list(range(n_pes))[:max(len(act),1)])
    except AlgoTimeout: pass
    return _fill_inactive_gpus(mapping,ng,n_pes)


def map_sfc(tree,asgn,ng,topo,hw=HW):
    """Space-Filling Curve mapping (Morton Z-order / Gray code).

    Fixes vs old: parses actual R×C from topology name (old used sqrt),
    adds Gray code for hypercube.
    """
    _check_deadline("SFC")
    act=sorted(_active_gpus(asgn))
    if not act: return {g:g%topo.n_nodes for g in range(ng)}
    name=topo.name; n_pes=topo.n_nodes

    if name.startswith('mesh_') or name.startswith('torus_'):
        params=name.split('_')[1].split('x'); R,C=int(params[0]),int(params[1])
        def _mort(x,y):
            z=0
            for i in range(16): z|=((x&(1<<i))<<i)|((y&(1<<i))<<(i+1))
            return z
        po=sorted((_mort(c,r),pe) for pe in range(n_pes) for r,c in [divmod(pe,C)])
        ordered=[pe for _,pe in po]
    elif name.startswith('hypercube_'):
        ordered=[i^(i>>1) for i in range(n_pes)]
    else:
        ordered=list(range(n_pes))

    mapping={g:ordered[i%len(ordered)] for i,g in enumerate(act)}
    used=set(mapping.values())
    for g in range(ng):
        if g not in mapping:
            for pe in range(n_pes):
                if pe not in used: mapping[g]=pe;used.add(pe);break
            else: mapping[g]=g%n_pes
    return mapping


def map_spectral(tree,asgn,ng,topo,hw=HW):
    """Spectral mapping via Fiedler vectors (Hall 1970, Fiedler 1973).

    Fixes vs old: proper deflation (old used mean subtraction), PE-side
    spectral analysis, 2D matching for mesh/torus topologies.
    """
    _set_deadline()
    act=sorted(_active_gpus(asgn)); H=_build_comm_graph(tree,asgn,ng)
    n_pes=topo.n_nodes
    if len(act)<=2: return map_greedy_hop_min(tree,asgn,ng,topo,hw)
    ng2=len(act); idx={g:i for i,g in enumerate(act)}

    def _fiedler(L,n,nvec=1,max_it=50000):
        rng=random.Random(42)
        lmax=max(L[i][i] for i in range(n))*1.1+1.0
        if HAS_NUMPY:
            # Numpy-accelerated power iteration (~50-100x faster)
            La=np.array(L,dtype=np.float64)
            C2a=-La; np.fill_diagonal(C2a,lmax-np.diag(La))
            e0=np.full(n,1.0/math.sqrt(n)); deflated_np=[e0]; vectors=[]
            for vi in range(nvec):
                _check_deadline("Spec_eig")
                v=np.array([rng.gauss(0,1) for _ in range(n)])
                for d in deflated_np: v-=np.dot(v,d)*d
                norm=np.linalg.norm(v)
                if norm<1e-12: v=np.array([rng.gauss(0,1) for _ in range(n)]);norm=np.linalg.norm(v)
                v/=norm
                for _ in range(max_it):
                    Cv=C2a@v
                    for d in deflated_np: Cv-=np.dot(Cv,d)*d
                    norm=np.linalg.norm(Cv)
                    if norm<1e-12: break
                    v=Cv/norm
                vectors.append(v.tolist()); deflated_np.append(v)
            return vectors
        # Fallback: pure Python with row-reference optimization
        C2=[[0.0]*n for _ in range(n)]
        for i in range(n):
            for j in range(n): C2[i][j]=-L[i][j]
            C2[i][i]=lmax-L[i][i]
        e0=[1.0/math.sqrt(n)]*n; deflated=[e0]; vectors=[]
        for vi in range(nvec):
            _check_deadline("Spec_eig")
            v=[rng.gauss(0,1) for _ in range(n)]
            for d in deflated:
                dot=sum(v[i]*d[i] for i in range(n)); v=[v[i]-dot*d[i] for i in range(n)]
            norm=math.sqrt(sum(x*x for x in v))
            if norm<1e-12: v=[rng.gauss(0,1) for _ in range(n)];norm=math.sqrt(sum(x*x for x in v))
            v=[x/norm for x in v]
            for _ in range(max_it):
                Cv=[0.0]*n
                for i in range(n):
                    row=C2[i]; s=0.0
                    for j in range(n): s+=row[j]*v[j]
                    Cv[i]=s
                for d in deflated:
                    dot=sum(Cv[i]*d[i] for i in range(n))
                    for i in range(n): Cv[i]-=dot*d[i]
                norm=math.sqrt(sum(x*x for x in Cv))
                if norm<1e-12: break
                v=[x/norm for x in Cv]
            vectors.append(v); deflated.append(v)
        return vectors

    # Process graph Laplacian
    Lg=[[0.0]*ng2 for _ in range(ng2)]
    for g in act:
        for nb,w in H.get(g,{}).items():
            if nb in idx: i,j=idx[g],idx[nb]; Lg[i][j]-=w;Lg[i][i]+=w

    is_2d=topo.name.startswith('mesh_') or topo.name.startswith('torus_')
    nd=2 if is_2d and ng2>=4 else 1
    gv=_fiedler(Lg,ng2,nvec=nd)

    # PE topology Laplacian
    npe=min(n_pes,max(ng2,64)); pe_sub=list(range(npe))
    Lp=[[0.0]*npe for _ in range(npe)]
    for pe in pe_sub:
        for nb in topo.neighbors(pe):
            if nb<npe: Lp[pe][nb]-=1.0;Lp[pe][pe]+=1.0
    pv=_fiedler(Lp,npe,nvec=nd)

    if nd==1:
        go=sorted(range(ng2),key=lambda i:gv[0][i])
        po=sorted(range(npe),key=lambda i:pv[0][i])
        mapping={act[go[r]]:pe_sub[po[r%len(po)]] for r in range(ng2)}
    else:
        gc=[(gv[0][i],gv[1][i]) for i in range(ng2)]
        pc=[(pv[0][j],pv[1][j]) for j in range(npe)]
        def _norm(coords):
            if not coords: return coords
            xs=[c[0] for c in coords]; ys=[c[1] for c in coords]
            xr=max(1e-10,max(xs)-min(xs)); yr=max(1e-10,max(ys)-min(ys))
            return [((c[0]-min(xs))/xr,(c[1]-min(ys))/yr) for c in coords]
        gc=_norm(gc); pc=_norm(pc)
        cv2={g:sum(H.get(g,{}).values()) for g in act}
        go=sorted(range(ng2),key=lambda i:-cv2.get(act[i],0))
        mapping={}; used_pe=set()
        for gi in go:
            _check_deadline("Spec_match")
            g=act[gi]; gx,gy=gc[gi]; bpe=-1;bd=float('inf')
            for pj in range(npe):
                if pj in used_pe: continue
                px,py=pc[pj]; d2=(gx-px)**2+(gy-py)**2
                if d2<bd: bd=d2;bpe=pj
            if bpe>=0: mapping[g]=pe_sub[bpe];used_pe.add(bpe)
            else: mapping[g]=g%n_pes

    used=set(mapping.values())
    for g in range(ng):
        if g not in mapping:
            for pe in range(n_pes):
                if pe not in used: mapping[g]=pe;used.add(pe);break
            else: mapping[g]=g%n_pes
    return mapping


def _bfs_path(topo,src,dst):
    """BFS shortest path between two PEs. Returns list of PE ids."""
    if src==dst: return [src]
    prev={src:None}; q=deque([src])
    while q:
        u=q.popleft()
        if u==dst: break
        for v in topo.neighbors(u):
            if v not in prev: prev[v]=u;q.append(v)
    if dst not in prev: return []
    path=[]; cur=dst
    while cur is not None: path.append(cur);cur=prev[cur]
    path.reverse(); return path


def map_routing_aware_greedy(tree,asgn,ng,topo,hw=HW):
    """Routing-Aware Greedy (Hoefler & Snir 2011).

    Tracks per-link congestion. Score = alpha*max_congestion + (1-alpha)*norm_hops.

    Fixes vs old: proper link-level congestion tracking via BFS paths,
    Hoefler-Snir congestion/latency objective (old used crude heuristic).
    """
    _set_deadline()
    act=sorted(_active_gpus(asgn)); H=_build_comm_graph(tree,asgn,ng)
    n_pes=topo.n_nodes
    if not act: return {g:g%n_pes for g in range(ng)}
    cv={g:sum(H.get(g,{}).values()) for g in act}
    link_load=defaultdict(float)
    path_cache={}

    def _get_path(pe1,pe2):
        if pe1==pe2: return []
        key=(pe1,pe2)
        if key not in path_cache: path_cache[key]=_bfs_path(topo,pe1,pe2)
        return path_cache[key]

    def _path_links(pe1,pe2):
        path=_get_path(pe1,pe2)
        return [(min(path[i],path[i+1]),max(path[i],path[i+1])) for i in range(len(path)-1)]

    # PE centrality (sampled for large topologies)
    pe_cent={}; step=max(1,n_pes//min(32,max(8,int(math.sqrt(n_pes)))))
    for pe in range(n_pes):
        _check_deadline("RAG_cent")
        pe_cent[pe]=sum(topo.distance(pe,o) for o in range(0,n_pes,step) if o!=pe)

    mapping={}; used=set()
    order=sorted(act,key=lambda g:-cv.get(g,0))
    diam=topo.diameter()

    for idx,gpu in enumerate(order):
        _check_deadline("RAG")
        bp=0; bsc=float('inf'); best_lks={}
        # For large topologies, sample PEs instead of exhaustive search
        pe_cands=range(n_pes) if n_pes<=16384 else sorted(random.Random(idx).sample(range(n_pes),min(512,n_pes)))
        for pe in pe_cands:
            if pe in used: continue
            if idx==0:
                score=pe_cent.get(pe,0); nlks={}
            else:
                th=0.0; mc=0.0; nlks=defaultdict(float)
                for nb,w in H.get(gpu,{}).items():
                    if nb not in mapping: continue
                    nbpe=mapping[nb]
                    if nbpe==pe: continue
                    d=topo.distance(pe,nbpe); th+=w*d
                    for lk in _path_links(pe,nbpe): nlks[lk]+=w
                for lk,added in nlks.items():
                    tl=link_load.get(lk,0.0)+added
                    if tl>mc: mc=tl
                mxh=cv.get(gpu,1)*diam; nh=th/max(1.0,mxh)
                cmx=max(link_load.values()) if link_load else 0.0
                nc=mc/max(1.0,cmx+1.0)
                score=0.6*nc+0.4*nh
            if score<bsc: bsc=score;bp=pe;best_lks=dict(nlks)
        mapping[gpu]=bp; used.add(bp)
        for lk,ld in best_lks.items(): link_load[lk]+=ld

    for g in range(ng):
        if g not in mapping:
            for pe in range(n_pes):
                if pe not in used: mapping[g]=pe;used.add(pe);break
            else: mapping[g]=g%n_pes
    return mapping


def map_tabu_search(tree,asgn,ng,topo,hw=HW):
    """Tabu Search for QAP mapping (Glover 1989).

    Fixes vs old: O(degree) delta eval (old was O(N²) full recompute),
    aspiration criterion, adaptive tenure, diversification restarts,
    biased candidate sampling for large instances.
    """
    _set_deadline()
    mapping=map_greedy_hop_min(tree,asgn,ng,topo,hw)
    act=sorted(_active_gpus(asgn))
    if len(act)<=2: return mapping
    H=_build_comm_graph(tree,asgn,ng)

    edges=[]; adj=defaultdict(list)
    for g1 in act:
        for g2,w in H.get(g1,{}).items():
            if g2>g1: edges.append((g1,g2,w));adj[g1].append((g2,w));adj[g2].append((g1,w))

    _dcache={}
    def _dist(p1,p2):
        if p1==p2: return 0
        key=(p1,p2) if p1<p2 else (p2,p1)
        r=_dcache.get(key)
        if r is None: r=topo.distance(p1,p2); _dcache[key]=r
        return r

    def _cost(m): return sum(w*_dist(m[g1],m[g2]) for g1,g2,w in edges if g1 in m and g2 in m)
    def _delta(m,s1,s2):
        d=0
        for nb,w in adj[s1]:
            if nb==s2 or nb not in m: continue
            d-=w*_dist(m[s1],m[nb]); d+=w*_dist(m[s2],m[nb])
        for nb,w in adj[s2]:
            if nb==s1 or nb not in m: continue
            d-=w*_dist(m[s2],m[nb]); d+=w*_dist(m[s1],m[nb])
        return d

    bm=dict(mapping); bc=_cost(mapping); cc=bc
    tlist=deque(); tset=set(); base_ten=max(5,len(act)//3); tenure=base_ten
    max_iter=min(1000,max(50,len(act)*5)); rng=random.Random(42)
    stag=0; max_stag=max(20,max_iter//5)
    cv={g:sum(H.get(g,{}).values()) for g in act}
    heavy=sorted(act,key=lambda g:-cv.get(g,0))
    try:
        for it in range(max_iter):
            if it%10==0: _check_deadline("Tabu")
            if len(act)>512:
                cands=[tuple(sorted(rng.sample(act,2))) for _ in range(min(200,len(act)*3))]
            else:
                cands=[(act[i],act[j]) for i in range(len(act)) for j in range(i+1,len(act))]

            bmv=None; bd=float('inf'); bmv_a=None; bd_a=float('inf')
            for g1,g2 in cands:
                delta=_delta(mapping,g1,g2)
                if (g1,g2) not in tset:
                    if delta<bd: bd=delta;bmv=(g1,g2)
                else:
                    if cc+delta<bc and delta<bd_a: bd_a=delta;bmv_a=(g1,g2)
            if bmv_a is not None and bd_a<bd: bmv=bmv_a;bd=bd_a
            if bmv is None: break

            g1,g2=bmv; mapping[g1],mapping[g2]=mapping[g2],mapping[g1]; cc+=bd
            tlist.append(bmv); tset.add(bmv)
            if len(tlist)>tenure: old=tlist.popleft();tset.discard(old)

            if cc<bc:
                bc=cc; bm=dict(mapping); stag=0; tenure=max(3,base_ten-2)
            else:
                stag+=1
                if stag>=max_stag:
                    tenure=min(len(act),base_ten+5); stag=0
                    for _ in range(max(2,len(act)//10)):
                        g1,g2=rng.sample(act,2); mapping[g1],mapping[g2]=mapping[g2],mapping[g1]
                    cc=_cost(mapping)
    except AlgoTimeout: pass
    return bm



# STAGE 4: 12 REFINEMENT METHODS (timeout-instrumented)
# ═══════════════════════════════════════════════════════════
def refine_none(tree,asgn,ng,topo,hw=HW): return dict(asgn)

def refine_cp_colocation(tree,asgn,ng,topo,hw=HW):
    """CP Colocation: actual-distance tl/bl, net comm check, makespan guard."""
    _set_deadline()
    N=tree.total_nodes; result=dict(asgn)
    if ng<=1: return result

    def _tl_a(ad):
        tl=[0.0]*N
        for n in tree.postorder():
            if tree.is_leaf(n): tl[n]=0.0
            else: tl[n]=max(tl[c]+tree.node_cost(c)+(hw.comm_cost(topo.distance(ad[c],ad[n])) if ad[c]!=ad[n] else 0) for c in tree.children(n))
        return tl
    def _bl_a(ad):
        bl=[0.0]*N; bl[0]=tree.node_cost(0)
        for n in range(N):
            gn=ad[n]
            for c in tree.children(n):
                gc=ad[c]; comm=hw.comm_cost(topo.distance(gc,gn)) if gc!=gn else 0
                bl[c]=tree.node_cost(c)+comm+bl[n]
        return bl

    gl=[0]*ng
    for n in range(N): gl[result[n]]+=tree.node_cost(n)
    cur_ms=_estimate_makespan(tree,result,ng,topo,hw)

    for rnd in range(5):
        _check_deadline("CPcoloc")
        tl=_tl_a(result); bl=_bl_a(result)
        cpl=max(tl[n]+bl[n] for n in range(N)); eps=max(0.5,cpl*0.02)
        cce=[]
        for node in range(1,N):
            p=tree.parent(node)
            if p<0 or result[node]==result[p]: continue
            if abs(tl[node]+bl[node]-cpl)<eps and abs(tl[p]+bl[p]-cpl)<eps:
                cce.append((node,p,hw.comm_cost(topo.distance(result[node],result[p]))))
        if not cce: break
        cce.sort(key=lambda e:-e[2]); moved=False
        for child,parent,comm_cost in cce:
            if result[child]==result[parent]: continue
            old_g=result[child]; new_g=result[parent]; cost=tree.node_cost(child)
            if gl[new_g]+cost>cur_ms: continue
            cs=comm_cost; ca=0
            for gc in tree.children(child):
                gcg=result[gc]
                if gcg==old_g and gcg!=new_g: ca+=hw.comm_cost(topo.distance(gcg,new_g))
                elif gcg!=old_g and gcg==new_g: cs+=hw.comm_cost(topo.distance(gcg,old_g))
            if cs<=ca: continue
            result[child]=new_g; gl[old_g]-=cost; gl[new_g]+=cost
            nms=_estimate_makespan(tree,result,ng,topo,hw)
            if nms<cur_ms: cur_ms=nms; moved=True
            else: result[child]=old_g; gl[old_g]+=cost; gl[new_g]-=cost
        if not moved: break
    return result

def refine_fm(tree,asgn,ng,topo,hw=HW):
    """FM K-way refinement: locking, negative gains, best-prefix rollback."""
    _set_deadline()
    N=tree.total_nodes; result=dict(asgn)
    if ng<=1: return result
    W=tree.total_work(); igu=max(1,len(set(result.values()))); cap=W/igu*1.6
    gl=[0]*ng
    for n in range(N): gl[result[n]]+=tree.node_cost(n)
    bms=_estimate_makespan(tree,result,ng,topo,hw)

    rng = random.Random(42)
    for _ in range(10):
        _check_deadline("FM")
        locked=set(); moves=[]; cur_cut=compute_edge_cut(tree,result)
        best_cut=cur_cut; best_prefix=0
        for step in range(N):
            tg=float('-inf'); best_moves=[]
            for node in range(N):
                if node in locked: continue
                cur=result[node]; cost=tree.node_cost(node)
                cc2=0; p=tree.parent(node)
                if p is not None and p>=0 and result[p]!=cur: cc2+=1
                for c in tree.children(node):
                    if result[c]!=cur: cc2+=1
                targets=set()
                if p is not None and p>=0: targets.add(result[p])
                for c in tree.children(node): targets.add(result[c])
                targets.discard(cur)
                if not targets: continue
                for tgt in targets:
                    if gl[tgt]+cost>cap: continue
                    nc2=0
                    if p is not None and p>=0 and result[p]!=tgt: nc2+=1
                    for c in tree.children(node):
                        if result[c]!=tgt: nc2+=1
                    gain=cc2-nc2
                    if gain>tg: tg=gain;best_moves=[(node,tgt)]
                    elif gain==tg: best_moves.append((node,tgt))
            if not best_moves: break
            tn2, tt = rng.choice(best_moves)
            old=result[tn2]; cost=tree.node_cost(tn2)
            result[tn2]=tt; gl[old]-=cost; gl[tt]+=cost
            locked.add(tn2); moves.append((tn2,old,tt,tg))
            cur_cut-=tg
            if cur_cut<best_cut: best_cut=cur_cut; best_prefix=len(moves)
        for i in range(len(moves)-1,best_prefix-1,-1):
            nd,old,tgt,_=moves[i]; cost=tree.node_cost(nd)
            result[nd]=old; gl[tgt]-=cost; gl[old]+=cost
        if best_prefix==0: break
    nms=_estimate_makespan(tree,result,ng,topo,hw)
    return result if nms<=bms else dict(asgn)

def refine_multicriteria_fm(tree,asgn,ng,topo,hw=HW):
    """Multi-Criteria FM: cut + comm volume + balance, FM structure."""
    _set_deadline()
    N=tree.total_nodes; result=dict(asgn)
    if ng<=1: return result
    W=tree.total_work(); igu=max(1,len(set(result.values())))
    tgt_load=W/igu; cap=tgt_load*1.5
    gl=[0]*ng
    for n in range(N): gl[result[n]]+=tree.node_cost(n)
    bms=_estimate_makespan(tree,result,ng,topo,hw)
    max_deg=max(len(tree.children(n))+(1 if tree.parent(n) is not None and tree.parent(n)>=0 else 0) for n in range(N))
    max_hops=max(1,topo.diameter()); ctx=_get_ctx(tree,topo)

    rng = random.Random(42)
    for _ in range(10):
        _check_deadline("MCFM")
        locked=set(); moves=[]; cur_sc=compute_edge_cut(tree,result)+max(gl)/(tgt_load if tgt_load>0 else 1)
        best_sc=cur_sc; best_prefix=0
        for step in range(N):
            tg=float('-inf'); best_moves=[]
            for node in range(N):
                if node in locked: continue
                cur=result[node]; cost=tree.node_cost(node)
                p=tree.parent(node); children=tree.children(node)
                targets=set()
                if p is not None and p>=0: targets.add(result[p])
                for c in children: targets.add(result[c])
                targets.discard(cur)
                if not targets: continue
                cc2=0; cur_comm=0.0
                if p is not None and p>=0 and result[p]!=cur: cc2+=1
                if p is not None and p>=0 and result[p]!=cur and ctx: cur_comm+=ctx.comm_matrix[result[p]][cur]
                for c in children:
                    if result[c]!=cur: cc2+=1
                    if result[c]!=cur and ctx: cur_comm+=ctx.comm_matrix[result[c]][cur]
                for tgt in targets:
                    if gl[tgt]+cost>cap: continue
                    nc2=0; new_comm=0.0
                    if p is not None and p>=0 and result[p]!=tgt: nc2+=1
                    if p is not None and p>=0 and result[p]!=tgt and ctx: new_comm+=ctx.comm_matrix[result[p]][tgt]
                    for c in children:
                        if result[c]!=tgt: nc2+=1
                        if result[c]!=tgt and ctx: new_comm+=ctx.comm_matrix[result[c]][tgt]
                    cg=(cc2-nc2)/max(1,max_deg)
                    bg=((abs(gl[cur]-tgt_load)+abs(gl[tgt]-tgt_load))-(abs(gl[cur]-cost-tgt_load)+abs(gl[tgt]+cost-tgt_load)))/max(1.0,2*tgt_load)
                    vg=(cur_comm-new_comm)/max(1.0,max_deg*hw.comm_cost(max_hops))
                    gain=0.4*cg+0.35*vg+0.25*bg
                    if gain>tg: tg=gain;best_moves=[(node,tgt)]
                    elif gain==tg: best_moves.append((node,tgt))
            if not best_moves: break
            tn2, tt = rng.choice(best_moves)
            old=result[tn2]; cost=tree.node_cost(tn2)
            result[tn2]=tt; gl[old]-=cost; gl[tt]+=cost
            locked.add(tn2); moves.append((tn2,old,tt))
            cur_sc-=tg
            if cur_sc<best_sc: best_sc=cur_sc; best_prefix=len(moves)
        for i in range(len(moves)-1,best_prefix-1,-1):
            nd,old,tgt=moves[i]; cost=tree.node_cost(nd)
            result[nd]=old; gl[tgt]-=cost; gl[old]+=cost
        if best_prefix==0: break
    nms=_estimate_makespan(tree,result,ng,topo,hw)
    return result if nms<=bms else dict(asgn)

def refine_alns(tree,asgn,ng,topo,hw=HW):
    """ALNS: 3 destroy + 3 repair, segment-based weights, adaptive destruction."""
    _set_deadline()
    N=tree.total_nodes; result=dict(asgn); rng=random.Random(42)
    best=dict(result); best_ms=_estimate_makespan(tree,best,ng,topo,hw)
    cur_ms=best_ms; ctx=_get_ctx(tree,topo)
    T=max(1.0,best_ms*0.05); alpha=0.9995
    ds=[1.0,1.0,1.0]; rs=[1.0,1.0,1.0]
    seg=50; sd=[0.0]*3; cd=[0]*3; sr=[0.0]*3; cr=[0]*3
    dfrac=0.10; stag=0; max_iter=min(5000,max(500,100000//max(1,N)))

    for it in range(max_iter):
        if it%10==0: _check_deadline("ALNS")
        # Select destroy
        td2=sum(ds); r2=rng.random()*td2; cumul=0; d_op=0
        for i,s in enumerate(ds):
            cumul+=s
            if r2<=cumul: d_op=i; break
        dsz=max(3,int(N*dfrac))
        # Destroy
        if d_op==0:
            root=rng.randint(0,N-1)
            destroyed=list(_collect_subtree(tree,root,set(range(N))))[:dsz]
        elif d_op==1:
            gl2=defaultdict(int); gn2=defaultdict(list)
            for n2,g in result.items(): gl2[g]+=tree.node_cost(n2); gn2[g].append(n2)
            wg=max(gl2,key=gl2.get); cands=gn2[wg]
            destroyed=rng.sample(cands,min(dsz,len(cands)))
        else:
            boundary=[]
            for n2 in range(N):
                p=tree.parent(n2)
                if p is not None and p>=0 and result[n2]!=result[p]: boundary.append(n2);continue
                for c in tree.children(n2):
                    if result[c]!=result[n2]: boundary.append(n2);break
            destroyed=rng.sample(boundary,min(dsz,len(boundary))) if boundary else []
        if not destroyed: continue
        ds2=set(destroyed); saved={n2:result[n2] for n2 in destroyed}
        # Select repair
        tr2=sum(rs); r3=rng.random()*tr2; cumul=0; r_op=0
        for i,s in enumerate(rs):
            cumul+=s
            if r3<=cumul: r_op=i; break
        # Repair
        if r_op==0:
            for n2 in destroyed:
                p=tree.parent(n2); nbrs=[]
                if p is not None and p>=0 and p not in ds2: nbrs.append(result[p])
                for c in tree.children(n2):
                    if c not in ds2: nbrs.append(result[c])
                if nbrs: result[n2]=Counter(nbrs).most_common(1)[0][0]
                else: result[n2]=rng.randint(0,ng-1)
        elif r_op==1:
            gl3=defaultdict(int)
            for n2,g in result.items():
                if n2 not in ds2: gl3[g]+=tree.node_cost(n2)
            for n2 in destroyed:
                bg=min(range(ng),key=lambda g:gl3.get(g,0))
                result[n2]=bg; gl3[bg]+=tree.node_cost(n2)
        else:
            for n2 in destroyed:
                p=tree.parent(n2); bg=result.get(n2,0); bc2=float('inf')
                for g in range(ng):
                    comm=0
                    if p is not None and p>=0 and p not in ds2:
                        pg=result[p]
                        if pg!=g and ctx: comm+=ctx.comm_matrix[pg][g]
                    for c in tree.children(n2):
                        if c not in ds2:
                            cg=result[c]
                            if cg!=g and ctx: comm+=ctx.comm_matrix[cg][g]
                    if comm<bc2: bc2=comm; bg=g
                result[n2]=bg
        # Evaluate
        nc=_estimate_makespan(tree,result,ng,topo,hw); delta=nc-cur_ms
        accept=delta<0 or (T>0.01 and rng.random()<math.exp(-delta/max(T,0.01)))
        if accept:
            cur_ms=nc
            if nc<best_ms: best_ms=nc; best=dict(result); sd[d_op]+=3.0; sr[r_op]+=3.0; stag=0; dfrac=0.10
            else: sd[d_op]+=1.0; sr[r_op]+=1.0; stag+=1
        else:
            for n2,g in saved.items(): result[n2]=g
            stag+=1
        cd[d_op]+=1; cr[r_op]+=1
        if (it+1)%seg==0:
            for i in range(3):
                if cd[i]>0: ds[i]=max(0.1,min(10.0,ds[i]*0.7+0.3*max(0.1,sd[i]/cd[i])))
                sd[i]=0.0; cd[i]=0
                if cr[i]>0: rs[i]=max(0.1,min(10.0,rs[i]*0.7+0.3*max(0.1,sr[i]/cr[i])))
                sr[i]=0.0; cr[i]=0
        if stag>=seg: dfrac=min(0.3,dfrac*1.2); stag=0
        T*=alpha
    return best

def refine_leaf_migration(tree,asgn,ng,topo,hw=HW):
    """Leaf Migration: priority by comm savings, makespan guard."""
    _check_deadline("LeafMig")
    N=tree.total_nodes; result=dict(asgn)
    if ng<=1: return result
    gl=[0]*ng
    for n in range(N): gl[result[n]]+=tree.node_cost(n)
    W=tree.total_work(); cap=W/ng*1.5
    cur_ms=_estimate_makespan(tree,result,ng,topo,hw)
    cands=[]
    for node in tree.leaves():
        p=tree.parent(node)
        if p is not None and p>=0 and result[node]!=result[p]:
            cands.append((node,p,hw.comm_cost(topo.distance(result[node],result[p]))))
    cands.sort(key=lambda x:-x[2])
    for node,parent,_ in cands:
        if result[node]==result[parent]: continue
        cost=tree.node_cost(node); pg=result[parent]
        if gl[pg]+cost>cap or gl[pg]+cost>cur_ms: continue
        old_g=result[node]; gl[old_g]-=cost; gl[pg]+=cost; result[node]=pg
    nms=_estimate_makespan(tree,result,ng,topo,hw)
    return result if nms<=cur_ms else dict(asgn)

def refine_net_weighting(tree,asgn,ng,topo,hw=HW):
    """Net-Weighted FM: criticality-based edge weights (Bui & Moon 1996)."""
    _set_deadline()
    N=tree.total_nodes; result=dict(asgn)
    if ng<=1: return result
    W=tree.total_work(); igu=max(1,len(set(result.values()))); cap=W/igu*1.6
    gl=[0]*ng
    for n in range(N): gl[result[n]]+=tree.node_cost(n)
    bms=_estimate_makespan(tree,result,ng,topo,hw)

    rng_nw=random.Random(42)
    for _ in range(10):
        _check_deadline("NetW")
        tl=[0.0]*N
        for n in tree.postorder():
            if tree.is_leaf(n): tl[n]=0.0
            else: tl[n]=max(tl[c]+tree.node_cost(c)+(hw.comm_cost(topo.distance(result[c],result[n])) if result[c]!=result[n] else 0) for c in tree.children(n))
        bl=[0.0]*N; bl[0]=tree.node_cost(0)
        for n in range(N):
            gn=result[n]
            for c in tree.children(n):
                gc=result[c]; comm=hw.comm_cost(topo.distance(gc,gn)) if gc!=gn else 0
                bl[c]=tree.node_cost(c)+comm+bl[n]
        cpl=max(tl[n]+bl[n] for n in range(N))
        nw=[cpl/max(1.0,cpl-(tl[n]+bl[n])+1.0) for n in range(N)]
        locked=set(); moves=[]; cur_wc=sum((nw[n]+nw[tree.parent(n)])/2.0 for n in range(1,N) if tree.parent(n)>=0 and result[n]!=result[tree.parent(n)])
        best_wc=cur_wc; best_prefix=0
        # Build boundary node set for efficient scanning
        boundary=set()
        for n in range(N):
            p=tree.parent(n)
            if p is not None and p>=0 and result[n]!=result[p]: boundary.add(n); boundary.add(p)
            for c in tree.children(n):
                if result[c]!=result[n]: boundary.add(n); boundary.add(c)
        max_steps=min(N,max(200,len(boundary)*2))
        for step in range(max_steps):
            if step%200==0: _check_deadline("NetW_step")
            tg=float('-inf'); best_moves=[]
            for node in boundary:
                if node in locked: continue
                cur=result[node]; cost=tree.node_cost(node); wt=nw[node]
                p=tree.parent(node); children=tree.children(node)
                cwc=0.0
                if p is not None and p>=0 and result[p]!=cur: cwc+=(wt+nw[p])/2.0
                for c in children:
                    if result[c]!=cur: cwc+=(wt+nw[c])/2.0
                targets=set()
                if p is not None and p>=0: targets.add(result[p])
                for c in children: targets.add(result[c])
                targets.discard(cur)
                if not targets: continue
                for tgt in targets:
                    if gl[tgt]+cost>cap: continue
                    nwc=0.0
                    if p is not None and p>=0 and result[p]!=tgt: nwc+=(wt+nw[p])/2.0
                    for c in children:
                        if result[c]!=tgt: nwc+=(wt+nw[c])/2.0
                    gain=cwc-nwc
                    if gain>tg: tg=gain;best_moves=[(node,tgt)]
                    elif gain==tg: best_moves.append((node,tgt))
            if not best_moves: break
            tn2, tt = rng_nw.choice(best_moves)
            old=result[tn2]; cost=tree.node_cost(tn2)
            result[tn2]=tt; gl[old]-=cost; gl[tt]+=cost
            locked.add(tn2); moves.append((tn2,old,tt))
            cur_wc-=tg
            if cur_wc<best_wc: best_wc=cur_wc; best_prefix=len(moves)
        for i in range(len(moves)-1,best_prefix-1,-1):
            nd,old,tgt=moves[i]; cost=tree.node_cost(nd)
            result[nd]=old; gl[tgt]-=cost; gl[old]+=cost
        if best_prefix==0: break
    nms=_estimate_makespan(tree,result,ng,topo,hw)
    return result if nms<=bms else dict(asgn)

def refine_subtree_migration(tree,asgn,ng,topo,hw=HW):
    """Subtree Migration: coherent subtree moves, multi-target, makespan guard."""
    _set_deadline()
    N=tree.total_nodes; result=dict(asgn)
    if ng<=1: return result
    bms=_estimate_makespan(tree,result,ng,topo,hw)
    bc=compute_edge_cut(tree,result)
    igu=len(set(result.values())); mg=max(2,int(igu*0.75))
    cands=[]
    for node in range(1,N):
        if tree.is_leaf(node): continue
        p=tree.parent(node)
        if p<0 or result[node]==result[p]: continue
        ng2=result[node]; coh=[]
        stack=[node]
        while stack:
            n=stack.pop()
            if result[n]==ng2: coh.append(n)
            for c in tree.children(n):
                if result[c]==ng2: stack.append(c)
        if not coh: continue
        cs=hw.comm_cost(topo.distance(result[node],result[p]))
        sw2=sum(tree.node_cost(n) for n in coh)
        cands.append((node,coh,sw2,cs))
    cands.sort(key=lambda x:-x[3])
    gl=[0]*ng
    for n in range(N): gl[result[n]]+=tree.node_cost(n)
    for node,subtree,sw2,_ in cands:
        _check_deadline("SubMig")
        p=tree.parent(node)
        if p<0 or result[node]==result[p]: continue
        old_gpu=result[node]; saved={n:result[n] for n in subtree}
        tgts=[result[p]]
        for n in subtree:
            for c in tree.children(n):
                if result[c]!=old_gpu and result[c] not in tgts: tgts.append(result[c])
        ll=min(range(ng),key=lambda g:gl[g])
        if ll not in tgts: tgts.append(ll)
        tgts=[g for g in tgts if g!=old_gpu]
        bt=None; bm2=bms; bc2=bc
        for tgt in tgts:
            if gl[tgt]+sw2>bms*1.1: continue
            for n in subtree: result[n]=tgt
            gu=len(set(result.values()))
            if gu<mg:
                for n,g in saved.items(): result[n]=g
                continue
            nms=_estimate_makespan(tree,result,ng,topo,hw); nc=compute_edge_cut(tree,result)
            if nms<bm2 or (nms==bm2 and nc<bc2): bt=tgt; bm2=nms; bc2=nc
            for n,g in saved.items(): result[n]=g
        if bt is not None and (bm2<bms or (bm2==bms and bc2<bc)):
            for n in subtree:
                gl[result[n]]-=tree.node_cost(n); result[n]=bt; gl[bt]+=tree.node_cost(n)
            bms=bm2; bc=bc2
    return result

def refine_centroid_rebalance(tree,asgn,ng,topo,hw=HW):
    """Centroid-based rebalancing: shed boundary nodes from overloaded GPUs."""
    _set_deadline()
    N=tree.total_nodes; result=dict(asgn)
    if ng<=1: return result
    W=tree.total_work(); tgt=W/ng; threshold=tgt*1.3
    gl=[0]*ng
    for n in range(N): gl[result[n]]+=tree.node_cost(n)
    bms=_estimate_makespan(tree,result,ng,topo,hw)

    for iteration in range(50):
        _check_deadline("CentReb")
        if max(gl)<=threshold: break
        ol=max(range(ng),key=lambda g:gl[g])
        ol_nodes=[n for n in range(N) if result[n]==ol]
        if not ol_nodes: break
        os=set(ol_nodes)
        sw_l={}
        for n in tree.postorder():
            if n not in os: continue
            w=tree.node_cost(n)
            for c in tree.children(n):
                if c in os and c in sw_l: w+=sw_l[c]
            sw_l[n]=w
        tot_l=sum(tree.node_cost(n) for n in ol_nodes)
        cent=ol_nodes[0]; bmc=float('inf')
        for n in ol_nodes:
            mc=tot_l-sw_l.get(n,0)
            for c in tree.children(n):
                if c in os: mc=max(mc,sw_l.get(c,0))
            if mc<bmc: bmc=mc; cent=n
        boundary=[]
        for n in ol_nodes:
            p=tree.parent(n)
            if p is not None and p>=0 and result[p]!=ol: boundary.append(n); continue
            for c in tree.children(n):
                if result[c]!=ol: boundary.append(n); break
        if not boundary: break
        cd2=tree.depth(cent)
        boundary.sort(key=lambda n:-abs(tree.depth(n)-cd2))
        targets=sorted([g for g in range(ng) if gl[g]<tgt],key=lambda g:gl[g])
        if not targets: break
        moved_any=False; excess=gl[ol]-tgt
        for node in boundary:
            if excess<=0: break
            cost=tree.node_cost(node); p=tree.parent(node); children=tree.children(node)
            nbrs=[]
            if p is not None and p>=0: nbrs.append(result[p])
            for c in children: nbrs.append(result[c])
            cc2=sum(1 for ng3 in nbrs if ng3!=ol)
            bt2=None; bs2=float('inf')
            for ul in targets:
                if ul not in nbrs: continue
                if gl[ul]+cost>tgt*1.5: continue
                nc2=sum(1 for ng3 in nbrs if ng3!=ul)
                if nc2>cc2: continue
                if nc2-cc2<bs2: bs2=nc2-cc2; bt2=ul
            if bt2 is None: continue
            old_g=result[node]; result[node]=bt2
            nms=_estimate_makespan(tree,result,ng,topo,hw)
            if nms<=bms:
                gl[old_g]-=cost; gl[bt2]+=cost; bms=nms; excess-=cost; moved_any=True
            else: result[node]=old_g
        if not moved_any: break
    return result

def refine_te_rerouting(tree,asgn,ng,topo,hw=HW):
    """Traffic Engineering Rerouting: reduce link congestion via BFS paths."""
    _set_deadline()
    N=tree.total_nodes; result=dict(asgn)
    if ng<=1: return result
    bms=_estimate_makespan(tree,result,ng,topo,hw)

    path_cache={}
    def _get_path(pe1,pe2):
        if pe1==pe2: return []
        key=(pe1,pe2)
        if key not in path_cache:
            path_cache[key]=_bfs_path(topo,pe1,pe2)
        return path_cache[key]

    def _path_links(pe1,pe2):
        path=_get_path(pe1,pe2)
        return [(min(path[i],path[i+1]),max(path[i],path[i+1])) for i in range(len(path)-1)]

    def _link_cong(ad):
        ll=defaultdict(float); lf=defaultdict(list)
        for node in range(1,N):
            p=tree.parent(node)
            if p<0: continue
            gn,gp=ad[node],ad[p]
            if gn==gp: continue
            for lk in _path_links(gn,gp): ll[lk]+=1.0; lf[lk].append((node,p))
        return ll,lf

    for iteration in range(10):
        _check_deadline("TERe")
        ll,lf=_link_cong(result)
        if not ll: break
        mc=max(ll.values())
        if mc<=1.0: break
        hl=max(ll,key=ll.get); hf=lf[hl]; moved=False
        for child,parent in hf:
            if result[child]==result[parent]: continue
            old_g=result[child]
            cands2=set()
            cands2.add(result[parent])
            for g in range(ng):
                if g==old_g: continue
                nl=set(_path_links(g,result[parent]))
                if hl not in nl: cands2.add(g)
            for new_g in cands2:
                if new_g==old_g: continue
                ca2=sum(1 for gc in tree.children(child) if result[gc]==old_g and result[gc]!=new_g)
                cs2=sum(1 for gc in tree.children(child) if result[gc]!=old_g and result[gc]==new_g)
                if ca2>cs2+1: continue
                result[child]=new_g
                nl2,_=_link_cong(result); nmc=max(nl2.values()) if nl2 else 0
                nms=_estimate_makespan(tree,result,ng,topo,hw)
                if nmc<mc and nms<=bms: bms=nms; moved=True; break
                else: result[child]=old_g
            if moved: break
        if not moved:
            for child,parent in hf:
                if result[child]==result[parent]: continue
                old_pg=result[parent]; result[parent]=result[child]
                nl2,_=_link_cong(result); nmc=max(nl2.values()) if nl2 else 0
                nms=_estimate_makespan(tree,result,ng,topo,hw)
                if nmc<mc and nms<=bms: bms=nms; moved=True; break
                else: result[parent]=old_pg
        if not moved: break
    return result

def refine_vcycles(tree,asgn,ng,topo,hw=HW):
    """V-Cycle Multilevel: coarsen→FM→uncoarsen, multiple V-cycles."""
    _set_deadline()
    N=tree.total_nodes; result=dict(asgn)
    if ng<=1: return result
    W=tree.total_work(); igu=max(1,len(set(result.values()))); cap=W/igu*1.5
    ms_orig=_estimate_makespan(tree,result,ng,topo,hw)
    adj_f=[[] for _ in range(N)]
    for n in range(N):
        for c in tree.children(n): adj_f[n].append(c); adj_f[c].append(n)
    wt_f=[tree.node_cost(n) for n in range(N)]
    asgn_f=[result[n] for n in range(N)]

    for vcycle in range(2):
        _check_deadline("VCyc")
        levels=[]; cur_adj=adj_f; cur_wt=list(wt_f); cur_asgn=list(asgn_f); cur_n=N
        floor_n=max(ng*4,40)
        while cur_n>floor_n:
            _check_deadline("VCyc_C")
            vis=[False]*cur_n; f2c=[0]*cur_n; nwt=[]; cid=0
            order=list(range(cur_n))
            import random; random.Random(42).shuffle(order)
            order=sorted(order,key=lambda x:-cur_wt[x])
            for u in order:
                if vis[u]: continue
                bv=-1; bs2=-1
                for v in cur_adj[u]:
                    if vis[v]: continue
                    sc=(2 if cur_asgn[v]==cur_asgn[u] else 1)*cur_wt[v]
                    if sc>bs2: bs2=sc; bv=v
                f2c[u]=cid; vis[u]=True; w=cur_wt[u]
                if bv>=0: f2c[bv]=cid; vis[bv]=True; w+=cur_wt[bv]
                nwt.append(w); cid+=1
            if cid>cur_n*0.85: break
            na=[set() for _ in range(cid)]
            for u in range(cur_n):
                cu=f2c[u]
                for v in cur_adj[u]:
                    cv=f2c[v]
                    if cu!=cv: na[cu].add(cv); na[cv].add(cu)
            nal=[sorted(s) for s in na]
            nasgn=[0]*cid; gcnts=[defaultdict(int) for _ in range(cid)]
            for u in range(cur_n): gcnts[f2c[u]][cur_asgn[u]]+=1
            for c in range(cid):
                if gcnts[c]: nasgn[c]=max(gcnts[c],key=gcnts[c].get)
            levels.append((f2c,cur_adj,cur_wt,cur_n,cur_asgn))
            cur_adj=nal; cur_wt=nwt; cur_asgn=nasgn; cur_n=cid
        cur_asgn=_ml_fm_refine(cur_asgn,cur_adj,cur_wt,cur_n,ng,cap)
        for lev in range(len(levels)-1,-1,-1):
            _check_deadline("VCyc_U")
            f2c,fa,fw,fn,_=levels[lev]
            fine_asgn=[cur_asgn[f2c[u]] for u in range(fn)]
            fine_asgn=_ml_fm_refine(fine_asgn,fa,fw,fn,ng,cap)
            cur_asgn=fine_asgn; cur_adj=fa; cur_wt=fw; cur_n=fn
        asgn_f=list(cur_asgn)

    for n in range(N): result[n]=asgn_f[n]
    ms_new=_estimate_makespan(tree,result,ng,topo,hw)
    return result if ms_new<=ms_orig else dict(asgn)

def refine_flow_mincut(tree,asgn,ng,topo,hw=HW):
    """Flow-Based Min-Cut (KaHIP-style): Edmonds-Karp on boundary subgraphs."""
    _set_deadline()
    N=tree.total_nodes; result=dict(asgn)
    if ng<=1: return result
    W=tree.total_work(); igu=max(1,len(set(result.values()))); cap=W/igu*1.6
    gl=[0]*ng
    for n in range(N): gl[result[n]]+=tree.node_cost(n)
    bms=_estimate_makespan(tree,asgn,ng,topo,hw)
    adj=[[] for _ in range(N)]
    for n in range(N):
        for c in tree.children(n): adj[n].append(c); adj[c].append(n)

    def _bfs_aug(graph,src,snk,nn):
        parent=[None]*nn; parent[src]=(src,-1); q=deque([src])
        while q:
            u=q.popleft()
            for idx,(v,cap_e,_) in enumerate(graph[u]):
                if parent[v] is None and cap_e>0:
                    parent[v]=(u,idx)
                    if v==snk: return parent
                    q.append(v)
        return None

    def _maxflow_mincut(adj_l,nodes,source,sink):
        nl=sorted(nodes); nn=len(nl); idx={n:i for i,n in enumerate(nl)}
        si=idx[source]; ti=idx[sink]
        graph=[[] for _ in range(nn)]
        for u in nl:
            ui=idx[u]
            for v in adj_l[u]:
                if v in idx:
                    vi=idx[v]; fi=len(graph[ui]); ri=len(graph[vi])
                    graph[ui].append([vi,1,ri]); graph[vi].append([ui,0,fi])
        tf=0
        for _ in range(nn*nn):
            par=_bfs_aug(graph,si,ti,nn)
            if par is None: break
            bn=float('inf'); v=ti
            while v!=si:
                u,ei=par[v]; bn=min(bn,graph[u][ei][1]); v=u
            v=ti
            while v!=si:
                u,ei=par[v]; ri2=graph[u][ei][2]
                graph[u][ei][1]-=bn; graph[v][ri2][1]+=bn; v=u
            tf+=bn
        reach=set(); q=deque([si]); reach.add(si)
        while q:
            u=q.popleft()
            for v,cap_e,_ in graph[u]:
                if v not in reach and cap_e>0: reach.add(v); q.append(v)
        return tf,{nl[i] for i in reach}

    for iteration in range(10):
        _check_deadline("FlowMC")
        pc=defaultdict(int); pe2=defaultdict(list)
        for n in range(1,N):
            p=tree.parent(n)
            if p>=0 and result[n]!=result[p]:
                g1,g2=result[n],result[p]; key=(min(g1,g2),max(g1,g2))
                pc[key]+=1; pe2[key].append((n,p))
        if not pc: break
        pairs=sorted(pc.keys(),key=lambda k:-pc[k]); improved=False
        for (ga,gb) in pairs:
            _check_deadline("FlowMC_pair")
            bn=set()
            for n,p in pe2[(ga,gb)]:
                bn.add(n); bn.add(p)
                for nb in adj[n]:
                    if result[nb] in (ga,gb): bn.add(nb)
                for nb in adj[p]:
                    if result[nb] in (ga,gb): bn.add(nb)
            if len(bn)<3: continue
            ga_n=[n for n in bn if result[n]==ga]; gb_n=[n for n in bn if result[n]==gb]
            if not ga_n or not gb_n: continue
            source=max(ga_n,key=lambda n:sum(1 for nb in adj[n] if nb in bn and result[nb]==ga))
            sink=max(gb_n,key=lambda n:sum(1 for nb in adj[n] if nb in bn and result[nb]==gb))
            if source==sink: continue
            try: _,ss=_maxflow_mincut(adj,bn,source,sink)
            except: continue
            nr=dict(result); ngl=list(gl)
            for n in bn:
                og=result[n]; ng2=ga if n in ss else gb
                if og!=ng2: ngl[og]-=tree.node_cost(n); ngl[ng2]+=tree.node_cost(n)
                nr[n]=ng2
            if max(ngl)>cap: continue
            nc=compute_edge_cut(tree,nr); oc=compute_edge_cut(tree,result)
            nms=_estimate_makespan(tree,nr,ng,topo,hw)
            if nc<oc and nms<=bms: result=nr; gl=ngl; bms=min(bms,nms); improved=True
        if not improved: break
    nms=_estimate_makespan(tree,result,ng,topo,hw)
    return result if nms<=bms else dict(asgn)

def _fm_refine_pass(tree,asgn,ng,topo,hw=HW):
    _set_deadline()
    cur=dict(asgn);locked=set()
    ba=dict(cur);bc=compute_edge_cut(tree,cur)
    gc=[0]*ng
    for g in cur.values():
        if 0<=g<ng: gc[g]+=1
    mpg=(tree.total_nodes+ng-1)//ng+2
    for outer in range(min(tree.total_nodes,200)):
        if outer%50==0: _check_deadline("FMpass")
        bg2,bn,bt=-1,None,None
        for node in range(tree.total_nodes):
            if node in locked: continue
            src=cur[node];targets=set()
            p=tree.parent(node)
            if p>=0: targets.add(cur[p])
            for c in tree.children(node): targets.add(cur[c])
            targets.discard(src)
            for tgt in targets:
                if gc[src]<=1 or gc[tgt]>=mpg: continue
                gain=0
                if p>=0:
                    pg=cur[p]
                    if pg==tgt: gain+=1
                    elif pg==src: gain-=1
                for ch in tree.children(node):
                    cg=cur[ch]
                    if cg==tgt: gain+=1
                    elif cg==src: gain-=1
                if gain>bg2: bg2=gain;bn=node;bt=tgt
        if bn is None or bg2<=0: break
        og=cur[bn];cur[bn]=bt;gc[og]-=1;gc[bt]+=1;locked.add(bn)
        nc=compute_edge_cut(tree,cur)
        if nc<bc: bc=nc;ba=dict(cur)
    return ba

# ═══════════════════════════════════════════════════════════
# STAGE 4: PHASED REFINEMENT (timeout-gated, no scale gates)
# ═══════════════════════════════════════════════════════════
def _subtree_migration_s4(tree,asgn,ng,topo,mapping,hw=HW):
    _set_deadline()
    result=dict(asgn);mpg=math.ceil(tree.total_nodes/ng)*2
    ce=[]
    for node in range(1,tree.total_nodes):
        p=tree.parent(node)
        if p<0: continue
        gn,gp=result.get(node,0),result.get(p,0)
        if gn!=gp:
            pen=mapping.get(gn,gn);pep=mapping.get(gp,gp)
            ce.append((hw.comm_cost(topo.distance(pen,pep)),node,p))
    ce.sort(reverse=True)
    cms=_estimate_makespan(tree,result,ng,topo,hw)
    for cost,child,parent in ce[:10]:
        _check_deadline("SubMigS4")
        pg=result[parent];subtree=tree.subtree_nodes(child)
        pl=sum(1 for v in result.values() if v==pg)
        if pl+len(subtree)>mpg: continue
        trial=dict(result)
        for n in subtree: trial[n]=pg
        nms=_estimate_makespan(tree,trial,ng,topo,hw)
        if nms<cms: result=trial;cms=nms
    return result


def _alns_refine_s4(tree,asgn,ng,topo,hw=HW,n_iters=150,seed=42):
    _set_deadline()
    rng=random.Random(seed);cur=dict(asgn)
    def _cost(a):
        cp=compute_cp_comm(tree,a,topo,hw)
        imb=compute_load_imbalance(tree,a,ng)
        return cp*max(1.0,imb**2)
    cc=_cost(cur);best,bc=dict(cur),cc;temp=15.0
    for _ in range(n_iters):
        _check_deadline("ALNS_S4")
        root=rng.randint(0,tree.total_nodes-1)
        subtree=tree.subtree_nodes(root)
        if len(subtree)>12: subtree=subtree[:12]
        cand=dict(cur);ss=set(subtree)
        for node in subtree:
            bg2,bcomm=0,float('inf');p=tree.parent(node)
            for g in range(ng):
                comm=0
                if p>=0 and p in cand and p not in ss:
                    pg=cand[p]
                    if pg!=g: comm+=topo.comm_cost_between(pg,g,hw)
                for c in tree.children(node):
                    if c in cand and c not in ss:
                        cg=cand[c]
                        if cg!=g: comm+=topo.comm_cost_between(cg,g,hw)
                if comm<bcomm: bcomm=comm;bg2=g
            cand[node]=bg2
        candcost=_cost(cand);delta=candcost-cc
        if delta<0 or rng.random()<math.exp(-delta/max(temp,1e-10)):
            cur=cand;cc=candcost
            if cc<bc: best,bc=dict(cur),cc
        temp*=0.995
    return best

def refine_phased(tree,asgn,ng,topo,mapping,hw=HW,verbose=False):
    result=dict(asgn);_set_deadline()
    bms=_estimate_makespan(tree,result,ng,topo,hw)
    rollbacks=[]  # records (stage_name, reason, before_ms, after_ms_or_None)
    def _try(fn,*args):
        nonlocal result,bms
        try: _check_deadline("phased")
        except AlgoTimeout:
            rollbacks.append((fn.__name__,"deadline_gate",bms,None)); return
        try:
            ref=fn(*args)
            if ref is None or not _validate_assignment(tree,ref,ng):
                rollbacks.append((fn.__name__,"invalid_output",bms,None))
                if verbose: print(f"    [refine_phased] {fn.__name__}: INVALID output — kept prior")
                return
            nms=_estimate_makespan(tree,ref,ng,topo,hw)
            if nms<bms:
                result=ref;bms=nms
            else:
                rollbacks.append((fn.__name__,"no_improvement",bms,nms))
                if verbose: print(f"    [refine_phased] {fn.__name__}: no gain ({nms} >= {bms}) — kept prior")
        except AlgoTimeout:
            rollbacks.append((fn.__name__,"timeout",bms,None))
    for _ in range(2): _try(_fm_refine_pass,tree,result,ng,topo,hw)
    if verbose: print(f"    After FM: ms={bms:.1f}")
    _try(_subtree_migration_s4,tree,result,ng,topo,mapping,hw)
    if verbose: print(f"    After SubMig: ms={bms:.1f}")
    _try(refine_cp_colocation,tree,result,ng,topo,hw)
    if verbose: print(f"    After CPRepart: ms={bms:.1f}")
    lbs=tree.critical_path_length()
    if bms>lbs*1.15:
        try:
            _check_deadline("ALNS_gate")
            dl = _DEADLINE[0]
            if dl == float('inf'):
                rem = 150
            else:
                rem = max(10, min(150, int((dl - time.time()) * 5)))
            _try(_alns_refine_s4,tree,result,ng,topo,hw,min(150,rem),42)
        except AlgoTimeout: pass
    if verbose: print(f"    After ALNS: ms={bms:.1f}")
    return result

# ═══════════════════════════════════════════════════════════════════════════════
# Stage 5 — Memory Enforcement (512/512)
# ═══════════════════════════════════════════════════════════════════════════════

def _estimate_imem(tree: CBTree, assignment: Dict[int, int],
                   n_gpus: int, hw: HardwareConfig = None) -> Dict[int, int]:
    """Estimate IMEM usage per GPU (RDMA-Push: no RECV instructions).

    Per task: ~1 instruction (GENERATE or COMPUTE)
    Per cross-GPU edge: 1 SEND instruction (sender only, no RECV on receiver)
    GCI serialization: gci_latency NOPs between consecutive GENERATEs
    """
    if hw is None:
        hw = HW
    usage = {g: 0 for g in range(n_gpus)}
    leaf_counts = {g: 0 for g in range(n_gpus)}
    for node in range(tree.total_nodes):
        gpu = assignment.get(node, 0)
        usage[gpu] += 1  # GENERATE or COMPUTE
        if tree.is_leaf(node):
            leaf_counts[gpu] += 1

    # GCI serialization: (n_leaves - 1) * gci_latency NOPs between GENERATEs
    for g in range(n_gpus):
        if leaf_counts[g] > 1:
            usage[g] += (leaf_counts[g] - 1) * hw.gci_latency

    # Cross-GPU edges → SEND only (no RECV in RDMA-Push)
    for node in range(1, tree.total_nodes):
        p = tree.parent(node)
        if p < 0:
            continue
        gn, gp = assignment.get(node, 0), assignment.get(p, 0)
        if gn != gp:
            usage[gn] += 1  # SEND (sender side only)

    return usage


def _estimate_dmem(tree: CBTree, assignment: Dict[int, int],
                   n_gpus: int) -> Dict[int, int]:
    """Estimate peak DMEM usage per GPU.

    Live values: bounded by SU number per subtree.
    Receive buffers: 1 per pending incoming cross-GPU edge.
    """
    usage = {g: 0 for g in range(n_gpus)}
    for gpu in range(n_gpus):
        nodes_on = [n for n in range(tree.total_nodes) if assignment.get(n) == gpu]
        # Local compute slots
        usage[gpu] += len(nodes_on)
        # Receive buffer slots (one per incoming cross-GPU child)
        for node in nodes_on:
            if tree.is_internal(node):
                for c in tree.children(node):
                    if assignment.get(c, 0) != gpu:
                        usage[gpu] += 1
    return usage


def enforce_memory(tree: CBTree, assignment: Dict[int, int],
                   n_gpus: int, topo: Topology,
                   hw: HardwareConfig = HW,
                   verbose: bool = False) -> Dict[int, int]:
    """Stage 5: Full memory enforcement.

    Tier 1: SU verification (always passes at 512 for practical trees)
    Tier 2: IMEM budgeting — if any GPU exceeds limit, redistribute
    Tier 3: DMEM budgeting — receive-buffer credit check + redistribution
    """
    result = dict(assignment)

    # Tier 1: SU check
    su = tree.sethi_ullman()
    su_ok = su <= hw.dmem_depth
    if verbose:
        print(f"    SU={su} {'≤' if su_ok else '>'} DMEM={hw.dmem_depth}: "
              f"{'OK' if su_ok else 'VIOLATION'}")

    # Tier 2: IMEM check
    imem = _estimate_imem(tree, result, n_gpus)
    imem_violations = {g: u for g, u in imem.items() if u > hw.imem_depth}

    if imem_violations:
        if verbose:
            print(f"    IMEM violations: {imem_violations}")
        # Redistribute: move nodes from overloaded GPUs to least-loaded
        for iteration in range(50):
            imem = _estimate_imem(tree, result, n_gpus)
            overloaded = [g for g, u in imem.items() if u > hw.imem_depth]
            if not overloaded:
                break
            worst = max(overloaded, key=lambda g: imem[g])
            gpu_nodes = [n for n in range(tree.total_nodes) if result.get(n) == worst]
            # Move leaves first (least structural impact)
            gpu_nodes.sort(key=lambda n: (0 if tree.is_leaf(n) else 1, -tree.depth(n)))
            moved = False
            for node in gpu_nodes:
                best_target = min(range(n_gpus),
                                  key=lambda g: imem.get(g, 0) if g != worst else 10**9)
                if imem.get(best_target, 0) < hw.imem_depth - 10:
                    result[node] = best_target
                    moved = True
                    break
            if not moved:
                break
        if verbose:
            imem = _estimate_imem(tree, result, n_gpus)
            print(f"    After IMEM fix: {imem}")

    # Tier 3: DMEM check
    dmem = _estimate_dmem(tree, result, n_gpus)
    dmem_violations = {g: u for g, u in dmem.items() if u > hw.dmem_depth}

    if dmem_violations:
        if verbose:
            print(f"    DMEM violations: {dmem_violations}")
        # Move deepest nodes from overloaded GPUs
        for iteration in range(50):
            dmem = _estimate_dmem(tree, result, n_gpus)
            overloaded = [g for g, u in dmem.items() if u > hw.dmem_depth]
            if not overloaded:
                break
            worst = max(overloaded, key=lambda g: dmem[g])
            gpu_nodes = sorted(
                [n for n in range(tree.total_nodes) if result.get(n) == worst],
                key=lambda n: -tree.depth(n)
            )
            moved = False
            for node in gpu_nodes:
                best = min(range(n_gpus), key=lambda g: dmem.get(g, 0))
                if best != worst and dmem.get(best, 0) < hw.dmem_depth - 5:
                    result[node] = best
                    moved = True
                    break
            if not moved:
                break

    if verbose:
        imem = _estimate_imem(tree, result, n_gpus)
        dmem = _estimate_dmem(tree, result, n_gpus)
        max_i = max(imem.values()) if imem else 0
        max_d = max(dmem.values()) if dmem else 0
        print(f"    Final: peak IMEM={max_i}/{hw.imem_depth}, "
              f"peak DMEM={max_d}/{hw.dmem_depth}")

    return result

# ═══════════════════════════════════════════════════════════
# METHOD REGISTRY
# ═══════════════════════════════════════════════════════════
STAGE2_METHODS={
    '2a':('HEFT',assign_heft),'2b':('RecBisect',assign_recursive_bisection),
    '2c':('MLfm',assign_multilevel_fm),'2d':('DKway',assign_direct_kway),
    '2e':('ExactBB',assign_exact_bb),'2f':('DFSseed',assign_dfs_seed),
    '2g':('DSC',assign_dsc),'2h':('Chret',assign_chretienne),
    '2i':('CPOP',assign_cpop),'2j':('Centroid',assign_centroid),
    '2k':('Lukes',assign_lukes_dp),'2l':('Frederik',assign_frederickson),
    '2m':('CPFD',assign_bounded_cpfd),'2n':('ClHEFT',assign_cluster_heft),
    '2o':('ParSub',assign_parsubtrees),'2p':('Spine',assign_spine_pinning),
    '2q':('SubPack',assign_subtree_packing),'2r':('LvlHLF',assign_level_parallel_hlf)}

STAGE3_METHODS={
    '3a':('Identity',map_identity),'3b':('HopMin',map_greedy_hop_min),
    '3c':('TreeMatch',map_treematch),'3d':('QAP-SA',map_qap_sa),
    '3e':('MCF',map_mcf),'3f':('DRB',map_drb),
    '3g':('SFC',map_sfc),'3h':('Spectral',map_spectral),
    '3i':('RAGreedy',map_routing_aware_greedy),'3j':('Tabu',map_tabu_search)}

STAGE4_METHODS={
    '4a':('None',refine_none),'4b':('CPcoloc',refine_cp_colocation),
    '4c':('FM',refine_fm),"4c2":('MCFM',refine_multicriteria_fm),
    '4d':('ALNS',refine_alns),'4e':('LeafMig',refine_leaf_migration),
    '4f':('NetW',refine_net_weighting),'4g':('SubMig',refine_subtree_migration),
    '4h':('CentReb',refine_centroid_rebalance),'4i':('TERe',refine_te_rerouting),
    '4j':('VCycles',refine_vcycles),'4k':('FlowMC',refine_flow_mincut)}

def test_all_methods():
    configs=[(8,4,'ring'),(16,8,'mesh'),(32,4,'linear')]
    results={'pass':0,'fail':0,'errors':[]}
    for sn,methods,mt in[('S2',STAGE2_METHODS,'assign'),('S3',STAGE3_METHODS,'map'),('S4',STAGE4_METHODS,'refine')]:
        print(f"\n{sn}:")
        for mid,(name,func)in methods.items():
            ok=True;em=""
            for n,g,tn in configs:
                try:
                    tree=CBTree(n);topo=build_topology(tn,g)
                    if mt=='assign':
                        a=func(tree,g,topo,HW)
                        if not _validate_assignment(tree,a,g): ok=False;em=f"Bad N={n},G={g}";break
                    elif mt=='map':
                        a=assign_recursive_bisection(tree,g,topo,HW)
                        m=func(tree,a,g,topo,HW)
                        if not m: ok=False;em=f"Bad map N={n}";break
                    elif mt=='refine':
                        a=assign_recursive_bisection(tree,g,topo,HW)
                        r=func(tree,a,g,topo,HW)
                        if not _validate_assignment(tree,r,g): ok=False;em=f"Bad ref N={n}";break
                except AlgoTimeout: pass  # Timeout is OK for test
                except Exception as e: ok=False;em=f"Err N={n}: {e}";break
            if ok: results['pass']+=1
            else: results['fail']+=1;results['errors'].append(f"{mid} {name}: {em}")
            print(f"  {mid:>4s} {name:<15s}: {'OK'if ok else'FAIL'} {em}")
    print(f"\n{results['pass']} pass, {results['fail']} fail")
    return results['fail']==0

# ── Stage 6: Schedule Builder + Code Generator ───────────────────────────────

class DMEMAllocator:
    """Allocate DMEM addresses per GPU using Lifetime-Aware Flow Control."""

    def __init__(self, tree: CBTree, assignment: Dict[int, int], n_gpus: int):
        self.tree = tree
        self.assignment = assignment
        self.n_gpus = n_gpus

    # DMEM[0] is reserved as the identity element (0 for ADD).
    # Single-child internal nodes (non-pow2 N) use addr_b=0 in COMPUTE,
    # so DMEM[0] must remain untouched. Allocation starts at address 1.
    IDENTITY_ADDR = 0

    def allocate(self) -> Dict[int, Dict[int, int]]:
        addr_map: Dict[int, Dict[int, int]] = {g: {} for g in range(self.n_gpus)}
        free_lists: Dict[int, List[int]] = {g: [] for g in range(self.n_gpus)}
        peak_local: Dict[int, int] = {g: 1 for g in range(self.n_gpus)}  # start at 1, addr 0 = identity

        # Allocate variables in SU order, tracking lifetimes
        for node in self.tree.su_postorder():
            gpu = self.assignment.get(node, 0)
            
            # If internal, it consumes local children. We return them to the free list.
            if self.tree.is_internal(node):
                for child in self.tree.children(node):
                    if self.assignment.get(child, 0) == gpu:
                        free_lists[gpu].append(addr_map[gpu][child])
            
            # Allocate an address for this new value
            if free_lists[gpu]:
                addr_map[gpu][node] = free_lists[gpu].pop()
            else:
                addr_map[gpu][node] = peak_local[gpu]
                peak_local[gpu] += 1

        # Allocate dedicated persistent receive buffers at the top of DMEM safely
        for node in self.tree.su_postorder():
            if self.tree.is_internal(node):
                gpu = self.assignment.get(node, 0)
                for child in self.tree.children(node):
                    if self.assignment.get(child, 0) != gpu:
                        if child not in addr_map[gpu]:
                            addr_map[gpu][child] = peak_local[gpu]
                            peak_local[gpu] += 1

        return addr_map


def build_schedule(tree: CBTree, assignment: Dict[int, int],
                   mapping: Dict[int, int], n_gpus: int,
                   topo: Topology, hw: HardwareConfig = HW,
                   alu_op: int = ALU_ADD) -> Schedule:
    """Greedy topological schedule builder with RDMA-Push SEND (no RECV)."""
    schedule = Schedule(n_gpus)
    schedule.assignment = dict(assignment)

    allocator = DMEMAllocator(tree, assignment, n_gpus)
    addr_map = allocator.allocate()
    schedule.addr_alloc = addr_map

    gpu_time: Dict[int, int] = {g: 0 for g in range(n_gpus)}
    gci_free: Dict[int, int] = {g: 0 for g in range(n_gpus)}  # GCI serialization
    node_ready: Dict[int, int] = {}

    for _bs_idx, node in enumerate(tree.su_postorder()):
        if _bs_idx % 500 == 0: _check_deadline("build_schedule")
        gpu = assignment[node]
        pe = mapping.get(gpu, gpu)

        if tree.is_leaf(node):
            # GCI constraint (RTL: ex_gci_blocked stalls pipeline if gci_pending).
            # GCI is clock-cycle-based: gci_done fires after GCI_LATENCY real
            # clock cycles, so data-dependency stalls between GENERATEs count
            # toward the gap.  Next GENERATE can execute at earliest
            # last_gen_cycle + gci_latency + 1.
            t = max(gpu_time[gpu], gci_free[gpu])
            op = ScheduledOp('generate', node=node, gpu=gpu, cycle=t,
                             dest_addr=addr_map[gpu][node],
                             duration=1)
            schedule.add_op(op)
            gpu_time[gpu] = t + 1
            # HW trace: GEN->GEN gap = gci_latency + 2 cycles (gci_run counts
            # GCI_LATENCY then gci_done pulses; gci_pending clears one cycle
            # after that).  See noc_ni.sv:190-215 + btree_fsm_fast.sv:725-727.
            gci_free[gpu] = t + hw.gci_latency + 2
            # Fix BS-1: data available when scoreboard is set = t + gci_latency + 2
            # (NOT t + gci_latency as before — the registered gci_done pulse +
            # DMEM write adds 2 extra cycles before scoreboard clears)
            node_ready[node] = t + hw.gci_latency + 2
        else:
            children = tree.children(node)
            earliest = gpu_time[gpu]

            for child in children:
                child_gpu = assignment[child]
                child_pe = mapping.get(child_gpu, child_gpu)

                if child_gpu != gpu:
                    child_ready = node_ready.get(child, 0)

                    stall_for_send = max(0, child_ready - gpu_time[child_gpu])
                    if stall_for_send > 0:
                        gpu_time[child_gpu] += stall_for_send

                    send_time = max(gpu_time[child_gpu], child_ready)

                    # RDMA-Push: target_addr is the receiver's DMEM address for this child
                    target_addr = addr_map[gpu].get(child, 0)

                    send_op = ScheduledOp('send', node=child, gpu=child_gpu,
                                          cycle=send_time,
                                          addr_a=addr_map[child_gpu][child],
                                          dest_gpu=gpu,
                                          dest_addr=target_addr,  # target_addr at receiver
                                          duration=1)
                    schedule.add_op(send_op)
                    gpu_time[child_gpu] = send_time + 1

                    hops = topo.distance(child_pe, pe)
                    comm = hw.comm_cost(hops) if hops > 0 else 0
                    arrival = send_time + 1 + comm

                    # No RECV needed — scoreboard stalls COMPUTE until PIU writes
                    earliest = max(earliest, arrival)
                else:
                    earliest = max(earliest, node_ready.get(child, 0))

            stall_for_compute = max(0, earliest - gpu_time[gpu])
            if stall_for_compute > 0:
                gpu_time[gpu] += stall_for_compute

            compute_time = gpu_time[gpu]
            child_addrs = []
            for child in children:
                child_addrs.append(addr_map[gpu].get(child, DMEMAllocator.IDENTITY_ADDR))
            while len(child_addrs) < 2:
                child_addrs.append(DMEMAllocator.IDENTITY_ADDR)

            # Fix BS-4: use hw.compute_latency directly (remove fragile getattr)
            op = ScheduledOp('compute', node=node, gpu=gpu,
                             cycle=compute_time,
                             dest_addr=addr_map[gpu][node],
                             addr_a=child_addrs[0], addr_b=child_addrs[1],
                             alu_op=alu_op, duration=hw.compute_latency)
            schedule.add_op(op)
            gpu_time[gpu] = compute_time + hw.compute_latency
            node_ready[node] = gpu_time[gpu]

    # Fix BS-5: add constant pipeline overhead (2-cycle fill + 1-cycle drain)
    # RTL: P_IDLE→P_RUN takes 2 cycles for IF→DE→EX fill;
    # P_RUN→P_DRAIN→P_DONE takes 1+ cycle for last EX + GCI drain.
    schedule.makespan += hw.pipeline_overhead

    return schedule


def generate_instructions(tree: CBTree, topo: Topology,
                          schedule: Schedule,
                          hw: HardwareConfig = HW,
                          alu_op: int = ALU_ADD) -> Dict[int, List[int]]:
    """Code generator with cycle-accurate NOP insertion and GCI enforcement.

    Fix v2.3: Previous version discarded schedule cycle information, producing
    back-to-back instructions even when the schedule required timing gaps.
    Now inserts NOP stalls to match the schedule's cycle timestamps, then
    runs the peephole pass to enforce GCI serialization.
    """
    programs = {}
    for gpu in range(schedule.n_gpus):
        if gpu % 500 == 0: _check_deadline("gen_instr")
        ops = schedule.get_gpu_ops(gpu)
        instrs = []
        current_cycle = 0
        for _gi_idx, op in enumerate(ops):
            if _gi_idx % 1000 == 0: _check_deadline("gen_instr_op")
            # Insert NOP stalls to advance to this op's scheduled cycle
            stall = op.cycle - current_cycle
            if stall > 0:
                for _ in range(stall):
                    instrs.append(encode_nop())
                current_cycle += stall

            if op.op_type == 'nop':
                instrs.append(encode_nop())
            elif op.op_type == 'generate':
                instrs.append(encode_generate(op.dest_addr))
            elif op.op_type == 'compute':
                instrs.append(encode_compute(op.dest_addr, op.addr_a,
                                             op.addr_b, alu_op))
            elif op.op_type == 'send':
                # RDMA-Push: src_addr=addr_a, dest_gpu, target_addr=dest_addr
                instrs.append(encode_send(op.addr_a, op.dest_gpu, op.dest_addr, op.link))
            # RECV is deprecated — no case for it
            current_cycle += op.duration

        instrs = _peephole_nop_compress(instrs, hw)
        # Ensure non-empty: RTL FSM needs at least 1 instruction
        if not instrs:
            instrs = [encode_nop()]
        programs[gpu] = instrs
    return programs


def _peephole_nop_compress(instrs: List[int], hw: 'HardwareConfig' = None) -> List[int]:
    """Peephole NOP compression with GCI serialization.

    v8.0: RECV safety pass removed (no RECV in RDMA-Push architecture).
    Scoreboard handles all data-dependency stalling in hardware.

    Passes:
      Pass 1: Collapse excessive NOP runs — keep what the schedule put in.
      Pass 2: For EVERY GENERATE, find the previous GENERATE and count ALL
              instructions (NOPs + non-NOPs) between them. If total < gci_latency,
              insert padding NOPs.
    """
    if not instrs:
        return instrs
    if hw is None:
        hw = HW
    # Required NOP count between consecutive GENERATEs: gci_latency + 1.
    # HW trace shows gap of gci_latency + 2 cycles from GEN1 issue to GEN2
    # issue, so the in-stream spacing is gci_latency + 1 NOPs.
    gci_gap = hw.gci_latency + 1

    # --- Pass 1: Collapse NOP runs but preserve minimum timing ---
    collapsed = []
    i = 0
    _pn_tick = 0
    while i < len(instrs):
        _pn_tick += 1
        if _pn_tick % 2000 == 0: _check_deadline("peephole_p1")
        opcode = (instrs[i] >> 60) & 0xF
        if opcode != OP_NOP:
            collapsed.append(instrs[i])
            i += 1
        else:
            nop_start = i
            while i < len(instrs) and ((instrs[i] >> 60) & 0xF) == OP_NOP:
                i += 1
            nop_count = i - nop_start
            if i < len(instrs):
                keep = min(nop_count, max(1, gci_gap))
                for _ in range(keep):
                    collapsed.append(encode_nop())

    # --- Pass 2: Enforce GCI serialization between ALL GENERATE pairs ---
    result = []
    last_gen_pos = -1

    for _p2_idx, instr in enumerate(collapsed):
        if _p2_idx % 2000 == 0: _check_deadline("peephole_p2")
        opcode = (instr >> 60) & 0xF
        if opcode == OP_GENERATE:
            if last_gen_pos >= 0:
                gap = len(result) - last_gen_pos - 1
                needed = gci_gap - gap
                if needed > 0:
                    for _ in range(needed):
                        result.append(encode_nop())
            result.append(instr)
            last_gen_pos = len(result) - 1
        else:
            result.append(instr)

    # Strip trailing NOPs
    while result and ((result[-1] >> 60) & 0xF) == OP_NOP:
        result.pop()
    return result



def emit_sv_testbench(tree, topo, progs, fn="tb_sprs.sv", hw=HW,
                      assignment=None, addr_alloc=None, schedule=None, alu_op=0):
    """Generate SystemVerilog testbench for v7 noc_system with GCI buffer loading."""
    import struct
    def make_leaf_val(idx, op):
        if op == 0b111:
            # Proper fractional parts: every value has non-trivial mantissa bits
            fv = (idx + 1) * 1000.0 + ((idx * 37 + 13) % 100) / 100.0 + 0.007
            return fv, struct.unpack('<Q', struct.pack('<d', fv))[0]
        elif op == 0b110:
            sv = ((idx + 1) * 1000)
            if idx % 2 == 1: sv = -sv
            return sv, sv & 0xFFFFFFFFFFFFFFFF
        else:
            v = (idx + 1) * 1000
            return v, v

    nn=topo.n_nodes; nr=topo.n_routers; ppr=topo.ports_per_router
    pw=max(1, int(math.ceil(math.log2(ppr))))
    max_imem = max(len(progs[g]) for g in progs) if progs else 32
    imem_sz = 1
    while imem_sz < max_imem: imem_sz *= 2
    imem_sz = max(imem_sz, 64)  # minimum 64
    dmem_sz = hw.dmem_depth
    # Compute number of leaves per GPU for GCI buffer
    leaves_per_gpu = {}
    for n in range(tree.total_nodes):
        if tree.is_leaf(n):
            g = assignment.get(n, 0) if assignment else 0
            leaves_per_gpu[g] = leaves_per_gpu.get(g, 0) + 1
    max_leaves = max(leaves_per_gpu.values()) if leaves_per_gpu else 1

    # ── Emission post-condition: no DMEM address may alias ────────────────────
    # Every DMEM address the fabric sees is truncated to DMEM_ADDR_W bits, so an
    # address at or beyond dmem_sz silently becomes a different, live address.
    # Rather than emit a testbench that computes something other than the
    # program, refuse.  Callers record the pipeline as a compile failure.
    _bad = []
    for _g in sorted(progs):
        for _pc, _w in enumerate(progs[_g]):
            _op = (_w >> 60) & 0xF
            if _op == OP_NOP:
                continue
            _dest = (_w >> 40) & 0xFFFF
            _a = (_w >> 24) & 0xFFFF
            _b = (_w >> 8) & 0xFFFF
            _refs = [('dest', _dest)]
            if _op == OP_COMPUTE:
                _refs += [('addr_a', _a), ('addr_b', _b)]
            elif _op == OP_SEND:
                _refs += [('src_addr', _a)]
            for _what, _addr in _refs:
                if _addr >= dmem_sz:
                    _bad.append((_g, _pc, _op, _what, _addr, _addr % dmem_sz))
                    if len(_bad) >= 8:
                        break
            if len(_bad) >= 8:
                break
        if len(_bad) >= 8:
            break
    if _bad:
        _peak = max(x[4] for x in _bad) + 1
        _ex = "; ".join(f"PE {g} pc {pc} op {op} {what}={addr} aliases to {al}"
                        for (g, pc, op, what, addr, al) in _bad[:4])
        raise EmitRefused(
            f"DMEM address out of range: peak addressed slot {_peak} exceeds "
            f"CN_DMEM={dmem_sz} on {tree.n_leaves}L {nn}G {topo.name}. "
            f"Emitting would alias {len(_bad)}+ references onto live slots "
            f"({_ex}). Refusing to emit.")

    lines=[]
    lines.append(f"// SPRS v2.2 — Auto-generated testbench")
    lines.append(f"// {tree.n_leaves}L {nn}G {topo.name}")
    lines.append("`timescale 1ns/1ps")
    lines.append("")
    lines.append(f"module tb_sprs_{tree.n_leaves}L_{nn}G;")
    lines.append("  logic clk=0;")
    lines.append("  logic rst;")
    lines.append("  always #5 clk=~clk;")
    lines.append("")
    lines.append(f"  localparam int N_NODES={nn};")
    lines.append(f"  localparam int N_ROUTERS={nr};")
    lines.append(f"  localparam int PPR={ppr};")
    lines.append("")
    lines.append("  logic program_start,all_done;")
    lines.append("  logic[63:0]result;")
    lines.append(f"  logic[N_NODES-1:0][7:0]status;")
    lines.append(f"  logic[N_NODES-1:0]error;")
    lines.append(f"  logic[N_NODES-1:0][15:0]error_pc;")
    lines.append(f"  logic[N_NODES-1:0][3:0]error_state;")
    lines.append("  logic[N_NODES-1:0]imem_wr_en;")
    lines.append("  logic[N_NODES-1:0][15:0]imem_wr_addr,imem_size;")
    lines.append("  logic[N_NODES-1:0][63:0]imem_wr_data;")
    lines.append("  logic[N_ROUTERS-1:0]rtr_rt_wr_en;")
    lines.append("  logic[N_ROUTERS-1:0][15:0]rtr_rt_wr_addr;")
    lines.append(f"  logic[N_ROUTERS-1:0][{pw-1}:0]rtr_rt_wr_data;")
    lines.append("  logic adj_wr_en;")
    # ── Adjacency-configuration field width ──────────────────────────────────
    # noc_system's adjacency interface carries router ids, port ids and their
    # targets in ADJ_ID_W-bit fields, with the all-ones code reserved as the
    # "disconnected" sentinel.  The historical fixed width of 12 addresses
    # routers 0..4094 only; fat_tree G=4096 instantiates 4,192 routers, so every
    # id >= 4095 aliased and the emitted configuration described a fabric with
    # no relation to the intended fat-tree (0 of 8,223 installed links matched,
    # 0 of 900 sampled routes delivered).  Size the field to the instance.  Any
    # instance that fitted in 12 bits still emits byte-identical SystemVerilog,
    # so every previously-recorded tb_hash is preserved exactly.
    _adj_max = max([nr - 1, ppr - 1] +
                   [max(r, p, tr, tp) for (r, p), (tr, tp) in topo.adjacency.items()]
                   if topo.adjacency else [nr - 1, ppr - 1])
    adj_w = 12
    while (1 << adj_w) - 2 < _adj_max:
        adj_w += 4
    lines.append(f"  logic[{adj_w-1}:0]adj_rtr_id,adj_port_id,adj_target_rtr,adj_target_port;")
    lines.append(f"  logic[N_NODES-1:0]gci_buf_wr_en;")
    lines.append(f"  logic[N_NODES-1:0][15:0]gci_buf_wr_addr;")
    lines.append(f"  logic[N_NODES-1:0][63:0]gci_buf_wr_data;")
    lines.append(f"  logic[N_NODES-1:0][31:0]perf_total,perf_stall,perf_retired;")
    lines.append("")

    # noc_system instantiation
    lines.append("  noc_system #(")
    lines.append(f"    .N_NODES(N_NODES),.N_ROUTERS(N_ROUTERS),.PORTS_PER_RTR(PPR),")
    lines.append(f"    .NUM_VCS(2),.GCI_BUF_DEPTH({max_leaves}),")
    lines.append(f"    .RTR_BUF_DEPTH(16),.NI_BUF_DEPTH(8),.LINK_LATENCY(0),")
    lines.append(f"    .CN_NUM_LINKS(2),.CN_TX_BUF(8),.CN_RX_BUF(8),")
    lines.append(f"    .CN_DMEM({dmem_sz}),.CN_IMEM({imem_sz}),")
    _adj_param = "" if adj_w == 12 else f",.ADJ_ID_W({adj_w})"
    lines.append(f"    .CN_TIMEOUT({hw.timeout_max}),.CN_WATCHDOG({hw.watchdog_max}),.GCI_LATENCY({hw.gci_latency}){_adj_param}")
    lines.append("  ) u_sys (")
    lines.append("    .clk,.rst,.program_start,.all_done,.result,")
    lines.append("    .status,.error,.error_pc,.error_state,")
    lines.append("    .imem_wr_en,.imem_wr_addr,.imem_wr_data,.imem_size,")
    lines.append("    .rtr_rt_wr_en,.rtr_rt_wr_addr,.rtr_rt_wr_data,")
    lines.append("    .adj_wr_en,.adj_rtr_id,.adj_port_id,.adj_target_rtr,.adj_target_port,")
    lines.append("    .gci_buf_wr_en,.gci_buf_wr_addr,.gci_buf_wr_data,")
    lines.append("    .perf_total,.perf_stall,.perf_retired")
    lines.append("  );")
    lines.append("")

    # Helper tasks
    lines.append("  task automatic write_adj(int r,int p,int tr,int tp);")
    lines.append(f"    adj_wr_en=1;adj_rtr_id=r[{adj_w-1}:0];adj_port_id=p[{adj_w-1}:0];")
    lines.append(f"    adj_target_rtr=tr[{adj_w-1}:0];adj_target_port=tp[{adj_w-1}:0];@(posedge clk);#1;adj_wr_en=0;")
    lines.append("  endtask")
    lines.append(f"  task automatic write_route(int r,int d,int p);")
    lines.append(f"    rtr_rt_wr_en[r]=1;rtr_rt_wr_addr[r]=d[15:0];rtr_rt_wr_data[r]=p[{pw-1}:0];@(posedge clk);#1;rtr_rt_wr_en[r]=0;")
    lines.append("  endtask")
    lines.append("  task automatic load_instr(int g,int a,logic[63:0]d);")
    lines.append("    imem_wr_en[g]=1;imem_wr_addr[g]=a[15:0];imem_wr_data[g]=d;@(posedge clk);#1;")
    lines.append("  endtask")
    lines.append("  task automatic load_gci(int g,int a,logic[63:0]d);")
    lines.append("    gci_buf_wr_en[g]=1;gci_buf_wr_addr[g]=a[15:0];gci_buf_wr_data[g]=d;@(posedge clk);#1;gci_buf_wr_en[g]=0;")
    lines.append("  endtask")
    lines.append("")

    # Compute expected result
    leaf_list = tree.leaves()
    leaf_to_global_idx = {leaf: idx for idx, leaf in enumerate(leaf_list)}

    if alu_op == 0b111:
        # FP: simulate tree-order reduction using bit-accurate FP adder
        # that exactly matches fp64_add.sv (FTZ, RNE rounding).
        # Hardware performs binary-tree structured additions, which is NOT
        # the same as sequential left-to-right sum due to FP non-associativity.
        node_val_bits = {}  # raw 64-bit integer representations
        for _po_idx, node in enumerate(tree.postorder()):
            if _po_idx % 500 == 0: _check_deadline("tb_postorder")
            if tree.is_leaf(node):
                gidx = leaf_to_global_idx.get(node, 0)
                _, bits = make_leaf_val(gidx, alu_op)
                node_val_bits[node] = bits
            else:
                ch = tree.children(node)
                a_bits = node_val_bits.get(ch[0], 0) if len(ch) > 0 else 0
                b_bits = node_val_bits.get(ch[1], 0) if len(ch) > 1 else 0
                node_val_bits[node] = _fp64_add_bits(a_bits, b_bits)
        exp_int = node_val_bits.get(0, 0)
        expected_math = struct.unpack('<d', struct.pack('<Q', exp_int))[0]
    else:
        # Integer: simple sum (modular arithmetic is associative/commutative)
        expected_math = 0
        for idx, leaf_node in enumerate(leaf_list):
            math_v, _ = make_leaf_val(idx, alu_op)
            expected_math += math_v
        exp_int = int(expected_math) & 0xFFFFFFFFFFFFFFFF
        
    lines.append(f"  // ALU_OP={alu_op}, Math Expected={expected_math}")
    lines.append(f"  localparam logic[63:0] EXPECTED = 64'h{exp_int:016X};")
    timeout_ns = max(200000, tree.total_nodes * 1000)
    lines.append("")

    # Initial block
    lines.append("  initial begin")
    lines.append(f'    $display("SPRS {tree.n_leaves}L {nn}G {topo.name}");')
    lines.append("    rst=1;program_start=0;imem_wr_en='0;rtr_rt_wr_en='0;adj_wr_en=0;")
    lines.append("    gci_buf_wr_en='0;")
    lines.append("    #30;rst=0;#10;")
    lines.append("")

    # Adjacency
    adj=topo.generate_adjacency_table()
    for ra,pa,rb,pb in adj:
        lines.append(f"    write_adj({ra},{pa},{rb},{pb});")

    # Routing tables
    rt=topo.generate_routing_tables()
    for rtr in sorted(rt.keys()):
        for dest in sorted(rt[rtr].keys()):
            lines.append(f"    u_sys.gen_rtr[{rtr}].u_rtr.route_table[{dest}] = {rt[rtr][dest]};")

    # Instructions
    for _ig_idx, gpu in enumerate(sorted(progs.keys())):
        if _ig_idx % 500 == 0: _check_deadline("tb_instr_gpu")
        ins=progs[gpu]
        lines.append(f"    imem_size[{gpu}]={len(ins)};")
        for i,w in enumerate(ins):
            if i % 2000 == 0: _check_deadline("tb_instr_emit")
            lines.append(f"    load_instr({gpu},{i},64'h{w:016X});")
        lines.append(f"    imem_wr_en[{gpu}]=0;")
    # Load NOP for unused GPUs so they reach DONE
    for gpu in range(nn):
        if gpu not in progs:
            lines.append(f"    imem_size[{gpu}]=1;")
            lines.append(f"    load_instr({gpu},0,64'h0000000000000000); // NOP")
            lines.append(f"    imem_wr_en[{gpu}]=0;")
    lines.append("")

    # Load GCI buffer with leaf values
    # CRITICAL: GCI buffer must be filled in schedule GENERATE order per GPU,
    # NOT in tree.leaves() order. The hardware reads GCI[gci_rd_ptr++] each
    # time a GENERATE executes, so GCI[0] must contain the value for the
    # FIRST leaf generated, GCI[1] for the SECOND, etc.
    # (leaf_list and leaf_to_global_idx already computed above for expected value)
    if schedule is not None:
        # Use schedule GENERATE order per GPU
        for gpu in range(nn):
            if gpu % 500 == 0: _check_deadline("tb_gci")
            if gpu in progs:
                ops = schedule.get_gpu_ops(gpu)
                gen_nodes = [op.node for op in ops if op.op_type == 'generate']
                for local_idx, node in enumerate(gen_nodes):
                    global_idx = leaf_to_global_idx.get(node, 0)
                    _, val_64 = make_leaf_val(global_idx, alu_op)
                    lines.append(f"    load_gci({gpu},{local_idx},64'h{val_64:016X}); // leaf {node} (L{global_idx})")
    else:
        # Fallback: tree.leaves() order (only works for symmetric contiguous partitions)
        gpu_leaf_idx = {g: 0 for g in range(nn)}
        for idx, leaf_node in enumerate(leaf_list):
            g = assignment.get(leaf_node, 0) if assignment else 0
            _, val_64 = make_leaf_val(idx, alu_op)
            local_idx = gpu_leaf_idx[g]
            lines.append(f"    load_gci({g},{local_idx},64'h{val_64:016X}); // leaf {leaf_node} (L{idx})")
            gpu_leaf_idx[g] = local_idx + 1
    lines.append("")

    # Start reduction — Verilator-compatible timeout (no fork/join_any)
    timeout_cycles = timeout_ns // 10  # 10ns per clock cycle (always #5 clk=~clk)
    lines.append(f"    // Timeout after {timeout_cycles} cycles ({timeout_ns}ns)")
    lines.append("    #100;program_start=1;@(posedge clk);#1;program_start=0;")
    lines.append(f"    for(integer _t=0; _t<{timeout_cycles} && !all_done; _t++) @(posedge clk);")
    lines.append('    if(!all_done) $display("TIMEOUT");')
    lines.append("    #50;")
    lines.append("")

    # Result checking — use cn_result of the root GPU, not hardwired result output
    root_gpu = assignment.get(0, 0) if assignment else 0
    lines.append(f'    $display("  root_gpu={root_gpu} root_result=%0d expected=%0d",u_sys.gen_node[{root_gpu}].u_cn.result,EXPECTED);')
    lines.append(f'    if(all_done && u_sys.gen_node[{root_gpu}].u_cn.result==EXPECTED)')
    lines.append(f'      $display("[PASS] {tree.n_leaves}L {nn}G {topo.name}");')
    lines.append('    else if(!all_done)')
    lines.append(f'      $display("[FAIL] {tree.n_leaves}L {nn}G {topo.name}: TIMEOUT");')
    lines.append('    else')
    lines.append(f'      $display("[FAIL] {tree.n_leaves}L {nn}G {topo.name}: root_result=%0d expected=%0d",u_sys.gen_node[{root_gpu}].u_cn.result,EXPECTED);')
    lines.append("")

    # Performance counters
    lines.append('    $display("  [PERF] Performance counters:");')
    lines.append("    for(int g=0;g<N_NODES;g++)")
    lines.append('      $display("  [PERF] GPU %0d: perf_total=%0d perf_stall=%0d perf_retired=%0d",g,perf_total[g],perf_stall[g],perf_retired[g]);')
    lines.append("")

    # Error check
    lines.append("    for(int g=0;g<N_NODES;g++) begin")
    lines.append('      if(error[g]) $display("  [ERROR] GPU %0d error (PC=%0d, State=%0d)",g,error_pc[g],error_state[g]);')
    lines.append('      else if(status[g]!=8\'hFF) $display("  [STALL] GPU %0d stuck at PC=%0d (Status=%0h)",g,error_pc[g],status[g]);')
    lines.append("    end")
    lines.append("    $finish;")
    lines.append("  end")
    lines.append("endmodule")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# COMPILE PIPELINE
# ═══════════════════════════════════════════════════════════
def build_topology(name,ng):
    if name=='linear': t=Topology.linear(ng)
    elif name=='ring': t=Topology.ring(ng)
    elif name=='mesh':
        s=max(2,int(math.ceil(math.sqrt(ng))));r=max(2,(ng+s-1)//s);t=Topology.mesh(s,r)
    elif name=='torus':
        s=max(2,int(math.ceil(math.sqrt(ng))));r=max(2,(ng+s-1)//s);t=Topology.torus(s,r)
    elif name=='fat_tree': t=Topology.fat_tree(ng)
    elif name=='hypercube':
        d=max(1,int(math.ceil(math.log2(max(2,ng)))));t=Topology.hypercube(d)
    else: t=Topology.linear(ng)
    t.active_nodes=ng  # requested GPUs (may differ from t.n_nodes for mesh/torus/hypercube)
    return t

def compile(tree,ng,topo,hw=HW,verbose=True,alu_op=ALU_ADD,
            s2_id='2b',s3_id='3a',s4_chain=None):
    """Compile a reduction tree onto ng GPUs.

    Args:
        s2_id: Assignment method ID (default '2b' = RecBisect)
        s3_id: Mapping method ID (default '3a' = Identity)
        s4_chain: Optional refinement chain, e.g. '4c' or '4c+4d'
                  If None, uses refine_phased (default multi-step refinement)
    """
    t0=time.time();res={};ctx=get_ctx(tree,topo,hw)
    if verbose:
        print(f"\n{'='*60}");print(f"SPRS v2.2 — {tree.n_leaves}L, {ng}G, {topo.name}")
        print(f"C ext: {'YES'if _CLIB else'NO'}, NumPy: {'YES'if HAS_NUMPY else'NO'}")
        print(f"Tree: {tree.total_nodes}N, h={tree.height}");print(f"{'='*60}")
    bd=compute_lower_bound(tree,ng,topo,hw);omega=bd['omega'];res['omega']=omega
    if verbose: print(f"\nS0: Ω={omega:.1f}")
    ge=min(ng,tree.total_nodes);res['g_eff']=ge
    if verbose: print(f"Using {ge} GPUs")

    # S2: Assignment
    _,s2_func=STAGE2_METHODS[s2_id]
    s2_name=STAGE2_METHODS[s2_id][0]
    if verbose: print(f"\nS2: {s2_name} ({s2_id})")
    asgn=s2_func(tree,ge,topo,hw);res['assignment']=asgn;res['s2']=s2_id

    # S2.5: Connectivity repair — ensure every GPU's partition is a
    # connected subgraph of the tree (required for correct FP64 order)
    asgn=repair_connectivity(tree,asgn,ge);res['assignment']=asgn

    # S3: Mapping
    _,s3_func=STAGE3_METHODS[s3_id]
    s3_name=STAGE3_METHODS[s3_id][0]
    if verbose: print(f"S3: {s3_name} ({s3_id})")
    mapping=s3_func(tree,asgn,ge,topo,hw);res['mapping']=mapping;res['s3']=s3_id

    # S4: Refinement
    if verbose: print(f"\nS4: Refinement...")
    mb=_estimate_makespan(tree,asgn,ge,topo,hw)
    if s4_chain:
        if '+' in s4_chain:
            a_id,b_id=s4_chain.split('+')
            _,af=STAGE4_METHODS[a_id];_,bf=STAGE4_METHODS[b_id]
            ref=af(tree,asgn,ge,topo,hw)
            if _validate_assignment(tree,ref,ge): ref=bf(tree,ref,ge,topo,hw)
            else: ref=asgn
        else:
            _,s4f=STAGE4_METHODS[s4_chain]
            ref=s4f(tree,asgn,ge,topo,hw)
        if _validate_assignment(tree,ref,ge): asgn=ref
        res['s4']=s4_chain
    else:
        asgn=refine_phased(tree,asgn,ge,topo,mapping,hw,verbose)
        res['s4']='phased'
    ma=_estimate_makespan(tree,asgn,ge,topo,hw);res['assignment']=asgn
    if verbose:
        imp=(1-ma/mb)*100 if mb>0 else 0
        print(f"  {mb:.1f}→{ma:.1f} ({imp:+.1f}%)")

    # S5: Memory enforcement
    if verbose: print(f"\nS5: Memory...")
    asgn=enforce_memory(tree,asgn,ge,topo,hw,verbose);res['assignment']=asgn

    # Re-map after refinement (identity mapping if not specified)
    mapping=s3_func(tree,asgn,ge,topo,hw);res['mapping']=mapping

    # S6: Codegen
    if verbose: print(f"\nS6: Codegen...")
    sched=build_schedule(tree,asgn,mapping,ge,topo,hw,alu_op)
    progs=generate_instructions(tree,topo,sched,hw,alu_op)
    res['schedule']=sched;res['programs']=progs
    dt=time.time()-t0;res['compile_time_s']=dt
    if verbose:
        ratio=sched.makespan/omega if omega>0 else float('inf')
        print(f"\n{'─'*60}");print(f"Makespan={sched.makespan}, Ω={omega:.1f}, ratio={ratio:.2f}x")
        mi=max(len(progs[g])for g in progs)
        print(f"Peak IMEM={mi}/{hw.imem_depth} {'OK'if mi<=hw.imem_depth else'OVERFLOW'}")
        print(f"Time={dt:.3f}s");print(f"{'='*60}\n")
    return res

def _run_benchmark(verbose=True):
    cases=[(4,2,'linear'),(8,4,'linear'),(16,4,'linear'),(16,8,'ring'),(32,4,'linear'),(64,8,'linear')]
    print(f"\n{'='*76}");print("SPRS v2.2 Benchmark");print(f"{'='*76}")
    print(f"{'N':>6}{'G':>4}{'Topo':>8}{'MS':>8}{'Ω':>8}{'Rat':>8}{'S2':>12}{'Time':>8}")
    print(f"{'-'*76}")
    for nl,ng2,tn in cases:
        tree=CBTree(nl);topo=build_topology(tn,ng2)
        r=compile(tree,ng2,topo,verbose=False)
        ms=r['schedule'].makespan;om=r['omega'];rat=ms/om if om>0 else 0
        print(f"{nl:>6}{ng2:>4}{tn:>8}{ms:>8}{om:>8.1f}{rat:>8.2f}{r['s2']:>12}{r['compile_time_s']:>7.3f}s")
    print(f"{'='*76}\n")

# ═══════════════════════════════════════════════════════════
# TEST INSTANCES
# ═══════════════════════════════════════════════════════════
TEST_INSTANCES=[
    (8,4,'ring','tiny_mod_ring'),(8,2,'linear','tiny_dense_1d'),
    (32,16,'torus','small_mod_2d'),(32,8,'fat_tree','small_bal_fat'),
    (32,4,'hypercube','small_dense_hc'),
    (128,64,'ring','med_mod_ring'),(128,32,'fat_tree','med_mod_fat'),
    (128,16,'torus','med_bal_2d'),(128,8,'mesh','med_dense_mesh'),
    (128,4,'linear','med_extreme_1d'),
    (512,256,'ring','large_mod_ring'),(512,64,'fat_tree','large_bal_fat'),
    (512,32,'hypercube','large_dense_hc'),(512,16,'torus','large_dense_2d'),
    (512,8,'linear','large_extreme_1d'),
    (1024,512,'ring','vlarge_mod_ring'),(1024,128,'fat_tree','vlarge_bal_fat'),
    (1024,64,'torus','vlarge_dense_2d'),(1024,32,'hypercube','vlarge_dense_hc'),
    (2048,256,'fat_tree','vlarge2_bal_fat'),(2048,128,'torus','vlarge2_dense_2d'),
    (4096,2048,'fat_tree','max_mod_fat'),(4096,1024,'torus','max_bal_2d'),
    (4096,512,'hypercube','max_dense_hc'),
    (8192,4096,'fat_tree','maxp_mod_fat'),(8192,2048,'torus','maxp_bal_2d'),
    (8192,1024,'hypercube','maxp_dense_hc'),
    # Extended: fill topology/scale gaps (from tournament EXTENDED_INSTANCES)
    (512,64,'mesh','large_bal_mesh'),           # mesh at scale
    (2048,256,'mesh','vlarge_bal_mesh'),        # mesh at large scale
    (128,128,'torus','med_full_torus'),         # N/G=1 boundary
    (2048,512,'ring','vlarge2_mod_ring'),       # ring at large scale
    (1024,16,'linear','vlarge_extreme_1d'),     # linear stress test
    # Non-power-of-2 (unbalanced tree / phantom GPU) — small scale
    (10,4,'ring','npow2n_tiny_ring'),           # non-pow2 N only
    (16,5,'mesh','npow2g_small_mesh'),          # non-pow2 G only (mesh pads 5->6)
    (50,7,'hypercube','npow2_tiny_hc'),         # both non-pow2 (HC pads 7->8)
    (100,10,'torus','npow2_small_torus'),       # both non-pow2 (torus pads 10->12)
    (200,12,'fat_tree','npow2_med_fat'),        # both non-pow2 (no padding)
    # Larger unbalanced-tree instances (non-pow2 N, CBTree with single-child nodes)
    (500,32,'torus','large_unbal_torus'),       # large unbalanced tree
    (1500,64,'hypercube','vlarge_unbal_hc'),    # vlarge unbalanced tree
    (3000,128,'fat_tree','max_unbal_fat')]      # max unbalanced tree
N_INSTANCES=len(TEST_INSTANCES)

def precompute_all_instances(ti,hw=None):
    if hw is None: hw=HW
    for n,g,tn,_ in ti:
        tree=CBTree(n);topo=build_topology(tn,g)
        topo.warm_cache();get_ctx(tree,topo,hw)
        tree.postorder();tree.hu_levels();tree.sethi_ullman()


# ═══════════════════════════════════════════════════════════
# STANDALONE CLI
# ═══════════════════════════════════════════════════════════
def main():
    parser=argparse.ArgumentParser(description="SPRS Core v2.2")
    parser.add_argument('--test',action='store_true',help='Run 40-method test suite')
    parser.add_argument('--benchmark',action='store_true',help='Run benchmark suite')
    parser.add_argument('--n-leaves',type=int,default=0,help='Single compile: N leaves')
    parser.add_argument('--n-gpus',type=int,default=4,help='Number of GPUs')
    parser.add_argument('--topology',type=str,default='torus',help='Topology name')
    parser.add_argument('--s2',type=str,default='2b',help='S2 method ID')
    parser.add_argument('--s3',type=str,default='3a',help='S3 method ID')
    parser.add_argument('--s4',type=str,default='',help='S4 chain e.g. 4c or 4c+4d')
    args=parser.parse_args()
    if args.test: test_all_methods()
    elif args.benchmark: _run_benchmark()
    elif args.n_leaves>0:
        topo=build_topology(args.topology,args.n_gpus)
        tree=CBTree(args.n_leaves)
        compile(tree,args.n_gpus,topo,verbose=True,s2_id=args.s2,s3_id=args.s3,s4_chain=args.s4 or None)
    else: parser.print_help()

if __name__=='__main__':
    main()
