"""Evaluation layer facade (ARCHITECTURE).

One import surface for every evaluation concern the pipeline uses:
electrical metrics, LUT timing/power, routability, layout sanity,
synthesis-reuse eligibility, the learned width proxy, the benefit
estimator, and liberty characterisation of generated cells.  The
implementations stay in their single-purpose modules (pySrc/ root) --
this facade is the layer boundary so pipeline and future consumers
never import them directly.
"""

from benefit import ShrinkModel, make_growth_benefit_estimator
from electrical import load_cell_electrical_metrics, pattern_electrical_metrics
from timing_power import (bilinear, load_timing_power, pattern_timing_power,
                          stage_delay_slew, stage_energy)
from routability import (RoutabilityMetrics, load_cell_routability,
                         parse_astran_log_routability)
from reuse import (function_complexity, function_to_verilog,
                   interface_output_count, output_functions, reuse_eligible,
                   verilog_design_for_function)
from width_proxy import (WidthProxy, collect_samples,
                         count_transistors_per_type, evaluate_loo,
                         load_width_proxy, make_proxy_benefit_estimator,
                         save_width_proxy, train_or_load_width_proxy,
                         width_proxy_model_stale)
from layout_sanity import (ASTRAN_GDS_UNITS_PER_UM, check_layout)
from liberty_gen import (generate_complex_liberty,
                         generate_liberty_for_spice_file, liberty_pin_name,
                         load_liberty_functions, rebuild_cluster_from_spice)
from pdk_config import (PdkProfile, get_pdk, list_pdks, multi_row_variant,
                        pdk_geometry_dict)
