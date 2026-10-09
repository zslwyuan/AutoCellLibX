"""Shim (ARCHITECTURE): readers live in core/parse, encoding in
core/encoding, seeding in core/seeding.  This module keeps the
orchestration and GNN-dataset helpers (load_data_and_preprocess,
convert_blif_graph_into_dataset, get_area) and re-exports the rest for the
older consumers (gui, tests, pipeline).
"""

import os
import blifparser.blifparser as blifparser
from global_variables import *
from blif_graph_util import *
from core.seeding import (heuristic_label_initial_clusters,
                          heuristic_label_initial_clusters_based_on)
from core.encoding import (extract_and_encode_subgraph_tree,
                           canonical_pattern_code, escape_output_count)
from core.parse import (load_liberty_file, load_bool_gate_from_blif,
                        gen_graph_from_liberty_and_blif)
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
def convert_blif_graph_into_dataset(blif_graph, std_cell_types_for_feature, max_num_type=36):

    print('converting BLIF Graph Into Dataset data')
    g_list = []
    feat_dict = {}

    g = blif_graph
    node_tags = []

    node_features = None

    labels_list_for_node = []

    max_label = 0

    type_set = set()
    for i in g.nodes():
        type_set.add(g.nodes()[i]['type'])

    type_set = list(type_set)
    type_set.sort()
    for type_id, std_cell_type in enumerate(std_cell_types_for_feature):
        feat_dict[std_cell_type] = type_id

    for tmp_type in type_set:
        if (not tmp_type in feat_dict.keys()):
            feat_dict[tmp_type] = len(feat_dict)

    print("feat_dict: ", feat_dict)
    print("type_set: ", type_set)
    # assert(len(type_set) < max_num_type)

    for i in g.nodes():
        if (g.nodes()[i]['node_label'] >= 0):
            labels_list_for_node.append(g.nodes()[i]['node_label'])
            max_label = max(max_label, g.nodes()[i]['node_label'])

        node_tags.append(feat_dict[g.nodes()[i]['type']])

    g_list = [S2VGraph(g, None, node_tags)]

    # add labels (based on pattern) and edge_mat
    for g in g_list:

        g.label = labels_list_for_node
        edges = [list((pair[0], pair[1], 1)) for pair in g.g.edges()]
        g.edge_mat = np.array(edges).T

    # add node feature based on node type
    feature_dim = max(max_num_type, len(feat_dict))
    for g in g_list:

        node_features = np.zeros((len(g.node_tags), feature_dim))
        node_features[range(len(g.node_tags)), [
            tag for tag in g.node_tags]] = 1

        g.node_features = np.array(node_features)

    print("# data: %d" % len(node_features))

    return g_list, max_label+1
def load_data_and_preprocess(lib_file_name="sky130_fd_sc_hd__tt_025C_1v80.lib", blif_file_name="rocket.blif", start_time=0, bypass_initial_cluster=False, single_output_seeds=False):
    blif_graph, cells, netlist, std_cell_types_for_feature = gen_graph_from_liberty_and_blif(
        lib_file_name, blif_file_name)
    end_time = time.time()
    print("gen_graph_from_liberty_and_blif done. time esclaped: ", end_time-start_time)

    initial_cluster_seqs = None
    cluster_num = None
    if (not bypass_initial_cluster):
        initial_cluster_seqs, cluster_num = heuristic_label_initial_clusters(
            blif_graph, cells, netlist)
        end_time = time.time()
        print("heuristic_label_initial_clusters done. time esclaped: ",
              end_time-start_time)

    dataset, max_label_index = convert_blif_graph_into_dataset(
        blif_graph, std_cell_types_for_feature, 36)
    end_time = time.time()
    print("load_data_and_preprocess done. time esclaped: ", end_time-start_time)

    return blif_graph, cells, netlist, std_cell_types_for_feature, dataset, max_label_index, initial_cluster_seqs, cluster_num
def get_area(cells, area_by_type):
    total_area = 0
    for cell in cells:
        if (cell.std_cell_type.type_name in area_by_type.keys()):
            total_area += area_by_type[cell.std_cell_type.type_name]
    return total_area
