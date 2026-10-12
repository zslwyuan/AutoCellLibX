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
import glob
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


def block_areas(results, fallback_height=ROW_HEIGHT):
    """{cell: area_um2} from queue results -- width x MEASURED height.

    The height comes from the same ASTRAN log line as the width, so a
    non-default geometry override (GUI / build_astran_commands) yields
    correct areas; the compiled-in constant only covers logs that lack
    the H field, it is NOT the source of truth.
    """
    out = {}
    for r in results:
        if r.ok and r.width:
            height = r.height if r.height else fallback_height
            out[r.name] = r.width * height
    return out


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


def rank_partitions(insts, lib_sp, areas, budgets, cells_spice_path):
    """Width-proxy pre-screening of candidate partitions.

    Trains the repo's WidthProxy (ridge on n_cells/n_transistors/
    base_width) on the existing benchmark corpus, then scores each
    candidate partition by predicted total custom width -- the cheap
    stand-in for hours of ASTRAN runs.  Returns
    (best_blocks, ranking_rows, proxy_report) or (None, [], report) when
    the corpus is too small / sklearn is missing -- the caller then just
    uses its default partition.
    """
    try:
        import width_proxy as wp
    except ImportError as exc:                       # sklearn missing etc.
        return None, [], {"skipped": str(exc)}

    repo_flow = os.path.dirname(os.path.abspath(__file__))
    output_dirs = sorted(
        d for d in glob.glob(os.path.join(repo_flow, "outputs", "*"))
        if glob.glob(os.path.join(d, "COMPLEX*.sp")))
    width_by_type = {t: a / ROW_HEIGHT for t, a in areas.items()}
    transistor_counts = wp.count_transistors_per_type(cells_spice_path)
    proxy, report = wp.train_or_load_width_proxy(
        output_dirs, transistor_counts, width_by_type,
        path=os.path.join(repo_flow, "outputs", "width_proxy.json"))
    if proxy is None:
        return None, [], report

    counts = gf.library_transistor_counts(lib_sp)
    ranking = []
    for budget in budgets:
        blocks = gf.partition_instances(insts, lib_sp, max_transistors=budget)
        predicted = 0.0
        for members in blocks:
            n_cells = len(members)
            n_trans = sum(counts[i.cell_type] for i in insts
                          if i.name in members)
            base_w = sum(areas[i.cell_type] for i in insts
                         if i.name in members) / ROW_HEIGHT
            predicted += proxy.predict(n_cells, n_trans, base_w)
        ranking.append({"budget": budget, "n_blocks": len(blocks),
                        "predicted_width_um": round(predicted, 3)})
    ranking.sort(key=lambda r: r["predicted_width_um"])
    best = gf.partition_instances(insts, lib_sp,
                                  max_transistors=ranking[0]["budget"])
    return best, ranking, report


