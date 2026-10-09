"""Pattern encoding (layer: encoding).

Extracted from blif_preproc.py: ``extract_and_encode_subgraph_tree`` builds
the BFS type-name code for a root cell; ``canonical_pattern_code`` makes
the identity order-invariant (children sorted after the root, AUDIT
5.18/P0-1); ``escape_output_count`` counts a seed's escaping outputs
(synthesis-reuse mode, AUDIT 5.27).
"""

from global_variables import bypass_types


def extract_and_encode_subgraph_tree(cells, root_node, depth_limit=2, cluster_id=None):
    depths = [0]
    tree = [root_node]
    encodes = [cells[root_node].std_cell_type.type_name]
    queue = [root_node]
    head = 0
    while (head < len(tree)):
        cur_node = cells[queue[head]]
        cur_depth = depths[head]
        if (cur_depth >= depth_limit):
            break
        for input_net in cur_node.input_nets:
            if (not input_net.pred_cell is None):
                should_bypass = False
                for type_key in bypass_types:
                    if (input_net.pred_cell.std_cell_type.type_name.find(type_key) >= 0):
                        should_bypass = True
                        break
                if ((not should_bypass)):
                    depths.append(cur_depth+1)
                    queue.append(input_net.pred_cell.id)
                    if (not input_net.pred_cell.id in tree):
                        tree.append(input_net.pred_cell.id)
                        encodes.append(input_net.pred_cell.std_cell_type.type_name)
        head += 1

    if (not cluster_id is None):
        for cell_id in tree:
            if (cells[cell_id].cluster_id >= 0):
                return None, None
        for cell_id in tree:
            cells[cell_id].set_cluster_id(cluster_id)

    return tree, encodes


def canonical_pattern_code(code):
    """Canonical pattern-code string for a raw encode list.

    ``extract_and_encode_subgraph_tree`` appends children in input-net
    enumeration order, so two structurally identical instances whose nets
    enumerate in different orders used to get different strings and were
    split into separate groups (frequency under-counted).  Keep the root
    first and sort the children.  This string is the pattern's identity, so
    every consumer -- initial grouping, cluster traces, and the prefix match
    in ``heuristic_label_initial_clusters_based_on`` -- must build
    it through this helper.  (The paired ``tree``/``code`` lists returned by
    the encoder are intentionally left in BFS order.)
    """
    canon = code[:1] + sorted(code[1:])
    return str(canon).replace(
        "\'", "").replace("\\", "").replace("\"", "").replace(" ", "")


def escape_output_count(cells, tree):
    """Number of escaping member output pins of a seed tree (== the
    complex cell's output pins): a member output pin whose loads are not
    all inside the tree.  Used by the single-output seed filter of the
    synthesis-reuse mode (AUDIT 5.27)."""
    inside = set(tree)
    count = 0
    for cell_id in tree:
        for out_net in cells[cell_id].output_nets:
            if (len(out_net.succ_cells) == 0
                    or not all(s.id in inside for s in out_net.succ_cells)):
                count += 1
    return count
