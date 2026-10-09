"""Per-cell electrical metrics from the liberty file (roadmap P1-7).

The flow's cost model was width-only: the liberty parser kept pin
directions and discarded the timing/power payload (759 lines of it in
gscl45nm.lib).  This module reads back three electrical quantities per
cell type and aggregates them per pattern, so a candidate's benefit can
be reported as more than "N um narrower":

* ``leakage``      -- ``cell_leakage_power`` (static power proxy;
                      unchanged by merging, reported for context);
* ``input_cap``    -- sum of input-pin ``capacitance`` (load a driver
                      sees; internalised pins *remove* this load);
* ``delay_proxy``  -- plain average of the ``cell_rise``/``cell_fall``
                      LUT values (crude intrinsic-delay proxy -- a real
                      delay number needs slew/load interpolation and is
                      documented as future work).

Plus the pattern-level ``internal_nets``: member output nets whose
loads are all inside the cluster.  Internalising a net removes its
wire capacitance from the outside world, which is the dominant
*dynamic* power saving of merging -- width alone never sees it.
"""

import os
import re

_num = r"([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"
_LEAK_RE = re.compile(r"cell_leakage_power\s*:\s*" + _num)
_AREA_RE = re.compile(r"^\s*area\s*:\s*" + _num, re.M)
_CAP_RE = re.compile(r"^\s*capacitance\s*:\s*" + _num, re.M)
_DIR_RE = re.compile(r"direction\s*:\s*(\w+)")
_VALUES_RE = re.compile(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?")

# parse cache keyed like blif_preproc._liberty_cache (path, mtime)
_electrical_cache = {}


def _sliceBlocks(text, keyword, start_pos=0):
    """Yield (args, body) for each ``keyword (args) { ... }`` block whose
    opening brace starts at nesting depth 1 relative to start_pos."""
    idx = start_pos
    while (True):
        m = re.search(re.escape(keyword) + r"\s*\(([^)]*)\)\s*\{",
                      text[idx:])
        if (not m):
            return
        args = m.group(1).replace("\"", "").replace("'", "").strip()
        depth = 1
        pos = idx + m.end()
        while (depth > 0 and pos < len(text)):
            if (text[pos] == "{"):
                depth += 1
            elif (text[pos] == "}"):
                depth -= 1
            pos += 1
        yield args, text[idx + m.end():pos - 1]
        idx = pos


def load_cell_electrical_metrics(lib_file_name):
    """{type_name: {leakage, input_cap, delay_proxy}} for one .lib file."""
    key = (os.path.abspath(lib_file_name), os.path.getmtime(lib_file_name))
    if (key in _electrical_cache):
        # Copy per entry: callers must not pollute the shared cache.
        return {k: dict(v) for k, v in _electrical_cache[key].items()}

    text = open(lib_file_name).read()
    metrics = {}
    for cell_args, cell_body in _sliceBlocks(text, "cell"):
        name = cell_args.split()[0] if cell_args else cell_args
        m = _LEAK_RE.search(cell_body)
        leakage = float(m.group(1)) if m else 0.0
        m = _AREA_RE.search(cell_body)
        area = float(m.group(1)) if m else None
        input_cap = 0.0
        pin_caps = {}
        delay_vals = []
        for pin_args, pin_body in _sliceBlocks(cell_body, "pin"):
            dir_m = _DIR_RE.search(pin_body)
            cap_m = _CAP_RE.search(pin_body)
            if (cap_m):
                pin_caps[pin_args] = float(cap_m.group(1))
            if (dir_m and dir_m.group(1) == "input" and cap_m):
                input_cap += float(cap_m.group(1))
        for kind in ("cell_rise", "cell_fall"):
            for _args, table_body in _sliceBlocks(cell_body, kind):
                vpos = table_body.find("values")
                if (vpos >= 0):
                    delay_vals.extend(
                        float(v) for v in
                        _VALUES_RE.findall(table_body[vpos:]))
        metrics[name] = {
            "leakage": leakage,
            "area": area,
            "input_cap": input_cap,
            "pin_caps": pin_caps,
            "delay_proxy": (sum(delay_vals) / len(delay_vals)
                            if delay_vals else None),
        }

    _electrical_cache[key] = metrics
    return metrics


def pattern_electrical_metrics(example_cells, cell_metrics):
    """Aggregate member-cell metrics for one pattern instance.

    ``internal_nets`` counts member output nets whose loads are all
    inside the pattern: each is a wire-capacitance (and its driver
    energy) removed from the outside world by the merge.
    """
    inside = set(c.id for c in example_cells)
    leakage_sum = 0.0
    area_sum = 0.0
    input_cap_sum = 0.0
    delay_vals = []
    internal_nets = 0
    for cell in example_cells:
        m = cell_metrics.get(cell.std_cell_type.type_name)
        if (m is not None):
            leakage_sum += m["leakage"]
            area_sum += m.get("area") or 0.0
            input_cap_sum += m["input_cap"]
            if (m["delay_proxy"] is not None):
                delay_vals.append(m["delay_proxy"])
        for out_net in cell.output_nets:
            if (len(out_net.succ_cells) > 0
                    and all(s.id in inside for s in out_net.succ_cells)):
                internal_nets += 1
    return {
        "leakage_sum": leakage_sum,
        "area_sum": area_sum,
        "input_cap_sum": input_cap_sum,
        "delay_proxy_avg": (sum(delay_vals) / len(delay_vals)
                            if delay_vals else None),
        "internal_nets": internal_nets,
    }
