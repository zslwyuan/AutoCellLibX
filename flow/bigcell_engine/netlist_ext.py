"""Extensions over smt_engine.netlist for big/irregular cells.

Spec: doc/STAGE3_BIGCELL_ENGINE.md section 2.1.  Everything here is
deterministic and pure; the structural model stays smt_engine.netlist's
(CellNetlist / find_series_chains / find_parallel_groups /
build_diffusion_blocks) -- this module only adds what big cells need:

1. ``fold_devices(...)``: up-front fold decision mirroring
   cellnetlst.cpp:254-286.  *Series folding* (foldingSeries/seriesFolding,
   cellnetlst.cpp:772-956) splits a series chain whose EVERY member is
   wider than the per-row diffusion budget into parallel legs -- the leg
   count is set by the widest member (``ceil(W/budget)``) so the stacks
   stay aligned; leg copies are new devices named ``name#legK`` whose
   *internal* (chain-junction) nets are suffixed ``net#legK``, exactly
   like ASTRAN's ``_K`` suffixing.  *Width folding* (the loop at
   cellnetlst.cpp:262-285) splits any device whose electrical width
   exceeds the budget into ``legs`` parallel fingers, represented in
   geometry.py's format as ``(legs, leg_width_cols)`` for that device
   (smt_engine folds in place the same way, layout_model.py:99-114).
   Folding runs BEFORE block building.
2. ``row_seeds(blocks)``: per-polarity initial block order, sorted by
   (-width, first-device-name) -- the same discipline as
   build_diffusion_blocks.
3. ``build_bigcell_blocks(netlist)``: the TOTAL block decomposition.
   Regular cells (no degree-3 pure internal nodes) get exactly
   ``build_diffusion_blocks``' output.  Irregular cells add *tree/branch
   blocks*: units (chains / parallel groups / singles) coupled through a
   pure internal degree-3 diffusion node (3 source/drain terminals, no
   gate terminal, not a port) are flattened into linear trails whose
   consecutive units share an end net -- the doc's "DFS from the
   lowest-net leaf" generalised to a deterministic best-trail search
   (every sorted start enumerated, longest trail kept, lexicographic
   tie-break), because the leaf-only rule provably misses the reference
   AOI21X1 arrangement [M1|M0|M2] where the pair shares VCC *and* the
   branch net.  A parallel group whose *internal* shared edge consumes a
   coupled degree-3 node (e.g. AOI21's P pair) is dissolved into singles
   first -- its pair net is hidden inside the group and could not be
   shared otherwise.  Every device ends up in exactly one block
   (property-tested over every benchmark cell).

4. ``build_bigcell_blocks`` ``variant`` knob: alternative TOTAL
   decompositions for the routability-aware speculate pool
   (place_sa.decomposition_variant_classes).  The conflict evidence
   (flow/_stage3_check/bench_int3) shows the plateau surviving every
   ordering/mirror of ONE decomposition, so the variants change the
   decomposition itself; each one keeps the orientation discipline
   (members carry (device, left, right), mirror_block stays valid) and
   covers every device exactly once:
   - ``"default"``: the tree/branch decomposition above;
   - ``"base"``: exactly ``build_diffusion_blocks`` (no tree coupling);
   - ``"parallel_phase"``: parallel groups re-phased -- the
     lexicographically SMALLER pair net becomes the internal shared
     edge (build_diffusion_blocks buries the larger one), which turns
     buried pair nets into two exposed block-end diffusions and the
     power end internal (rail-covered) -- a structural change no block
     flip can express;
   - ``"split_parallel"`` / ``"split_series"``: that kind dissolved
     into per-member singles (canonical (source, drain) orientation),
     then tree-coupled as "default" does;
   - ``"singles"``: every kind dissolved, no coupling -- the
     maximal-split extreme (maximum diffusion breaks / corridors);
   - ``"max_merge"``: "default" with ``max_coupler_degree=None``.

5. ``chain_split_decompositions(...)``: the chain-SPLIT candidate
   decompositions -- the arrangement-space extension for the
   entangled-wall class (AUDIT 5.50/5.52).  A series chain may legally
   place as two sub-chains with its internal node wired by metal instead
   of shared diffusion; each decomposition splits ONE series chain of
   the default decomposition at ONE internal point into two sub-chain
   blocks (facing ends carry the same internal net, so every consumer's
   break rule inserts the gap exactly when the sub-chains sit
   non-adjacent, and the net becomes multi-region/contactable like a
   tree block's re-exposed branch net).  Placed adjacent the pair IS the
   original block, so splits only ADD arrangements.  Bounded
   (``CHAIN_SPLIT_MAX_DECOMPOSITIONS``, :func:`split_points_for_chain`)
   and deterministic; consumed by place_sa.chain_split_classes.

All iterations are over sorted structures (AGENTS.md invariant 9).
"""

