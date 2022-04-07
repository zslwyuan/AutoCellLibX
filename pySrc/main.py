from BLIFPreProc import *
#from BLIFGNNTraining import *
from BLIFPatternGrowth import *
import os
import time
import matplotlib
from spice import *
from Astran import *


def main():
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    # ASTRANBuildPath = "" # empty when Astran is unavailable.
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    ASTRANBuildPath = "../tools/astran/Astran/build"

    startTime = time.time()

    # load liberty/spice/design BLIF
    subckts = loadSpiceSubcircuits("../stdCelllib/cellsAstranFriendly.sp")
    BLIFGraph, cells, netlist, stdCellTypesForFeature, dataset, maxLabelIndex, clusterSeqs, clusterNum = loadDataAndPreprocess(
        libFileName="../stdCelllib/gscl45nm.lib", blifFileName="../benchmark/boomModule/boom.blif", startTime=startTime)

    # actually we don't need GCN for ASIC netlist, FPGA netlists need it
    # encodes = enbeddedNodes_GNN(
    #     BLIFGraph, dataset, maxLabelIndex, startTime)

    # encodedEntireGraphWIthLabelOrder(
    #     cells=cells, encodes=encodes, startTime=startTime)

    # export initial patterns
    for id, clusterSeq in enumerate(clusterSeqs):
        patternSubgraph = BLIFGraph.subgraph(
            clusterSeq.patternClusters[0].cellIdsContained)
        drawColorfulFigureForGraphWithAttributes(
            patternSubgraph, save_to_file="./figs/COMPLEX"+str(id)+".png", withLabel=True, figsize=(20, 20))

        # export the SPICE netlist of the complex of cells
        exportSpiceNetlist(clusterSeq, subckts, str(id),
                           './netlistsAndLayouts/')

        # if ASTRAN is available, run it to get the layout and area evaluation
        if (ASTRANBuildPath != ""):
            runAstranForNetlist(AstranPath=ASTRANBuildPath, gurobiPath="/opt/gurobi950/linux64/bin/gurobi_cl",
                                technologyPath="../tools/astran/Astran/build/Work/tech_freePDK45.rul",
                                spiceNetlistPath='./netlistsAndLayouts/COMPLEX' +
                                str(id)+'.sp',
                                complexName='COMPLEX'+str(id), commandDir='./netlistsAndLayouts/')

    # iteratively to pick the most frequent subgraph and extend them by absorbing their neighbors
    for i in range(0, 20):
        newSeqOfClusters = growASeqOfClusters(
            BLIFGraph, clusterSeqs[0], clusterNum, len(clusterSeqs), paintPattern=True)

        # export the SPICE netlist of the complex of cells
        exportSpiceNetlist(newSeqOfClusters[0], subckts, len(
            clusterSeqs), './netlistsAndLayouts/')

        # if ASTRAN is available, run it to get the layout and area evaluation
        if (ASTRANBuildPath != ""):
            runAstranForNetlist(AstranPath=ASTRANBuildPath, gurobiPath="/opt/gurobi950/linux64/bin/gurobi_cl",
                                technologyPath="../tools/astran/Astran/build/Work/tech_freePDK45.rul",
                                spiceNetlistPath='./netlistsAndLayouts/COMPLEX' +
                                str(len(clusterSeqs))+'.sp',
                                complexName='COMPLEX'+str(len(clusterSeqs)), commandDir='./netlistsAndLayouts/')

        clusterSeqs = clusterSeqs[1:]
        clusterSeqs += newSeqOfClusters
        clusterSeqs = removeEmptySeqs(clusterSeqs)
        clusterSeqs = sortPatternClusterSeqs(clusterSeqs)


if __name__ == '__main__':
    matplotlib.use("Pdf")
    main()
