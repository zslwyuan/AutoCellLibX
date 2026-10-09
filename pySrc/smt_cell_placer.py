"""SAT-style joint folding + placement reference implementation (P2 stage 4).

ASTRAN's transistor layout is sequential: placement (threshold accepting)
first, ILP compaction later.  Recent literature (SAT-based joint folding +
placement, ASP-DAC'26) shows the two decisions interact -- folding a wide
transistor into parallel legs changes both diffusion sharing and row width,
so solving them jointly finds strictly smaller cells.  This module is the
planned *reference implementation* for that idea: it takes a SPICE
subcircuit of at most ~12-16 transistors, solves folding + placement
jointly with OR-Tools CP-SAT, and reports the minimal row width on the
routing grid.  It exists to score ASTRAN's quality (P2_MERGE_PLAN stage 4),
NOT to replace the flow -- see doc/P2_MERGE_PLAN.md.

Model (two diffusion rows per polarity, like ASTRAN's double-row packing):

- every transistor is placed in a P row or an N row (two rows per
  polarity, chosen by the solver -- ASTRAN stacks two P and two N
  diffusions in the 2.47 um row, which is where most of its width win
  over a single-row model comes from);
- transistors connected through an internal node (degree-2 node that is
  not a subcircuit port) form a *series chain*; chain members must share
  a row and abut (end of one == start of the next) so they share
  diffusion;
- a transistor can be *folded* into k parallel legs, each of width
  ceil(w / k) on the grid; the legs occupy k contiguous columns.  A leg is
  capped at ``maxLegUm`` (a manufacturing limit on one diffusion finger,
  like ASTRAN's foldTrans): folding only ever widens a block (ceil
  division), so without that cap the optimum is always k=1 and the joint
  choice would be meaningless.  The joint solve picks the k whose waste is
  smallest while the chain still abuts;
- different chains must not overlap (NoOverlap2D over row + column
  intervals).

Deliberate simplifications (documented so the score stays explainable):
parallel-group diffusion sharing, diffusion-break spacing between
unrelated chains, diffusion-sharing row stickiness (parallel PMOS may
split across the two rows, which ASTRAN would not do), and intra-cell
routing are not modelled -- width is an idealized lower bound, and the
comparison table says so.  ASTRAN usually wins or ties once routing
overhead counts, which is exactly the quality signal the reference is
for.

Determinism: CP-SAT is deterministic for an identical model, and every
iteration here is over sorted structures, so two runs on the same machine
give the same placement (AGENTS.md invariant 9).

Usage:
    from smt_cell_placer import placeCell
    result = placeCell("outputs/adder/COMPLEX0.sp", gridUm=0.19)
    print(result.widthUm)
"""

import argparse
import collections
import math
import os
import re

from ortools.sat.python import cp_model

DEFAULT_GRID_UM = 0.19          # routing grid of the GSCL45 binding
MIN_LEG_UM = 0.4                # below this a transistor is not worth folding
MAX_LEG_UM = 1.0                # cap on one diffusion finger (manufacturing)
_SOLVE_TIME_LIMIT_S = 60.0      # per cell; tests lower it
_OBJECTIVE_WIDTH_WEIGHT = 1000  # width dominates; leg count breaks ties

_SPICE_MOS_RE = re.compile(
    r"^(?P<name>M[A-Za-z0-9_#]+)\s+(?P<drain>\S+)\s+(?P<gate>\S+)"
    r"\s+(?P<source>\S+)\s+(?P<bulk>\S+)\s+(?P<type>PMOS|NMOS)"
    r"(?:\s+W=(?P<w>[0-9.]+)u)?",
    re.MULTILINE | re.IGNORECASE)
_SUBCKT_RE = re.compile(
    r"\.subckt\s+(?P<name>\S+)\s+(?P<ports>[^\n]+)", re.IGNORECASE)


class Device(object):
    """One MOS transistor of a subcircuit."""

    def __init__(self, name, drain, gate, source, bulk, isP, widthUm):
        self.name = name
        self.drain = drain
        self.gate = gate
        self.source = source
        self.bulk = bulk
        self.isP = isP
        self.widthUm = widthUm

    def __repr__(self):
        return "Device(%s, %s, w=%.2f)" % (
            self.name, "P" if self.isP else "N", self.widthUm)