import math

from smt_cell_placer import Device, TransistorNetlist
from smt_engine.netlist import (BlockMember, CellNetlist, DiffusionBlock,
                                build_diffusion_blocks, find_series_chains)
from bigcell_engine.geometry import GRID_UM, N_ROW, P_ROW  # noqa: F401

#: re-exported for callers that want one import site
DiffusionBlock = DiffusionBlock  # noqa: F401

#: Per-row diffusion-height budget in um.  The rule-algebra estimate from
#: calcArea (autocell2.cpp:68-128, "Tapless" template at the flow's fixed
#: geometry: H = 2.47 um, nwellpos = 1.235 um) gives 1.0875 um, but the
#: ASTRAN logs pin the *observable* budget at 1.2 um: FAX1 folds
#: 28 -> 43 T (P 14 -> 29) and BUFX4 6 -> 7, both reproduced exactly with
#: 1.2 and not with 1.0875 (the only two cells ASTRAN ever folded on this
#: corpus -- folding is otherwise inactive at W <= 1 um).  Both polarities
#: fold at the same budget, like ASTRAN's foldTrans(pSize, nSize).
FOLD_BUDGET_P_UM = 1.2
FOLD_BUDGET_N_UM = 1.2

_EPS = 1e-9


# --------------------------------------------------------------------------
# folding (cellnetlst.cpp:254-286)
# --------------------------------------------------------------------------

def _budget_um(dev, p_budget_um, n_budget_um):
    return p_budget_um if dev.is_p else n_budget_um


def _junction_nets(chain):
    """Nets shared by consecutive members of a series chain (sorted)."""
    junctions = set()
    for a, b in zip(chain, chain[1:]):
        shared = (set((a.source, a.drain)) & set((b.source, b.drain)))
        junctions |= shared
    return junctions


def _leg_device(dev, leg_k, legs, junctions):
    """One series-fold leg copy: ``name#legK`` with junction nets suffixed.

    Mirrors seriesFolding (cellnetlst.cpp:859-956): every terminal that is
    an internal chain junction gets the leg suffix; outer terminals (and
    the gate, which is never a diffusion junction) keep their nets.
    """
    def ren(net):
        return "%s#leg%d" % (net, leg_k) if net in junctions else net

    return Device("%s#leg%d" % (dev.name, leg_k), ren(dev.drain),
                  dev.gate, ren(dev.source), dev.bulk, dev.is_p,
                  dev.width_um / legs)


