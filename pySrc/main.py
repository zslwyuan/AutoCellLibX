from BLIFPreProc import *
#from BLIFGNNTraining import *
from BLIFPatternGrowth import *
import os
import time
import matplotlib
from spice import *
from Astran import *


def mkdir(pathStr):
    if os.path.exists(pathStr):
        pass
    else:
        os.mkdir(pathStr)


def main():
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    # ASTRANBuildPath = ""  # empty when Astran is unavailable.
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    ASTRANBuildPath = "../tools/astran/Astran/build"

    startTime = time.time()

    benchmarks = ['tc_l4_0427']

    for benchmarkName in benchmarks:
        # load liberty/spice/design BLIF
        subckts = loadSpiceSubcircuits("../stdCelllib/cellsAstranFriendly.sp")
        BLIFGraph, cells, netlist, stdCellTypesForFeature, dataset, maxLabelIndex, clusterSeqs, clusterNum = loadDataAndPreprocess(
            libFileName="../stdCelllib/gscl45nm.lib", blifFileName="../benchmark/blif/"+benchmarkName+".blif", startTime=startTime)
        outputPath = "./outputs/"+benchmarkName
        mkdir(outputPath)

        if (ASTRANBuildPath != ""):
            for oriStdCellType in stdCellTypesForFeature:
                bypass = False
                for tmpType in bypassTypes:
                    if (oriStdCellType.find(tmpType) >= 0):
                        bypass = True
                        break
                if (bypass or os.path.exists('./originalAstranStdCells/'+oriStdCellType+'.gds')):
                    continue
                runAstranForNetlist(AstranPath=ASTRANBuildPath, gurobiPath="/opt/gurobi950/linux64/bin/gurobi_cl",
                                    technologyPath="../tools/astran/Astran/build/Work/tech_freePDK45.rul",
                                    spiceNetlistPath='../stdCelllib/cellsAstranFriendly.sp',
                                    complexName=oriStdCellType, commandDir='./originalAstranStdCells/')

        clusterSeqs = sortPatternClusterSeqs(clusterSeqs)

        # # export initial patterns
        # for id, clusterSeq in enumerate(clusterSeqs):
        #     patternSubgraph = BLIFGraph.subgraph(
        #         clusterSeq.patternClusters[0].cellIdsContained)

        #     patternTraceId = clusterSeq.patternClusters[0].clusterTypeId
        #     drawColorfulFigureForGraphWithAttributes(
        #         patternSubgraph, save_to_file=outputPath+"/COMPLEX"+str(patternTraceId)+".png", withLabel=True, figsize=(20, 20))

        #     # export the SPICE netlist of the complex of cells
        #     exportSpiceNetlist(clusterSeq, subckts, str(patternTraceId),
        #                        outputPath)

        #     # if ASTRAN is available, run it to get the layout and area evaluation
        #     if (ASTRANBuildPath != ""):
        #         runAstranForNetlist(AstranPath=ASTRANBuildPath, gurobiPath="/opt/gurobi950/linux64/bin/gurobi_cl",
        #                             technologyPath="../tools/astran/Astran/build/Work/tech_freePDK45.rul",
        #                             spiceNetlistPath=outputPath+'/COMPLEX' +
        #                             str(patternTraceId)+'.sp',
        #                             complexName='COMPLEX'+str(patternTraceId), commandDir=outputPath)

        # iteratively to pick the most frequent subgraph and extend them by absorbing their neighbors
        dumpedPaterns = set()

        patternNum = len(clusterSeqs)
        for i in range(0, 20):
            if (len(clusterSeqs[0].patternClusters) == 0):
                break

            clusterSeq = clusterSeqs[0]
            patternSubgraph = BLIFGraph.subgraph(
                clusterSeq.patternClusters[0].cellIdsContained)
            patternTraceId = clusterSeq.patternClusters[0].clusterTypeId

            if (not patternTraceId in dumpedPaterns):
                dumpedPaterns.add(patternTraceId)
                print("dealing with pattern#", patternTraceId, " with ", len(
                    clusterSeqs[0].patternClusters), " clusters (size=", len(clusterSeq.patternClusters[0].cellIdsContained), ")")

                drawColorfulFigureForGraphWithAttributes(
                    patternSubgraph, save_to_file=outputPath+"/COMPLEX"+str(patternTraceId)+".png", withLabel=True, figsize=(20, 20))

                # export the SPICE netlist of the complex of cells
                exportSpiceNetlist(clusterSeq, subckts, str(patternTraceId),
                                   outputPath)

                # if ASTRAN is available, run it to get the layout and area evaluation
                if (ASTRANBuildPath != ""):
                    if (len(clusterSeq.patternClusters[0].cellIdsContained) < 11):
                        runAstranForNetlist(AstranPath=ASTRANBuildPath, gurobiPath="/opt/gurobi950/linux64/bin/gurobi_cl",
                                            technologyPath="../tools/astran/Astran/build/Work/tech_freePDK45.rul",
                                            spiceNetlistPath=outputPath+'/COMPLEX' +
                                            str(patternTraceId)+'.sp',
                                            complexName='COMPLEX'+str(patternTraceId), commandDir=outputPath)

            newSeqOfClusters, patternNum = growASeqOfClusters(
                BLIFGraph, clusterSeq, clusterNum, patternNum, paintPattern=True)

            # export the SPICE netlist of the complex of cells
            exportSpiceNetlist(newSeqOfClusters[0], subckts, len(
                clusterSeqs), outputPath)

            clusterSeqs = clusterSeqs[1:]
            clusterSeqs += newSeqOfClusters
            clusterSeqs = removeEmptySeqsAndDisableClusters(clusterSeqs)
            clusterSeqs = sortPatternClusterSeqs(clusterSeqs)


if __name__ == '__main__':
    matplotlib.use("Pdf")
    main()
