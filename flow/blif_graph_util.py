import networkx as nx
import matplotlib.cm as cm
import matplotlib.pyplot as plt
from itertools import count
import numpy as np
import warnings


class StdCellType(object):
    def __init__(self, type_name):
        self.id = id
        self.type_name = type_name
        self.pins = []
        self.input_pins = []
        self.output_pins = []
        self.input_pin_map = dict()
        self.output_pin_map = dict()

    def add_pin(self, pin_name, direction):
        if (direction == "input"):
            self.input_pins.append(pin_name)
        if (direction == "output"):
            self.output_pins.append(pin_name)
        self.pins.append(pin_name)


class DesignCell(object):
    def __init__(self, id, name, std_cell_type):
        self.id = id
        self.name = name
        self.std_cell_type = std_cell_type
        self.input_pin_ref_names = []
        self.input_net_names = []
        self.input_nets = []
        self.output_pin_ref_names = []
        self.output_net_names = []
        self.output_nets = []
        self.cluster_id = -1
        self.cluster = None
        self.feature_v = None
        self.feature_order = None
        self.stop_type = False

    def add_cell_pin(self, ref_pin_name, net_name):
        if (ref_pin_name in self.std_cell_type.input_pins):
            self.input_pin_ref_names.append(ref_pin_name)
            self.input_net_names.append(net_name)
        else:
            self.output_pin_ref_names.append(ref_pin_name)
            self.output_net_names.append(net_name)

    def add_input_net(self, cur_net):
        self.input_nets.append(cur_net)

    def add_output_net(self, cur_net):
        self.output_nets.append(cur_net)

    def set_cluster_id(self, cluster_id):
        self.cluster_id = cluster_id

    def set_cluster(self, cluster):
        self.cluster = cluster

    def set_feature(self, feature_v):
        self.feature_v = feature_v
        self.feature_order = (-feature_v).argsort()


class DesignNet(object):
    # Class-level tally of multi-driver overwrite events (per process), so a
    # silent data problem is visible and testable instead of buried.
    multi_driver_count = 0

    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.succ_pins = []
        self.pred_pin = None
        self.succ_cells = []
        self.pred_cell = None
        self.pins = []

    def add_pin(self, pin_name, cell, is_succ):
        if (is_succ):
            self.succ_pins.append(pin_name)
            self.succ_cells.append(cell)
        else:
            if (self.pred_cell is not None):
                # Multi-driver net: historically the later driver silently
                # overwrote pred_cell, corrupting edge directions without a
                # trace.  Keep the resolution (last wins) but never quietly.
                DesignNet.multi_driver_count += 1
                warnings.warn(
                    "net %r has multiple drivers (%r and %r); keeping the "
                    "last one" % (self.name, self.pred_cell.name, cell.name),
                    RuntimeWarning)
            self.pred_pin = pin_name
            self.pred_cell = cell
        self.pins.append(pin_name)


class DesignPatternCluster(object):
    def __init__(self, cluster_id, pattern_str, cells, cell_ids, cluster_type_id):
        self.pattern_extension_trace = pattern_str.replace(
            "\'", "").replace("\\", "").replace("\"", "")
        self.cluster_id = cluster_id
        self.cell_ids = cell_ids
        self.cells = []
        for cell_id in cell_ids:
            self.cells.append(cells[cell_id])
        self.disabled = False
        self.cluster_type_id = cluster_type_id

    def add_cell(self, cell):
        self.cell_ids.append(cell.id)
        self.cells.append(cell)


class DesignPatternClusterSeq(object):
    def __init__(self, pattern_str):
        self.pattern_extension_trace = pattern_str.replace(
            "\'", "").replace("\\", "").replace("\"", "")
        self.pattern_clusters = []

    def add_cluster(self, pattern_cluster):
        self.pattern_clusters.append(pattern_cluster)


def remove_empty_seqs_and_disable_clusters(seqs):
    new_cluster_seqs = []
    for cur_seq in seqs:
        if (len(cur_seq.pattern_clusters) > 0):
            new_clusters = []
            for tmp_cluster in cur_seq.pattern_clusters:
                if (not tmp_cluster.disabled):
                    new_clusters.append(tmp_cluster)
            if (len(new_clusters) > 0):
                cur_seq.pattern_clusters = new_clusters
                new_cluster_seqs.append(cur_seq)
            else:
                del cur_seq
        else:
            del cur_seq
    return new_cluster_seqs


def count_uncovered_clusters(pattern_clusters, covered_cell_ids):
    """Count clusters disjoint from ``covered_cell_ids``, marking them covered.

    Candidates evaluated in the same round can claim overlapping design
    cells, but a cell cannot be instantiated inside two different complex
    cells -- a cluster that overlaps an already-counted candidate must not
    be counted again.  The old summation counted every cluster of every
    candidate, double-counting the overlap and over-reporting the savings.
    """
    unique = 0
    for cluster in pattern_clusters:
        if any(cid in covered_cell_ids for cid in cluster.cell_ids):
            continue
        unique += 1
        covered_cell_ids.update(cluster.cell_ids)
    return unique


def sort_pattern_cluster_seqs(seqs):
    counts = []
    sizes = []

    for cur_seq in seqs:
        counts.append(
            len(cur_seq.pattern_clusters) * len(cur_seq.pattern_clusters[0].cell_ids))
        sizes.append(
            len(cur_seq.pattern_clusters[0].cell_ids))

    newClusterSeqsCnts_Order = np.lexsort(
        (np.array(sizes), -np.array(counts)))

    res_seqs = []

    for idx in newClusterSeqsCnts_Order:
        res_seqs.append(seqs[idx])

    return res_seqs


def draw_graph_figure(tmp_graph, color_attribute='type', save_to_file="", with_label=True, fig=None, figsize=None, prog='dot'):

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

    groups1 = set(nx.get_node_attributes(tmp_graph, color_attribute).values())
    mapping1 = dict(zip(sorted(groups1), count()))
    nodes1 = tmp_graph.nodes()
    colors1 = [mapping1[tmp_graph.nodes()[n][color_attribute]] for n in nodes1]

    ec = nx.draw_networkx_edges(tmp_graph, pos, alpha=1, width=5)

    label_pos = dict()
    for key in pos.keys():
        label_pos[key] = (pos[key][0], pos[key][1])

    labels = dict((n, (str(d[color_attribute])+"\n("+str(d["name"])+")").replace("\\", "").replace("$", ""))
                  for n, d in tmp_graph.nodes(data=True))

    if (with_label):
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
