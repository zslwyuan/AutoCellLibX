"""Pattern growth (layer: growth).

Extracted from blif_pattern_growth.py (AST-verbatim): the greedy/beam
growth of a cluster sequence by absorbing the most frequent absorbable
neighbour class, with the optional benefit-estimator pruning (P0-3),
the internalize_only synthesis-reuse bias (AUDIT 5.26) and the _BasedOn
replay variant.
"""

from blif_graph_util import DesignPatternClusterSeq


def _collect_neighbor_features(clusters, internalize_only):
    """Shared neighbour classification for both growth variants.

    Walks every cluster's member cells, buckets their boundary neighbours
    by feature code (``TYPE_c<k>i<o>`` / ``...o<k>``), and maps each
    neighbour back to the cluster it would extend.  ``internalize_only``
    (synthesis-reuse mode) skips neighbours whose outputs would escape.
    Returns (neighbors_by_feature, feature2cnt, neighbor2cluster).
    """
    visited_neighbors = set()
    neighbors_by_feature = dict()
    feature2cnt = dict()
    neighbor2cluster = dict()
    # iterate all the neighbors of the clusters in the current pattern and classify them
    for cluster in clusters:
        cell_order_id = 0
        this_cluster_neighbors = dict()
        for cell in cluster.cells:

            # iterate input predecessors
            in_order_id = 0
            for input_net in cell.input_nets:
                cur_neighbor = input_net.pred_cell
                if (cur_neighbor is None):
                    continue
                # bypass cells in current cluster or visited
                if (cur_neighbor.cluster_id == cluster.cluster_id or cur_neighbor in visited_neighbors or cur_neighbor.stop_type):
                    continue
                if (cur_neighbor.cluster_id != -1):
                    if (cur_neighbor.cluster.cluster_type_id == cluster.cluster_type_id):
                        continue
                if (internalize_only and not _absorbable(
                        cur_neighbor, cluster.cell_ids)):
                    continue
                neighbor2cluster[cur_neighbor] = cluster

                if (not cur_neighbor in this_cluster_neighbors):
                    this_cluster_neighbors[cur_neighbor] = cur_neighbor.std_cell_type.type_name + "_" + \
                        "c"+str(cell_order_id)+"i" + str(in_order_id)
                else:
                    this_cluster_neighbors[cur_neighbor] += "c" + \
                        str(cell_order_id)+"i" + str(in_order_id)

                in_order_id += 1

            # iterate output successors
            out_order_id = 0
            for output_net in cell.output_nets:
                for cur_neighbor in output_net.succ_cells:
                    # bypass cells in current cluster or visited
                    if (cur_neighbor.cluster_id == cluster.cluster_id or cur_neighbor in visited_neighbors or cur_neighbor.stop_type):
                        continue
                    if (cur_neighbor.cluster_id != -1):
                        if (cur_neighbor.cluster.cluster_type_id == cluster.cluster_type_id):
                            continue
                    if (internalize_only and not _absorbable(
                            cur_neighbor, cluster.cell_ids)):
                        continue
                    neighbor2cluster[cur_neighbor] = cluster

                    if (not cur_neighbor in this_cluster_neighbors):
                        this_cluster_neighbors[cur_neighbor] = cur_neighbor.std_cell_type.type_name + "_" + \
                            "c" + \
                            str(cell_order_id)+"o"+str(out_order_id)
                    else:
                        this_cluster_neighbors[cur_neighbor] += "c" + \
                            str(cell_order_id)+"o"+str(out_order_id)

                out_order_id += 1
            cell_order_id += 1

        for neighbor in this_cluster_neighbors.keys():
            neighbor_feature = this_cluster_neighbors[neighbor]
            visited_neighbors.add(neighbor)
            if (not neighbor_feature in neighbors_by_feature.keys()):
                neighbors_by_feature[neighbor_feature] = []
                feature2cnt[neighbor_feature] = 0
            neighbors_by_feature[neighbor_feature].append(neighbor)
            feature2cnt[neighbor_feature] += 1
    return (neighbors_by_feature, feature2cnt, neighbor2cluster)


def _absorbable(neighbor, cluster_ids):
    """Whether absorbing ``neighbor`` adds no new escaping output: every
    load of its output nets must already sit inside the cluster (or be
    the neighbor itself), so all its outputs stay internalised."""
    for out_net in neighbor.output_nets:
        for succ in out_net.succ_cells:
            if (succ.id not in cluster_ids and succ.id != neighbor.id):
                return False
    return True


