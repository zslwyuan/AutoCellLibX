"""The shared die-orientation view of a placed cell.

A placement IR ({Device: PlacedTransistor}) carries column positions but
no orientation: place_row always lays a diffusion block's members out in
the block's own member-list order, and a MIRRORED block (netlist_ext.
mirror_block, place_sa's mirror move) carries the reversed list with
every member's left/right edge nets swapped.  Consumers that derive
per-net geometry from the base smt_engine.netlist walk alone therefore
scramble net->column on SA-mirrored placements -- the defect that once
built power stripes on foreign signal columns ("terminal clash at
('M1', 4, 8): cl0#Y and VCC", route_grid / verify false positives).

This module reconstructs the DIE view from (netlist, placement) alone,
pure and deterministic (AGENTS.md invariants 8/9):

- a multi-member block is mirrored exactly when its members' placement
  start_cols DESCEND in the block's own member order;
- a single-member block's flip is invisible in the column order, so it
  is recovered from the abutment constraints geometry.place_row encoded
  into the inter-block gaps of each row (gap 0 <=> the facing end nets
  are equal, one break column <=> they differ).  Orientations propagate
  to a fixpoint; singles no constraint pins stay PRISTINE -- the one
  case the die cannot distinguish, where every consumer of this module
  makes the same assumption (so the router and the verifier always
  agree, even there).

Consumers: bigcell_engine.route_grid (terminal slots on the die
orientation) and smt_engine.verify (orientation-aware diffusion access
points); both must see the SAME view for the same placement, which is
why the reconstruction lives here and not in either engine.
"""

import itertools

from .netlist import build_diffusion_blocks, exposed_net_set

#: the diffusion-break gap in columns (geometry.BREAK_GAP_COLS and the
#: exact engine's DIFF_BREAK_UM/grid both equal one 0.19 um column).
DEFAULT_BREAK_COLS = 1

_POWER_NAMES = ("VCC", "GND", "VDD", "VSS")


class DieBlockView(object):
    """One diffusion block's DIE state: members in die order + flip.

    ``members`` are the block's BlockMembers reordered the way the die
    lays them out; ``flipped`` is True (mirrored), False (pristine) or
    None (the die cannot distinguish -- pristine assumed).
    """

    __slots__ = ("block", "members", "flipped")

    def __init__(self, block, members, flipped):
        self.block = block
        self.members = list(members)
        self.flipped = flipped

    @property
    def kind(self):
        return self.block.kind


def is_slot_placement(placement):
    """Whether ``placement`` speaks the slot geometry model.

    The slot chain (geometry.fold_devices / default_leg_widths) emits
    ``leg_width_cols == 1`` for EVERY device -- one leg occupies one
    (terminal | gate | terminal) column, W is drawn vertically.  The
    exact engine's device-width model emits ``leg_width_cols >= 2`` for
    any electrical width above one grid pitch.  The empty placement is
    not slot-model (nothing to route).
    """
    return bool(placement) and all(
        p.leg_width_cols == 1 for p in placement.values())