def fold_devices(netlist, p_budget_um=FOLD_BUDGET_P_UM,
                 n_budget_um=FOLD_BUDGET_N_UM, grid_um=GRID_UM):
    """Fold decisions made up front; returns (netlist2, leg_widths).

    ``netlist2`` is the input ``CellNetlist`` unchanged when no series
    fold fires, else a new CellNetlist whose device list is the originals
    (widths divided by their leg count) followed by the leg copies in
    (chain, K, member) order -- ASTRAN's append-at-end discipline
    (cellnetlst.cpp:269-285).  Devices are never mutated in place.

    ``leg_widths`` maps EVERY device name of ``netlist2`` to
    ``(legs, leg_width_cols)`` in geometry.py's slot format: the
    width-fold decision (in place, like smt_engine's k/legw) with
    ``leg_width_cols = 1`` -- one column per leg, W drawn vertically
    (doc/BIGCELL_SLOT_GEOMETRY.md section 3).
    """
    chains, _internal = find_series_chains(netlist)
    # work on copies: the input netlist stays untouched (purity)
    devices = [Device(d.name, d.drain, d.gate, d.source, d.bulk, d.is_p,
                      d.width_um) for d in netlist.devices]
    by_name = {d.name: d for d in devices}
    new_devices = []
    for chain in chains:
        # ASTRAN folds a series stack only when EVERY member is over the
        # budget, into ceil(widest/budget) legs (foldingSeries,
        # cellnetlst.cpp:802-845); length-1 chains degrade to plain width
        # copies (the numTrans == 0 branch, cellnetlst.cpp:873-886).
        if not all(d.width_um > _budget_um(d, p_budget_um, n_budget_um) + _EPS
                   for d in chain):
            continue
        biggest = max(chain, key=lambda d: (d.width_um, d.name))
        legs = int(math.ceil(biggest.width_um
                             / _budget_um(biggest, p_budget_um, n_budget_um)
                             - _EPS))
        junctions = _junction_nets(chain)
        for leg_k in range(legs, 1, -1):        # ASTRAN: copies K=legs..2
            for dev in chain:
                new_devices.append(
                    _leg_device(by_name[dev.name], leg_k, legs, junctions))
        for dev in chain:                       # originals: width /= legs
            orig = by_name[dev.name]
            orig.width_um = orig.width_um / legs

    all_devices = devices + new_devices

    # width folding, cellnetlst.cpp:262-285: any device whose electrical
    # width exceeds the per-row diffusion budget becomes ceil(w/budget)
    # parallel legs; each leg occupies ONE slot column (the slot model's
    # leg_width_cols = 1) with the leg's W/legs as its strip height.
    leg_widths = {}
    for dev in all_devices:
        bud = _budget_um(dev, p_budget_um, n_budget_um)
        legs = 1
        if dev.width_um > bud + _EPS:
            legs = int(math.ceil(dev.width_um / bud - _EPS))
        leg_widths[dev.name] = (legs, 1)

    if not new_devices:
        return netlist, leg_widths
    sub = netlist.subckt
    folded = TransistorNetlist(sub.subckt_name, sub.ports, all_devices)
    return CellNetlist(folded), leg_widths


# --------------------------------------------------------------------------
# mirror helper (shared with place_euler / place_sa)
# --------------------------------------------------------------------------

def mirror_block(block):
    """A new DiffusionBlock: members reversed, each member flipped.

    Electrically identical (MOS S/D are symmetric); the block's exposed
    ends swap.  Consecutive shared edges stay shared under reversal, so
    place_row's contiguous-member rule stays valid for the mirrored block.
    """
    members = [BlockMember(m.device, m.right_net, m.left_net)
               for m in reversed(block.members)]
    return DiffusionBlock(block.kind, members)


# --------------------------------------------------------------------------
# tree/branch blocks: the total decomposition (doc section 2.1.3)
# --------------------------------------------------------------------------

def _pure_internal_nodes(netlist, max_degree=None):
    """({net: [devices]} for pure internal coupler nodes of degree >= 3,
    and the set of all pure internal diffusion nodes of degree 2 or 3.

    "Pure": no gate terminal on the net (the poly stripe would separate
    the diffusions, smt_engine.netlist.find_series_chains' rule) and not
    a subcircuit port.  ``max_degree`` caps the coupler degree (the
    default 3 reproduces the historical degree-3-only behaviour; the
    slot chain passes None so doubled networks' degree-4 junctions --
    NOR3X1's a_2_64#/a_25_64# -- couple their units too,
    doc/BIGCELL_SLOT_GEOMETRY.md section 5).
    """
    terms = {}
    gates = set()
    for dev in netlist.devices:
        terms.setdefault(dev.source, []).append(dev)
        terms.setdefault(dev.drain, []).append(dev)
        gates.add(dev.gate)
    couplers = {}
    all_pure = set()
    for net in sorted(terms):
        if net in netlist.external or net in gates:
            continue
        n = len(terms[net])
        if n >= 3 and (max_degree is None or n <= max_degree):
            couplers[net] = sorted(terms[net], key=lambda d: d.name)
        if n in (2, 3):
            all_pure.add(net)
    return couplers, all_pure


