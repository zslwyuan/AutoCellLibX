"""External-tool layer facade (ARCHITECTURE).

One import surface for the tools the flow drives: ASTRAN (layout
synthesis + area reads), gds_analysis (baseline widths), Yosys
(stat cross-checks, abc re-mapping evaluation).  Implementations stay
in their own modules; pipeline and consumers go through this facade.
"""

from astran import (ASTRAN_BUILD_PATH, ASTRAN_CELLS_HEIGHT,
                    ASTRAN_CELL_TEMPLATE, ASTRAN_HGRID, ASTRAN_NWELL_POS,
                    ASTRAN_SUPPLY_SIZE, ASTRAN_TECHNOLOGY, ASTRAN_VGRID,
                    GUROBI_CL, astran_layout_is_stale, build_astran_commands,
                    load_astran_area, run_astran_for_netlist)
from gds_analysis import load_astran_gds, load_original_gscl45_gds
from yosys_import import (compare_cell_counts, compare_with_flow_area,
                          find_yosys, parse_stat_json, run_yosys_stat)
from yosys_eval import (build_extended_liberty, compare_mapped_area,
                        evaluate_design_savings, run_yosys_mapped_area)
