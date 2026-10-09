"""Liberty timing/power lookup tables and a mini pattern-level STA.

User priority: re-import delay/power/area -- the data the flow used to
throw away.  This module parses, per cell type, the liberty timing arcs

    timing() { related_pin : "A";
               cell_rise/fall (delay_template)  {index_1, index_2, values}
               rise/fall_transition (...)       {...} }
    internal_power() { rise_power/fall_power (...) {...} }

(delay_template_6x6: variable_1 = total_output_net_capacitance -- rows,
variable_2 = input_net_transition -- columns; time in ns, cap in pF,
energy in the lib's energy unit) and evaluates them with bilinear
interpolation (edge-clamped: the lib's load grid starts at 0.1 pF while
a fanout-4 load is ~0.01 pF -- clamping is the standard approximation).

On top of the tables, ``patternTimingPower`` runs a tiny static timing
analysis over the pattern's DAG: per-net load = sum of the driven pins'
capacitances, stage delay = worst arc of cell_rise/cell_fall at that
load, output slew from the transition tables, longest path wins.  It is
deliberately a *proxy* (no wire RC, worst-arc reduction, nominal input
slew) -- honest numbers for ranking candidates, not sign-off STA.
"""

import os
import re

from electrical import _sliceBlocks

_num = r"([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"
_RELATED_RE = re.compile(r"related_pin\s*:\s*\"?(\w+)\"?")
_INDEX_RE = re.compile(r"index_[12]\s*\(([^)]*)\)", re.S)
_VALUES_RE = re.compile(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?")

_TABLE_KINDS = ("cell_rise", "cell_fall", "rise_transition",
                "fall_transition", "rise_power", "fall_power")

_lut_cache = {}


def _parseTable(blockText):
    """(loads, slews, values[row][col]) from one LUT block; None if bad."""
    indices = _INDEX_RE.findall(blockText)
    vpos = blockText.find("values")
    if (len(indices) != 2 or vpos < 0):
        return None
    loads = [float(v) for v in _VALUES_RE.findall(indices[0])]
    slews = [float(v) for v in _VALUES_RE.findall(indices[1])]
    flat = [float(v) for v in _VALUES_RE.findall(blockText[vpos:])]
    if (len(flat) != len(loads) * len(slews)):
        return None
    values = [flat[r * len(slews):(r + 1) * len(slews)]
              for r in range(len(loads))]
    return (loads, slews, values)


def loadTimingPower(libFileName):
    """{typeName: {arcs: {pin: {kind: table}}, power: {kind: table}}}
    for one .lib file (cached per (path, mtime))."""
    key = (os.path.abspath(libFileName), os.path.getmtime(libFileName))
    if (key in _lut_cache):
        return _lut_cache[key]

    text = open(libFileName).read()
    lib = {}
    for cellArgs, cellBody in _sliceBlocks(text, "cell"):
        name = cellArgs.split()[0] if cellArgs else cellArgs
        arcs = {}
        power = {}
        for _tArgs, timingBody in _sliceBlocks(cellBody, "timing"):
            m = _RELATED_RE.search(timingBody)
            related = m.group(1) if m else "?"
            for kind in _TABLE_KINDS[:4]:
                for _args, tableBody in _sliceBlocks(timingBody, kind):
                    table = _parseTable(tableBody)
                    if (table is not None):
                        arcs.setdefault(related, {})[kind] = table
        for _pArgs, powerBody in _sliceBlocks(cellBody, "internal_power"):
            m = _RELATED_RE.search(powerBody)
            related = m.group(1) if m else "?"
            for kind in _TABLE_KINDS[4:]:
                for _args, tableBody in _sliceBlocks(powerBody, kind):
                    table = _parseTable(tableBody)
                    if (table is not None):
                        power.setdefault(related, {})[kind] = table
        lib[name] = {"arcs": arcs, "power": power}

    _lut_cache[key] = lib
    return lib


def bilinear(grid1, grid2, values, x1, x2):
    """Bilinear interpolation on a monotone grid, edge-clamped."""
    def bracket(grid, x):
        if (x <= grid[0]):
            return 0, 0, 0.0
        if (x >= grid[-1]):
            return len(grid) - 1, len(grid) - 1, 0.0
        for i in range(1, len(grid)):
            if (x <= grid[i]):
                t = (x - grid[i - 1]) / (grid[i] - grid[i - 1])
                return i - 1, i, t
        return len(grid) - 1, len(grid) - 1, 0.0

    i0, i1, t1 = bracket(grid1, x1)
    j0, j1, t2 = bracket(grid2, x2)
    v00 = values[i0][j0]
    v01 = values[i0][j1]
    v10 = values[i1][j0]
    v11 = values[i1][j1]
    top = v00 + (v01 - v00) * t2
    bot = v10 + (v11 - v10) * t2
    return top + (bot - top) * t1


def stageDelaySlew(typeMetrics, loadPf, inputSlewNs):
    """(delay, output slew) of a cell stage: worst over its timing arcs
    and over rise/fall, at the given output load and input slew."""
    delay = 0.0
    slew = inputSlewNs
    for _pin, arcTables in typeMetrics.get("arcs", {}).items():
        for kind, acc in (("cell_rise", "d"), ("cell_fall", "d"),
                          ("rise_transition", "s"),
                          ("fall_transition", "s")):
            table = arcTables.get(kind)
            if (table is None):
                continue
            loads, slews, values = table
            v = bilinear(loads, slews, values, loadPf, inputSlewNs)
            if (acc == "d"):
                delay = max(delay, v)
            else:
                slew = max(slew, v)
    return delay, slew


def stageEnergy(typeMetrics, loadPf, inputSlewNs):
    """Average rise/fall energy of one full output toggle (worst pin)."""
    best = 0.0
    for _pin, tables in typeMetrics.get("power", {}).items():
        total = 0.0
        count = 0
        for kind in ("rise_power", "fall_power"):
            table = tables.get(kind)
            if (table is None):
                continue
            loads, slews, values = table
            total += bilinear(loads, slews, values, loadPf, inputSlewNs)
            count += 1
        if (count):
            best = max(best, total / count)
    return best


def patternTimingPower(exampleCells, lutMetrics, electricalMetrics,
                       defaultInputSlewNs=0.06):
    """Mini-STA over one pattern instance.

    Per-net load = sum of the driven pins' capacitances (wire RC
    neglected); stages are visited in topological order; per stage the
    worst-arc delay at its actual output load; returns the longest path
    delay, the total toggle energy (sum of per-stage energies), and the
    per-stage breakdown for inspection.
    """
    inside = set(c.id for c in exampleCells)

    def netLoad(net):
        load = 0.0
        for succCell, succPin in zip(net.succCells, net.succPins):
            m = electricalMetrics.get(succCell.stdCellType.typeName)
            if (m is not None):
                load += m.get("pin_caps", {}).get(succPin, 0.0)
        return load

    # longest-path in topological order (cells are few; iterate to fixpoint)
    arrival = {}          # cell id -> (arrivalNs, slewNs)
    order = list(exampleCells)
    progressed = True
    guard = 0
    while (progressed and guard <= len(order) * len(order)):
        progressed = False
        guard += 1
        for cell in order:
            if (cell.id in arrival):
                continue
            inputArrivals = []
            ready = True
            for net in cell.inputNets:
                pred = net.predCell
                if (pred is None or pred.id not in inside):
                    inputArrivals.append((0.0, defaultInputSlewNs))
                elif (pred.id in arrival):
                    inputArrivals.append(arrival[pred.id])
                else:
                    ready = False
            if (not ready):
                continue
            tm = lutMetrics.get(cell.stdCellType.typeName, {})
            stageIn = max((a for a, _s in inputArrivals), default=0.0)
            slewIn = max((s for _a, s in inputArrivals),
                         default=defaultInputSlewNs)
            # the stage's own output nets drive its fanout load
            load = 0.0
            for net in cell.outputNets:
                load = max(load, netLoad(net))
            delay, slewOut = stageDelaySlew(tm, load, slewIn)
            arrival[cell.id] = (stageIn + delay, slewOut)
            progressed = True

    criticalPath = max((a for a, _s in arrival.values()), default=0.0)
    energy = 0.0
    for cell in order:
        tm = lutMetrics.get(cell.stdCellType.typeName, {})
        load = 0.0
        for net in cell.outputNets:
            load = max(load, netLoad(net))
        _a, slewIn = arrival.get(cell.id, (0.0, defaultInputSlewNs))
        energy += stageEnergy(tm, load, slewIn)

    return {
        "critical_path_ns": criticalPath,
        "toggle_energy": energy,
        "stages_timed": len(arrival),
    }
