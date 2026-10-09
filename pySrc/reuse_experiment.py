"""Dual-mode comparison experiment (AUDIT 5.26/5.27).

Physical mode  : current mining -- multi-output, area-maximal cells
                  (outputs/<bench>/); abc never uses them (cone mismatch).
Reuse mode     : AUTOCELL_REUSE_MODE=1 -- single-output, simple-function
                  cells via the internalizeOnly growth bias; abc CAN use
                  them (proven e2e in tests).

This script runs the reuse-mode MINING only (no ASTRAN unless
AUTOCELL_RUN_LAYOUT=1) and prints the eligible patterns with their
functions, frequencies and member-area sums, then -- with layouts
enabled -- picks the top pattern, lays it out, characterises it and
re-runs the abc proof on a generated matching design.

    python reuse_experiment.py [benchmark]
"""

import glob
import json
import os
import subprocess
import sys
import tempfile

from BLIFPreProc import (genGraphFromLibertyAndBLIF,
                         heuristicLabelSomeNodesAndGetInitialClusters)
from BLIFGraphUtil import sortPatternClusterSeqs
from electrical import loadCellElectricalMetrics
from liberty_gen import loadLibertyFunctions, generateComplexLiberty
from reuse import reuseEligible, verilogDesignForFunction
from timing_power import loadTimingPower
from yosys_eval import buildExtendedLiberty
from yosys_import import findYosys

LIB = "../stdCelllib/gscl45nm.lib"


