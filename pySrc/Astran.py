import os

# MinGW runtime DLLs (wxWidgets etc.) for Astran.exe
if ("PATH" in os.environ):
    os.environ["PATH"] = "C:\\msys64\\mingw64\\bin;" + os.environ["PATH"]
else:
    os.environ["PATH"] = "C:\\msys64\\mingw64\\bin"

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


def runAstranForNetlist(AstranPath, gurobiPath, technologyPath, spiceNetlistPath, complexName, commandDir):
    # The circuit parameters are set explicitly (instead of relying on the
    # compiled-in defaults of Circuit::Circuit()) so that every generated cell
    # uses a known, reproducible configuration.  Values below equal ASTRAN's
    # defaults: row height = cellsHeight(13) x vGrid(0.20) = 2.6 um.
    # To match a different target library's row height, change cellsHeight
    # and/or vGrid here (e.g. 13 x 0.19 = 2.47 um for the GSCL45 site height)
    # and re-validate the layouts.
    commands_tmplate = """set lpsolve \"gurobiPath\"
load technology \"technologyPath\"
load netlist \"spiceNetlistPath\"
set rowheight 13
set grid 0.20 0.20
set supplysize 0.72
set nwellpos 1.14
set celltemplate \"Tapless\"
cellgen select complexName
cellgen autoflow
export layout complexName commandDir/complexName.gds
exit
    """

    commands = commands_tmplate.replace("gurobiPath", gurobiPath).replace("technologyPath", technologyPath).replace(
        "spiceNetlistPath", spiceNetlistPath).replace("complexName", complexName).replace("commandDir", commandDir)

    outputFile = open(commandDir+"/"+complexName+".run", 'w')
    print(commands, file=outputFile)
    outputFile.close()

    os.system(AstranPath+"/bin/Astran --shell " +
              commandDir+"/"+complexName+".run > " +
              commandDir+"/"+complexName+".Astranlog")