class TransistorNetlist(object):
    """Parsed subcircuit: port list + devices (in file order)."""

    def __init__(self, subcktName, ports, devices):
        self.subcktName = subcktName
        self.ports = list(ports)
        self.devices = list(devices)

    @property
    def externalNodes(self):
        return set(self.ports)


def parseSpiceSubckt(text):
    """Parse the first .subckt block; return TransistorNetlist.

    Mirrors spice.py's reader in the small: 'M<name> d g s b PMOS W=xu L=yu'
    lines (the '+' continuation lines are ignored -- the flow writes one
    device per physical line).  Raises ValueError on a missing subckt or on
    a MOS line without a parseable width.
    """
    m = _SUBCKT_RE.search(text)
    if (m is None):
        raise ValueError("no .subckt block found")
    subcktName = m.group("name")
    ports = m.group("ports").split()
    devices = []
    for line in text.splitlines():
        mm = _SPICE_MOS_RE.match(line.strip())
        if (mm is None):
            continue
        w = float(mm.group("w")) if mm.group("w") is not None else 0.5
        devices.append(Device(
            mm.group("name"), mm.group("drain"), mm.group("gate"),
            mm.group("source"), mm.group("bulk"),
            mm.group("type").upper() == "PMOS", w))
    if (not devices):
        raise ValueError("no MOS devices found in subckt %s" % subcktName)
    return TransistorNetlist(subcktName, ports, devices)


def findSeriesChains(netlist):
    """Group devices into series chains via degree-2 internal nodes.

    A node with exactly two device terminals that is not a subcircuit port
    is a diffusion-sharing point: the two devices on it are in series.
    Chains are walked deterministically (devices sorted by name, then the
    unique path through internal nodes); standalone devices come back as
    length-1 chains.
    """
    nodeTerms = collections.defaultdict(list)
    for dev in netlist.devices:
        nodeTerms[dev.source].append((dev, "s"))
        nodeTerms[dev.drain].append((dev, "d"))
    internal = set()
    for node, terms in nodeTerms.items():
        if (node in netlist.externalNodes):
            continue
        if (len(terms) == 2 and terms[0][0] is not terms[1][0]):
            internal.add(node)

    chains = []
    used = set()
    for dev in sorted(netlist.devices, key=lambda d: d.name):
        if (dev in used):
            continue
        chain = [dev]
        used.add(dev)
        # walk right from the last device through internal nodes
        while (True):
            last = chain[-1]
            nxt = None
            for node in (last.drain, last.source):
                if (node in internal):
                    for other, _ in nodeTerms[node]:
                        if (other is not last and other not in used):
                            nxt = (node, other)
                            break
                if (nxt is not None):
                    break
            if (nxt is None):
                break
            chain.append(nxt[1])
            used.add(nxt[1])
        # walk left from the first device (rare: chain built from an
        # interior device because of the name-sorted iteration)
        while (True):
            first = chain[0]
            nxt = None
            for node in (first.drain, first.source):
                if (node in internal):
                    for other, _ in nodeTerms[node]:
                        if (other is not first and other not in used):
                            nxt = (node, other)
                            break
                if (nxt is not None):
                    break
            if (nxt is None):
                break
            chain.insert(0, nxt[1])
            used.add(nxt[1])
        chains.append(chain)
    # deterministic order: longest chains first, then first device name
    chains.sort(key=lambda c: (-len(c), c[0].name))
    return chains


class PlacementResult(object):
    """Solved placement of one cell."""

    def __init__(self, statusName, widthCols, widthUm, devices):
        self.statusName = statusName
        self.widthCols = widthCols
        self.widthUm = widthUm
        self.devices = devices          # list of PlacedDevice

    def asDict(self):
        return {
            "status": self.statusName,
            "width_cols": self.widthCols,
            "width_um": round(self.widthUm, 4),
            "devices": [d.asDict() for d in self.devices],
        }


