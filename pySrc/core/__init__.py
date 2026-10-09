"""core: layered, modular core of the AutoCellLibX flow.

Layers (bottom-up):
  core.graph / pySrc.BLIFGraphUtil   -- netlist data structures
  core.encoding / core.seeding       -- pattern encoding and initial
                                        clustering (split out of BLIFPreProc)
  core.growth                        -- pattern growth (split out of
                                        BLIFPatternGrowth)
  core.evaluate / core.external      -- evaluation and tool facades
  core.pipeline                      -- the mining pipeline (split out of
                                        main.py); main.py is a thin CLI
  core.config                        -- FlowConfig dataclass replacing the
                                        mutable globalVariables module

Migration rule: legacy modules (BLIFPreProc, BLIFPatternGrowth, spice,
Astran, ...) keep their names as re-export shims so gui/ and tests keep
working; new code goes into core/.
"""