def grow_sequence_of_clusters(blif_graph, cluster_seq, cluster_num, pattern_num, paint_pattern=False, feature_len=20, benefit_estimator=None, internalize_only=False):

    clusters = []
    cells_in_clusters = set()
    # Filter out disabled clusters.  With beam growth (grow_beam_width>1) a
    # head grown later in the same round can contain clusters that an
    # earlier head just disabled by stealing their cells -- the pool is
    # only cleaned (remove_empty_seqs_and_disable_clusters) after the whole
    # beam, so a hard assert here is a stale single-head invariant.
    for cluster in cluster_seq.pattern_clusters:
        if (not cluster.disabled):
            clusters.append(cluster)
            for cell_id in cluster.cell_ids:
                # used to detect merging of clusters in this seq (i.e., merge the same patterns)
                cells_in_clusters.add(cell_id)

    # count the neighbors of the clusters:
    visited_neighbors = set()  # cells_in_clusters
    neighbors_by_cluster = []
    neighbors_by_feature = dict()
    feature2cnt = dict()
    neighbor2cluster = dict()

    neighbors_by_feature, feature2cnt, neighbor2cluster =         _collect_neighbor_features(clusters, internalize_only)


    sorted_neighbor_features = []
    for key in feature2cnt.keys():
        sorted_neighbor_features.append((key, feature2cnt[key]))
    sorted_neighbor_code = sorted(
        sorted_neighbor_features, key=lambda tup: -tup[1])
    if (len(sorted_neighbor_code) > 10):
        sorted_neighbor_code = sorted_neighbor_code[:10]
    print("sorted_neighbor_features: ")
    for neighbor_code, code_cnt in sorted_neighbor_code:
        print(neighbors_by_feature[neighbor_code][0].std_cell_type.type_name,
              " code: (", neighbor_code, ") cnt:", code_cnt)

    # Merge the best branch whose *estimated* benefit is positive.  Pure
    # frequency ranking (the old `[:1]`) walked into negative-outcome
    # shapes (COMPLEX10: -56.05 um^2) and only found out after a 5-10 min
    # ASTRAN run; the estimator (benefit.py, calibrated online from the
    # layouts already produced in this run) vetoes those branches up
    # front when provided.  Branches are tried in frequency order and at
    # most one is merged, preserving the single-mutation semantics.
    res_seqs = []
    merged_cluster = set()
    for neighbor_code, code_cnt in sorted_neighbor_code:
        neighbors = neighbors_by_feature[neighbor_code]

        if (benefit_estimator is not None and len(clusters) > 0):
            member_type_names = [c.std_cell_type.type_name
                               for c in clusters[0].cells]
            est_benefit = benefit_estimator(
                member_type_names,
                neighbors[0].std_cell_type.type_name,
                len(clusters[0].cells) + 1,
                len(neighbors))
            if (est_benefit <= 0):
                print("pruned growth branch (", neighbor_code,
                      "): estimated benefit ", round(est_benefit, 4), " <= 0")
                continue

        neighbors_in_this_seq_cnt = 0
        for neighbor in neighbors:
            if (neighbor in cells_in_clusters):
                neighbors_in_this_seq_cnt += 1

        new_clusters = []
        for neighbor in neighbors:
            target_cluster = neighbor2cluster[neighbor]

            if (target_cluster.disabled):
                continue

            if (target_cluster in merged_cluster):
                continue

            if (not neighbor.cluster is None):
                # disable the cluster which contains this neighbor
                neighbor.cluster.disabled = True
            neighbor.cluster_id = target_cluster.cluster_id
            neighbor.cluster = target_cluster
            merged_cluster.add(target_cluster)
            target_cluster.pattern_extension_trace += "+" + neighbor_code
            target_cluster.cluster_type_id = pattern_num
            target_cluster.add_cell(neighbor)
            new_clusters.append(target_cluster)

        if (len(new_clusters) == 0):
            continue

        print("extended ", len(new_clusters), " clusters and new pattern is : ",
              new_clusters[0].pattern_extension_trace, " and the size of each clustet is ", len(new_clusters[0].cells))

        new_seq = DesignPatternClusterSeq(new_clusters[0].pattern_extension_trace)
        for cluster in new_clusters:
            new_seq.add_cluster(cluster)

        pattern_num += 1

        res_seqs.append(new_seq)
        break

    # record those clusters which did not extend
    cluster_seq.pattern_clusters = []
    for cluster in clusters:
        if (cluster in merged_cluster):
            continue
        cluster_seq.pattern_clusters.append(cluster)

    res_seqs.append(cluster_seq)

    return res_seqs, pattern_num


