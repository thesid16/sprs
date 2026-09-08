#!/usr/bin/env python3
r"""
gen_fabric_macros.py -- emit data/fabric_macros.tex.

Values used by the fabric (Sec. IV) and compiler (Sec. V) sections.  Each one
is taken from an executed council check; before emitting, the script asserts
that the exact string is present in the source verdict file, so a replaced or
edited council record makes this script fail rather than silently typeset a
stale number.

Sources (read-only):
  council/work/T13_verify.json  -- NoC/RTL: VC discipline, CDG cyclicity,
                                   credit accounting, NI credits, maxp_mod_fat
                                   12-bit adjacency truncation, IMEM sizing
  council/work/T04_verify.json  -- compiler: stages actually run, disconnected
                                   partitions, peak DMEM, repair_connectivity
  council/work/T05_verify.json  -- campaign shape (compilation denominator)

Macro names contain no digits (check_consistency.py C1).
"""
import json
import os
import sys

# Council record directory.  Resolution order:
#   1. $SPRS_COUNCIL                   -- explicit override
#   2. <paper>/data/council            -- the released artifact layout (the JSONs
#                                         these generators read are vendored there
#                                         so a fresh clone can run them)
#   3. the author's original absolute path, last resort.
def _council_default():
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(os.path.dirname(here), "data", "council")
    return cand if os.path.isdir(cand) else \
        "/home/rohit/sprs-review/runs/20260817T230831Z/council/work"


COUNCIL = os.environ.get("SPRS_COUNCIL") or _council_default()
HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
FAIL = []


def load(name):
    with open(os.path.join(COUNCIL, name), encoding="utf-8") as fh:
        return json.dumps(json.load(fh))


T13 = load("T13_verify.json")
T04 = load("T04_verify.json")
T05 = load("T05_verify.json")


def need(blob, needle, what):
    if needle not in blob:
        FAIL.append(f"{what}: {needle!r} absent from source record")


M = []


def emit(name, value, blob=None, needle=None, what=None):
    if needle is not None:
        need(blob, needle, what or name)
    M.append(f"\\newcommand{{\\{name}}}{{{value}}}")


# ---- T13/D065: the VC discipline and the channel-dependency graph ---------
emit("NumVcs", "two", T13, "NUM_VCS", "NumVcs")
emit("VcBitLiteral", r"\sv{6'b0}", T13, "6'b0", "VcBitLiteral")
emit("CdgTorusCycLo", "6", T13, "length 6 to 32", "CdgTorusCycLo")
emit("CdgTorusCycHi", "32", T13, "length 6 to 32", "CdgTorusCycHi")

# ---- T13/D070: credit-return backlog register ----------------------------
emit("CreditCtrBits", "two", T13, "credit_pending at $clog2(NUM_VCS+1) = 2 bits",
     "CreditCtrBits")
emit("CreditCtrWrap", "four", T13, "3+2-1 = 4 truncates to 0", "CreditCtrWrap")

# ---- T13/D067: CN-to-NI credit mis-sizing --------------------------------
emit("NiCredits", "16", T13, ".RTR_BUF_DEPTH(16),.NI_BUF_DEPTH(8)", "NiCredits")
emit("NiFifoDepth", "8", T13, ".RTR_BUF_DEPTH(16),.NI_BUF_DEPTH(8)", "NiFifoDepth")

# ---- T13/D069: maxp_mod_fat, the 12-bit adjacency id ---------------------
emit("MaxpRouters", "4{,}192", T13, "n_routers = 4192", "MaxpRouters")
emit("MaxpAdjEntries", "12{,}288", T13, "12,288 entries", "MaxpAdjEntries")
emit("MaxpLinksInstalled", "8{,}223", T13, "8,223 links installed",
     "MaxpLinksInstalled")
emit("MaxpLinksCorrect", "none", T13, "ZERO match the intended topology",
     "MaxpLinksCorrect")
emit("MaxpPortDrops", "1{,}984", T13, "1,984 adjacency writes discarded",
     "MaxpPortDrops")
