"""The mining pipeline (layer: pipeline).

Extracted verbatim from main.py (AST move): the full benchmark loop --
initial clustering, greedy/beam growth, SPICE export, ASTRAN layout,
area / electrical / timing / routability / reuse evaluation, and the
phase-2 per-pattern records.  main.py is now a thin CLI that builds a
FlowConfig and calls ``runPipeline``; the GUI (flow_core) is the next
consumer to migrate onto it (AUDIT/ARCHITECTURE note).
"""

import os
import time
import glob
import matplotlib
from core.log import get_flow_logger

_flowLog = get_flow_logger()

from blif_preproc import *
from blif_pattern_growth import *
from spice import *
from core.external import *
from core.evaluate import *
from llm_hint_provider import getHintProvider


def mkdir(pathStr):
    if os.path.exists(pathStr):
        pass
    else:
        os.mkdir(pathStr)




class PipelineHooks(object):
    """Observer interface for runPipeline (GUI / experiments / tests).

    All methods are no-ops by default: with ``hooks=None`` the pipeline
    behaves exactly like the CLI.  ``run_layout`` lets a host supply its
    own layout runner (the GUI needs Popen + CREATE_NO_WINDOW + custom
    geometry); returning ``None`` means "excluded this pattern".
    ``check_cancel`` should raise to abort the run.
    """

    def stage(self, name, status, message="", extra=None):
        pass

    def log(self, message, level="info"):
        pass

    def pattern(self, info):
        pass

    def metric(self, info):
        pass

    def record(self, kind, info):
        pass

    def check_cancel(self):
        pass

    def run_layout(self, pattern_trace_id):
        return None

    def result(self, key, value):
        pass


