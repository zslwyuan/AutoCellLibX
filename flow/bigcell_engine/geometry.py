"""Ordering -> column geometry: the shared math every bigcell module uses.

An *ordering* is one row's diffusion-block sequence (a list of
DiffusionBlock with per-block orientation already fixed -- the orientation
lives in BlockMember.left_net/right_net, smt_engine/netlist.py:154-203).
Turning an ordering into geometry is pure and deterministic:

- each member device occupies ``leg_width_cols[device.name]`` columns and
  ``legs`` legs (the fold decision, made up front by netlist_ext.py);
  the default is one leg of ceil(W / GRID) columns, clamped to at least
  the minimum two-column contactable width;
- blocks abut sharing diffusion when the previous block's right_net equals
  the next block's left_net, otherwise one break-gap column is inserted
  (DIFF_BREAK_UM, layout_model.py:35);
- a device's PlacedTransistor start_col is its block's start plus the
  widths of the members before it inside the block.

The resulting placement is directly consumable by
``smt_engine.route_model.solve_routing`` and ``smt_engine/gds.py``.
"""

import math

from smt_engine.layout_model import PlacedTransistor
from smt_engine.netlist import DiffusionBlock

GRID_UM = 0.19                    # the placement grid (invariant 2)
HEIGHT_UM = 2.47                  # GSCL45 CoreSite height, 13 v-grids
P_ROW = 0                         # upper row, PMOS
N_ROW = 1                         # lower row, NMOS
BREAK_GAP_COLS = 1                # DIFF_BREAK_UM = one grid column

#: a device leg must be contactable: below 2 columns a gate has no room
#: for its contact stripe (layout_model's mixed-width INV lesson).
DEFAULT_LEG_WIDTHS_MIN_COLS = 2


def default_leg_widths(devices):
    """No-fold default: one leg per device, ceil(W / GRID) columns each.

    ``devices`` is any iterable of smt_engine Device objects.  Deterministic
    and pure; netlist_ext.py replaces this with the real fold decision.
    """
    out = {}
    for dev in devices:
        cols = max(DEFAULT_LEG_WIDTHS_MIN_COLS,
                   int(math.ceil(float(dev.width_um) / GRID_UM)))
        out[dev.name] = (1, cols)
    return out


def block_width_cols(block, leg_widths):
    """Columns one DiffusionBlock occupies: the sum of its members' widths.

    ``leg_widths`` maps device name -> (legs, leg_width_cols).
    """
    total = 0
    for member in block.members:
        legs, cols = leg_widths[member.device.name]
        total += legs * cols
    return total


def place_row(row, blocks, leg_widths):
    """Place one row's block sequence; returns (placements, row_end_col).

    ``placements`` maps Device -> PlacedTransistor for every device in
    ``blocks``.  Pure function of the block order: identical input order
    always yields identical columns (invariant 9).
    """
    placements = {}
    col = 0
    prev_right = None
    for block in blocks:
        if prev_right is not None and block.members[0].left_net != prev_right:
            col += BREAK_GAP_COLS
        for member in block.members:
            legs, cols = leg_widths[member.device.name]
            placements[member.device] = PlacedTransistor(
                row, col, legs, cols)
            col += legs * cols
        prev_right = block.members[-1].right_net
    return placements, col


def layout_cell(ordering_p, ordering_n, leg_widths):
    """Place both rows; returns (placements, width_cols).

    ``ordering_p``/``ordering_n`` are the P-row (row 0) and N-row (row 1)
    block sequences.  Width is the max row end -- the rows need not be
    equal; row legalization pads nothing here (the router and the GDS
    writer see the true asymmetric width, as ASTRAN's do).
    """
    if not ordering_p or not ordering_n:
        raise ValueError("both rows need at least one diffusion block")
    placements = {}
    width = 0
    row_placements, row_end = place_row(P_ROW, ordering_p, leg_widths)
    placements.update(row_placements)
    width = max(width, row_end)
    row_placements, row_end = place_row(N_ROW, ordering_n, leg_widths)
    placements.update(row_placements)
    width = max(width, row_end)
    return placements, width
