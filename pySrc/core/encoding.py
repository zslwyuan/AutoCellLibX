"""Pattern encoding (layer: encoding).

Extracted from BLIFPreProc.py: ``extractAndEncodeSubgraph_Tree`` builds
the BFS type-name code for a root cell; ``canonicalPatternCode`` makes
the identity order-invariant (children sorted after the root, AUDIT
5.18/P0-1); ``escapeOutputCount`` counts a seed's escaping outputs
(synthesis-reuse mode, AUDIT 5.27).
"""

from globalVariables import bypassTypes


def extractAndEncodeSubgraph_Tree(cells, rootNode, depthLimit=2, clusterId=None):
    depths = [0]
    tree = [rootNode]
    encodes = [cells[rootNode].stdCellType.typeName]
    Que = [rootNode]
    head = 0
    while (head < len(tree)):
        curNode = cells[Que[head]]
        curDepth = depths[head]
        if (curDepth >= depthLimit):
            break
        for inputNet in curNode.inputNets:
            if (not inputNet.predCell is None):
                shouldBypass = False
                for typeKey in bypassTypes:
                    if (inputNet.predCell.stdCellType.typeName.find(typeKey) >= 0):
                        shouldBypass = True
                        break
                if ((not shouldBypass)):
                    depths.append(curDepth+1)
                    Que.append(inputNet.predCell.id)
                    if (not inputNet.predCell.id in tree):
                        tree.append(inputNet.predCell.id)
                        encodes.append(inputNet.predCell.stdCellType.typeName)
        head += 1

    if (not clusterId is None):
        for cellId in tree:
            if (cells[cellId].clusterId >= 0):
                return None, None
        for cellId in tree:
            cells[cellId].setClusterId(clusterId)

    return tree, encodes


def canonicalPatternCode(code):
    """Canonical pattern-code string for a raw encode list.

    ``extractAndEncodeSubgraph_Tree`` appends children in input-net
    enumeration order, so two structurally identical instances whose nets
    enumerate in different orders used to get different strings and were
    split into separate groups (frequency under-counted).  Keep the root
    first and sort the children.  This string is the pattern's identity, so
    every consumer -- initial grouping, cluster traces, and the prefix match
    in ``heuristicLabelSomeNodesAndGetInitialClusters_BasedOn`` -- must build
    it through this helper.  (The paired ``tree``/``code`` lists returned by
    the encoder are intentionally left in BFS order.)
    """
    canon = code[:1] + sorted(code[1:])
    return str(canon).replace(
        "\'", "").replace("\\", "").replace("\"", "").replace(" ", "")


def escapeOutputCount(cells, tree):
    """Number of escaping member output pins of a seed tree (== the
    complex cell's output pins): a member output pin whose loads are not
    all inside the tree.  Used by the single-output seed filter of the
    synthesis-reuse mode (AUDIT 5.27)."""
    inside = set(tree)
    count = 0
    for cellId in tree:
        for outNet in cells[cellId].outputNets:
            if (len(outNet.succCells) == 0
                    or not all(s.id in inside for s in outNet.succCells)):
                count += 1
    return count
