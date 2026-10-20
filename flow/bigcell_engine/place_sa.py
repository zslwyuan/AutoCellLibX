"""Threshold-Accept placement refinement (stage 3, doc section 2.2 B).

Faithful port of ASTRAN's representation and move set (cellnetlst.cpp:
462-508, thresholdaccept.h) at diffusion-block granularity: dual-row
block ordering, shift/mirror segment moves with P/N/both at 1/4 / 1/4 /
1/2 (``PorN = rand()%4``).  The cost function transfers ASTRAN's terms
term-for-term (cellnetlst.cpp:365-460):

    cost = localCong
         + 100 * (4*maxCong + 4*mismatchesGate + 2*wGaps
                  + 1*wRouting + 4*width)

with the weights autoFlow passes to placeTrans (autocell2.cpp:152:
``4, 4, 1, 4, 2``).  Two adaptations, both documented:

- ``posPN`` (ASTRAN's lockstep slot-coordinate width proxy) becomes the
  real cell width in 0.19 um columns -- max over the two rows of
  (sum of member columns + one break column per diffusion break), which
  is exactly what geometry.layout_cell emits;
- ``mismatchesGate`` counts per *column* (both rows carry a gate stripe
  in the same column with different nets) instead of per slot; net
  bounding boxes / congestion cover every diffusion edge and gate centre
  of every non-power net in one HALF-SLOT space shared by both rows --
  ASTRAN's posPN space (edge e at 2e, column c's gate at 2c+1, one
  position per terminal/gate slot, cellnetlst.cpp:406-443); power nets
  are excluded from the bbox terms, as in getCost.

Upgrades over ASTRAN:

- incremental cost evaluation: per-row column pictures (diffusion edge
  net / gate net per column) and per-net bounds are cached; a move
  rebuilds only the moved row's picture and updates only the affected
  column range (a shift/mirror provably leaves the pictures identical
  outside it) and only the nets whose bounds changed.  ``localCong`` and
  ``maxCong`` are derived from the congestion array by an O(width) scan
  per move -- simpler and stronger than partial updates for equality
  with the full recompute.  ``full_recompute`` rebuilds everything from
  the orderings; sa_refine asserts incremental == full at every
  iteration boundary (and tests do the same after random sequences);
- determinism (invariant 9): the RNG is seeded from a content hash of
  the cell (sorted device names + netlist text + engine version), all
  budgets are iteration counts -- thresholdaccept.h's 17500 s wall-clock
  escape is explicitly NOT ported -- and every output-affecting iteration
  is over sorted/insertion-ordered structures.  The per-move cost sums
  are order-independent integers, so the remaining unsorted dict walks
  cannot reach the output.  sa_refine is a pure function: same inputs
  give identical output orderings.

A move's inverse is the same machinery applied to the inverse move
(mirror is an involution; a shift's inverse shifts back), so undo is
exact without an undo log.

Routability-aware selection (doc section 2.2 "Composition" -- ASTRAN's
speculate loop, autocell2.cpp:187-216): SA's cost is blind to
routability, and on cells like the library NAND2X1 the cost-optimal
orientation is structurally unroutable (both power accesses land on the
input gate's column, leaving the output merge and the input crossing to
fight over one corridor node) while an electrically identical MIRRORED
orientation routes in one attempt.  ``sa_refine_routable`` therefore
adds a selection stage after the pure-cost refine: a deterministic pool
of top-K distinct candidate orderings (the SA best, its row
mirror/die-mirror variants, the pre-SA euler seed and its variants,
plus cost-ranked per-block flip combinations) is trial-routed by
``route_grid.route_cell`` at a REDUCED attempt budget, and the first
candidate that routes FEASIBLE wins; if none does, the candidate with
the lowest (trial conflicts, SA cost, pool index) is returned so the
caller's full-budget route starts from the best-known orientation.
The pure-cost path (``sa_refine``) is unchanged and remains available;
the selection is additive, parameterized (``candidate_count``,
``trial_attempts``, injectable ``trial_router``) and fully
deterministic (no RNG; every candidate and score is a pure function of
the inputs, invariant 9).

Decomposition-variant classes (``select_orderings``'
``variant_classes=True``): the bench_int3 evidence shows plateaus that
survive every ordering/mirror of ONE decomposition, so a lazy second
pool phase joins alternative TOTAL decompositions
(netlist_ext.build_bigcell_blocks' ``variant`` knob: base, re-phased
parallel groups, split chains/groups, all-singles, unbounded tree
coupling) as extra candidate classes -- per variant the euler+SA best
(budget-bounded, size-aware), its proven mirror classes, and alignment
nominees (aligned P/N terminal columns + corridor count, a routability
signal SA's cost cannot see, found by a capped exhaustive search over
the variant's ordering space).  Measured on the ctrl/COMPLEX0 8T
plateau (fixed pool's floor: 4 trial conflicts / 3 at full budget):
``var:singles-align4`` trial-scores 2 conflicts and the full-budget
route from it shrinks the residual {cl0#B, cl0#Y, cl1#Y} to the single
internal net {cl0#a_2_6#}.

Throughput note: DEFAULT_QUALITY is 20, not ASTRAN's 150 -- Python
applies ~5k moves/s where ASTRAN's C applies ~10^6/s; the budget is set
by measured convergence on the benchmark corpus (doc section 6, risk 1),
not by copying ASTRAN's constant.  ``quality`` stays a parameter.

The gate-cage lever (AUDIT 5.46 -- the 22-36T COMPLEX wall): the
round-6 diagnosis proved the heavy cells fail against REAL 7-track
walls -- gate contacts whose every legal crossing track sits inside a
pre-built power-stripe span at one of the crossing's two endpoint
columns -- and the lever is the PLACEMENT: arrangements whose gate
columns dodge the power-access columns.  This module ports the
forced-coverage census (scratch diag_forced_census.py) as the static
predicate :func:`gate_cage_penalty` (O(width x tracks), no router) and
applies it at three points:

- the SA cost: ``_SAState(..., netlist=...)`` carries
  ``CAGE_WEIGHT * caged_gates`` -- the term DOMINATES the legacy terms
  (which stay term-for-term ASTRAN's below it) so past the initial
  threshold the search never wanders into a power-caged arrangement;
  ``sa_refine(..., cage=True)`` / ``sa_refine_routable(..., cage=True)``
  opt in, the default keeps the pure ASTRAN cost byte-for-byte (the
  pure-cost research path and its pinned phase-1 specimens);
- the speculate selection (:func:`select_orderings`): every candidate
  carries its census count; FEASIBLE + cage-free wins immediately, a
  FEASIBLE-but-caged candidate loses to a cage-free one regardless of
  legacy cost, and the no-route fallback ranks by
  (conflicts, cage, cost, index) -- the router's honest conflict floor
  leads, the cage breaks the floor ties;
- the candidate classes: the per-block flip combinations rank
  cage-aware (:func:`generate_candidates` ``netlist``) and the
  alignment finalists break (cost, cage) ties cage-free-first
  (:func:`alignment_candidates` ``netlist``) -- pinned to the rank TAIL
  because the ctrl/COMPLEX0 M2-fingerprint closure rides a
  census-caged nominee.

Dual-basin pool (bench_int5 -> bench_int6 restoration): the steering is
a DIFFERENT SEARCH BASIN, not a strict improvement -- where it lands
well it wins (adder/COMPLEX1's zero-caged arrangement, the round-6
gains), but the pool of a steered chain no longer contains the
pure-cost (legacy) arrangements, so any cell whose closure lives in the
legacy basin loses its candidate.  Both basins therefore join the pool
of a steered chain:

- the MAIN refine runs twice -- ``cage=True`` (the steered head, pool
  priority unchanged) and ``cage=False`` (the pure ASTRAN cost); the
  legacy best becomes fixed-pool classes (``best-legacy`` plus its
  proven both-rows flip / die-mirror), ranked AFTER the ten steered
  fixed classes and BEFORE the flip combinations, so a cell closing in
  the steered head's classes is unaffected and a cell closing in the
  legacy basin gets its candidate back;
- the decomposition VARIANTS get legacy twins as a lazy THIRD phase:
  phase 2a trials the steered-refined variant classes exactly as today
  (every current closure rides it untouched); only when phase 2a finds
  no FEASIBLE candidate do the ``cage=False``-refined twins
  (``var:<name>-legacy`` and its proven mirrors) join -- the pure-cost
  arrangement of each alternative decomposition.

Selection stays trial-driven and basin-blind: the first FEASIBLE
cage-free candidate in pool order wins, a FEASIBLE-but-caged candidate
can only be beaten by a cage-free FEASIBLE one (never by a plateau),
and a legacy-basin FEASIBLE therefore always outranks a steered
plateau.  The added refines reuse agent E's size-aware budgets
verbatim; on cells above _VARIANT_SA_PROBLEM_CAP the variant twins
degenerate to the euler seed and dedupe away, so the doubling cost is
the MAIN refine (measured in the bench reports).

The crossing-level lever (AUDIT 5.49 -- the XOR/MUX/TBUF/LATCH 12T
class): M2B's CP-SAT dissection proved that class binds on
CROSSING-SAFETY (M1 landing-point supply) -- the demanded wire
crossings sit inside the power bars' mandatory coverage bands and no
track count lifts it; the freedom is the PLACEMENT.  The census
extends one level deeper than the gate-contact lever,
:func:`crossing_cage_penalty` (contact escapable -> crossing
escapable): per net the boundaries its wire MUST span (presence on
both sides) are checked for a fully-walled escape (no M1 track free of
foreign forced coverage at either endpoint, no poly escape).  It joins
the speculate selection as a rank BELOW the measured evidence (a
FEASIBLE route outranks any static census, so an M2-dissolvable M1
contest -- NAND2X1's Y -- never demotes a closing candidate):

- the speculate selection: every candidate report carries ``crossing``
  (evidence next to the router's measured floor); the FEASIBLE-but-
  caged tier key gains the crossing tie-break (a caged-FEASIBLE
  candidate whose crossings dodge the striped columns outranks an
  equal-cage contested one); the fallback ranks stay byte-compatible
  with the pinned (floor, cost, index) contracts;
- the alignment nominees break (cost, cage) ties crossing-free-first
  (:func:`alignment_candidates`);
- the SA cost and the two no-route fallback ranks are deliberately NOT
  touched: the steered basins' pinned specimens (INVX1/NAND2/NAND2X1
  ``best``, the ctrl M2-fingerprint nominee, COMPLEX4's variant
  closure) must keep their exact arrangements, the fallback ranks are
  pinned (floor, cost, index)-verbatim, and the exhaustive census
  sweeps (AUDIT 5.49 evidence) showed the 12T class's selections are
  floor-driven with NO (crossing=0, cage=0) arrangement in the
  enumerable spaces -- the census's selection role is evidence and
  tie-breaks, and the class's next lever is the CP-SAT
  sufficient-assumptions dissection, not a rank change.

TRUE-VIEW trials (the multiplier/COMPLEX4 14T closure, the last piece
of a7b23cc's chain): the trial-router contract gains an optional
trailing ``blocks`` keyword carrying the CANDIDATE'S OWN
orientation-aware block view (``list(ordering_p) + list(ordering_n)`` --
the very ``blocks`` engine meta carries for the winner), probed once
per selection (:func:`_router_accepts_blocks`) so routers without the
parameter -- every injected fake that predates it -- keep their exact
blocks-less call.  The blocks-less trial ranked a tree-arrangement
candidate by a die view the real route never recreates: on
multiplier/COMPLEX4 the closers ``var:parallel_phase-flip-both`` /
``-align3`` trialed BELOW ``var:parallel_phase-die-both`` (floors 3/6
vs 2) while their own views route clean and die-both's own view has
full-budget floor 4 with a CP-SAT-proven unwirable window.  On every
placement the pristine reconstruction explains, ``blocks`` changes
nothing (die_view returns the reconstruction either way), so cells
closing on non-tree candidates keep byte-identical trials; deriving
the view is O(#blocks) per candidate (the orderings exist), bounded
static work, no wall-clock (invariant 9).
"""

import hashlib
import inspect
import itertools
import math
import random
import re

from smt_engine.netlist import BlockMember, exposed_net_set

