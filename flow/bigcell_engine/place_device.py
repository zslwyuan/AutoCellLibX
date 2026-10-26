"""DEVICE-granularity placement: a transistor-level arrangement space as
a strict superset of every censused block space (the structural answer to
AUDIT 5.50-5.58's entangled-wall class).

Every arrangement space censured so far keeps some structural unit
CONTIGUOUS: the contiguous spaces keep each diffusion BLOCK whole, the
chain/pair-split spaces keep each SUB-CHAIN whole, the fold spaces keep
the fold decision fixed.  ASTRAN has no such unit -- it places individual
TRANSISTORS (cellnetlst.cpp's orderingP/orderingN are per-slot
TransistorTerminal lists) and lets diffusion sharing EMERGE wherever two
adjacent transistors happen to face the same net.  That is exactly the
freedom the entangled class proved unreachable in the block spaces: the
census walls live on GATE COLUMNS, and only interleaving a chain's
members with foreign devices moves a gate column across a power-coverage
band without splitting the chain's diffusion at a decomposition-chosen
point.  This module is that space.

Representation (the slot model's sharing rule at device granularity):

- an arrangement is a per-row ORDERED list of DEVICES, each with its own
  S/D orientation (the flip) -- represented as one single-member
  DiffusionBlock per device whose BlockMember carries the oriented
  (left, right) edge nets (``blocks_to_devices`` / the SA output);
- a diffusion run emerges wherever two adjacent devices share the facing
  net (no break column); different facing nets insert one break column
  exactly as geometry.place_row does for blocks -- because a row of
  single-member blocks IS a device row, the whole geometry/cost/census
  stack (place_sa._row_picture, _cage_row_view, ...) reads it
  unchanged, and the pictures are at DEVICE granularity by
  construction;
- the slot geometry (doc/BIGCELL_SLOT_GEOMETRY.md: terminal slots on
  column edges, gates at centres) applies per device -- a fold leg run
  (legs, leg_width_cols) is one device's own columns, so ``leg_widths``
  is consumed exactly as the block engine consumes it.

Cost: ASTRAN's terms (cellnetlst.cpp:364-460) term-for-term -- width,
gaps, gate mismatch, routing span, congestion, the same weights
place_sa uses (:data:`place_sa.COST_WEIGHTS` / :data:`place_sa.COST_SCALE`,
IMPORTED, never duplicated), plus the census steering
(:data:`place_sa.CAGE_WEIGHT` per caged gate and
:data:`place_sa.CORE_SA_WEIGHT` per walled crossing when ``census=True``
-- the crossing term rides the core-guided channel with the critical set
set to EVERY signal net, so both censuses steer over all nets).  The
machinery is place_sa._SAState itself, subclassed: a row of single-member
blocks feeds the SAME incremental row-picture/bbox/congestion
maintenance, the SAME content-cached census refresh and the SAME
incremental==full assertion discipline (``device_sa`` re-asserts it at
every iteration boundary, agent P's precedent).

Moves (the task's device move set, all expressed as size-1 segment ops
of _SAState.apply so undo is exact via the inherited inverse):

- FLIP: one device's S/D orientation (a 1-element mirror);
- SWAP ADJACENT: transposition of neighbours (a 1-element shift one to
  the right) -- any adjacent pair, any row;
- SWAP ANY PAIR: transposition of two devices at arbitrary distance
  (two 1-element shifts, index math verified by the round-trip tests);
- ROW-MOVE: relocation of one device to any other index of its row.
  Following ASTRAN's perturbation structure (cellnetlst.cpp:462-473),
  one drawn move perturbs the P row at 1/4, the N row at 1/4 and both
  at 1/2, each with one device move of a uniformly drawn type.

Search: deterministic seeded Threshold Accept (the sa_refine loop
ported): the RNG is seeded from a content hash of the cell (sorted
device names + netlist text + THIS engine's version tag, sha256, never
hash() -- invariant 9), every budget is an iteration count (no
wall-clock anywhere), and the incremental==full assertion runs at every
iteration boundary.  Seeds come from the block chain (``device_seeds``:
the euler ordering and the row seeds, both exploded to devices), so the
search starts inside the known block space and can only leave it
through device moves.

Block view (the existing machinery consumes the result unchanged):
:func:`devices_to_blocks` regroups consecutive devices whose facing
nets abut into multi-member DiffusionBlocks -- the inverse of the
explosion.  The converted view is orientation-consistent (each member
carries its die edge nets) and total (every device exactly once), which
is exactly the contract engine meta["blocks"] / route_cell(blocks=...)
/ verify_cell(blocks=...) / gds_cells consume; a fused group's members
abut by construction (facing nets equal -> no break column), so
verify's abutment invariant holds, and kind "device_run" / "single" is
a label no consumer branches on (the block-engine decomposition logic
that keys on "series"/"parallel" runs on decompositions, never on
arrangement views).  A block-chain arrangement converted to devices and
back reproduces its geometry, member walk and census byte-for-byte;
adjacent same-net blocks fuse into one run (the boundary between them
carries no geometry -- place_row inserts no break there), documented
and pinned by test.

Polarity is fixed: P devices live in the P row, N devices in the N row
(rows are uniform in polarity, geometry.place_row's contract), so every
move is row-internal.
"""

