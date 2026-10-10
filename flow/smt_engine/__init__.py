"""SMT cell-synthesis engine: complete SAT encoding of folding + diffusion
sharing + placement + routing (P2-13, full engine).

Two-stage exact pipeline over the routed grid:

- stage 1 (layout_model): joint folding + placement -- series chains and
  parallel groups abut and share diffusion (net-pair alternating
  orientation), diffusion breaks between different-net block ends, two
  rows per polarity, gate alignment as a soft objective, and
  access-point column exclusivity (one vertical M1 stripe per column);
- stage 2 (route_model): grid routing -- vertical stripes per column
  (rails 0..5), horizontal segments on 4 cell rails, gate contacts on
  segment/poly crossings, connectivity by full column-interval coverage
  with per-pair bridge segments, crossing safety against foreign
  stripes, power rails fixed at the row edges.

Output is GDS on the ASTRAN layer map (gds.py) consumable by the existing
layout-sanity and pin-accessibility checkers, plus a structural
self-check (verify.py).

The engine is a *generator*, not a replacement for the flow: it solves
regular cells up to 12+ transistors (NAND3..NAND6 all close the loop,
M1-only) and irregular cells within budget; the reference
implementation (smt_cell_placer) stays as the ideal-width scorer.  See
doc/RESEARCH_AND_OPTIMIZATION.md section 4.2 for the roadmap.
"""

from .layout_model import (DEFAULT_GRID_UM, MAX_LEG_UM, MIN_LEG_UM,
                           PlacementSolution, PlacedTransistor, solve_layout)
from .netlist import (BlockMember, CellNetlist, DiffusionBlock,
                      build_diffusion_blocks, diffusion_access_points,
                      exposed_net_set, find_parallel_groups,
                      find_series_chains, gate_access_points)
from .route_model import (GND_RAIL, N_RAILS, VCC_RAIL, RouteResult,
                          RoutingModel, build_routing_model, device_rail,
                          solve_routing)
from . import verify
from smt_cell_placer import parse_spice_subckt

__all__ = [
    "CellNetlist", "PlacementSolution", "PlacedTransistor", "RouteResult",
    "solve_layout", "solve_routing", "parse_spice_subckt",
    "synth_cell", "SynthResult", "verify",
]


class SynthResult(object):
    """One synthesis run: netlist + stage results + verification report."""

    def __init__(self, netlist, layout, route, report):
        self.netlist = netlist
        self.layout = layout
        self.route = route
        self.report = report

    @property
    def ok(self):
        return (self.layout.width_cols is not None
                and self.route is not None and self.route.ok
                and self.report is not None and self.report.ok())


def synth_cell(spText, grid_um=DEFAULT_GRID_UM, height_um=2.47,
               layout_time_s=60.0, route_time_s=60.0):
    """Run both stages; returns SynthResult.

    The route is verified structurally (verify.verify_cell); a failed
    verification is reported in ``report`` -- never silently swallowed.
    """
    netlist = CellNetlist(parse_spice_subckt(spText))
    layout = solve_layout(netlist, grid_um=grid_um,
                          time_limit_s=layout_time_s)
    if (layout.width_cols is None):
        return SynthResult(netlist, layout, None, None)
    route = solve_routing(netlist, layout.devices,
                          time_limit_s=route_time_s)
    if (not route.ok):
        return SynthResult(netlist, layout, route, None)
    report = verify.verify_cell(netlist, layout.devices, route,
                                grid_um=grid_um, height_um=height_um)
    return SynthResult(netlist, layout, route, report)