from bigcell_engine.geometry import (BREAK_GAP_COLS, GRID_UM, HEIGHT_UM,
                                     MID_UM, N_ROW, P_ROW, WELL_GAP_UM)
from bigcell_engine.netlist_ext import mirror_block

ENGINE_VERSION = "bigcell-sa/2"     # /2: the slot-model cost (half-slots)

POWER_NETS = ("VCC", "GND", "VDD", "VSS")

#: ASTRAN autoFlow: placeTrans(false, 150, 3, 4, 4, 1, 4, 2) --
#: (wCost, gmCost, rCost, congCost, ngCost); getCost multiplies the sum
#: by 100 and adds localCong unscaled (cellnetlst.cpp:460).
COST_WEIGHTS = {"width": 4, "gate_mismatch": 4, "span": 1,
                "max_congestion": 4, "gaps": 2}
COST_SCALE = 100

#: TA iteration cap (the same-cost rule usually terminates far earlier)
#: and ASTRAN's saquality factor, reduced for Python throughput (see
#: the module docstring).
DEFAULT_ITERATIONS = 40
DEFAULT_QUALITY = 20.0

_MAX_INT = 0xFFFFFFF

# --------------------------------------------------------------------------
# the gate-cage predicate (AUDIT 5.46: the 22-36T COMPLEX wall)
# --------------------------------------------------------------------------
# The round-6 diagnosis (commit 6b35cee, scratch diag_forced_census.py)
# proved WHY every 22-36T COMPLEX placement fails against the real 7-track
# walls: gate contacts whose every legal crossing track sits inside a
# pre-built power-stripe span at one of the crossing's two endpoint
# columns.  Power stripes are pinned geometry (a GND access spans the
# whole N half up to its rail track, a VCC access the whole P half), a
# signal diffusion access pins its own rail node, and a same-net dual
# access column's merged bars span rail-to-rail through the corridor --
# so the covered tracks are FORCED, independent of the router's freedom.
# A gate whose legal tracks are all forced-covered at c or c+1 can never
# be crossed at that placement: the wall is the PLACEMENT's, and the
# search must prefer arrangements whose gate columns dodge the power
# access columns.  This file ports the census as a static predicate over
# an ordering pair.

#: weight of the cage term in the cost.  Provenance: "proven structural
#: wall" (AUDIT 5.46) -- unlike the ASTRAN weights above this term is not
#: a proxy for area/wirelength but a routability floor measured on the
#: benchmark, so it is weighted to DOMINATE: one caged gate costs more
#: than any legacy cost a plausibly-sized cell can reach (legacy totals
#: are bounded by ~10^6 for the corpus; the term is an integer count).
CAGE_WEIGHT = 10 ** 7

#: the shared 7-track / 9-bar RouteResult contract the census speaks
#: (smt_engine.route_model: N_TRACKS, BOUNDARY_T, ROW_TRACK -- T3 is the
#: well-boundary corridor; diffusion rails sit on tracks 0/2 (N rows
#: 0/1) and 4/6 (P rows 0/1)).  Frozen constants, re-declared here so
#: the placement-side predicate stays standalone (no router import in
#: the cost path); route_grid's track-count-parametric widening is the
#: documented extension path and must widen this map in lockstep.
CAGE_N_TRACKS = 7
CAGE_BOUNDARY_T = 3
CAGE_RAIL_TRACK = {0: 0, 1: 2, 2: 4, 3: 6}
#: the poly-jump row tracks (route_model.ROW_TRACKS) and the diffusion
#: row each carries (route_grid._ROW_OF_TRACK) -- a gate contact may
#: cross on the POLY layer where M1 is walled (route_grid._gate_forced's
#: ``m1_ok or pj_ok`` disjunction, the authority this predicate mirrors)
CAGE_ROW_TRACKS = (0, 2, 4, 6)

GND_NAMES = ("GND", "VSS")
VCC_NAMES = ("VCC", "VDD")

_TRACK_MODEL = None


def _track_model():
    """(span_n, span_p, span_np, corridor).

    span_*: the raw gate-stripe y-spans' covered row tracks for a gate
    carried by the N row only / P row only / both rows -- a gate with
    this span blocks foreign poly jumps on exactly these row tracks
    (route_grid._spans_track over route_grid._gate_span).  corridor:
    the well-boundary tracks an ALIGNED P/N gate pair's merged poly
    offers (route_grid._gate_maps' strip_pol branch).  Rows are uniform
    in polarity (P row 0, N row 1 -- geometry.place_row's contract), so
    a gate's contributing bands are one of exactly three merges.
    Cached; pure."""
    global _TRACK_MODEL
    if _TRACK_MODEL is None:
        from smt_engine.gds import CONTACT_S, POLY_OVERHANG
        from smt_engine.gds import row_geometry, track_geometry
        trackY, _bar = track_geometry(HEIGHT_UM, GRID_UM)
        _rails, rows = row_geometry(HEIGHT_UM, GRID_UM)

        def _span(bands):
            y0 = min(b[0] for b in bands) - POLY_OVERHANG
            y1 = max(b[1] for b in bands) + POLY_OVERHANG
            return frozenset(t for t in CAGE_ROW_TRACKS
                             if y0 <= trackY[t] <= y1)

        n_band = rows[(False, N_ROW)]
        p_band = rows[(True, P_ROW)]
        half = CONTACT_S / 2.0
        corridor = frozenset(
            t for t in range(CAGE_N_TRACKS)
            if MID_UM - WELL_GAP_UM + half <= trackY[t]
            <= MID_UM + WELL_GAP_UM - half)
        _TRACK_MODEL = (_span((n_band,)), _span((p_band,)),
                        _span((n_band, p_band)), corridor)
    return _TRACK_MODEL


_DEVICE_CROSS_CACHE = {}


def _device_cross_tracks(dev):
    """The tracks ONE device's drawn strip offers its gate contact --
    route_grid._gate_maps' slot math verbatim: the W-tall strip
    intersected with the device's row band, shrunk by CONTACT_S/2.
    Depends only on (polarity, width); cached (pure, invariant 9)."""
    key = (dev.is_p, dev.width_um)
    got = _DEVICE_CROSS_CACHE.get(key)
    if got is None:
        from smt_engine.gds import CONTACT_S, POLY_OVERHANG
        from smt_engine.gds import row_geometry, track_geometry
        trackY, _bar = track_geometry(HEIGHT_UM, GRID_UM)
        _rails, rows = row_geometry(HEIGHT_UM, GRID_UM)
        half = CONTACT_S / 2.0
        y0, y1 = rows[(dev.is_p, P_ROW if dev.is_p else N_ROW)]
        w = dev.width_um
        if dev.is_p:
            sy0 = MID_UM + WELL_GAP_UM
        else:
            sy0 = MID_UM - WELL_GAP_UM - w
        sy1 = sy0 + w
        lo = max(sy0, y0) - POLY_OVERHANG + half
        hi = min(sy1, y1) + POLY_OVERHANG - half
        got = frozenset(t for t in range(CAGE_N_TRACKS)
                        if lo <= trackY[t] <= hi)
        if len(_DEVICE_CROSS_CACHE) > 4096:   # keep the cache bounded
            _DEVICE_CROSS_CACHE.clear()
        _DEVICE_CROSS_CACHE[key] = got
    return got


def _cage_row_view(entries, is_p, exposed):
    """One row's cage view (edges, counts, gates, forced, active, width).

    ``entries`` is the row's oriented _Entry sequence (the same objects
    _SAState.rows holds).  Walked exactly like _row_picture /
    geometry.place_row: one break column where the facing end nets
    differ.  ``gates`` maps (gate net, column) -> the union of the
    carrying devices' crossing tracks (route_grid._gate_maps' per-device
    strip math).  ``forced`` maps column -> {track: set(nets)} for the
    build-time metal THIS row pins: a power access covers its
    half-domain up to the device's rail track (GND: tracks 0..rail in
    the N slot, VCC: rail..6 in the P slot) and a contactable signal
    diffusion access (per-row contactability, the die_slot_access_points
    rule: multi-region within the row, or an exposed block-end net) pins
    its own rail node.  ``active`` is the row's diffusion-span columns
    (route_grid._field_map's active set)."""
    edges = {}
    counts = {}
    gates = {}
    rail = CAGE_RAIL_TRACK[P_ROW + 2 if is_p else N_ROW]
    forced = {}
    active = set()
    col = 0
    prev_right = None
    for entry in entries:
        if prev_right is not None \
                and entry.members[0][1] != prev_right:
            col += 1
        for dev, lnet, rnet, w, centres in entry.members:
            edges[col] = lnet
            tracks = _device_cross_tracks(dev)
            for off in centres:
                key = (dev.gate, col + off)
                got = gates.get(key)
                if got is None:
                    gates[key] = set(tracks)
                else:
                    got.update(tracks)
            col += w
            edges[col] = rnet
            active.update(range(col - w, col))
        prev_right = entry.members[-1][2]
    for c, net in edges.items():
        counts[net] = counts.get(net, 0) + 1
    for c, net in edges.items():
        if net in POWER_NETS:
            slots = forced.setdefault(c, {})
            if net in GND_NAMES:
                for t in range(0, rail + 1):
                    slots.setdefault(t, set()).add(net)
            else:
                for t in range(rail, CAGE_N_TRACKS):
                    slots.setdefault(t, set()).add(net)
        elif counts[net] > 1 or net in exposed:
            forced.setdefault(c, {}).setdefault(rail, set()).add(net)
    return edges, counts, gates, forced, active, col


def _cage_from_views(vp, vn, exposed):
    """The census over two row views (see :func:`gate_cage_penalty` for
    the model).  Split from it so the alignment nomination can score
    pairs from per-row precomputed views without re-walking."""
    span_n, span_p, span_np, corridor = _track_model()
    span_of = {False: span_p, True: span_np}   # keyed by "carries P row"
    B = CAGE_BOUNDARY_T
    ep, counts_p, gates_p, forced_p, active_p, wp = vp
    en, counts_n, gates_n, forced_n, active_n, wn = vn
    rw = (wp if wp >= wn else wn) + 1  # slot model: the edge axis
    # same-net dual access columns: a net exposed on BOTH rows at one
    # column (contactable per row in each) merges its bars rail-to-rail
    # through the corridor at that column -- the tie stripe spans from
    # its N rail up to its P rail (the census docstring's spelling; the
    # census CODE covered the whole P half, which produced false cages
    # on closing arrangements -- ctrl/COMPLEX0's M2-fingerprint winner)
    duals = {}
    for c, net_n in en.items():
        if net_n in POWER_NETS or ep.get(c) != net_n:
            continue
        if not (counts_n[net_n] > 1 or net_n in exposed):
            continue
        if not (counts_p[net_n] > 1 or net_n in exposed):
            continue
        duals[c] = (net_n, CAGE_RAIL_TRACK[P_ROW + 2])
    # gate contacts: (gate net, column) -> merged crossing tracks +
    # which rows carry it; per column the raw poly spans of every gate
    # stripe (the foreign side of the poly-jump legality)
    legal_of = {}
    gspans = {}
    for (net, c), tracks in gates_p.items():     # P row
        legal_of[(net, c)] = [tracks, False, True]
        gspans.setdefault(c, {})[net] = span_of[True]
    for (net, c), tracks in gates_n.items():     # N row
        got = legal_of.get((net, c))
        if got is None:
            legal_of[(net, c)] = [tracks, True, False]
        else:
            got[0] = got[0] | tracks
            got[1] = True
        gspans.setdefault(c, {}).setdefault(net, span_of[False])
    caged = 0
    columns = set()
    for (net, c), (legal, in_n, in_p) in legal_of.items():
        if in_n and in_p:
            legal = legal | corridor
        if not legal:
            continue                   # the census counts only non-empty gt
        free = False
        for t in legal:
            blocked = False
            for cc in (c, c + 1):
                if cc >= rw:
                    continue
                slots = (forced_n if t < B else forced_p).get(cc)
                if slots:
                    others = slots.get(t)
                    if others and (len(others) > 1 or net not in others):
                        blocked = True
                        break
                dual = duals.get(cc)
                if (dual is not None and dual[0] != net
                        and CAGE_RAIL_TRACK[N_ROW] <= t <= dual[1]):
                    blocked = True
                    break
            if blocked:
                # the poly escape: a row-track jump over field oxide
                # whose column c hosts no foreign gate stripe on t.
                # Tracks 0/6 belong to the unused outer rows (no active
                # anywhere); 2/4 are the used N/P rows.
                if t in CAGE_ROW_TRACKS:
                    row_active = (active_n if t == 2
                                  else active_p if t == 4 else ())
                    if ((c + 1) not in row_active
                            and all(n == net
                                    for n, sp in gspans[c].items()
                                    if t in sp)):
                        free = True
                        break
                continue
            free = True
            break
        if not free:
            caged += 1
            columns.add(c)
    return caged, tuple(sorted(columns))


