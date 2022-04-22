from numpy import record
from BLIFPreProc import *
# from BLIFGNNTraining import *
from BLIFPatternGrowth import *
import os
import time
import matplotlib
from spice import *
from Astran import *
from GDSIIAnalysis import *


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
# "tc_001_arthmetic_adder", "tc_002_arthmetic_bar", "tc_003_arthmetic_divisor",
#                   "tc_004_arthmetic_hypotenuse", "tc_005_arthmetic_log2",
#                   "tc_006_arthmetic_max","tc_007_arthmetic_multiplier",
    #   "tc_008_arthmetic_sin",
    #   "tc_009_arthmetic_sqrt", "tc_010_arthmetic_square"
    # "tc_l4_0413", "tc_l4_0430", "tc_l4_0431", "tc_l4_0409",
    #        "tc_l4_0428", "tc_l4_0432",
    benchmarks = ["tc_l4_0412", "tc_l4_0429",
                  "tc_l4_0427", "tc_l8_0415"
                  ]

    stdType2GSCLArea = loadOrignalGSCL45nmGDS()
    topThr = 5
    ratioThr = 0.05
    cntThr = 30
    # benchmarks = ["tc_008_arthmetic_sin"]
    # ratioThr = -1
    # cntThr = -1

    for benchmarkName in benchmarks:

        ratioThr = 0.05
        cntThr = 30
        if (benchmarkName == "tc_008_arthmetic_sin"):
            ratioThr = 0.025

        print("=================================================================================\n",
              benchmarkName, "\n=================================================================================\n")
        # load liberty/spice/design BLIF
        subckts = loadSpiceSubcircuits("../stdCelllib/cellsAstranFriendly.sp")
        BLIFGraph, cells, netlist, stdCellTypesForFeature, dataset, maxLabelIndex, clusterSeqs, clusterNum = loadDataAndPreprocess(
            libFileName="../stdCelllib/gscl45nm.lib", blifFileName="../benchmark/blif/"+benchmarkName+".blif", startTime=startTime)
        oriArea = getArea(cells, stdType2GSCLArea)
        print("originalArea=", oriArea)

        outputPath = "./outputs/"+benchmarkName+"/"
        mkdir(outputPath)

        if (ASTRANBuildPath != ""):
            for oriStdCellType in stdCellTypesForFeature:
                if (oriStdCellType.find("bool") >= 0):
                    continue
                if (os.path.exists('./originalAstranStdCells/'+oriStdCellType+'.gds')):
                    continue
                runAstranForNetlist(AstranPath=ASTRANBuildPath, gurobiPath="/opt/gurobi950/linux64/bin/gurobi_cl",
                                    technologyPath="../tools/astran/Astran/build/Work/tech_freePDK45.rul",
                                    spiceNetlistPath='../stdCelllib/cellsAstranFriendly.sp',
                                    complexName=oriStdCellType, commandDir='./originalAstranStdCells/')
        stdType2AstranArea = loadAstranGDS()
        astranArea = getArea(cells, stdType2AstranArea)
        print("astranArea=", astranArea)

        clusterSeqs = sortPatternClusterSeqs(clusterSeqs)

        # iteratively to pick the most frequent subgraph and extend them by absorbing their neighbors
        dumpedPaterns = dict()
        detectedPatterns = []

        patternNum = len(clusterSeqs)
        lastSaveArea = 0
        lastSaveGSCLArea = 0
        lastComplexSelection = 0
        targetPatternTrace = ""

        for i in range(0, topThr):
            if (len(clusterSeqs[0].patternClusters) == 0):
                break
            if (len(clusterSeqs[0].patternClusters[0].cellIdsContained) >= 11):
                continue

            saveArea = 0
            saveGSCLArea = 0
            complexSelection = []
            for j in range(0, topThr):
                if (j >= len(clusterSeqs)):
                    break
                tmpClusterSeq = clusterSeqs[j]
                patternTraceId = tmpClusterSeq.patternClusters[0].clusterTypeId
                patternSubgraph = BLIFGraph.subgraph(
                    tmpClusterSeq.patternClusters[0].cellIdsContained)

                if (not patternTraceId in dumpedPaterns.keys()):
                    if (len(tmpClusterSeq.patternClusters[0].cellIdsContained) >= 11):
                        continue
                    print("dealing with pattern#", patternTraceId, " with ", len(
                        tmpClusterSeq.patternClusters), " clusters (size=", len(tmpClusterSeq.patternClusters[0].cellIdsContained), ")")

                    if (len(tmpClusterSeq.patternClusters[0].cellIdsContained)*len(tmpClusterSeq.patternClusters) < ratioThr * len(cells) and len(tmpClusterSeq.patternClusters) < cntThr):
                        print("===Warning: the pattern is too small and bypassed. pattern: [", tmpClusterSeq.patternExtensionTrace, "]", len(
                            tmpClusterSeq.patternClusters[0].cellIdsContained)*len(tmpClusterSeq.patternClusters), "<<<", len(cells))
                        break
                    dumpedPaterns[tmpClusterSeq.patternExtensionTrace] = patternTraceId
                    detectedPatterns.append(
                        tmpClusterSeq.patternExtensionTrace)

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

                exampleCells = []
                for cellId in tmpClusterSeq.patternClusters[0].cellIdsContained:
                    exampleCells.append(cells[cellId])

                complexSelection.append(("COMPLEX"+str(patternTraceId), len(
                    tmpClusterSeq.patternClusters), len(tmpClusterSeq.patternClusters[0].cellIdsContained), tmpClusterSeq.patternExtensionTrace))
                oriUnitAstranArea = getArea(exampleCells, stdType2AstranArea)
                oriUnitGSCLArea = getArea(exampleCells, stdType2GSCLArea)
                newUnitAstranArea = loadAstranArea(
                    outputPath, "COMPLEX"+str(patternTraceId))
                saveArea += (oriUnitAstranArea-newUnitAstranArea) * \
                    len(tmpClusterSeq.patternClusters)
                saveGSCLArea += (oriUnitGSCLArea-newUnitAstranArea) * \
                    len(tmpClusterSeq.patternClusters)

            print("saveArea=", saveArea, " / ", saveArea/astranArea*100, "%")
            if (saveArea > lastSaveArea):
                lastSaveArea = saveArea
                lastSaveGSCLArea = saveGSCLArea
                lastComplexSelection = complexSelection
                fileResult = open(outputPath+"/bestRecord-"+benchmarkName, 'w')
                print(lastSaveArea, " <- compared to Astran GDS area",
                      file=fileResult)
                print(lastSaveArea/astranArea*100,
                      "% <- compared to Astran GDS area", file=fileResult)
                print(lastSaveGSCLArea,
                      " <- compared to GSCL GDS area", file=fileResult)
                print(lastSaveGSCLArea/oriArea*100,
                      "% <- compared to GSCL GDS area", file=fileResult)
                print(
                    "The generated complex cells are (name, clusterNum, cellNumInOneCluster, patternCode):", file=fileResult)
                for complexName in lastComplexSelection:
                    print(complexName, file=fileResult)
                fileResult.close()
            else:
                break

            clusterSeq = clusterSeqs[0]

            assert(ratioThr > 0)
            if (len(clusterSeq.patternClusters[0].cellIdsContained)*len(clusterSeq.patternClusters) < ratioThr * len(cells)
                    and len(clusterSeq.patternClusters) < cntThr):
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

        countedSet = set()
        recordPatternDetails = []
        detectedPatterns.reverse()
        fileResult = open(
            outputPath+"/bestRecord-"+benchmarkName, 'w')
        for targetPatternTrace in detectedPatterns:
            if (targetPatternTrace in countedSet):
                continue

            BLIFGraph, cells, netlist, stdCellTypesForFeature, dataset, maxLabelIndex, clusterSeqs, clusterNum = loadDataAndPreprocess(
                libFileName="../stdCelllib/gscl45nm.lib", blifFileName="../benchmark/blif/"+benchmarkName+".blif", startTime=startTime, bypassInitialCluster=True)

            clusterSeqs, clusterNum = heuristicLabelSomeNodesAndGetInitialClusters_BasedOn(
                BLIFGraph, cells, netlist, targetPatternTrace)
            endTime = time.time()
            print("heuristicLabelSomeNodesAndGetInitialClusters done. time esclaped: ",
                  endTime-startTime)

            oriArea = getArea(cells, stdType2GSCLArea)
            print("originalArea=", oriArea)

            outputPath = "./outputs/"+benchmarkName+"/"
            mkdir(outputPath)

            stdType2AstranArea = loadAstranGDS()
            astranArea = getArea(cells, stdType2AstranArea)
            print("astranArea=", astranArea)

            clusterSeqs = sortPatternClusterSeqs(clusterSeqs)

            patternNum = len(clusterSeqs)
            lastSaveArea = 0
            lastSaveGSCLArea = 0
            lastComplexSelection = 0

            for i in range(0, 10):
                print("searching for ", targetPatternTrace)
                if (len(clusterSeqs[0].patternClusters) == 0):
                    break
                if (len(clusterSeqs[0].patternClusters[0].cellIdsContained) >= 11):
                    continue

                saveArea = 0
                saveGSCLArea = 0
                complexSelection = []
                touch = False
                for j in range(0, 1):
                    if (j >= len(clusterSeqs)):
                        break
                    tmpClusterSeq = clusterSeqs[j]
                    patternTraceId = dumpedPaterns[tmpClusterSeq.patternExtensionTrace]
                    patternSubgraph = BLIFGraph.subgraph(
                        tmpClusterSeq.patternClusters[0].cellIdsContained)

                    exampleCells = []
                    for cellId in tmpClusterSeq.patternClusters[0].cellIdsContained:
                        exampleCells.append(cells[cellId])

                    complexSelection.append(("COMPLEX"+str(patternTraceId), len(
                        tmpClusterSeq.patternClusters), len(tmpClusterSeq.patternClusters[0].cellIdsContained), tmpClusterSeq.patternExtensionTrace))
                    oriUnitAstranArea = getArea(
                        exampleCells, stdType2AstranArea)
                    oriUnitGSCLArea = getArea(exampleCells, stdType2GSCLArea)
                    newUnitAstranArea = loadAstranArea(
                        outputPath, "COMPLEX"+str(patternTraceId))
                    saveArea += (oriUnitAstranArea-newUnitAstranArea) * \
                        len(tmpClusterSeq.patternClusters)
                    saveGSCLArea += (oriUnitGSCLArea-newUnitAstranArea) * \
                        len(tmpClusterSeq.patternClusters)

                    touch = True

                print("saveArea=", saveArea, " / ",
                      saveArea/astranArea*100, "%")
                if (touch and (not tmpClusterSeq.patternExtensionTrace in countedSet)):

                    countedSet.add(tmpClusterSeq.patternExtensionTrace)
                    lastSaveArea = saveArea
                    lastSaveGSCLArea = saveGSCLArea
                    lastComplexSelection = complexSelection

                    # print(lastSaveArea, " <- compared to Astran GDS area",
                    #       file=fileResult)
                    # print(lastSaveArea/astranArea*100,
                    #       "% <- compared to Astran GDS area", file=fileResult)
                    # print(lastSaveGSCLArea,
                    #       " <- compared to GSCL GDS area", file=fileResult)
                    # print(lastSaveGSCLArea/oriArea*100,
                    #       "% <- compared to GSCL GDS area", file=fileResult)
                    # print(
                    #     "The generated complex cells are (name, clusterNum, cellNumInOneCluster, patternCode):", file=fileResult)

                    recordPatternDetails.append((lastSaveArea, lastSaveArea/astranArea*100,
                                                 len(tmpClusterSeq.patternClusters),
                                                 len(
                                                     tmpClusterSeq.patternClusters[0].cellIdsContained),
                                                 len(tmpClusterSeq.patternClusters[0].cellIdsContained)*len(
                                                     tmpClusterSeq.patternClusters),
                                                 "COMPLEX"+str(patternTraceId),
                                                 tmpClusterSeq.patternExtensionTrace)
                                                )
                    if (targetPatternTrace == lastComplexSelection[0][3]):
                        break

                clusterSeq = clusterSeqs[0]
                if (len(clusterSeq.patternClusters[0].cellIdsContained)*len(clusterSeq.patternClusters) < ratioThr * len(cells)
                        and len(clusterSeq.patternClusters) < cntThr):
                    break

                newSeqOfClusters, patternNum = growASeqOfClusters_BasedOn(
                    BLIFGraph, clusterSeq, clusterNum, patternNum,  paintPattern=True, targetPatternTrace=targetPatternTrace)

                # export the SPICE netlist of the complex of cells
                exportSpiceNetlist(newSeqOfClusters[0], subckts, len(
                    clusterSeqs), outputPath)

                clusterSeqs = clusterSeqs[1:]
                clusterSeqs += newSeqOfClusters
                clusterSeqs = removeEmptySeqsAndDisableClusters(clusterSeqs)
                clusterSeqs = sortPatternClusterSeqs(clusterSeqs)

        recordPatternDetails = sorted(recordPatternDetails,
                                      key=lambda x: -x[0])
        print("| designOverallArea | saveArea | saveRatio | patternCnt | patternSize |"
              " patternCoverage | patternName | patternCode |",  file=fileResult)
        for saveArea, saveRatio, patternCnt, patternSize, patternCoverage, patternName, patternCode in recordPatternDetails:
            print('|', oriArea, '|', saveArea, '|', saveRatio, '|', patternCnt, '|', patternSize, '|',
                  patternCoverage, '|', patternName, '|', patternCode, '|', file=fileResult)
        fileResult.close()


if __name__ == '__main__':
    matplotlib.use("Pdf")
    main()
