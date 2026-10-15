"""Big-cell engine orchestration: the ladder between the exact engine and
ASTRAN (stage 3, doc section 2.4 / section 5).

smt-exact (route_model, W<=14 and N<=12, 60 s) -> route_grid (workhorse) ->
per-cell ASTRAN fallback (stays until the quality gates in doc section 4
are met).  One cell per call, same artifact contract as astran_queue
(.sp/.gds pairs, .gds fresher than .sp, invariant 7).
"""


def synth_cell(netlist, leg_widths=None, exact_budget_s=60.0,
               grid_budget_s=120.0):
    """Return (placement, route, meta) or raise UnsupportedCell.

    Not implemented yet -- wired by the integrator once place/route land
    (agents: bigcell-placement, bigcell-routing).
    """
    raise NotImplementedError("engine.synth_cell")
