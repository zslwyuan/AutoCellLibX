"""Negotiated-congestion grid router (stage 3, doc section 2.4 rung 2).

Faithful GraphRouter port (graphrouter.cpp:92-282) onto the merged grid:
per-column element graph from AutoCell::route (autocell2.cpp:243-474) with
GridRouter's 3-layer structure (gridrouter.cpp:33-47).  Arc costs ported
verbatim: horizontal 4 in-field / 16 over-diffusion (autocell2.cpp:28-33),
poly 6, poly-M1 contacts 20 over diffusion / 500 at I/O hubs (autocell2.cpp:
41-62).  Solver: route all nets permitting overlap, history += contested,
cost = arc + history * (users + 1), rip-up conflicted nets, <=8000 attempts,
then <=2 Steiner sweeps.  Deterministic: nets in sorted order, priority
queue ties broken by (node id, insertion counter), fixed attempt caps.

Output geometry must be consumable by smt_engine/gds.py's M2+via1 emitters
and pass smt_engine/verify.py's BFS unchanged.
"""

MAX_ATTEMPTS = 8000
STEINER_SWEEPS = 2


def route_cell(netlist, placement, width_cols, leg_widths):
    """Return a RouteResult-compatible route (segments/vias/contacts).

    Not implemented yet -- stage 3 step 4 (agent: bigcell-routing).
    """
    raise NotImplementedError("route_grid.route_cell")
