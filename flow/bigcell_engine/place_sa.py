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
"""

import hashlib
import itertools
import math
import random
import re

from smt_engine.netlist import BlockMember

from bigcell_engine.geometry import BREAK_GAP_COLS, N_ROW, P_ROW
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
    """Dual-row ordering + cached cost.  All arithmetic is integer."""

    def __init__(self, ordering_p, ordering_n, leg_widths):
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
        self.total = self._total_from_terms()

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
        self.total = self._total_from_terms()
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
              check=True):
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
    """
    state = _SAState(ordering_p, ordering_n, leg_widths)
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
                         limit=ALIGN_CANDIDATES, pair_cap=None):
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
        5. lexicographic ordering signature (deterministic tie-break).

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
    # cost, signature), truncate
    p_by_sig = {sp: r for (_m, sp), r in zip(p_maps, p_rows)}
    n_by_sig = {sn: r for (_m, sn), r in zip(n_maps, n_rows)}
    ranked = []
    for ga, da, br, wp, sp, sn in finalists:
        op = p_by_sig[sp]
        on = n_by_sig[sn]
        cost = _SAState(op, on, leg_widths).total
        ranked.append(((ga, da, br, cost, sp, sn), op, on))
    # stable two-stage final rank: cost (then signature) ascending, then
    # the alignment/corridor key descending -- ties keep the cheaper,
    # lexicographically smaller ordering
    ranked.sort(key=lambda t: (t[0][3], t[0][4], t[0][5]))
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
                                  align_limit=ALIGN_CANDIDATES):
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
                                        problem_size, cap=sa_iterations))
        else:
            bp, bn = eop, eon
        classes = [("var:%s" % name, bp, bn),
                   ("var:%s-flip-both" % name,
                    _row_flipped(bp), _row_flipped(bn)),
                   ("var:%s-die-both" % name,
                    _row_die_mirror(bp), _row_die_mirror(bn))]
        for j, (op, on) in enumerate(
                alignment_candidates(p_blocks, n_blocks, leg_widths,
                                     limit=align_limit,
                                     pair_cap=_alignment_pair_cap(
                                         problem_size)), start=1):
            classes.append(("var:%s-align%d" % (name, j), op, on))
        for kind, op, on in classes:
            sig = ordering_signature(op, on)
            if sig in seen:
                continue
            seen.add(sig)
            out.append((kind, op, on))
    return out


def generate_candidates(best_p, best_n, seed_p, seed_n, leg_widths,
                        candidate_count=DEFAULT_CANDIDATES,
                        extra_classes=None):
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
    5. further per-block flip combinations of the SA best, ranked by
       SA cost then lexicographic bit order (only below the fixed
       classes when ``candidate_count`` allows, and only when
       2**(nP+nN) <= _MAX_FLIP_COMBOS);
    6. ``extra_classes`` -- pre-built (kind, ordering_p, ordering_n)
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
    n_blocks = len(best_p) + len(best_n)
    if 2 ** n_blocks <= _MAX_FLIP_COMBOS:
        combos = []
        for bits in _iter_flip_bits(len(best_p), len(best_n)):
            op = [b if not bit else mirror_block(b)
                  for b, bit in zip(best_p, bits[:len(best_p)])]
            on = [b if not bit else mirror_block(b)
                  for b, bit in zip(best_n, bits[len(best_p):])]
            combos.append((_SAState(op, on, leg_widths).total, bits, op, on))
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


