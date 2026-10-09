"""Liberty (.lib) generation for generated COMPLEX cells.

Question answered here: after ASTRAN regenerates a layout, the .sp does
*not* change (it is the mining product and ASTRAN's input -- the cache
contract watches its mtime), but the complex cell has **no liberty
entry at all**: the library only covers the 31 base cells.  To reuse a
complex cell downstream (map onto it, run STA, or just cross-check its
numbers), it needs a .lib fragment with area / pin capacitances /
leakage / timing / power.

What can be filled honestly without simulation:

* **area**      -- width (from .Astranlog) x row height.  Sanity anchor:
                   NAND2X1 LEF 0.76 x 2.47 = 1.877200 == its lib `area`.
* **leakage**   -- sum of member `cell_leakage_power` (same transistors).
* **pin caps**  -- each input port is a base-cell pin: its capacitance
                   comes straight from the base liberty entry.
* **timing**    -- mini-STA over the member DAG (same primitives as
                   timing_power.py) swept over the base lib's 6x6
                   (load x slew) grid, producing proper delay/transition
                   LUTs.  Pre-layout estimate: worst-arc, no wire RC.
* **power**     -- internal_power tables swept the same way from the
                   member LUT energies.
* **function**  -- Boolean composition of the members' liberty function
                   strings through the internal nets (fully parenthesised
                   infix: space=AND, +=OR, ^=XOR, !=NOT).

The fragment merges with the base library for re-mapping experiments;
characterisation-quality numbers still need SPICE (the .sp is ready for
ngspice -- see AUDIT_REPORT 5.21).
"""

import os
import re

from electrical import _sliceBlocks
from timing_power import stageDelaySlew, stageEnergy

_FUNC_RE = re.compile(r"function\s*:\s*\"([^\"]*)\"")
_DIR_RE = re.compile(r"direction\s*:\s*(\w+)")
SUPPLY_NAMES = {"VCC", "GND", "VDD", "VSS"}

# gscl45nm delay_template_6x6 grid (rows: load pF, cols: slew ns)
DEFAULT_LOADS = [0.1, 0.5, 1.2, 3.0, 4.0, 5.0]
DEFAULT_SLEWS = [0.06, 0.24, 0.48, 0.9, 1.2, 1.8]


def loadLibertyFunctions(libFileName):
    """{(cellName, outPin): function-string} from a liberty file."""
    text = open(libFileName).read()
    functions = {}
    for cellArgs, cellBody in _sliceBlocks(text, "cell"):
        name = cellArgs.split()[0] if cellArgs else cellArgs
        for pinArgs, pinBody in _sliceBlocks(cellBody, "pin"):
            dirM = _DIR_RE.search(pinBody)
            funcM = _FUNC_RE.search(pinBody)
            if (dirM and dirM.group(1) == "output" and funcM):
                functions[(name, pinArgs)] = funcM.group(1)
    return functions


def _substitute(funcText, pinExpr):
    """Whole-word pin substitution into a fully parenthesised function."""
    out = funcText
    for pin, expr in sorted(pinExpr.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(pin) +
                     r"(?![A-Za-z0-9_])", "(" + expr + ")", out)
    return out


def libertyPinName(portName):
    """Liberty-safe port name: `#` is not a valid liberty identifier
    character (yosys rejects it), so cl<k>#<pin> becomes cl<k>_<pin>.
    Injective for the exported port set (k and base pin names contain
    only letters/digits)."""
    return portName.replace("#", "_")


