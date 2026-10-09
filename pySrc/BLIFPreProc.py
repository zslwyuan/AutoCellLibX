"""Shim (ARCHITECTURE): readers live in core/parse, encoding in
core/encoding, seeding in core/seeding.  This module keeps the
orchestration and GNN-dataset helpers (loadDataAndPreprocess,
convertBLIFGraphIntoDataset, getArea) and re-exports the rest for the
older consumers (gui, tests, pipeline).
"""

import os
import blifparser.blifparser as blifparser
from globalVariables import *
from BLIFGraphUtil import *
from core.seeding import (heuristicLabelSomeNodesAndGetInitialClusters,
                          heuristicLabelSomeNodesAndGetInitialClusters_BasedOn)
from core.encoding import (extractAndEncodeSubgraph_Tree,
                           canonicalPatternCode, escapeOutputCount)
from core.parse import (loadLibertyFile, loadBoolGateFromBLIF,
                        genGraphFromLibertyAndBLIF)
import networkx as nx
import numpy as np
import networkx as nx
import time
from liberty.parser import parse_liberty
class S2VGraph(object):
    def __init__(self, g, label, node_tags=None, node_features=None):
        '''
            g: a networkx graph
            label: an integer graph label
            node_tags: a list of integer node tags
            node_features: a torch float tensor, one-hot representation of the tag that is used as input to neural nets
            edge_mat: a torch long tensor, contain edge list, will be used to create torch sparse tensor
            neighbors: list of neighbors (without self-loop)
        '''
        self.label = label
        self.g = g
        self.node_tags = node_tags
        self.neighbors = []
        self.node_features = 0
        self.edge_mat = 0

        self.max_neighbor = 0
def softmax(x):
    """Compute softmax values for each sets of scores in x."""
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum()
def convertBLIFGraphIntoDataset(BLIFGraph, stdCellTypesForFeature, maxNumType=36):

    print('converting BLIF Graph Into Dataset data')
    g_list = []
    feat_dict = {}

    g = BLIFGraph
    node_tags = []

    node_features = None

    labelsListForNode = []

    maxLabel = 0

    typeSet = set()
    for i in g.nodes():
        typeSet.add(g.nodes()[i]['type'])

    typeSet = list(typeSet)
    typeSet.sort()
    for typeId, stdCellType in enumerate(stdCellTypesForFeature):
        feat_dict[stdCellType] = typeId

    for tmpType in typeSet:
        if (not tmpType in feat_dict.keys()):
            feat_dict[tmpType] = len(feat_dict)

    print("feat_dict: ", feat_dict)
    print("typeSet: ", typeSet)
    # assert(len(typeSet) < maxNumType)

    for i in g.nodes():
        if (g.nodes()[i]['nodeLabel'] >= 0):
            labelsListForNode.append(g.nodes()[i]['nodeLabel'])
            maxLabel = max(maxLabel, g.nodes()[i]['nodeLabel'])

        node_tags.append(feat_dict[g.nodes()[i]['type']])

    g_list = [S2VGraph(g, None, node_tags)]

    # add labels (based on pattern) and edge_mat
    for g in g_list:

        g.label = labelsListForNode
        edges = [list((pair[0], pair[1], 1)) for pair in g.g.edges()]
        g.edge_mat = np.array(edges).T

    # add node feature based on node type
    featureDim = max(maxNumType, len(feat_dict))
    for g in g_list:

        node_features = np.zeros((len(g.node_tags), featureDim))
        node_features[range(len(g.node_tags)), [
            tag for tag in g.node_tags]] = 1

        g.node_features = np.array(node_features)

    print("# data: %d" % len(node_features))

    return g_list, maxLabel+1
def loadDataAndPreprocess(libFileName="sky130_fd_sc_hd__tt_025C_1v80.lib", blifFileName="rocket.blif", startTime=0, bypassInitialCluster=False, singleOutputSeeds=False):
    BLIFGraph, cells, netlist, stdCellTypesForFeature = genGraphFromLibertyAndBLIF(
        libFileName, blifFileName)
    endTime = time.time()
    print("genGraphFromLibertyAndBLIF done. time esclaped: ", endTime-startTime)

    initialClusterSeqs = None
    clusterNum = None
    if (not bypassInitialCluster):
        initialClusterSeqs, clusterNum = heuristicLabelSomeNodesAndGetInitialClusters(
            BLIFGraph, cells, netlist)
        endTime = time.time()
        print("heuristicLabelSomeNodesAndGetInitialClusters done. time esclaped: ",
              endTime-startTime)

    dataset, maxLabelIndex = convertBLIFGraphIntoDataset(
        BLIFGraph, stdCellTypesForFeature, 36)
    endTime = time.time()
    print("loadDataAndPreprocess done. time esclaped: ", endTime-startTime)

    return BLIFGraph, cells, netlist, stdCellTypesForFeature, dataset, maxLabelIndex, initialClusterSeqs, clusterNum
def getArea(cells, type2Area):
    resArea = 0
    for cell in cells:
        if (cell.stdCellType.typeName in type2Area.keys()):
            resArea += type2Area[cell.stdCellType.typeName]
    return resArea