def runPipeline(cfg, hooks=None):

    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    # Dual-mode coexistence (AUDIT 5.26): AUTOCELL_REUSE_MODE=1 runs the
    # mining with the synthesis-reuse constraints (single-output, simple
    # functions, internalize-only growth) into a separate outputs/
    # directory, leaving the physical-mode snapshots untouched.
    reuseMode = cfg.reuseMode
    if (reuseMode):
        global requireReuseEligible
        requireReuseEligible = True
    # ASTRANBuildPath = ""  # empty when Astran is unavailable.
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    ASTRANBuildPath = cfg.astranBuildPath or ASTRAN_BUILD_PATH  # vendored

    benchmarks = ["sqrt",
                  "voter", "arbiter", "cavlc", "div",
                  "int2float", "max", "priority", "sin",
                  "square", "BoomBranchPredictor",
                  "GemminiLoopMatmul", "GemminiLoopConv", "DCache", "BoomRegisterFile", "GemminiMesh", ]
    # benchmarks = ["adder",  "ctrl", "i2c", "multiplier", "router"]
    benchmarks = cfg.benchmarks

    stdType2GSCLArea = loadOrignalGSCL45nmGDS()
    topThr = cfg.topThr
    ratioThr = 0.05
    cntThr = 30
    # benchmarks = ["tc_008_arthmetic_sin"]
    # ratioThr = -1
    # cntThr = -1

    for benchmarkName in benchmarks:
        startTime = time.time()
        ratioThr = cfg.ratioThrFor(benchmarkName)
        cntThr = cfg.cntThr

        print("=================================================================================\n",
              benchmarkName, "\n=================================================================================\n")
        # load liberty/spice/design BLIF
        subckts = load_spice_subcircuits(cfg.spiceLib)
        BLIFGraph, cells, netlist, stdCellTypesForFeature, dataset, maxLabelIndex, clusterSeqs, clusterNum = loadDataAndPreprocess(
            libFileName=cfg.liberty, blifFileName=cfg.blifDir+"/"+benchmarkName+".blif", startTime=startTime, singleOutputSeeds=reuseMode)
        oriArea = getArea(cells, stdType2GSCLArea)
        print("originalArea=", oriArea)

        outputPath = cfg.outputDir(benchmarkName)
        mkdir(outputPath)

        if (ASTRANBuildPath != ""):
            for oriStdCellType in stdCellTypesForFeature:
                if (oriStdCellType.find("bool") >= 0):
                    continue
                if (os.path.exists('./originalAstranStdCells/'+oriStdCellType+'.gds')):
                    continue
                runAstranForNetlist(AstranPath=ASTRANBuildPath, gurobiPath=GUROBI_CL,
                                    technologyPath=ASTRAN_TECHNOLOGY,
                                    spiceNetlistPath=cfg.spiceLib,
                                    complexName=oriStdCellType, commandDir='./originalAstranStdCells/')
        stdType2AstranArea = loadAstranGDS()
        astranArea = getArea(cells, stdType2AstranArea)
        _flowLog.info("astranArea=%.2f", astranArea)
        if (hooks is not None):
            hooks.result("cells", cells)
            hooks.result("BLIFGraph", BLIFGraph)
            hooks.result("clusterSeqs", clusterSeqs)
            hooks.result("stdType2GSCLArea", stdType2GSCLArea)
            hooks.result("stdType2AstranArea", stdType2AstranArea)
            hooks.result("oriArea", oriArea)
            hooks.result("astranArea", astranArea)
            hooks.stage("parse", "done", "parsed %d cells" % len(cells))

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
        cellElectricalMetrics = loadCellElectricalMetrics(cfg.liberty)

        # Delay/power from the liberty LUTs (mini-STA per candidate) and
        # a Yosys re-import for design-level cross-check (user priority).
        cellTimingPower = loadTimingPower(cfg.liberty)
        libFunctions = loadLibertyFunctions(cfg.liberty)
        designLibArea = 0.0
        for tmpCell in cells:
            m = cellElectricalMetrics.get(tmpCell.stdCellType.typeName)
            if (m is not None and m["area"] is not None):
                designLibArea += m["area"]
        yosysStat = runYosysStat(cfg.liberty,
                                 cfg.blifDir+"/"+benchmarkName+".blif")
        _flowLog.info("yosys stat cross-check: %s",
                      compareWithFlowArea(yosysStat, designLibArea))
        ourTypeCounts = {}
        for tmpCell in cells:
            if (tmpCell.stopType):
                continue
            tmpType = tmpCell.stdCellType.typeName
            ourTypeCounts[tmpType] = ourTypeCounts.get(tmpType, 0) + 1
        _flowLog.info("yosys cell-count cross-check: %s",
                      compareCellCounts(yosysStat, ourTypeCounts))

        # Width proxy (P2 phase 1): learned from the layouts already in
        # this repo.  Report-only by default (LOO ~16% MAPE overestimates
        # compact shapes -- it would have vetoed COMPLEX9); opt into
        # growth pruning via useWidthProxyForGrowth.
        transistorCounts = countTransistorsPerType(cfg.spiceLib)
        # Width-proxy training pipeline: load the persisted model when
        # fresh, else retrain from the layout corpus and persist.
        widthProxy, proxyReport = trainOrLoadWidthProxy(
            sorted(glob.glob("./outputs/*/")), transistorCounts,
            stdType2AstranArea)
        if (widthProxy is not None):
            _flowLog.info("width proxy: n=%s source=%s LOO MAPE=%s",
                          proxyReport.get("n"), proxyReport.get("source"),
                          None if proxyReport.get("mape") is None
                          else round(proxyReport["mape"], 4))
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
            if (hooks is not None):
                hooks.check_cancel()
                hooks.stage("mine", "running",
                            "iteration %d/%d" % (i + 1, topThr),
                            (i, topThr))
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
                if (hooks is not None):
                    hooks.check_cancel()
                    hooks.log("pattern #%d '%s' x%d (size=%d)"
                              % (patternTraceId,
                                 tmpClusterSeq.patternExtensionTrace,
                                 len(tmpClusterSeq.patternClusters),
                                 len(tmpClusterSeq.patternClusters[0].cellIdsContained)))
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

                # Advisory layout hints (P2 stage 3): an offline/LLM hint
                # provider annotates the grown netlist before it costs an
                # ASTRAN run.  Report-only and gated by cfg.hintMode
                # (default "off" -> byte-identical default runs).
                if (cfg.hintMode != "off"):
                    hintSpPath = outputPath+'/COMPLEX'+str(patternTraceId)+'.sp'
                    if (os.path.exists(hintSpPath)):
                        hintProvider = getHintProvider(mode=cfg.hintMode)
                        if (hintProvider is not None):
                            with open(hintSpPath, 'r', errors="ignore") as spFh:
                                hints = hintProvider.suggestHints(
                                    "COMPLEX"+str(patternTraceId),
                                    spFh.read())
                            if (hints):
                                _flowLog.info(
                                    "layout hints COMPLEX%d: %s",
                                    patternTraceId,
                                    ", ".join(
                                        "%s %s=%.2f[%s]"
                                        % (h.kind, h.target, h.value, h.source)
                                        for h in hints))

                # if ASTRAN is available (or a host layout runner is
                # provided), run it to get the layout and area evaluation
                if (ASTRANBuildPath != "" or hooks is not None):
                    if (hooks is not None):
                        newWidth = hooks.run_layout(patternTraceId)
                        if (newWidth is None):
                            print("WARNING :", benchmarkName,
                                  " COMPLEX"+str(patternTraceId),
                                  " layout hook returned None; excluding the pattern")
                            continue
                    gdsPath = outputPath+'/COMPLEX'+str(patternTraceId)+'.gds'
                    spPath = outputPath+'/COMPLEX'+str(patternTraceId)+'.sp'
                    if (hooks is not None):
                        pass  # layout already produced by the hook
                    elif (astranLayoutIsStale(gdsPath, spPath)):
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
                # Synthesis-reuse eligibility (AUDIT 5.25): abc only uses
                # single-output, simple-function cells.  Reported always;
                # enforced when requireReuseEligible is set.
                reuseInfo = reuseEligible(exampleCells, libFunctions)
                print("reuse ", "COMPLEX"+str(patternTraceId), ": ",
                      reuseInfo)
                if (requireReuseEligible and not reuseInfo["eligible"]):
                    print("WARNING :", benchmarkName,
                          " COMPLEX"+str(patternTraceId),
                          " not synthesis-reuse eligible (",
                          reuseInfo["reason"], "); excluding the pattern")
                    continue
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
            if (hooks is not None):
                hooks.metric({"benchmark": benchmarkName, "iteration": i,
                              "save_area": saveArea,
                              "ratio": saveArea/astranArea*100 if astranArea else 0.0,
                              "best": bestSaveArea})
            if (saveArea > bestSaveArea):
                bestSaveArea = saveArea
                lastSaveGSCLArea = saveGSCLArea
                lastComplexSelection = complexSelection
                if (hooks is not None):
                    hooks.record("best", {
                        "benchmark": benchmarkName,
                        "path": outputPath+"/bestRecord-"+benchmarkName,
                        "save_area": saveArea,
                        "ratio": saveArea/astranArea*100 if astranArea else 0.0,
                        "selection": list(complexSelection)})
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
                newSeqOfClusters, patternNum = grow_sequence_of_clusters(
                    BLIFGraph, headSeq, clusterNum, patternNum,
                    paintPattern=True, benefitEstimator=growthBenefitEstimator,
                    internalizeOnly=reuseMode)
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
        if (hooks is not None):
            hooks.stage("phase2", "running", "%d records" % len(detectedPatterns))
        for targetPatternTrace in detectedPatterns:
            if (hooks is not None):
                hooks.check_cancel()
            if (targetPatternTrace in countedSet):
                continue

            BLIFGraph, cells, netlist, stdCellTypesForFeature, dataset, maxLabelIndex, clusterSeqs, clusterNum = loadDataAndPreprocess(
                libFileName=cfg.liberty, blifFileName=cfg.blifDir+"/"+benchmarkName+".blif", startTime=startTime, bypassInitialCluster=True)

            clusterSeqs, clusterNum = heuristic_label_initial_clusters_based_on(
                BLIFGraph, cells, netlist, targetPatternTrace, singleOutputSeeds=reuseMode)
            endTime = time.time()
            print("heuristic_label_initial_clusters done. time esclaped: ",
                  endTime-startTime)

            oriArea = getArea(cells, stdType2GSCLArea)
            print("originalArea=", oriArea)

            outputPath = "./outputs/"+benchmarkName+"/"
            mkdir(outputPath)

            stdType2AstranArea = loadAstranGDS()
            astranArea = getArea(cells, stdType2AstranArea)
            _flowLog.info("astranArea=%.2f", astranArea)

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

                newSeqOfClusters, patternNum = grow_sequence_of_clusters_based_on(
                    BLIFGraph, clusterSeq, clusterNum, patternNum, paintPattern=True, targetPatternTrace=targetPatternTrace, internalizeOnly=reuseMode)

                # No netlist export here: phase 2 only computes the per-pattern
                # records, and exporting the grown netlist under a patternNum-
                # derived id collides with ids already on disk (it silently
                # overwrote COMPLEX1.sp with another pattern in testing).

                clusterSeqs = clusterSeqs[1:]
                clusterSeqs += newSeqOfClusters
                clusterSeqs = removeEmptySeqsAndDisableClusters(clusterSeqs)
                clusterSeqs = sortPatternClusterSeqs(clusterSeqs)

        if (hooks is not None):
            hooks.result("recordPatternDetails", recordPatternDetails)
            hooks.result("bestSaveArea", bestSaveArea)
            hooks.result("runtime", time.time() - startTime)
            hooks.stage("mine", "done", "best saveArea=%.2f" % bestSaveArea)
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
