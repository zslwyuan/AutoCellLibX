"""Regenerate outputs/adder/bestRecord-seperateadder.

A verbatim replay of main.py's phase 2 (the per-pattern record loop), driven
with the phase-1 state of the committed adder run: the five dumped traces and
their trace->id mapping.  Phase 2 itself cannot run in the full pipeline
because COMPLEX11/12's generation does not terminate (CBC ignores the time
limit on the largest models), which previously aborted the benchmark before
phase 2.  The replay keeps the same guards main.py now has (skip patterns
without a usable layout) and additionally skips grown traces that were never
dumped.  Deterministic: same formulas, same floats as the real loop.
"""
import os
import sys
import time

sys.path.insert(0, os.getcwd())
from astran import load_astran_area
from blif_graph_util import (remove_empty_seqs_and_disable_clusters,
                           sort_pattern_cluster_seqs)
from blif_pattern_growth import grow_sequence_of_clusters_based_on
from blif_preproc import (get_area,
                         heuristic_label_initial_clusters_based_on,
                         load_data_and_preprocess)
from gds_analysis import load_astran_gds, load_original_gscl45_gds
from spice import export_spice_netlist, load_spice_subcircuits

benchmark_name = "adder"
output_path = "./outputs/" + benchmark_name + "/"
ratio_thr, cnt_thr = 0.05, 30

dumped_patterns = {
    "[NAND2X1,NAND2X1,OR2X1]": 0,
    "[XNOR2X1,XOR2X1,OAI21X1]": 1,
    "[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0": 9,
    "[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0+OAI21X1_c2o0": 10,
    "[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0+OAI21X1_c2o0+AND2X1_c4i0": 11,
}
detected_patterns = list(dumped_patterns)

subckts = load_spice_subcircuits("../std_celllib/cellsAstranFriendly.sp")
gscl_area_by_type = load_original_gscl45_gds()

counted_set = set()
record_pattern_details = []
detected_patterns.reverse()
file_result = open(output_path + "bestRecord-seperate" + benchmark_name, 'w')
for target_pattern_trace in detected_patterns:
    if (target_pattern_trace in counted_set):
        continue

    blif_graph, cells, netlist, std_cell_types_for_feature, dataset, max_label_index, cluster_seqs, cluster_num = load_data_and_preprocess(
        lib_file_name="../std_celllib/gscl45nm.lib", blif_file_name="../benchmark/blif/"+benchmark_name+".blif", start_time=0, bypass_initial_cluster=True)

    cluster_seqs, cluster_num = heuristic_label_initial_clusters_based_on(
        blif_graph, cells, netlist, target_pattern_trace)

    orig_area = get_area(cells, gscl_area_by_type)

    astran_area_by_type = load_astran_gds()
    astran_area = get_area(cells, astran_area_by_type)

    cluster_seqs = sort_pattern_cluster_seqs(cluster_seqs)

    pattern_num = len(cluster_seqs)
    best_save_area = 0
    last_save_gscl_area = 0
    last_complex_selection = 0

    for i in range(0, 10):
        print("searching for ", target_pattern_trace)
        if (len(cluster_seqs) == 0 or len(cluster_seqs[0].pattern_clusters) == 0):
            break
        if (len(cluster_seqs[0].pattern_clusters[0].cell_ids) >= 11):
            continue

        save_area = 0
        save_gscl_area = 0
        complex_selection = []
        touch = False
        for j in range(0, 1):
            if (j >= len(cluster_seqs)):
                break
            tmp_cluster_seq = cluster_seqs[j]
            if (tmp_cluster_seq.pattern_extension_trace not in dumped_patterns):
                break  # grown beyond the dumped patterns: nothing to record
            pattern_trace_id = dumped_patterns[tmp_cluster_seq.pattern_extension_trace]

            example_cells = []
            for cell_id in tmp_cluster_seq.pattern_clusters[0].cell_ids:
                example_cells.append(cells[cell_id])

            complex_selection.append(("COMPLEX"+str(pattern_trace_id), len(
                tmp_cluster_seq.pattern_clusters), len(tmp_cluster_seq.pattern_clusters[0].cell_ids), tmp_cluster_seq.pattern_extension_trace))
            orig_unit_astran_area = get_area(
                example_cells, astran_area_by_type)
            orig_unit_gscl_area = get_area(example_cells, gscl_area_by_type)
            try:
                new_unit_astran_area = load_astran_area(
                    output_path, "COMPLEX"+str(pattern_trace_id))
            except Exception:
                print("WARNING :", benchmark_name,
                      " COMPLEX"+str(pattern_trace_id),
                      " has no usable layout; skipping it in the records")
                continue
            if (new_unit_astran_area <= 0):
                print("WARNING :", benchmark_name,
                      " COMPLEX"+str(pattern_trace_id),
                      " has zero width; skipping it in the records")
                continue
            save_area += (orig_unit_astran_area-new_unit_astran_area) * \
                len(tmp_cluster_seq.pattern_clusters)
            save_gscl_area += (orig_unit_gscl_area-new_unit_astran_area) * \
                len(tmp_cluster_seq.pattern_clusters)

            touch = True

        print("save_area=", save_area, " / ",
              save_area/astran_area*100, "%")
        if (touch and (not tmp_cluster_seq.pattern_extension_trace in counted_set)):

            counted_set.add(tmp_cluster_seq.pattern_extension_trace)
            best_save_area = save_area
            last_save_gscl_area = save_gscl_area
            last_complex_selection = complex_selection

            record_pattern_details.append((best_save_area, best_save_area/astran_area*100,
                                         len(tmp_cluster_seq.pattern_clusters),
                                         len(
                                             tmp_cluster_seq.pattern_clusters[0].cell_ids),
                                         len(tmp_cluster_seq.pattern_clusters[0].cell_ids)*len(
                                             tmp_cluster_seq.pattern_clusters),
                                         "COMPLEX"+str(pattern_trace_id),
                                         tmp_cluster_seq.pattern_extension_trace)
                                        )
            if (target_pattern_trace == last_complex_selection[0][3]):
                break

        cluster_seq = cluster_seqs[0]
        if (len(cluster_seq.pattern_clusters[0].cell_ids)*len(cluster_seq.pattern_clusters) < ratio_thr * len(cells)
                and len(cluster_seq.pattern_clusters) < cnt_thr):
            break

        new_seq_of_clusters, pattern_num = grow_sequence_of_clusters_based_on(
            blif_graph, cluster_seq, cluster_num, pattern_num,  paint_pattern=True, target_pattern_trace=target_pattern_trace)

        cluster_seqs = cluster_seqs[1:]
        cluster_seqs += new_seq_of_clusters
        cluster_seqs = remove_empty_seqs_and_disable_clusters(cluster_seqs)
        cluster_seqs = sort_pattern_cluster_seqs(cluster_seqs)

record_pattern_details = sorted(record_pattern_details,
                              key=lambda x: -x[0])
print("| designOverallArea | saveArea | saveRatio | patternCnt | patternSize |"
      " patternCoverage | patternName | patternCode |",  file=file_result)
for save_area, save_ratio, pattern_cnt, pattern_size, pattern_coverage, pattern_name, pattern_code in record_pattern_details:
    print('|', orig_area, '|', save_area, '|', save_ratio, '|', pattern_cnt, '|', pattern_size, '|',
          pattern_coverage, '|', pattern_name, '|', pattern_code, '|', file=file_result)
file_result.close()
print("wrote", output_path + "bestRecord-seperate" + benchmark_name)
