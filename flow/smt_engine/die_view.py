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

The reconstruction above models the die as an ORIENTATION of the base
smt_engine.netlist decomposition.  Tree-coupled arrangements
(bigcell_engine.netlist_ext's "tree" blocks) violate that model: the
tree rearranges WHICH device sits at which block boundary, so no
orientation assignment of the pristine decomposition is consistent with
the die -- the abutment constraints contradict each other and the
fixpoint silently leaves the members pristine, scrambling net->column
across the rearranged region (the phantom "terminal clash at
('M1', 4, 1): cl3#Y and VCC" that blocked the 22-36T COMPLEX class).
The reconstruction therefore CHECKS its own output against the die's
device-level adjacency (facing nets equal across a 0 gap / different
across a break) and, when the pristine model cannot explain the die,
falls back to a TRAIL reconstruction: per-device orientation unknowns
over the device's own {source, drain} terminals, pinned by the same
adjacency constraints -- which the rearrangement's shared internal
edges pin exactly where the die can distinguish them.  Callers holding
the orientation-aware block view the placement was actually built from
(bigcell_engine.engine meta["blocks"]) can pass it as ``blocks``: it is
consulted ONLY in the fallback, replacing the trail solution with the
exact die state -- on every placement the pristine model explains (all
exact-engine placements, all non-tree slot placements) the historical
reconstruction is returned untouched, so routes stay byte-identical and
the router and the verifier keep seeing the same view even where the
die cannot distinguish a single's flip.

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
    None (the die cannot distinguish -- pristine assumed).  ``flips``
    optionally carries PER-MEMBER flips (aligned with ``members``) for
    the trail reconstruction, where a rearranged block's members need
    not all face the same way; None means "use ``flipped`` for every
    member" (the historical block-level behaviour).
    """

    __slots__ = ("block", "members", "flipped", "flips")

    def __init__(self, block, members, flipped, flips=None):
        self.block = block
        self.members = list(members)
        self.flipped = flipped
        self.flips = list(flips) if flips is not None else None

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


def die_orientation(netlist, placement, break_cols=DEFAULT_BREAK_COLS,
                    blocks=None):
    """Per-block die view: [DieBlockView] in build_diffusion_blocks order.

    Pure and deterministic: constraints are visited in a fixed sorted
    order, every pin is permanent, and the joint enumeration of the
    remaining unknowns takes the pristine-first vector (per block index
    order).  Identical inputs give an identical output (invariant 9).

    The reconstruction models the die as an orientation of the base
    decomposition; its output is CHECKED against the die's device-level
    adjacency (facing nets equal across a 0 gap, different across a
    break).  On the pass -- every exact-engine placement and every
    non-tree slot placement -- the historical result is returned
    untouched (byte-identical).  On the fail (the placement is a TREE
    arrangement no orientation of the pristine decomposition explains)
    the view is rebuilt: from ``blocks`` -- the orientation-aware view
    the placement was actually built from, whose members already carry
    their die edge nets -- when supplied, else from the device TRAILS
    (:func:`_trail_views`).
    """
    blocks = _check_blocks_arg(netlist, placement, blocks)
    views = _reconstruct_views(netlist, placement, break_cols)
    adjacency = _device_adjacency(netlist, placement, break_cols)
    if _map_satisfies_adjacency(adjacency, _views_to_map(views)):
        return views
    if blocks is not None:
        return _blocks_views(blocks, placement)
    return _trail_views(netlist, placement, break_cols)


def _check_blocks_arg(netlist, placement, blocks):
    """The orientation-aware block view, or None.

    Accepted: any iterable of DiffusionBlock-compatible objects covering
    exactly the netlist's devices once (bigcell_engine.engine's
    meta["blocks"], list(ordering_p) + list(ordering_n)).  Anything else
    (None, or a view that does not cover the placement's devices) falls
    back to the trail reconstruction -- a partial view would silently
    drop devices from the orientation map.
    """
    if (blocks is None):
        return None
    blocks = list(blocks)           # materialize: consumed twice below
    seen = set()
    for blk in blocks:
        for member in blk.members:
            if (member.device.name in seen):
                return None             # not a total decomposition
            seen.add(member.device.name)
    if (seen != {d.name for d in netlist.devices}):
        return None
    return blocks


def _reconstruct_views(netlist, placement, break_cols=DEFAULT_BREAK_COLS):
    """The historical block-level reconstruction (see die_orientation)."""
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


def _device_adjacency(netlist, placement, break_cols=DEFAULT_BREAK_COLS):
    """The die's device-level abutment constraints: sorted
    [(left_dev, right_dev, equal)] over each diffusion strip's devices
    ordered by start_col, where the inter-device gap is 0 (facing
    terminals sit on ONE shared diffusion node: nets equal) or
    ``break_cols`` (a diffusion break: nets differ).  Wider gaps carry
    no information.  Strips key on (row, is_p): the exact engine
    interleaves P and N devices in one placement row (overlapping
    x-ranges, disjoint y-strips), so ``row`` alone is not a strip.
    Deterministic: strips in sorted order, devices by (start_col, name).
    """
    strips = {}
    for dev in netlist.devices:
        p = placement[dev]
        strips.setdefault((p.row, dev.is_p), []).append(dev)
    adjacency = []
    for strip in sorted(strips):
        devs = sorted(strips[strip],
                      key=lambda d: (placement[d].start_col, d.name))
        for a, b in zip(devs, devs[1:]):
            gap = placement[b].start_col - placement[a].end_col
            if gap == 0 or gap == break_cols:
                adjacency.append((a, b, gap == 0))
    return adjacency


def _map_satisfies_adjacency(adjacency, mapping):
    """Whether every device adjacency holds under the orientation map."""
    for a, b, equal in adjacency:
        if ((mapping[a.name][1] == mapping[b.name][0]) != equal):
            return False
    return True


def _views_to_map(views):
    """{device name: (die_left_net, die_right_net)} from DieBlockViews."""
    mapping = {}
    for view in views:
        for i, member in enumerate(view.members):
            flip = (view.flips[i] if view.flips is not None
                    else view.flipped)
            mapping[member.device.name] = (
                (member.right_net, member.left_net) if flip
                else (member.left_net, member.right_net))
    return mapping


def _blocks_views(blocks, placement):
    """Die views straight from the orientation-aware block view.

    The refined orderings' blocks carry each member's DIE edge nets in
    die order (place_row laid the members out in member-list order), so
    every view is unflipped as carried; members are re-sorted by
    start_col defensively (a no-op for place_row-built orderings).
    """
    views = []
    for blk in blocks:
        die = sorted(blk.members,
                     key=lambda m: (placement[m.device].start_col,
                                    m.device.name))
        views.append(DieBlockView(blk, die, False))
    return views


def _trail_views(netlist, placement, break_cols=DEFAULT_BREAK_COLS):
    """Die views rebuilt from the device TRAILS (the fallback for tree
    arrangements the pristine decomposition cannot orient).

    Drops the block-membership fiction entirely: every device is one
    binary unknown (which of ITS OWN {source, drain} terminals faces
    left -- the pristine BlockMember orientation supplies the reference
    order), constrained by :func:`_device_adjacency` exactly like the
    block-level singles.  The rearrangement's shared internal edges are
    gap-0 equalities that pin the trail members relative to each other,
    so the die-determined part of the arrangement reconstructs TRUE
    where the block-level model cannot even express it.

    The adjacency graph is a union of paths (only column-consecutive
    devices are constrained), so each component is solved EXACTLY by a
    backward-feasibility DP followed by a forward greedy walk: the
    lexicographically-first satisfying assignment in column order,
    pristine orientation first per device.  A component with no
    satisfying assignment (a die no orientation explains -- cannot come
    out of place_row) keeps every member pristine, deterministically.
    Devices no constraint touches stay pristine too (the shared
    die-invisible convention).

    Views come out in build_diffusion_blocks order with members in die
    order and PER-MEMBER flips (a rearranged block's members need not
    all face the same way); the block-level ``flipped`` is None there.
    """
    blocks = build_diffusion_blocks(netlist)
    pristine = {}                     # device name -> (left, right) pristine
    for blk in blocks:
        for member in blk.members:
            pristine[member.device.name] = (member.left_net,
                                            member.right_net)
    adjacency = _device_adjacency(netlist, placement, break_cols)

    def die_nets(name, flip):
        left, right = pristine[name]
        return (right, left) if flip else (left, right)

    def options(prev_name, prev_flip, name, equal):
        """Flips of ``name`` satisfying the (prev, name) adjacency."""
        need = die_nets(prev_name, prev_flip)[1]
        return [flip for flip in (False, True)
                if (die_nets(name, flip)[0] == need) == equal]

    flipped = dict.fromkeys(sorted(pristine), None)
    # components of the adjacency graph, in path (column) order: the
    # constraints couple column-consecutive devices only, so walking
    # each strip's sorted device list splits it into maximal runs
    strips = {}
    for dev in netlist.devices:
        p = placement[dev]
        strips.setdefault((p.row, dev.is_p), []).append(dev)
    for strip in sorted(strips):
        devs = sorted(strips[strip],
                      key=lambda d: (placement[d].start_col, d.name))
        by_name = {d.name: d for d in devs}
        cons = {}
        for a, b, equal in adjacency:
            if a.name in by_name:               # same strip by construction
                cons[(a.name, b.name)] = equal
        run = []                                # (device, next-constraint)
        for d in devs:
            if run and (run[-1][0].name, d.name) not in cons:
                _trail_solve_run(run, cons, options, flipped)
                run = []
            run.append((d, cons.get((run[-1][0].name, d.name))
                        if run else None))
        if run:
            _trail_solve_run(run, cons, options, flipped)
    views = []
    for blk in blocks:
        die = sorted(blk.members,
                     key=lambda m: (placement[m.device].start_col,
                                    m.device.name))
        flips = [bool(flipped[m.device.name]) for m in die]
        views.append(DieBlockView(blk, die, None, flips))
    return views


def _trail_solve_run(run, cons, options, flipped):
    """Solve one maximal constraint path; internal to _trail_views.

    ``run`` is [(device, constraint-to-predecessor)] in column order
    (the first entry's constraint is None).  Backward feasibility per
    flip, then the forward greedy walk taking the pristine orientation
    wherever both remain feasible -- the lexicographically-first
    satisfying assignment, deterministic (invariant 9).  A run with no
    satisfying assignment keeps every member pristine.
    """
    names = [d.name for d, _c in run]
    feas = [None] * len(names)                  # index -> {flip: bool}
    feas[-1] = {False: True, True: True}
    for i in range(len(names) - 2, -1, -1):
        equal = cons[(names[i], names[i + 1])]
        feas[i] = {f: any(feas[i + 1][g]
                          for g in options(names[i], f, names[i + 1], equal))
                   for f in (False, True)}
    if not (feas[0][False] or feas[0][True]):
        return                    # unorientable die: pristine (shared rule)
    # pristine orientation unless the first constraint rejects it
    flipped[names[0]] = False if feas[0][False] else True
    for i in range(len(names) - 1):
        equal = cons[(names[i], names[i + 1])]
        opts = options(names[i], flipped[names[i]], names[i + 1], equal)
        flip = next(g for g in (False, True)
                    if g in opts and feas[i + 1][g])
        flipped[names[i + 1]] = flip


def die_orientation_map(netlist, placement, break_cols=DEFAULT_BREAK_COLS,
                        blocks=None):
    """{device name: (die_left_net, die_right_net)} per die_orientation."""
    return _views_to_map(die_orientation(netlist, placement, break_cols,
                                         blocks))


def die_slot_access_points(netlist, placement,
                           break_cols=DEFAULT_BREAK_COLS, blocks=None):
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
    orientation = die_orientation_map(netlist, placement, break_cols,
                                      blocks)
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
