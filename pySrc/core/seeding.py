"""Initial clustering (layer: seeding).

Extracted from blif_preproc.py (AST-verbatim): group root cells by
canonical pattern code into DesignPatternClusterSeq candidates ordered
by (cluster count x cluster size); the _BasedOn variant replays one
specific trace for phase-2 records.  single_output_seeds implements the
synthesis-reuse seed filter (AUDIT 5.27).
"""

from blif_graph_util import (DesignPatternCluster,
                           DesignPatternClusterSeq,
                           sort_pattern_cluster_seqs)
from global_variables import bypass_types
from core.encoding import (canonical_pattern_code, escape_output_count,
                           extract_and_encode_subgraph_tree)


def heuristic_label_initial_clusters(blif_graph, cells, netlist, single_output_seeds=False):

    tree_depth = 1

    root_cells_by_pattern = dict()
    for cell in cells:
        should_bypass = False
        for type_key in bypass_types:
            if (cell.std_cell_type.type_name.find(type_key) >= 0):
                should_bypass = True
                break
        if (should_bypass):
            continue
        tree, code = extract_and_encode_subgraph_tree(cells, cell.id, tree_depth)
        if (len(tree) < 2):
            continue
        if (single_output_seeds and escape_output_count(cells, tree) != 1):
            continue
        code_str = canonical_pattern_code(code)
        if (code_str.find("bool-") >= 0):
            continue
        if (not code_str in root_cells_by_pattern.keys()):
            root_cells_by_pattern[code_str] = []
        root_cells_by_pattern[code_str].append(cell.id)

    count_by_pattern = []
    for key in root_cells_by_pattern.keys():
        count_by_pattern.append((key, len(root_cells_by_pattern[key])))
    sorted_by_second = sorted(count_by_pattern, key=lambda tup: -tup[1])
    print("top pattern types: ", sorted_by_second[:30])

    pattern_to_be_labeled = []
    label_id = 0
    labeled_cnt = 0
    cluster_cells_cnt = 0

    initial_cluster_seqs = []
    for tmp_type in sorted_by_second[:30]:
        pattern_to_be_labeled.append(tmp_type[0])
        new_seq = DesignPatternClusterSeq(tmp_type[0])
        for cell_id in root_cells_by_pattern[tmp_type[0]]:
            blif_graph.nodes()[cell_id]['node_label'] = label_id
            tree, code = extract_and_encode_subgraph_tree(   # color the nodes in a pattern
                cells, cell_id, tree_depth, labeled_cnt)
            if (tree is None):
                continue
            code = canonical_pattern_code(code)
            new_cluster = DesignPatternCluster(
                labeled_cnt, code, cells, tree, label_id)
            for cell_id in tree:
                cells[cell_id].set_cluster(new_cluster)

            new_seq.add_cluster(new_cluster)
            labeled_cnt += 1
            cluster_cells_cnt += len(tree)
        if (len(new_seq.pattern_clusters) > 0):
            initial_cluster_seqs.append(new_seq)
            label_id += 1
        else:
            del new_seq

    res_seqs = sort_pattern_cluster_seqs(initial_cluster_seqs)

    print("labeled ", labeled_cnt, " nodes (", labeled_cnt /
          blif_graph.number_of_nodes()*100, "%)")
    print("clustered ", cluster_cells_cnt, " nodes (", cluster_cells_cnt /
          blif_graph.number_of_nodes()*100, "%)")

    return res_seqs, labeled_cnt


def heuristic_label_initial_clusters_based_on(blif_graph, cells, netlist, target_pattern_trace, single_output_seeds=False):

    tree_depth = 1

    root_cells_by_pattern = dict()
    for cell in cells:
        should_bypass = False
        for type_key in bypass_types:
            if (cell.std_cell_type.type_name.find(type_key) >= 0):
                should_bypass = True
                break
        if (should_bypass):
            continue
        tree, code = extract_and_encode_subgraph_tree(cells, cell.id, tree_depth)
        if (len(tree) < 2):
            continue
        if (single_output_seeds and escape_output_count(cells, tree) != 1):
            continue
        code_str = canonical_pattern_code(code)
        if (code_str.find("bool-") >= 0):
            continue
        if (target_pattern_trace.find(code_str) != 0):
            continue
        if (not code_str in root_cells_by_pattern.keys()):
            root_cells_by_pattern[code_str] = []
        root_cells_by_pattern[code_str].append(cell.id)

    count_by_pattern = []
    for key in root_cells_by_pattern.keys():
        count_by_pattern.append((key, len(root_cells_by_pattern[key])))
    sorted_by_second = sorted(count_by_pattern, key=lambda tup: -tup[1])
    print("top pattern types: ", sorted_by_second[:30])

    pattern_to_be_labeled = []
    label_id = 0
    labeled_cnt = 0
    cluster_cells_cnt = 0

    initial_cluster_seqs = []
    for tmp_type in sorted_by_second[:30]:
        pattern_to_be_labeled.append(tmp_type[0])
        new_seq = DesignPatternClusterSeq(tmp_type[0])
        for cell_id in root_cells_by_pattern[tmp_type[0]]:
            blif_graph.nodes()[cell_id]['node_label'] = label_id
            tree, code = extract_and_encode_subgraph_tree(   # color the nodes in a pattern
                cells, cell_id, tree_depth, labeled_cnt)
            if (tree is None):
                continue
            code = canonical_pattern_code(code)
            new_cluster = DesignPatternCluster(
                labeled_cnt, code, cells, tree, label_id)
            for cell_id in tree:
                cells[cell_id].set_cluster(new_cluster)

            new_seq.add_cluster(new_cluster)
            labeled_cnt += 1
            cluster_cells_cnt += len(tree)
        if (len(new_seq.pattern_clusters) > 0):
            initial_cluster_seqs.append(new_seq)
            label_id += 1
        else:
            del new_seq

    res_seqs = sort_pattern_cluster_seqs(initial_cluster_seqs)

    print("labeled ", labeled_cnt, " nodes (", labeled_cnt /
          blif_graph.number_of_nodes()*100, "%)")
    print("clustered ", cluster_cells_cnt, " nodes (", cluster_cells_cnt /
          blif_graph.number_of_nodes()*100, "%)")

    return res_seqs, labeled_cnt
