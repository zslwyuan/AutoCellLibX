import os


def runAstranForNetlist(AstranPath, gurobiPath, technologyPath, spiceNetlistPath, complexName, commandDir):

    commands = """set lpsolve \"gurobiPath\"
load technology \"technologyPath\"
load netlist \"spiceNetlistPath\"
cellgen select complexName
cellgen autoflow
export layout complexName commandDir/complexName.gds
exit
""".replace("gurobiPath", gurobiPath).replace("technologyPath", technologyPath).replace("spiceNetlistPath", spiceNetlistPath).replace("complexName", complexName).replace("commandDir", commandDir)

    outputFile = open(commandDir+"/"+complexName+".run", 'w')
    print(commands, file=outputFile)
    outputFile.close()

    os.system(AstranPath+"/bin/Astran --shell " +
              commandDir+"/"+complexName+".run > " +
              commandDir+"/"+complexName+".Astranlog")
