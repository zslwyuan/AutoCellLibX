"""Initial clustering (layer: seeding).

Extracted from blif_preproc.py (AST-verbatim): group root cells by
canonical pattern code into DesignPatternClusterSeq candidates ordered
by (cluster count x cluster size); the _BasedOn variant replays one
specific trace for phase-2 records.  singleOutputSeeds implements the
synthesis-reuse seed filter (AUDIT 5.27).
"""

from blif_graph_util import (DesignPatternCluster,
                           DesignPatternClusterSeq,
                           sortPatternClusterSeqs)
from global_variables import bypassTypes
from core.encoding import (canonical_pattern_code, escape_output_count,
                           extract_and_encode_subgraph_tree)


def heuristic_label_initial_clusters(BLIFGraph, cells, netlist, singleOutputSeeds=False):

    treeDepth = 1

    pattern2RootCells = dict()
    for cell in cells:
        shouldBypass = False
        for typeKey in bypassTypes:
            if (cell.stdCellType.typeName.find(typeKey) >= 0):
                shouldBypass = True
                break
        if (shouldBypass):
            continue
        tree, code = extract_and_encode_subgraph_tree(cells, cell.id, treeDepth)
        if (len(tree) < 2):
            continue
        if (singleOutputSeeds and escape_output_count(cells, tree) != 1):
            continue
        codeStr = canonical_pattern_code(code)
        if (codeStr.find("bool-") >= 0):
            continue
        if (not codeStr in pattern2RootCells.keys()):
            pattern2RootCells[codeStr] = []
        pattern2RootCells[codeStr].append(cell.id)

    pattern2Cnt = []
    for key in pattern2RootCells.keys():
        pattern2Cnt.append((key, len(pattern2RootCells[key])))
    sorted_by_second = sorted(pattern2Cnt, key=lambda tup: -tup[1])
    print("top pattern types: ", sorted_by_second[:30])

    patternToBeLabeled = []
    labelId = 0
    labeledCnt = 0
    clusterCellsCnt = 0

    initialClusterSeqs = []
    for tmpType in sorted_by_second[:30]:
        patternToBeLabeled.append(tmpType[0])
        newSeq = DesignPatternClusterSeq(tmpType[0])
        for cellId in pattern2RootCells[tmpType[0]]:
            BLIFGraph.nodes()[cellId]['nodeLabel'] = labelId
            tree, code = extract_and_encode_subgraph_tree(   # color the nodes in a pattern
                cells, cellId, treeDepth, labeledCnt)
            if (tree is None):
                continue
            code = canonical_pattern_code(code)
            newCluster = DesignPatternCluster(
                labeledCnt, code, cells, tree, labelId)
            for cellId in tree:
                cells[cellId].setCluster(newCluster)

            newSeq.addCluster(newCluster)
            labeledCnt += 1
            clusterCellsCnt += len(tree)
        if (len(newSeq.patternClusters) > 0):
            initialClusterSeqs.append(newSeq)
            labelId += 1
        else:
            del newSeq

    resSeqs = sortPatternClusterSeqs(initialClusterSeqs)

    print("labeled ", labeledCnt, " nodes (", labeledCnt /
          BLIFGraph.number_of_nodes()*100, "%)")
    print("clustered ", clusterCellsCnt, " nodes (", clusterCellsCnt /
          BLIFGraph.number_of_nodes()*100, "%)")

    return resSeqs, labeledCnt


def heuristic_label_initial_clusters_based_on(BLIFGraph, cells, netlist, targetPatternTrace, singleOutputSeeds=False):

    treeDepth = 1

    pattern2RootCells = dict()
    for cell in cells:
        shouldBypass = False
        for typeKey in bypassTypes:
            if (cell.stdCellType.typeName.find(typeKey) >= 0):
                shouldBypass = True
                break
        if (shouldBypass):
            continue
        tree, code = extract_and_encode_subgraph_tree(cells, cell.id, treeDepth)
        if (len(tree) < 2):
            continue
        if (singleOutputSeeds and escape_output_count(cells, tree) != 1):
            continue
        codeStr = canonical_pattern_code(code)
        if (codeStr.find("bool-") >= 0):
            continue
        if (targetPatternTrace.find(codeStr) != 0):
            continue
        if (not codeStr in pattern2RootCells.keys()):
            pattern2RootCells[codeStr] = []
        pattern2RootCells[codeStr].append(cell.id)

    pattern2Cnt = []
    for key in pattern2RootCells.keys():
        pattern2Cnt.append((key, len(pattern2RootCells[key])))
    sorted_by_second = sorted(pattern2Cnt, key=lambda tup: -tup[1])
    print("top pattern types: ", sorted_by_second[:30])

    patternToBeLabeled = []
    labelId = 0
    labeledCnt = 0
    clusterCellsCnt = 0

    initialClusterSeqs = []
    for tmpType in sorted_by_second[:30]:
        patternToBeLabeled.append(tmpType[0])
        newSeq = DesignPatternClusterSeq(tmpType[0])
        for cellId in pattern2RootCells[tmpType[0]]:
            BLIFGraph.nodes()[cellId]['nodeLabel'] = labelId
            tree, code = extract_and_encode_subgraph_tree(   # color the nodes in a pattern
                cells, cellId, treeDepth, labeledCnt)
            if (tree is None):
                continue
            code = canonical_pattern_code(code)
            newCluster = DesignPatternCluster(
                labeledCnt, code, cells, tree, labelId)
            for cellId in tree:
                cells[cellId].setCluster(newCluster)

            newSeq.addCluster(newCluster)
            labeledCnt += 1
            clusterCellsCnt += len(tree)
        if (len(newSeq.patternClusters) > 0):
            initialClusterSeqs.append(newSeq)
            labelId += 1
        else:
            del newSeq

    resSeqs = sortPatternClusterSeqs(initialClusterSeqs)

    print("labeled ", labeledCnt, " nodes (", labeledCnt /
          BLIFGraph.number_of_nodes()*100, "%)")
    print("clustered ", clusterCellsCnt, " nodes (", clusterCellsCnt /
          BLIFGraph.number_of_nodes()*100, "%)")

    return resSeqs, labeledCnt