class PlacedDevice(object):
    def __init__(self, name, isP, row, startCol, legs, legWidthCols):
        self.name = name
        self.isP = isP
        self.row = row
        self.startCol = startCol
        self.legs = legs
        self.legWidthCols = legWidthCols

    @property
    def endCol(self):
        return self.startCol + self.legs * self.legWidthCols

    def asDict(self):
        return {
            "name": self.name,
            "type": "P" if self.isP else "N",
            "row": self.row,
            "start_col": self.startCol,
            "end_col": self.endCol,
            "legs": self.legs,
            "leg_width_cols": self.legWidthCols,
        }


def buildSmtModel(netlist, gridUm=DEFAULT_GRID_UM, minLegUm=MIN_LEG_UM,
                  maxLegUm=MAX_LEG_UM, maxWidthUm=None):
    """Build the CP-SAT joint folding+placement model.

    Returns (model, Wvar, endVars, devVars, chains) where devVars maps
    Device -> (startVar, kVar, legwVar, blockWVar, endVar).  Exposed for
    tests; placeCell() wraps it.
    """
    model = cp_model.CpModel()
    wCols = {}
    for dev in netlist.devices:
        cols = int(round(dev.widthUm / gridUm))
        wCols[dev] = max(1, cols)
    if (maxWidthUm is None):
        maxWidthUm = 4.0 * sum(wCols.values()) * gridUm
    widthUb = max(1, int(math.ceil(maxWidthUm / gridUm)))

    minLegCols = max(1, int(math.ceil(minLegUm / gridUm)))
    maxLegCols = max(1, int(math.ceil(maxLegUm / gridUm)))
    chains = findSeriesChains(netlist)

    devVars = {}
    endVars = []
    perPolarity = {"P": [], "N": []}       # (x interval, y interval) pairs
    for dev in netlist.devices:
        maxFold = max(1, int(math.ceil(wCols[dev] / minLegCols)))
        start = model.NewIntVar(0, widthUb, "start_%s" % dev.name)
        row = model.NewIntVar(0, 1, "row_%s" % dev.name)   # 2 rows/polarity
        k = model.NewIntVar(1, maxFold, "k_%s" % dev.name)
        num = model.NewIntVar(0, wCols[dev] + maxFold, "num_%s" % dev.name)
        legw = model.NewIntVar(1, wCols[dev], "legw_%s" % dev.name)
        block = model.NewIntVar(1, widthUb + 1, "block_%s" % dev.name)
        end = model.NewIntVar(1, widthUb + 1, "end_%s" % dev.name)
        # legw == ceil(wCols / k) == (wCols + k - 1) // k
        model.Add(num == wCols[dev] + k - 1)
        model.AddDivisionEquality(legw, num, k)
        model.Add(legw <= maxLegCols)      # manufacturing cap on one finger
        model.AddMultiplicationEquality(block, k, legw)
        model.Add(end == start + block)
        interval = model.NewIntervalVar(start, block, end, "iv_%s" % dev.name)
        rowInterval = model.NewIntervalVar(row, 1, row + 1,
                                           "rowiv_%s" % dev.name)
        devVars[dev] = (start, row, k, legw, block, end, interval, rowInterval)
        endVars.append(end)
        perPolarity["P" if dev.isP else "N"].append((interval, rowInterval))

    for polarity, pairs in perPolarity.items():
        if (len(pairs) > 1):
            model.AddNoOverlap2D(
                [p[0] for p in pairs], [p[1] for p in pairs])

    # series chains: same row, member i+1 starts where member i ends
    for chain in chains:
        for a, b in zip(chain, chain[1:]):
            model.Add(devVars[a][1] == devVars[b][1])
            model.Add(devVars[a][5] == devVars[b][0])

    width = model.NewIntVar(1, widthUb + 1, "width")
    model.AddMaxEquality(width, endVars)
    totalLegs = model.NewIntVar(1, sum(
        max(1, int(math.ceil(wCols[dev] / minLegCols))) for dev in netlist.devices),
        "total_legs")
    kAll = [devVars[dev][2] for dev in netlist.devices]
    model.Add(sum(kAll) == totalLegs)
    model.Minimize(width * _OBJECTIVE_WIDTH_WEIGHT + totalLegs)
    return model, width, endVars, devVars, chains


