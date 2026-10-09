import os
import sys

# ASTRAN needs the MSYS2 runtime DLLs (wxWidgets, libstdc++...) on PATH, and its
# LP-solver wrapper (tools/gurobi_cl/gurobi_cl.cmd) calls bare `python`, which
# must be the interpreter that has python-mip installed -- i.e. the one this
# flow itself runs on.  MSYS2 also ships its own python.exe in mingw64/bin
# (pulled in by unrelated mingw packages), so the flow's interpreter must come
# FIRST or the solver wrapper resolves the wrong python and dies with
# "No module named 'mip'".
if ("PATH" in os.environ):
    os.environ["PATH"] = os.path.dirname(sys.executable) + ";" + \
        "C:\\msys64\\mingw64\\bin;" + os.environ["PATH"]
else:
    os.environ["PATH"] = os.path.dirname(sys.executable) + ";" + \
        "C:\\msys64\\mingw64\\bin"

# ASTRAN and the LP-solver wrapper are vendored under <repo>/tools so the
# project is self-contained.  Resolve everything relative to this file so the
# paths stay valid regardless of the current working directory.
_REPO_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."))
ASTRAN_BUILD_PATH = os.path.join(_REPO_DIR, "tools", "astran", "build")
ASTRAN_TECHNOLOGY = os.path.join(
    ASTRAN_BUILD_PATH, "Work", "tech_freePDK45.rul")
# Open-source replacement of Gurobi's command-line solver (gurobi_cl):
# a wrapper around python-mip + COIN-OR CBC.
GUROBI_CL = os.path.join(_REPO_DIR, "tools", "gurobi_cl", "gurobi_cl.cmd")


def load_astran_area(gds_path, type_name):
    """Nominal cell width of a generated cell, read from its ASTRAN log.

    Width is used as the area proxy: cell area is proportional to width at a
    fixed row height, so this compares the ASTRAN baseline and the locally
    generated cells (both at the GSCL45 row height H=2.47um) consistently.
    Same metric as gds_analysis.load_astran_gds / load_original_gscl45_gds.
    """
    log_file_name = os.path.join(gds_path, type_name + ".Astranlog")
    if (os.path.exists(log_file_name)):
        for line in open(log_file_name, 'r'):
            if (line.find("-> Cell Size (W x H): ") >= 0):
                return float(line.replace("-> Cell Size (W x H): ", "").split("x")[0])

    # Never fabricate a width: an assert here is stripped under `python -O`,
    # silently yielding the fallback value and corrupting the savings total.
    raise RuntimeError(
        "Cell Size line not found in ASTRAN log: " + log_file_name)


# Cell geometry written into every ASTRAN run script, calibrated to the
# GSCL45 library: the LEF's M1 routing pitch is 0.19 um, so the routing grid
# is 0.19 and the row height is cells_height * v_grid = 13 * 0.19 = 2.47 um,
# which is exactly the GSCL45 CoreSite height (LEF `SIZE x BY 2.47`).  The
# supply rails use the library's abutment style: 0.13 um tall, centred on
# the row boundary (half inside, half overhanging), hence supplysize 0.26.
# Cell widths come out as multiples of 0.19, matching the library's own
# half-site granularity.  These are set explicitly instead of relying on
# ASTRAN's compiled-in defaults so a run is reproducible.
ASTRAN_CELLS_HEIGHT = 13
ASTRAN_HGRID = 0.19
ASTRAN_VGRID = 0.19
ASTRAN_SUPPLY_SIZE = 0.26
ASTRAN_NWELL_POS = 1.235
ASTRAN_CELL_TEMPLATE = "Tapless"


def build_astran_commands(gurobi_path, technology_path, spice_netlist_path, complex_name, command_dir, geometry=None):
    """Build the ASTRAN shell-mode script for one cell (runs nothing).

    ``geometry`` optionally overrides the compiled-in constants above (keys:
    cells_height, h_grid, v_grid, supply_size, nwell_pos, cell_template).  The GUI
    uses this so the user can experiment with row height / grid / supply rails
    without editing this file; anything not in the dict keeps the constants.
    """
    script = """set lpsolve "@gurobi_path@"
load technology "@technology_path@"
load netlist "@netlist_path@"
set rowheight @cells_height@
set grid @h_grid@ @v_grid@
set supplysize @supply_size@
set nwellpos @nwell_pos@
set celltemplate "@cell_template@"
cellgen select @name@
cellgen autoflow
export layout @name@ @command_dir@/@name@.gds
exit
"""
    geometry = geometry or {}
    substitutions = {
        "gurobi_path": gurobi_path,
        "technology_path": technology_path,
        "netlist_path": spice_netlist_path,
        "cells_height": str(geometry.get("cells_height", ASTRAN_CELLS_HEIGHT)),
        "h_grid": "%g" % geometry.get("h_grid", ASTRAN_HGRID),
        "v_grid": "%g" % geometry.get("v_grid", ASTRAN_VGRID),
        "supply_size": "%g" % geometry.get("supply_size", ASTRAN_SUPPLY_SIZE),
        "nwell_pos": "%g" % geometry.get("nwell_pos", ASTRAN_NWELL_POS),
        "cell_template": geometry.get("cell_template", ASTRAN_CELL_TEMPLATE),
        "name": complex_name,
        "command_dir": command_dir,
    }
    for key, value in substitutions.items():
        script = script.replace("@%s@" % key, value)
    return script


def run_astran_for_netlist(astran_path, gurobi_path, technology_path, spice_netlist_path, complex_name, command_dir):
    commands = build_astran_commands(gurobi_path, technology_path,
                                   spice_netlist_path, complex_name, command_dir)

    output_file = open(command_dir+"/"+complex_name+".run", 'w')
    print(commands, file=output_file)
    output_file.close()

    os.system(astran_path+"/bin/Astran --shell " +
              command_dir+"/"+complex_name+".run > " +
              command_dir+"/"+complex_name+".Astranlog")


def astran_layout_is_stale(gds_path, netlist_path):
    """Whether a cached ASTRAN layout must be regenerated.

    A layout is stale when it is missing, or when the netlist it was built from
    is newer than the layout file.  This guards the "skip when the .gds already
    exists" cache in main.py: the pattern/cluster fixes can change a COMPLEX
    netlist while an older layout is still on disk, and reusing that layout
    silently reports an area that does not belong to the current netlist.
    """
    if (not os.path.exists(gds_path)):
        return True
    if (os.path.exists(netlist_path) and
            os.path.getmtime(gds_path) < os.path.getmtime(netlist_path)):
        return True
    return False