def _slot_nets(block):
    """Every diffusion-terminal net the block consumes, with the number of
    slots it consumes *internally* (shared edges between members)."""
    ends = {}
    internal = {}
    for member in block.members:
        ends[member.left_net] = ends.get(member.left_net, 0) + 1
        ends[member.right_net] = ends.get(member.right_net, 0) + 1
    for a, b in zip(block.members, block.members[1:]):
        if a.right_net == b.left_net:
            internal[a.right_net] = internal.get(a.right_net, 0) + 1
    return ends, internal


#: the decomposition variants build_bigcell_blocks understands (documented
#: in the module docstring); the non-default ones are mirrored by
#: place_sa.DECOMPOSITION_VARIANTS, whose order is the speculate pool's
#: variant priority.
BLOCK_VARIANTS = ("default", "base", "parallel_phase", "split_parallel",
                  "split_series", "singles", "max_merge")


def _dissolved_blocks(blocks, kinds):
    """``blocks`` with every multi-member block of kind in ``kinds``
    replaced by per-member singles (canonical (source, drain)
    orientation, like build_diffusion_blocks' standalone blocks).

    Totality is preserved member-for-member; a dissolved parallel pair
    or series chain's internal shared edge becomes re-exposable (the
    router ties split regions with metal, exactly like the tree
    linearizer's re-exposed branch nets).  Deterministic.
    """
    out = []
    for block in blocks:
        if block.kind in kinds and len(block.members) > 1:
            for member in block.members:
                out.append(DiffusionBlock("single", [BlockMember(
                    member.device, member.device.source,
                    member.device.drain)]))
        else:
            out.append(block)
    out.sort(key=lambda b: (len(b.members) == 1, b.first.name))
    return out


def _parallel_phase_blocks(blocks):
    """``blocks`` with every parallel group re-phased.

    build_diffusion_blocks orients a parallel group's member j as
    (l0, r0) when j is even -- so the shared edge between consecutive
    members is the lexicographically LARGER pair net (r0) and the
    smaller one (l0) sits on both block ends.  This variant flips the
    alternation: the smaller net is internal, the larger one re-exposed
    at both ends.  For a power/pair split (e.g. NAND pull-ups over
    {VCC, Y}) that buries the rail edge -- which the rail covers anyway
    -- and exposes the signal net twice, a diffusion-access structure
    no member flip or reordering of the original block can reach.
    Deterministic (member order kept, alternation start swapped).
    """
    out = []
    for block in blocks:
        if block.kind != "parallel" or len(block.members) < 2:
            out.append(block)
            continue
        l0, r0 = sorted((block.members[0].left_net,
                         block.members[0].right_net))
        members = []
        for j, member in enumerate(block.members):
            left, right = (r0, l0) if j % 2 == 0 else (l0, r0)
            members.append(BlockMember(member.device, left, right))
        out.append(DiffusionBlock("parallel", members))
    out.sort(key=lambda b: (len(b.members) == 1, b.first.name))
    return out


def _block_shape(blocks):
    """Comparable value-shape of a block list (kinds + oriented members),
    the identity test place_sa uses to skip variants that cannot produce
    a new ordering."""
    return tuple(
        (b.kind,) + tuple((m.device.name, m.left_net, m.right_net)
                          for m in b.members)
        for b in blocks)