def _clusterInterface(members, electricalMetrics):
    """Split member pins into interface inputs/outputs + the member DAG.

    Mirrors spice.py's port logic: a member input pin is an interface
    input when its driver is outside the cluster; a member output pin is
    an interface output unless every load sits inside the cluster.
    Returns (inputs, outputs, edges, netDriver) where edges maps
    member index -> set(member indices it drives), and pin/net tuples
    carry (memberIdx, pinName).
    """
    inside = set(c.id for c in members)
    indexOf = {c.id: k for k, c in enumerate(members)}
    inputs, outputs = [], []
    edges = {k: set() for k in range(len(members))}
    netDriver = {}                    # net id -> (memberIdx, pinName)
    for k, cell in enumerate(members):
        for pinName, net in zip(cell.inputPinRefNames, cell.inputNets):
            if (net.predCell is None or net.predCell.id not in inside):
                inputs.append((k, pinName))
        for pinName, net in zip(cell.outputPinRefNames, cell.outputNets):
            netDriver[net.id] = (k, pinName)
            if (len(net.succCells) == 0
                    or not all(s.id in inside for s in net.succCells)):
                outputs.append((k, pinName))
            for succCell in net.succCells:
                if (succCell.id in inside):
                    edges[k].add(indexOf[succCell.id])
    return inputs, outputs, edges, netDriver


def _stageArrivalOrder(members, edges):
    """Topological order of member indices (few members; fixpoint loop)."""
    order = []
    done = set()
    preds = {k: set() for k in range(len(members))}
    for src, dsts in edges.items():
        for d in dsts:
            preds[d].add(src)
    while (len(order) < len(members)):
        progressed = False
        for k in range(len(members)):
            if (k not in done and preds[k] <= done):
                order.append(k)
                done.add(k)
                progressed = True
        if (not progressed):
            break                      # cycle fallback: keep remaining order
    for k in range(len(members)):
        if (k not in done):
            order.append(k)
    return order


def _sweepSta(members, edges, outputs, outLoadPf, inSlewNs,
              lutMetrics, electricalMetrics):
    """Arrival at each output pin for one (load, slew) grid point."""
    inside = set(c.id for c in members)
    arrival = {}                      # memberIdx -> (arrivalNs, slewNs)
    order = _stageArrivalOrder(members, edges)
    outSet = set(outputs)
    for k in order:
        cell = members[k]
        # input slew / arrival from the latest driving member
        stageIn, slewIn = 0.0, inSlewNs
        load = 0.0
        for net in cell.outputNets:
            for succCell, succPin in zip(net.succCells, net.succPins):
                if (succCell.id in inside):
                    m = electricalMetrics.get(
                        succCell.stdCellType.typeName)
                    if (m is not None):
                        load += m.get("pin_caps", {}).get(succPin, 0.0)
            if (net.predCell is None):
                continue
        for net in cell.inputNets:
            pred = net.predCell
            if (pred is not None and pred.id in inside):
                pk = None
                for kk, cc in enumerate(members):
                    if (cc.id == pred.id):
                        pk = kk
                        break
                if (pk is not None and pk in arrival):
                    stageIn = max(stageIn, arrival[pk][0])
                    slewIn = max(slewIn, arrival[pk][1])
        # external load on interface outputs
        for pinName, net in zip(cell.outputPinRefNames, cell.outputNets):
            if ((k, pinName) in outSet):
                load += outLoadPf
        tm = lutMetrics.get(cell.stdCellType.typeName, {})
        delay, slewOut = stageDelaySlew(tm, load, slewIn)
        arrival[k] = (stageIn + delay, slewOut)
    result = {}
    for (k, pinName) in outputs:
        result[(k, pinName)] = arrival.get(k, (0.0, inSlewNs))
    # toggle energy of the whole pattern at this corner
    energy = 0.0
    for k in order:
        cell = members[k]
        tm = lutMetrics.get(cell.stdCellType.typeName, {})
        load = 0.0
        for net in cell.outputNets:
            for succCell, succPin in zip(net.succCells, net.succPins):
                if (succCell.id in inside):
                    m = electricalMetrics.get(
                        succCell.stdCellType.typeName)
                    if (m is not None):
                        load += m.get("pin_caps", {}).get(succPin, 0.0)
        _a, sIn = arrival.get(k, (0.0, inSlewNs))
        energy += stageEnergy(tm, load, sIn)
    return result, energy


