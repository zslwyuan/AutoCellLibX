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
from timing_power import stage_delay_slew, stage_energy

_FUNC_RE = re.compile(r"function\s*:\s*\"([^\"]*)\"")
_DIR_RE = re.compile(r"direction\s*:\s*(\w+)")
SUPPLY_NAMES = {"VCC", "GND", "VDD", "VSS"}

# gscl45nm delay_template_6x6 grid (rows: load pF, cols: slew ns)
DEFAULT_LOADS = [0.1, 0.5, 1.2, 3.0, 4.0, 5.0]
DEFAULT_SLEWS = [0.06, 0.24, 0.48, 0.9, 1.2, 1.8]


def load_liberty_functions(lib_file_name):
    """{(cell_name, out_pin): function-string} from a liberty file."""
    text = open(lib_file_name).read()
    functions = {}
    for cell_args, cell_body in _sliceBlocks(text, "cell"):
        name = cell_args.split()[0] if cell_args else cell_args
        for pin_args, pin_body in _sliceBlocks(cell_body, "pin"):
            dir_m = _DIR_RE.search(pin_body)
            func_m = _FUNC_RE.search(pin_body)
            if (dir_m and dir_m.group(1) == "output" and func_m):
                functions[(name, pin_args)] = func_m.group(1)
    return functions


def _substitute(func_text, pin_expr):
    """Whole-word pin substitution into a fully parenthesised function."""
    out = func_text
    for pin, expr in sorted(pin_expr.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(pin) +
                     r"(?![A-Za-z0-9_])", "(" + expr + ")", out)
    return out


def liberty_pin_name(port_name):
    """Liberty-safe port name: `#` is not a valid liberty identifier
    character (yosys rejects it), so cl<k>#<pin> becomes cl<k>_<pin>.
    Injective for the exported port set (k and base pin names contain
    only letters/digits)."""
    return port_name.replace("#", "_")


def _clusterInterface(members, electrical_metrics):
    """Split member pins into interface inputs/outputs + the member DAG.

    Mirrors spice.py's port logic: a member input pin is an interface
    input when its driver is outside the cluster; a member output pin is
    an interface output unless every load sits inside the cluster.
    Returns (inputs, outputs, edges, net_driver) where edges maps
    member index -> set(member indices it drives), and pin/net tuples
    carry (member_idx, pin_name).
    """
    inside = set(c.id for c in members)
    indexOf = {c.id: k for k, c in enumerate(members)}
    inputs, outputs = [], []
    edges = {k: set() for k in range(len(members))}
    net_driver = {}                    # net id -> (member_idx, pin_name)

    def nets_of(cell, pin_idx, ref_names, net_names, nets):
        """All DesignNet objects belonging to one pin: name-matched when
        the flow populated net_names, positional otherwise (a pin may fan
        out over several nets -- zip() would silently drop the rest)."""
        name = net_names[pin_idx] if pin_idx < len(net_names) else None
        matched = [n for n in nets if n.name == name] if name else []
        if (matched):
            return matched
        return [nets[pin_idx]] if pin_idx < len(nets) else []

    for k, cell in enumerate(members):
        for i, pin_name in enumerate(cell.input_pin_ref_names):
            nets = nets_of(cell, i, cell.input_pin_ref_names,
                          cell.input_net_names, cell.input_nets)
            if (not nets):
                # no net object at all -> driven from outside the cluster
                inputs.append((k, pin_name))
                continue
            for net in nets:
                if (net.pred_cell is None or net.pred_cell.id not in inside):
                    inputs.append((k, pin_name))
                    break
        for i, pin_name in enumerate(cell.output_pin_ref_names):
            escaped = False
            for net in nets_of(cell, i, cell.output_pin_ref_names,
                              cell.output_net_names, cell.output_nets):
                net_driver[net.id] = (k, pin_name)
                if (len(net.succ_cells) == 0
                        or not all(s.id in inside for s in net.succ_cells)):
                    escaped = True
                for succ_cell in net.succ_cells:
                    if (succ_cell.id in inside):
                        edges[k].add(indexOf[succ_cell.id])
            if (escaped):
                outputs.append((k, pin_name))
    return inputs, outputs, edges, net_driver


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