def gate_cage_penalty(ordering_p, ordering_n, netlist, leg_widths=None):
    """Static gate-cage census over one ordering pair (AUDIT 5.46).

    Returns ``(caged_gates, blocked_columns)``: how many gate contacts
    are hard-blocked and which columns host them -- 0/() when every
    gate contact has a free lane.  O(width x tracks) per call, no
    router involved.

    The model (port of flow/_stage3_check/diag_forced_census.py's
    forced-coverage census, derived from the ordering pair via the same
    walk geometry.place_row / _row_picture use):

    - per-column FORCED coverage (see :func:`_cage_row_view`): power
      accesses pin their half-domain, contactable signal accesses pin
      their rail node, same-net dual access columns pin rail-to-rail
      through the corridor;
    - a gate contact at column c is HARD-BLOCKED iff no legal track t
      survives, where t survives when its crossing endpoints c, c+1 are
      free of foreign forced coverage in the track's slot (N slot for
      t < 3, P slot for t >= 3; the gate's own net never blocks itself),
      OR the poly escape exists (route_grid._gate_forced's
      ``m1_ok or pj_ok`` disjunction: t is a row track whose (c+1) end
      is field oxide in the track's row and no foreign gate stripe spans
      t at c -- the census's M1-only spelling, extended because the
      closers' gates cross exactly through that escape, INVX1 being the
      minimal case);
    - the legal tracks are the router's own slot-model set
      (route_grid._gate_maps: per-device strip x row band, plus the
      corridor where an aligned P/N pair merges the poly).

    ``ordering_p``/``ordering_n`` are the oriented block sequences
    (mirror_block state included -- the edge nets are read as they sit);
    ``netlist`` is the (folded) CellNetlist the orderings decompose (it
    supplies the exposed-net set); ``leg_widths`` the fold map
    (device name -> (legs, leg_width_cols)), defaulting to the slot
    model's (1, 1).  Pure and deterministic (invariant 9)."""
    if leg_widths is None:
        devices = [m.device for row in (ordering_p, ordering_n)
                   for b in row for m in b.members]
        leg_widths = {dev.name: (1, 1) for dev in devices}
    exposed = exposed_net_set(netlist) if netlist is not None else None
    if exposed is None:
        return 0, ()
    vp = _cage_row_view([_entry(b, False, leg_widths)
                         for b in ordering_p], True, exposed)
    vn = _cage_row_view([_entry(b, False, leg_widths)
                         for b in ordering_n], False, exposed)
    return _cage_from_views(vp, vn, exposed)


# --------------------------------------------------------------------------
# the crossing-level predicate (AUDIT 5.49: the XOR/MUX/TBUF/LATCH class)
# --------------------------------------------------------------------------
# M2B's CP-SAT dissection proved the 12T class binds on CROSSING-SAFETY
# (M1 landing-point supply): dropping that one constraint family alone
# flips each exact model to OPTIMAL and verify then fails exactly at
# crossings INSIDE the power bars' mandatory coverage bands (a GND
# access column's stripe covers T0-T2, a VCC access column's T4-T6 --
# the coverage is forced by the "reach the power end" rule, not the
# router's freedom), and adding tracks does not lift it (k=12 still
# INFEASIBLE).  The lever is the PLACEMENT axis: the demanded crossings
# must move off the striped columns, one level deeper than agent H's
# gate-contact census -- a gate column whose CONTACT has a poly escape
# can still wall the net's OTHER crossings (a plain M1 span has no
# contact to hide behind).

def _crossing_from_views(vp, vn, exposed):
    """The crossing-contest census over two row views (see
    :func:`crossing_cage_penalty` for the model).  Split from it so the
    alignment nomination can score pairs from per-row precomputed views
    without re-walking.  Same slot conventions as :func:`_cage_from_views`
    (N slot for t < BOUNDARY_T, P slot above; same-net dual blankets
    rail-to-rail through the corridor; the poly escape on row tracks)."""
    B = CAGE_BOUNDARY_T
    ep, counts_p, gates_p, forced_p, active_p, wp = vp
    en, counts_n, gates_n, forced_n, active_n, wn = vn
    rw = (wp if wp >= wn else wn) + 1  # slot model: the edge axis
    # same-net dual access columns (the census's spelling: a net
    # contactable on BOTH rows at one column merges its bars
    # rail-to-rail through the corridor -- its blanket spans from the
    # N rail track up to the P rail track)
    duals = {}
    for c, net_n in en.items():
        if net_n in POWER_NETS or ep.get(c) != net_n:
            continue
        if not (counts_n[net_n] > 1 or net_n in exposed):
            continue
        if not (counts_p[net_n] > 1 or net_n in exposed):
            continue
        duals[c] = (net_n, CAGE_RAIL_TRACK[P_ROW + 2])
    # per-net M1 presence columns: a contactable diffusion access pins
    # its rail (the row views' own forced map), a gate contact's
    # crossing spans [c, c+1] (verify's rule (c): every gate column
    # carries a crossing, so both endpoint columns hold the net's M1)
    presence = {}
    for forced in (forced_n, forced_p):
        for c, slots in forced.items():
            for nets in slots.values():
                for net in nets:
                    if net not in POWER_NETS:
                        presence.setdefault(net, set()).add(c)
    for gates_map in (gates_p, gates_n):
        for (net, c) in gates_map:
            got = presence.setdefault(net, set())
            got.add(c)
            got.add(c + 1)
    # the raw poly spans of every gate stripe per column (the foreign
    # side of the poly-jump legality, as in the census)
    span_n, span_p, span_np, _corridor = _track_model()
    span_of = {False: span_p, True: span_np}
    gspans = {}
    for (net, c) in gates_p:                 # P row
        gspans.setdefault(c, {})[net] = span_of[True]
    for (net, c) in gates_n:                 # N row
        gspans.setdefault(c, {}).setdefault(net, span_of[False])

    def _escape_tracks(net, c):
        """The tracks net ``net`` can cross boundary (c, c+1) on:
        M1 where both endpoint columns are free of foreign forced
        coverage in the track's slot (the net's own pins never block
        it), plus the ANCHORED poly escape (route_model's E4 rule:
        every maximal poly run must cross a same-net gate, and the
        gate merge is the only M1<->poly junction -- so unlike the
        gate-contact census, whose contact at c is its own anchor, a
        plain boundary's poly jump needs the net's OWN gate stripe
        spanning t at the crossed column c; T3 has no poly escape)."""
        out = []
        for t in range(CAGE_N_TRACKS):
            blocked = False
            for cc in (c, c + 1):
                slots = (forced_n if t < B else forced_p).get(cc)
                if slots:
                    others = slots.get(t)
                    if others and (len(others) > 1 or net not in others):
                        blocked = True
                        break
                dual = duals.get(cc)
                if (dual is not None and dual[0] != net
                        and CAGE_RAIL_TRACK[N_ROW] <= t <= dual[1]):
                    blocked = True
                    break
            if not blocked:
                out.append(t)
                continue
            # the anchored poly escape: a row-track jump over field
            # oxide whose column c hosts no foreign gate stripe on t
            # and hosts the net's own (the run anchor)
            if t in CAGE_ROW_TRACKS:
                row_active = (active_n if t == 2
                              else active_p if t == 4 else ())
                spans = gspans.get(c, {})
                if ((c + 1) not in row_active
                        and all(n == net
                                for n, sp in spans.items() if t in sp)
                        and any(n == net and t in sp
                                for n, sp in spans.items())):
                    out.append(t)
        return out

    contested = 0
    columns = set()
    claims = {}                              # (track, col) -> {nets}
    for net in sorted(presence):
        cols = presence[net]
        lo, hi = min(cols), max(cols)
        if lo == hi:
            continue
        for c in range(lo, hi):
            # boundary (c, c+1) is DEMANDED: the net's wire must span
            # it (presence on both sides -- the exact model's sweep
            # forces presence in every column between the leftmost and
            # rightmost access and bridges every gap)
            if c + 1 >= rw:
                continue
            escapes = _escape_tracks(net, c)
            if not escapes:
                # level 1: every lane is walled (power band / dual
                # blanket / foreign rail pin, no anchored poly escape)
                contested += 1
                columns.add(c)
            elif len(escapes) == 1:
                # level 2: the sole surviving lane FORCES the
                # crossing onto it (route_grid._gate_forced's rule:
                # the crossing segment claims both endpoint nodes,
                # and M2 cannot lift a forced M1 crossing) -- two
                # nets forced onto the same node contest it
                t = escapes[0]
                for cc in (c, c + 1):
                    claims.setdefault((t, cc), set()).add(net)
    for (t, cc), nets in sorted(claims.items()):
        if len(nets) > 1:
            contested += 1
            columns.add(cc)
    return contested, tuple(sorted(columns))


def crossing_cage_penalty(ordering_p, ordering_n, netlist, leg_widths=None):
    """Static crossing-contest census over one ordering pair (AUDIT
    5.49's placement-axis lever).

    Returns ``(contested_crossings, blocked_boundaries)``: how many
    boundaries a signal net MUST span (M1 landing supply) have no
    escapable track at all, and the sorted left columns of those
    boundaries -- 0/() when every demanded crossing has a lane.
    O(width x tracks x nets) per call, no router involved.

    The model (the gate-contact census of :func:`gate_cage_penalty`
    extended one level deeper, contact escapable -> crossing escapable):

    - per-net M1 PRESENCE columns: contactable diffusion accesses pin
      their rail (the row views' forced map), a gate contact's crossing
      spans [c, c+1] (verify's rule (c) demands a crossing for every
      gate column, so both endpoint columns hold the net's M1);
    - a boundary (c, c+1) is DEMANDED for a net when the net's presence
      has a column at or left of c AND at or right of c+1 -- the exact
      model's connectivity sweep forces presence in every column
      between the leftmost and rightmost access and bridges every gap,
      so the wire cannot dodge the boundary;
    - the boundary is CONTESTED at two levels:
      level 1 -- no track escapes it: M1 needs both endpoint columns
      free of foreign forced coverage in the track's slot (N slot for
      t < 3, P slot for t >= 3; power bands T0-T2 / T4-T6, contactable
      signal rail pins, same-net dual blankets rail-to-rail -- the
      net's own pins never block it), and the ANCHORED poly escape
      (row track over field oxide at c+1, the net's OWN gate stripe
      spanning t at c and no foreign stripe there -- route_model's E4
      run-anchoring: unlike a gate contact, which is its own anchor, a
      plain boundary's poly jump needs a same-net gate merge inside
      the run; T3 has no poly escape);
      level 2 -- a boundary whose SOLE surviving lane forces the
      crossing onto it (route_grid._gate_forced's rule: the crossing
      segment claims both endpoint nodes and M2 cannot lift a forced
      M1 crossing); two nets forced onto the same node contest it --
      the downstream mechanism that makes the class INFEASIBLE (the
      forced lane is usually the T3 corridor);

    Known blind spots, by design (documented honesty): only FORCED
    node claims are counted (a net that merely CHOOSES the contested
    lane is not -- the under-approximation never invents a contest,
    matching :meth:`route_grid._RouteGrid.structural_diagnosis`'s
    discipline), multi-boundary poly runs anchoring left of c are not
    modelled (the anchored escape is local, so the census may
    over-count), and the metal2 span vocabulary is not modelled (an
    M1-contested boundary the M2 freedom could dissolve is
    over-counted -- the term therefore only ever ranks candidates that
    failed their trials, never demotes a FEASIBLE winner whose route
    already proves the arrangement).

    ``ordering_p``/``ordering_n`` are the oriented block sequences
    (mirror_block state included -- the edge nets are read as they sit);
    ``netlist`` is the (folded) CellNetlist the orderings decompose (it
    supplies the exposed-net set); ``leg_widths`` the fold map
    (device name -> (legs, leg_width_cols)), defaulting to the slot
    model's (1, 1).  Pure and deterministic (invariant 9)."""
    if leg_widths is None:
        devices = [m.device for row in (ordering_p, ordering_n)
                   for b in row for m in b.members]
        leg_widths = {dev.name: (1, 1) for dev in devices}
    exposed = exposed_net_set(netlist) if netlist is not None else None
    if exposed is None:
        return 0, ()
    vp = _cage_row_view([_entry(b, False, leg_widths)
                         for b in ordering_p], True, exposed)
    vn = _cage_row_view([_entry(b, False, leg_widths)
                         for b in ordering_n], False, exposed)
    return _crossing_from_views(vp, vn, exposed)


