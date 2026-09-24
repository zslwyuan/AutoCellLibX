import os

# MinGW runtime DLLs (wxWidgets etc.) for Astran.exe
if ("PATH" in os.environ):
    os.environ["PATH"] = "C:\\msys64\\mingw64\\bin;" + os.environ["PATH"]
else:
    os.environ["PATH"] = "C:\\msys64\\mingw64\\bin"

# Open-source replacement of Gurobi's command-line solver (gurobi_cl):
# a wrapper around python-mip + COIN-OR CBC.  See D:\aclx-tools\gurobi_cl.py
GUROBI_CL = "D:/aclx-tools/gurobi_cl.cmd"


def loadAstranArea(GDSPath, typeName):
    gdsFiles = [f for f in os.listdir(GDSPath) if os.path.isfile(
        os.path.join(GDSPath, f)) and f.find(".gds") >= 0]
    for gdsFile in gdsFiles:
        if (typeName+".gds" != gdsFile):
            continue
        logFileName = GDSPath+gdsFile.replace(".gds", ".Astranlog")
        logFile = open(logFileName, 'r')
        lines = logFile.readlines()
        logFile.close()

        for line in lines:
            if (line.find("-> Cell Size (W x H): ") >= 0):
                return float(line.replace("-> Cell Size (W x H): ", "").split("x")[0])*0.8*3.2

    assert(False)
    return 123


def runAstranForNetlist(AstranPath, gurobiPath, technologyPath, spiceNetlistPath, complexName, commandDir):
    commands_tmplate = """set lpsolve \"gurobiPath\"
load technology \"technologyPath\"
load netlist \"spiceNetlistPath\"
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
