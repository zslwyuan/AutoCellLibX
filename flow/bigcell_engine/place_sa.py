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
  (sum of block widths + one break column per diffusion break), which is
  exactly what geometry.layout_cell emits;
- ``mismatchesGate`` counts per *column* (both rows carry a gate stripe
  in the same column with different nets) instead of per slot, because
  blocks span several columns; net bounding boxes / congestion cover
  every diffusion edge and gate centre of every non-power net in one
  column space shared by both rows, like ASTRAN's posPN space; power
  nets are excluded from the bbox terms, as in getCost.

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

Throughput note: DEFAULT_QUALITY is 20, not ASTRAN's 150 -- Python
applies ~5k moves/s where ASTRAN's C applies ~10^6/s; the budget is set
by measured convergence on the benchmark corpus (doc section 6, risk 1),
not by copying ASTRAN's constant.  ``quality`` stays a parameter.
"""

import hashlib
import math
import random

from smt_engine.netlist import BlockMember

from bigcell_engine.netlist_ext import mirror_block

ENGINE_VERSION = "bigcell-sa/1"

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
    """Column picture of one row, mirroring geometry.place_row exactly:
    one break column where a block's left net differs from the previous
    block's right net; a member registers its left net at its first
    column, right net at its last, gate stripes at the leg centres.
    Returns (dnet, gate, breaks, width, starts, ends)."""
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
            dnet[col] = lnet
            dnet[col + w - 1] = rnet
            for off in centres:
                gate[col + off] = dev.gate
            col += w
            end = col - 1
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
            # geometry.default_leg_widths semantics, inlined: that helper
            # currently reads a nonexistent Device.width attribute
            # (flagged to geometry's owner); keep the fallback local.
            from bigcell_engine.geometry import (DEFAULT_LEG_WIDTHS_MIN_COLS,
                                                 GRID_UM)
            devices = [m.device for row in (ordering_p, ordering_n)
                       for b in row for m in b.members]
            leg_widths = {dev.name: (1, max(
                DEFAULT_LEG_WIDTHS_MIN_COLS,
                int(math.ceil(float(dev.width_um) / GRID_UM))))
                for dev in devices}
        self.leg_widths = leg_widths
        self.rows = [[_entry(b, False, leg_widths) for b in ordering_p],
                     [_entry(b, False, leg_widths) for b in ordering_n]]
        self.power = frozenset(POWER_NETS)
        total_w = sum(e.width for row in self.rows for e in row)
        breaks_ub = sum(max(0, len(row) - 1) for row in self.rows)
        self.max_cols = total_w + breaks_ub + 2
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
