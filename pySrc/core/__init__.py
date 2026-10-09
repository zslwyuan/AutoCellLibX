"""core: layered, modular core of the AutoCellLibX flow.

Layers (bottom-up):
  core.graph / pySrc.blif_graph_util   -- netlist data structures
  core.encoding / core.seeding       -- pattern encoding and initial
                                        clustering (split out of blif_preproc)
  core.growth                        -- pattern growth (split out of
                                        blif_pattern_growth)
  core.evaluate / core.external      -- evaluation and tool facades
  core.pipeline                      -- the mining pipeline (split out of
                                        main.py); main.py is a thin CLI
  core.config                        -- FlowConfig dataclass replacing the
                                        mutable global_variables module

Migration rule: legacy modules (blif_preproc, blif_pattern_growth, spice,
Astran, ...) keep their names as re-export shims so gui/ and tests keep
working; new code goes into core/.
"""
