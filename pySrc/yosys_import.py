"""Re-import Yosys synthesis statistics (user priority: delay/power/area).

The benchmarks are produced by Yosys+ABC (benchmark/syn.ys), but the
flow only kept the BLIF structure.  Yosys' ``stat`` reports design-level
numbers on the technology-mapped netlist -- cell histogram and, with the
liberty file's ``area`` attributes, total cell area.  This module runs

    yosys -Q -T -p "read_liberty -lib <lib>; read_blif <blif>;
                    stat -json <report>"

and parses the report defensively (key presence and string/number
coercion are tolerated; a schema drift in a new Yosys version degrades
to missing metrics, not crashes).  Yosys itself does no STA: delay and
power come from the liberty LUTs via pySrc/timing_power.py -- this
module additionally cross-checks our lib-derived area sums against the
numbers Yosys reports, so a disagreement is visible instead of silent.

When no yosys executable is found, everything degrades gracefully
(``runYosysStat`` returns ok=False with a reason) -- the flow never
hard-depends on it.
"""

import json
import os
import shutil
import subprocess
import tempfile

YOSYS_CANDIDATES = [
    "yosys", "yosys.exe",
    r"C:\msys64\mingw64\bin\yosys.exe",
    r"C:\msys64\usr\bin\yosys.exe",
    "/usr/bin/yosys", "/usr/local/bin/yosys",
]


def findYosys():
    """First yosys executable on PATH or in the usual places; None."""
    for cand in YOSYS_CANDIDATES:
        path = shutil.which(cand)
        if (path):
            return path
        if (os.path.exists(cand)):
            return os.path.abspath(cand)
    return None


def _asFloat(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parseStatJson(text):
    """Defensive parse of ``stat -json`` output.

    Returns {"area": float|None, "num_cells": int|None,
             "histogram": {type: int}, "modules": [names]} -- the union
    over modules (a flattened benchmark has exactly one).
    """
    data = json.loads(text)
    modules = data.get("modules", {}) if isinstance(data, dict) else {}
    totalArea = 0.0
    haveArea = False
    totalCells = 0
    haveCells = False
    histogram = {}
    for _name, mod in modules.items():
        if (not isinstance(mod, dict)):
            continue
        area = _asFloat(mod.get("area"))
        if (area is not None):
            totalArea += area
            haveArea = True
        cells = _asFloat(mod.get("num_cells"))
        if (cells is not None):
            totalCells += int(cells)
            haveCells = True
        hist = mod.get("cell_histogram")
        if (isinstance(hist, dict)):
            for cellType, cnt in hist.items():
                cntF = _asFloat(cnt)
                if (cntF is not None):
                    histogram[cellType] = \
                        histogram.get(cellType, 0) + int(cntF)
    return {
        "area": totalArea if haveArea else None,
        "num_cells": totalCells if haveCells else None,
        "histogram": histogram,
        "modules": sorted(modules.keys()),
    }


def runYosysStat(libPath, blifPath, yosysExe=None, timeout=300):
    """Run ``stat -json`` on one BLIF; dict with ok/area/num_cells/... """
    exe = yosysExe or findYosys()
    if (exe is None):
        return {"ok": False,
                "reason": "no yosys executable found (PATH/MSYS2 probed)"}
    with tempfile.TemporaryDirectory() as tmp:
        reportPath = os.path.join(tmp, "stat.json")
        script = ("read_liberty -lib %s; read_blif %s; stat -json %s"
                  % (libPath, blifPath, reportPath))
        try:
            proc = subprocess.run(
                [exe, "-Q", "-T", "-p", script],
                capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "reason": "yosys launch failed: %s" % exc}
        if (not os.path.exists(reportPath)):
            return {"ok": False,
                    "reason": "yosys wrote no report (rc=%d): %s"
                    % (proc.returncode, (proc.stderr or "")[-400:])}
        result = parseStatJson(open(reportPath).read())
        result["ok"] = True
        return result


def compareWithFlowArea(yosysStat, flowAreaSum):
    """Cross-check yosys' area against the flow's lib-derived sum."""
    report = {"flow_area": flowAreaSum}
    if (not yosysStat.get("ok")):
        report["compared"] = False
        report["reason"] = yosysStat.get("reason", "unavailable")
        return report
    report["compared"] = True
    report["yosys_area"] = yosysStat.get("area")
    if (yosysStat.get("area") is not None and flowAreaSum):
        report["rel_diff"] = abs(yosysStat["area"] - flowAreaSum) / \
            flowAreaSum
    return report
