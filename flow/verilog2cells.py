"""One-command flow: a Verilog module -> custom complex cells via ASTRAN.

Wraps the steps that used to be done by hand:

    verilog --(yosys synth + abc -liberty)--> mapped gates
            --(logic_verify: gold vs mapped, exhaustive/random)--> proof
            --(gate_flatten: partition under a transistor budget)--> .sp
            --(astran_lint: preflight)--> reject bad decks in ms
            --(astran_queue: resumable, parallel-safe)--> .gds + widths
            --> report.md (+ layout PNGs)

Usage:
    python verilog2cells.py module.v [--top NAME] [--out DIR]
        [--max-transistors 36] [--jobs N] [--resume]
        [--skip-verify] [--skip-astran] [--no-png]

Defaults follow the repo conventions: gscl45nm liberty, the
ASTRAN-friendly transistor library, row height 13*0.19 = 2.47 um.
The output directory is created where you point it -- for sensitive
work point it somewhere git-ignored (see .gitignore's _private*/ rule).
"""

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_REPO = os.path.normpath(os.path.join(os.path.dirname(
    os.path.abspath(__file__)), ".."))

from astran import ASTRAN_CELLS_HEIGHT, ASTRAN_VGRID          # noqa: E402
from astran_queue import run_queue                            # noqa: E402
import gate_flatten as gf                                     # noqa: E402
import logic_verify as lv                                     # noqa: E402
from yosys_import import find_yosys, parse_stat_json         # noqa: E402

DEFAULT_LIB = os.path.join(_REPO, "std_celllib", "gscl45nm.lib")
DEFAULT_CELLS_SP = os.path.join(_REPO, "std_celllib",
                                "cellsAstranFriendly.sp")
ROW_HEIGHT = ASTRAN_CELLS_HEIGHT * ASTRAN_VGRID               # 2.47 um


def parse_liberty_areas(lib_path):
    """{cell: area_um2} -- the width proxy denominator lives in the lib."""
    text = open(lib_path, "r", errors="replace").read()
    areas = {}
    for m in lv.re.finditer(r"cell \((\w+)\)\s*\{", text):
        end = lv._brace_block(text, text.index("{", m.start()))
        body = text[m.start():end]
        am = lv.re.search(r"area\s*:\s*([\d.]+)", body)
        if am:
            areas[m.group(1)] = float(am.group(1))
    return areas