def main(argv=None, on_note=None, should_cancel=None):
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
    parser.add_argument("--partition-search", action="store_true",
                        help="score candidate partition budgets with the "
                             "width proxy and use the predicted best "
                             "(falls back to --max-transistors when the "
                             "proxy corpus is too small)")
    parser.add_argument("--jobs", type=int, default=1,
                        help="parallel ASTRAN workers")
    parser.add_argument("--resume", action="store_true",
                        help="skip cells whose .sp is unchanged")
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--skip-astran", action="store_true")
    parser.add_argument("--no-png", action="store_true")
    parser.add_argument("--liberty-closure", action="store_true",
                        help="emit .lib fragments for the measured blocks "
                             "and re-map the design with the extended "
                             "library (abc) for a design-level benefit "
                             "number; needs measured widths")
    args = parser.parse_args(argv)

    stem = os.path.splitext(os.path.basename(args.verilog))[0]
    outdir = os.path.abspath(args.out or (stem + "_cells"))
    os.makedirs(outdir, exist_ok=True)
    t_start = time.time()
    log_lines = []

    def note(msg):
        if should_cancel and should_cancel():
            from astran_queue import CancelledError
            raise CancelledError("cancelled by user")
        print("[v2c] " + msg, flush=True)
        log_lines.append("[v2c] " + msg)
        if on_note:
            on_note(msg)

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
    ranking = None
    if args.partition_search:
        blocks, ranking, proxy_report = rank_partitions(
            insts, lib_sp, areas,
            budgets=sorted({8, 16, 24, args.max_transistors, 48}),
            cells_spice_path=args.cells_spice)
        if blocks is None:
            note("partition search skipped (proxy: %s); using budget %d"
                 % (proxy_report, args.max_transistors))
        else:
            note("partition search (proxy n=%s): %s"
                 % (proxy_report.get("n"), "; ".join(
                     "budget %d -> %.2f um" % (r["budget"],
                                               r["predicted_width_um"])
                     for r in ranking)))
    if not ranking:
        blocks = gf.partition_instances(
            insts, lib_sp, max_transistors=args.max_transistors)
    flat = gf.flatten_blocks(blocks, insts, lib_sp, module_inputs,
                             module_outputs)
    block_members = {name: members
                     for name, members in zip(flat, blocks)}
    for name, (text, n_trans) in flat.items():
        # write only when the content actually changes: the .sp mtime is
        # the queue's resume signal (same contract as export_spice_netlist)
        path = os.path.join(outdir, name + ".sp")
        if (not os.path.exists(path)) or open(path).read() != text:
            with open(path, "w") as fh:
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
                            resume=args.resume,
                            should_cancel=should_cancel)
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
    area_by_block = block_areas(results)
    custom_total = sum(width_by_block.values())
    discrete_total = sum(discrete_by_block.values())

    odd_heights = {r.name: r.height for r in results
                   if r.ok and r.height
                   and abs(r.height - ROW_HEIGHT) > 0.01}
    if odd_heights:
        note("WARNING: measured heights differ from the discrete "
             "baseline's row height (%.2f um): %s -- per invariant 10 the "
             "width comparison is not like-for-like"
             % (ROW_HEIGHT, odd_heights))

    # ---- 5b. liberty closure ---------------------------------------------
    closure = None
    if args.liberty_closure:
        if not width_by_block:
            note("liberty closure skipped: no measured block widths")
        else:
            note("generating .lib fragments and re-mapping with abc ...")
            import block_liberty as bl
            lib_text = open(args.lib, errors="replace").read()
            lib_funcs = lv.parse_liberty_functions(lib_text)
            lib_caps = bl.parse_pin_caps(lib_text)
            fragments = []
            for name in sorted(width_by_block):
                members = block_members[name]
                ports = gf.block_ports(members, insts, module_inputs,
                                       module_outputs)
                ports = [bl._sanitize(p) for p in ports
                         if p not in ("VCC", "GND")]
                produced = {net for m in members
                            for pin, net in
                            next(i for i in insts if i.name == m).pins.items()
                            if pin in gf.OUTPUT_PINS}
                out_nets = [p for p in ports if p in produced]
                funcs = bl.compose_block_functions(
                    members, insts, lib_funcs, out_nets)
                caps = bl.block_pin_caps(members, insts, ports, lib_caps)
                fragments.append(bl.emit_fragment(
                    name, funcs, ports,
                    area_um2=area_by_block[name],
                    pin_caps=caps))
            closure = bl.closure_remap(fragments, args.verilog, args.top,
                                       args.lib, outdir)
            if closure.get("ok"):
                ext_areas = dict(areas)
                ext_areas.update(area_by_block)
                hist = closure["histogram"]
                missing = [t for t in hist if t not in ext_areas]
                if missing:
                    closure = {"ok": False,
                               "reason": "extended remap used unknown "
                                         "cells: %s" % missing}
                else:
                    extended_area = sum(ext_areas[t] * n
                                        for t, n in hist.items())
                    closure["extended_area"] = extended_area
                    closure["baseline_area"] = baseline_area
                    closure["area_saved"] = baseline_area - extended_area
                    closure["area_saved_pct"] = (
                        (baseline_area - extended_area) / baseline_area
                        * 100 if baseline_area else 0.0)
                    used = {t: n for t, n in hist.items()
                            if t in width_by_block}
                    note("closure: baseline %.4f -> extended %.4f um^2 "
                         "(%.1f%% saved), blocks used: %s"
                         % (baseline_area, extended_area,
                            closure["area_saved_pct"], used or "none"))
            if not closure.get("ok"):
                note("closure failed: %s" % closure.get("reason"))

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
        if ranking:
            fh.write("\n## Partition search (width-proxy predictions)\n\n")
            fh.write("| budget (T) | blocks | predicted width (um) |"
                     " chosen |\n|---|---|---|---|\n")
            for row in ranking:
                chosen = "x" if row is ranking[0] else ""
                fh.write("| %d | %d | %.2f | %s |\n"
                         % (row["budget"], row["n_blocks"],
                            row["predicted_width_um"], chosen))
            if custom_total:
                fh.write("\nPredicted total %.2f um vs measured %.2f um "
                         "(proxy error %.1f%%).\n"
                         % (ranking[0]["predicted_width_um"], custom_total,
                            abs(ranking[0]["predicted_width_um"]
                                - custom_total) / custom_total * 100))
        if closure:
            fh.write("\n## Design-level closure (abc remap)\n\n")
            if closure.get("ok"):
                fh.write("Re-mapping the unmapped design with the base "
                         "library vs the extended library (blocks "
                         "available as cells):\n\n")
                fh.write("- baseline area: %.4f um^2\n"
                         "- extended area: %.4f um^2\n"
                         "- saved: %.4f um^2 (%.2f%%)\n"
                         % (closure.get("baseline_area") or 0,
                            closure.get("extended_area") or 0,
                            closure.get("area_saved") or 0,
                            closure.get("area_saved_pct") or 0))
                used = {t: n for t, n in closure.get("histogram", {}).items()
                        if t in width_by_block}
                fh.write("- blocks used by abc: %s\n"
                         % (used if used else "none"))
                fh.write("- extended library: `%s`\n"
                         % closure.get("extended_lib"))
            else:
                fh.write("closure failed: %s\n" % closure.get("reason"))
        fh.write("\n_Generated by verilog2cells.py in %.0fs._\n"
                 % (time.time() - t_start))
    note("report: %s" % report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
