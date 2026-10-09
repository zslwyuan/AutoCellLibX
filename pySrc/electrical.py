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
_CAP_RE = re.compile(r"^\s*capacitance\s*:\s*" + _num, re.M)
_DIR_RE = re.compile(r"direction\s*:\s*(\w+)")
_VALUES_RE = re.compile(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?")

# parse cache keyed like BLIFPreProc._liberty_cache (path, mtime)
_electrical_cache = {}


def _sliceBlocks(text, keyword, startPos=0):
    """Yield (args, body) for each ``keyword (args) { ... }`` block whose
    opening brace starts at nesting depth 1 relative to startPos."""
    idx = startPos
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


def loadCellElectricalMetrics(libFileName):
    """{typeName: {leakage, input_cap, delay_proxy}} for one .lib file."""
    key = (os.path.abspath(libFileName), os.path.getmtime(libFileName))
    if (key in _electrical_cache):
        # Copy per entry: callers must not pollute the shared cache.
        return {k: dict(v) for k, v in _electrical_cache[key].items()}

    text = open(libFileName).read()
    metrics = {}
    for cellArgs, cellBody in _sliceBlocks(text, "cell"):
        name = cellArgs.split()[0] if cellArgs else cellArgs
        m = _LEAK_RE.search(cellBody)
        leakage = float(m.group(1)) if m else 0.0
        inputCap = 0.0
        delayVals = []
        for pinArgs, pinBody in _sliceBlocks(cellBody, "pin"):
            dirM = _DIR_RE.search(pinBody)
            capM = _CAP_RE.search(pinBody)
            if (dirM and dirM.group(1) == "input" and capM):
                inputCap += float(capM.group(1))
        for kind in ("cell_rise", "cell_fall"):
            for _args, tableBody in _sliceBlocks(cellBody, kind):
                vpos = tableBody.find("values")
                if (vpos >= 0):
                    delayVals.extend(
                        float(v) for v in
                        _VALUES_RE.findall(tableBody[vpos:]))
        metrics[name] = {
            "leakage": leakage,
            "input_cap": inputCap,
            "delay_proxy": (sum(delayVals) / len(delayVals)
                            if delayVals else None),
        }

    _electrical_cache[key] = metrics
    return metrics


def patternElectricalMetrics(exampleCells, cellMetrics):
    """Aggregate member-cell metrics for one pattern instance.

    ``internal_nets`` counts member output nets whose loads are all
    inside the pattern: each is a wire-capacitance (and its driver
    energy) removed from the outside world by the merge.
    """
    inside = set(c.id for c in exampleCells)
    leakageSum = 0.0
    inputCapSum = 0.0
    delayVals = []
    internalNets = 0
    for cell in exampleCells:
        m = cellMetrics.get(cell.stdCellType.typeName)
        if (m is not None):
            leakageSum += m["leakage"]
            inputCapSum += m["input_cap"]
            if (m["delay_proxy"] is not None):
                delayVals.append(m["delay_proxy"])
        for outNet in cell.outputNets:
            if (len(outNet.succCells) > 0
                    and all(s.id in inside for s in outNet.succCells)):
                internalNets += 1
    return {
        "leakage_sum": leakageSum,
        "input_cap_sum": inputCapSum,
        "delay_proxy_avg": (sum(delayVals) / len(delayVals)
                            if delayVals else None),
        "internal_nets": internalNets,
    }