import hashlib
import random

from smt_engine.netlist import BlockMember, DiffusionBlock

from bigcell_engine.geometry import N_ROW, P_ROW
from bigcell_engine.netlist_ext import build_bigcell_blocks, row_seeds
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import (  # noqa: F401  (re-exported provenance)
    CAGE_WEIGHT, CORE_SA_WEIGHT, COST_SCALE, COST_WEIGHTS,
    _SAState, _find_initial_threshold,
    crossing_cage_penalty, gate_cage_penalty)

#: the device engine's identity in the content-hash seed (a distinct
#: stream from place_sa's "bigcell-sa/2", so the two engines' RNGs never
#: correlate; pure string, invariant 9)
DEVICE_ENGINE_VERSION = "bigcell-device/1"

#: default Threshold-Accept iteration budget (the ``budget`` parameter
#: of :func:`place_devices`; pure iteration count -- never wall-clock,
#: invariant 9).  Sized by measurement (flow/_stage3_check/
#: _device_runtime.json): one census-steered move costs one crossing+cage
#: census, so the default runs a 12T cell in ~5-12 s (NAND2X1 0.4 s,
#: XOR2X1 ~9 s, MUX2X1 ~5 s) and a 22T DFF in ~85 s at the full seed
#: pair; the budget scales near-linearly (DFFNEGX1 51/85/184 s at
#: budgets 6/12/24).  The search is seeded from the block chain, so the
#: arrangement never regresses below the block engine's start.
DEVICE_ITERATIONS = 12

#: TA quality: num_repetitions = problem_size * quality, problem_size
#: being the per-row device-count product (place_sa's discipline; the
#: device space is bigger, so the quality is a fraction of
#: place_sa.DEFAULT_QUALITY to keep the move budget bounded)
DEVICE_QUALITY = 6.0

#: per-step move cap of the initial-threshold bisection (ASTRAN uses
#: 5000; the census-steered cost pays one census per move, so the cap
#: follows place_sa's CORE_REFINE_INIT_MOVES discipline)
DEVICE_INIT_MOVES = 96


