"""Ordering -> slot geometry: the shared math every bigcell module uses.

ASTRAN's terminal-slot model (doc/BIGCELL_SLOT_GEOMETRY.md, reverse-
engineered from flow/original_astran_cells GDS + autocell2.cpp): a
transistor's electrical width W is drawn VERTICALLY (the diffusion
strip's y-extent equals W); the horizontal footprint is a fixed slot
sequence.  One 0.19 um column = one (terminal | gate | terminal) slot
triple: a diffusion run of M transistors spans M columns with M+1
terminal slots on the column EDGES (x = c * GRID) and M gate slots at
the column CENTRES (x = (c+0.5) * GRID) -- exactly the column
conventions smt_engine.gds already uses (_track_x / _col_x).

An *ordering* is one row's diffusion-block sequence (a list of
DiffusionBlock with per-block orientation in BlockMember.left_net /
right_net).  Turning an ordering into geometry is pure and
deterministic:

- the IR keeps its shape, {Device: PlacedTransistor(row, start_col,
  legs, leg_width_cols)}, reinterpreted: ``legs`` is the fold-leg count
  and ``leg_width_cols`` is the slot run ONE leg occupies -- 1 column
  in the fixed slot model (netlist_ext.fold_devices emits ``(legs, 1)``;
  W no longer widens anything horizontally).  Since AUDIT 5.61's
  geometry round a member's run is ALSO free to exceed one column: a
  ``(1, k)`` member is a **k-column terminal region** -- the
  multi-column slot ASTRAN's LP compaction produces when it pushes
  gates apart for routing corridors (measured up to 4.3 pitches, doc/
  AUDIT_REPORT.md 5.60): terminals at the run's EDGES (start_col,
  start_col + legs*leg_width_cols), the gate at the run's centre
  column (start_col + legs*leg_width_cols//2 -- the same formula every
  consumer uses for the fold legs);
- a block of k members occupies k columns; facing-equal-net blocks
  share the boundary edge slot (the next block starts at the previous
  block's end column -- no gap), different nets insert one break
  column (BREAK_GAP_COLS, the wGaps slot);
- **row x-offsets** (AUDIT 5.61): every row's first edge column is a
  variable -- ``place_row(..., x_offset=...)`` / ``layout_cell(...,
  x_offsets=...)`` shift a row's whole run right by whole columns, the
  second geometry freedom ASTRAN's layouts use (independent row
  starts, measured up to 5.6 columns apart, NOR3X1's centred N chain
  being the textbook case).  Offsets are pure data: every start_col
  shifts by the same integer, so all same-row relationships (edge
  sharing, breaks, adjacency) are unchanged -- only the row-to-row
  alignment and the cell width (max end column) move.  Default 0 is
  byte-identical to the historical chain;
- cell width (um) = width_cols * GRID_UM + WIDTH_MARGIN_UM, the
  measured strip enclosure + pin-escape margins (section 2.5 of the
  design note) -- the constant reproduces every reference cell inside
  the 0.8-1.3x parity band.

The placement is consumable by ``smt_engine.verify.verify_cell`` (with
``slot_model=True``) and rendered by ``bigcell_engine.gds_cells``.
``smt_engine.route_model`` / ``route_grid.py`` still speak the exact
engine's column semantics; what the router must adapt is listed in the
design note's section 8.
"""

from smt_engine.layout_model import PlacedTransistor
from smt_engine.netlist import DiffusionBlock

GRID_UM = 0.19                    # the placement grid (invariant 2)
HEIGHT_UM = 2.47                  # GSCL45 CoreSite height, 13 v-grids
P_ROW = 0                         # upper row, PMOS
N_ROW = 1                         # lower row, NMOS
BREAK_GAP_COLS = 1                # diffusion break: one empty column

#: a device leg occupies one terminal/gate slot column; W is vertical.
DEFAULT_LEG_WIDTHS_MIN_COLS = 1

#: die-frame margins, measured on INVX1/NAND2X1 (design note 2.5): the
#: strip extends 0.0375 past the outermost contacts on each side, the
#: left pin-escape column is 0.2375 and the right margin 0.0725.
STRIP_ENC_UM = 0.075
ESCAPE_L_UM = 0.2375
RAIL_MARGIN_R_UM = 0.0725
WIDTH_MARGIN_UM = STRIP_ENC_UM + ESCAPE_L_UM + RAIL_MARGIN_R_UM   # 0.385

