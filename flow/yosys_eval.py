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

from yosys_import import find_yosys, parse_stat_json


def build_extended_liberty(base_lib_text, fragment_texts):
    """Merge `cell (...) {...}` fragments into a base library text.

    The library's closing brace is found by brace-depth scan (not
    ``rfind("}")``): gscl45nm.lib ends with a stray trailing ``}``
    after the library block, and inserting before it would drop the
    fragments outside the library.
    """
    depth = 0
    library_close = -1
    for i, ch in enumerate(base_lib_text):
        if (ch == "{"):
            depth += 1
        elif (ch == "}"):
            if (depth == 1):
                library_close = i          # last 1->0 transition wins
            depth -= 1
    if (library_close < 0):
        raise ValueError("base liberty text has no top-level closing brace")
    merged = (base_lib_text[:library_close]
              + "\n  /* --- generated complex cells --- */\n"
              + "\n".join(fragment_texts) + "\n"
              + base_lib_text[library_close:])
    return merged


def run_yosys_mapped_area(lib_path, blif_path, yosys_exe=None, timeout=900):
    """abc -liberty remap + stat; returns the parsed stat dict (ok=...)."""
    exe = yosys_exe or find_yosys()
    if (exe is None):
        return {"ok": False,
                "reason": "no yosys executable found"}
    script = ("read_liberty -lib %s; read_blif %s; abc -liberty %s; "
              "stat -json" % (lib_path, blif_path, lib_path))
    try:
        proc = subprocess.run(
            [exe, "-Q", "-T", "-p", script],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": "yosys launch failed: %s" % exc}
    try:
        result = parse_stat_json(proc.stdout or "")
    except Exception as exc:                       # noqa: BLE001
        return {"ok": False,
                "reason": "no JSON in yosys output (rc=%d): %s | %s"
                % (proc.returncode, (proc.stdout or "")[-200:],
                   (proc.stderr or "")[-200:])}
    result["ok"] = True
    return result


def compare_mapped_area(baseline_stat, extended_stat):
    """Area + complex-cell usage comparison of two mapped stats."""
    report = {"compared": False}
    if (not (baseline_stat.get("ok") and extended_stat.get("ok"))):
        report["reason"] = "baseline: %s | extended: %s" % (
            baseline_stat.get("reason", "?"),
            extended_stat.get("reason", "?"))
        return report
    report["compared"] = True
    report["baseline_area"] = baseline_stat.get("area")
    report["extended_area"] = extended_stat.get("area")
    b, e = baseline_stat.get("area"), extended_stat.get("area")
    if (b and e):
        report["area_saved"] = b - e
        report["area_saved_pct"] = (b - e) / b * 100.0
    complex_hist = {t: n for t, n in
                   extended_stat.get("histogram", {}).items()
                   if re.match(r"COMPLEX", t)}
    report["complex_cells_used"] = complex_hist
    report["complex_instances"] = sum(complex_hist.values())
    return report


def evaluate_design_savings(yosys_stat, accepted_patterns, lib_areas,
                          complex_areas):
    """Design-level area savings in the library's own area units.

    ``yosys_stat``: ``run_yosys_stat`` output (its histogram is an
    independent parser's count of the mapped design -- our baseline).
    ``accepted_patterns``: [(name, occurrences, [member type names])] --
    e.g. from a bestRecord file.
    ``lib_areas``: {type: area} from the liberty ``area`` attribute.
    ``complex_areas``: {name: area} = layout width x row height.

    Returns baseline area, total/relative savings and a per-pattern
    table.  This is the flow's own savings formula expressed in
    lib-area units rather than layout widths.
    """
    report = {"compared": False}
    if (not yosys_stat.get("ok")):
        report["reason"] = yosys_stat.get("reason", "unavailable")
        return report
    hist = yosys_stat.get("histogram") or {}
    missing = sorted(t for t in hist if t not in lib_areas)
    baseline = sum(lib_areas[t] * n for t, n in hist.items()
                   if t in lib_areas)
    rows = []
    total_saved = 0.0
    for name, occurrences, member_types in accepted_patterns:
        if (any(t not in lib_areas for t in member_types)
                or name not in complex_areas):
            rows.append({"name": name, "skipped": "missing area data"})
            continue
        members_area = sum(lib_areas[t] for t in member_types)
        saved = occurrences * (members_area - complex_areas[name])
        rows.append({
            "name": name,
            "occurrences": occurrences,
            "member_area": round(members_area, 4),
            "complex_area": round(complex_areas[name], 4),
            "saved_area": round(saved, 4),
        })
        total_saved += saved
    report.update({
        "compared": True,
        "baseline_area": baseline,
        "baseline_cells": sum(hist.values()),
        "missing_area_types": missing,
        "saved_area": round(total_saved, 4),
        "saved_pct": (total_saved / baseline * 100.0) if baseline else None,
        "patterns": rows,
    })
    return report