def _composeFunction(outPin, members, netDriver, libFunctions, portNameOf):
    """Boolean function of one interface output pin, composed through
    the members' own liberty functions (None when uncomposable)."""
    def exprOf(memberIdx, pinName, depth):
        if (depth > len(members) + 1):
            return None
        func = libFunctions.get(
            (members[memberIdx].stdCellType.typeName, pinName))
        if (func is None):
            return None
        cell = members[memberIdx]
        pinExpr = {}
        for pName, net in zip(cell.inputPinRefNames, cell.inputNets):
            if (net.predCell is None):
                pinExpr[pName] = portNameOf(memberIdx, pName)
                continue
            found = None
            for kk, cc in enumerate(members):
                if (cc.id == net.predCell.id):
                    found = kk
                    break
            if (found is None):
                pinExpr[pName] = portNameOf(memberIdx, pName)
            else:
                _drvK, drvPin = netDriver[net.id]
                sub = exprOf(found, drvPin, depth + 1)
                if (sub is None):
                    return None
                pinExpr[pName] = sub
        return _substitute(func, pinExpr)
    return exprOf(outPin[0], outPin[1], 0)


def generateComplexLiberty(cluserSeq, complexName, widthUm,
                           lutMetrics, electricalMetrics, libFunctions,
                           rowHeightUm=2.47, loads=None, slews=None):
    """Emit (libText, report) for one generated complex cell."""
    loads = loads or DEFAULT_LOADS
    slews = slews or DEFAULT_SLEWS
    members = list(cluserSeq.patternClusters[0].cellsContained)
    inside = set(c.id for c in members)
    inputs, outputs, edges, netDriver = _clusterInterface(
        members, electricalMetrics)

    def portNameOf(memberIdx, pinName):
        return libertyPinName("cl%d#%s" % (memberIdx, pinName))

    leakage = 0.0
    for cell in members:
        m = electricalMetrics.get(cell.stdCellType.typeName)
        if (m is not None):
            leakage += m["leakage"]
    area = widthUm * rowHeightUm

    lines = []
    lines.append("  cell (%s) {" % complexName)
    lines.append("    area : %.6f;" % area)
    lines.append("    cell_leakage_power : %.6f;" % leakage)
    lines.append("    /* pattern: %s */"
                 % cluserSeq.patternClusters[0].patternExtensionTrace)
    lines.append("    /* estimated pre-layout (LUT mini-STA, no wire RC);"
                 " re-characterise with SPICE for sign-off */")

    for k, pinName in inputs:
        m = electricalMetrics.get(members[k].stdCellType.typeName)
        cap = m.get("pin_caps", {}).get(pinName, 0.0) if m else 0.0
        lines.append("    pin (%s)  {" % portNameOf(k, pinName))
        lines.append("      direction : input;")
        lines.append("      capacitance : %.8f;" % cap)
        lines.append("    }")
    for outPin in outputs:
        k, pinName = outPin
        func = _composeFunction(outPin, members, netDriver,
                                libFunctions, portNameOf)
        lines.append("    pin (%s)  {" % portNameOf(k, pinName))
        lines.append("      direction : output;")
        lines.append("      capacitance : 0;")
        lines.append("      max_capacitance : 0;")
        if (func is not None):
            lines.append('      function : "%s";' % func)
        else:
            lines.append('      /* function unavailable (base cell '
                         'function missing) */')
        # sweep the grid once per output: delay + transition tables
        delayTable, slewTable = [], []
        energyTable = []
        for load in loads:
            delayRow, slewRow, energyRow = [], [], []
            for slew in slews:
                arrivals, energy = _sweepSta(
                    members, edges, outputs, load, slew,
                    lutMetrics, electricalMetrics)
                delayRow.append(arrivals[outPin][0])
                slewRow.append(arrivals[outPin][1])
                energyRow.append(energy)
            delayTable.append(delayRow)
            slewTable.append(slewRow)
            energyTable.append(energyRow)

        inputPortNames = [portNameOf(kk, pp) for kk, pp in inputs]
        related = inputPortNames[0] if inputPortNames else "?"
        lines.append("      timing() {")
        lines.append('        related_pin : "%s";' % related)

        def tableLines(kind, table, unit_comment):
            idx1 = ", ".join("%g" % v for v in loads)
            idx2 = ", ".join("%g" % v for v in slews)
            lines.append('        %s(delay_template_6x6) {  /* %s */'
                         % (kind, unit_comment))
            lines.append('          index_1 ("%s");' % idx1)
            lines.append('          index_2 ("%s");' % idx2)
            lines.append("          values ( \\")
            for r, row in enumerate(table):
                suffix = "," if r < len(table) - 1 else ");"
                lines.append('            "%s"%s'
                             % (", ".join("%.6f" % v for v in row), suffix))
            lines.append("        }")

        tableLines("cell_rise", delayTable, "ns; worst-arc estimate")
        tableLines("cell_fall", delayTable, "ns; same as rise (estimate)")
        tableLines("rise_transition", slewTable, "ns")
        tableLines("fall_transition", slewTable, "ns")
        lines.append("      }")
        lines.append("      internal_power() {")
        lines.append('        related_pin : "%s";' % related)
        tableLines("rise_power", energyTable, "per toggle")
        tableLines("fall_power", energyTable, "per toggle")
        lines.append("      }")
        lines.append("    }")
    lines.append("  }")

    report = {
        "area": area, "leakage": leakage,
        "inputs": len(inputs), "outputs": len(outputs),
        "grid": "%dx%d" % (len(loads), len(slews)),
    }
    return "\n".join(lines) + "\n", report


