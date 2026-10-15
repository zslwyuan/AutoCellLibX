"""Extensions over smt_engine.netlist for big/irregular cells.

Spec: doc/STAGE3_BIGCELL_ENGINE.md section 2.1.  Everything here is
deterministic and pure; the structural model stays smt_engine.netlist's
(CellNetlist / find_series_chains / find_parallel_groups /
build_diffusion_blocks) -- this module only adds what big cells need:

1. ``fold_devices(netlist, ... -> leg_widths)``: up-front fold decision
   mirroring cellnetlst.cpp:254-286 -- width folding when ceil(W/0.19)
   exceeds the per-row diffusion budget, series-stack folding when a
   chain overflows one row half.  Folded devices get reproducible names
   ``name#legK``.  Runs BEFORE block building.
2. ``row_seeds(blocks)``: per-polarity initial block order, sorted by
   (-size, first-device-name) -- the same discipline as
   build_diffusion_blocks.
3. tree/branch blocks: connected components over pure internal degree-2/3
   nodes, DFS-flattened from the lowest-net leaf with lexicographic
   tie-breaks, so build_diffusion_blocks becomes total (every device in
   exactly one block) on all benchmark cells.  Property-tested over
   flow/outputs/*/*.sp.
"""

from smt_engine.netlist import DiffusionBlock  # noqa: F401  (re-export)


def fold_devices(netlist, max_leg_cols=5):
    """Return {device name: (legs, leg_width_cols)} with the fold applied.

    Not implemented yet -- stage 3 step 1 (agent: bigcell-placement).
    """
    raise NotImplementedError("netlist_ext.fold_devices")


def row_seeds(blocks_by_row):
    """Return {P_ROW: [DiffusionBlock, ...], N_ROW: [...]} seed orderings.

    Not implemented yet -- stage 3 step 1 (agent: bigcell-placement).
    """
    raise NotImplementedError("netlist_ext.row_seeds")