def run_synthesis(verilog_path, top, lib_path, outdir):
    """yosys synth + abc map; returns (artefact paths, stat dict)."""
    yosys = find_yosys()
    if yosys is None:
        raise RuntimeError(
            "no yosys executable found (expected the vendored one at "
            "tools/yosys/mingw64/bin/yosys.exe)")
    paths = {
        "gold_blif": os.path.join(outdir, "gold.blif"),
        "gate_blif": os.path.join(outdir, "gates.blif"),
        "mapped_v": os.path.join(outdir, "mapped.v"),
        "log": os.path.join(outdir, "yosys.log"),
    }
    steps = ["read_verilog %s" % verilog_path]
    if top:
        steps.append("synth -top %s" % top)
    else:
        steps.append("hierarchy -auto-top")
        steps.append("synth")
    steps += [
        "write_blif %s" % paths["gold_blif"],
        "abc -liberty %s" % lib_path,
        "opt_clean",
        "write_verilog -noattr %s" % paths["mapped_v"],
        "write_blif -gates %s" % paths["gate_blif"],
        "stat -json",
    ]
    proc = subprocess.run([yosys, "-Q", "-T", "-p", "; ".join(steps)],
                          capture_output=True, text=True, timeout=1800)
    with open(paths["log"], "w") as log:
        log.write(proc.stdout or "")
        log.write(proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError("yosys failed (rc=%d), see %s"
                           % (proc.returncode, paths["log"]))
    stat = parse_stat_json(proc.stdout or "")
    return paths, stat


def render_pngs(outdir, cell_names):
    """Best-effort layout renders via the repo's Qt-free GDS reader."""
    sys.path.insert(0, _REPO)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPolygon
    from gui.gds_model import load_layout

    png_dir = os.path.join(outdir, "png")
    os.makedirs(png_dir, exist_ok=True)
    written = []
    for name in cell_names:
        gds = os.path.join(outdir, name + ".gds")
        log = os.path.join(outdir, name + ".Astranlog")
        if not os.path.exists(gds):
            continue
        model = load_layout(gds, log_path=log)
        fig, ax = plt.subplots(figsize=(max(4.0, model.width_um * 1.1), 3.4),
                               dpi=200)
        for layer in model.ordered_layers():
            for poly in layer.polygons:
                ax.add_patch(MplPolygon(poly, closed=True,
                                        facecolor=layer.colour,
                                        edgecolor="none", alpha=0.85, lw=0))
        x0, y0, x1, y1 = model.full_bbox
        ax.set_xlim(x0 - 0.05, x1 + 0.05)
        ax.set_ylim(y0 - 0.05, y1 + 0.05)
        ax.set_aspect("equal")
        ax.set_title("%s -- %.2f x %.2f um" % (name, model.width_um,
                                               model.height_um), fontsize=9)
        fig.tight_layout()
        path = os.path.join(png_dir, name + ".png")
        fig.savefig(path)
        plt.close(fig)
        written.append(path)
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("verilog", help="input Verilog module file")
    parser.add_argument("--top", default=None, help="top module name "
                        "(default: yosys hierarchy -auto-top)")
    parser.add_argument("--lib", default=DEFAULT_LIB,
                        help="liberty file for mapping and the area baseline")
    parser.add_argument("--cells-spice", default=DEFAULT_CELLS_SP,
                        help="transistor-level cell library for flattening")
    parser.add_argument("--out", default=None,
                        help="output directory (default: <verilog>_cells; "
                             "keep sensitive work under a git-ignored path)")
    parser.add_argument("--max-transistors", type=int, default=36,
                        help="transistor budget per merged block")
    parser.add_argument("--jobs", type=int, default=1,
                        help="parallel ASTRAN workers")
    parser.add_argument("--resume", action="store_true",
                        help="skip cells whose .sp is unchanged")
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--skip-astran", action="store_true")
    parser.add_argument("--no-png", action="store_true")
    args = parser.parse_args(argv)

    stem = os.path.splitext(os.path.basename(args.verilog))[0]
    outdir = os.path.abspath(args.out or (stem + "_cells"))
    os.makedirs(outdir, exist_ok=True)
    t_start = time.time()
    log_lines = []

    def note(msg):
        print("[v2c] " + msg, flush=True)
        log_lines.append("[v2c] " + msg)

    # ---- 1. synthesis ----------------------------------------------------
    note("synthesising with yosys+abc ...")
    art, stat = run_synthesis(args.verilog, args.top, args.lib, outdir)
    cell_hist = stat["histogram"]
    if not cell_hist:
        raise RuntimeError("yosys stat reports no mapped cells -- see "
                           + art["log"])
    areas = parse_liberty_areas(args.lib)
    missing_area = [c for c in cell_hist if c not in areas]
    if missing_area:
        raise RuntimeError("mapped cells missing area in liberty: %s"
                           % missing_area)
    baseline_area = sum(areas[c] * n for c, n in cell_hist.items())
    baseline_width = baseline_area / ROW_HEIGHT
    note("mapped: %d cells (%s), discrete baseline %.4f um^2 -> %.2f um"
         % (sum(cell_hist.values()),
            ", ".join("%sx%d" % (c, n) for c, n in
                      sorted(cell_hist.items())),
            baseline_area, baseline_width))

    # ---- 2. equivalence --------------------------------------------------
    if args.skip_verify:
        verify_report = None
        note("equivalence check skipped (--skip-verify)")
    else:
        note("verifying gold vs mapped (this is exhaustive for small "
             "input counts) ...")
        lib_funcs = lv.parse_liberty_functions(
            open(args.lib, errors="replace").read())
        verify_report = lv.verify(art["gold_blif"], art["gate_blif"],
                                  lib_funcs)
        note(str(verify_report))
        if not verify_report.ok:
            note("MISMATCH examples:")
            for vector, g, m in verify_report.mismatches:
                note("  in=%s gold=%s mapped=%s" % (vector, g, m))
            raise SystemExit("equivalence failed -- aborting before any "
                             "layout work")

    # ---- 3. partition + flatten ------------------------------------------
    lib_sp = gf.parse_library_spice(args.cells_spice)
    mapped_text = open(art["mapped_v"]).read()
    known = set(lib_sp)
    insts = gf.parse_mapped_verilog(mapped_text, known_cells=known)
    unsupported = sorted({c for c in cell_hist if c not in known})
    if unsupported:
        raise RuntimeError(
            "mapped netlist uses cells with no transistor-level model in "
            "%s: %s" % (args.cells_spice, unsupported))
    module_inputs, module_outputs = gf.parse_module_ports(mapped_text)
    blocks = gf.partition_instances(insts, lib_sp,
                                    max_transistors=args.max_transistors)
    flat = gf.flatten_blocks(blocks, insts, lib_sp, module_inputs,
                             module_outputs)
    block_members = {name: members
                     for name, members in zip(flat, blocks)}
    for name, (text, n_trans) in flat.items():
        with open(os.path.join(outdir, name + ".sp"), "w") as fh:
            fh.write(text)
    note("partitioned into %d block(s): %s"
         % (len(flat), ", ".join("%s=%dT" % (n, t)
                                 for n, (_, t) in flat.items())))

    # ---- 4/5. layout -------------------------------------------------------
    results = []
    if args.skip_astran:
        note("layout skipped (--skip-astran)")
    else:
        note("running ASTRAN queue (jobs=%d) ..." % args.jobs)
        results = run_queue(sorted(flat), outdir, jobs=args.jobs,
                            resume=args.resume)
        for r in results:
            note("%s: %s" % (r.name,
                             ("width %.2f um (%.0fs)" % (r.width, r.seconds))
                             if r.ok else "FAILED: " + r.note))

    # ---- 6. report ---------------------------------------------------------
    counts = gf.library_transistor_counts(lib_sp)
    discrete_by_block = {}
    for name in flat:
        members = block_members[name]
        area = 0.0
        for m in members:
            inst = next(i for i in insts if i.name == m)
            area += areas[inst.cell_type]
        discrete_by_block[name] = area / ROW_HEIGHT

    width_by_block = {r.name: r.width for r in results if r.ok}
    custom_total = sum(width_by_block.values())
    discrete_total = sum(discrete_by_block.values())

    pngs = []
    if results and not args.no_png:
        try:
            pngs = render_pngs(outdir, sorted(width_by_block))
        except Exception as exc:                            # noqa: BLE001
            note("PNG rendering skipped: %s" % exc)

    report_path = os.path.join(outdir, "report.md")
    with open(report_path, "w") as fh:
        fh.write("# verilog2cells report: %s\n\n" % stem)
        fh.write("- input: `%s`\n- liberty: `%s`\n- row height: %.2f um\n"
                 % (os.path.abspath(args.verilog),
                    os.path.abspath(args.lib), ROW_HEIGHT))
        if verify_report is not None:
            fh.write("- equivalence: %s\n" % verify_report)
        fh.write("\n## Baseline (discrete mapped gates)\n\n")
        fh.write("%d cells (%s), area %.4f um^2 -> width **%.2f um**\n\n"
                 % (sum(cell_hist.values()),
                    ", ".join("%sx%d" % kv for kv in
                              sorted(cell_hist.items())),
                    baseline_area, baseline_width))
        fh.write("## Blocks\n\n")
        fh.write("| block | members | T | discrete um | custom um | "
                 "saving | layout |\n|---|---|---|---|---|---|\n")
        for name in sorted(flat):
            members = block_members[name]
            member_types = sorted({next(i for i in insts if i.name == m)
                                   .cell_type for m in members})
            custom = width_by_block.get(name)
            disc = discrete_by_block[name]
            saving = ("%.1f%%" % ((disc - custom) / disc * 100)
                      if custom else "--")
            png = ("[png](png/%s.png)" % name if any(
                p.endswith(name + ".png") for p in pngs) else "")
            fh.write("| %s | %dx (%s) | %d | %.2f | %s | %s | %s |\n"
                     % (name, len(members), "+".join(member_types),
                        flat[name][1], disc,
                        ("%.2f" % custom) if custom else "--", saving, png))
        fh.write("| **total** | %d | %d | **%.2f** | **%s** | %s | |\n"
                 % (len(insts), sum(t for _, t in flat.values()),
                    discrete_total,
                    ("%.2f" % custom_total) if custom_total else "--",
                    ("%.1f%%" % ((discrete_total - custom_total)
                                 / discrete_total * 100))
                    if custom_total else "--"))
        fh.write("\n_Generated by verilog2cells.py in %.0fs._\n"
                 % (time.time() - t_start))
    note("report: %s" % report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
