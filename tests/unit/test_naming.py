"""Naming reform (direct rename, no aliases): the legacy camelCase names
must not appear anywhere in flow/gui/tests.

Exceptions that legitimately keep camelCase: Qt signal/method names (Qt
convention), ASTRAN C++ identifiers quoted in comments, and the tokens of
the bestRecord-* file format (see pipeline.py's protected literals)."""
import pathlib
import re

LEGACY = [
    # --- batch 1: module file names ---
    "BLIFPreProc", "BLIFGraphUtil", "BLIFPatternGrowth", "GDSIIAnalysis",
    "globalVariables", "resultAnalysisCountTops", "replay_seperateadder",
    # --- batch 1 (previous round): core entry points ---
    "loadLibertyFile", "loadBoolGateFromBLIF",
    "genGraphFromLibertyAndBLIF", "loadSpiceSubcircuits",
    "extractAndEncodeSubgraph_Tree", "canonicalPatternCode",
    "escapeOutputCount", "heuristicLabelSomeNodesAndGetInitialClusters",
    "growASeqOfClusters", "getFlowLogger", "setFlowLogLevel",
    # --- batch 2: entry-point functions ---
    "loadDataAndPreprocess", "convertBLIFGraphIntoDataset", "getArea",
    "exportSpiceNetlist", "loadAstranGDS", "loadOrignalGSCL45nmGDS",
    "loadAstranArea", "runAstranForNetlist", "buildAstranCommands",
    "astranLayoutIsStale", "runPipeline",
    "drawColorfulFigureForGraphWithAttributes", "sortPatternClusterSeqs",
    "removeEmptySeqsAndDisableClusters", "countUncoveredClusters",
    "checkLayout", "reuseEligible", "generateComplexLiberty",
    "loadLibertyFunctions", "loadTimingPower", "loadCellElectricalMetrics",
    "loadCellRoutability", "parseAstranLogRoutability",
    "patternElectricalMetrics", "patternTimingPower",
    "countTransistorsPerType", "trainOrLoadWidthProxy",
    "makeGrowthBenefitEstimator", "makeProxyBenefitEstimator",
    "findYosys", "runYosysStat", "parseStatJson", "compareWithFlowArea",
    "compareCellCounts", "buildExtendedLiberty", "runYosysMappedArea",
    "compareMappedArea", "evaluateDesignSavings", "generatePortOrders",
    "writePortOrderVariants", "parseSubcktHeader", "evaluatePortOrderVariants",
    "getPdk", "listPdks", "pdkGeometryDict", "multiRowVariant",
    "legacyPatternCode", "canonicalizationImpact", "findStat",
    "solveLpWithCpSat", "solveCpSat", "getHintProvider", "suggestHints",
    "suggestHintsBatch", "defaultCachePath", "hintCacheKey",
    "parseSpiceSubckt", "findSeriesChains", "buildSmtModel", "placeCell",
    "compareWithAstran", "astranWidthFromLog", "loadCellGeometry",
    "cellPinAccessibility", "renamePrefix", "replaceInputPin",
    "addInterface", "addInternalSignal", "estimateShrink", "estimateBenefit",
    "evaluateLOO", "saveWidthProxy", "loadWidthProxy",
    "widthProxyModelStale", "collectSamples", "parseTraceTypes",
    "interfaceOutputCount", "outputFunctions", "functionComplexity",
    "functionToVerilog", "verilogDesignForFunction", "libertyPinName",
    "parseSpiceExampleCells", "rebuildClusterFromSpice",
    "generateLibertyForSpiceFile", "stageDelaySlew", "stageEnergy", "asDict",
    # --- batch 2: data-model attributes & flow globals ---
    "patternExtensionTrace", "patternClusters", "cellIdsContained",
    "cellsContained", "clusterTypeId", "stdCellType", "typeName",
    "stopType", "predCell", "succCells", "inputNets", "outputNets",
    "dumpedPaterns", "stdType2GSCLArea", "stdType2AstranArea",
    "topThr", "ratioThr", "cntThr", "growBeamWidth",
    "useWidthProxyForGrowth", "routabilityDensityGate", "layoutSanityGate",
    "requireReuseEligible", "bypassTypes", "BLIFGraph", "ASTRANBuildPath",
    "clusterSeqs", "bestSaveArea", "complexSelection",
    "recordPatternDetails", "coveredCellIds", "exampleCells", "hintMode",
    "internalizeOnly", "singleOutputSeeds", "bypassInitialCluster",
]


def test_no_legacy_names_in_code():
    root = pathlib.Path(__file__).resolve().parents[2]
    hits = []
    for path in list((root / "flow").rglob("*.py")) \
            + list((root / "gui").rglob("*.py")) \
            + list((root / "tests").rglob("*.py")):
        if path.name in ("test_naming.py",       # the LEGACY list lives here
                          "gnn_model.py",          # dead TF experiment
                          "blif_gnn_training.py"):  # (cannot even import)
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in LEGACY:
            if re.search(r"(?<![A-Za-z0-9_])" + name + r"(?![A-Za-z0-9_])",
                         text):
                hits.append("%s: %s" % (path.name, name))
    assert not hits, hits