#: vertical anchors: the N strip's top edge sits S1DNWN = 0.0725 below
#: the nwell boundary (H/2 = 1.235), the P strip's bottom the same
#: distance above it; strips grow away from the boundary by W.
WELL_GAP_UM = 0.0725
MID_UM = HEIGHT_UM / 2.0

POWER_NETS = ("VCC", "GND", "VDD", "VSS")


def width_um(width_cols, grid_um=GRID_UM):
    """Cell width in um for a slot-model column count."""
    return width_cols * grid_um + WIDTH_MARGIN_UM


def default_leg_widths(devices):
    """No-fold default: every device is one leg of one column.

    ``devices`` is any iterable of smt_engine Device objects.  W does
    not widen the footprint in the slot model (it is the strip height);
    netlist_ext.fold_devices replaces this with the real fold decision.
    Deterministic and pure.
    """
    return {dev.name: (1, DEFAULT_LEG_WIDTHS_MIN_COLS) for dev in devices}


def block_width_cols(block, leg_widths):
    """Columns one DiffusionBlock occupies: the sum of its members' runs.

    ``leg_widths`` maps device name -> (legs, leg_width_cols).
    """
    total = 0
    for member in block.members:
        legs, cols = leg_widths[member.device.name]
        total += legs * cols
    return total


def place_row(row, blocks, leg_widths, x_offset=0):
    """Place one row's block sequence; returns (placements, row_end_col).

    ``placements`` maps Device -> PlacedTransistor for every device in
    ``blocks``.  ``row_end_col`` is the row's width in columns AND the
    index of its final terminal edge (edge e is column e's left
    boundary).  ``x_offset`` shifts the whole run right by that many
    columns (AUDIT 5.61's row x-offset variable): every start_col gains
    the same integer, the end column becomes ``x_offset + row width``.
    Default 0 is the historical behaviour byte-for-byte.  Pure function
    of the block order: identical input order always yields identical
    columns (invariant 9).
    """
    placements = {}
    col = x_offset
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


def layout_cell(ordering_p, ordering_n, leg_widths, x_offsets=None):
    """Place both rows; returns (placements, width_cols).

    ``ordering_p``/``ordering_n`` are the P-row (row 0) and N-row (row 1)
    block sequences.  Width is the max row end -- the rows need not be
    equal; the GDS writer sees the true asymmetric width, as ASTRAN's
    does.  ``x_offsets`` optionally supplies per-row x-offsets as
    ``(p_offset, n_offset)`` (AUDIT 5.61: ASTRAN's rows start at
    different x -- the model pins both at column 0 by default, which
    stays the exact historical behaviour when ``x_offsets`` is None).
    """
    if not ordering_p or not ordering_n:
        raise ValueError("both rows need at least one diffusion block")
    if x_offsets is None:
        off_p = off_n = 0
    else:
        off_p, off_n = x_offsets
    placements = {}
    width = 0
    row_placements, row_end = place_row(P_ROW, ordering_p, leg_widths,
                                        x_offset=off_p)
    placements.update(row_placements)
    width = max(width, row_end)
    row_placements, row_end = place_row(N_ROW, ordering_n, leg_widths,
                                        x_offset=off_n)
    placements.update(row_placements)
    width = max(width, row_end)
    return placements, width


# --------------------------------------------------------------------------
# slot derivation: edges, gates, contacts (shared by gds_cells and
# smt_engine.verify's slot_model path)
# --------------------------------------------------------------------------

