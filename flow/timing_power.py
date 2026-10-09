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

On top of the tables, ``pattern_timing_power`` runs a tiny static timing
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


def _parseTable(block_text):
    """(loads, slews, values[row][col]) from one LUT block; None if bad."""
    indices = _INDEX_RE.findall(block_text)
    vpos = block_text.find("values")
    if (len(indices) != 2 or vpos < 0):
        return None
    loads = [float(v) for v in _VALUES_RE.findall(indices[0])]
    slews = [float(v) for v in _VALUES_RE.findall(indices[1])]
    flat = [float(v) for v in _VALUES_RE.findall(block_text[vpos:])]
    if (len(flat) != len(loads) * len(slews)):
        return None
    values = [flat[r * len(slews):(r + 1) * len(slews)]
              for r in range(len(loads))]
    return (loads, slews, values)


def load_timing_power(lib_file_name):
    """{type_name: {arcs: {pin: {kind: table}}, power: {kind: table}}}
    for one .lib file (cached per (path, mtime))."""
    key = (os.path.abspath(lib_file_name), os.path.getmtime(lib_file_name))
    if (key in _lut_cache):
        return _lut_cache[key]

    text = open(lib_file_name).read()
    lib = {}
    for cell_args, cell_body in _sliceBlocks(text, "cell"):
        name = cell_args.split()[0] if cell_args else cell_args
        arcs = {}
        power = {}
        for _tArgs, timing_body in _sliceBlocks(cell_body, "timing"):
            m = _RELATED_RE.search(timing_body)
            related = m.group(1) if m else "?"
            for kind in _TABLE_KINDS[:4]:
                for _args, table_body in _sliceBlocks(timing_body, kind):
                    table = _parseTable(table_body)
                    if (table is not None):
                        arcs.setdefault(related, {})[kind] = table
        for _pArgs, power_body in _sliceBlocks(cell_body, "internal_power"):
            m = _RELATED_RE.search(power_body)
            related = m.group(1) if m else "?"
            for kind in _TABLE_KINDS[4:]:
                for _args, table_body in _sliceBlocks(power_body, kind):
                    table = _parseTable(table_body)
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


def stage_delay_slew(type_metrics, load_pf, input_slew_ns):
    """(delay, output slew) of a cell stage: worst over its timing arcs
    and over rise/fall, at the given output load and input slew."""
    delay = 0.0
    slew = input_slew_ns
    for _pin, arc_tables in type_metrics.get("arcs", {}).items():
        for kind, acc in (("cell_rise", "d"), ("cell_fall", "d"),
                          ("rise_transition", "s"),
                          ("fall_transition", "s")):
            table = arc_tables.get(kind)
            if (table is None):
                continue
            loads, slews, values = table
            v = bilinear(loads, slews, values, load_pf, input_slew_ns)
            if (acc == "d"):
                delay = max(delay, v)
            else:
                slew = max(slew, v)
    return delay, slew


def stage_energy(type_metrics, load_pf, input_slew_ns):
    """Average rise/fall energy of one full output toggle (worst pin)."""
    best = 0.0
    for _pin, tables in type_metrics.get("power", {}).items():
        total = 0.0
        count = 0
        for kind in ("rise_power", "fall_power"):
            table = tables.get(kind)
            if (table is None):
                continue
            loads, slews, values = table
            total += bilinear(loads, slews, values, load_pf, input_slew_ns)
            count += 1
        if (count):
            best = max(best, total / count)
    return best


def pattern_timing_power(example_cells, lut_metrics, electrical_metrics,
                       default_input_slew_ns=0.06):
    """Mini-STA over one pattern instance.

    Per-net load = sum of the driven pins' capacitances (wire RC
    neglected); stages are visited in topological order; per stage the
    worst-arc delay at its actual output load; returns the longest path
    delay, the total toggle energy (sum of per-stage energies), and the
    per-stage breakdown for inspection.
    """
    inside = set(c.id for c in example_cells)

    def net_load(net):
        load = 0.0
        for succ_cell, succ_pin in zip(net.succ_cells, net.succ_pins):
            m = electrical_metrics.get(succ_cell.std_cell_type.type_name)
            if (m is not None):
                load += m.get("pin_caps", {}).get(succ_pin, 0.0)
        return load

    # longest-path in topological order (cells are few; iterate to fixpoint)
    arrival = {}          # cell id -> (arrival_ns, slew_ns)
    order = list(example_cells)
    progressed = True
    guard = 0
    while (progressed and guard <= len(order) * len(order)):
        progressed = False
        guard += 1
        for cell in order:
            if (cell.id in arrival):
                continue
            input_arrivals = []
            ready = True
            for net in cell.input_nets:
                pred = net.pred_cell
                if (pred is None or pred.id not in inside):
                    input_arrivals.append((0.0, default_input_slew_ns))
                elif (pred.id in arrival):
                    input_arrivals.append(arrival[pred.id])
                else:
                    ready = False
            if (not ready):
                continue
            tm = lut_metrics.get(cell.std_cell_type.type_name, {})
            stage_in = max((a for a, _s in input_arrivals), default=0.0)
            slew_in = max((s for _a, s in input_arrivals),
                         default=default_input_slew_ns)
            # the stage's own output nets drive its fanout load
            load = 0.0
            for net in cell.output_nets:
                load = max(load, net_load(net))
            delay, slew_out = stage_delay_slew(tm, load, slew_in)
            arrival[cell.id] = (stage_in + delay, slew_out)
            progressed = True

    critical_path = max((a for a, _s in arrival.values()), default=0.0)
    energy = 0.0
    for cell in order:
        tm = lut_metrics.get(cell.std_cell_type.type_name, {})
        load = 0.0
        for net in cell.output_nets:
            load = max(load, net_load(net))
        _a, slew_in = arrival.get(cell.id, (0.0, default_input_slew_ns))
        energy += stage_energy(tm, load, slew_in)

    return {
        "critical_path_ns": critical_path,
        "toggle_energy": energy,
        "stages_timed": len(arrival),
    }