def _sweepSta(members, edges, outputs, out_load_pf, in_slew_ns,
              lut_metrics, electrical_metrics):
    """Arrival at each output pin for one (load, slew) grid point."""
    inside = set(c.id for c in members)
    arrival = {}                      # member_idx -> (arrival_ns, slew_ns)
    order = _stageArrivalOrder(members, edges)
    out_set = set(outputs)
    for k in order:
        cell = members[k]
        # input slew / arrival from the latest driving member
        stage_in, slew_in = 0.0, in_slew_ns
        load = 0.0
        for net in cell.output_nets:
            for succ_cell, succ_pin in zip(net.succ_cells, net.succ_pins):
                if (succ_cell.id in inside):
                    m = electrical_metrics.get(
                        succ_cell.std_cell_type.type_name)
                    if (m is not None):
                        load += m.get("pin_caps", {}).get(succ_pin, 0.0)
            if (net.pred_cell is None):
                continue
        for net in cell.input_nets:
            pred = net.pred_cell
            if (pred is not None and pred.id in inside):
                pk = None
                for kk, cc in enumerate(members):
                    if (cc.id == pred.id):
                        pk = kk
                        break
                if (pk is not None and pk in arrival):
                    stage_in = max(stage_in, arrival[pk][0])
                    slew_in = max(slew_in, arrival[pk][1])
        # external load on interface outputs
        for pin_name, net in zip(cell.output_pin_ref_names, cell.output_nets):
            if ((k, pin_name) in out_set):
                load += out_load_pf
        tm = lut_metrics.get(cell.std_cell_type.type_name, {})
        delay, slew_out = stage_delay_slew(tm, load, slew_in)
        arrival[k] = (stage_in + delay, slew_out)
    result = {}
    for (k, pin_name) in outputs:
        result[(k, pin_name)] = arrival.get(k, (0.0, in_slew_ns))
    # toggle energy of the whole pattern at this corner
    energy = 0.0
    for k in order:
        cell = members[k]
        tm = lut_metrics.get(cell.std_cell_type.type_name, {})
        load = 0.0
        for net in cell.output_nets:
            for succ_cell, succ_pin in zip(net.succ_cells, net.succ_pins):
                if (succ_cell.id in inside):
                    m = electrical_metrics.get(
                        succ_cell.std_cell_type.type_name)
                    if (m is not None):
                        load += m.get("pin_caps", {}).get(succ_pin, 0.0)
        _a, s_in = arrival.get(k, (0.0, in_slew_ns))
        energy += stage_energy(tm, load, s_in)
    return result, energy


def _composeFunction(out_pin, members, net_driver, lib_functions, port_name_of):
    """Boolean function of one interface output pin, composed through
    the members' own liberty functions (None when uncomposable).

    Members share pin names (NAND2X1 and OR2X1 both have A/B), so the
    substitution map of an outer member would also hit the *inner*
    expressions' same-named pins.  Each member's function is therefore
    tokenised with a unique ``@@<k>@@<pin>@@`` placeholder first, then
    the map is applied in one pass -- tokens cannot collide with
    anything inside a sub-expression."""
    def expr_of(member_idx, pin_name, depth):
        if (depth > len(members) + 1):
            return None
        func = lib_functions.get(
            (members[member_idx].std_cell_type.type_name, pin_name))
        if (func is None):
            return None
        cell = members[member_idx]
        # unique-ify this member's own pins
        token_map = {}
        for p_name in cell.input_pin_ref_names:
            token = "@@%d@@%s@@" % (member_idx, p_name)
            func = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(p_name) +
                          r"(?![A-Za-z0-9_])", token, func)
            token_map[p_name] = token
        pin_expr = {}
        for i, p_name in enumerate(cell.input_pin_ref_names):
            token = token_map[p_name]
            net = cell.input_nets[i] if i < len(cell.input_nets) else None
            if (net is None or net.pred_cell is None):
                pin_expr[token] = port_name_of(member_idx, p_name)
                continue
            found = None
            for kk, cc in enumerate(members):
                if (cc.id == net.pred_cell.id):
                    found = kk
                    break
            if (found is None):
                pin_expr[token] = port_name_of(member_idx, p_name)
            else:
                _drvK, drv_pin = net_driver[net.id]
                sub = expr_of(found, drv_pin, depth + 1)
                if (sub is None):
                    return None
                pin_expr[token] = sub
        return _substitute(func, pin_expr)
    return expr_of(out_pin[0], out_pin[1], 0)