def _statusName(status):
    return {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE"}.get(status, "UNKNOWN")


def placeCell(spPath, gridUm=DEFAULT_GRID_UM, minLegUm=MIN_LEG_UM,
              maxLegUm=MAX_LEG_UM, timeLimitS=_SOLVE_TIME_LIMIT_S):
    """Solve folding+placement for one .sp file; return PlacementResult.

    Solver failures degrade to the objective upper bound recorded by the
    solver (never fabricated): widthCols is the best feasible width the
    solver found, or None when even the trivial bound failed (kept as
    status UNKNOWN so callers can tell a real result from a breakdown).
    """
    with open(spPath, 'r', errors="ignore") as f:
        text = f.read()
    netlist = parseSpiceSubckt(text)
    model, width, endVars, devVars, chains = buildSmtModel(
        netlist, gridUm=gridUm, minLegUm=minLegUm, maxLegUm=maxLegUm)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeLimitS
    status = solver.Solve(model)
    if (status not in (cp_model.OPTIMAL, cp_model.FEASIBLE)):
        return PlacementResult(_statusName(status), None, None, [])
    placed = []
    for dev in netlist.devices:
        start, row, k, legw, block, end, _, _ = devVars[dev]
        placed.append(PlacedDevice(
            dev.name, dev.isP, solver.Value(row),
            solver.Value(start), solver.Value(k), solver.Value(legw)))
    widthCols = solver.Value(width)
    return PlacementResult(
        _statusName(status), widthCols, widthCols * gridUm, placed)


def astranWidthFromLog(logPath):
    """ASTRAN cell width (um) from its log; None when absent."""
    if (not os.path.exists(logPath)):
        return None
    for line in open(logPath, 'r', errors="ignore"):
        if ("-> Cell Size (W x H): " in line):
            return float(line.split("-> Cell Size (W x H): ")[1]
                         .split("x")[0])
    return None


def compareWithAstran(spPath, logPath=None, gridUm=DEFAULT_GRID_UM,
                      timeLimitS=_SOLVE_TIME_LIMIT_S):
    """Width comparison for one cell: {smt, astran, ratio}."""
    result = placeCell(spPath, gridUm=gridUm, timeLimitS=timeLimitS)
    astran = astranWidthFromLog(logPath) if logPath else None
    row = {
        "cell": os.path.basename(spPath).replace(".sp", ""),
        "smt_status": result.statusName,
        "smt_width_um": result.widthUm,
    }
    if (astran is not None and result.widthUm is not None):
        row["astran_width_um"] = astran
        row["ratio"] = round(result.widthUm / astran, 3)
    else:
        row["astran_width_um"] = astran
        row["ratio"] = None
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="SMT joint folding+placement reference implementation")
    ap.add_argument("--sp", help="one .sp subcircuit file")
    ap.add_argument("--dir", help="directory of .sp files (pairs with "
                    "<name>.Astranlog)")
    ap.add_argument("--grid", type=float, default=DEFAULT_GRID_UM)
    ap.add_argument("--time-limit", type=float, default=_SOLVE_TIME_LIMIT_S)
    args = ap.parse_args(argv)
    spFiles = [args.sp] if args.sp else []
    if (args.dir):
        spFiles += sorted(os.path.join(args.dir, f) for f in
                          os.listdir(args.dir) if f.endswith(".sp"))
    if (not spFiles):
        ap.error("pass --sp FILE or --dir DIR")
    for sp in spFiles:
        log = sp[:-3] + ".Astranlog" if args.dir else None
        row = compareWithAstran(sp, log, gridUm=args.grid,
                                timeLimitS=args.time_limit)
        print("%(cell)-14s %(smt_status)-10s smt=%(smt_width_um)-8s "
              "astran=%(astran_width_um)-8s ratio=%(ratio)s" % row)


if (__name__ == "__main__"):
    main()