def row_edges(ordering, leg_widths, x_offset=0):
    """One row's terminal-edge slots: [(edge_col, net, width_cols)].

    One entry per distinct SLOT: consecutive members sharing an edge
    produce a single entry (shared junction), so a net appearing at
    several slot columns is genuinely multi-region.  The list is
    ordered left to right.  ``x_offset`` shifts the walk's origin (the
    same integer place_row applied), so the edges match a placed row
    (AUDIT 5.61).  Pure; deterministic in the ordering.
    """
    edges = []
    col = x_offset
    prev_right = None
    for block in ordering:
        if prev_right is not None and block.members[0].left_net != prev_right:
            col += BREAK_GAP_COLS
        for member in block.members:
            legs, cols = leg_widths[member.device.name]
            w = legs * cols
            if not edges or edges[-1][0] != col:
                edges.append((col, member.left_net, w))
            col += w
            edges.append((col, member.right_net, w))
        prev_right = block.members[-1].right_net
    return edges


def row_gate_columns(ordering, leg_widths, x_offset=0):
    """One row's gate slots: [(col, gate_net, device)] per leg.

    Leg j of a member at column c sits at column ``c + j*leg_width_cols``
    with its poly stripe at the leg run's CENTRE column
    (``c + j*cols + cols//2``) -- the same centre formula
    gate_access_points, route_model/verify's gate maps and gds_cells'
    gate-contact walk use (a k>1 leg is a multi-column terminal region
    whose gate sits at its centre; the legacy ``c + j*cols`` agreed
    with the centre formula only while every leg was one column wide).
    Columns come from the same walk place_row does (blocks, breaks,
    member runs), shifted by ``x_offset`` exactly like place_row.
    """
    out = []
    col = x_offset
    prev_right = None
    for block in ordering:
        if prev_right is not None and block.members[0].left_net != prev_right:
            col += BREAK_GAP_COLS
        for member in block.members:
            legs, cols = leg_widths[member.device.name]
            for j in range(legs):
                out.append((col + j * cols + cols // 2,
                            member.device.gate, member.device))
            col += legs * cols
        prev_right = block.members[-1].right_net
    return out


def contact_nets(ordering, netlist, leg_widths, x_offset=0):
    """Nets that carry diffusion contacts in ``ordering``'s row.

    ASTRAN contacts a terminal slot when the net needs M1 access there
    (NAND2X1's P-row middle slot is the output Y; NOR2X1's internal Z
    carries none): exposed nets (block ends, per smt_engine's
    exposed_net_set), power nets, and multi-region nets -- a net
    occupying several slots of the row must have its regions tied.
    Returns a frozenset of net names.  ``x_offset`` only shifts the
    slots (the net multiset is shift-invariant); it is accepted so the
    signature matches row_edges/row_gate_columns.
    """
    from smt_engine.netlist import exposed_net_set
    exposed = exposed_net_set(netlist)
    counts = {}
    for edge, net, _w in row_edges(ordering, leg_widths, x_offset):
        counts[net] = counts.get(net, 0) + 1
    return frozenset(
        net for net, n in counts.items()
        if n > 1 or net in exposed or net in POWER_NETS)


def slot_diffusion_access(netlist, placement, orderings, leg_widths):
    """Slot-model diffusion access points: ({net: [(edge_col, dev)]},
    {power_net: [(edge_col, dev)]}).

    Every member edge slot whose net is contactable (``contact_nets``)
    is an access point at its TRUE edge column -- the exact engine's
    diffusion_access_points insets a width-1 device's right access into
    its own column, which is wrong once a leg is one slot wide.  The
    ``orderings`` pair supplies the rows' block sequences (the
    orientation-aware view the placement was built from).  The edge
    columns come from the PLACEMENT itself (start_col/end_col), so a
    row x-offset place_row applied is reproduced exactly (AUDIT 5.61).
    Deterministic (sorted output).
    """
    contactable = (contact_nets(orderings[0], netlist, leg_widths)
                   | contact_nets(orderings[1], netlist, leg_widths))
    signal = {}
    power = {}
    for row_ordering in orderings:
        for block in row_ordering:
            for member in block.members:
                p = placement[member.device]
                for net, edge in ((member.left_net, p.start_col),
                                  (member.right_net, p.end_col)):
                    if net not in contactable:
                        continue
                    dst = power if net in POWER_NETS else signal
                    dst.setdefault(net, []).append((edge, member.device))
    key = lambda t: (t[0], t[1].name)                     # noqa: E731
    return ({n: sorted(set(pts), key=key) for n, pts in signal.items()},
            {n: sorted(set(pts), key=key) for n, pts in power.items()})
