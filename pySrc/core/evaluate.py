"""Evaluation layer facade (ARCHITECTURE).

One import surface for every evaluation concern the pipeline uses:
electrical metrics, LUT timing/power, routability, layout sanity,
synthesis-reuse eligibility, the learned width proxy, the benefit
estimator, and liberty characterisation of generated cells.  The
implementations stay in their single-purpose modules (pySrc/ root) --
this facade is the layer boundary so pipeline and future consumers
never import them directly.
"""

from benefit import ShrinkModel, makeGrowthBenefitEstimator
from electrical import loadCellElectricalMetrics, patternElectricalMetrics
from timing_power import (bilinear, loadTimingPower, patternTimingPower,
                          stageDelaySlew, stageEnergy)
from routability import (RoutabilityMetrics, loadCellRoutability,
                         parseAstranLogRoutability)
from reuse import (functionComplexity, functionToVerilog,
                   interfaceOutputCount, outputFunctions, reuseEligible,
                   verilogDesignForFunction)
from width_proxy import (WidthProxy, collectSamples,
                         countTransistorsPerType, evaluateLOO,
                         makeProxyBenefitEstimator)
from layout_sanity import (ASTRAN_GDS_UNITS_PER_UM, checkLayout)
from liberty_gen import (generateComplexLiberty,
                         generateLibertyForSpiceFile, libertyPinName,
                         loadLibertyFunctions, rebuildClusterFromSpice)
from pdk_config import (PdkProfile, getPdk, listPdks, multiRowVariant,
                        pdkGeometryDict)
