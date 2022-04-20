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

    benchmarks = ["tc_001_arthmetic_adder",
                  "tc_005_arthmetic_log2",
                  "tc_009_arthmetic_sqrt",
                  "tc_l4_0413",
                  "tc_l4_0430",
                  "tc_002_arthmetic_bar",
                  "tc_l4_0431",
                  "tc_l4_0409",
                  "tc_l4_0428",
                  "tc_l4_0432",
                  "tc_l4_0412",
                  "tc_l4_0429",
                  "tc_l4_0427",
                  "tc_l8_0415"
                  ] + ["tc_006_arthmetic_max",
                       "tc_010_arthmetic_square",
                       "tc_003_arthmetic_divisor",
                       "tc_007_arthmetic_multiplier",
                       "tc_004_arthmetic_hypotenuse",
                       "tc_008_arthmetic_sin"
                       ]

    for benchmarkName in benchmarks:
        print("=================================================================================\n",
              benchmarkName, "\n=================================================================================\n")
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

        # iteratively to pick the most frequent subgraph and extend them by absorbing their neighbors
        dumpedPaterns = set()

        patternNum = len(clusterSeqs)
        for i in range(0, 10):
            if (len(clusterSeqs[0].patternClusters) == 0):
                break
            if (len(clusterSeqs[0].patternClusters[0].cellIdsContained) >= 11):
                continue

            for j in range(0, 5):
                if (j >= len(clusterSeqs)):
                    break
                tmpClusterSeq = clusterSeqs[j]
                patternTraceId = tmpClusterSeq.patternClusters[0].clusterTypeId
                patternSubgraph = BLIFGraph.subgraph(
                    tmpClusterSeq.patternClusters[0].cellIdsContained)

                if (not patternTraceId in dumpedPaterns):
                    if (len(tmpClusterSeq.patternClusters[0].cellIdsContained) >= 11):
                        continue
                    print("dealing with pattern#", patternTraceId, " with ", len(
                        tmpClusterSeq.patternClusters), " clusters (size=", len(tmpClusterSeq.patternClusters[0].cellIdsContained), ")")
                    if (len(tmpClusterSeq.patternClusters[0].cellIdsContained)*len(tmpClusterSeq.patternClusters) < 0.05 * len(cells) and len(tmpClusterSeq.patternClusters) < 100):
                        print("===Warning: the pattern is too small and bypassed.")
                        break
                    dumpedPaterns.add(patternTraceId)

                    drawColorfulFigureForGraphWithAttributes(
                        patternSubgraph, save_to_file=outputPath+"/COMPLEX"+str(patternTraceId)+".png", withLabel=True, figsize=(20, 20))

                    # export the SPICE netlist of the complex of cells
                    exportSpiceNetlist(tmpClusterSeq, subckts, str(patternTraceId),
                                       outputPath)

                    # if ASTRAN is available, run it to get the layout and area evaluation
                    if (ASTRANBuildPath != ""):
                        if (not os.path.exists(outputPath+'/COMPLEX' +
                                               str(patternTraceId)+'.gds')):
                            if (len(tmpClusterSeq.patternClusters[0].cellIdsContained) < 11):
                                runAstranForNetlist(AstranPath=ASTRANBuildPath, gurobiPath="/opt/gurobi950/linux64/bin/gurobi_cl",
                                                    technologyPath="../tools/astran/Astran/build/Work/tech_freePDK45.rul",
                                                    spiceNetlistPath=outputPath+'/COMPLEX' +
                                                    str(patternTraceId)+'.sp',
                                                    complexName='COMPLEX'+str(patternTraceId), commandDir=outputPath)

            clusterSeq = clusterSeqs[0]

            if (len(clusterSeq.patternClusters[0].cellIdsContained)*len(clusterSeq.patternClusters) < 0.05 * len(cells) and len(clusterSeq.patternClusters) < 100):
                break

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
