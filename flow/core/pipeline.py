"""The mining pipeline (layer: pipeline).

Extracted verbatim from main.py (AST move): the full benchmark loop --
initial clustering, greedy/beam growth, SPICE export, ASTRAN layout,
area / electrical / timing / routability / reuse evaluation, and the
phase-2 per-pattern records.  main.py is now a thin CLI that builds a
FlowConfig and calls ``run_pipeline``; the GUI (flow_core) is the next
consumer to migrate onto it (AUDIT/ARCHITECTURE note).
"""

import os
import time
import glob
import matplotlib
from core.log import get_flow_logger

_flowLog = get_flow_logger()

from blif_preproc import *
from blif_pattern_growth import *
from spice import *
from core.external import *
from core.evaluate import *
from llm_hint_provider import get_hint_provider


def mkdir(path_str):
    if os.path.exists(path_str):
        pass
    else:
        os.mkdir(path_str)




class PipelineHooks(object):
    """Observer interface for run_pipeline (GUI / experiments / tests).

    All methods are no-ops by default: with ``hooks=None`` the pipeline
    behaves exactly like the CLI.  ``run_layout`` lets a host supply its
    own layout runner (the GUI needs Popen + CREATE_NO_WINDOW + custom
    geometry); returning ``None`` means "excluded this pattern".
    ``check_cancel`` should raise to abort the run.
    """

    def stage(self, name, status, message="", extra=None):
        pass

    def log(self, message, level="info"):
        pass

    def pattern(self, info):
        pass

    def metric(self, info):
        pass

    def record(self, kind, info):
        pass

    def check_cancel(self):
        pass

    def run_layout(self, pattern_trace_id):
        return None

    def result(self, key, value):
        pass


