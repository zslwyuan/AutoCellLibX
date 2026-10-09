import networkx as nx
import matplotlib.cm as cm
import matplotlib.pyplot as plt
from itertools import count
import numpy as np
import warnings


class StdCellType(object):
    def __init__(self, typeName):
        self.id = id
        self.typeName = typeName
        self.pins = []
        self.inputPins = []
        self.outputPins = []
        self.inputPinMap = dict()
        self.outputPinMap = dict()

    def addPin(self, pinName, direction):
        if (direction == "input"):
            self.inputPins.append(pinName)
        if (direction == "output"):
            self.outputPins.append(pinName)
        self.pins.append(pinName)


class DesignCell(object):
    def __init__(self, id, name, stdCellType):
        self.id = id
        self.name = name
        self.stdCellType = stdCellType
        self.inputPinRefNames = []
        self.inputNetNames = []
        self.inputNets = []
        self.outputPinRefNames = []
        self.outputNetNames = []
        self.outputNets = []
        self.clusterId = -1
        self.cluster = None
        self.featureV = None
        self.featureOrder = None
        self.stopType = False

    def addCellPin(self, refPinName, netName):
        if (refPinName in self.stdCellType.inputPins):
            self.inputPinRefNames.append(refPinName)
            self.inputNetNames.append(netName)
        else:
            self.outputPinRefNames.append(refPinName)
            self.outputNetNames.append(netName)

    def addInputNet(self, curNet):
        self.inputNets.append(curNet)

    def addOutputNet(self, curNet):
        self.outputNets.append(curNet)

    def setClusterId(self, clusterId):
        self.clusterId = clusterId

    def setCluster(self, cluster):
        self.cluster = cluster

    def setFeature(self, featureV):
        self.featureV = featureV
        self.featureOrder = (-featureV).argsort()


class DesignNet(object):
    # Class-level tally of multi-driver overwrite events (per process), so a
    # silent data problem is visible and testable instead of buried.
    multiDriverCount = 0

    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.succPins = []
        self.predPin = None
        self.succCells = []
        self.predCell = None
        self.pins = []

    def addPin(self, pinName, cell, isSucc):
        if (isSucc):
            self.succPins.append(pinName)
            self.succCells.append(cell)
        else:
            if (self.predCell is not None):
                # Multi-driver net: historically the later driver silently
                # overwrote predCell, corrupting edge directions without a
                # trace.  Keep the resolution (last wins) but never quietly.
                DesignNet.multiDriverCount += 1
                warnings.warn(
                    "net %r has multiple drivers (%r and %r); keeping the "
                    "last one" % (self.name, self.predCell.name, cell.name),
                    RuntimeWarning)
            self.predPin = pinName
            self.predCell = cell
        self.pins.append(pinName)


class DesignPatternCluster(object):
    def __init__(self, clusterId, patternStr, cells, cellIdsContained, clusterTypeId):
        self.patternExtensionTrace = patternStr.replace(
            "\'", "").replace("\\", "").replace("\"", "")
        self.clusterId = clusterId
        self.cellIdsContained = cellIdsContained
        self.cellsContained = []
        for cellId in cellIdsContained:
            self.cellsContained.append(cells[cellId])
        self.disabled = False
        self.clusterTypeId = clusterTypeId

    def addCell(self, cell):
        self.cellIdsContained.append(cell.id)
        self.cellsContained.append(cell)


class DesignPatternClusterSeq(object):
    def __init__(self, patternStr):
        self.patternExtensionTrace = patternStr.replace(
            "\'", "").replace("\\", "").replace("\"", "")
        self.patternClusters = []

    def addCluster(self, patternCluster):
        self.patternClusters.append(patternCluster)


