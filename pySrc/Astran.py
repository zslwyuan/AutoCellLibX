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


def loadAstranArea(GDSPath, typeName):
    """Nominal cell width of a generated cell, read from its ASTRAN log.

    Width is used as the area proxy: cell area is proportional to width at a
    fixed row height, so this compares the ASTRAN baseline (generated at
    H=3.2um) and the locally generated cells (H=2.6um) consistently.  Same
    metric as GDSIIAnalysis.loadAstranGDS / loadOrignalGSCL45nmGDS.
    """
    logFileName = os.path.join(GDSPath, typeName + ".Astranlog")
    if (os.path.exists(logFileName)):
        for line in open(logFileName, 'r'):
            if (line.find("-> Cell Size (W x H): ") >= 0):
                return float(line.replace("-> Cell Size (W x H): ", "").split("x")[0])

    assert(False)
    return 123


# Cell geometry written into every ASTRAN run script.  Row height is
# cellsHeight * vGrid = 13 * 0.20 = 2.6 um.  These are set explicitly instead
# of relying on ASTRAN's compiled-in defaults so a run is reproducible.  To
# target a different library's row height, change them here (e.g. 13 * 0.19 =
# 2.47 um for the GSCL45 site height) and re-validate DRC on the layouts.
ASTRAN_CELLS_HEIGHT = 13
ASTRAN_HGRID = 0.20
ASTRAN_VGRID = 0.20
ASTRAN_SUPPLY_SIZE = 0.72
ASTRAN_NWELL_POS = 1.14
ASTRAN_CELL_TEMPLATE = "Tapless"


def buildAstranCommands(gurobiPath, technologyPath, spiceNetlistPath, complexName, commandDir):
    """Build the ASTRAN shell-mode script for one cell (runs nothing)."""
    script = """set lpsolve "@gurobiPath@"
load technology "@technologyPath@"
load netlist "@netlistPath@"
set rowheight @cellsHeight@
set grid @hGrid@ @vGrid@
set supplysize @supplySize@
set nwellpos @nwellPos@
set celltemplate "@cellTemplate@"
cellgen select @name@
cellgen autoflow
export layout @name@ @commandDir@/@name@.gds
exit
"""
    substitutions = {
        "gurobiPath": gurobiPath,
        "technologyPath": technologyPath,
        "netlistPath": spiceNetlistPath,
        "cellsHeight": str(ASTRAN_CELLS_HEIGHT),
        "hGrid": "%g" % ASTRAN_HGRID,
        "vGrid": "%g" % ASTRAN_VGRID,
        "supplySize": "%g" % ASTRAN_SUPPLY_SIZE,
        "nwellPos": "%g" % ASTRAN_NWELL_POS,
        "cellTemplate": ASTRAN_CELL_TEMPLATE,
        "name": complexName,
        "commandDir": commandDir,
    }
    for key, value in substitutions.items():
        script = script.replace("@%s@" % key, value)
    return script


def runAstranForNetlist(AstranPath, gurobiPath, technologyPath, spiceNetlistPath, complexName, commandDir):
    commands = buildAstranCommands(gurobiPath, technologyPath,
                                   spiceNetlistPath, complexName, commandDir)

    outputFile = open(commandDir+"/"+complexName+".run", 'w')
    print(commands, file=outputFile)
    outputFile.close()

    os.system(AstranPath+"/bin/Astran --shell " +
              commandDir+"/"+complexName+".run > " +
              commandDir+"/"+complexName+".Astranlog")


def astranLayoutIsStale(gdsPath, netlistPath):
    """Whether a cached ASTRAN layout must be regenerated.

    A layout is stale when it is missing, or when the netlist it was built from
    is newer than the layout file.  This guards the "skip when the .gds already
    exists" cache in main.py: the pattern/cluster fixes can change a COMPLEX
    netlist while an older layout is still on disk, and reusing that layout
    silently reports an area that does not belong to the current netlist.
    """
    if (not os.path.exists(gdsPath)):
        return True
    if (os.path.exists(netlistPath) and
            os.path.getmtime(gdsPath) < os.path.getmtime(netlistPath)):
        return True
    return False