def run_pipeline(cfg, hooks=None):

    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    # Dual-mode coexistence (AUDIT 5.26): AUTOCELL_REUSE_MODE=1 runs the
    # mining with the synthesis-reuse constraints (single-output, simple
    # functions, internalize-only growth) into a separate outputs/
    # directory, leaving the physical-mode snapshots untouched.
    reuse_mode = cfg.reuse_mode
    if (reuse_mode):
        global require_reuse_eligible
        require_reuse_eligible = True
    # astran_build_path = ""  # empty when Astran is unavailable.
    # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    astran_build_path = cfg.astran_build_path or ASTRAN_BUILD_PATH  # vendored

    benchmarks = ["sqrt",
                  "voter", "arbiter", "cavlc", "div",
                  "int2float", "max", "priority", "sin",
                  "square", "BoomBranchPredictor",
                  "GemminiLoopMatmul", "GemminiLoopConv", "DCache", "BoomRegisterFile", "GemminiMesh", ]
    # benchmarks = ["adder",  "ctrl", "i2c", "multiplier", "router"]
    benchmarks = cfg.benchmarks

    gscl_area_by_type = load_original_gscl45_gds()
    top_thr = cfg.top_thr
    ratio_thr = 0.05
    cnt_thr = 30
    # benchmarks = ["tc_008_arthmetic_sin"]
    # ratio_thr = -1
    # cnt_thr = -1

    for benchmark_name in benchmarks:
        start_time = time.time()
        ratio_thr = cfg.ratio_thr_for(benchmark_name)
        cnt_thr = cfg.cnt_thr

        print("=================================================================================\n",
              benchmark_name, "\n=================================================================================\n")
        # load liberty/spice/design BLIF
        subckts = load_spice_subcircuits(cfg.spice_lib)
        blif_graph, cells, netlist, std_cell_types_for_feature, dataset, max_label_index, cluster_seqs, cluster_num = load_data_and_preprocess(
            lib_file_name=cfg.liberty, blif_file_name=cfg.blif_dir+"/"+benchmark_name+".blif", start_time=start_time, single_output_seeds=reuse_mode)
        orig_area = get_area(cells, gscl_area_by_type)
        print("original_area=", orig_area)

        output_path = cfg.output_dir(benchmark_name)
        mkdir(output_path)

        if (astran_build_path != ""):
            for orig_std_cell_type in std_cell_types_for_feature:
                if (orig_std_cell_type.find("bool") >= 0):
                    continue
                if (os.path.exists('./original_astran_cells/'+orig_std_cell_type+'.gds')):
                    continue
                run_astran_for_netlist(astran_path=astran_build_path, gurobi_path=GUROBI_CL,
                                    technology_path=ASTRAN_TECHNOLOGY,
                                    spice_netlist_path=cfg.spice_lib,
                                    complex_name=orig_std_cell_type, command_dir='./original_astran_cells/')
        astran_area_by_type = load_astran_gds()
        astran_area = get_area(cells, astran_area_by_type)
        _flowLog.info("astran_area=%.2f", astran_area)
        if (hooks is not None):
            hooks.result("cells", cells)
            hooks.result("blif_graph", blif_graph)
            hooks.result("cluster_seqs", cluster_seqs)
            hooks.result("gscl_area_by_type", gscl_area_by_type)
            hooks.result("astran_area_by_type", astran_area_by_type)
            hooks.result("orig_area", orig_area)
            hooks.result("astran_area", astran_area)
            hooks.stage("parse", "done", "parsed %d cells" % len(cells))

        # Online-calibrated shrink model for growth benefit estimation
        # (P0-3): observes each finished layout's new/baseline width ratio
        # per cell count, and vetoes growth branches whose predicted
        # benefit is non-positive before they cost an ASTRAN run.
        shrink_model = ShrinkModel()
        growth_benefit_estimator = make_growth_benefit_estimator(
            astran_area_by_type, shrink_model)

        # Electrical context per candidate (P1-7): leakage / input
        # capacitance / delay proxy from the liberty file, plus the count
        # of nets the merge internalises (dynamic-power saving proxy).
        # Reported only -- the selection metric stays width-based.
        cell_electrical_metrics = load_cell_electrical_metrics(cfg.liberty)

        # Delay/power from the liberty LUTs (mini-STA per candidate) and
        # a Yosys re-import for design-level cross-check (user priority).
        cell_timing_power = load_timing_power(cfg.liberty)
        lib_functions = load_liberty_functions(cfg.liberty)
        design_lib_area = 0.0
        for tmp_cell in cells:
            m = cell_electrical_metrics.get(tmp_cell.std_cell_type.type_name)
            if (m is not None and m["area"] is not None):
                design_lib_area += m["area"]
        yosys_stat = run_yosys_stat(cfg.liberty,
                                 cfg.blif_dir+"/"+benchmark_name+".blif")
        _flowLog.info("yosys stat cross-check: %s",
                      compare_with_flow_area(yosys_stat, design_lib_area))
        our_type_counts = {}
        for tmp_cell in cells:
            if (tmp_cell.stop_type):
                continue
            tmp_type = tmp_cell.std_cell_type.type_name
            our_type_counts[tmp_type] = our_type_counts.get(tmp_type, 0) + 1
        _flowLog.info("yosys cell-count cross-check: %s",
                      compare_cell_counts(yosys_stat, our_type_counts))

        # Width proxy (P2 phase 1): learned from the layouts already in
        # this repo.  Report-only by default (LOO ~16% MAPE overestimates
        # compact shapes -- it would have vetoed COMPLEX9); opt into
        # growth pruning via use_width_proxy_for_growth.
        transistor_counts = count_transistors_per_type(cfg.spice_lib)
        # Width-proxy training pipeline: load the persisted model when
        # fresh, else retrain from the layout corpus and persist.
        width_proxy, proxy_report = train_or_load_width_proxy(
            sorted(glob.glob("./outputs/*/")), transistor_counts,
            astran_area_by_type)
        if (width_proxy is not None):
            _flowLog.info("width proxy: n=%s source=%s LOO MAPE=%s",
                          proxy_report.get("n"), proxy_report.get("source"),
                          None if proxy_report.get("mape") is None
                          else round(proxy_report["mape"], 4))
        if (use_width_proxy_for_growth and width_proxy is not None):
            growth_benefit_estimator = make_proxy_benefit_estimator(
                width_proxy, astran_area_by_type, transistor_counts)

        cluster_seqs = sort_pattern_cluster_seqs(cluster_seqs)

        # iteratively to pick the most frequent subgraph and extend them by absorbing their neighbors
        dumped_patterns = dict()
        detected_patterns = []

        pattern_num = len(cluster_seqs)
        best_save_area = 0
        last_save_gscl_area = 0
        last_complex_selection = 0
        target_pattern_trace = ""
        fail_improve_cnt = 0
        benchmark_failure = False

        for i in range(0, top_thr):
            if (hooks is not None):
                hooks.check_cancel()
                hooks.stage("mine", "running",
                            "iteration %d/%d" % (i + 1, top_thr),
                            (i, top_thr))
            if (len(cluster_seqs) == 0 or len(cluster_seqs[0].pattern_clusters) == 0):
                break
            if (len(cluster_seqs[0].pattern_clusters[0].cell_ids) >= 11):
                # Pop the oversized head instead of `continue`: continuing
                # without consuming cluster_seqs[0] re-tests the same pattern
                # every round and burns the whole top_thr budget doing nothing.
                cluster_seqs = cluster_seqs[1:]
                continue

            save_area = 0
            save_gscl_area = 0
            complex_selection = []
            # Cells already claimed by a candidate counted this round: a
            # design cell cannot be instantiated inside two different
            # complex cells, so overlapping clusters are counted once
            # (count_uncovered_clusters), not once per candidate.
            covered_cell_ids = set()
            for j in range(0, top_thr):
                if (j >= len(cluster_seqs)):
                    break
                tmp_cluster_seq = cluster_seqs[j]
                pattern_trace_id = tmp_cluster_seq.pattern_clusters[0].cluster_type_id
                pattern_subgraph = blif_graph.subgraph(
                    tmp_cluster_seq.pattern_clusters[0].cell_ids)

                # A pattern's trace is its identity: the same pattern can be
                # produced again in a later iteration under a different
                # cluster_type_id.  Skip it outright -- re-dumping it under a new
                # id would double-count its occurrences in the reported area
                # savings, and the area lookup below would then look for a
                # layout for a duplicate id that was never generated.
                if (tmp_cluster_seq.pattern_extension_trace in dumped_patterns.keys()):
                    continue
                if (len(tmp_cluster_seq.pattern_clusters[0].cell_ids) >= 11):
                    continue
                if (hooks is not None):
                    hooks.check_cancel()
                    hooks.log("pattern #%d '%s' x%d (size=%d)"
                              % (pattern_trace_id,
                                 tmp_cluster_seq.pattern_extension_trace,
                                 len(tmp_cluster_seq.pattern_clusters),
                                 len(tmp_cluster_seq.pattern_clusters[0].cell_ids)))
                print("dealing with pattern#", pattern_trace_id, " with ", len(
                    tmp_cluster_seq.pattern_clusters), " clusters (size=", len(tmp_cluster_seq.pattern_clusters[0].cell_ids), ")")

                if (len(tmp_cluster_seq.pattern_clusters[0].cell_ids)*len(tmp_cluster_seq.pattern_clusters) < ratio_thr * len(cells) and len(tmp_cluster_seq.pattern_clusters) < cnt_thr):
                    print("===Warning: the pattern is too small and bypassed. pattern: [", tmp_cluster_seq.pattern_extension_trace, "]", len(
                        tmp_cluster_seq.pattern_clusters[0].cell_ids)*len(tmp_cluster_seq.pattern_clusters), "<<<", len(cells))
                    break
                dumped_patterns[tmp_cluster_seq.pattern_extension_trace] = pattern_trace_id
                detected_patterns.append(
                    tmp_cluster_seq.pattern_extension_trace)

                draw_graph_figure(
                    pattern_subgraph, save_to_file=output_path+"/COMPLEX"+str(pattern_trace_id)+".png", with_label=True, figsize=(20, 20))

                # export the SPICE netlist of the complex of cells
                export_spice_netlist(tmp_cluster_seq, subckts, str(pattern_trace_id),
                                   output_path)

                # Advisory layout hints (P2 stage 3): an offline/LLM hint
                # provider annotates the grown netlist before it costs an
                # ASTRAN run.  Report-only and gated by cfg.hint_mode
                # (default "off" -> byte-identical default runs).
                if (cfg.hint_mode != "off"):
                    hint_sp_path = output_path+'/COMPLEX'+str(pattern_trace_id)+'.sp'
                    if (os.path.exists(hint_sp_path)):
                        hint_provider = get_hint_provider(mode=cfg.hint_mode)
                        if (hint_provider is not None):
                            with open(hint_sp_path, 'r', errors="ignore") as sp_fh:
                                hints = hint_provider.suggest_hints(
                                    "COMPLEX"+str(pattern_trace_id),
                                    sp_fh.read())
                            if (hints):
                                _flowLog.info(
                                    "layout hints COMPLEX%d: %s",
                                    pattern_trace_id,
                                    ", ".join(
                                        "%s %s=%.2f[%s]"
                                        % (h.kind, h.target, h.value, h.source)
                                        for h in hints))

                # if ASTRAN is available (or a host layout runner is
                # provided), run it to get the layout and area evaluation
                if (astran_build_path != "" or hooks is not None):
                    if (hooks is not None):
                        new_width = hooks.run_layout(pattern_trace_id)
                        if (new_width is None):
                            print("WARNING :", benchmark_name,
                                  " COMPLEX"+str(pattern_trace_id),
                                  " layout hook returned None; excluding the pattern")
                            continue
                    gds_path = output_path+'/COMPLEX'+str(pattern_trace_id)+'.gds'
                    sp_path = output_path+'/COMPLEX'+str(pattern_trace_id)+'.sp'
                    if (hooks is not None):
                        pass  # layout already produced by the hook
                    elif (astran_layout_is_stale(gds_path, sp_path)):
                        if (len(tmp_cluster_seq.pattern_clusters[0].cell_ids) < 11):
                            try:
                                run_astran_for_netlist(astran_path=astran_build_path, gurobi_path=GUROBI_CL,
                                                    technology_path=ASTRAN_TECHNOLOGY,
                                                    spice_netlist_path=output_path+'/COMPLEX' +
                                                    str(pattern_trace_id) +
                                                    '.sp',
                                                    complex_name='COMPLEX'+str(pattern_trace_id), command_dir=output_path)
                                new_width = load_astran_area(
                                    output_path, "COMPLEX"+str(pattern_trace_id))
                                # A failed LP solve makes ASTRAN read an
                                # all-zero solution and emit a 0 x 0 cell;
                                # counting it would report fake area savings.
                                # Exclude the pattern; one failed cell must
                                # not kill the whole benchmark.
                                if (new_width <= 0):
                                    print("WARNING :", benchmark_name,
                                          " COMPLEX"+str(pattern_trace_id),
                                          " has zero width (solver failed); excluding the pattern")
                                    continue
                            except Exception:
                                # ASTRAN could not produce a layout for this
                                # pattern (e.g. every conservative attempt of
                                # autoFlow failed).  Exclude the pattern instead
                                # of failing the whole benchmark, so later
                                # patterns and phase 2 still run.
                                print("WARNING :", benchmark_name,
                                      " COMPLEX"+str(pattern_trace_id),
                                      " could not be generated; excluding the pattern")
                                continue

                if (benchmark_failure):
                    break
                example_cells = []
                for cell_id in tmp_cluster_seq.pattern_clusters[0].cell_ids:
                    example_cells.append(cells[cell_id])

                orig_unit_astran_area = get_area(example_cells, astran_area_by_type)
                orig_unit_gscl_area = get_area(example_cells, gscl_area_by_type)
                new_unit_astran_area = load_astran_area(
                    output_path, "COMPLEX"+str(pattern_trace_id))
                if (new_unit_astran_area <= 0):   # a cached 0 x 0 layout counts nothing
                    continue
                shrink_model.observe(len(example_cells),
                                    orig_unit_astran_area, new_unit_astran_area)
                # Second metric beside width (P0-4): ASTRAN's own routing
                # congestion, parsed from the cell's log.  Reported always;
                # enforced only when routability_density_gate is set.
                rt_metrics = load_cell_routability(
                    output_path, "COMPLEX"+str(pattern_trace_id))
                if (rt_metrics is not None):
                    print("routability ", "COMPLEX"+str(pattern_trace_id),
                          ": ", rt_metrics.as_dict())
                if (rt_metrics is not None
                        and routability_density_gate is not None
                        and rt_metrics.rt_density > routability_density_gate):
                    print("WARNING :", benchmark_name,
                          " COMPLEX"+str(pattern_trace_id),
                          " rt_density", rt_metrics.rt_density,
                          "> gate", routability_density_gate,
                          "; excluding the pattern")
                    continue
                elec_metrics = pattern_electrical_metrics(
                    example_cells, cell_electrical_metrics)
                print("electrical ", "COMPLEX"+str(pattern_trace_id),
                      ": ", elec_metrics)
                # Synthesis-reuse eligibility (AUDIT 5.25): abc only uses
                # single-output, simple-function cells.  Reported always;
                # enforced when require_reuse_eligible is set.
                reuse_info = reuse_eligible(example_cells, lib_functions)
                print("reuse ", "COMPLEX"+str(pattern_trace_id), ": ",
                      reuse_info)
                if (require_reuse_eligible and not reuse_info["eligible"]):
                    print("WARNING :", benchmark_name,
                          " COMPLEX"+str(pattern_trace_id),
                          " not synthesis-reuse eligible (",
                          reuse_info["reason"], "); excluding the pattern")
                    continue
                timing_metrics = pattern_timing_power(
                    example_cells, cell_timing_power, cell_electrical_metrics)
                print("timing/power ", "COMPLEX"+str(pattern_trace_id),
                      ": ", timing_metrics)
                if (width_proxy is not None):
                    proxy_width = width_proxy.predict(
                        len(example_cells),
                        sum(transistor_counts.get(
                            c.std_cell_type.type_name, 0)
                            for c in example_cells),
                        orig_unit_astran_area)
                    print("width proxy  COMPLEX"+str(pattern_trace_id),
                          ": predicted=", round(proxy_width, 3),
                          " actual=", new_unit_astran_area)
                # Structural layout sanity (P2 phase 0): degenerate /
                # wrong-height / off-grid / label-missing layouts are
                # unambiguous breakage and are excluded when gated.
                sanity_report = check_layout(
                    os.path.join(output_path, "COMPLEX"+str(pattern_trace_id)+".gds"),
                    log_path=os.path.join(
                        output_path, "COMPLEX"+str(pattern_trace_id)+".Astranlog"))
                if (not sanity_report.ok()):
                    print("layout sanity ", "COMPLEX"+str(pattern_trace_id),
                          ": ", sanity_report.as_dict())
                if (layout_sanity_gate and not sanity_report.ok()):
                    print("WARNING :", benchmark_name,
                          " COMPLEX"+str(pattern_trace_id),
                          " failed layout sanity; excluding the pattern")
                    continue
                # Liberty fragment for the generated cell (area from the
                # layout width, leakage/caps from the base lib, timing and
                # power from the LUT mini-STA sweep): the data a downstream
                # flow needs to reuse the cell.  Written on change only.
                lib_text, lib_report = generate_complex_liberty(
                    tmp_cluster_seq, "COMPLEX"+str(pattern_trace_id),
                    new_unit_astran_area, cell_timing_power,
                    cell_electrical_metrics, lib_functions)
                lib_path = output_path+"/COMPLEX"+str(pattern_trace_id)+".lib"
                if ((not os.path.exists(lib_path))
                        or open(lib_path).read() != lib_text):
                    with open(lib_path, 'w') as lib_fh:
                        lib_fh.write(lib_text)
                if (orig_unit_astran_area-new_unit_astran_area > 0):
                    unique_clusters = count_uncovered_clusters(
                        tmp_cluster_seq.pattern_clusters, covered_cell_ids)
                    if (unique_clusters == 0):
                        continue
                    complex_selection.append(("COMPLEX"+str(pattern_trace_id), unique_clusters, len(
                        tmp_cluster_seq.pattern_clusters[0].cell_ids), tmp_cluster_seq.pattern_extension_trace))
                    save_area += (orig_unit_astran_area-new_unit_astran_area) * \
                        unique_clusters
                    save_gscl_area += (orig_unit_gscl_area-new_unit_astran_area) * \
                        unique_clusters

            if (benchmark_failure):
                break

            print("save_area=", save_area, " / ", save_area/astran_area*100, "%")
            if (hooks is not None):
                hooks.metric({"benchmark": benchmark_name, "iteration": i,
                              "save_area": save_area,
                              "ratio": save_area/astran_area*100 if astran_area else 0.0,
                              "best": best_save_area})
            if (save_area > best_save_area):
                best_save_area = save_area
                last_save_gscl_area = save_gscl_area
                last_complex_selection = complex_selection
                if (hooks is not None):
                    hooks.record("best", {
                        "benchmark": benchmark_name,
                        "path": output_path+"/bestRecord-"+benchmark_name,
                        "save_area": save_area,
                        "ratio": save_area/astran_area*100 if astran_area else 0.0,
                        "selection": list(complex_selection)})
                file_result = open(output_path+"/bestRecord-"+benchmark_name, 'w')
                print(best_save_area, " <- compared to Astran GDS area",
                      file=file_result)
                print(best_save_area/astran_area*100,
                      "% <- compared to Astran GDS area", file=file_result)
                print(last_save_gscl_area,
                      " <- compared to GSCL GDS area", file=file_result)
                print(last_save_gscl_area/orig_area*100,
                      "% <- compared to GSCL GDS area", file=file_result)
                print(
                    "The generated complex cells are (name, clusterNum, cellNumInOneCluster, patternCode):", file=file_result)
                for complex_name in last_complex_selection:
                    print(complex_name, file=file_result)
                print("\n runtime:", time.time() -
                      start_time, " (s)", file=file_result)
                file_result.close()
            else:
                break

            # Beam growth (P0-3): grow the first grow_beam_width heads per
            # round instead of only the top one -- the candidate queue is
            # the beam.  Each grown branch is pre-screened by the benefit
            # estimator, so predicted-loss shapes (the COMPLEX10 pattern:
            # -56.05 um^2 on adder) never cost an ASTRAN run.
            grown_heads = 0
            for head_seq in list(cluster_seqs):
                if (grown_heads >= grow_beam_width):
                    break
                if (len(head_seq.pattern_clusters) == 0):
                    cluster_seqs.remove(head_seq)
                    continue
                head_size = len(head_seq.pattern_clusters[0].cell_ids)
                if (grown_heads == 0):
                    assert(ratio_thr > 0)
                    if (head_size*len(head_seq.pattern_clusters) < ratio_thr * len(cells)
                            and len(head_seq.pattern_clusters) < cnt_thr):
                        break
                if (head_size >= 10):
                    # a grown 11+-cell candidate is excluded at layout time
                    # anyway; growing it here would only churn the pool
                    cluster_seqs.remove(head_seq)
                    continue
                new_seq_of_clusters, pattern_num = grow_sequence_of_clusters(
                    blif_graph, head_seq, cluster_num, pattern_num,
                    paint_pattern=True, benefit_estimator=growth_benefit_estimator,
                    internalize_only=reuse_mode)
                cluster_seqs.remove(head_seq)
                cluster_seqs += new_seq_of_clusters
                grown_heads += 1
                if (len(new_seq_of_clusters) > 1):
                    # Export the grown netlist under the grown pattern's own
                    # id.  len(cluster_seqs) collides with ids already used by
                    # dumped patterns and silently overwrites their .sp files
                    # (observed: the grown 6-cell pattern overwrote
                    # COMPLEX9.sp while COMPLEX9.gds remained the 4-cell
                    # layout).
                    export_spice_netlist(new_seq_of_clusters[0], subckts,
                                       new_seq_of_clusters[0].pattern_clusters[0].cluster_type_id,
                                       output_path)

            cluster_seqs = remove_empty_seqs_and_disable_clusters(cluster_seqs)
            cluster_seqs = sort_pattern_cluster_seqs(cluster_seqs)

        if (benchmark_failure):
            continue

        counted_set = set()
        record_pattern_details = []
        detected_patterns.reverse()
        # bestRecord-seperate is opened only at the end: opening it with 'w'
        # up front erases the previous record, and a crash mid-loop would
        # leave an empty file (the writes below happen after the loop anyway).
        if (hooks is not None):
            hooks.stage("phase2", "running", "%d records" % len(detected_patterns))
        for target_pattern_trace in detected_patterns:
            if (hooks is not None):
                hooks.check_cancel()
            if (target_pattern_trace in counted_set):
                continue

            blif_graph, cells, netlist, std_cell_types_for_feature, dataset, max_label_index, cluster_seqs, cluster_num = load_data_and_preprocess(
                lib_file_name=cfg.liberty, blif_file_name=cfg.blif_dir+"/"+benchmark_name+".blif", start_time=start_time, bypass_initial_cluster=True)

            cluster_seqs, cluster_num = heuristic_label_initial_clusters_based_on(
                blif_graph, cells, netlist, target_pattern_trace, single_output_seeds=reuse_mode)
            end_time = time.time()
            print("heuristic_label_initial_clusters done. time esclaped: ",
                  end_time-start_time)

            orig_area = get_area(cells, gscl_area_by_type)
            print("original_area=", orig_area)

            output_path = "./outputs/"+benchmark_name+"/"
            mkdir(output_path)

            astran_area_by_type = load_astran_gds()
            astran_area = get_area(cells, astran_area_by_type)
            _flowLog.info("astran_area=%.2f", astran_area)

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
                    # Pop, don't just continue: re-testing the same oversized
                    # head would burn the whole iteration budget (see the
                    # phase-1 loop for the same pattern).
                    cluster_seqs = cluster_seqs[1:]
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
                        # grown beyond the dumped patterns: nothing to record
                        break
                    pattern_trace_id = dumped_patterns[tmp_cluster_seq.pattern_extension_trace]
                    pattern_subgraph = blif_graph.subgraph(
                        tmp_cluster_seq.pattern_clusters[0].cell_ids)

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

                    # print(best_save_area, " <- compared to Astran GDS area",
                    #       file=file_result)
                    # print(best_save_area/astran_area*100,
                    #       "% <- compared to Astran GDS area", file=file_result)
                    # print(last_save_gscl_area,
                    #       " <- compared to GSCL GDS area", file=file_result)
                    # print(last_save_gscl_area/orig_area*100,
                    #       "% <- compared to GSCL GDS area", file=file_result)
                    # print(
                    #     "The generated complex cells are (name, clusterNum, cellNumInOneCluster, patternCode):", file=file_result)

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
                    blif_graph, cluster_seq, cluster_num, pattern_num, paint_pattern=True, target_pattern_trace=target_pattern_trace, internalize_only=reuse_mode)

                # No netlist export here: phase 2 only computes the per-pattern
                # records, and exporting the grown netlist under a pattern_num-
                # derived id collides with ids already on disk (it silently
                # overwrote COMPLEX1.sp with another pattern in testing).

                cluster_seqs = cluster_seqs[1:]
                cluster_seqs += new_seq_of_clusters
                cluster_seqs = remove_empty_seqs_and_disable_clusters(cluster_seqs)
                cluster_seqs = sort_pattern_cluster_seqs(cluster_seqs)

        if (hooks is not None):
            hooks.result("record_pattern_details", record_pattern_details)
            hooks.result("best_save_area", best_save_area)
            hooks.result("runtime", time.time() - start_time)
            hooks.stage("mine", "done", "best save_area=%.2f" % best_save_area)
        record_pattern_details = sorted(record_pattern_details,
                                      key=lambda x: -x[0])
        file_result = open(
            output_path+"/bestRecord-seperate"+benchmark_name, 'w')
        print("| designOverallArea | saveArea | saveRatio | patternCnt | patternSize |"
              " patternCoverage | patternName | patternCode |",  file=file_result)
        for save_area, save_ratio, pattern_cnt, pattern_size, pattern_coverage, pattern_name, pattern_code in record_pattern_details:
            print('|', orig_area, '|', save_area, '|', save_ratio, '|', pattern_cnt, '|', pattern_size, '|',
                  pattern_coverage, '|', pattern_name, '|', pattern_code, '|', file=file_result)
        file_result.close()