def main():
    bench = sys.argv[1] if len(sys.argv) > 1 else "adder"
    runLayout = os.environ.get("AUTOCELL_RUN_LAYOUT", "0") == "1"

    G, cells, netlist, types = genGraphFromLibertyAndBLIF(
        LIB, "../benchmark/blif/" + bench + ".blif")
    em = loadCellElectricalMetrics(LIB)
    tp = loadTimingPower(LIB)
    funcs = loadLibertyFunctions(LIB)
    libAreas = {t: m["area"] for t, m in em.items() if m["area"]}

    seqs, _ = heuristicLabelSomeNodesAndGetInitialClusters(
        G, cells, netlist, singleOutputSeeds=True)
    seqs = sortPatternClusterSeqs(seqs)

    eligible = []
    for seq in seqs[:30]:
        members = seq.patternClusters[0].cellsContained
        r = reuseEligible(members, funcs)
        if (not r["eligible"]):
            continue
        trace = seq.patternClusters[0].patternExtensionTrace
        occ = len(seq.patternClusters)
        memberArea = sum(libAreas.get(c.stdCellType.typeName, 0)
                         for c in members)
        func = list(r["functions"].values())[0]
        eligible.append({
            "trace": trace, "occurrences": occ,
            "member_area": memberArea,
            "function": func,
            "n_cells": len(members),
        })

    eligible.sort(key=lambda e: -e["occurrences"])
    print("== reuse-mode eligible patterns on %s ==" % bench)
    for e in eligible[:10]:
        print("  x%-4d area=%.2f cells=%d  %s" % (
            e["occurrences"], e["member_area"], e["n_cells"], e["trace"]))
        print("         function: %s" % e["function"][:90])

    if (not eligible):
        print("no reuse-eligible pattern; nothing to lay out")
        return

    top = eligible[0]
    outDir = "./outputs/" + bench + "_reuse"
    os.makedirs(outDir, exist_ok=True)

    if (runLayout):
        from Astran import (ASTRAN_BUILD_PATH, ASTRAN_TECHNOLOGY, GUROBI_CL,
                            runAstranForNetlist, loadAstranArea)
        # find the seed seq again and export its .sp (the flow's export)
        from spice import exportSpiceNetlist, loadSpiceSubcircuits
        subckts = loadSpiceSubcircuits("../stdCelllib/cellsAstranFriendly.sp")
        seed = None
        for seq in sortPatternClusterSeqs(seqs):
            if (seq.patternClusters[0].patternExtensionTrace
                    == top["trace"].split("+")[0]):
                seed = seq
                break
        if (seed is None):
            print("seed seq not found for %s" % top["trace"])
            return
        complexName = "COMPLEX_REUSE"
        exportSpiceNetlist(seed, subckts, "REUSE", outDir)  # -> COMPLEXREUSE.sp? id unused
        spPath = outDir + "/COMPLEXREUSE.sp"
        # exportSpiceNetlist writes COMPLEX<id>.sp; id="REUSE" -> COMPLEXREUSE.sp
        runAstranForNetlist(AstranPath=ASTRAN_BUILD_PATH,
                            gurobiPath=GUROBI_CL,
                            technologyPath=ASTRAN_TECHNOLOGY,
                            spiceNetlistPath=spPath,
                            complexName=complexName, commandDir=outDir)
        width = loadAstranArea(outDir, complexName)
        print("reuse cell layout width: %.2f um" % width)
        # rebuild the cluster and characterise
        members = [c for c in cells if c.name in
                   [l.split()[1] for l in open(spPath).read().split("\n")
                    if l.startswith("*   .subckt")]]
        from BLIFGraphUtil import DesignPatternCluster, \
            DesignPatternClusterSeq
        cluster = DesignPatternCluster(
            0, top["trace"], cells, [c.id for c in members], 0)
        seq2 = DesignPatternClusterSeq(top["trace"])
        seq2.addCluster(cluster)
        frag, _rep = generateComplexLiberty(
            seq2, complexName, width, tp, em, funcs)
        open(outDir + "/" + complexName + ".lib", "w").write(frag)
        print("characterisation written to %s/%s.lib"
              % (outDir, complexName))
    else:
        print("(layout run disabled; set AUTOCELL_RUN_LAYOUT=1 to lay out "
              "the top pattern)")

    # abc proof on a design matching the top pattern's function
    exe = findYosys()
    if (exe is None):
        print("no yosys; skipping the abc proof")
        return
    vText = verilogDesignForFunction(top["function"])
    if (vText is None):
        print("function not translatable; skipping the abc proof")
        return
    base = open(LIB).read()
    frag = None
    if (os.path.exists(outDir + "/COMPLEX_REUSE.lib")):
        frag = open(outDir + "/COMPLEX_REUSE.lib").read()
    else:
        # minimal fragment with the composed function and dummy area:
        # pins must carry the SAME (mapped) names the function and the
        # verification design use, or abc sees a function over pins it
        # does not have and never uses the cell.
        import re as _re
        letterMap, used = {}, set()
        for name in _re.findall(r"[A-Za-z0-9_]+", top["function"]):
            if (name not in used):
                used.add(name)
                letterMap[name] = "abcdefghijklmnop"[len(letterMap)]
        libertyFunc = top["function"]
        for src, dst in sorted(letterMap.items(),
                               key=lambda kv: -len(kv[0])):
            libertyFunc = _re.sub(
                r"(?<![A-Za-z0-9_])" + _re.escape(src) +
                r"(?![A-Za-z0-9_])", dst, libertyFunc)
        frag = ("  cell (COMPLEX_REUSE) {\n"
                "    area : %.4f;\n"
                "    cell_leakage_power : 1.0;\n" % (top["member_area"] * 0.9))
        for name in sorted(letterMap.values()):
            frag += ("    pin (%s) { direction : input; "
                     "capacitance : 0.002; }\n" % name)
        frag += ("    pin (Y) {\n      direction : output;\n"
                 "      function : \"%s\";\n" % libertyFunc)
        frag += ("      timing() {\n        related_pin : \"P0\";\n")
        table = ("          index_1 (\"0.1, 0.5, 1.2, 3, 4, 5\");\n"
                 "          index_2 (\"0.06, 0.24, 0.48, 0.9, 1.2, 1.8\");\n"
                 "          values ( \\\n"
                 "            \"0.1, 0.1, 0.1, 0.1, 0.1, 0.1\", \\\n"
                 "            \"0.1, 0.1, 0.1, 0.1, 0.1, 0.1\", \\\n"
                 "            \"0.1, 0.1, 0.1, 0.1, 0.1, 0.1\", \\\n"
                 "            \"0.1, 0.1, 0.1, 0.1, 0.1, 0.1\", \\\n"
                 "            \"0.1, 0.1, 0.1, 0.1, 0.1, 0.1\", \\\n"
                 "            \"0.1, 0.1, 0.1, 0.1, 0.1, 0.1\");\n")
        for kind in ("cell_rise", "cell_fall", "rise_transition",
                     "fall_transition"):
            frag += ("        %s(delay_template_6x6) {\n" % kind + table +
                     "        }\n")
        frag += "      }\n    }\n  }\n"
    ext = buildExtendedLiberty(base, [frag])
    with tempfile.NamedTemporaryFile("w", suffix=".lib",
                                     delete=False) as f:
        f.write(ext)
        libPath = f.name
    with tempfile.NamedTemporaryFile("w", suffix=".v",
                                     delete=False) as f:
        f.write(vText)
        vPath = f.name
    env = dict(os.environ)
    env["TEMP"] = env.get("TEMP", "").replace("\\", "/")
    env["TMP"] = env.get("TMP", "").replace("\\", "/")
    try:
        proc = subprocess.run(
            [exe, "-Q", "-T",
             "-p", ("read_liberty -lib %s; read -sv %s; synth -top top; "
                    "abc -liberty %s; stat -json" % (libPath, vPath,
                                                     libPath))],
            capture_output=True, text=True, timeout=300, env=env)
        import re as _re, json as _json
        m = _re.search(r"\{.*\}", proc.stdout + proc.stderr, _re.S)
        if (m is None):
            print("abc proof failed:", (proc.stderr or "")[-200:])
            return
        hist = list(_json.loads(m.group(0))["modules"].values())[0][
            "num_cells_by_type"]
        used = hist.get("COMPLEX_REUSE", 0)
        print("abc proof: COMPLEX_REUSE used %d time(s) on a matching "
              "design -> %s" % (used,
                                "REUSE PATH WORKS" if used >= 1
                                else "still unused (unexpected)"))
    finally:
        os.unlink(libPath)
        os.unlink(vPath)


if __name__ == "__main__":
    main()
