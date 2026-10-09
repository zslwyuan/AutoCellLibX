"""Dual-mode comparison experiment (AUDIT 5.26/5.27).

Physical mode  : current mining -- multi-output, area-maximal cells
                  (outputs/<bench>/); abc never uses them (cone mismatch).
Reuse mode     : AUTOCELL_REUSE_MODE=1 -- single-output, simple-function
                  cells via the internalize_only growth bias; abc CAN use
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

from blif_preproc import (gen_graph_from_liberty_and_blif,
                         heuristic_label_initial_clusters)
from blif_graph_util import sort_pattern_cluster_seqs
from electrical import load_cell_electrical_metrics
from liberty_gen import load_liberty_functions, generate_complex_liberty
from reuse import reuse_eligible, verilog_design_for_function
from timing_power import load_timing_power
from yosys_eval import build_extended_liberty
from yosys_import import find_yosys

LIB = "../std_celllib/gscl45nm.lib"


def main():
    bench = sys.argv[1] if len(sys.argv) > 1 else "adder"
    run_layout = os.environ.get("AUTOCELL_RUN_LAYOUT", "0") == "1"

    G, cells, netlist, types = gen_graph_from_liberty_and_blif(
        LIB, "../benchmark/blif/" + bench + ".blif")
    em = load_cell_electrical_metrics(LIB)
    tp = load_timing_power(LIB)
    funcs = load_liberty_functions(LIB)
    lib_areas = {t: m["area"] for t, m in em.items() if m["area"]}

    seqs, _ = heuristic_label_initial_clusters(
        G, cells, netlist, single_output_seeds=True)
    seqs = sort_pattern_cluster_seqs(seqs)

    eligible = []
    for seq in seqs[:30]:
        members = seq.pattern_clusters[0].cells
        r = reuse_eligible(members, funcs)
        if (not r["eligible"]):
            continue
        trace = seq.pattern_clusters[0].pattern_extension_trace
        occ = len(seq.pattern_clusters)
        member_area = sum(lib_areas.get(c.std_cell_type.type_name, 0)
                         for c in members)
        func = list(r["functions"].values())[0]
        eligible.append({
            "trace": trace, "occurrences": occ,
            "member_area": member_area,
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
    out_dir = "./outputs/" + bench + "_reuse"
    os.makedirs(out_dir, exist_ok=True)

    if (run_layout):
        from astran import (ASTRAN_BUILD_PATH, ASTRAN_TECHNOLOGY, GUROBI_CL,
                            run_astran_for_netlist, load_astran_area)
        # find the seed seq again and export its .sp (the flow's export)
        from spice import export_spice_netlist, load_spice_subcircuits
        subckts = load_spice_subcircuits("../std_celllib/cellsAstranFriendly.sp")
        seed = None
        for seq in sort_pattern_cluster_seqs(seqs):
            if (seq.pattern_clusters[0].pattern_extension_trace
                    == top["trace"].split("+")[0]):
                seed = seq
                break
        if (seed is None):
            print("seed seq not found for %s" % top["trace"])
            return
        complex_name = "COMPLEX_REUSE"
        export_spice_netlist(seed, subckts, "REUSE", out_dir)  # -> COMPLEXREUSE.sp? id unused
        sp_path = out_dir + "/COMPLEXREUSE.sp"
        # export_spice_netlist writes COMPLEX<id>.sp; id="REUSE" -> COMPLEXREUSE.sp
        run_astran_for_netlist(astran_path=ASTRAN_BUILD_PATH,
                            gurobi_path=GUROBI_CL,
                            technology_path=ASTRAN_TECHNOLOGY,
                            spice_netlist_path=sp_path,
                            complex_name=complex_name, command_dir=out_dir)
        width = load_astran_area(out_dir, complex_name)
        print("reuse cell layout width: %.2f um" % width)
        # rebuild the cluster and characterise
        members = [c for c in cells if c.name in
                   [l.split()[1] for l in open(sp_path).read().split("\n")
                    if l.startswith("*   .subckt")]]
        from blif_graph_util import DesignPatternCluster, \
            DesignPatternClusterSeq
        cluster = DesignPatternCluster(
            0, top["trace"], cells, [c.id for c in members], 0)
        seq2 = DesignPatternClusterSeq(top["trace"])
        seq2.add_cluster(cluster)
        frag, _rep = generate_complex_liberty(
            seq2, complex_name, width, tp, em, funcs)
        open(out_dir + "/" + complex_name + ".lib", "w").write(frag)
        print("characterisation written to %s/%s.lib"
              % (out_dir, complex_name))
    else:
        print("(layout run disabled; set AUTOCELL_RUN_LAYOUT=1 to lay out "
              "the top pattern)")

    # abc proof on a design matching the top pattern's function
    exe = find_yosys()
    if (exe is None):
        print("no yosys; skipping the abc proof")
        return
    v_text = verilog_design_for_function(top["function"])
    if (v_text is None):
        print("function not translatable; skipping the abc proof")
        return
    base = open(LIB).read()
    frag = None
    if (os.path.exists(out_dir + "/COMPLEX_REUSE.lib")):
        frag = open(out_dir + "/COMPLEX_REUSE.lib").read()
    else:
        # minimal fragment with the composed function and dummy area:
        # pins must carry the SAME (mapped) names the function and the
        # verification design use, or abc sees a function over pins it
        # does not have and never uses the cell.
        import re as _re
        letter_map, used = {}, set()
        for name in _re.findall(r"[A-Za-z0-9_]+", top["function"]):
            if (name not in used):
                used.add(name)
                letter_map[name] = "abcdefghijklmnop"[len(letter_map)]
        liberty_func = top["function"]
        for src, dst in sorted(letter_map.items(),
                               key=lambda kv: -len(kv[0])):
            liberty_func = _re.sub(
                r"(?<![A-Za-z0-9_])" + _re.escape(src) +
                r"(?![A-Za-z0-9_])", dst, liberty_func)
        frag = ("  cell (COMPLEX_REUSE) {\n"
                "    area : %.4f;\n"
                "    cell_leakage_power : 1.0;\n" % (top["member_area"] * 0.9))
        for name in sorted(letter_map.values()):
            frag += ("    pin (%s) { direction : input; "
                     "capacitance : 0.002; }\n" % name)
        frag += ("    pin (Y) {\n      direction : output;\n"
                 "      function : \"%s\";\n" % liberty_func)
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
    ext = build_extended_liberty(base, [frag])
    with tempfile.NamedTemporaryFile("w", suffix=".lib",
                                     delete=False) as f:
        f.write(ext)
        lib_path = f.name
    with tempfile.NamedTemporaryFile("w", suffix=".v",
                                     delete=False) as f:
        f.write(v_text)
        v_path = f.name
    env = dict(os.environ)
    env["TEMP"] = env.get("TEMP", "").replace("\\", "/")
    env["TMP"] = env.get("TMP", "").replace("\\", "/")
    try:
        proc = subprocess.run(
            [exe, "-Q", "-T",
             "-p", ("read_liberty -lib %s; read -sv %s; synth -top top; "
                    "abc -liberty %s; stat -json" % (lib_path, v_path,
                                                     lib_path))],
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
        os.unlink(lib_path)
        os.unlink(v_path)


if __name__ == "__main__":
    main()