def die_orientation(netlist, placement, break_cols=DEFAULT_BREAK_COLS):
    """Per-block die view: [DieBlockView] in build_diffusion_blocks order.

    Pure and deterministic: constraints are visited in a fixed sorted
    order, every pin is permanent, and the joint enumeration of the
    remaining unknowns takes the pristine-first vector (per block index
    order).  Identical inputs give an identical output (invariant 9).
    """
    blocks = build_diffusion_blocks(netlist)
    flipped = []                      # block index -> True / False / None
    die_members = []                  # block index -> members in die order
    for blk in blocks:
        starts = [placement[m.device].start_col for m in blk.members]
        die = sorted(blk.members,
                     key=lambda m: (placement[m.device].start_col,
                                    m.device.name))
        die_starts = [placement[m.device].start_col for m in die]
        die_members.append(die)
        if len(blk.members) == 1:
            flipped.append(None)
        elif die_starts == starts:
            flipped.append(False)
        elif die_starts == starts[::-1]:
            flipped.append(True)
        else:
            flipped.append(None)      # illegal placement: leave to defaults

    def end_nets(idx, flip):
        """(die_left, die_right) end nets of block idx under flip."""
        blk = blocks[idx]
        left = blk.members[0].left_net
        right = blk.members[-1].right_net
        return (right, left) if flip else (left, right)

    # per-row die sequences and the gap constraints between neighbours
    rows = {}
    for idx, die in enumerate(die_members):
        rows.setdefault(placement[die[0].device].row, []).append(idx)
    constraints = []
    for row in sorted(rows):
        seq = sorted(rows[row],
                     key=lambda i: placement[die_members[i][0].device]
                     .start_col)
        for a, b in zip(seq, seq[1:]):
            gap = (placement[die_members[b][0].device].start_col
                   - placement[die_members[a][-1].device].end_col)
            if gap == 0 or gap == break_cols:
                constraints.append((a, b, gap == 0))

    def satisfied(ia, ib, equal, flips):
        """Whether the constraint holds under the given orientations."""
        need = end_nets(ia, flips[ia])[1]             # a's die_right
        return (end_nets(ib, flips[ib])[0] == need) == equal

    # 1) propagate pinned blocks into unknown singles (fixpoint)
    changed = True
    while changed:
        changed = False
        for ia, ib, equal in constraints:
            for x, y in ((ia, ib), (ib, ia)):
                if flipped[x] is None or flipped[y] is not None:
                    continue
                ok = []
                for cand in (False, True):
                    trial = {ia: flipped[ia], ib: flipped[ib]}
                    trial[y] = cand
                    if satisfied(ia, ib, equal, trial):
                        ok.append(cand)
                if len(ok) == 1:
                    flipped[y] = ok[0]
                    changed = True

    # 2) remaining unknowns that any constraint touches: the die cannot
    # pin them one at a time (e.g. two abutting singles), so enumerate
    # their joint assignments deterministically -- pristine first, per
    # block index order -- and take the first vector that satisfies every
    # constraint whose both sides resolve
    unknown = sorted(i for i, f in enumerate(flipped) if f is None
                     and any(i in c[:2] for c in constraints))
    if unknown and len(unknown) <= 16:
        for vector in itertools.product((False, True), repeat=len(unknown)):
            trial = dict(zip(unknown, vector))
            ok = True
            for ia, ib, equal in constraints:
                fa = trial.get(ia, flipped[ia])
                fb = trial.get(ib, flipped[ib])
                if fa is None or fb is None:
                    continue              # touches an unpinned outsider
                if ((end_nets(ia, fa)[1] == end_nets(ib, fb)[0]) != equal):
                    ok = False
                    break
            if ok:
                for i, f in zip(unknown, vector):
                    flipped[i] = f
                break
    # 3) anything still unknown is orientation-invisible in the die:
    # pristine (the shared convention every consumer assumes)
    return [DieBlockView(blocks[idx], die_members[idx], flipped[idx])
            for idx in range(len(blocks))]


def die_orientation_map(netlist, placement, break_cols=DEFAULT_BREAK_COLS):
    """{device name: (die_left_net, die_right_net)} per die_orientation."""
    mapping = {}
    for view in die_orientation(netlist, placement, break_cols):
        for member in view.members:
            mapping[member.device.name] = (
                (member.right_net, member.left_net) if view.flipped
                else (member.left_net, member.right_net))
    return mapping


def die_slot_access_points(netlist, placement,
                           break_cols=DEFAULT_BREAK_COLS):
    """Slot-model diffusion access points on the DIE orientation.

    Returns ({signal_net: [(edge_col, device)]},
    {power_net: [(edge_col, device)]}).

    Every member's terminals sit on its TRUE edge columns (edge e is the
    left boundary of column e: left access at ``start_col``, right access
    at ``start_col + legs*leg_width_cols`` -- the exact engine's walk
    insets a width-1 leg's right access into its own column, which
    collapses both terminals onto one column).  A net is contactable when
    it is exposed (a block end somewhere, smt_engine's exposed_net_set),
    a power net, or MULTI-REGION: occupying several edge slots of one row
    (its regions must stay tied by metal).  Consecutive members sharing
    an edge produce a single slot, exactly like geometry.row_edges.

    Deterministic: rows and devices in sorted order, dedup + sort by
    (column, device name).
    """
    exposed = exposed_net_set(netlist)
    orientation = die_orientation_map(netlist, placement, break_cols)
    signal = {}
    power = {}
    rows = sorted({p.row for p in placement.values()})
    for row in rows:
        devs = sorted((d for d in netlist.devices
                       if placement[d].row == row),
                      key=lambda d: (placement[d].start_col, d.name))
        slots = []                    # (edge_col, net, device) left->right
        for dev in devs:
            p = placement[dev]
            w = p.legs * p.leg_width_cols
            lnet, rnet = orientation[dev.name]
            if not slots or slots[-1][0] != p.start_col \
                    or slots[-1][1] != lnet:
                slots.append((p.start_col, lnet, dev))
            slots.append((p.start_col + w, rnet, dev))
        counts = {}
        for _c, net, _d in slots:
            counts[net] = counts.get(net, 0) + 1
        contactable = {n for n, k in counts.items() if k > 1}
        contactable |= exposed
        contactable |= set(_POWER_NAMES)
        for c, net, dev in slots:
            if net not in contactable:
                continue
            dst = power if net in _POWER_NAMES else signal
            dst.setdefault(net, []).append((c, dev))
    key = lambda t: (t[0], t[1].name)                     # noqa: E731
    return ({n: sorted(set(pts), key=key) for n, pts in signal.items()},
            {n: sorted(set(pts), key=key) for n, pts in power.items()})