def generate_complex_liberty(cluster_seq, complex_name, width_um,
                           lut_metrics, electrical_metrics, lib_functions,
                           row_height_um=2.47, loads=None, slews=None):
    """Emit (lib_text, report) for one generated complex cell."""
    loads = loads or DEFAULT_LOADS
    slews = slews or DEFAULT_SLEWS
    members = list(cluster_seq.pattern_clusters[0].cells)
    inside = set(c.id for c in members)
    inputs, outputs, edges, net_driver = _clusterInterface(
        members, electrical_metrics)

    def port_name_of(member_idx, pin_name):
        return liberty_pin_name("cl%d#%s" % (member_idx, pin_name))

    leakage = 0.0
    for cell in members:
        m = electrical_metrics.get(cell.std_cell_type.type_name)
        if (m is not None):
            leakage += m["leakage"]
    area = width_um * row_height_um

    lines = []
    lines.append("  cell (%s) {" % complex_name)
    lines.append("    area : %.6f;" % area)
    lines.append("    cell_leakage_power : %.6f;" % leakage)
    lines.append("    /* pattern: %s */"
                 % cluster_seq.pattern_clusters[0].pattern_extension_trace)
    lines.append("    /* estimated pre-layout (LUT mini-STA, no wire RC);"
                 " re-characterise with SPICE for sign-off */")

    for k, pin_name in inputs:
        m = electrical_metrics.get(members[k].std_cell_type.type_name)
        cap = m.get("pin_caps", {}).get(pin_name, 0.0) if m else 0.0
        lines.append("    pin (%s)  {" % port_name_of(k, pin_name))
        lines.append("      direction : input;")
        lines.append("      capacitance : %.8f;" % cap)
        lines.append("    }")
    for out_pin in outputs:
        k, pin_name = out_pin
        func = _composeFunction(out_pin, members, net_driver,
                                lib_functions, port_name_of)
        lines.append("    pin (%s)  {" % port_name_of(k, pin_name))
        lines.append("      direction : output;")
        lines.append("      capacitance : 0;")
        lines.append("      max_capacitance : 0;")
        if (func is not None):
            lines.append('      function : "%s";' % func)
        else:
            lines.append('      /* function unavailable (base cell '
                         'function missing) */')
        # sweep the grid once per output: delay + transition tables
        delay_table, slew_table = [], []
        energy_table = []
        for load in loads:
            delay_row, slew_row, energy_row = [], [], []
            for slew in slews:
                arrivals, energy = _sweepSta(
                    members, edges, outputs, load, slew,
                    lut_metrics, electrical_metrics)
                delay_row.append(arrivals[out_pin][0])
                slew_row.append(arrivals[out_pin][1])
                energy_row.append(energy)
            delay_table.append(delay_row)
            slew_table.append(slew_row)
            energy_table.append(energy_row)

        input_port_names = [port_name_of(kk, pp) for kk, pp in inputs]
        related = input_port_names[0] if input_port_names else "?"
        lines.append("      timing() {")
        lines.append('        related_pin : "%s";' % related)

        def table_lines(kind, table, unit_comment):
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

        table_lines("cell_rise", delay_table, "ns; worst-arc estimate")
        table_lines("cell_fall", delay_table, "ns; same as rise (estimate)")
        table_lines("rise_transition", slew_table, "ns")
        table_lines("fall_transition", slew_table, "ns")
        lines.append("      }")
        lines.append("      internal_power() {")
        lines.append('        related_pin : "%s";' % related)
        table_lines("rise_power", energy_table, "per toggle")
        table_lines("fall_power", energy_table, "per toggle")
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


def parse_spice_example_cells(sp_text):
    """(trace, [example member .subckt lines in cluster order]) from a
    generated COMPLEX*.sp's trailing comments."""
    trace_m = _TRACE_COMMENT_RE.search(sp_text)
    trace = trace_m.group(1).strip() if trace_m else None
    members = _EXAMPLE_RE.findall(sp_text)
    return trace, members


def rebuild_cluster_from_spice(sp_path, cells):
    """Reconstruct the exact cluster a generated .sp was exported from,
    by matching the '* Example occurence' member lines to design cells
    (DesignCell.name is the .subckt line verbatim)."""
    from blif_graph_util import DesignPatternCluster, DesignPatternClusterSeq

    text = open(sp_path).read()
    trace, member_names = parse_spice_example_cells(text)
    if (trace is None or not member_names):
        raise ValueError("no pattern trace / example cells in %s" % sp_path)
    by_name = {}
    for c in cells:
        by_name.setdefault(c.name, c)
    members = []
    for name in member_names:
        cell = by_name.get(name)
        if (cell is None):
            raise ValueError("example cell not found in the design graph: %s"
                             % name)
        members.append(cell)
    cluster = DesignPatternCluster(
        0, trace, cells, [c.id for c in members], 0)
    seq = DesignPatternClusterSeq(trace)
    seq.add_cluster(cluster)
    return seq


def generate_liberty_for_spice_file(sp_path, cells, lut_metrics,
                                electrical_metrics, lib_functions,
                                row_height_um=2.47):
    """(.lib fragment, report) for an already-generated COMPLEX*.sp,
    taking the width from the sibling .Astranlog."""
    log_path = os.path.splitext(sp_path)[0] + ".Astranlog"
    width = None
    if (os.path.exists(log_path)):
        for line in open(log_path, 'r', errors="ignore"):
            if (line.find("-> Cell Size (W x H): ") >= 0):
                width = float(line.replace(
                    "-> Cell Size (W x H): ", "").split("x")[0])
    if (width is None or width <= 0):
        raise RuntimeError("no usable width in %s" % log_path)
    seq = rebuild_cluster_from_spice(sp_path, cells)
    name = os.path.splitext(os.path.basename(sp_path))[0]
    return generate_complex_liberty(seq, name, width, lut_metrics,
                                  electrical_metrics, lib_functions,
                                  row_height_um=row_height_um)
