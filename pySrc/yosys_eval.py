"""Design-level area evaluation by re-mapping with Yosys (user request).

The flow's native savings number is a width summation: occurrences x
(member widths - complex width).  The honest end-to-end check is to let
the synthesiser re-map the design with the generated cells available
and read the mapped area:

    baseline : read_liberty -lib gscl45nm.lib;
               read_blif <bench>; abc -liberty gscl45nm.lib; stat -json
    extended : same with gscl45nm.lib + COMPLEX<n>.lib fragments merged

ABC does the technology mapping by *function* (which is why
liberty_gen composes the Boolean functions), so the complex cells are
genuinely eligible candidates -- the area difference is the savings the
tool itself can find, not our estimate of it.

Works with any yosys executable (yowasp-yosys on this machine); degrades
gracefully when none is found.
"""

import os
import re
import subprocess

from yosys_import import findYosys, parseStatJson


def buildExtendedLiberty(baseLibText, fragmentTexts):
    """Merge `cell (...) {...}` fragments into a base library text."""
    insertAt = baseLibText.rfind("}")
    if (insertAt < 0):
        raise ValueError("base liberty text has no closing brace")
    merged = (baseLibText[:insertAt]
              + "\n  /* --- generated complex cells --- */\n"
              + "\n".join(fragmentTexts) + "\n"
              + baseLibText[insertAt:])
    return merged


def runYosysMappedArea(libPath, blifPath, yosysExe=None, timeout=900):
    """abc -liberty remap + stat; returns the parsed stat dict (ok=...)."""
    exe = yosysExe or findYosys()
    if (exe is None):
        return {"ok": False,
                "reason": "no yosys executable found"}
    script = ("read_liberty -lib %s; read_blif %s; abc -liberty %s; "
              "stat -json" % (libPath, blifPath, libPath))
    try:
        proc = subprocess.run(
            [exe, "-Q", "-T", "-p", script],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": "yosys launch failed: %s" % exc}
    try:
        result = parseStatJson(proc.stdout or "")
    except Exception as exc:                       # noqa: BLE001
        return {"ok": False,
                "reason": "no JSON in yosys output (rc=%d): %s | %s"
                % (proc.returncode, (proc.stdout or "")[-200:],
                   (proc.stderr or "")[-200:])}
    result["ok"] = True
    return result


def compareMappedArea(baselineStat, extendedStat):
    """Area + complex-cell usage comparison of two mapped stats."""
    report = {"compared": False}
    if (not (baselineStat.get("ok") and extendedStat.get("ok"))):
        report["reason"] = "baseline: %s | extended: %s" % (
            baselineStat.get("reason", "?"),
            extendedStat.get("reason", "?"))
        return report
    report["compared"] = True
    report["baseline_area"] = baselineStat.get("area")
    report["extended_area"] = extendedStat.get("area")
    b, e = baselineStat.get("area"), extendedStat.get("area")
    if (b and e):
        report["area_saved"] = b - e
        report["area_saved_pct"] = (b - e) / b * 100.0
    complexHist = {t: n for t, n in
                   extendedStat.get("histogram", {}).items()
                   if re.match(r"COMPLEX", t)}
    report["complex_cells_used"] = complexHist
    report["complex_instances"] = sum(complexHist.values())
    return report


def evaluateDesignSavings(yosysStat, acceptedPatterns, libAreas,
                          complexAreas):
    """Design-level area savings in the library's own area units.

    ``yosysStat``: ``runYosysStat`` output (its histogram is an
    independent parser's count of the mapped design -- our baseline).
    ``acceptedPatterns``: [(name, occurrences, [member type names])] --
    e.g. from a bestRecord file.
    ``libAreas``: {type: area} from the liberty ``area`` attribute.
    ``complexAreas``: {name: area} = layout width x row height.

    Returns baseline area, total/relative savings and a per-pattern
    table.  This is the flow's own savings formula expressed in
    lib-area units rather than layout widths.
    """
    report = {"compared": False}
    if (not yosysStat.get("ok")):
        report["reason"] = yosysStat.get("reason", "unavailable")
        return report
    hist = yosysStat.get("histogram") or {}
    missing = sorted(t for t in hist if t not in libAreas)
    baseline = sum(libAreas[t] * n for t, n in hist.items()
                   if t in libAreas)
    rows = []
    totalSaved = 0.0
    for name, occurrences, memberTypes in acceptedPatterns:
        if (any(t not in libAreas for t in memberTypes)
                or name not in complexAreas):
            rows.append({"name": name, "skipped": "missing area data"})
            continue
        membersArea = sum(libAreas[t] for t in memberTypes)
        saved = occurrences * (membersArea - complexAreas[name])
        rows.append({
            "name": name,
            "occurrences": occurrences,
            "member_area": round(membersArea, 4),
            "complex_area": round(complexAreas[name], 4),
            "saved_area": round(saved, 4),
        })
        totalSaved += saved
    report.update({
        "compared": True,
        "baseline_area": baseline,
        "baseline_cells": sum(hist.values()),
        "missing_area_types": missing,
        "saved_area": round(totalSaved, 4),
        "saved_pct": (totalSaved / baseline * 100.0) if baseline else None,
        "patterns": rows,
    })
    return report
