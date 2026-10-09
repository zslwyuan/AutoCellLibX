"""Regenerate outputs/adder/bestRecord-seperateadder.

A verbatim replay of main.py's phase 2 (the per-pattern record loop), driven
with the phase-1 state of the committed adder run: the five dumped traces and
their trace->id mapping.  Phase 2 itself cannot run in the full pipeline
because COMPLEX11/12's generation does not terminate (CBC ignores the time
limit on the largest models), which previously aborted the benchmark before
phase 2.  The replay keeps the same guards main.py now has (skip patterns
without a usable layout) and additionally skips grown traces that were never
dumped.  Deterministic: same formulas, same floats as the real loop.
"""
import os
import sys
import time

sys.path.insert(0, os.getcwd())
from astran import loadAstranArea
from blif_graph_util import (removeEmptySeqsAndDisableClusters,
                           sortPatternClusterSeqs)
from blif_pattern_growth import grow_sequence_of_clusters_based_on
from blif_preproc import (getArea,
                         heuristic_label_initial_clusters_based_on,
                         loadDataAndPreprocess)
from gds_analysis import loadAstranGDS, loadOrignalGSCL45nmGDS
from spice import exportSpiceNetlist, load_spice_subcircuits

benchmarkName = "adder"
outputPath = "./outputs/" + benchmarkName + "/"
ratioThr, cntThr = 0.05, 30

dumpedPaterns = {
    "[NAND2X1,NAND2X1,OR2X1]": 0,
    "[XNOR2X1,XOR2X1,OAI21X1]": 1,
    "[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0": 9,
    "[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0+OAI21X1_c2o0": 10,
    "[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0+OAI21X1_c2o0+AND2X1_c4i0": 11,
}
detectedPatterns = list(dumpedPaterns)

subckts = load_spice_subcircuits("../stdCelllib/cellsAstranFriendly.sp")
stdType2GSCLArea = loadOrignalGSCL45nmGDS()

countedSet = set()
recordPatternDetails = []
detectedPatterns.reverse()
fileResult = open(outputPath + "bestRecord-seperate" + benchmarkName, 'w')
for targetPatternTrace in detectedPatterns:
    if (targetPatternTrace in countedSet):
        continue

    BLIFGraph, cells, netlist, stdCellTypesForFeature, dataset, maxLabelIndex, clusterSeqs, clusterNum = loadDataAndPreprocess(
        libFileName="../stdCelllib/gscl45nm.lib", blifFileName="../benchmark/blif/"+benchmarkName+".blif", startTime=0, bypassInitialCluster=True)

    clusterSeqs, clusterNum = heuristic_label_initial_clusters_based_on(
        BLIFGraph, cells, netlist, targetPatternTrace)

    oriArea = getArea(cells, stdType2GSCLArea)

    stdType2AstranArea = loadAstranGDS()
    astranArea = getArea(cells, stdType2AstranArea)

    clusterSeqs = sortPatternClusterSeqs(clusterSeqs)

    patternNum = len(clusterSeqs)
    bestSaveArea = 0
    lastSaveGSCLArea = 0
    lastComplexSelection = 0

    for i in range(0, 10):
        print("searching for ", targetPatternTrace)
        if (len(clusterSeqs) == 0 or len(clusterSeqs[0].patternClusters) == 0):
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
            if (tmpClusterSeq.patternExtensionTrace not in dumpedPaterns):
                break  # grown beyond the dumped patterns: nothing to record
            patternTraceId = dumpedPaterns[tmpClusterSeq.patternExtensionTrace]

            exampleCells = []
            for cellId in tmpClusterSeq.patternClusters[0].cellIdsContained:
                exampleCells.append(cells[cellId])

            complexSelection.append(("COMPLEX"+str(patternTraceId), len(
                tmpClusterSeq.patternClusters), len(tmpClusterSeq.patternClusters[0].cellIdsContained), tmpClusterSeq.patternExtensionTrace))
            oriUnitAstranArea = getArea(
                exampleCells, stdType2AstranArea)
            oriUnitGSCLArea = getArea(exampleCells, stdType2GSCLArea)
            try:
                newUnitAstranArea = loadAstranArea(
                    outputPath, "COMPLEX"+str(patternTraceId))
            except Exception:
                print("WARNING :", benchmarkName,
                      " COMPLEX"+str(patternTraceId),
                      " has no usable layout; skipping it in the records")
                continue
            if (newUnitAstranArea <= 0):
                print("WARNING :", benchmarkName,
                      " COMPLEX"+str(patternTraceId),
                      " has zero width; skipping it in the records")
                continue
            saveArea += (oriUnitAstranArea-newUnitAstranArea) * \
                len(tmpClusterSeq.patternClusters)
            saveGSCLArea += (oriUnitGSCLArea-newUnitAstranArea) * \
                len(tmpClusterSeq.patternClusters)

            touch = True

        print("saveArea=", saveArea, " / ",
              saveArea/astranArea*100, "%")
        if (touch and (not tmpClusterSeq.patternExtensionTrace in countedSet)):

            countedSet.add(tmpClusterSeq.patternExtensionTrace)
            bestSaveArea = saveArea
            lastSaveGSCLArea = saveGSCLArea
            lastComplexSelection = complexSelection

            recordPatternDetails.append((bestSaveArea, bestSaveArea/astranArea*100,
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

        newSeqOfClusters, patternNum = grow_sequence_of_clusters_based_on(
            BLIFGraph, clusterSeq, clusterNum, patternNum,  paintPattern=True, targetPatternTrace=targetPatternTrace)

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
print("wrote", outputPath + "bestRecord-seperate" + benchmarkName)
