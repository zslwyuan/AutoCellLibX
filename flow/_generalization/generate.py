"""Generate the hold-out .sp decks from the committed .v modules.

The hold-out set for the generalization evaluation
(bigcell_engine.benchmark.run_generalization) is COMMITTED: the Verilog
sources (``*.v``) and their synthesized transistor decks (``*.sp``) live
side by side in this directory.  This driver is the reproducible bridge
between them -- it runs the verilog2cells synthesis/flatten steps per
module:

    <module>.v --(yosys synth + abc -liberty gscl45nm)--> mapped gates
             --(logic_verify: gold vs mapped, exhaustive)--> proof
             --(gate_flatten: ONE block, budget >> module size)--> .sp

Each module becomes exactly ONE cell (the partition budget is far above
any module's transistor count), named after the module, with the
flatten port order the pipeline always emits (VCC, inputs, outputs,
GND).  Everything is deterministic: fixed yosys steps, fixed liberty,
sorted file order, no timestamps -- regenerating must reproduce the
committed decks byte-for-byte (``--check`` asserts exactly that).

Usage (repo root or flow/):
    python flow/_generalization/generate.py            # regenerate + check
    python flow/_generalization/generate.py --write    # overwrite decks
    python flow/_generalization/generate.py --json     # machine-readable
"""

import argparse
import glob
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_FLOW = os.path.dirname(_HERE)
if (_FLOW not in sys.path):
    sys.path.insert(0, _FLOW)

import gate_flatten as gf                                     # noqa: E402
import logic_verify as lv                                     # noqa: E402
from verilog2cells import (DEFAULT_CELLS_SP, DEFAULT_LIB,      # noqa: E402
                           run_synthesis)

#: one cell per module: the budget only needs to exceed every module's
#: transistor count (the largest hold-out module is far below this)
PARTITION_BUDGET_T = 200


def _module_stem(v_path):
    return os.path.splitext(os.path.basename(v_path))[0]


def _rename_block(text, cell_name):
    """BLK0 -> <module> in the .subckt/.ends lines (device lines never
    carry the block name; a plain string replace would still be safe,
    but rewriting the two structural lines is explicit)."""
    lines = text.splitlines()
    assert lines[0].startswith(".subckt BLK0 "), lines[0]
    assert lines[-1] == ".ends BLK0", lines[-1]
    lines[0] = lines[0].replace(".subckt BLK0 ", ".subckt %s " % cell_name,
                                1)
    lines[-1] = ".ends %s" % cell_name
    return "\n".join(lines) + "\n"


def synthesize_holdout_module(v_path, work_dir):
    """One .v -> (deck_text, transistor_count, cell_histogram).

    Runs the same synthesis + equivalence + flatten steps as
    verilog2cells (run_synthesis, logic_verify.verify, gate_flatten),
    with a partition budget that keeps the whole module as ONE block.
    Raises RuntimeError on any honest failure (unknown mapped cell,
    multi-block partition, equivalence mismatch) -- a broken deck must
    never enter the hold-out set.
    """
    stem = _module_stem(v_path)
    art, stat = run_synthesis(v_path, None, DEFAULT_LIB, work_dir)
    cell_hist = stat["histogram"]
    if (not cell_hist):
        raise RuntimeError("%s: yosys stat reports no mapped cells" % stem)

    lib_funcs = lv.parse_liberty_functions(
        open(DEFAULT_LIB, errors="replace").read())
    verify = lv.verify(art["gold_blif"], art["gate_blif"], lib_funcs)
    if (not verify.ok):
        raise RuntimeError("%s: equivalence failed (%s)"
                           % (stem, verify))

    lib_sp = gf.parse_library_spice(DEFAULT_CELLS_SP)
    mapped_text = open(art["mapped_v"]).read()
    insts = gf.parse_mapped_verilog(mapped_text, known_cells=set(lib_sp))
    if (not insts):
        raise RuntimeError("%s: no known-library instances in the mapped "
                           "netlist (unmappable cells: %s)"
                           % (stem, sorted(cell_hist)))
    module_inputs, module_outputs = gf.parse_module_ports(mapped_text)
    blocks = gf.partition_instances(insts, lib_sp,
                                    max_transistors=PARTITION_BUDGET_T)
    if (len(blocks) != 1):
        raise RuntimeError("%s: partition produced %d blocks (expected "
                           "exactly one cell per module -- is the module "
                           "over %d transistors?)"
                           % (stem, len(blocks), PARTITION_BUDGET_T))
    flat = gf.flatten_blocks(blocks, insts, lib_sp, module_inputs,
                             module_outputs, name_prefix="BLK")
    text, n_trans = flat["BLK0"]
    return _rename_block(text, stem), n_trans, cell_hist


