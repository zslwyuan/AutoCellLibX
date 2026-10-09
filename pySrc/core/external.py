"""External-tool layer facade (ARCHITECTURE).

One import surface for the tools the flow drives: ASTRAN (layout
synthesis + area reads), gds_analysis (baseline widths), Yosys
(stat cross-checks, abc re-mapping evaluation).  Implementations stay
in their own modules; pipeline and consumers go through this facade.
"""

from astran import (ASTRAN_BUILD_PATH, ASTRAN_CELLS_HEIGHT,
                    ASTRAN_CELL_TEMPLATE, ASTRAN_HGRID, ASTRAN_NWELL_POS,
                    ASTRAN_SUPPLY_SIZE, ASTRAN_TECHNOLOGY, ASTRAN_VGRID,
                    GUROBI_CL, astranLayoutIsStale, buildAstranCommands,
                    loadAstranArea, runAstranForNetlist)
from gds_analysis import loadAstranGDS, loadOrignalGSCL45nmGDS
from yosys_import import (compareCellCounts, compareWithFlowArea,
                          findYosys, parseStatJson, runYosysStat)
from yosys_eval import (buildExtendedLiberty, compareMappedArea,
                        evaluateDesignSavings, runYosysMappedArea)