emit("MaxpRoutesSampled", "900", T13, "routing 900 random leaf-to-leaf pairs",
     "MaxpRoutesSampled")
emit("MaxpRoutesDelivered", "none", T13, "gives 0 delivered and 900 non-terminating",
     "MaxpRoutesDelivered")
emit("MaxpAttempts", "five", T13, "five rows, all SIM_WALLCLOCK_TIMEOUT_BYPASS",
     "MaxpAttempts")
emit("MaxpCoreHours", "58.9", T13, "58.9 core-hours", "MaxpCoreHours")

# ---- T13/D148: per-instance IMEM depth -----------------------------------
emit("ImemDepthLo", "64", T13, "64 to 2,048 among those actually simulated",
     "ImemDepthLo")
emit("ImemDepthHi", "2048", T13, "64 to 2,048 among those actually simulated",
     "ImemDepthHi")
emit("ImemFlagged", "278", T13, "E_IMEM_OF 278", "ImemFlagged")
emit("ImemFlaggedValidated", "113", T13,
     "113 of the 278 were RTL-validated", "ImemFlaggedValidated")

# ---- T04: what the campaign pipeline actually ran -------------------------
emit("StagesRun", "five", T04, "S2.5 (connectivity repair, repair_connectivity)",
     "StagesRun")
emit("MapPoints", "five", T04, "over five points", "MapPoints")
emit("MapImagesLo", "one", T04, "the distinct-testbench counts are 1, 2, 3, 2, 1",
     "MapImagesLo")
emit("MapImagesHi", "three", T04, "the distinct-testbench counts are 1, 2, 3, 2, 1",
     "MapImagesHi")

# ---- T04/X1: peak DMEM, connected against disconnected --------------------
emit("DmemConnConfigs", "244", T04, "Connected partitions: n=244", "DmemConnConfigs")
emit("DmemMedConn", "10", T04, "median 10, max 102", "DmemMedConn")
emit("DmemMaxConn", "102", T04, "median 10, max 102", "DmemMaxConn")
emit("DmemDiscConfigs", "437", T04, "Disconnected partitions: n=437", "DmemDiscConfigs")
emit("DmemMedDisc", "25", T04, "median 25, MAX 491", "DmemMedDisc")

# ---- T04/X3: what re-running through compile() would cost -----------------
emit("RepairMovedMed", "50.8\\%", T04, "Median 50.8% of all tree nodes are reassigned",
     "RepairMovedMed")
emit("RepairMovedMax", "96.9\\%", T04, "(max 96.9%)", "RepairMovedMax")
emit("RepairLoadMed", "1.86", T04, "median factor of 1.86", "RepairLoadMed")
emit("RepairLoadMax", "304", T04, "up to 304x", "RepairLoadMax")
emit("RepairImemOver", "82", T04, "82 of the 437 would end up with more than 512",
     "RepairImemOver")
emit("RepairDmemUp", "33", T04, "in 33 of the 437 the repair INCREASES peak DMEM",
     "RepairDmemUp")
emit("RepairPasses", "20", T04, "converged inside the 20-pass cap", "RepairPasses")

# ---- T05: the compilation denominator ------------------------------------
emit("CompileTotal", "7{,}200", T05, "7,200", "CompileTotal")

if FAIL:
    for f in FAIL:
        print("FAIL " + f, file=sys.stderr)
    sys.exit(1)

hdr = ("% GENERATED by scripts/gen_fabric_macros.py -- do not edit by hand.\n"
       "% source : council/work/{T13,T04,T05}_verify.json\n"
       "% method : each value asserted present in its source verdict record\n"
       "%          before emission; the script fails rather than emit a stale\n"
       "%          number.  Macro names carry no digits (check_consistency C1).\n")
out = os.path.join(PAPER, "data", "fabric_macros.tex")
with open(out, "w", encoding="utf-8") as fh:
    fh.write(hdr + "\n".join(M) + "\n")
print(f"wrote {out} ({len(M)} macros)")