def generate(work_dir, verilog_paths=None):
    """{(module stem): {"spice", "transistors", "cells"}} in sorted
    module order -- the complete regeneration of the hold-out decks."""
    if (verilog_paths is None):
        verilog_paths = sorted(glob.glob(os.path.join(_HERE, "*.v")))
    if (not verilog_paths):
        raise RuntimeError("no hold-out .v modules under %s" % _HERE)
    out = {}
    for v_path in verilog_paths:
        stem = _module_stem(v_path)
        mod_work = os.path.join(work_dir, stem)
        os.makedirs(mod_work, exist_ok=True)
        text, n_trans, hist = synthesize_holdout_module(v_path, mod_work)
        out[stem] = {"spice": text, "transistors": n_trans,
                     "cells": dict(sorted(hist.items()))}
    return out


def _committed_decks():
    """{(stem): committed deck text} for every *.sp in this directory."""
    decks = {}
    for path in sorted(glob.glob(os.path.join(_HERE, "*.sp"))):
        with open(path, "r", newline="") as fh:
            decks[_module_stem(path)] = fh.read()
    return decks


def check_against_committed(generated):
    """(ok, rows): per-module byte comparison of the regenerated decks
    against the committed ones (a module without a committed deck, or a
    committed deck without a module, is a mismatch)."""
    committed = _committed_decks()
    rows = []
    ok = True
    for stem in sorted(set(committed) | set(generated)):
        gen = generated.get(stem, {}).get("spice")
        com = committed.get(stem)
        match = (gen is not None and com is not None and gen == com)
        ok = ok and match
        rows.append({"module": stem, "match": match,
                     "transistors": generated.get(stem, {}).get(
                         "transistors")})
    return ok, rows


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Generate/check the hold-out .sp decks")
    ap.add_argument("--write", action="store_true",
                    help="write the regenerated decks next to the .v "
                         "files (content-only; default just checks)")
    ap.add_argument("--json", action="store_true",
                    help="emit the per-module table as JSON")
    args = ap.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="holdout_gen_") as work_dir:
        generated = generate(work_dir)
    ok, rows = check_against_committed(generated)
    for stem in sorted(generated):
        info = generated[stem]
        row = next(r for r in rows if r["module"] == stem)
        print("%-12s %3d T  %-6s cells: %s"
              % (stem, info["transistors"],
                 "match" if row["match"] else "DIFFERS",
                 ",".join("%sx%d" % kv for kv in info["cells"].items())))
    if (args.write):
        for stem in sorted(generated):
            path = os.path.join(_HERE, stem + ".sp")
            with open(path, "w", newline="") as fh:
                fh.write(generated[stem]["spice"])
        print("wrote %d deck(s) to %s" % (len(generated), _HERE))
    elif (not ok):
        missing = [r["module"] for r in rows if not r["match"]]
        print("MISMATCH: %s (run with --write to refresh)" % missing)
        return 1
    if (args.json):
        print(json.dumps({"ok": ok, "modules": rows,
                          "budget_t": PARTITION_BUDGET_T}, sort_keys=True))
    return 0 if ok else 1


if (__name__ == "__main__"):
    sys.exit(main())