def select_orderings(best_p, best_n, seed_p, seed_n, netlist, leg_widths,
                     candidate_count=DEFAULT_CANDIDATES,
                     trial_attempts=DEFAULT_TRIAL_ATTEMPTS,
                     trial_router=None, variant_classes=False):
    """Speculate stage (doc section 2.2 "Composition"): score the
    candidate pool by a fast trial route and pick the winner.

    Returns ``(ordering_p, ordering_n, report)``.  A candidate that
    routes FEASIBLE at ``trial_attempts`` wins immediately, in pool
    priority order (the SA-best candidate is tried first, so a cell
    whose cost-optimal orientation already routes is unaffected --
    INVX1/NAND2 stay on the pure-cost path).  When nothing routes
    within the trial budget the candidate with the lowest
    (conflicts, SA cost, pool index) is returned: the caller's
    full-budget route then starts from the best-known orientation.

    ``variant_classes`` extends the pool with the decomposition-variant
    classes (:func:`decomposition_variant_classes`) when the fixed
    classes all fail their trials -- the conflict evidence shows
    plateaus that survive every ordering of ONE decomposition, so the
    alternative decompositions join as a lazy second phase (a cell that
    closes in the fixed classes never pays for them).  Variants rank
    exactly like the mirror classes: first FEASIBLE wins, fallback =
    lowest (conflicts, cost, pool index).  Candidates are deduped by
    :func:`ordering_signature` (content-only: two decompositions
    producing the same ordering route identically, so one trial
    covers both; the report's ``kind`` carries the first occurrence's
    provenance).

    ``trial_router`` defaults to ``route_grid.route_cell`` and is
    called as ``router(netlist, placements, width_cols, leg_widths,
    max_attempts=trial_attempts)``; an injected stub must keep that
    contract.  A router exception is caught and scored _UNROUTABLE
    (recorded in the report) so one bad candidate cannot kill the
    placement.

    ``report`` (plain data, no wall-clock -- invariant 9):
    ``selected``/``kind``/``feasible``/``conflicts`` of the winner plus
    per-trialed-candidate entries.  Pure and deterministic.
    """
    router = trial_router if trial_router is not None \
        else _default_trial_router()
    if leg_widths is None:
        from bigcell_engine.geometry import default_leg_widths
        leg_widths = default_leg_widths(
            [m.device for row in (best_p, best_n, seed_p, seed_n)
             for b in row for m in b.members])
    pool = generate_candidates(best_p, best_n, seed_p, seed_n, leg_widths,
                               candidate_count)
    from bigcell_engine.geometry import layout_cell
    entries = []
    fallback = None                     # (conflicts, cost, index) -> entry

    def _trial(idx):
        """Trial-route pool[idx]; append the report entry; return it."""
        kind, op, on = pool[idx]
        placements, width = layout_cell(op, on, leg_widths)
        try:
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
                 "feasible": conflicts == 0,
                 "attempts": getattr(result, "attempts_used", None),
                 "note": note}
        entries.append(entry)
        return entry

    def _keep(entry, op, on):
        """Short-circuit on FEASIBLE; track the fallback winner."""
        nonlocal fallback
        if entry["conflicts"] == 0:
            return op, on, {
                "selected": entry["index"], "kind": entry["kind"],
                "feasible": True, "conflicts": 0,
                "trial_attempts": trial_attempts,
                "candidate_count": len(pool), "candidates": entries,
            }
        if fallback is None or (entry["conflicts"], entry["cost"],
                                entry["index"]) < \
                (fallback["conflicts"], fallback["cost"],
                 fallback["index"]):
            fallback = entry
        return None

    for idx in range(len(pool)):
        entry = _trial(idx)
        won = _keep(entry, pool[idx][1], pool[idx][2])
        if won is not None:
            return won
    if variant_classes:
        # phase 2: the decomposition-variant classes, deduped against
        # everything already trialed
        extra = decomposition_variant_classes(netlist, leg_widths)
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
    return pool[fallback["index"]][1], pool[fallback["index"]][2], {
        "selected": fallback["index"], "kind": fallback["kind"],
        "feasible": False, "conflicts": fallback["conflicts"],
        "trial_attempts": trial_attempts,
        "candidate_count": len(pool), "candidates": entries,
    }


def sa_refine_routable(ordering_p, ordering_n, netlist, leg_widths,
                       candidate_count=DEFAULT_CANDIDATES,
                       trial_attempts=DEFAULT_TRIAL_ATTEMPTS,
                       trial_router=None, iterations=None,
                       quality=DEFAULT_QUALITY, init_moves=None,
                       seed=None, check=True, variant_classes=False):
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
    ``route_grid.route_cell`` at ``trial_attempts``.
    ``variant_classes=True`` additionally joins the decomposition-
    variant classes (see :func:`select_orderings`) when the fixed
    classes all fail -- the upstream lever for the one-decomposition
    routing plateaus.
    """
    cost_p, cost_n, _bd = sa_refine(
        ordering_p, ordering_n, netlist, leg_widths,
        iterations=iterations, quality=quality, init_moves=init_moves,
        seed=seed, check=check)
    sel_p, sel_n, sel = select_orderings(
        cost_p, cost_n, ordering_p, ordering_n, netlist, leg_widths,
        candidate_count=candidate_count, trial_attempts=trial_attempts,
        trial_router=trial_router, variant_classes=variant_classes)
    breakdown = _SAState(sel_p, sel_n, leg_widths).breakdown()
    breakdown["selection"] = sel
    return sel_p, sel_n, breakdown
