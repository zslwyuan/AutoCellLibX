"""Threshold-Accept placement refinement (stage 3, doc section 2.2 B).

Faithful port of ASTRAN's representation and move set (placer.cpp +
thresholdaccept.h) at diffusion-block granularity: dual-row block ordering,
shift/mirror moves with P/N/both at 1/4 / 1/4 / 1/2, GAP padding.  The cost
function transfers ASTRAN's terms term-for-term (width, diffusion breaks,
gate mismatches, routing span, bounding-box congestion -- cellnetlst.cpp:
364-460) with two upgrades:

- incremental cost evaluation: cache per-column net-edge/gate arrays and
  update only the moved segment's affected columns; full recompute only at
  iteration boundaries, asserted equal to the incremental sum in tests;
- determinism: content-hashed per-cell RNG seed, iteration budgets only
  (thresholdaccept.h's 17500 s wall-clock escape is explicitly NOT ported),
  sorted iteration everywhere (invariant 9).
"""

COST_WEIGHTS = {"width": 1000, "gaps": 100, "gate_mismatch": 10,
                "span": 1, "congestion": 1}


def sa_refine(ordering_p, ordering_n, netlist, leg_widths, iterations=None):
    """Return (ordering_p, ordering_n, cost_breakdown) after refinement.

    Not implemented yet -- stage 3 step 3 (agent: bigcell-placement).
    """
    raise NotImplementedError("place_sa.sa_refine")