def build_bigcell_blocks(netlist, max_coupler_degree=3, variant="default"):
    """The TOTAL diffusion-block decomposition: smt_engine blocks plus
    tree/branch blocks over degree-3-coupled units, or one of the
    alternative decompositions (``variant``, see BLOCK_VARIANTS and the
    module docstring).

    ``max_coupler_degree`` caps how high a pure internal node's terminal
    count may go and still couple its units into one trail (None =
    unbounded).  The default 3 keeps the historical behaviour exactly:
    when the cell has no coupled degree-3 node the output is exactly
    ``build_diffusion_blocks(netlist)`` (same objects, same order).  The
    slot-model chain (geometry parity with ASTRAN's eulerian runs) calls
    with ``max_coupler_degree=None`` so doubled networks' degree-4
    junctions linearize into one strip (doc/BIGCELL_SLOT_GEOMETRY.md
    section 5).  ``variant="max_merge"`` is that same unbounded coupling.

    Returns a deterministic list of DiffusionBlock (kinds: series /
    parallel / single / tree) covering every device exactly once, for
    every variant.
    """
    if variant not in BLOCK_VARIANTS:
        raise ValueError("unknown block decomposition variant %r (choose "
                         "from %s)" % (variant, ", ".join(BLOCK_VARIANTS)))
    if variant == "max_merge":
        max_coupler_degree = None
    base = build_diffusion_blocks(netlist)
    if variant == "base":
        return base
    if variant == "parallel_phase":
        base = _parallel_phase_blocks(base)
    elif variant == "split_parallel":
        base = _dissolved_blocks(base, ("parallel",))
    elif variant == "split_series":
        base = _dissolved_blocks(base, ("series",))
    elif variant == "singles":
        return _dissolved_blocks(base, ("parallel", "series"))
    deg3, _all_pure = _pure_internal_nodes(netlist, max_coupler_degree)
    if not deg3:
        return base

    # --- units: base blocks, with groups that hide a coupled degree-3
    # node behind an internal shared edge dissolved into singles ------
    unit_of = {}                       # device name -> unit index
    units = []
    for idx, block in enumerate(base):
        for m in block.members:
            unit_of[m.device.name] = idx
        units.append(block)

    def coupled(net):
        return len({unit_of[d.name] for d in deg3[net]}) >= 2

    dissolved = set()
    for net in sorted(deg3):
        if not coupled(net):
            continue
        for idx, block in enumerate(units):
            if block.kind != "parallel" or idx in dissolved:
                continue
            _ends, internal = _slot_nets(block)
            if internal.get(net):
                dissolved.add(idx)
    if dissolved:
        units = []
        unit_of = {}
        for idx, block in enumerate(base):
            if idx in dissolved:
                for member in block.members:
                    single = DiffusionBlock("single", [BlockMember(
                        member.device, member.device.source,
                        member.device.drain)])
                    unit_of[member.device.name] = len(units)
                    units.append(single)
            else:
                for m in block.members:
                    unit_of[m.device.name] = len(units)
                units.append(block)

    # --- coupling adjacency: units sharing a coupled degree-3 end net,
    # same polarity only (P and N diffusions never share a strip) ------
    unit_nets = []
    for block in units:
        ends, _internal = _slot_nets(block)
        unit_nets.append(sorted(n for n in ends
                                if n in deg3 and coupled(n)))
    polarity = [block.first.is_p for block in units]

    parent = list(range(len(units)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    by_net = {}
    for idx, nets in enumerate(unit_nets):
        for net in nets:
            by_net.setdefault(net, []).append(idx)
    for net in sorted(by_net):
        same = [i for i in sorted(by_net[net])
                if polarity[i] == polarity[by_net[net][0]]]
        for i in same[1:]:
            union(same[0], i)
    components = {}
    for idx in range(len(units)):
        components.setdefault(find(idx), []).append(idx)
    tree_units = set()
    for members in components.values():
        if len(members) >= 2:
            tree_units.update(members)

    # --- DFS-flatten each multi-unit component into linear runs -------
    runs = []
    for root in sorted(components):
        member_idxs = components[root]
        if len(member_idxs) < 2:
            continue
        runs.extend(_linearize(units, member_idxs))

    # --- materialize: untouched units keep their base block objects;
    # each linear run fuses into ONE tree block (consecutive units share
    # their end net by trail construction, so place_row's contiguous-
    # member rule stays valid) -----------------------------------------
    out = []
    for idx, block in enumerate(units):
        if idx not in tree_units:
            out.append(block)
    for run in runs:
        members = []
        for unit_idx, flip in run:
            block = units[unit_idx]
            if not flip:
                members.extend(block.members)
            else:
                members.extend(BlockMember(m.device, m.right_net, m.left_net)
                               for m in reversed(block.members))
        out.append(DiffusionBlock("tree", members))
    out.sort(key=lambda b: (len(b.members) == 1, b.first.name))
    return out


def _linearize(units, member_idxs):
    """Flatten one component into linear runs of (unit_idx, flip).

    A run is a trail over the component's units where consecutive units
    share ANY equal end net (power rails included -- two block ends on
    VCC abut on the rail exactly like ASTRAN's flat transistor ordering).
    The most sharing a linear diffusion row can realize is one shared
    edge per consecutive pair; a degree-3 branch net whose third terminal
    cannot stay inside the run re-exposes at a later run's left end (the
    router ties the two diffusion regions with metal).

    Deterministic search: enumerate every (unit, orientation) start in
    sorted order, greedily grow the trail preferring candidates whose
    other end continues it (one-step lookahead), splice leftover CLOSED
    circles into the run at their leftmost incident position (Euler
    splicing -- NOR3X1's doubled pull-up linearizes into ASTRAN's single
    6-transistor strip this way, doc/BIGCELL_SLOT_GEOMETRY.md section 5);
    keep the best run by (-shared edges, lexicographic sequence); then
    repeat on the rest.
    """
    remaining = sorted(member_idxs, key=lambda i: units[i].first.name)
    runs = []
    while remaining:
        best = None                          # (key, run)
        for idx in remaining:
            block = units[idx]
            flips = (False,) if block.left_net == block.right_net \
                else (False, True)
            for flip in flips:
                run = _grow_run(units, remaining, idx, flip)
                run = _splice(units, remaining, run)
                key = (-(len(run) - 1),
                       tuple((units[i].first.name, f) for i, f in run))
                if best is None or key < best[0]:
                    best = (key, run)
        run = best[1]
        runs.append(run)
        done = {i for i, _f in run}
        remaining = [i for i in remaining if i not in done]
    return runs


def _splice(units, avail, run):
    """Extend ``run`` with leftover units incident to one of its slots.

    Only CLOSED sub-runs (start net == end net) may be inserted before
    the run's end -- the surrounding shared-edge chain stays valid; at
    the run's right end an open sub-run may attach.  Leftmost position
    first, candidate units sorted, sub-runs grown by _grow_run's greedy;
    repeats until nothing incident remains.  Deterministic.
    """
    run = list(run)
    used = {i for i, _f in run}
    free = [i for i in avail if i not in used]
    while True:
        found = None                         # (cand-key, pos, sub)
        for pos in range(len(run)):
            _l, right = _unit_ends(units, run[pos][0], run[pos][1])
            for i in free:
                flip = _match_flip(units, i, right)
                if flip is None:
                    continue
                sub = _grow_run(units, free, i, flip)
                closes = _unit_ends(units, sub[-1][0], sub[-1][1])[1] == right
                if pos + len(sub) < len(run) and not closes:
                    continue                 # open trail mid-run: invalid
                cand = (pos, 0 if closes else 1, units[i].first.name)
                if found is None or cand < found[0]:
                    found = (cand, pos, sub)
        if found is None:
            return run
        _cand, pos, sub = found
        run = run[:pos + 1] + sub + run[pos + 1:]
        used |= {i for i, _f in sub}
        free = [i for i in free if i not in used]


def _unit_ends(units, idx, flip):
    block = units[idx]
    return (block.left_net if not flip else block.right_net,
            block.right_net if not flip else block.left_net)


def _match_flip(units, idx, net):
    """Orientation of ``units[idx]`` that faces ``net`` left (or None)."""
    block = units[idx]
    if block.left_net == net:
        return False
    if block.right_net == net:
        return True
    return None


def _grow_run(units, avail, idx0, flip0):
    """Greedy trail from the oriented start, one-step lookahead."""
    run = [(idx0, flip0)]
    used = {idx0}
    _l, right = _unit_ends(units, idx0, flip0)
    while True:
        cands = []
        for i in avail:
            if i in used:
                continue
            flip = _match_flip(units, i, right)
            if flip is None:
                continue
            _l2, other = _unit_ends(units, i, flip)
            continues = any(
                other in (units[j].left_net, units[j].right_net)
                for j in avail if j not in used and j != i)
            cands.append((not continues, units[i].first.name, i, flip))
        if not cands:
            return run
        cands.sort()
        _neg, _name, i, flip = cands[0]
        run.append((i, flip))
        used.add(i)
        _l, right = _unit_ends(units, i, flip)


# --------------------------------------------------------------------------
# chain-split decompositions: the arrangement-space extension (the
# entangled-wall class's split lever, AUDIT 5.50/5.52)
# --------------------------------------------------------------------------
# The censused arrangement space (decomposition variant x block ordering x
# block flips) keeps every diffusion block CONTIGUOUS: a series chain's
# members always share every internal diffusion edge.  But a series chain
# can legally SPLIT: [M1,M2,M3] placed as [M1,M2] + gap + [M3] with the
# internal node (M2.right == M3.left) wired by metal instead of shared
# diffusion -- electrically identical (MOS S/D are symmetric, the internal
# net keeps its identity), and exactly the freedom that moves gate columns
# across the power-coverage bands the censused walls live in.  The split is
# expressed WITHOUT any geometry/netlist change: the chain becomes two
# sub-chain blocks whose facing ends carry the same internal net, so
# place_row's break rule -- and every consumer's (row_edges, die_view,
# verify, the router) -- inserts the gap exactly when the sub-chains are
# placed non-adjacent, and the internal net becomes multi-region
# (contactable, regions tied by metal) like every tree block's re-exposed
# branch net.  Placed ADJACENT the pair IS the original block (facing nets
# equal -> no break -> shared diffusion, one slot): the split only ever
# ADDS arrangements, never rewrites one.

#: series chains with at most this many members split at EVERY internal
#: point; longer chains split at the capped deterministic set of
#: :func:`split_points_for_chain`.
CHAIN_SPLIT_ALL_POINTS_MAX_MEMBERS = 6

#: split points nominated for a chain longer than the all-points bound
CHAIN_SPLIT_LONG_CHAIN_POINTS = 4

#: (chain, point) split decompositions generated at most, in sorted
#: (chain first-device name, point) order -- the pool-cost cap
CHAIN_SPLIT_MAX_DECOMPOSITIONS = 8


def split_points_for_chain(member_count):
    """The deterministic split-point set for a k-member series chain.

    ``k <= CHAIN_SPLIT_ALL_POINTS_MAX_MEMBERS``: every internal point
    (1..k-1) -- each cut is its own candidate decomposition.  Longer
    chains: ``CHAIN_SPLIT_LONG_CHAIN_POINTS`` evenly spaced interior
    points (rounded, deduped, clamped to 1..k-1) -- a long chain's
    well-separated cuts bracket its distinct structural regions, and the
    all-points enumeration would multiply the pool by k-1.  Pure function
    (invariant 9).
    """
    if member_count <= CHAIN_SPLIT_ALL_POINTS_MAX_MEMBERS:
        return tuple(range(1, member_count))
    k = member_count
    points = set()
    for j in range(1, CHAIN_SPLIT_LONG_CHAIN_POINTS + 1):
        p = int(round(j * k / float(CHAIN_SPLIT_LONG_CHAIN_POINTS + 1)))
        points.add(min(max(p, 1), k - 1))
    return tuple(sorted(points))


def _subchain_block(members):
    """One sub-chain DiffusionBlock: members keep their orientation."""
    kind = "series" if len(members) > 1 else "single"
    return DiffusionBlock(kind, [BlockMember(m.device, m.left_net,
                                             m.right_net)
                                 for m in members])


def split_chain_in_blocks(blocks, chain_first_name, point):
    """``blocks`` with ONE series chain split at ``point``.

    The chain is the ``kind == "series"`` block whose first member's
    device is named ``chain_first_name``; ``point`` cuts between members
    ``point-1`` and ``point``.  Returns the new deterministic block list
    (build_bigcell_blocks' own sort discipline) or None when the name is
    not a series chain or the point is not internal.  Pure (invariant 9).
    """
    idx = None
    for i, block in enumerate(blocks):
        if (block.kind == "series" and block.first.name == chain_first_name
                and len(block.members) > 1):
            idx = i
            break
    if idx is None or not 1 <= point <= len(blocks[idx].members) - 1:
        return None
    left, right = (_subchain_block(blocks[idx].members[:point]),
                   _subchain_block(blocks[idx].members[point:]))
    out = list(blocks)
    out[idx:idx + 1] = [left, right]
    out.sort(key=lambda b: (len(b.members) == 1, b.first.name))
    return out


def chain_split_decompositions(
        netlist, max_decompositions=CHAIN_SPLIT_MAX_DECOMPOSITIONS):
    """The split-candidate decompositions over the DEFAULT total
    decomposition: ``[(chain_name, point, blocks)]``.

    For every series chain (kind "series", >= 2 members) of
    ``build_bigcell_blocks(netlist)`` -- chains sorted by first-device
    name, points ascending per :func:`split_points_for_chain` -- the
    decomposition replaces that ONE chain with its two sub-chains and
    keeps every other block untouched.  Chains are capped by
    ``max_decompositions`` (the first sorted (chain, point) pairs), so
    the candidate pool stays bounded on chain-heavy cells.  Tree/parallel
    blocks are not split (the lever is the SERIES chain's internal edge).
    Totality: every device ends up in exactly one block, every output
    covers the netlist exactly once.  Deterministic (invariant 9).
    """
    blocks = build_bigcell_blocks(netlist)
    chains = sorted(
        (block.first.name for block in blocks
         if block.kind == "series" and len(block.members) > 1))
    out = []
    for name in chains:
        chain = next(b for b in blocks
                     if b.kind == "series" and b.first.name == name)
        for point in split_points_for_chain(len(chain.members)):
            if len(out) >= max_decompositions:
                return out
            split = split_chain_in_blocks(blocks, name, point)
            if split is not None:
                out.append((name, point, split))
    return out


# --------------------------------------------------------------------------
# row seeds (doc section 2.1.2)
# --------------------------------------------------------------------------

def _block_sort_key(block, leg_widths):
    if leg_widths:
        from bigcell_engine.geometry import block_width_cols
        width = block_width_cols(block, leg_widths)
    else:
        width = len(block.members)
    return (-width, block.first.name)


def row_seeds(blocks, leg_widths=None):
    """Deterministic per-polarity initial block order.

    ``blocks`` is either a flat list of DiffusionBlock (split by the
    first member's polarity) or an already-split {P_ROW: [...],
    N_ROW: [...]} mapping.  Each row is sorted by (-block width,
    first-device-name); widths come from ``leg_widths`` when given,
    member counts otherwise.  Returns {P_ROW: [...], N_ROW: [...]}.
    """
    if isinstance(blocks, dict):
        flat = list(blocks[P_ROW]) + list(blocks[N_ROW])
    else:
        flat = list(blocks)
    by_row = {P_ROW: [], N_ROW: []}
    for block in sorted(flat, key=lambda b: _block_sort_key(b, leg_widths)):
        by_row[P_ROW if block.first.is_p else N_ROW].append(block)
    return by_row