def grow_sequence_of_clusters_based_on(blif_graph, cluster_seq, cluster_num, pattern_num, paint_pattern=False, feature_len=20, target_pattern_trace="", benefit_estimator=None, internalize_only=False):

    assert(target_pattern_trace != "")
    clusters = []
    cells_in_clusters = set()
    # Filter out disabled clusters.  With beam growth (grow_beam_width>1) a
    # head grown later in the same round can contain clusters that an
    # earlier head just disabled by stealing their cells -- the pool is
    # only cleaned (remove_empty_seqs_and_disable_clusters) after the whole
    # beam, so a hard assert here is a stale single-head invariant.
    for cluster in cluster_seq.pattern_clusters:
        if (not cluster.disabled):
            clusters.append(cluster)
            for cell_id in cluster.cell_ids:
                # used to detect merging of clusters in this seq (i.e., merge the same patterns)
                cells_in_clusters.add(cell_id)

    # count the neighbors of the clusters:
    visited_neighbors = set()  # cells_in_clusters
    neighbors_by_cluster = []
    neighbors_by_feature = dict()
    feature2cnt = dict()
    neighbor2cluster = dict()

    neighbors_by_feature, feature2cnt, neighbor2cluster =         _collect_neighbor_features(clusters, internalize_only)


    sorted_neighbor_features = []
    for key in feature2cnt.keys():
        sorted_neighbor_features.append((key, feature2cnt[key]))
    sorted_neighbor_code = sorted(
        sorted_neighbor_features, key=lambda tup: -tup[1])
    if (len(sorted_neighbor_code) > 10):
        sorted_neighbor_code = sorted_neighbor_code[:10]
    print("sorted_neighbor_features: ")
    for neighbor_code, code_cnt in sorted_neighbor_code:
        print(neighbors_by_feature[neighbor_code][0].std_cell_type.type_name,
              " code: (", neighbor_code, ") cnt:", code_cnt)

    # Merge the best branch whose *estimated* benefit is positive.  Pure
    # frequency ranking (the old `[:1]`) walked into negative-outcome
    # shapes (COMPLEX10: -56.05 um^2) and only found out after a 5-10 min
    # ASTRAN run; the estimator (benefit.py, calibrated online from the
    # layouts already produced in this run) vetoes those branches up
    # front when provided.  Branches are tried in frequency order and at
    # most one is merged, preserving the single-mutation semantics.
    res_seqs = []
    merged_cluster = set()
    for neighbor_code, code_cnt in sorted_neighbor_code:
        neighbors = neighbors_by_feature[neighbor_code]

        if (benefit_estimator is not None and len(clusters) > 0):
            member_type_names = [c.std_cell_type.type_name
                               for c in clusters[0].cells]
            est_benefit = benefit_estimator(
                member_type_names,
                neighbors[0].std_cell_type.type_name,
                len(clusters[0].cells) + 1,
                len(neighbors))
            if (est_benefit <= 0):
                print("pruned growth branch (", neighbor_code,
                      "): estimated benefit ", round(est_benefit, 4), " <= 0")
                continue

        neighbors_in_this_seq_cnt = 0
        for neighbor in neighbors:
            if (neighbor in cells_in_clusters):
                neighbors_in_this_seq_cnt += 1

        new_clusters = []
        for neighbor in neighbors:
            target_cluster = neighbor2cluster[neighbor]

            if (target_cluster.disabled):
                continue

            if (target_cluster in merged_cluster):
                continue

            if (not neighbor.cluster is None):
                # disable the cluster which contains this neighbor
                neighbor.cluster.disabled = True
            neighbor.cluster_id = target_cluster.cluster_id
            neighbor.cluster = target_cluster
            merged_cluster.add(target_cluster)
            target_cluster.pattern_extension_trace += "+" + neighbor_code
            target_cluster.cluster_type_id = pattern_num
            target_cluster.add_cell(neighbor)
            new_clusters.append(target_cluster)

        if (len(new_clusters) == 0):
            continue

        print("extended ", len(new_clusters), " clusters and new pattern is : ",
              new_clusters[0].pattern_extension_trace, " and the size of each clustet is ", len(new_clusters[0].cells))

        new_seq = DesignPatternClusterSeq(new_clusters[0].pattern_extension_trace)
        for cluster in new_clusters:
            new_seq.add_cluster(cluster)

        pattern_num += 1

        res_seqs.append(new_seq)
        break

    # record those clusters which did not extend
    cluster_seq.pattern_clusters = []
    for cluster in clusters:
        if (cluster in merged_cluster):
            continue
        cluster_seq.pattern_clusters.append(cluster)

    res_seqs.append(cluster_seq)

    return res_seqs, pattern_num