def removeEmptySeqsAndDisableClusters(seqs):
    newClusterSeqs = []
    for curSeq in seqs:
        if (len(curSeq.patternClusters) > 0):
            newClusters = []
            for tmpCluster in curSeq.patternClusters:
                if (not tmpCluster.disabled):
                    newClusters.append(tmpCluster)
            if (len(newClusters) > 0):
                curSeq.patternClusters = newClusters
                newClusterSeqs.append(curSeq)
            else:
                del curSeq
        else:
            del curSeq
    return newClusterSeqs


def countUncoveredClusters(patternClusters, coveredCellIds):
    """Count clusters disjoint from ``coveredCellIds``, marking them covered.

    Candidates evaluated in the same round can claim overlapping design
    cells, but a cell cannot be instantiated inside two different complex
    cells -- a cluster that overlaps an already-counted candidate must not
    be counted again.  The old summation counted every cluster of every
    candidate, double-counting the overlap and over-reporting the savings.
    """
    unique = 0
    for cluster in patternClusters:
        if any(cid in coveredCellIds for cid in cluster.cellIdsContained):
            continue
        unique += 1
        coveredCellIds.update(cluster.cellIdsContained)
    return unique


def sortPatternClusterSeqs(seqs):
    newClusterSeqsCnts = []
    newClusterSeqsSize = []

    for curSeq in seqs:
        newClusterSeqsCnts.append(
            len(curSeq.patternClusters) * len(curSeq.patternClusters[0].cellIdsContained))
        newClusterSeqsSize.append(
            len(curSeq.patternClusters[0].cellIdsContained))

    newClusterSeqsCnts_Order = np.lexsort(
        (np.array(newClusterSeqsSize), -np.array(newClusterSeqsCnts)))

    resSeqs = []

    for SeqsId in newClusterSeqsCnts_Order:
        resSeqs.append(seqs[SeqsId])

    return resSeqs


def drawColorfulFigureForGraphWithAttributes(tmp_graph, colorArrtibute='type', save_to_file="", withLabel=True, fig=None, figsize=None, prog='dot'):

    if (save_to_file == ""):
        if (fig is None):
            f = plt.figure(figsize=figsize)
        else:
            f = plt.figure(num=fig.number, figsize=figsize)
    else:
        f = plt.figure(figsize=figsize)

    try:
        pos = nx.drawing.nx_agraph.graphviz_layout(tmp_graph, prog=prog)
    except Exception:
        pos = nx.spring_layout(tmp_graph, seed=1)

    groups1 = set(nx.get_node_attributes(tmp_graph, colorArrtibute).values())
    mapping1 = dict(zip(sorted(groups1), count()))
    nodes1 = tmp_graph.nodes()
    colors1 = [mapping1[tmp_graph.nodes()[n][colorArrtibute]] for n in nodes1]

    ec = nx.draw_networkx_edges(tmp_graph, pos, alpha=1, width=5)

    label_pos = dict()
    for key in pos.keys():
        label_pos[key] = (pos[key][0], pos[key][1])

    labels = dict((n, (str(d[colorArrtibute])+"\n("+str(d["name"])+")").replace("\\", "").replace("$", ""))
                  for n, d in tmp_graph.nodes(data=True))

    if (withLabel):
        nx.draw_networkx_labels(tmp_graph, label_pos,
                                labels=labels, font_size=12)

    nc = nx.draw_networkx_nodes(tmp_graph, pos, nodelist=nodes1, node_color=colors1,
                                node_size=150, cmap=plt.cm.plasma)

    plt.gca().set_axis_off()
    plt.subplots_adjust(top=1, bottom=0, right=1, left=0,
                        hspace=0, wspace=0)
    plt.margins(0, 0)
    plt.gca().xaxis.set_major_locator(plt.NullLocator())
    plt.gca().yaxis.set_major_locator(plt.NullLocator())

    if (save_to_file == ""):
        plt.show()
    else:
        plt.savefig(save_to_file, bbox_inches='tight', pad_inches=0)

    plt.clf()
    f.clear()
    plt.close()
    plt.close()

    return