# ---------------------------------------------------------------------------
# Rebuild a cluster from an exported .sp (no re-mining needed)
# ---------------------------------------------------------------------------

_TRACE_COMMENT_RE = re.compile(r"^\* pattern code: (.+)$", re.M)
_EXAMPLE_RE = re.compile(r"^\*\s+(\.subckt\s+.+)$", re.M)


def parseSpiceExampleCells(spText):
    """(trace, [example member .subckt lines in cluster order]) from a
    generated COMPLEX*.sp's trailing comments."""
    traceM = _TRACE_COMMENT_RE.search(spText)
    trace = traceM.group(1).strip() if traceM else None
    members = _EXAMPLE_RE.findall(spText)
    return trace, members


def rebuildClusterFromSpice(spPath, cells):
    """Reconstruct the exact cluster a generated .sp was exported from,
    by matching the '* Example occurence' member lines to design cells
    (DesignCell.name is the .subckt line verbatim)."""
    from BLIFGraphUtil import DesignPatternCluster, DesignPatternClusterSeq

    text = open(spPath).read()
    trace, memberNames = parseSpiceExampleCells(text)
    if (trace is None or not memberNames):
        raise ValueError("no pattern trace / example cells in %s" % spPath)
    byName = {}
    for c in cells:
        byName.setdefault(c.name, c)
    members = []
    for name in memberNames:
        cell = byName.get(name)
        if (cell is None):
            raise ValueError("example cell not found in the design graph: %s"
                             % name)
        members.append(cell)
    cluster = DesignPatternCluster(
        0, trace, cells, [c.id for c in members], 0)
    seq = DesignPatternClusterSeq(trace)
    seq.addCluster(cluster)
    return seq


def generateLibertyForSpiceFile(spPath, cells, lutMetrics,
                                electricalMetrics, libFunctions,
                                rowHeightUm=2.47):
    """(.lib fragment, report) for an already-generated COMPLEX*.sp,
    taking the width from the sibling .Astranlog."""
    logPath = os.path.splitext(spPath)[0] + ".Astranlog"
    width = None
    if (os.path.exists(logPath)):
        for line in open(logPath, 'r', errors="ignore"):
            if (line.find("-> Cell Size (W x H): ") >= 0):
                width = float(line.replace(
                    "-> Cell Size (W x H): ", "").split("x")[0])
    if (width is None or width <= 0):
        raise RuntimeError("no usable width in %s" % logPath)
    seq = rebuildClusterFromSpice(spPath, cells)
    name = os.path.splitext(os.path.basename(spPath))[0]
    return generateComplexLiberty(seq, name, width, lutMetrics,
                                  electricalMetrics, libFunctions,
                                  rowHeightUm=rowHeightUm)