def cell_seed(netlist):
    """Content-derived RNG seed (doc section 3.1): sorted device names +
    netlist text + engine version, sha256, never hash() (invariant 9)."""
    sub = netlist.subckt
    parts = ["%s|%s" % (sub.subckt_name, ",".join(sub.ports))]
    for dev in sorted(netlist.devices, key=lambda d: d.name):
        parts.append("%s %s %s %s %d %s" % (
            dev.name, dev.drain, dev.gate, dev.source,
            1 if dev.is_p else 0, float(dev.width_um)))
    digest = hashlib.sha256(
        ("|".join(parts) + "|" + ENGINE_VERSION).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


class _Entry(object):
    """One oriented block in a row: immutable, flip via the factory."""

    __slots__ = ("block", "flip", "width", "members")

    def __init__(self, block, flip, members, width):
        self.block = block
        self.flip = flip
        self.members = members        # ((dev, left, right, w, centres), ..)
        self.width = width


_ENTRY_CACHE = {}


def _entry(block, flip, leg_widths):
    key = (id(block), flip)
    got = _ENTRY_CACHE.get(key)
    if got is not None and got[0] is block:
        return got[1]
    members = []
    width = 0
    oriented = block.members if not flip else [
        BlockMember(m.device, m.right_net, m.left_net)
        for m in reversed(block.members)]
    for m in oriented:
        legs, cols = leg_widths[m.device.name]
        w = legs * cols
        centres = tuple(j * cols + cols // 2 for j in range(legs))
        members.append((m.device, m.left_net, m.right_net, w, centres))
        width += w
    entry = _Entry(block, flip, tuple(members), width)
    if len(_ENTRY_CACHE) > 4096:          # keep the cache bounded
        _ENTRY_CACHE.clear()
    # the cache holds the block reference so id(block) cannot be
    # recycled while the entry is cached
    _ENTRY_CACHE[key] = (block, entry)
    return entry


def _row_picture(entries):
    """Half-slot picture of one row, mirroring geometry.place_row exactly:
    one break column where a block's left net differs from the previous
    block's right net; a member registers its left net at its left edge
    (2*col), right net at its right edge (2*(col+w)) and its gate
    stripes at the leg centres (2*(col+j*legw)+1) -- the slot space
    ASTRAN's posPN counts (doc/BIGCELL_SLOT_GEOMETRY.md section 4).
    Returns (dnet, gate, breaks, width_cols, starts, ends)."""
    dnet = {}
    gate = {}
    col = 0
    breaks = 0
    prev_right = None
    starts = []
    ends = []
    for entry in entries:
        starts.append(col)
        if prev_right is not None and entry.members[0][1] != prev_right:
            col += 1
            breaks += 1
        end = col
        for dev, lnet, rnet, w, centres in entry.members:
            dnet[2 * col] = lnet
            for off in centres:
                gate[2 * (col + off) + 1] = dev.gate
            col += w
            end = col - 1
            dnet[2 * col] = rnet
        ends.append(end)
        prev_right = entry.members[-1][2]
    return dnet, gate, breaks, col, starts, ends


def _bounds_from_pics(dnet, gate, power):
    """{net: (lo, hi)} over both picture kinds, power nets excluded."""
    bounds = {}
    for col, net in dnet.items():
        if net in power:
            continue
        got = bounds.get(net)
        if got is None:
            bounds[net] = (col, col)
        elif col < got[0]:
            bounds[net] = (col, got[1])
        elif col > got[1]:
            bounds[net] = (got[0], col)
    for col, net in gate.items():
        if net in power:
            continue
        got = bounds.get(net)
        if got is None:
            bounds[net] = (col, col)
        elif col < got[0]:
            bounds[net] = (col, got[1])
        elif col > got[1]:
            bounds[net] = (got[0], col)
    return bounds


class _SAState(object):
    """Dual-row ordering + cached cost.  All arithmetic is integer.

    With ``netlist`` given, the cost carries the gate-cage term
    (:func:`gate_cage_penalty`, weight CAGE_WEIGHT -- the proven
    structural wall of AUDIT 5.46): total = legacy total +
    CAGE_WEIGHT * caged_gates, so a placement that cages a gate contact
    under power metal loses against ANY cage-free arrangement
    regardless of the legacy terms, which stay term-for-term ASTRAN's.
    The scan is refreshed exactly (full recompute of the census) on
    every picture change, so the incremental delta the TA loop accepts
    on includes the cage delta and ``sa_refine``'s check (incremental
    == full) keeps holding.  ``netlist=None`` (the default) skips the
    scan: the cost is byte-identical legacy -- the pure-cost path's
    contract, consumed by tests that construct the state directly.
    """

    def __init__(self, ordering_p, ordering_n, leg_widths, netlist=None):
        if leg_widths is None:
            # geometry.default_leg_widths' slot-model semantics: one leg
            # of one column per device (W is vertical).
            devices = [m.device for row in (ordering_p, ordering_n)
                       for b in row for m in b.members]
            leg_widths = {dev.name: (1, 1) for dev in devices}
        self.leg_widths = leg_widths
        self.rows = [[_entry(b, False, leg_widths) for b in ordering_p],
                     [_entry(b, False, leg_widths) for b in ordering_n]]
        self.power = frozenset(POWER_NETS)
        # the census's exposure set, frozen once (None disables the term)
        self.exposed = None if netlist is None else \
            frozenset(exposed_net_set(netlist))
        self._cage_cache = None
        self._view_cache = [None, None]
        total_w = sum(e.width for row in self.rows for e in row)
        breaks_ub = sum(max(0, len(row) - 1) for row in self.rows)
        # the pictures live in half-slots (edges 2e, gates 2c+1)
        self.max_cols = 2 * (total_w + breaks_ub) + 3
        self.full_recompute()

    # -- moves ---------------------------------------------------------

    def draw_move(self, rng):
        """ASTRAN's perturbation (cellnetlst.cpp:462-473): P at 1/4,
        N at 1/4, both at 1/2; each row move is a random segment either
        shifted elsewhere or mirrored (move(), :475-508)."""
        which = rng.randrange(4)
        moves = []
        if which != 1:
            moves.append(self._draw_row(rng, 0))
        if which >= 2:
            moves.append(self._draw_row(rng, 1))
        return tuple(moves)

    def _draw_row(self, rng, r):
        row = self.rows[r]
        n = len(row)
        size = 1 + rng.randrange(n)
        origin = rng.randrange(n - size + 1)
        if rng.randrange(2):
            return (r, origin, size, True, None)       # mirror
        dest = rng.randrange(n - size + 1)             # ASTRAN: over the
        return (r, origin, size, False, dest)          # shortened list

    @staticmethod
    def inverse(move):
        out = []
        for r, origin, size, mirror, dest in reversed(move):
            if mirror:
                out.append((r, origin, size, True, None))
            else:
                out.append((r, dest, size, False, origin))
        return tuple(out)

    def apply(self, move):
        """Apply a move; return the exact cost delta (incremental)."""
        old = self.total
        for r, origin, size, mirror, dest in move:
            self._apply_row(r, origin, size, mirror, dest)
        return self.total - old

    def _apply_row(self, r, origin, size, mirror, dest):
        row = self.rows[r]
        old_pic = self.pic[r]
        if mirror:
            seg = [_entry(e.block, not e.flip, self.leg_widths)
                   for e in row[origin:origin + size]][::-1]
            row[origin:origin + size] = seg
        else:
            seg = row[origin:origin + size]
            del row[origin:origin + size]
            row[dest:dest] = seg
        new_pic = _row_picture(row)
        self._diff_row(r, old_pic, new_pic)

    # -- incremental cache maintenance ---------------------------------

    def _diff_row(self, r, old_pic, new_pic):
        old_gate = old_pic[1]
        new_gate = new_pic[1]
        other_gate = self.pic[1 - r][1]
        # gate mismatches, per column, over the SPARSE union of the old
        # and new gate columns.  No tighter range is safe here: a shift
        # can change the break count at the span's edge, which translates
        # every later block's columns, so the whole row may move.
        # (Everything else below is derived from full-picture walks.)
        for col in old_gate.keys() | new_gate.keys():
            was = old_gate.get(col)
            now = new_gate.get(col)
            if was == now:
                continue
            if was is not None:
                other = other_gate.get(col)
                if other is not None and other != was:
                    self.gate_mismatch -= 1
            if now is not None:
                other = other_gate.get(col)
                if other is not None and other != now:
                    self.gate_mismatch += 1
        self.pic[r] = new_pic
        # per-row net bounds: rebuilt from the moved row's new picture
        # (one walk), then merged into the global bbox per changed net
        bounds = self.row_bounds[r]
        new_bounds = _bounds_from_pics(new_pic[0], new_pic[1], self.power)
        for net, got in new_bounds.items():
            if bounds.get(net) != got:
                bounds[net] = got
                self._refresh_net(net)
        for net in [n for n in bounds if n not in new_bounds]:
            del bounds[net]
            self._refresh_net(net)
        self.local_cong = sum(v * v for v in self.cong)
        self.max_cong = max(self.cong)
        self._refresh_cage()
        self.total = self._total_from_terms() + CAGE_WEIGHT * self.caged

    def _refresh_cage(self):
        """Re-run the gate-cage census over the current rows.

        The census is a pure function of the two rows' ENTRY sequences,
        and an undone move restores the exact previous entry objects
        (_entry caches by (block, flip)), so the last scan is cached by
        row content: the TA loop's reject path (apply + apply(inverse))
        pays one list comparison instead of a second scan.  Per-row
        views are cached the same way, so a single-row move rebuilds
        only the moved row's view."""
        if self.exposed is None:
            self.caged = 0
            self.cage_cols = ()
            return
        cache = self._cage_cache
        if cache is not None \
                and cache[0] == self.rows[0] and cache[1] == self.rows[1]:
            self.caged, self.cage_cols = cache[2], cache[3]
            return
        vc = self._view_cache
        views = []
        for r in (0, 1):
            got = vc[r]
            if got is None or got[1] != self.rows[r]:
                vc[r] = (_cage_row_view(self.rows[r], r == 0, self.exposed),
                         list(self.rows[r]))
            views.append(vc[r][0])
        self.caged, self.cage_cols = _cage_from_views(
            views[0], views[1], self.exposed)
        self._cage_cache = (list(self.rows[0]), list(self.rows[1]),
                            self.caged, self.cage_cols)

    def _refresh_net(self, net):
        """Merge a net's changed per-row bounds into its global bbox;
        routing spans and the congestion array follow.  Only the columns
        that LEAVE/ENTER the bbox are touched (symmetric difference)."""
        lo = hi = None
        for row_bounds in self.row_bounds:
            got = row_bounds.get(net)
            if got is not None:
                lo = got[0] if lo is None else min(lo, got[0])
                hi = got[1] if hi is None else max(hi, got[1])
        old = self.net_bbox.get(net)
        if lo is None:
            if old is not None:
                self._cong_add(old[0], old[1], -1)
                self.w_routing -= old[1] - old[0]
                del self.net_bbox[net]
            return
        if old == (lo, hi):
            return
        if old is None:
            self._cong_add(lo, hi, 1)
            self.w_routing += hi - lo
        else:
            a, b = old
            # columns leaving the old bbox
            self._cong_add(a, min(b, lo - 1), -1)
            self._cong_add(max(a, hi + 1), b, -1)
            # columns entering the new bbox
            self._cong_add(lo, min(hi, a - 1), 1)
            self._cong_add(max(b + 1, lo), hi, 1)
            self.w_routing += (hi - lo) - (b - a)
        self.net_bbox[net] = (lo, hi)

    def _cong_add(self, lo, hi, delta):
        if lo > hi:
            return
        cong = self.cong
        for x in range(lo, hi + 1):
            cong[x] += delta

    def _total_from_terms(self):
        w = COST_WEIGHTS
        gaps = self.pic[0][2] + self.pic[1][2]
        width = max(self.pic[0][3], self.pic[1][3])
        return (self.local_cong
                + COST_SCALE * (w["max_congestion"] * self.max_cong
                                + w["gate_mismatch"] * self.gate_mismatch
                                + w["gaps"] * gaps
                                + w["span"] * self.w_routing
                                + w["width"] * width))

    def cost(self):
        return self.total

    def breakdown(self):
        return {
            "width": max(self.pic[0][3], self.pic[1][3]),
            "gaps": self.pic[0][2] + self.pic[1][2],
            "gate_mismatch": self.gate_mismatch,
            "span": self.w_routing,
            "max_congestion": self.max_cong,
            "local_congestion": self.local_cong,
            "caged_gates": self.caged,
            "total": self.total,
        }

    # -- full recompute (the incremental path's reference) --------------

    def full_recompute(self):
        self.pic = [_row_picture(row) for row in self.rows]
        self.row_bounds = [_bounds_from_pics(pic[0], pic[1], self.power)
                           for pic in self.pic]
        self.net_bbox = {}
        for bounds in self.row_bounds:
            for net, (lo, hi) in bounds.items():
                got = self.net_bbox.get(net)
                if got is None:
                    self.net_bbox[net] = (lo, hi)
                else:
                    self.net_bbox[net] = (min(got[0], lo), max(got[1], hi))
        self.cong = [0] * self.max_cols
        for lo, hi in self.net_bbox.values():
            for x in range(lo, hi + 1):
                self.cong[x] += 1
        self.local_cong = sum(v * v for v in self.cong)
        self.max_cong = max(self.cong)
        self.w_routing = sum(hi - lo
                             for lo, hi in self.net_bbox.values())
        g0, g1 = self.pic[0][1], self.pic[1][1]
        self.gate_mismatch = sum(
            1 for col in set(g0) & set(g1) if g0[col] != g1[col])
        self._refresh_cage()
        self.total = self._total_from_terms() + CAGE_WEIGHT * self.caged
        return self.total

    # -- snapshot / restore ---------------------------------------------

    def snapshot(self):
        return (list(self.rows[0]), list(self.rows[1]))

    def restore(self, snap):
        self.rows = [list(snap[0]), list(snap[1])]
        self.full_recompute()

    # -- materialization -------------------------------------------------

    def orderings(self):
        """Materialized block sequences (flips become real blocks)."""
        out = []
        for row in self.rows:
            out.append([e.block if not e.flip
                        else mirror_block(e.block) for e in row])
        return out[0], out[1]


def _find_initial_threshold(state, rng, moves):
    """thresholdaccept.h:22-81: bisection for the threshold where the
    average accepted delta is zero, ``moves`` perturbations per step on a
    scratch copy of the solution."""
    ini_cost = state.cost()
    snap = state.snapshot()
    temp_max = _MAX_INT
    temp_min = 0
    temp = 0
    for _step in range(64):
        temp = (temp_max - temp_min) // 2 + temp_min
        state.restore(snap)
        cost = ini_cost
        acc = 0.0
        cnt = 0
        for _r in range(moves):
            mv = state.draw_move(rng)
            delta = state.apply(mv)
            if delta <= temp:
                acc += delta
                cost += delta
                cnt += 1
            else:
                state.apply(state.inverse(mv))
        avg = acc / cnt if cnt else float("inf")
        if avg < 0:
            temp_min = temp
        else:
            temp_max = temp
        if ini_cost and abs(avg / ini_cost) < 1e-9:
            break
        if temp_max - temp_min <= 1:
            break
    state.restore(snap)
    return float(max(temp, 0))


def sa_refine(ordering_p, ordering_n, netlist, leg_widths, iterations=None,
              quality=DEFAULT_QUALITY, init_moves=None, seed=None,
              check=True, cage=False):
    """Refine the seed orderings with Threshold Accept; returns
    (ordering_p, ordering_n, cost_breakdown).

    Pure and deterministic: same inputs -> identical output orderings
    (invariant 9).  ``iterations`` caps the TA loop (the same-cost rule
    usually terminates earlier); ``quality`` sets
    ``num_repetitions = problemSize * quality`` (thresholdaccept.h:94,
    ASTRAN uses 150 -- see the module docstring for the Python-budget
    reduction).  ``init_moves`` caps each bisection step of the initial
    threshold search (ASTRAN: 5000).  ``check`` asserts the incremental
    cost against a full recompute at every iteration boundary -- a
    mismatch is an engine bug and raises.

    ``cage=True`` adds the gate-cage term (CAGE_WEIGHT, :func:`_SAState`)
    to the search's cost: the TA acceptance then sees a caged move as
    ~10^7 worse, so past the initial threshold the search never wanders
    into a power-caged arrangement, and the best-snapshot prefers
    cage-free states over cheaper caged ones.  The default False keeps
    the pure ASTRAN cost byte-for-byte (the pure-cost research path and
    its pinned phase-1 specimens; the production chain opts in).
    """
    state = _SAState(ordering_p, ordering_n, leg_widths,
                     netlist=netlist if cage else None)
    rng = random.Random(seed if seed is not None else cell_seed(netlist))
    problem_size = len(state.rows[0]) * len(state.rows[1])
    num_reps = max(1, int(problem_size * quality))
    if iterations is None:
        iterations = DEFAULT_ITERATIONS
    if init_moves is None:
        init_moves = min(2000, max(500, 4 * problem_size))

    threshold = _find_initial_threshold(state, rng, init_moves)
    cost = state.cost()
    if cost == 0:
        op, on = state.orderings()
        return op, on, state.breakdown()
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
    return op, on, state.breakdown()


# --------------------------------------------------------------------------
# routability-aware selection (doc section 2.2 "Composition": ASTRAN's
# speculate loop, autocell2.cpp:187-216 -- place -> trial route -> keep best)
# --------------------------------------------------------------------------

#: default speculate-pool size and trial budget.  K = 10 covers the SA
#: best, all six row mirror/die-mirror variants and the euler seed with
#: its flip/die-mirror variants (the classes the stage-3 plateau
#: analysis identified); per-block flip combinations fill any further
#: slots.  The trial budget is a fraction of route_grid.MAX_ATTEMPTS
#: (8000): the negotiation either separates the nets early (the proven
#: NAND2X1 mirror closure routes at attempt 1) or its plateau conflict
#: count already ranks candidates correctly (measured on
#: ctrl/COMPLEX0: the trial ranking picks the same class the full
#: 8000-attempt sweep does).
DEFAULT_CANDIDATES = 10
DEFAULT_TRIAL_ATTEMPTS = 300

#: 2**(nP + nN) per-block flip combinations are enumerated only below
#: this cap; bigger rows fall back to the row-level variants.
_MAX_FLIP_COMBOS = 1024

#: trial score of a candidate the router cannot even BUILD (misaligned
#: gate order, terminal clash) -- worse than any negotiable plateau.
_UNROUTABLE = 1 << 30

# --------------------------------------------------------------------------
# decomposition-variant candidate classes (the upstream lever)
# --------------------------------------------------------------------------
# The conflict evidence (flow/_stage3_check/bench_int3, ctrl/COMPLEX0)
# shows the routing plateau surviving EVERY ordering/mirror of one
# decomposition -- agent T exhausted all 64 flip combinations of both
# base orderings at full budget.  The lever left is the decomposition
# itself: netlist_ext.build_bigcell_blocks' ``variant`` knob builds
# alternative TOTAL decompositions (split chains/groups, re-phased
# parallel groups, unbounded tree coupling), whose ordering spaces
# contain arrangements the default block structure cannot express (a
# split pair's re-exposed internal net, a re-phased group's buried rail
# edge).  These join the speculate pool as extra candidate classes,
# ranked by the SAME trial route as the mirror classes.

#: variants joined to the speculate pool when the fixed classes all fail
#: their trials ("default" is the main pool itself, so it is not listed;
#: the order here is the pool priority)
DECOMPOSITION_VARIANTS = ("base", "parallel_phase", "split_parallel",
                          "split_series", "singles", "max_merge")

#: per-variant Threshold-Accept budget.  The full DEFAULT_ITERATIONS x
#: DEFAULT_QUALITY budget is the MAIN path's; a variant only needs its
#: best ordering locally sane for the fallback (conflicts, cost) rank --
#: the variant's VALUE is its different block structure, not a tighter
#: cost optimum (measured: the ctrl 8T cell's variant SA plateaus at the
#: default's own ordering in a fraction of the main budget).  The
#: iteration count additionally shrinks with the problem size so one
#: variant's refine stays within the size-aware move budget of
#: _variant_sa_moves -- measured on adder/COMPLEX10 (36T, 18x18 blocks)
#: the unshrunk budget alone cost ~30 s per variant.
VARIANT_SA_ITERATIONS = 12

#: move budget for ONE variant's Threshold-Accept refine on a SMALL cell
#: (the initial-threshold search's own bounded pass comes on top); big
#: cells scale it down, see _VARIANT_SA_FULL_PROBLEM / _variant_sa_moves
VARIANT_SA_MOVES = 6000

#: problem-size cap (P blocks x N blocks of the variant's seed) beyond
#: which the variant skips its Threshold-Accept refine and nominates the
#: euler seed directly: the variant's value is its different STRUCTURE,
#: and sa_refine's initial-threshold bisection alone (64 x init_moves)
#: costs ~10 s per call once the product nears 300 (measured on
#: adder/COMPLEX10: 18x18 blocks).  Big cells still get every variant's
#: euler-seed ordering as a candidate, at euler's own bounded cost.
_VARIANT_SA_PROBLEM_CAP = 120

#: problem size (P blocks x N blocks of a variant's seed) up to which a
#: variant keeps the FULL per-variant budgets (VARIANT_SA_MOVES,
#: VARIANT_SA_ITERATIONS, _ALIGN_PAIR_CAP): any cell with at most ~12
#: blocks total has a worst-case split of 6 x 6 = 36, so every small
#: cell keeps today's constants (the pinned ctrl/COMPLEX0
#: var:singles-align4 win among them).  Above it the per-variant
#: budgets shrink linearly with the size -- the doc's windowed
#: philosophy: on big cells a variant is a cheap probe of a different
#: STRUCTURE, not a full refinement -- reaching the euler-only floor at
#: _VARIANT_SA_PROBLEM_CAP (measured on the round-5 heavy cells: the
#: per-variant refine is the whole variant-build cost, 1-1.4 s each on
#: the 22-30T cells; builds/seeds/euler/alignment enumeration are
#: ~0.05 s).
_VARIANT_SA_FULL_PROBLEM = 36

#: alignment-nomination search caps.  Per variant, EVERY per-row block
#: ordering (permutations x flips) is enumerated up to _ALIGN_ROW_CAP
#: rows per side and _ALIGN_PAIR_CAP pair scorings -- the routability
#: signal (aligned P/N terminal columns, corridor count) is one SA cost
#: cannot see, and the plateau cells are small enough to search
#: exhaustively; bigger rows fall back to the euler+SA classes only.
_ALIGN_ROW_CAP = 4096
_ALIGN_PAIR_CAP = 200000

#: exact SA cost is computed only for the top cheap-ranked alignment
#: pairs (the final nomination rank is alignment first, then corridors,
#: then SA cost)
_ALIGN_COST_POOL = 64

#: alignment nominees added per variant
ALIGN_CANDIDATES = 4


def ordering_signature(ordering_p, ordering_n):
    """Canonical dedupe key for a candidate: per-row block content.

    Blocks are compared by (kind, members as (device, left, right)) --
    never by identity (mirror_block builds new objects) and never by
    hash() (invariant 9).
    """

    def row_key(row):
        return tuple(
            (b.kind,) + tuple((m.device.name, m.left_net, m.right_net)
                              for m in b.members)
            for b in row)

    return (row_key(ordering_p), row_key(ordering_n))


def _row_flipped(row):
    """Every block mirrored IN PLACE, sequence order kept (the
    orientation the mirrored-demo closure evidence used)."""
    return [mirror_block(b) for b in row]


def _row_die_mirror(row):
    """The row's left-right die image: sequence reversed AND every block
    flipped.  Same breaks/width as the identity (adjacency pairs are
    preserved), different access sides."""
    return [mirror_block(b) for b in reversed(row)]


# --------------------------------------------------------------------------
# decomposition-variant candidate classes
# --------------------------------------------------------------------------

def _row_terminals(ordering, leg_widths):
    """({col: gate nets}, {col: signal edge nets}, breaks, width_cols)
    for one row ordering -- the cheap routability picture the alignment
    nomination scores (mirrors geometry.place_row's walk: break columns
    where the facing end nets differ)."""
    gates = {}
    edges = {}
    col = 0
    breaks = 0
    prev_right = None
    for block in ordering:
        if prev_right is not None \
                and block.members[0].left_net != prev_right:
            col += BREAK_GAP_COLS
            breaks += 1
        for member in block.members:
            legs, cols = leg_widths[member.device.name]
            w = legs * cols
            gates.setdefault(col, set()).add(member.device.gate)
            if member.left_net not in POWER_NETS:
                edges.setdefault(col, set()).add(member.left_net)
            col += w
            if member.right_net not in POWER_NETS:
                edges.setdefault(col, set()).add(member.right_net)
        prev_right = block.members[-1].right_net
    return gates, edges, breaks, col


def _row_orderings(blocks):
    """Every ordering of one row's blocks over all flip combinations
    (deterministic: permutations in index order, flip bits lexicographic)."""
    out = []
    for perm in itertools.permutations(range(len(blocks))):
        for flips in itertools.product((0, 1), repeat=len(blocks)):
            out.append([mirror_block(blocks[i]) if f else blocks[i]
                        for i, f in zip(perm, flips)])
    return out


def alignment_candidates(p_blocks, n_blocks, leg_widths,
                         limit=ALIGN_CANDIDATES, pair_cap=None,
                         netlist=None):
    """Routability-nominated orderings for one variant's decomposition.

    SA's cost cannot see routability (the proven NAND2X1/ctrl-plateau
    mechanism), so the variant's aligned-terminal orderings are nominated
    directly: every per-row ordering is enumerated (bounded by
    _ALIGN_ROW_CAP rows per side and ``pair_cap`` pair scorings --
    beyond them the nomination is skipped for that variant; the caller
    passes the size-aware cap of :func:`_alignment_pair_cap`, default
    the flat _ALIGN_PAIR_CAP) and pairs rank by

        1. aligned gate columns   (a merged P/N poly crossing is free),
        2. aligned signal diffusion edges (a shared M1 stub),
        3. diffusion breaks DESC  (a break column is a routing corridor),
        4. SA cost ASC            (only for the _ALIGN_COST_POOL
                                   cheap-ranked finalists, so the exact
                                   cost never runs on the full pair
                                   space),
        5. gate-cage ASC          (with ``netlist``: the static
                                   :func:`gate_cage_penalty` census -- a
                                   finalist whose gate columns dodge the
                                   power-access columns beats an equal
                                   alignment/cost finalist that cages
                                   one; pinned to the TAIL of the rank
                                   because the ctrl/COMPLEX0 M2-fingerprint
                                   closure rides a census-caged nominee),
        6. crossing-contest ASC   (with ``netlist``: the static
                                   :func:`crossing_cage_penalty` census --
                                   the placement-axis lever of AUDIT 5.49:
                                   a finalist whose demanded wire
                                   crossings dodge the striped columns
                                   beats an equal finalist whose
                                   crossings land inside the power
                                   bands; ranked after the cage for the
                                   same tail-pin reason),
        7. lexicographic ordering signature (deterministic tie-break).

    Returns up to ``limit`` distinct (ordering_p, ordering_n) pairs.
    Pure and deterministic (invariant 9); no router is invoked.
    """
    if not p_blocks or not n_blocks:
        return []
    if (pair_cap is None):
        pair_cap = _ALIGN_PAIR_CAP
    n_p_rows = math.factorial(len(p_blocks)) * 2 ** len(p_blocks)
    n_n_rows = math.factorial(len(n_blocks)) * 2 ** len(n_blocks)
    if (n_p_rows > _ALIGN_ROW_CAP or n_n_rows > _ALIGN_ROW_CAP
            or n_p_rows * n_n_rows > pair_cap):
        return []
    p_rows = _row_orderings(p_blocks)
    n_rows = _row_orderings(n_blocks)
    p_maps = [(_row_terminals(r, leg_widths),
               ordering_signature(r, [])) for r in p_rows]
    n_maps = [(_row_terminals(r, leg_widths),
               ordering_signature([], r)) for r in n_rows]
    # per-row cage views, built once for the finalist stage (the census
    # then costs two view merges per FINALIST, not per pair -- the pair
    # space itself is ranked alignment-only, exactly as before)
    exposed = None
    if netlist is not None:
        exposed = exposed_net_set(netlist)
    p_views = [_cage_row_view([_entry(b, False, leg_widths)
                               for b in r], True, exposed)
               for r in p_rows] if exposed is not None else None
    n_views = [_cage_row_view([_entry(b, False, leg_widths)
                               for b in r], False, exposed)
               for r in n_rows] if exposed is not None else None
    scored = []
    for (gp, ep, bp, wp), sp in p_maps:
        for (gn, en, bn, wn), sn in n_maps:
            cols = set(gp) | set(gn)
            ga = sum(1 for c in cols if gp.get(c, set()) & gn.get(c, set()))
            da = sum(1 for c in cols if ep.get(c, set()) & en.get(c, set()))
            scored.append((ga, da, bp + bn, wp + wn, sp, sn))
    # stable two-stage rank: signature ascending, then the numeric key
    # descending -- ties keep the lexicographically smaller signature
    scored.sort(key=lambda t: (t[4], t[5]))
    scored.sort(key=lambda t: (t[0], t[1], t[2], t[3]), reverse=True)
    finalists = scored[:_ALIGN_COST_POOL]
    # exact SA cost for the finalists, final rank (alignment, corridors,
    # cost, cage, signature), truncate
    p_by_sig = {sp: r for (_m, sp), r in zip(p_maps, p_rows)}
    n_by_sig = {sn: r for (_m, sn), r in zip(n_maps, n_rows)}
    p_view_by_sig = {sp: v for v, (_m, sp) in zip(p_views, p_maps)} \
        if p_views is not None else None
    n_view_by_sig = {sn: v for v, (_m, sn) in zip(n_views, n_maps)} \
        if n_views is not None else None
    ranked = []
    for ga, da, br, wp, sp, sn in finalists:
        op = p_by_sig[sp]
        on = n_by_sig[sn]
        cost = _SAState(op, on, leg_widths).total
        cage = _cage_from_views(p_view_by_sig[sp], n_view_by_sig[sn],
                                exposed)[0] \
            if p_view_by_sig is not None else 0
        crossing = _crossing_from_views(p_view_by_sig[sp],
                                        n_view_by_sig[sn],
                                        exposed)[0] \
            if p_view_by_sig is not None else 0
        ranked.append(((ga, da, br, cost, cage, crossing, sp, sn), op, on))
    # stable two-stage final rank: (cost, cage, crossing, signature)
    # ascending, then the alignment/corridor key descending -- ties keep
    # the cheaper, cage-free, crossing-free, lexicographically smaller
    # ordering
    ranked.sort(key=lambda t: (t[0][3], t[0][4], t[0][5], t[0][6], t[0][7]))
    ranked.sort(key=lambda t: (t[0][0], t[0][1], t[0][2]), reverse=True)
    out = []
    seen = set()
    for _key, op, on in ranked:
        sig = ordering_signature(op, on)
        if sig in seen:
            continue
        seen.add(sig)
        out.append((op, on))
        if len(out) >= limit:
            break
    return out


def _variant_sa_moves(problem_size):
    """Per-variant TA move budget at ``problem_size`` (pure, invariant 9).

    The full VARIANT_SA_MOVES while the cell is small (see
    _VARIANT_SA_FULL_PROBLEM), shrinking linearly to 0 at
    _VARIANT_SA_PROBLEM_CAP, where the refine is skipped outright."""

    if (problem_size <= _VARIANT_SA_FULL_PROBLEM):
        return VARIANT_SA_MOVES
    span = _VARIANT_SA_PROBLEM_CAP - _VARIANT_SA_FULL_PROBLEM
    frac = (_VARIANT_SA_PROBLEM_CAP - problem_size) / float(span)
    return max(0, int(VARIANT_SA_MOVES * frac))


def _variant_sa_iterations(problem_size, cap=VARIANT_SA_ITERATIONS):
    """Deterministic per-variant TA iteration count: the full ``cap``
    while the cell is small, shrinking so one refine's move count
    (problem_size x DEFAULT_QUALITY per iteration) stays within the
    size-aware move budget of :func:`_variant_sa_moves`.  Pure function
    (invariant 9)."""
    reps = int(problem_size * DEFAULT_QUALITY)
    if reps <= 0:
        return cap
    return max(1, min(int(cap), _variant_sa_moves(problem_size) // reps))


def _alignment_pair_cap(problem_size):
    """Size-aware cap on the alignment nomination's scored pairs.

    The full _ALIGN_PAIR_CAP while the cell is small (at most ~12
    blocks -- see _VARIANT_SA_FULL_PROBLEM), shrinking linearly to 0 at
    _VARIANT_SA_PROBLEM_CAP: on big cells the alignment nominees are a
    cheap probe too (the per-row enumeration cap already skips rows
    beyond 5 blocks, so this bounds the small-row variants of mid-size
    cells).  Pure function (invariant 9)."""
    if (problem_size <= _VARIANT_SA_FULL_PROBLEM):
        return _ALIGN_PAIR_CAP
    span = _VARIANT_SA_PROBLEM_CAP - _VARIANT_SA_FULL_PROBLEM
    frac = (_VARIANT_SA_PROBLEM_CAP - problem_size) / float(span)
    return max(0, int(_ALIGN_PAIR_CAP * frac))


def decomposition_variant_classes(netlist, leg_widths,
                                  variant_names=DECOMPOSITION_VARIANTS,
                                  sa_iterations=VARIANT_SA_ITERATIONS,
                                  align_limit=ALIGN_CANDIDATES,
                                  cage=False, basin="steered"):
    """The per-variant candidate classes for the speculate pool.

    For every decomposition variant (netlist_ext.BLOCK_VARIANTS minus
    "default", which IS the main pool): build blocks -> row seeds ->
    euler -> a budget-bounded Threshold-Accept refine (the same
    content-hash seed discipline as the main path; the move budget and
    the alignment pair cap are size-aware -- full on small cells, i.e.
    at most ~12 blocks, shrinking linearly with the P x N problem size
    to the euler-only / no-nominee floor at _VARIANT_SA_PROBLEM_CAP,
    see _variant_sa_moves / _alignment_pair_cap) and nominate

        1. the variant's SA best ("var:<name>"; above the
           _VARIANT_SA_PROBLEM_CAP problem size the euler seed stands
           in -- the structure is the candidate),
        2. its both-rows flip / die-mirror (the proven closure classes),
        3. up to ``align_limit`` alignment nominees
           ("var:<name>-align<j>") from :func:`alignment_candidates`.

    ``basin`` picks the refine's cost: "steered" refines with the
    ``cage`` flag (the production chain's cage term when True), "legacy"
    always refines with the pure ASTRAN cost (``cage=False``) and
    suffixes every kind with "-legacy" -- the dual-basin twins of a
    steered chain (see :func:`sa_refine_routable`).  On cells above
    _VARIANT_SA_PROBLEM_CAP both basins nominate the same euler seed, so
    the legacy twins dedupe away at zero cost.

    Variants whose block shape equals the default decomposition's are
    skipped outright (their whole ordering space is the main pool's --
    the classes would only dedupe away).  Deduped internally by
    :func:`ordering_signature` (first occurrence wins); the caller
    dedupes against the main pool.  Pure and deterministic.
    """
    from bigcell_engine.netlist_ext import (_block_shape,
                                            build_bigcell_blocks,
                                            row_seeds)
    from bigcell_engine.place_euler import euler_orderings
    if basin == "legacy":
        cage = False
    elif basin != "steered":
        raise ValueError("unknown basin %r" % (basin,))
    suffix = "" if basin == "steered" else "-legacy"
    default_shape = _block_shape(build_bigcell_blocks(netlist))
    out = []
    seen = set()
    for name in variant_names:
        blocks = build_bigcell_blocks(netlist, variant=name)
        if _block_shape(blocks) == default_shape:
            continue
        p_blocks = [b for b in blocks if b.first.is_p]
        n_blocks = [b for b in blocks if not b.first.is_p]
        seeds = row_seeds(blocks, leg_widths)
        eop, eon = euler_orderings(seeds, leg_widths)
        problem_size = len(seeds[P_ROW]) * len(seeds[N_ROW])
        if problem_size <= _VARIANT_SA_PROBLEM_CAP:
            bp, bn, _bd = sa_refine(eop, eon, netlist, leg_widths,
                                    iterations=_variant_sa_iterations(
                                        problem_size, cap=sa_iterations),
                                    cage=cage)
        else:
            bp, bn = eop, eon
        classes = [("var:%s%s" % (name, suffix), bp, bn),
                   ("var:%s%s-flip-both" % (name, suffix),
                    _row_flipped(bp), _row_flipped(bn)),
                   ("var:%s%s-die-both" % (name, suffix),
                    _row_die_mirror(bp), _row_die_mirror(bn))]
        for j, (op, on) in enumerate(
                alignment_candidates(p_blocks, n_blocks, leg_widths,
                                     limit=align_limit,
                                     pair_cap=_alignment_pair_cap(
                                         problem_size),
                                     netlist=netlist), start=1):
            classes.append(("var:%s%s-align%d" % (name, suffix, j),
                            op, on))
        for kind, op, on in classes:
            sig = ordering_signature(op, on)
            if sig in seen:
                continue
            seen.add(sig)
            out.append((kind, op, on))
    return out


#: classes added to the fixed pool for the legacy basin (best + its two
#: proven both-rows mirrors) when a steered chain runs the dual refine
LEGACY_BASIN_CLASSES = 3


def generate_candidates(best_p, best_n, seed_p, seed_n, leg_widths,
                        candidate_count=DEFAULT_CANDIDATES,
                        extra_classes=None, netlist=None,
                        legacy_best=None):
    """The deterministic top-K candidate pool (speculate stage, step 1).

    ``best_p``/``best_n`` are the SA cost-best orderings;
    ``seed_p``/``seed_n`` the pre-SA seed (``sa_refine_routable`` passes
    the euler output, an alternative block ORDER the SA search may have
    moved away from).  Pool priority order:

    1. the SA best (the pure-cost optimum -- keeps already-closing
       cells on their proven orientation);
    2. its both-rows flip / die-mirror (the proven NAND2X1 closure
       class);
    3. single-row flip / die-mirror variants;
    4. the seed ordering and its flip / die-mirror variants;
    5. with ``legacy_best`` (the ``cage=False`` refine's best of a
       dual-basin chain, see :func:`sa_refine_routable`): the
       legacy-basin specimen ``best-legacy`` and its proven both-rows
       flip / die-mirror -- ranked AFTER the ten steered fixed classes
       and BEFORE the flip combinations, so a steered-head closure is
       unaffected and a legacy-basin closure gets its candidate back
       (bench_int5 -> bench_int6 restoration);
    6. further per-block flip combinations of the SA best, ranked by
       SA cost then lexicographic bit order (only below the fixed
       classes when ``candidate_count`` allows, and only when
       2**(nP+nN) <= _MAX_FLIP_COMBOS).  With ``netlist`` given the
       cost is the cage-aware total (:func:`_SAState`), so the
       combinations sort cage-free-first -- the flip space is where a
       cage-free orientation of the SA basin most often lives;
    7. ``extra_classes`` -- pre-built (kind, ordering_p, ordering_n)
       entries appended after the flip combinations and deduped like
       every class (the decomposition-variant classes of
       :func:`decomposition_variant_classes`; the ``candidate_count``
       cap applies to the FINAL pool, so a caller passing extras must
       raise it accordingly).

    Deduped by :func:`ordering_signature` (first occurrence wins) and
    truncated to ``candidate_count``.  Pure and deterministic.
    """
    best_p, best_n = list(best_p), list(best_n)
    seed_p, seed_n = list(seed_p), list(seed_n)
    pool = [
        ("best", best_p, best_n),
        ("flip-both", _row_flipped(best_p), _row_flipped(best_n)),
        ("die-both", _row_die_mirror(best_p), _row_die_mirror(best_n)),
        ("flip-P", _row_flipped(best_p), best_n),
        ("flip-N", best_p, _row_flipped(best_n)),
        ("die-P", _row_die_mirror(best_p), best_n),
        ("die-N", best_p, _row_die_mirror(best_n)),
        ("seed", seed_p, seed_n),
        ("seed-flip-both", _row_flipped(seed_p), _row_flipped(seed_n)),
        ("seed-die-both", _row_die_mirror(seed_p), _row_die_mirror(seed_n)),
    ]
    if legacy_best is not None:
        leg_p, leg_n = list(legacy_best[0]), list(legacy_best[1])
        pool.extend([
            ("best-legacy", leg_p, leg_n),
            ("best-legacy-flip-both",
             _row_flipped(leg_p), _row_flipped(leg_n)),
            ("best-legacy-die-both",
             _row_die_mirror(leg_p), _row_die_mirror(leg_n)),
        ])
    n_blocks = len(best_p) + len(best_n)
    if 2 ** n_blocks <= _MAX_FLIP_COMBOS:
        combos = []
        for bits in _iter_flip_bits(len(best_p), len(best_n)):
            op = [b if not bit else mirror_block(b)
                  for b, bit in zip(best_p, bits[:len(best_p)])]
            on = [b if not bit else mirror_block(b)
                  for b, bit in zip(best_n, bits[len(best_p):])]
            combos.append((_SAState(op, on, leg_widths,
                                    netlist=netlist).total, bits, op, on))
        combos.sort(key=lambda t: (t[0], t[1]))
        pool.extend(("flip%s" % ("".join(map(str, t[1])),), t[2], t[3])
                    for t in combos)
    if extra_classes:
        pool.extend(extra_classes)
    seen = set()
    out = []
    for kind, op, on in pool:
        sig = ordering_signature(op, on)
        if sig in seen:
            continue
        seen.add(sig)
        out.append((kind, op, on))
        if len(out) >= candidate_count:
            break
    return out


def _iter_flip_bits(n_p, n_n):
    """Flip-bit tuples, P row's blocks first; deterministic order."""
    from itertools import product
    return product((0, 1), repeat=n_p + n_n)


def _trial_conflicts(result):
    """Trial score of a route result: 0 when FEASIBLE, otherwise the
    plateau's best conflict count parsed from the honest fail note; a
    build-time failure (misaligned gate order, terminal clash) has no
    count and scores _UNROUTABLE."""
    if getattr(result, "ok", False):
        return 0
    note = getattr(result, "fail_note", None) or ""
    m = re.search(r"best (\d+) conflicts", note)
    return int(m.group(1)) if m else _UNROUTABLE


def _default_trial_router():
    """The production trial router (lazy import keeps place_sa
    import-light and cycle-free)."""
    from bigcell_engine.route_grid import route_cell
    return route_cell


def _router_accepts_blocks(router):
    """Whether ``router`` accepts the trial contract's optional
    ``blocks`` keyword (the TRUE-VIEW trial, see :func:`select_orderings`).

    True when the callable declares a ``blocks`` parameter (the real
    ``route_grid.route_cell`` since a7b23cc) or a ``**kwargs`` catch-all
    (a permissive stub); False otherwise -- today's injected fakes
    (``router(netlist, placements, width, leg_widths, max_attempts)``)
    keep their exact blocks-less call, so every existing fake-router
    test contract survives unchanged.  Pure function of the router
    object (invariant 9): the probe is ``inspect.signature``, probed
    once per selection and reused for every candidate."""
    try:
        params = inspect.signature(router).parameters.values()
    except (TypeError, ValueError):    # no introspectable signature
        return False
    for p in params:
        if p.kind == inspect.Parameter.VAR_KEYWORD:
            return True
        if p.name == "blocks" and p.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY):
            return True
    return False


def select_orderings(best_p, best_n, seed_p, seed_n, netlist, leg_widths,
                     candidate_count=DEFAULT_CANDIDATES,
                     trial_attempts=DEFAULT_TRIAL_ATTEMPTS,
                     trial_router=None, variant_classes=False,
                     cage=False, legacy_best=None):
    """Speculate stage (doc section 2.2 "Composition"): score the
    candidate pool by a fast trial route and pick the winner.

    Returns ``(ordering_p, ordering_n, report)``.  Ranking policy (the
    gate-cage lever, AUDIT 5.46, extended by the crossing lever, AUDIT
    5.49):

    - every candidate carries its :func:`gate_cage_penalty` count in the
      report entry (``cage``) -- the static census of the placement-side
      wall (gate contacts hard-blocked under power metal) -- and its
      :func:`crossing_cage_penalty` count (``crossing``) -- the
      demanded wire crossings walled inside the power bands (the
      XOR/MUX/TBUF/LATCH class's binding family, one level deeper than
      the contact census);
    - a candidate that routes FEASIBLE **and** cages no gate wins
      immediately, in pool priority order (the SA-best candidate is
      tried first, so a cell whose cost-optimal orientation already
      routes cage-free is unaffected -- INVX1/NAND2 stay on the
      pure-cost path);
    - when the first FEASIBLE candidate cages gates, the scan continues:
      a FEASIBLE candidate that does NOT cage loses to nothing -- a
      candidate that cages a gate where another doesn't loses even with
      better legacy cost -- and among equal-cage FEASIBLE candidates the
      earlier pool entry wins (the pool priority survives within a cage
      tier);
    - when nothing routes within the trial budget, the candidate with
      the best floor key is returned.  Candidates with a real conflict
      count (a negotiation plateau -- the router's honest floor) keep
      today's (conflicts, SA cost, pool index) rank verbatim.
      Candidates with NO floor (_UNROUTABLE: the router could not even
      negotiate -- the build-time structural-failure class the census
      diagnoses) keep today's (cage, SA cost, pool index) rank
      verbatim.  A real floor always beats _UNROUTABLE.  The caller's
      full-budget route then starts from the best-known orientation.
      The crossing census therefore acts in the selection as EVIDENCE
      (the report field) and through the FEASIBLE-but-caged tier key
      and the alignment finalists -- the fallback ranks stay
      byte-compatible with the pinned contracts (equal-(floor, cost)
      ties resolve by pool index exactly as before).

    ``variant_classes`` extends the pool with the decomposition-variant
    classes (:func:`decomposition_variant_classes`) when the fixed
    classes all fail their trials -- the conflict evidence shows
    plateaus that survive every ordering of ONE decomposition, so the
    alternative decompositions join as a lazy second phase (a cell that
    closes in the fixed classes never pays for them).  Variants rank
    exactly like the mirror classes.  ``cage`` steers the variant
    refines' SA cost (see :func:`sa_refine`).  ``legacy_best`` (the
    ``cage=False`` refine's best of a dual-basin chain) joins the
    legacy-basin specimen to the fixed pool (``best-legacy`` and its
    proven both-rows mirrors, after the steered fixed classes) and, on
    a steered chain whose steered classes leave no cage-free FEASIBLE
    winner, runs the
    lazy third phase: the ``cage=False``-refined variant twins
    (``var:<name>-legacy`` ...).  The selection policy is basin-blind:
    a legacy-basin FEASIBLE beats every steered plateau, and the cage
    rank only ever breaks ties BETWEEN feasible candidates.  Candidates
    are deduped
    by :func:`ordering_signature` (content-only: two decompositions
    producing the same ordering route identically, so one trial
    covers both; the report's ``kind`` carries the first occurrence's
    provenance).

    ``trial_router`` defaults to ``route_grid.route_cell`` and is
    called as ``router(netlist, placements, width_cols, leg_widths,
    max_attempts=trial_attempts, blocks=<candidate's block view>)`` --
    the TRUE-VIEW trial: each candidate is measured against its OWN
    orientation-aware die view (``list(ordering_p) + list(ordering_n)``,
    exactly the ``blocks`` the production route and verify consume for
    the winner), so the trial's verdict is the same view the
    full-budget route sees.  The blocks-less legacy trial ranked a
    tree-arrangement candidate by a die view the real route never
    recreates (the multiplier/COMPLEX4 evidence: the closers
    ``var:parallel_phase-flip-both``/``-align3`` trial below
    ``var:parallel_phase-die-both`` blocks-less yet route CLEAN on
    their own view, while die-both's own view is full-budget-floor-4
    with a CP-SAT-proven unwirable window).  On every placement the
    pristine reconstruction explains, ``blocks`` changes nothing (the
    router's die view is identical either way), so non-tree candidates
    keep their byte-identical trial.  A router that does not accept the
    keyword (today's injected fakes, probed once via
    :func:`_router_accepts_blocks`) keeps the exact blocks-less legacy
    call ``router(netlist, placements, width_cols, leg_widths,
    max_attempts=trial_attempts)``.  A router exception is caught and
    scored _UNROUTABLE (recorded in the report) so one bad candidate
    cannot kill the placement.

    ``report`` (plain data, no wall-clock -- invariant 9):
    ``selected``/``kind``/``feasible``/``conflicts``/``cage`` of the
    winner plus per-trialed-candidate entries; ``trial_view`` records
    which trial contract measured the pool ("blocks" = the true view,
    "blocks-less" = a router without the parameter).  Pure and
    deterministic.
    """
    router = trial_router if trial_router is not None \
        else _default_trial_router()
    blocks_aware = _router_accepts_blocks(router)
    if leg_widths is None:
        from bigcell_engine.geometry import default_leg_widths
        leg_widths = default_leg_widths(
            [m.device for row in (best_p, best_n, seed_p, seed_n)
             for b in row for m in b.members])
    pool = generate_candidates(best_p, best_n, seed_p, seed_n, leg_widths,
                               candidate_count, netlist=netlist,
                               legacy_best=legacy_best)
    from bigcell_engine.geometry import layout_cell
    entries = []
    fallback = None               # (conflicts, cage, cost, index) -> entry
    feasible = None               # (cage, index) -> entry, FEASIBLE tier

    def _trial(idx):
        """Trial-route pool[idx]; append the report entry; return it."""
        kind, op, on = pool[idx]
        placements, width = layout_cell(op, on, leg_widths)
        # the candidate's OWN die view: the orientation-aware block view
        # the production route would consume for exactly this placement
        # (engine meta["blocks"] is list(ordering_p) + list(ordering_n)
        # of the winner -- here every candidate gets the same courtesy).
        # Deriving it is O(#blocks) (the blocks exist; nothing is
        # rebuilt), and the router consumes it only where the pristine
        # reconstruction fails (the tree-arrangement fallback), so
        # non-tree candidates keep their byte-identical blocks-less
        # trial.  No wall-clock, no hash() (invariant 9).
        blocks_view = list(op) + list(on)
        try:
            if blocks_aware:
                result = router(netlist, placements, width, leg_widths,
                                max_attempts=trial_attempts,
                                blocks=blocks_view)
            else:
                result = router(netlist, placements, width, leg_widths,
                                max_attempts=trial_attempts)
        except Exception as exc:                   # noqa: BLE001
            result = None
            note = "trial router raised %s: %s" % (
                type(exc).__name__, exc)
        else:
            note = getattr(result, "fail_note", None)
        conflicts = _trial_conflicts(result) if result is not None \
            else _UNROUTABLE
        cost = _SAState(op, on, leg_widths).total
        entry = {"index": idx, "kind": kind, "cost": cost,
                 "width_cols": width, "conflicts": conflicts,
                 "cage": gate_cage_penalty(op, on, netlist, leg_widths)[0],
                 "crossing": crossing_cage_penalty(
                     op, on, netlist, leg_widths)[0],
                 "feasible": conflicts == 0,
                 "attempts": getattr(result, "attempts_used", None),
                 "note": note}
        entries.append(entry)
        return entry

    def _keep(entry, op, on):
        """Short-circuit on FEASIBLE cage-free; track the tier winners."""
        nonlocal fallback, feasible
        if entry["conflicts"] == 0:
            key = (entry["cage"], entry["crossing"], entry["index"])
            if entry["cage"] == 0:
                return op, on, {
                    "selected": entry["index"], "kind": entry["kind"],
                    "feasible": True, "conflicts": 0, "cage": 0,
                    "crossing": entry["crossing"],
                    "trial_attempts": trial_attempts,
                    "trial_view": "blocks" if blocks_aware
                    else "blocks-less",
                    "candidate_count": len(pool), "candidates": entries,
                }
            if feasible is None or key < (feasible["cage"],
                                          feasible["crossing"],
                                          feasible["index"]):
                feasible = entry
            return None
        if entry["conflicts"] == _UNROUTABLE:
            # no measured floor: today's (cage, cost, index) rank
            # verbatim
            key = (1, entry["cage"], entry["cost"], entry["index"])
        else:
            # a real negotiation plateau: today's (conflicts, cost,
            # index) rank verbatim -- the router's honest floor leads
            key = (0, entry["conflicts"], entry["cost"], entry["index"])
        if fallback is None or key < fallback[0]:
            fallback = (key, entry)
        return None

    def _won(entry, op, on):
        """The winner report for a tracked tier entry."""
        return op, on, {
            "selected": entry["index"], "kind": entry["kind"],
            "feasible": entry["conflicts"] == 0,
            "conflicts": entry["conflicts"], "cage": entry["cage"],
            "crossing": entry["crossing"],
            "trial_attempts": trial_attempts,
            "trial_view": "blocks" if blocks_aware else "blocks-less",
            "candidate_count": len(pool), "candidates": entries,
        }

    for idx in range(len(pool)):
        entry = _trial(idx)
        won = _keep(entry, pool[idx][1], pool[idx][2])
        if won is not None:
            return won
    if variant_classes:
        # phase 2: the decomposition-variant classes, deduped against
        # everything already trialed
        extra = decomposition_variant_classes(netlist, leg_widths,
                                              cage=cage)
        known = {ordering_signature(op, on) for _k, op, on in pool}
        for kind, op, on in extra:
            if ordering_signature(op, on) in known:
                continue
            known.add(ordering_signature(op, on))
            pool.append((kind, op, on))
        for idx in range(len(entries), len(pool)):
            entry = _trial(idx)
            won = _keep(entry, pool[idx][1], pool[idx][2])
            if won is not None:
                return won
        # phase 3 (dual-basin chains only): the legacy-refined variant
        # twins.  Fired only when the steered classes left no cage-free
        # FEASIBLE winner -- every cell closing in phases 1/2 keeps its
        # exact pool, trials and selection (the ctrl/COMPLEX0
        # M2-fingerprint contract); a plateau cell gets the pure-cost
        # arrangement of each alternative decomposition as a candidate.
        # On a cage=False chain the twins would refine identically, so
        # the phase is gated on the steering.
        if cage and legacy_best is not None and \
                (feasible is None or feasible["cage"] > 0):
            extra = decomposition_variant_classes(netlist, leg_widths,
                                                  cage=cage,
                                                  basin="legacy")
            for kind, op, on in extra:
                if ordering_signature(op, on) in known:
                    continue
                known.add(ordering_signature(op, on))
                pool.append((kind, op, on))
            for idx in range(len(entries), len(pool)):
                entry = _trial(idx)
                won = _keep(entry, pool[idx][1], pool[idx][2])
                if won is not None:
                    return won
    # feasible tracks the ENTRY dict; fallback tracks (key, entry)
    winner = feasible if feasible is not None else fallback[1]
    op, on = pool[winner["index"]][1], pool[winner["index"]][2]
    return _won(winner, op, on)


def sa_refine_routable(ordering_p, ordering_n, netlist, leg_widths,
                       candidate_count=DEFAULT_CANDIDATES,
                       trial_attempts=DEFAULT_TRIAL_ATTEMPTS,
                       trial_router=None, iterations=None,
                       quality=DEFAULT_QUALITY, init_moves=None,
                       seed=None, check=True, variant_classes=False,
                       cage=None):
    """``sa_refine`` + the speculate selection stage: the rung-3 entry
    point for routability-aware placement.

    Mirrors :func:`sa_refine`'s positional signature and RETURN SHAPE
    -- ``(ordering_p, ordering_n, breakdown)`` -- so a call site only
    changes the function name.  Differences:

    - the returned orderings are the routability-selected candidate,
      not necessarily the cost-best one (the cost-best is tried first,
      so a cell that already routes keeps it);
    - ``breakdown`` describes the SELECTED ordering (what will actually
      be laid out) and carries the speculate ``selection`` report;
      ``breakdown["selection"]["feasible"]`` says whether any candidate
      routed at the trial budget.

    ``ordering_p``/``ordering_n`` are consumed twice: as the SA seed
    and as the alternative-ordering candidates of the speculate pool.
    All randomness stays inside sa_refine's content-hash discipline;
    the selection itself uses none (invariant 9).  ``trial_router`` is
    injectable for tests; the default runs the real
    ``route_grid.route_cell`` at ``trial_attempts``, TRUE-VIEW: every
    candidate is trialed against its own block view (see
    :func:`select_orderings`; injected fakes without the ``blocks``
    parameter keep the blocks-less legacy call).
    ``variant_classes=True`` additionally joins the decomposition-
    variant classes (see :func:`select_orderings`) when the fixed
    classes all fail -- the upstream lever for the one-decomposition
    routing plateaus.  ``cage`` runs the refine AND the
    decomposition-variant refines with the gate-cage term in their cost
    (see :func:`sa_refine`) -- the placement-side avoidance lever for
    the power-stripe-caged gate contacts of AUDIT 5.46.  ``cage=None``
    (the default) binds the steering to the full production chain
    (``variant_classes=True``): the engine's rung-3 chain prefers
    cage-free arrangements end to end, while the fixed-pool path keeps
    the pure ASTRAN cost byte-for-byte -- the structural-diagnosis
    specimens are derived on THOSE arrangements and pinned so.  An
    explicit ``cage`` (True/False) overrides the binding everywhere.

    Dual basin (bench_int5 -> bench_int6 restoration): a steered chain
    (``cage=True``) refines the seed TWICE -- the steered cost leads
    the pool exactly as before, and the ``cage=False`` refine's best
    joins the fixed pool as ``best-legacy`` (plus its proven both-rows
    mirrors) and, lazily, as the legacy twins of every decomposition
    variant -- so a closure living in the pure-cost basin keeps its
    candidate in the pool.  The extra refines reuse the caller's
    budgets verbatim (agent E's size-aware variant scaling is
    untouched); above _VARIANT_SA_PROBLEM_CAP the variant twins
    degenerate to the euler seed and dedupe away.
    """
    if cage is None:
        cage = bool(variant_classes)
    cost_p, cost_n, _bd = sa_refine(
        ordering_p, ordering_n, netlist, leg_widths,
        iterations=iterations, quality=quality, init_moves=init_moves,
        seed=seed, check=check, cage=cage)
    legacy_best = None
    eff_candidates = candidate_count
    if cage:
        leg_p, leg_n, _lbd = sa_refine(
            ordering_p, ordering_n, netlist, leg_widths,
            iterations=iterations, quality=quality, init_moves=init_moves,
            seed=seed, check=check, cage=False)
        legacy_best = (leg_p, leg_n)
        eff_candidates = candidate_count + LEGACY_BASIN_CLASSES
    sel_p, sel_n, sel = select_orderings(
        cost_p, cost_n, ordering_p, ordering_n, netlist, leg_widths,
        candidate_count=eff_candidates, trial_attempts=trial_attempts,
        trial_router=trial_router, variant_classes=variant_classes,
        cage=cage, legacy_best=legacy_best)
    breakdown = _SAState(sel_p, sel_n, leg_widths).breakdown()
    breakdown["selection"] = sel
    return sel_p, sel_n, breakdown