def device_seed(netlist, salt=0):
    """Content-derived RNG seed for the device engine (place_sa.cell_seed's
    discipline with THIS engine's version tag, so the two engines' RNG
    streams are independent; ``salt`` selects the deterministic restart).
    sha256, never hash() (invariant 9).  Pure."""
    sub = netlist.subckt
    parts = ["%s|%s" % (sub.subckt_name, ",".join(sub.ports))]
    for dev in sorted(netlist.devices, key=lambda d: d.name):
        parts.append("%s %s %s %s %d %s" % (
            dev.name, dev.drain, dev.gate, dev.source,
            1 if dev.is_p else 0, float(dev.width_um)))
    digest = hashlib.sha256(
        ("|".join(parts) + "|" + DEVICE_ENGINE_VERSION + "|%d" % salt)
        .encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


# --------------------------------------------------------------------------
# the two views: devices <-> blocks
# --------------------------------------------------------------------------

def blocks_to_devices(ordering_p, ordering_n):
    """Explode a block-chain arrangement to the DEVICE view.

    Each block member becomes one single-member DiffusionBlock carrying
    the member's orientation verbatim (BlockMember (left, right) kept),
    in member order; the two rows' device lists are returned as
    ``(device_p, device_n)``.  Total and orientation-preserving by
    construction; pure (invariant 9)."""
    out = []
    for ordering in (ordering_p, ordering_n):
        row = []
        for block in ordering:
            for member in block.members:
                row.append(DiffusionBlock(
                    "single", [BlockMember(member.device,
                                           member.left_net,
                                           member.right_net)]))
        out.append(row)
    return out[0], out[1]


def devices_to_blocks(ordering_p, ordering_n):
    """Regroup a device arrangement into the BLOCK view the existing
    route/verify/gds machinery consumes.

    Consecutive devices whose facing nets abut (previous right net ==
    next left net) fuse into one DiffusionBlock of kind ``"device_run"``
    (single devices stay kind ``"single"``) -- the inverse of
    :func:`blocks_to_devices` and of netlist_ext's block building: the
    fused members abut by construction (equal facing nets insert no
    break column, geometry.place_row's sharing rule), so verify's
    abutment invariant holds and the die view is orientation-consistent
    (every member carries its true die edge nets).  A block-chain
    arrangement exploded and fused back reproduces its geometry, member
    walk and census exactly; adjacent same-NET blocks of the original
    fuse into one run (their shared boundary carries no geometry).
    Total: every device exactly once.  Pure and deterministic
    (invariant 9)."""
    out = []
    for ordering in (ordering_p, ordering_n):
        row = []
        run = []
        prev_right = None
        for dev_block in ordering:
            member = dev_block.members[0]
            if run and member.left_net != prev_right:
                row.append(DiffusionBlock(
                    "device_run" if len(run) > 1 else "single", run))
                run = []
            run.append(BlockMember(member.device, member.left_net,
                                   member.right_net))
            prev_right = member.right_net
        if run:
            row.append(DiffusionBlock(
                "device_run" if len(run) > 1 else "single", run))
        out.append(row)
    return out[0], out[1]


def device_seeds(netlist, leg_widths=None):
    """The deterministic device-level seeds: the block chain exploded.

    Returns ``[(kind, ordering_p, ordering_n), ...]`` in priority order:

    1. ``"euler"`` -- euler_orderings of the default decomposition's
       row seeds (place_sa's initializer), exploded to devices;
    2. ``"seeds"`` -- the raw row seeds (the default blocks' own order),
       exploded to devices.

    Both start INSIDE the block space; device moves carry the search out
    of it.  Pure (invariant 9)."""
    blocks = build_bigcell_blocks(netlist)
    seeds = row_seeds(blocks, leg_widths)
    out = []
    for kind, (op, on) in (
            ("euler", euler_orderings(seeds, leg_widths)),
            ("seeds", (seeds[P_ROW], seeds[N_ROW]))):
        dp, dn = blocks_to_devices(op, on)
        out.append((kind, dp, dn))
    return out


# --------------------------------------------------------------------------
# the device state: place_sa._SAState over single-member blocks
# --------------------------------------------------------------------------

class _DeviceState(_SAState):
    """_SAState with the DEVICE move set (everything else inherited).

    The rows hold one single-member block per device (orientation in the
    BlockMember), so the inherited incremental row pictures, net bounds,
    congestion, gate-mismatch, cage/crossing census refresh and
    incremental==full machinery all run at DEVICE granularity unchanged.
    Only :meth:`draw_move` differs -- the task's device moves, each
    expressed as size-1 segment ops of the inherited ``apply`` format
    ``((row, origin, size, mirror, dest), ...)`` so the inherited
    ``inverse`` undoes them exactly:

    - flip:          (r, i, 1, True, None)
    - adjacent swap: (r, i, 1, False, i+1)          [shortened coords]
    - any-pair swap: (r, i, 1, False, j), (r, j-1, 1, False, i)   [i<j]
    - row-move:      (r, i, 1, False, dest)         [dest != i]

    The two-op any-pair swap moves device i after old j (old j slides
    to j-1), then old j to index i -- a pure transposition; the inverse
    (reversed (dest -> origin) ops) restores the row exactly (pinned by
    test).  ASTRAN's perturbation structure is kept: one drawn move
    touches the P row at 1/4, the N row at 1/4, both at 1/2
    (cellnetlst.cpp:462-473).
    """

    def draw_move(self, rng):
        which = rng.randrange(4)
        ops = []
        if which != 1 and self.rows[0]:
            ops.extend(self._draw_device(rng, 0))
        if which >= 2 and self.rows[1]:
            ops.extend(self._draw_device(rng, 1))
        if not ops:                       # both rows empty: cannot happen
            ops.extend(self._draw_device(rng, 0))   # pragma: no cover
        return tuple(ops)

    def _draw_device(self, rng, r):
        """One device move of a uniformly drawn type, as size-1 ops."""
        row = self.rows[r]
        n = len(row)
        if n == 1:
            # only the flip is expressible on a singleton row
            return [(r, 0, 1, True, None)]
        kind = rng.randrange(4)
        if kind == 0:                                   # flip
            i = rng.randrange(n)
            return [(r, i, 1, True, None)]
        if kind == 1:                                   # adjacent swap
            i = rng.randrange(n - 1)
            return [(r, i, 1, False, i + 1)]
        if kind == 2:                                   # any-pair swap
            i = rng.randrange(n)
            j = rng.randrange(n - 1)
            j = j if j < i else j + 1
            if j < i:
                i, j = j, i
            if j == i + 1:                              # adjacent: 1 op
                return [(r, i, 1, False, i + 1)]
            return [(r, i, 1, False, j), (r, j - 1, 1, False, i)]
        # kind == 3: row-move (relocation to any other index)
        i = rng.randrange(n)
        dest = rng.randrange(n - 1)
        if dest >= i:
            dest += 1
        return [(r, i, 1, False, dest)]


def _signal_nets(netlist):
    """The cell's signal (non-power) net names, sorted (invariant 9)."""
    nets = set()
    for dev in netlist.devices:
        nets.update((dev.drain, dev.gate, dev.source))
    return tuple(sorted(n for n in nets
                        if n not in ("VCC", "GND", "VDD", "VSS")))


def device_census(ordering_p, ordering_n, netlist, leg_widths=None):
    """``{"cage": c, "crossing": x}`` of one DEVICE arrangement -- the
    two public censuses (place_sa.gate_cage_penalty /
    crossing_cage_penalty) over the device rows; the (0, 0) probe's
    verdict function.  Pure (invariant 9)."""
    cage = gate_cage_penalty(ordering_p, ordering_n, netlist, leg_widths)[0]
    crossing = crossing_cage_penalty(ordering_p, ordering_n, netlist,
                                     leg_widths)[0]
    return {"cage": cage, "crossing": crossing}


# --------------------------------------------------------------------------
# the search: deterministic seeded Threshold Accept over device moves
# --------------------------------------------------------------------------

def device_sa(seed_p, seed_n, netlist, leg_widths, iterations=None,
              quality=DEVICE_QUALITY, init_moves=None, seed=None,
              check=True, census=True, critical_nets=None):
    """Refine one device-level seed with Threshold Accept; returns
    ``(ordering_p, ordering_n, breakdown)`` (sa_refine's shape).

    Pure and deterministic (invariant 9): the RNG is seeded from
    :func:`device_seed` (content hash, this engine's tag) unless ``seed``
    is given; every budget is an iteration count.  ``check`` asserts the
    incremental cost against a full recompute at every iteration boundary
    (a mismatch is an engine bug and raises).

    ``census=True`` (the default) steers the search with BOTH static
    censuses: the cost carries place_sa.CAGE_WEIGHT per caged gate and
    place_sa.CORE_SA_WEIGHT per walled demanded crossing, with the
    critical-net set defaulting to EVERY signal net
    (:func:`_signal_nets`) so both terms cover all nets -- one caged
    gate or walled crossing outweighs any legacy total a plausibly-sized
    cell can reach, so past the initial threshold the search prefers
    census-clean arrangements.  ``critical_nets`` overrides the set
    (the assumption-core nets, place_sa.core_critical_nets' discipline).
    ``census=False`` keeps the pure ASTRAN cost byte-for-byte (the
    legacy research path).

    ``breakdown`` is the inherited term breakdown (width/gaps/gate
    mismatch/span/congestion/caged) plus ``census`` (the final
    arrangement's two counts) and ``width_cols``."""
    crit = None
    if census:
        crit = frozenset(_signal_nets(netlist) if critical_nets is None
                         else critical_nets)
    state = _DeviceState(seed_p, seed_n, leg_widths,
                         netlist=netlist if census else None,
                         critical_nets=crit)
    rng = random.Random(seed if seed is not None
                        else device_seed(netlist))
    problem_size = max(1, len(state.rows[0]) * len(state.rows[1]))
    num_reps = max(1, int(problem_size * quality))
    if iterations is None:
        iterations = DEVICE_ITERATIONS
    if init_moves is None:
        init_moves = DEVICE_INIT_MOVES

    threshold = _find_initial_threshold(state, rng, init_moves)
    cost = state.cost()
    if cost == 0:
        op, on = state.orderings()
        return op, on, _device_breakdown(state, leg_widths)
    best = state.snapshot()
    best_cost = cost
    prev_cost = cost
    cont_same = 0
    for _it in range(iterations):
        accepts = 0
        for _i in range(num_reps):
            mv = state.draw_move(rng)
            delta = state.apply(mv)
            if delta <= threshold:
                cost += delta
                accepts += 1
            else:
                state.apply(state.inverse(mv))
        if check:
            full = state.full_recompute()
            if full != cost:
                raise RuntimeError(
                    "incremental cost %d != full recompute %d"
                    % (cost, full))
        accept_ratio = accepts / float(num_reps)
        if cost < best_cost:
            best_cost = cost
            best = state.snapshot()
        cost_ratio = cost / prev_cost if prev_cost else 1.0
        if (0.9999 <= cost_ratio <= 1.0
                and (accept_ratio < 0.8 or cost == prev_cost)):
            cont_same += 1
        else:
            cont_same = 0
            prev_cost = cost
        if cont_same > 9:
            break
        threshold = threshold * (0.98 - accept_ratio * accept_ratio / 2.0)
    state.restore(best)
    if check and state.cost() != best_cost:
        raise RuntimeError("best snapshot cost mismatch")
    op, on = state.orderings()
    return op, on, _device_breakdown(state, leg_widths)


def _device_breakdown(state, leg_widths):
    """The inherited breakdown + the device engine's own provenance
    (census counts, width columns).  Pure."""
    out = state.breakdown()
    out["census"] = {"cage": state.caged, "crossing": state.contested}
    out["width_cols"] = max(state.pic[0][3], state.pic[1][3])
    return out


def place_devices(netlist, leg_widths, budget=None, seed_orderings=None,
                  census=True, critical_nets=None, seed=None, check=True,
                  quality=DEVICE_QUALITY, init_moves=None):
    """Place one cell at DEVICE granularity; the module's entry point.

    ``netlist`` is the (folded) CellNetlist whose devices are placed
    (polarity fixed per row), ``leg_widths`` its fold map (consumed
    exactly as the block engine consumes it).  ``budget`` is the TA
    iteration count per seed (None = :data:`DEVICE_ITERATIONS`);
    ``quality``/``init_moves`` follow place_sa's sa_refine parameters;
    all iteration budgets, never wall-clock (invariant 9).

    Seeds: ``seed_orderings`` (a block-level ``(ordering_p,
    ordering_n)`` pair, exploded to devices) or the default
    :func:`device_seeds` chain (euler + row seeds).  Each seed gets its
    own TA refine (its own salted content-hash RNG stream when ``seed``
    is None); the winner is picked by

        (caged gates, walled crossings, legacy total)

    -- the census leads (a census-clean arrangement beats any cheaper
    caged one), the legacy cost breaks census ties, and the first seed
    pair that reaches census (0, 0) short-circuits the rest (the
    probe's acceptance).  With ``census=False`` the rank is the pure
    legacy total and the early exit never fires.

    Returns ``(ordering_p, ordering_n, breakdown)``: the DEVICE-level
    orderings (lists of single-member DiffusionBlock, orientation in
    the members -- feed :func:`devices_to_blocks` for the block view the
    router/verifier/GDS emitter consume) and the winning refine's
    breakdown (``device_sa``'s shape) plus ``seed_kind``/``candidates``
    provenance.  Pure and deterministic (invariant 9)."""
    if seed_orderings is not None:
        seeds = [("given",) + blocks_to_devices(*seed_orderings)]
    else:
        seeds = device_seeds(netlist, leg_widths)
    best = None
    best_key = None
    tried = []
    for salt, (kind, sp, sn) in enumerate(seeds):
        op, on, bd = device_sa(
            sp, sn, netlist, leg_widths, iterations=budget,
            quality=quality, init_moves=init_moves,
            seed=None if seed is None else seed + salt, check=check,
            census=census, critical_nets=critical_nets)
        key = (bd["census"]["cage"], bd["census"]["crossing"],
               bd["total"])
        tried.append({"seed_kind": kind, "census": bd["census"],
                      "cost": bd["total"], "width_cols": bd["width_cols"]})
        if best_key is None or key < best_key:
            best_key = key
            best = (op, on, bd, kind)
        if census and bd["census"]["cage"] == 0 \
                and bd["census"]["crossing"] == 0:
            break                       # the probe's acceptance
    op, on, bd, kind = best
    bd = dict(bd)
    bd["seed_kind"] = kind
    bd["candidates"] = tried
    return op, on, bd
