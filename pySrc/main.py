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
from benefit import ShrinkModel, makeGrowthBenefitEstimator
from routability import loadCellRoutability
from electrical import loadCellElectricalMetrics, patternElectricalMetrics
from timing_power import loadTimingPower, patternTimingPower
from yosys_import import (runYosysStat, compareWithFlowArea,
                          compareCellCounts)
from layout_sanity import checkLayout
from liberty_gen import generateComplexLiberty, loadLibertyFunctions
from width_proxy import (WidthProxy, collectSamples,
                         countTransistorsPerType, evaluateLOO,
                         makeProxyBenefitEstimator)
import glob


def mkdir(pathStr):
    if os.path.exists(pathStr):
        pass
    else:
        os.mkdir(pathStr)


def main():
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    # ASTRANBuildPath = ""  # empty when Astran is unavailable.
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    ASTRANBuildPath = ASTRAN_BUILD_PATH  # <repo>/tools/astran/build (vendored)

    benchmarks = ["sqrt",
                  "voter", "arbiter", "cavlc", "div",
                  "int2float", "max", "priority", "sin",
                  "square", "BoomBranchPredictor",
                  "GemminiLoopMatmul", "GemminiLoopConv", "DCache", "BoomRegisterFile", "GemminiMesh", ]
    # benchmarks = ["adder",  "ctrl", "i2c", "multiplier", "router"]
    benchmarks = ["adder"]

    stdType2GSCLArea = loadOrignalGSCL45nmGDS()
    topThr = 5
    ratioThr = 0.05
    cntThr = 30
    # benchmarks = ["tc_008_arthmetic_sin"]
    # ratioThr = -1
    # cntThr = -1

    for benchmarkName in benchmarks:
        startTime = time.time()
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
                runAstranForNetlist(AstranPath=ASTRANBuildPath, gurobiPath=GUROBI_CL,
                                    technologyPath=ASTRAN_TECHNOLOGY,
                                    spiceNetlistPath='../stdCelllib/cellsAstranFriendly.sp',
                                    complexName=oriStdCellType, commandDir='./originalAstranStdCells/')
        stdType2AstranArea = loadAstranGDS()
        astranArea = getArea(cells, stdType2AstranArea)
        print("astranArea=", astranArea)

        # Online-calibrated shrink model for growth benefit estimation
        # (P0-3): observes each finished layout's new/baseline width ratio
        # per cell count, and vetoes growth branches whose predicted
        # benefit is non-positive before they cost an ASTRAN run.
        shrinkModel = ShrinkModel()
        growthBenefitEstimator = makeGrowthBenefitEstimator(
            stdType2AstranArea, shrinkModel)

        # Electrical context per candidate (P1-7): leakage / input
        # capacitance / delay proxy from the liberty file, plus the count
        # of nets the merge internalises (dynamic-power saving proxy).
        # Reported only -- the selection metric stays width-based.
        cellElectricalMetrics = loadCellElectricalMetrics(
            "../stdCelllib/gscl45nm.lib")

        # Delay/power from the liberty LUTs (mini-STA per candidate) and
        # a Yosys re-import for design-level cross-check (user priority).
        cellTimingPower = loadTimingPower("../stdCelllib/gscl45nm.lib")
        libFunctions = loadLibertyFunctions("../stdCelllib/gscl45nm.lib")
        designLibArea = 0.0
        for tmpCell in cells:
            m = cellElectricalMetrics.get(tmpCell.stdCellType.typeName)
            if (m is not None and m["area"] is not None):
                designLibArea += m["area"]
        yosysStat = runYosysStat("../stdCelllib/gscl45nm.lib",
                                 "../benchmark/blif/"+benchmarkName+".blif")
        print("yosys stat cross-check: ",
              compareWithFlowArea(yosysStat, designLibArea))
        ourTypeCounts = {}
        for tmpCell in cells:
            if (tmpCell.stopType):
                continue
            tmpType = tmpCell.stdCellType.typeName
            ourTypeCounts[tmpType] = ourTypeCounts.get(tmpType, 0) + 1
        print("yosys cell-count cross-check: ",
              compareCellCounts(yosysStat, ourTypeCounts))

        # Width proxy (P2 phase 1): learned from the layouts already in
        # this repo.  Report-only by default (LOO ~16% MAPE overestimates
        # compact shapes -- it would have vetoed COMPLEX9); opt into
        # growth pruning via useWidthProxyForGrowth.
        transistorCounts = countTransistorsPerType(
            "../stdCelllib/cellsAstranFriendly.sp")
        widthProxySamples = collectSamples(
            sorted(glob.glob("./outputs/*/")),
            transistorCounts, stdType2AstranArea)
        widthProxy = None
        if (len(widthProxySamples) >= 4):
            widthProxy = WidthProxy().fit(widthProxySamples)
            loo = evaluateLOO(widthProxySamples)
            print("width proxy: n=", loo["n"], " LOO MAPE=",
                  None if loo["mape"] is None else round(loo["mape"], 4),
                  " R2=", loo["r2"])
        if (useWidthProxyForGrowth and widthProxy is not None):
            growthBenefitEstimator = makeProxyBenefitEstimator(
                widthProxy, stdType2AstranArea, transistorCounts)

        clusterSeqs = sortPatternClusterSeqs(clusterSeqs)

        # iteratively to pick the most frequent subgraph and extend them by absorbing their neighbors
        dumpedPaterns = dict()
        detectedPatterns = []

        patternNum = len(clusterSeqs)
        bestSaveArea = 0
        lastSaveGSCLArea = 0
        lastComplexSelection = 0
        targetPatternTrace = ""
        failImproveCnt = 0
        benchmarkFailure = False

        for i in range(0, topThr):
            if (len(clusterSeqs) == 0 or len(clusterSeqs[0].patternClusters) == 0):
                break
            if (len(clusterSeqs[0].patternClusters[0].cellIdsContained) >= 11):
                # Pop the oversized head instead of `continue`: continuing
                # without consuming clusterSeqs[0] re-tests the same pattern
                # every round and burns the whole topThr budget doing nothing.
                clusterSeqs = clusterSeqs[1:]
                continue

            saveArea = 0
            saveGSCLArea = 0
            complexSelection = []
            # Cells already claimed by a candidate counted this round: a
            # design cell cannot be instantiated inside two different
            # complex cells, so overlapping clusters are counted once
            # (countUncoveredClusters), not once per candidate.
            coveredCellIds = set()
            for j in range(0, topThr):
                if (j >= len(clusterSeqs)):
                    break
                tmpClusterSeq = clusterSeqs[j]
                patternTraceId = tmpClusterSeq.patternClusters[0].clusterTypeId
                patternSubgraph = BLIFGraph.subgraph(
                    tmpClusterSeq.patternClusters[0].cellIdsContained)

                # A pattern's trace is its identity: the same pattern can be
                # produced again in a later iteration under a different
                # clusterTypeId.  Skip it outright -- re-dumping it under a new
                # id would double-count its occurrences in the reported area
                # savings, and the area lookup below would then look for a
                # layout for a duplicate id that was never generated.
                if (tmpClusterSeq.patternExtensionTrace in dumpedPaterns.keys()):
                    continue
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
                    gdsPath = outputPath+'/COMPLEX'+str(patternTraceId)+'.gds'
                    spPath = outputPath+'/COMPLEX'+str(patternTraceId)+'.sp'
                    if (astranLayoutIsStale(gdsPath, spPath)):
                        if (len(tmpClusterSeq.patternClusters[0].cellIdsContained) < 11):
                            try:
                                runAstranForNetlist(AstranPath=ASTRANBuildPath, gurobiPath=GUROBI_CL,
                                                    technologyPath=ASTRAN_TECHNOLOGY,
                                                    spiceNetlistPath=outputPath+'/COMPLEX' +
                                                    str(patternTraceId) +
                                                    '.sp',
                                                    complexName='COMPLEX'+str(patternTraceId), commandDir=outputPath)
                                newWidth = loadAstranArea(
                                    outputPath, "COMPLEX"+str(patternTraceId))
                                # A failed LP solve makes ASTRAN read an
                                # all-zero solution and emit a 0 x 0 cell;
                                # counting it would report fake area savings.
                                # Exclude the pattern; one failed cell must
                                # not kill the whole benchmark.
                                if (newWidth <= 0):
                                    print("WARNING :", benchmarkName,
                                          " COMPLEX"+str(patternTraceId),
                                          " has zero width (solver failed); excluding the pattern")
                                    continue
                            except Exception:
                                # ASTRAN could not produce a layout for this
                                # pattern (e.g. every conservative attempt of
                                # autoFlow failed).  Exclude the pattern instead
                                # of failing the whole benchmark, so later
                                # patterns and phase 2 still run.
                                print("WARNING :", benchmarkName,
                                      " COMPLEX"+str(patternTraceId),
                                      " could not be generated; excluding the pattern")
                                continue

                if (benchmarkFailure):
                    break
                exampleCells = []
                for cellId in tmpClusterSeq.patternClusters[0].cellIdsContained:
                    exampleCells.append(cells[cellId])

                oriUnitAstranArea = getArea(exampleCells, stdType2AstranArea)
                oriUnitGSCLArea = getArea(exampleCells, stdType2GSCLArea)
                newUnitAstranArea = loadAstranArea(
                    outputPath, "COMPLEX"+str(patternTraceId))
                if (newUnitAstranArea <= 0):   # a cached 0 x 0 layout counts nothing
                    continue
                shrinkModel.observe(len(exampleCells),
                                    oriUnitAstranArea, newUnitAstranArea)
                # Second metric beside width (P0-4): ASTRAN's own routing
                # congestion, parsed from the cell's log.  Reported always;
                # enforced only when routabilityDensityGate is set.
                rtMetrics = loadCellRoutability(
                    outputPath, "COMPLEX"+str(patternTraceId))
                if (rtMetrics is not None):
                    print("routability ", "COMPLEX"+str(patternTraceId),
                          ": ", rtMetrics.asDict())
                if (rtMetrics is not None
                        and routabilityDensityGate is not None
                        and rtMetrics.rtDensity > routabilityDensityGate):
                    print("WARNING :", benchmarkName,
                          " COMPLEX"+str(patternTraceId),
                          " rtDensity", rtMetrics.rtDensity,
                          "> gate", routabilityDensityGate,
                          "; excluding the pattern")
                    continue
                elecMetrics = patternElectricalMetrics(
                    exampleCells, cellElectricalMetrics)
                print("electrical ", "COMPLEX"+str(patternTraceId),
                      ": ", elecMetrics)
                timingMetrics = patternTimingPower(
                    exampleCells, cellTimingPower, cellElectricalMetrics)
                print("timing/power ", "COMPLEX"+str(patternTraceId),
                      ": ", timingMetrics)
                if (widthProxy is not None):
                    proxyWidth = widthProxy.predict(
                        len(exampleCells),
                        sum(transistorCounts.get(
                            c.stdCellType.typeName, 0)
                            for c in exampleCells),
                        oriUnitAstranArea)
                    print("width proxy  COMPLEX"+str(patternTraceId),
                          ": predicted=", round(proxyWidth, 3),
                          " actual=", newUnitAstranArea)
                # Structural layout sanity (P2 phase 0): degenerate /
                # wrong-height / off-grid / label-missing layouts are
                # unambiguous breakage and are excluded when gated.
                sanityReport = checkLayout(
                    os.path.join(outputPath, "COMPLEX"+str(patternTraceId)+".gds"),
                    logPath=os.path.join(
                        outputPath, "COMPLEX"+str(patternTraceId)+".Astranlog"))
                if (not sanityReport.ok()):
                    print("layout sanity ", "COMPLEX"+str(patternTraceId),
                          ": ", sanityReport.asDict())
                if (layoutSanityGate and not sanityReport.ok()):
                    print("WARNING :", benchmarkName,
                          " COMPLEX"+str(patternTraceId),
                          " failed layout sanity; excluding the pattern")
                    continue
                # Liberty fragment for the generated cell (area from the
                # layout width, leakage/caps from the base lib, timing and
                # power from the LUT mini-STA sweep): the data a downstream
                # flow needs to reuse the cell.  Written on change only.
                libText, libReport = generateComplexLiberty(
                    tmpClusterSeq, "COMPLEX"+str(patternTraceId),
                    newUnitAstranArea, cellTimingPower,
                    cellElectricalMetrics, libFunctions)
                libPath = outputPath+"/COMPLEX"+str(patternTraceId)+".lib"
                if ((not os.path.exists(libPath))
                        or open(libPath).read() != libText):
                    with open(libPath, 'w') as libFh:
                        libFh.write(libText)
                if (oriUnitAstranArea-newUnitAstranArea > 0):
                    uniqueClusters = countUncoveredClusters(
                        tmpClusterSeq.patternClusters, coveredCellIds)
                    if (uniqueClusters == 0):
                        continue
                    complexSelection.append(("COMPLEX"+str(patternTraceId), uniqueClusters, len(
                        tmpClusterSeq.patternClusters[0].cellIdsContained), tmpClusterSeq.patternExtensionTrace))
                    saveArea += (oriUnitAstranArea-newUnitAstranArea) * \
                        uniqueClusters
                    saveGSCLArea += (oriUnitGSCLArea-newUnitAstranArea) * \
                        uniqueClusters

            if (benchmarkFailure):
                break

            print("saveArea=", saveArea, " / ", saveArea/astranArea*100, "%")
            if (saveArea > bestSaveArea):
                bestSaveArea = saveArea
                lastSaveGSCLArea = saveGSCLArea
                lastComplexSelection = complexSelection
                fileResult = open(outputPath+"/bestRecord-"+benchmarkName, 'w')
                print(bestSaveArea, " <- compared to Astran GDS area",
                      file=fileResult)
                print(bestSaveArea/astranArea*100,
                      "% <- compared to Astran GDS area", file=fileResult)
                print(lastSaveGSCLArea,
                      " <- compared to GSCL GDS area", file=fileResult)
                print(lastSaveGSCLArea/oriArea*100,
                      "% <- compared to GSCL GDS area", file=fileResult)
                print(
                    "The generated complex cells are (name, clusterNum, cellNumInOneCluster, patternCode):", file=fileResult)
                for complexName in lastComplexSelection:
                    print(complexName, file=fileResult)
                print("\n runtime:", time.time() -
                      startTime, " (s)", file=fileResult)
                fileResult.close()
            else:
                break

            # Beam growth (P0-3): grow the first growBeamWidth heads per
            # round instead of only the top one -- the candidate queue is
            # the beam.  Each grown branch is pre-screened by the benefit
            # estimator, so predicted-loss shapes (the COMPLEX10 pattern:
            # -56.05 um^2 on adder) never cost an ASTRAN run.
            grownHeads = 0
            for headSeq in list(clusterSeqs):
                if (grownHeads >= growBeamWidth):
                    break
                if (len(headSeq.patternClusters) == 0):
                    clusterSeqs.remove(headSeq)
                    continue
                headSize = len(headSeq.patternClusters[0].cellIdsContained)
                if (grownHeads == 0):
                    assert(ratioThr > 0)
                    if (headSize*len(headSeq.patternClusters) < ratioThr * len(cells)
                            and len(headSeq.patternClusters) < cntThr):
                        break
                if (headSize >= 10):
                    # a grown 11+-cell candidate is excluded at layout time
                    # anyway; growing it here would only churn the pool
                    clusterSeqs.remove(headSeq)
                    continue
                newSeqOfClusters, patternNum = growASeqOfClusters(
                    BLIFGraph, headSeq, clusterNum, patternNum,
                    paintPattern=True, benefitEstimator=growthBenefitEstimator)
                clusterSeqs.remove(headSeq)
                clusterSeqs += newSeqOfClusters
                grownHeads += 1
                if (len(newSeqOfClusters) > 1):
                    # Export the grown netlist under the grown pattern's own
                    # id.  len(clusterSeqs) collides with ids already used by
                    # dumped patterns and silently overwrites their .sp files
                    # (observed: the grown 6-cell pattern overwrote
                    # COMPLEX9.sp while COMPLEX9.gds remained the 4-cell
                    # layout).
                    exportSpiceNetlist(newSeqOfClusters[0], subckts,
                                       newSeqOfClusters[0].patternClusters[0].clusterTypeId,
                                       outputPath)

            clusterSeqs = removeEmptySeqsAndDisableClusters(clusterSeqs)
            clusterSeqs = sortPatternClusterSeqs(clusterSeqs)

        if (benchmarkFailure):
            continue

        countedSet = set()
        recordPatternDetails = []
        detectedPatterns.reverse()
        # bestRecord-seperate is opened only at the end: opening it with 'w'
        # up front erases the previous record, and a crash mid-loop would
        # leave an empty file (the writes below happen after the loop anyway).
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
            bestSaveArea = 0
            lastSaveGSCLArea = 0
            lastComplexSelection = 0

            for i in range(0, 10):
                print("searching for ", targetPatternTrace)
                if (len(clusterSeqs) == 0 or len(clusterSeqs[0].patternClusters) == 0):
                    break
                if (len(clusterSeqs[0].patternClusters[0].cellIdsContained) >= 11):
                    # Pop, don't just continue: re-testing the same oversized
                    # head would burn the whole iteration budget (see the
                    # phase-1 loop for the same pattern).
                    clusterSeqs = clusterSeqs[1:]
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
                        # grown beyond the dumped patterns: nothing to record
                        break
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

                    # print(bestSaveArea, " <- compared to Astran GDS area",
                    #       file=fileResult)
                    # print(bestSaveArea/astranArea*100,
                    #       "% <- compared to Astran GDS area", file=fileResult)
                    # print(lastSaveGSCLArea,
                    #       " <- compared to GSCL GDS area", file=fileResult)
                    # print(lastSaveGSCLArea/oriArea*100,
                    #       "% <- compared to GSCL GDS area", file=fileResult)
                    # print(
                    #     "The generated complex cells are (name, clusterNum, cellNumInOneCluster, patternCode):", file=fileResult)

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

                newSeqOfClusters, patternNum = growASeqOfClusters_BasedOn(
                    BLIFGraph, clusterSeq, clusterNum, patternNum,  paintPattern=True, targetPatternTrace=targetPatternTrace)

                # No netlist export here: phase 2 only computes the per-pattern
                # records, and exporting the grown netlist under a patternNum-
                # derived id collides with ids already on disk (it silently
                # overwrote COMPLEX1.sp with another pattern in testing).

                clusterSeqs = clusterSeqs[1:]
                clusterSeqs += newSeqOfClusters
                clusterSeqs = removeEmptySeqsAndDisableClusters(clusterSeqs)
                clusterSeqs = sortPatternClusterSeqs(clusterSeqs)

        recordPatternDetails = sorted(recordPatternDetails,
                                      key=lambda x: -x[0])
        fileResult = open(
            outputPath+"/bestRecord-seperate"+benchmarkName, 'w')
        print("| designOverallArea | saveArea | saveRatio | patternCnt | patternSize |"
              " patternCoverage | patternName | patternCode |",  file=fileResult)
        for saveArea, saveRatio, patternCnt, patternSize, patternCoverage, patternName, patternCode in recordPatternDetails:
            print('|', oriArea, '|', saveArea, '|', saveRatio, '|', patternCnt, '|', patternSize, '|',
                  patternCoverage, '|', patternName, '|', patternCode, '|', file=fileResult)
        fileResult.close()


if __name__ == '__main__':
    matplotlib.use("Pdf")
    main()
