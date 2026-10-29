"""The faithful ASTRAN router port: the element graph + GraphRouter.

A line-by-line port of the routing algorithm ASTRAN's own cell generator
runs (AutoCell::route, tools/astran/src/autocell2.cpp:243-474, driving
GraphRouter, tools/astran/src/graphrouter.cpp) onto the astran13 track
domain and the slot-model geometry (region widths + row x-offsets,
geometry.py's variables).  This is the router that closed the 21
ASTRAN-fallback cells' .gds layouts; route_grid.py is its earlier
adaptation to the 9-bar vocabulary -- the two are compared divergence
by divergence in the module header below.

The graph (the C++ node kinds, verbatim costs)
----------------------------------------------
Per COLUMN c (the slot-model edge axis, 0..W -- one column per element
of autocell2.cpp's walk; edges 0/W double the leading/trailing lateral
GAP escape elements, autocell2.cpp:304/:463) and per signal track t of
the domain (gds.py's astran13 list -- the 16 interior levels of
ASTRAN's own rule-derived trackPos, autocell2.cpp:83-100; the two power
end tracks the C++ reserves for gnd/vdd, autocell2.cpp:55-56, are the
bar-domain rail ends):

- ``MET``   met[x]      (autocell2.cpp:25)   -- the M1 point grid;
- ``POL``   pol[x]      (autocell2.cpp:40)   -- poly points;
- ``DIFF``  diffP/diffN (autocell2.cpp:13-14)-- diffusion terminals;
- ``HUB``   inoutCnt    (autocell2.cpp:58)   -- the per-column pin hub;
- ``PIN``   inoutPins   (autocell2.cpp:296)  -- one per external net;
- ``M2``    the 3-layer grid's second metal (Router::setup layer 2,
  router.cpp:55) -- the port's metal2 phase.

Arcs, all with the C++ costs (file:line in the constants below):
vertical M1 (the createElement three-way rule), horizontal M1 (4),
poly vertical along a gate stripe and poly horizontal over field (6),
gate-column poly<->M1 contacts (20), diffusion contacts over the
terminal span (20), the hub entry (495 corridor / 500), pin-hub (0);
the M2 phase adds the directional GridRouter triple M2 h=4 / v=11 with
via 4 at every node (router.cpp:54-55 -- the vocabulary the RouteResult
contract's m2/m2v/m2via fields speaks).

The solver is GraphRouter verbatim (graphrouter.cpp): routeNets'
negotiated congestion (rip up conflicted nets, history-priced
re-route, the 8000-attempt cap and the 50000-stall break), then
optimize() twice (autocell2.cpp:470-472) with prim/addSteiner.  The
queue discipline is a deterministic heap: (cost, insertion counter) --
the C++'s priority_queue pops the least cost; ties keep insertion
order.

Divergences from route_grid.py (the port follows the C++)
---------------------------------------------------------
route_grid adapted the C++ to the 9-bar RouteResult vocabulary; this
port re-derives from the C++ and clips only where the RouteResult
contract itself is narrower (every clip is checkable by verify_cell):

1. Gate terminals: route_grid uses ONE gate node per (net, column)
   with cost-0 poly-junction arcs; the C++ makes the pol[x] NODES over
   the gate stripe the terminals, joined by the cost-6 vertical chain
   (autocell2.cpp:380-391) -- the drawn merged poly stripe IS the
   router's resource.  The port follows the C++ (clipped to the stripe
   verify's gate connector joins).
2. Poly jumps: route_grid prices them via a per-net _allow rule
   (foreign-gate + field legality, its own invention); the C++ has
   only node ownership -- a foreign gate's pol nodes are that net's
   terminals, so no foreign poly route can ever touch them.  The port
   creates the arcs where the C++ does (right end over field,
   autocell2.cpp:45-52) and lets ownership do the rest.
3. Diffusion terminals: route_grid claims ONE M1 point per access (the
   rail track); the C++ has the diff node with 20-cost contact arcs
   over the whole terminal span (autocell2.cpp:277, :352-353) -- the
   contact can land anywhere the drawn strip spans.  The port follows
   the C++ and solidifies the access stripe to the rail track in the
   conversion (verify's access-track demand).
4. Power: the C++ routes gnd/vdd as ordinary nets (met[0]/met[last]
   terminals at every element, autocell2.cpp:55-56); the port
   pre-builds their stripes (the rails are drawn unconditionally by
   gds_cells, so the C++ rail chain is subsumed) -- the negotiated
   outcome the C++ always reaches, without the churn.
5. No vocabulary post-pass: route_grid negotiates the RouteResult
   constraints (one stripe per slot, via forms, single pin stubs) with
   history bumps -- extensions of its own; the C++ has ONLY node
   conflicts.  The port keeps the C++ loop pure and does the
   vocabulary work in the conversion (build_result): fills and
   crossings are added with full collision checks and an honest fail
   note where the C++ solution needs geometry the vocabulary cannot
   express (e.g. two nets' vertical runs in one half-column).

Divergences forced by the RouteResult contract (documented, checked)
----------------------------------------------------------------------
- pol<->M1 contacts exist only at gate columns in the C++ too (cost 20
  at GATE elements, autocell2.cpp:48) but ALSO at source/drain elements
  (cost 200, autocell2.cpp:47); the 200-cost contacts join a poly route
  to an M1 route in mid-field, and the vocabulary has NO such junction
  (verify: a poly<->M1 layer switch between adjacent same-net segments
  is a violation; only the gate crossing is a legal contact).  The
  port drops the 200-cost arcs -- poly routes end at gates or over
  field, exactly the freedom verify accepts.
- The C++'s vertical pol chains at gate elements span the full column
  height (autocell2.cpp:41, type==GATE); the port clips them to the
  drawn gate stripe (verify's gate span + overhang -- a contact
  outside it would float).
- The M1 contact at a gate must span the column rightward
  (hseg (t, c), the contact square drawn at the column centre); the
  C++ contact sits at the element x and is covered by metal leaving
  either way.  The conversion solidifies the right span
  (collision-checked) and reports a gate with no realizable crossing
  honestly.
- optimize() in the C++ ignores bfsRoute2's return, so a net whose
  strict re-route fails silently keeps a partial, disconnected tree;
  the port restores the conflict-free pre-optimize solution there (a
  safety net, never observed to fire on the oracle cells).

The conversion and the vocabulary feedback
-------------------------------------------
The C++ solution is NODE-exclusive; the RouteResult contract is
narrower, and the port bridges the two in three layers:

1. **build_result** converts the trees ARC BY ARC (the C++ draws its
   solution arc by arc; the tree's node set alone cannot distinguish a
   used wire from two terminals that merely sit in adjacent columns).
   The stripes come from the used vertical met arcs plus the claimed
   rail points, filled only where the vocabulary demands it (the
   access coverage, per half); the segments come from the used
   horizontal arcs; the gate merges from the used contact arcs plus
   the arrival merges of wires ending at gate terminals; every added
   point is collision-checked against the geometry the other nets
   actually draw, and an inexpressible need is an honest fail.
2. **the gate-join repair**: a net's gate stripes are separate
   conductors, and the tree's tie may have been dropped (an
   unanchored poly run) or half-expressed (a departure merge whose
   arrival collided).  When the emitted margin crossings do not chain
   the net's gate columns, the conversion re-crosses them with M1
   stubs at one common free drawable track (adjacent stubs touch), or
   an L-join: a horizontal wire at t1, a vertical stripe at the
   target column, and the crossing stub at t2 -- the track-change tie
   for two drawable bands that do not overlap.
3. **the vocabulary feedback** (route_cell_ported): when a routed
   solution cannot be expressed, the conversion reports the blocker
   NODES and the router re-routes with their congestion history
   bumped -- GraphRouter's own negotiated-congestion mechanism
   (graphrouter.cpp:135-138) applied to the vocabulary layer -- for at
   most VOCAB_ROUNDS rounds per phase, then the next phase runs.  The
   C++'s optimize clears the graph's history every sweep, so the
   feedback keeps its own cumulative bookkeeping.

Determinism (AGENTS.md invariants 8/9): nets are routed in sorted-name
order (the C++ iterates its netlist map by net id -- a SPICE-order
artifact; the port pins the order); the heap breaks cost ties by
insertion counter; every loop runs on sorted structures or fixed
counts; no wall-clock, no set/dict iteration order reaches an output.
Identical inputs give a byte-identical RouteResult cross-process.
"""

import heapq

from bigcell_engine.geometry import WELL_GAP_UM
from smt_engine import die_view
from smt_engine.gds import (CONTACT_S, POLY_OVERHANG, row_geometry,
                            track_domain)
from smt_engine.netlist import gate_access_points
from smt_engine.route_model import RouteResult, _field_map, device_rail

# ---- the C++'s own fixed budgets (autocell2.cpp / graphrouter.cpp) ----
MAX_ATTEMPTS = 8000             # autocell2.cpp:470 routeNets(8000)
STEINER_SWEEPS = 2              # autocell2.cpp:472 optimize() && optimize()
STALL_ATTEMPTS = 50000          # graphrouter.cpp:165 cntConflict stall break
VOCAB_ROUNDS = 6               # the vocabulary feedback's round cap per
                               # phase (route -> convert -> bump -> re-route)
VOCAB_BUMP = 25                # the history increment per blocked node
                               # per round (the C++ bumps by 1 per contested
                               # node per attempt; the vocabulary blocks are
                               # coarser, so the price is too)

# ---- the verbatim arc-cost table (AutoCell::route / createElement) ----
H_MET_COST = 4              # autocell2.cpp:36-38 horizontal met-met arc
VCOST_DIFF = 4              # autocell2.cpp:333/:428 createElement(4, ...):
                            # diffusion/gap/break columns
VCOST_GATE = 16             # autocell2.cpp:304/:375/:463 createElement(16,..):
                            # gate and lateral columns
V_OUTSIDE_DISCOUNT = 1      # autocell2.cpp:28 vertical arc = vcost-1 outside
                            # the diffusion spans
V_CORRIDOR_SURCHARGE = 1    # autocell2.cpp:31 vertical arc = vcost+1 in the
                            # N<->P well-boundary corridor (non-gate columns;
                            # the reduceVRt=true branch doubles vcost instead)
POLY_ARC_COST = 6           # autocell2.cpp:42/:51 poly-poly arcs
GATE_CONTACT_COST = 20      # autocell2.cpp:48 pol<->met at gate columns
DIFF_CONTACT_COST = 20      # autocell2.cpp:277 COST_CNT_INSIDE_DIFF
HUB_CORRIDOR_COST = 495     # autocell2.cpp:62 inoutCnt->met, corridor tracks
HUB_COST = 500              # autocell2.cpp:62 inoutCnt->met, elsewhere
# ---- the 3-layer directional grid's metal2 triple (Router::setup) ----
M2_H_COST = 4               # router.cpp:55 layer-2 h-cost
M2_V_COST = 11              # router.cpp:55 layer-2 v-cost
VIA_COST = 4                # router.cpp:54/:55 via-up at any node

GND_NAMES = ("GND", "VSS")
VCC_NAMES = ("VCC", "VDD")
POWER_NAMES = GND_NAMES + VCC_NAMES

_MET, _M2, _POL, _DIFF, _HUB, _PIN = ("MET", "M2", "POL", "DIFF", "HUB",
                                      "PIN")


class _Node(object):
    """graphrouter.h Node: kind, owning net, users, history, source."""

    __slots__ = ("kind", "net", "nr_nets", "history", "source", "arcs")

    def __init__(self, kind):
        self.kind = kind            # (kind-tag, ...) geometry tuple
        self.net = -1
        self.nr_nets = 0
        self.history = 0
        self.source = 0             # 1 = terminal, 2 = added Steiner point
        self.arcs = []              # arc indexes, insertion order


class _Arc(object):
    """graphrouter.h t_arc."""

    __slots__ = ("cost", "label", "n1", "n2", "lock_net")

    def __init__(self, n1, n2, cost):
        self.cost = cost
        self.label = -1
        self.n1 = n1
        self.n2 = n2
        self.lock_net = -1          # never assigned (graphrouter.cpp)


class _Net(object):
    """graphrouter.h t_nets: the net's terminals and current tree.

    ``arcs_used`` records the arc ids of every definitive traceback
    (the C++ draws its solution arc by arc -- the tree's NODE set alone
    cannot distinguish a used wire from two terminals that merely sit
    in adjacent columns, so the port keeps the arcs too).
    """

    __slots__ = ("index", "name", "nodes", "tree", "conflict",
                 "arcs_used")

    def __init__(self, index, name):
        self.index = index
        self.name = name
        self.nodes = []             # terminals (+ Steiner points), fixed order
        self.tree = []              # the current routing tree (node list)
        self.conflict = False
        self.arcs_used = []         # arc ids of the definitive tracebacks


class _ElementRouter(object):
    """The element graph + GraphRouter solver for one cell.

    Deterministic and pure: identical (netlist, placement, geometry)
    inputs produce a byte-identical solution.
    """

    def __init__(self, netlist, placement, width_cols, blocks=None,
                 height_um=2.47, grid_um=0.19, metal2=False,
                 tracks="astran13"):
        self.netlist = netlist
        self.placement = placement
        # the slot-model edge grid: one column per element, edges 0..W --
        # the trailing edge W doubles ASTRAN's trailing lateral GAP
        # escape column (route_grid's slot convention; the leading one
        # is edge 0), so the route covers every placement column + 1
        self.width_cols = max(width_cols,
                              max((p.end_col
                                   for p in placement.values()), default=0))
        self.n_cols = self.width_cols + 1
        self.height_um = height_um
        self.grid_um = grid_um
        self.metal2 = metal2
        self.dom = dom = track_domain(tracks, height_um, grid_um)
        self.n_tracks = dom.n_tracks
        self.boundary_t = dom.boundary_t
        self.bar_levels = dom.bar_levels
        self.row_track = dom.row_track
        self.row_tracks = dom.row_tracks
        self.trackY = dom.trackY
        self.blocks = blocks
        self.graph = []
        self.arcs = []
        self._id = {}
        self.nets = []              # routed signal nets, sorted-name order
        self.power = []             # pre-built power stripe nets
        self._fail_note = None
        self._label = 0
        self.attempts_used = 0
        self.conflict_trace = []
        self._build()
        self._prepare_hot()

    # ---------------- graph construction ----------------

    def _node(self, kind):
        nid = self._id.get(kind)
        if nid is None:
            nid = len(self.graph)
            self.graph.append(_Node(kind))
            self._id[kind] = nid
        return nid

    def _met(self, t, c):
        return self._node((_MET, t, c))

    def _pol(self, t, c):
        return self._node((_POL, t, c))

    def _add_arc(self, a, b, cost):
        self.arcs.append(_Arc(a, b, cost))
        self.graph[a].arcs.append(len(self.arcs) - 1)
        self.graph[b].arcs.append(len(self.arcs) - 1)

    def _claim(self, nid, net):
        """GraphRouter::addNodetoNet (graphrouter.cpp:32-39)."""
        node = self.graph[nid]
        if node.net != -1:
            return
        node.net = net.index
        node.nr_nets = 0
        node.source = 1
        net.nodes.append(nid)

    def _dev_strip_y(self, dev):
        """(y0, y1) the device's drawn diffusion spans (verify's rule:
        the W-tall well-anchored strip on astran13, the row band on
        bar9 -- smt_engine.verify._gate_spans' dom branch)."""
        if self.dom.strip_anchored:
            return self.dom.strip_y(dev.is_p, dev.width_um, self.height_um)
        _, rows = row_geometry(self.height_um, self.grid_um)
        return rows[(dev.is_p, self.placement[dev].row)]

    def _cost_spans(self):
        """{col: {is_p: (lo, hi) track span or None}} -- the per-element
        diffusion spans of autocell2.cpp:319-329 (the strips covering
        the column, edges inclusive: a terminal edge sees its strip,
        the C++ source element sits inside the region)."""
        sets = {c: {False: set(), True: set()} for c in range(self.n_cols)}
        for dev in self.netlist.devices:
            p = self.placement[dev]
            y0, y1 = self._dev_strip_y(dev)
            ts = set(t for t in range(self.n_tracks)
                     if y0 <= self.trackY[t] <= y1)
            for c in range(p.start_col, p.end_col + 1):
                if c < self.n_cols:
                    sets[c][dev.is_p] |= ts
        return {c: {side: ((min(ts), max(ts)) if ts else None)
                    for side, ts in per.items()}
                for c, per in sets.items()}

    def _gate_maps(self):
        """(gate_tracks, gate_pol, gate_span, gate_nets_at).

        - ``gate_tracks``: the drawable M1 contact range per (net, col)
          -- route_grid._gate_maps' slot formula (the strip clipped to
          the verify row band, poly overhang in, contact half-size out,
          plus the well-boundary corridor track of an aligned P/N
          pair): the range gds_cells draws a contact square on and
          every consumer of the shared die view accepts;
        - ``gate_pol``: the poly-join tracks per (net, col) -- verify's
          gate span (the strips +/- POLY_OVERHANG), where a poly
          crossing merges with the drawn stripe: the C++ pol-node
          terminal range (autocell2.cpp:380-391);
        - ``gate_span``: the raw (y0, y1) per (net, col);
        - ``gate_nets_at``: {net: set(cols)} like every consumer.
        """
        netlist, placement = self.netlist, self.placement
        _, rows = row_geometry(self.height_um, self.grid_um)
        trackY = self.trackY
        spans = {}                # (net, c) -> row-band union (route_grid)
        strip_ranges = {}         # (net, c) -> [(strip y0, strip y1)]
        strip_pol = {}            # (net, c) -> [has_p, has_n]
        vspans = {}               # (net, c) -> drawn-strip union (verify)
        for dev in netlist.devices:
            p = placement[dev]
            y0, y1 = rows[(dev.is_p, p.row)]
            sy0, sy1 = self._dev_strip_y(dev)
            for j in range(p.legs):
                c = p.start_col + j * p.leg_width_cols \
                    + p.leg_width_cols // 2
                if c >= self.n_cols:
                    continue
                key = (dev.gate, c)
                if key in spans:
                    o0, o1 = spans[key]
                    spans[key] = (min(o0, y0), max(o1, y1))
                    v0, v1 = vspans[key]
                    vspans[key] = (min(v0, sy0), max(v1, sy1))
                else:
                    spans[key] = (y0, y1)
                    vspans[key] = (sy0, sy1)
                strip_ranges.setdefault(key, []).append((sy0, sy1))
                pol = strip_pol.setdefault(key, [False, False])
                pol[0 if dev.is_p else 1] = True
        gate_tracks = {}
        gate_pol = {}
        gate_span = {}
        gate_nets_at = {}
        for key, (y0, y1) in sorted(spans.items()):
            net, c = key
            gate_nets_at.setdefault(net, set()).add(c)
            gate_span[key] = (y0 - POLY_OVERHANG, y1 + POLY_OVERHANG)
            vy = vspans[key]
            gate_pol[key] = sorted(
                t for t in range(self.n_tracks)
                if vy[0] - POLY_OVERHANG <= trackY[t]
                <= vy[1] + POLY_OVERHANG)
            tracks = set()
            for sy0, sy1 in strip_ranges[key]:
                lo = max(sy0, y0) - POLY_OVERHANG + CONTACT_S / 2.0
                hi = min(sy1, y1) + POLY_OVERHANG - CONTACT_S / 2.0
                tracks.update(t for t in range(self.n_tracks)
                              if lo <= trackY[t] <= hi)
            pol = strip_pol[key]
            if pol[0] and pol[1]:
                # aligned P/N pair: the drawn merged stripe is continuous
                # over the well boundary -- the corridor contact joins
                mid = self.height_um / 2.0
                lo = mid - WELL_GAP_UM + CONTACT_S / 2.0
                hi = mid + WELL_GAP_UM - CONTACT_S / 2.0
                tracks.update(t for t in range(self.n_tracks)
                              if lo <= trackY[t] <= hi)
            gate_tracks[key] = sorted(tracks)
        return gate_tracks, gate_pol, gate_span, gate_nets_at

    def _build(self):
        netlist, placement = self.netlist, self.placement
        W = self.width_cols
        T = self.n_tracks

        # ---- static per-column geometry (shared with verify) ----
        self.spans = self._cost_spans()
        (self.gate_tracks, self.gate_pol, self.gate_span,
         self.gate_nets_at) = self._gate_maps()
        self.gate_cols = set()
        for cols in self.gate_nets_at.values():
            self.gate_cols.update(cols)
        self.field = _field_map(netlist, placement, self.n_cols,
                                self.dom, self.height_um)
        # the gate pol terminals per column: {c: {t: net}} (a column can
        # carry one P and one N gate, foreign -- the projection's
        # optional cross-row share; the vertical chains clip to each
        # gate's own stripe so they never touch)
        self.gate_terminal = {}
        for (net, c), ts in sorted(self.gate_pol.items()):
            for t in ts:
                self.gate_terminal.setdefault(c, {})[t] = net

        # ---- terminals from the shared die view (verify's own) ----
        self.sig_diff, self.pow_diff = die_view.die_slot_access_points(
            netlist, placement, blocks=self.blocks)
        gate_pts = gate_access_points(netlist, placement)
        ports = getattr(netlist, "external", set())
        routed = sorted(n for n in netlist.signal_nets()
                        if self.sig_diff.get(n) or gate_pts.get(n))
        index = 0
        for name in routed:
            self.nets.append(_Net(index, name))
            index += 1
        for name in sorted(self.pow_diff):
            self.power.append(_Net(index, name))
            index += 1
        self.power_index = {net.name: net.index for net in self.power}
        self.net_by_name = {net.name: net for net in self.nets + self.power}
        self.net_index = {net.index: net for net in self.nets + self.power}

        # ---- nodes: MET / POL (+M2) at every (track, column) ----
        for c in range(self.n_cols):
            for t in range(T):
                self._met(t, c)
                self._pol(t, c)
                if self.metal2:
                    self._node((_M2, t, c))

        # ---- arcs, per column, in the createElement order ----
        for c in range(self.n_cols):
            n_end, n_ini = self._span_of(c, False)
            p_ini, p_end = self._span_of(c, True)
            vcost = VCOST_GATE if c in self.gate_cols else VCOST_DIFF
            for t in range(T):
                # vertical MET (autocell2.cpp:26-33): outside the spans
                # vcost-1, the well-boundary corridor vcost+1 (non-gate
                # columns), else vcost
                if t:
                    if (t <= n_end or t > p_end):
                        cost = vcost - V_OUTSIDE_DISCOUNT
                    elif (t > n_ini and t <= p_ini
                          and c not in self.gate_cols):
                        cost = vcost + V_CORRIDOR_SURCHARGE
                    else:
                        cost = vcost
                    self._add_arc(self._met(t - 1, c), self._met(t, c),
                                  cost)
                # horizontal MET (autocell2.cpp:34-39) with the previous
                # column; reduceMetTracks = conservative = 0 in the
                # production autoFlow, so every track qualifies
                if c:
                    self._add_arc(self._met(t, c - 1), self._met(t, c),
                                  H_MET_COST)
                # vertical POL: the C++ chains the full column at gate
                # elements (autocell2.cpp:41, type==GATE); the port
                # clips to the drawn gate stripes (the vocabulary's
                # gate connector -- see the module header)
                if (t and c in self.gate_terminal
                        and (t - 1) in self.gate_terminal[c]
                        and t in self.gate_terminal[c]):
                    self._add_arc(self._pol(t - 1, c), self._pol(t, c),
                                  POLY_ARC_COST)
                # horizontal POL (autocell2.cpp:50-51, hPoly): the arc
                # (t, c-1)-(t, c) is the pj (t, c-1) -- its RIGHT end
                # (column c) over field (the C++ arc-existence rule:
                # the arc is created from the right element's spans),
                # its LEFT end over field or at a gate's own pol
                # terminals (verify's poly-jump rules 1/2 exactly)
                if c and t in self.field and c in self.field[t]:
                    left_gate = ((c - 1) in self.gate_terminal
                                 and t in self.gate_terminal[c - 1])
                    if (c - 1) in self.field[t] or left_gate:
                        self._add_arc(self._pol(t, c - 1), self._pol(t, c),
                                      POLY_ARC_COST)
                # M2 (the metal2 phase): the directional GridRouter
                # triple -- via at every node, M2 h, M2 v
                if self.metal2:
                    if c:
                        self._add_arc(self._node((_M2, t, c - 1)),
                                      self._node((_M2, t, c)), M2_H_COST)
                    if t:
                        self._add_arc(self._node((_M2, t - 1, c)),
                                      self._node((_M2, t, c)), M2_V_COST)
                    self._add_arc(self._met(t, c), self._node((_M2, t, c)),
                                  VIA_COST)

        # ---- gate terminals + contacts (autocell2.cpp:377-392) ----
        for (net_name, c) in sorted(self.gate_pol):
            net = self.net_by_name.get(net_name)
            if net is None or net not in self.nets:
                continue                 # a power gate net: no signal route
            for t in self.gate_pol[(net_name, c)]:
                self._claim(self._pol(t, c), net)
            for t in self.gate_tracks[(net_name, c)]:
                self._add_arc(self._pol(t, c), self._met(t, c),
                              GATE_CONTACT_COST)

        # ---- diffusion terminals (autocell2.cpp:340-370) ----
        # one DIFF node per (column, side) -- the shared junction of the
        # members abutting the edge (the C++'s 0-cost diff-diff bridge
        # of adjacent elements, one node here); the 20-cost contact
        # arcs span the drawn strips union the access track (the C++
        # span anchors at the terminal band -- our rail track).  The
        # rail-track MET point of every access is ALSO claimed as a
        # terminal: the vocabulary draws the access contact at the rail
        # band (verify demands the stripe cover it), so the router must
        # route there -- the C++'s contact position inside the span is
        # a drawing detail the RouteResult pins (route_grid's own model
        # claims exactly that point).
        for name in sorted(self.sig_diff):
            net = self.net_by_name.get(name)
            if net is None or net not in self.nets:
                continue
            by_edge = {}
            for c, dev in self.sig_diff[name]:
                by_edge.setdefault((c, dev.is_p), []).append(dev)
            for (c, is_p), devs in sorted(by_edge.items()):
                diff = self._node((_DIFF, c, is_p))
                self._claim(diff, net)
                ts = set()
                for dev in devs:
                    rail = self.row_track[device_rail(
                        dev, placement[dev].row)]
                    ts.add(rail)
                    self._claim(self._met(rail, c), net)
                    y0, y1 = self._dev_strip_y(dev)
                    ts.update(t for t in range(T)
                              if y0 <= self.trackY[t] <= y1)
                for t in sorted(ts):
                    self._add_arc(self._met(t, c), diff, DIFF_CONTACT_COST)

        # ---- the pin hubs (autocell2.cpp:58-62, :303-309, :384-385,
        # :457-459): one inoutCnt per column, arcs to every met track
        # (495 in the well-boundary corridor, 500 elsewhere), 0-cost to
        # every external net's pin ----
        for c in range(self.n_cols):
            n_end, n_ini = self._span_of(c, False)
            p_ini, p_end = self._span_of(c, True)
            hub = self._node((_HUB, c))
            for t in range(T):
                cost = HUB_CORRIDOR_COST if (t > n_ini and t < p_ini) \
                    else HUB_COST
                self._add_arc(hub, self._met(t, c), cost)
        for net in self.nets:
            if net.name not in ports:
                continue
            pin = self._node((_PIN, net.name))
            for c in range(self.n_cols):
                self._add_arc(pin, self._node((_HUB, c)), 0)
            # the C++ creates the pin FIRST (the inouts loop,
            # autocell2.cpp:287-300) -- the tree seed
            self._claim(pin, net)
            net.nodes.insert(0, net.nodes.pop())

        # ---- pre-built power stripes (the C++ routes gnd/vdd to the
        # same outcome: the rail chain + the access stubs; our rails are
        # drawn unconditionally -- module header, divergence 4) ----
        for net in self.power:
            is_vcc = net.name in VCC_NAMES
            for c, dev in sorted(self.pow_diff.get(net.name, ())):
                t_star = self.row_track[device_rail(dev,
                                                    placement[dev].row)]
                span = range(t_star, T) if is_vcc else range(0, t_star + 1)
                for t in span:
                    self._claim(self._met(t, c), net)
            net.tree = list(net.nodes)
            net.arcs_used = []

    def _span_of(self, c, is_p):
        """(lo, hi) track span of column c's is_p diffusion (the C++
        nDiffEnd/nDiffIni, pDiffIni/pDiffEnd); the virtual centre track
        when no strip covers the column (ASTRAN's lateral GAP elements,
        autocell2.cpp:304)."""
        span = self.spans[c][is_p]
        if span is None:
            return self.boundary_t, self.boundary_t
        return span

    def _prepare_hot(self):
        """The adjacency image the solver's hot loops read (a pure
        build-time image; the arc order -- the C++ list order -- is the
        tie-relevant part and is preserved)."""
        arcs = self.arcs
        adj = [None] * len(self.graph)
        for nid, node in enumerate(self.graph):
            adj[nid] = tuple((arcs[ai].n2 if arcs[ai].n1 == nid
                              else arcs[ai].n1, ai)
                             for ai in node.arcs)
        self._adj = adj
        self._m1_tab = [[self._id[(_MET, t, c)]
                         for c in range(self.n_cols)]
                        for t in range(self.n_tracks)]
        self._pol_tab = [[self._id[(_POL, t, c)]
                          for c in range(self.n_cols)]
                         for t in range(self.n_tracks)]
        self._m2_tab = ([[self._id[(_M2, t, c)]
                          for c in range(self.n_cols)]
                         for t in range(self.n_tracks)]) if self.metal2 \
            else None

    # ---------------- the GraphRouter solver ----------------

    def _bfs_route(self, net, tree, label, attempt, definitive=True,
                   strict=False):
        """GraphRouter::bfsRoute / bfsRoute2 (graphrouter.cpp:285-426).

        Multi-source Dijkstra from the current tree to the nearest
        not-yet-tree terminal.  ``strict`` selects bfsRoute2's push
        filter (nodes free or own); its calcCost always takes the
        attempt-1 form (the C++ hardcodes 1, graphrouter.cpp:393/:403)
        -- the caller passes attempt=1 for it.  Returns the path cost
        or -1.

        The C++ queue discipline: std::priority_queue by cost, the loop
        condition re-tested with the last-popped node (a stale
        target-net duplicate ends the search through it --
        graphrouter.cpp:308/:312); ties keep insertion order here.
        """
        graph = self.graph
        arcs = self.arcs
        adj = self._adj
        target = net.index
        visited = set(tree)
        father = {}
        heap = []
        seq = 0
        for nd in tree:
            heap.append((0, seq, nd, -1, -1))
            seq += 1
        heapq.heapify(heap)
        found = -1
        found_cost = 0
        while heap:
            cost, _s, node, fnode, farc = heapq.heappop(heap)
            if fnode != -1:
                if node in visited:
                    # stale duplicate: the C++ 'continue' re-tests the
                    # loop condition with this node
                    if graph[node].net == target:
                        found, found_cost = node, cost
                        break
                    continue
                visited.add(node)
                father[node] = (fnode, farc)
                if graph[node].net == target:
                    found, found_cost = node, cost
                    break
            # expand (graphrouter.cpp:317-337): the push filters are
            # !visited and no foreign terminal (checkConflict=false and
            # lockNet=-1 at every C++ call site); bfsRoute2 adds the
            # free-or-own filter
            for other, aid in adj[node]:
                if other in visited:
                    continue
                onode = graph[other]
                if onode.source and onode.net != target:
                    continue
                if strict and onode.net != -1 and onode.net != target:
                    continue
                onode_history = onode.history
                if attempt != 1:
                    onode_history *= (onode.nr_nets + 1)
                heap.append((cost + arcs[aid].cost + onode_history,
                             seq, other, node, aid))
                seq += 1
        if found == -1:
            return -1
        # the traceback (graphrouter.cpp:341-351 / :413-424)
        node = found
        while node in father:
            tree.append(node)
            if definitive:
                arcs[father[node][1]].label = label
                net.arcs_used.append(father[node][1])
                if strict:
                    graph[node].net = target
            node = father[node][0]
        return found_cost

    def _prim(self, net, nodes, label):
        """GraphRouter::prim (graphrouter.cpp:75-90): greedy tree cost."""
        tree = [nodes[0]]
        cost = 0
        for _ in range(len(nodes) - 1):
            ok = self._bfs_route(net, tree, label, 1, definitive=False,
                                 strict=True)
            if ok == -1:
                return -1
            cost += ok
        return cost

    def _add_steiner(self, net, label):
        """GraphRouter::addSteiner (graphrouter.cpp:185-227): greedily
        add unowned degree>2 nodes while they reduce the Prim cost."""
        candidates = [nid for nid in range(len(self.graph))
                      if self.graph[nid].net == -1
                      and len(self.graph[nid].arcs) > 2]
        best_cost = self._prim(net, list(net.nodes), label)
        added = 0
        improved = True
        while improved:
            improved = False
            best = None
            for cand in candidates:
                if self.graph[cand].net != -1:
                    continue
                self.graph[cand].source = 1
                self.graph[cand].net = net.index
                cost = self._prim(net, list(net.nodes) + [cand], label)
                self.graph[cand].net = -1
                self.graph[cand].source = 0
                if cost != -1 and cost < best_cost:
                    best, best_cost = cand, cost
            if best is not None:
                self._claim(best, net)
                self.graph[best].source = 2
                candidates.remove(best)
                added += 1
                improved = True
        return added

    def _snapshot(self):
        return ([(n.net, n.nr_nets, n.history, n.source)
                 for n in self.graph],
                [(net.nodes[:], net.tree[:], net.conflict,
                  net.arcs_used[:]) for net in self.nets],
                [arc.label for arc in self.arcs])

    def _restore(self, snap):
        nodes, nets, labels = snap
        for node, state in zip(self.graph, nodes):
            node.net, node.nr_nets, node.history, node.source = state
        for net, state in zip(self.nets, nets):
            net.nodes, net.tree, net.conflict, net.arcs_used = state
        for arc, label in zip(self.arcs, labels):
            arc.label = label

    def _optimize(self):
        """GraphRouter::optimize (graphrouter.cpp:230-282).

        The C++ re-routes every net overlap-free, adding Steiner points
        while they pay.  bfsRoute2's return is IGNORED there, so a net
        whose strict re-route fails silently keeps a partial,
        disconnected tree -- the port restores the conflict-free
        pre-optimize solution in that case (the one deviation from the
        letter of the C++; documented in the module header).
        """
        snap = self._snapshot()
        for node in self.graph:
            node.history = 0
        nr_steiners = 1
        while nr_steiners != 0:
            nr_steiners = 0
            self._label += 1
            for net in self.nets:
                for nid in net.tree:
                    node = self.graph[nid]
                    node.nr_nets -= 1
                    if not node.source:
                        node.net = -1
                net.tree = []
                net.arcs_used = []
                if len(net.nodes) > 2:
                    nr_steiners += self._add_steiner(net, self._label)
                net.tree = [net.nodes[0]]
                net.arcs_used = []
                for _ in range(len(net.nodes) - 1):
                    self._bfs_route(net, net.tree, self._label, 1,
                                    definitive=True, strict=True)
                for nid in net.tree:
                    self.graph[nid].nr_nets += 1
        for net in self.nets:
            if not set(net.nodes) <= set(net.tree):
                self._restore(snap)
                return False
        # the C++ ignores bfsRoute2's return, so its optimize can leave
        # PARTIAL and even OVERLAPPING trees (shared nodes draw
        # shorting metal); the port restores the conflict-free
        # pre-optimize solution whenever the sweeps damaged it -- the
        # one documented deviation from the letter of the C++
        for node in self.graph:
            if node.nr_nets > 1:
                self._restore(snap)
                return False
        return True

    def _reset(self):
        """GraphRouter::reset (graphrouter.cpp:533-549)."""
        for net in self.nets:
            net.nodes = [nid for nid in net.nodes
                         if self.graph[nid].source == 1]
            net.tree = []
            net.arcs_used = []
        for node in self.graph:
            node.history = 0
            if node.source == 2:
                node.source = 0
            if not node.source:
                node.net = -1
            node.nr_nets = 0
        for arc in self.arcs:
            arc.label = -1

    def route(self, max_attempts=MAX_ATTEMPTS, optimize=True,
              keep_history=False):
        """GraphRouter::routeNets (graphrouter.cpp:92-184) + AutoCell's
        optimize() && optimize() (autocell2.cpp:470-472).  True when the
        cell routed with zero node conflicts.

        ``keep_history``: the vocabulary feedback's re-entry -- the
        router keeps the congestion history across calls (the C++'s
        own mechanism: history prices the nodes the last conversion
        could not express, so the next routeNets trades them away).
        """
        if self._fail_note is not None:
            return False
        history = [n.history for n in self.graph] if keep_history             else None
        self._reset()
        if history is not None:
            for node, h in zip(self.graph, history):
                node.history = h
        attempt = 0
        ok = 0
        conflicts = 0
        min_conflict = 0
        cnt_conflict = -1
        solved = {}
        while True:
            attempt += 1
            self._label = attempt
            ok = 0
            # the nets loop (graphrouter.cpp:116-143): every net on
            # attempt 1, conflicted nets after; iteration in the port's
            # sorted-name order (the C++ walks its netlist map by net
            # id -- a SPICE-order artifact; invariant 9)
            for net in self.nets:
                if not (net.conflict or attempt == 1):
                    continue
                # rip up (graphrouter.cpp:120-125)
                for nid in net.tree:
                    node = self.graph[nid]
                    node.nr_nets -= 1
                    if (not node.source and node.net == net.index):
                        node.net = -1
                net.tree = [net.nodes[0]]
                net.arcs_used = []
                # grow to every terminal (graphrouter.cpp:128-134)
                ok = 0
                for _ in range(len(net.nodes) - 1):
                    ok = self._bfs_route(net, net.tree, attempt, attempt,
                                         definitive=True)
                    if ok == -1:
                        break
                # re-claim (graphrouter.cpp:135-139): the C++ sets net
                # UNCONDITIONALLY (it steals overlapping nodes back)
                for nid in net.tree:
                    node = self.graph[nid]
                    node.nr_nets += 1
                    node.net = net.index
                    if node.nr_nets > 1:
                        node.history += 1
                if ok == -1:
                    self._fail_note = ("impossible to find a path for net "
                                       "%s" % net.name)
                    break
            # the conflict pass (graphrouter.cpp:145-158) runs even on
            # the failure path (the do-while tests at the bottom)
            conflicts = 0
            for net in self.nets:
                ant = net.conflict
                net.conflict = False
                for nid in net.tree:
                    if self.graph[nid].nr_nets > 1:
                        conflicts += self.graph[nid].nr_nets
                        net.conflict = True
                if (not net.conflict and (ant or attempt == 1)):
                    solved[net.index] = attempt
            self.conflict_trace.append((
                attempt, conflicts,
                tuple(net.name for net in self.nets if net.conflict)))
            if conflicts < min_conflict or cnt_conflict == -1:
                cnt_conflict = 0
                min_conflict = conflicts
            else:
                cnt_conflict += 1
            if cnt_conflict > STALL_ATTEMPTS:
                break
            if ok == -1 or not conflicts or attempt >= max_attempts:
                break
        self.attempts_used = attempt
        # the solved-arc relabel (graphrouter.cpp:169-171): arcs of
        # solved nets whose label equals the net's solved attempt
        # become the final solution's arcs (finalNet = the last label)
        final_net = self._label
        for arc in self.arcs:
            owner = self.graph[arc.n1].net
            if arc.label == solved.get(owner, 0):
                arc.label = final_net
        if ok == -1 or conflicts:
            if ok != -1 and conflicts and self._fail_note is None:
                best = min(self.conflict_trace,
                           key=lambda t: (t[1], t[0]))
                self._fail_note = (
                    "no conflict-free routing after %d attempts (best %d "
                    "conflicts at attempt %d; unresolved: %s)"
                    % (attempt, best[1], best[0],
                       ", ".join(best[2]) if best[2] else "-"))
            return False
        if optimize:
            self._optimize()
            self._optimize()
        return True

    # ---------------- the RouteResult conversion ----------------

    def _occupancy(self, net):
        """The net's tree point sets by layer (MET/M2/POL), dropping the
        kinds that draw no geometry (DIFF/HUB/PIN)."""
        m1 = set()
        m2 = set()
        pol = set()
        for nid in net.tree:
            kind = self.graph[nid].kind
            if kind[0] == _MET:
                m1.add((kind[1], kind[2]))
            elif kind[0] == _M2:
                m2.add((kind[1], kind[2]))
            elif kind[0] == _POL:
                pol.add((kind[1], kind[2]))
        return m1, m2, pol

    def _net_name(self, index):
        net = self.net_index.get(index)
        return net.name if net is not None else "?%d" % index

    def _m2_bridges(self, tracks):
        """Whether one column's M2 track set contains a contiguous run
        covering tracks on both sides of the well boundary (route_grid's
        _m2_bridges_slots: the second N<->P crossover)."""
        m2t = sorted(tracks)
        if not m2t:
            return False
        start = prev = m2t[0]
        for t in m2t[1:] + [None]:
            if t == prev + 1:
                prev = t
                continue
            if start < prev and start <= self.boundary_t <= prev:
                return True
            if t is None:
                break
            start = prev = t
        return False

    def build_result(self, dual_merge=False):
        """Convert the routed trees to a RouteResult (the vocabulary
        work), ARC by ARC -- the C++ draws its solution arc by arc, and
        the tree's node set alone cannot distinguish a used wire from
        two terminals that merely sit in adjacent columns.

        The vocabulary quantization the conversion bridges (route_grid's
        established conventions, all checkable by verify_cell):

        - a vertical M1 run is ONE interval per half-column: the run
          comes from the used vertical met arcs, filled contiguously
          only where the vocabulary demands it (an access column's rail
          coverage, or the dual merge) -- two disjoint runs of one net
          in a half are the honest inexpressible case;
        - a used horizontal poly arc spans BOTH its endpoint slots'
          centres (the wire between adjacent slots' crossing points),
          so it emits the pj of its left slot and, when its right
          endpoint is a gate terminal, the ARRIVAL merge segment of the
          right slot -- that is how a wire arriving at a gate from the
          left still touches the stripe (which sits at the slot
          centre);
        - every maximal emitted poly run must contain a margin-legal
          gate crossing (verify's anchored-run rule): an unanchorable
          run is dropped and the connectivity is verify's verdict;
        - every gate needs one margin-legal crossing: a used contact
          arc (an M1 segment with a contact square) or a poly merge
          segment at a drawable track;
        - one hseg slot carries one net and one layer: a same-layer
          cross-net conflict is an honest fail, a cross-layer conflict
          drops the lower-priority segment (the M1 stays; the net's
          connectivity is verify's verdict).
        """
        if self._fail_note is not None:
            return self.failed_result()
        W = self.width_cols
        arcs = self.arcs
        graph = self.graph
        m1_tab, pol_tab = self._m1_tab, self._pol_tab
        self._collisions = set()    # nodes the vocabulary could not
                                    # express -- the feedback bumps them
        # the access rail tracks per (net, column) + the power access
        # columns (the stripe-qualification rule's terminal set)
        access_rail = {}
        for name, pts in self.sig_diff.items():
            for c, dev in pts:
                access_rail.setdefault((name, c), set()).add(
                    self.row_track[device_rail(
                        dev, self.placement[dev].row)])
        for name, pts in self.pow_diff.items():
            for c, _dev in pts:
                access_rail.setdefault((name, c), set())

        # ---- pass 1: classify every net's used arcs ----
        used = {}
        for net in self.nets + self.power:
            m1_h = set()            # (t, c): horizontal met arc
            m1_v = set()            # (t, c): vertical met arc covering
                                    # tracks {t-1, t} at column c
            m2_h = set()
            m2_v = set()
            via_pts = set()         # (t, c)
            pol_h = set()           # (t, c): horizontal poly arc
            contact = set()         # (t, c): gate-column pol<->met
            for aid in set(net.arcs_used):
                k1 = graph[arcs[aid].n1].kind
                k2 = graph[arcs[aid].n2].kind
                pair = (k1, k2) if k1 <= k2 else (k2, k1)
                if pair[0][0] == _MET and pair[1][0] == _MET:
                    if pair[0][2] == pair[1][2]:
                        m1_v.add((max(pair[0][1], pair[1][1]),
                                  pair[0][2]))
                    else:
                        m1_h.add((pair[0][1], min(pair[0][2],
                                                  pair[1][2])))
                elif pair[0][0] == _M2 and pair[1][0] == _M2:
                    if pair[0][2] == pair[1][2]:
                        m2_v.add((max(pair[0][1], pair[1][1]),
                                  pair[0][2]))
                    else:
                        m2_h.add((pair[0][1], min(pair[0][2],
                                                  pair[1][2])))
                elif pair[0][0] == _MET and pair[1][0] == _M2:
                    via_pts.add((pair[0][1], pair[0][2]))
                elif pair[0][0] == _POL and pair[1][0] == _POL:
                    if pair[0][2] != pair[1][2]:
                        pol_h.add((pair[0][1], min(pair[0][2],
                                                   pair[1][2])))
                    # same column: the vertical chain inside a gate
                    # stripe -- the drawn stripe itself (subsumed by
                    # gds_cells' gate poly, no separate geometry)
                elif pair[0][0] == _MET and pair[1][0] == _POL:
                    contact.add((pair[0][1], pair[0][2]))
                # HUB/PIN/DIFF arcs draw no route geometry (the pin is
                # a label; the diffusion contact is the geometry pass's
                # own square; the hub hop is pure graph)
            used[net.index] = (m1_h, m1_v, m2_h, m2_v, via_pts, pol_h,
                               contact)

        # the drawn-collision sets: a foreign met arc endpoint draws
        # (an hseg or a stripe piece) and blocks fills over it; a
        # foreign poly SEGMENT blocks same-layer poly adjacency (a
        # foreign gate terminal alone draws nothing at the point -- the
        # merge segment ends at the slot edge, half a pitch clear)
        m1_users = {}
        poly_pairs = {}
        for net in self.nets + self.power:
            (m1_h, m1_v, _m2_h, _m2_v, _via, pol_h, contact) = \
                used[net.index]
            for (t, c) in m1_h:
                m1_users.setdefault((t, c), set()).add(net.index)
                m1_users.setdefault((t, c + 1), set()).add(net.index)
            for (t, c) in m1_v:
                m1_users.setdefault((t - 1, c), set()).add(net.index)
                m1_users.setdefault((t, c), set()).add(net.index)
            for (t, c) in contact:
                m1_users.setdefault((t, c), set()).add(net.index)
            if net in self.power:
                # the pre-built power stripes' claimed points are drawn
                # occupancy: a fill over one would short the rail stub
                for nid in net.nodes:
                    kind = graph[nid].kind
                    if kind[0] == _MET:
                        m1_users.setdefault((kind[1], kind[2]),
                                            set()).add(net.index)
            else:
                # the signal nets' claimed rail points are drawn
                # occupancy too (the access stripes)
                for nid in net.nodes:
                    kind = graph[nid].kind
                    if kind[0] == _MET:
                        m1_users.setdefault((kind[1], kind[2]),
                                            set()).add(net.index)
            for (t, c) in pol_h:
                poly_pairs.setdefault((t, c), set()).add(net.index)

        def met_free(t, c, net):
            users = m1_users.get((t, c))
            return users is None or users == {net.index}

        def poly_free(t, c, net):
            for slot in ((t, c - 1), (t, c), (t, c + 1)):
                users = poly_pairs.get(slot)
                if users is not None and users - {net.index}:
                    return False
            return True

        def m1_joinable(t, c, name):
            # an M1 segment may not touch the SAME net's poly segment
            # (verify: a poly<->metal layer switch has no contact); an
            # M2 neighbour is fine -- the adjacent-segment via covers it
            for side in (c - 1, c + 1):
                if hseg.get((t, side)) == name and pj.get((t, side)):
                    return False
            return True

        def poly_joinable(t, c, name):
            for side in (c - 1, c + 1):
                if hseg.get((t, side)) == name and not pj.get((t, side)):
                    return False
            return True

        hseg = {}
        pj = {}
        m2flag = {}
        via = {}
        m2v = {}
        m2via = {}
        owner_n = [None] * (W + 1)
        owner_p = [None] * (W + 1)
        lo_n = [0] * (W + 1)
        hi_n = [0] * (W + 1)
        lo_p = [self.bar_levels - 1] * (W + 1)
        hi_p = [self.bar_levels - 1] * (W + 1)
        reachB_n = [False] * (W + 1)
        reachB_p = [False] * (W + 1)
        # multi-interval half-column stripes: the 9-bar representation
        # carries ONE interval per half (owner + lo/hi); the C++ has no
        # stripe concept at the routing level (graphrouter.h:33-44 -- a
        # flat node graph, per-node ownership, LP-enforced S1M1M1
        # spacing at draw time).  extra_stripes carries the ADDITIONAL
        # intervals, each >=1 free track from every other interval in
        # the same half-column (the quantized S1M1M1).
        extra_stripes = []

        def _half_intervals(c, is_n):
            out = []
            if is_n and owner_n[c] is not None:
                out.append((lo_n[c], hi_n[c]))
            if not is_n and owner_p[c] is not None:
                out.append((lo_p[c], hi_p[c]))
            out.extend((elo, ehi) for (ec, _en, elo, ehi, es)
                       in extra_stripes if ec == c and es == is_n)
            return out

        def _try_extra(c, net, slo, shi, is_n, side):
            """A second (or later) interval in a half-column: spaced
            >=1 free track from every existing interval (the C++'s
            S1M1M1 quantized), or an honest fail."""
            for (plo, phi) in _half_intervals(c, is_n):
                if not (shi + 2 <= plo or phi + 2 <= slo):
                    for t in side:
                        self._collisions.add(m1_tab[t][c])
                    return False
            extra_stripes.append(
                (c, net.name, slo, shi, "N" if is_n else "P"))
            return True

        def emit_seg(t, c, net, poly=False, m2=False):
            """Claim the hseg slot (t, c).  Returns 'ok', 'skip' (a
            cross-layer conflict: the other net's different-layer
            segment keeps the slot, ours is dropped) or 'fail' (a
            same-layer conflict -- a real short)."""
            prev = hseg.get((t, c))
            if prev is not None and prev != net.name:
                if bool(pj.get((t, c))) == bool(poly) \
                        and bool(m2flag.get((t, c))) == bool(m2):
                    return "fail"
                return "skip"
            hseg[(t, c)] = net.name
            pj.pop((t, c), None)
            m2flag.pop((t, c), None)
            if poly:
                pj[(t, c)] = True
                poly_pairs.setdefault((t, c), set()).add(net.index)
            elif m2:
                m2flag[(t, c)] = True
            else:
                m1_users.setdefault((t, c), set()).add(net.index)
                m1_users.setdefault((t, c + 1), set()).add(net.index)
            return "ok"

        # ---- pass 2: stripes, segments, vias per net ----
        for net in self.nets + self.power:
            (m1_h, m1_v, m2_h, m2_v, via_pts, pol_h, contact) = \
                used[net.index]
            m1pts = set()
            for t, c in m1_v:
                m1pts.update(((t - 1, c), (t, c)))
            for t, c in m1_h:
                m1pts.update(((t, c), (t, c + 1)))
            for t, c in contact:
                m1pts.add((t, c))
            # 1. the vertical runs: the used vertical met arcs' track
            #    pairs, per column, merged per half where the
            #    vocabulary demands it (the access rail coverage; the
            #    dual merge on the retry pass)
            runs_by_col = {}
            # the claimed rail points (the access terminals the tree had
            # to reach) are stripe members even where the tree used no
            # vertical arc -- the access stripe is the vocabulary's own
            # demand, not a routing choice
            rail_pts = {}
            for nid in net.nodes:
                kind = graph[nid].kind
                if kind[0] == _MET:
                    rail_pts.setdefault(kind[2], set()).add(kind[1])
            for c in range(W + 1):
                tracks = set(rail_pts.get(c, ()))
                for (t, cc) in m1_v:
                    if cc == c:
                        tracks.update((t - 1, t))
                if not tracks:
                    continue
                runs = []
                start = prev = None
                for t in sorted(tracks):
                    if start is None:
                        start = t
                    elif t != prev + 1:
                        runs.append((start, prev))
                        start = t
                    prev = t
                if start is not None:
                    runs.append((start, prev))
                is_access = (net.name, c) in access_rail
                if is_access:
                    rails = access_rail.get((net.name, c), ())
                    # the well-boundary track belongs to the P half here:
                    # assigning it to both (route_grid's stripe-split
                    # convention) merges an N access with a P-side
                    # point one track above the boundary and fills the
                    # gap through a foreign crossing; the emission's
                    # own split still covers it in both stripes when
                    # the run actually spans it
                    need_n = {t for t in tracks
                              if t < self.boundary_t}
                    need_n.update(r for r in rails
                                  if r < self.boundary_t)
                    need_p = {t for t in tracks
                              if t >= self.boundary_t}
                    need_p.update(r for r in rails
                                  if r >= self.boundary_t)
                    runs = [r for r in runs
                            if r[0] < self.boundary_t < r[1]]
                    if need_n:
                        runs.append((min(need_n), max(need_n)))
                    if need_p:
                        runs.append((min(need_p), max(need_p)))
                elif dual_merge and len(runs) > 1:
                    n_side = [r for r in runs if r[1] <= self.boundary_t]
                    p_side = [r for r in runs if r[0] >= self.boundary_t]
                    runs = [r for r in runs
                            if r[0] < self.boundary_t < r[1]]
                    if n_side:
                        runs.append((min(r[0] for r in n_side),
                                     self.boundary_t))
                    if p_side:
                        runs.append((self.boundary_t,
                                     max(r[1] for r in p_side)))
                runs_by_col[c] = runs
                # the fills: make each run's interval solid
                for lo, hi in runs:
                    for t in range(lo, hi + 1):
                        if (t, c) in m1pts:
                            continue
                        if not met_free(t, c, net):
                            users = m1_users[(t, c)] - {net.index}
                            self._collisions.add(m1_tab[t][c])
                            return self._fail(
                                "vocabulary: %s's stripe fill at column %d "
                                "track %d collides with %s"
                                % (net.name, c, t,
                                   self._net_name(max(users))))
                        m1pts.add((t, c))
                        m1_users.setdefault((t, c), set()).add(net.index)
            # 2. emit the stripes (one per slot per run, only when the
            #    run qualifies -- len >= 2 or an access column; power
            #    reaches the bar-domain ends, verify's power rule)
            for c, runs in sorted(runs_by_col.items()):
                is_access = (net.name, c) in access_rail
                for lo, hi in runs:
                    side_n = [t for t in range(lo, hi + 1)
                              if t <= self.boundary_t]
                    side_p = [t for t in range(lo, hi + 1)
                              if t >= self.boundary_t]
                    for side, is_n in ((side_n, True), (side_p, False)):
                        if not side or (len(side) < 2 and not is_access):
                            continue
                        # a foreign segment endpoint on a covered track
                        # is a crossing short (verify's rule): reject and
                        # record both sides for the feedback
                        clash = None
                        for t in side:
                            users = m1_users.get((t, c))
                            if users and users - {net.index}:
                                clash = max(users - {net.index})
                                break
                        if clash is not None:
                            for t in side:
                                self._collisions.add(m1_tab[t][c])
                            return self._fail(
                                "vocabulary: %s's stripe at column %d "
                                "covers %s's segment endpoint"
                                % (net.name, c, self._net_name(clash)))
                        if is_n:
                            slo = 0 if net.name in GND_NAMES else side[0] + 1
                            shi = side[-1] + 1
                            prev = owner_n[c]
                            if prev is not None and prev != net.name:
                                # the C++ has no single-stripe rule --
                                # a second net's interval is legal when
                                # spaced >=1 free track (S1M1M1)
                                if not _try_extra(c, net, slo, shi,
                                                  True, side):
                                    return self._fail(
                                        "vocabulary: %s's extra N stripe "
                                        "at column %d violates the M1-M1 "
                                        "spacing against the existing "
                                        "interval" % (net.name, c))
                                reachB_n[c] = reachB_n[c] or (
                                    shi == self.boundary_t + 1)
                            elif prev == net.name:
                                # the net's own second run at this
                                # column MERGES into the one interval
                                # (the vocabulary's single stripe per
                                # half-column) -- the fused gap draws
                                # metal, so every added track must be
                                # free (the fill's own rule)
                                for t in range(min(lo_n[c], slo),
                                               max(hi_n[c], shi) + 1):
                                    if (t, c) in m1pts:
                                        continue
                                    if not met_free(t, c, net):
                                        users = m1_users[(t, c)] \
                                            - {net.index}
                                        self._collisions.add(
                                            m1_tab[t][c])
                                        return self._fail(
                                            "vocabulary: %s's stripe "
                                            "merge at column %d track %d "
                                            "collides with %s"
                                            % (net.name, c, t,
                                               self._net_name(
                                                   max(users))))
                                lo_n[c] = min(lo_n[c], slo)
                                hi_n[c] = max(hi_n[c], shi)
                            else:
                                owner_n[c], lo_n[c], hi_n[c] = \
                                    net.name, slo, shi
                            reachB_n[c] = hi_n[c] == self.boundary_t + 1
                        else:
                            slo = side[0] + 1
                            shi = self.bar_levels - 1 \
                                if net.name in VCC_NAMES else side[-1] + 1
                            prev = owner_p[c]
                            if prev is not None and prev != net.name:
                                if not _try_extra(c, net, slo, shi,
                                                  False, side):
                                    return self._fail(
                                        "vocabulary: %s's extra P stripe "
                                        "at column %d violates the M1-M1 "
                                        "spacing against the existing "
                                        "interval" % (net.name, c))
                                reachB_p[c] = reachB_p[c] or (
                                    slo == self.boundary_t + 1)
                            elif prev == net.name:
                                for t in range(min(lo_p[c], slo),
                                               max(hi_p[c], shi) + 1):
                                    if (t, c) in m1pts:
                                        continue
                                    if not met_free(t, c, net):
                                        users = m1_users[(t, c)] \
                                            - {net.index}
                                        self._collisions.add(
                                            m1_tab[t][c])
                                        return self._fail(
                                            "vocabulary: %s's stripe "
                                            "merge at column %d track %d "
                                            "collides with %s"
                                            % (net.name, c, t,
                                               self._net_name(
                                                   max(users))))
                                lo_p[c] = min(lo_p[c], slo)
                                hi_p[c] = max(hi_p[c], shi)
                            else:
                                owner_p[c], lo_p[c], hi_p[c] = \
                                    net.name, slo, shi
                            reachB_p[c] = lo_p[c] == self.boundary_t + 1
            # the power nets' pre-built stripes (their static claims --
            # the rails are drawn unconditionally; module header,
            # divergence 4)
            if net in self.power:
                for c in range(W + 1):
                    claimed = set()
                    for nid in net.nodes:
                        kind = graph[nid].kind
                        if kind[0] == _MET and kind[2] == c:
                            claimed.add(kind[1])
                    if not claimed:
                        continue
                    is_access = (net.name, c) in access_rail
                    for side, is_n in (
                            (sorted(t for t in claimed
                                    if t <= self.boundary_t), True),
                            (sorted(t for t in claimed
                                    if t >= self.boundary_t), False)):
                        if not side:
                            continue
                        if is_n:
                            slo = 0 if net.name in GND_NAMES else side[0] + 1
                            shi = side[-1] + 1
                            prev = owner_n[c]
                            if prev is not None and prev != net.name:
                                if not _try_extra(c, net, slo, shi,
                                                  True, side):
                                    return self._fail(
                                        "vocabulary: %s's extra N stripe "
                                        "at column %d violates the M1-M1 "
                                        "spacing" % (net.name, c))
                            else:
                                owner_n[c], lo_n[c], hi_n[c] = \
                                    net.name, slo, shi
                            reachB_n[c] = (reachB_n[c]
                                           or shi == self.boundary_t + 1)
                        else:
                            slo = side[0] + 1
                            shi = self.bar_levels - 1 \
                                if net.name in VCC_NAMES else side[-1] + 1
                            prev = owner_p[c]
                            if prev is not None and prev != net.name:
                                if not _try_extra(c, net, slo, shi,
                                                  False, side):
                                    return self._fail(
                                        "vocabulary: %s's extra P stripe "
                                        "at column %d violates the M1-M1 "
                                        "spacing" % (net.name, c))
                            else:
                                owner_p[c], lo_p[c], hi_p[c] = \
                                    net.name, slo, shi
                            reachB_p[c] = (reachB_p[c]
                                           or slo == self.boundary_t + 1)
                continue
            # 3. the M1 horizontal segments (the used wires)
            own_slots = set()
            for t, c in sorted(m1_h):
                st = emit_seg(t, c, net)
                if st == "fail":
                    return self._fail(
                        "vocabulary: M1 segment slot (%d, %d) contested "
                        "between %s and %s" % (t, c, hseg[(t, c)],
                                               net.name))
                if st == "ok":
                    own_slots.add((t, c))
            # the gate-contact crossings (the used contact arcs): the
            # M1 stub spans the gate's slot rightward (the contact
            # square sits at the slot centre) -- solidify the right
            # span when the route only continued left
            for t, c in sorted(contact):
                if hseg.get((t, c)) == net.name and not pj.get((t, c)):
                    continue                     # already crossed
                if c + 1 > W:
                    continue
                if ((t, c + 1) not in m1pts
                        and not met_free(t, c + 1, net)):
                    continue
                if not m1_joinable(t, c, net.name):
                    continue
                st = emit_seg(t, c, net)
                if st == "fail":
                    return self._fail(
                        "vocabulary: M1 crossing slot (%d, %d) contested "
                        "between %s and %s" % (t, c, hseg[(t, c)],
                                               net.name))
                if st == "ok":
                    own_slots.add((t, c))
            # 4. the M2 segments, spans and vias
            m2own = set()
            for t, c in sorted(m2_h):
                if (t, c) in own_slots:
                    continue
                st = emit_seg(t, c, net, m2=True)
                if st == "fail":
                    return self._fail(
                        "vocabulary: M2 segment slot (%d, %d) contested "
                        "between %s and %s" % (t, c, hseg[(t, c)],
                                               net.name))
                if st == "ok":
                    m2own.add((t, c))
                    if hseg.get((t, c - 1)) == net.name \
                            and not pj.get((t, c - 1)):
                        via[(t, c)] = True
                    if c + 1 <= W and hseg.get((t, c + 1)) == net.name \
                            and not pj.get((t, c + 1)):
                        via[(t, c + 1)] = True
            m2cols = {}
            for t, c in m2_v:
                m2cols.setdefault(c, set()).update((t - 1, t))
            for t, c in via_pts:
                m2cols.setdefault(c, set()).add(t)
            for c in sorted(m2cols):
                tracks = sorted(m2cols[c])
                start = prev = None
                runs = []
                for t in tracks:
                    if start is None:
                        start = t
                    elif t != prev + 1:
                        runs.append((start, prev))
                        start = t
                    prev = t
                if start is not None:
                    runs.append((start, prev))
                for t1, t2 in runs:
                    if t2 > t1:
                        m2v[(c, t1, t2)] = net.name
            for t, c in sorted(via_pts):
                if (t, c) not in m1pts:
                    continue         # the M1 side was dropped; verify
                                     # judges the M2 leaf's fate
                both_side = (
                    c > 0 and c < W
                    and (((t, c - 1) in m1_h and (t, c + 1) in m2_h)
                         or ((t, c - 1) in m2_h and (t, c + 1) in m1_h)))
                if both_side:
                    via[(t, c)] = True
                    continue
                m1_real = (
                    (t, c - 1) in m1_h or (t, c + 1) in m1_h
                    or (t, c) in m1_v or (t + 1, c) in m1_v
                    or (t, c) in contact)
                m2_real = (
                    (t, c - 1) in m2_h or (t, c + 1) in m2_h
                    or (t, c) in m2_v or (t + 1, c) in m2_v)
                if m1_real and m2_real:
                    m2via[(t, c)] = True
                # else: a dead via side (the C++ tree used the via arc
                # with an M2 leaf our vocabulary cannot draw) -- drop
                # the junction, the net's connectivity is verify's
                # verdict
            # 5. the poly runs: the used poly arcs' slots + the gate
            #    arrival merges, grouped per track; a run is emitted
            #    only when it contains a margin-legal gate crossing
            #    (verify's anchored-run rule)
            segs = set()
            for (t, c) in pol_h:
                segs.add((t, c))
                if ((c + 1) in self.gate_terminal
                        and self.gate_terminal[c + 1].get(t) == net.name):
                    segs.add((t, c + 1))       # the arrival merge
            anchored = set(
                (t, c) for (t, c) in segs
                if c in self.gate_nets_at.get(net.name, ())
                and t in self.gate_tracks.get((net.name, c), ()))
            runs_by_track = {}
            for (t, c) in segs:
                runs_by_track.setdefault(t, []).append(c)
            keep = set()
            for t, cs in runs_by_track.items():
                cs = sorted(cs)
                start = prev = None
                for c in cs + [None]:
                    if c is not None and (prev is None
                                          or c == prev + 1):
                        prev = c
                        if start is None:
                            start = c
                        continue
                    if start is not None:
                        if any((t, cc) in anchored
                               for cc in range(start, prev + 1)):
                            keep.update((t, cc)
                                        for cc in range(start, prev + 1))
                        else:
                            # the run has no margin-legal gate touch:
                            # the vocabulary rejects this wire -- record
                            # its nodes so the feedback re-routes it
                            for cc in range(start, prev + 1):
                                self._collisions.add(self._pol_tab[t][cc])
                        start = prev = None
                    if c is None:
                        break
                    start = prev = c
            for slot in sorted(keep):
                if slot in own_slots or slot in m2own:
                    continue
                if not poly_free(slot[0], slot[1], net):
                    continue
                if not poly_joinable(slot[0], slot[1], net.name):
                    continue
                if (slot[1] + 1 > W
                        or (slot[1] + 1) not in self.field.get(
                            slot[0], ())):
                    continue    # verify's field rule (pj rule 1)
                st = emit_seg(slot[0], slot[1], net, poly=True)
                if st == "fail":
                    return self._fail(
                        "vocabulary: poly segment slot %s contested "
                        "between %s and %s" % (slot, hseg[slot],
                                               net.name))

        # ---- pass 3: every gate needs one margin-legal crossing ----
        for (gnet, c) in sorted(self.gate_pol):
            net = self.net_by_name.get(gnet)
            if net is None or net not in self.nets:
                continue
            (m1_h, m1_v, m2_h, m2_v, via_pts, pol_h, contact) = \
                used[net.index]
            crossed = False
            # an already-emitted right-spanning segment at a drawable
            # track
            for t in self.gate_tracks[(gnet, c)]:
                if hseg.get((t, c)) == gnet and not m2flag.get((t, c)):
                    crossed = True
                    break
            if not crossed:
                # the poly merge: emit a merge segment at a drawable
                # track (the dangling left endpoint is a pure marker;
                # the drawn segment covers the stripe's centre, and the
                # stripe joins the net's other geometry)
                for t in self.gate_tracks[(gnet, c)]:
                    if c + 1 > W or (c + 1) not in self.field.get(t, ()):
                        continue
                    if not poly_free(t, c, net):
                        continue
                    if not poly_joinable(t, c, gnet):
                        continue
                    st = emit_seg(t, c, net, poly=True)
                    if st == "fail":
                        return self._fail(
                            "vocabulary: poly merge slot (%d, %d) contested "
                            "between %s and %s" % (t, c, hseg[(t, c)], gnet))
                    if st == "ok":
                        crossed = True
                        break
            if not crossed:
                # the M1 contact merge: draw the contact anyway -- the
                # M1 stub plus the contact square join the stripe, and
                # the stripe joins the net's other geometry
                for t in self.gate_tracks[(gnet, c)]:
                    if c + 1 > W:
                        continue
                    if not (met_free(t, c, net) and met_free(t, c + 1, net)):
                        continue
                    if not m1_joinable(t, c, gnet):
                        continue
                    st = emit_seg(t, c, net)
                    if st == "fail":
                        return self._fail(
                            "vocabulary: M1 contact merge slot (%d, %d) "
                            "contested between %s and %s"
                            % (t, c, hseg[(t, c)], gnet))
                    if st == "ok":
                        crossed = True
                        break
            if not crossed:
                for t in self.gate_pol[(gnet, c)]:
                    self._collisions.add(self._pol_tab[t][c])
                return self._fail(
                    "vocabulary: gate %s@%d has no realizable crossing"
                    % (gnet, c))

        # ---- pass 4: the gate-join repair.  A net's gate stripes are
        # separate conductors; the tree tied them with wires the
        # vocabulary may have dropped (an unanchored poly run) or
        # half-expressed (a departure merge whose arrival was blocked).
        # When the emitted margin crossings do not chain the net's gate
        # columns, re-cross them all with M1 stubs at ONE common free
        # drawable track -- adjacent stubs touch, so the stripes chain
        # through the contacts (exactly how the exact model ties a
        # multi-gate net).
        for net in self.nets:
            gates = sorted(self.gate_nets_at.get(net.name, ()))
            if len(gates) < 2:
                continue
            # the margin crossings per gate column
            crossings = {}
            for c in gates:
                crossings[c] = set(
                    t for t in self.gate_tracks.get((net.name, c), ())
                    if hseg.get((t, c)) == net.name)
            # union-find over the gate columns; two adjacent columns
            # join when one track has margin crossings at both
            parent = {c: c for c in gates}

            def find(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            for c in gates:
                for c2 in gates:
                    if c2 <= c or find(c) == find(c2):
                        continue
                    if c2 != c + 1:
                        continue
                    if any(t in crossings[c] and t in crossings[c2]
                           for t in range(self.n_tracks)):
                        parent[find(c)] = find(c2)
            # the repair: chain the components with M1 wires -- a wire
            # at one margin track common to both columns, spanning every
            # slot between them (the intermediate gate stripes of other
            # nets are layers apart; the free-point checks keep it short-
            # safe).  Deterministic: the nearest component pair, then
            # the smallest track.
            for _pass in range(len(gates)):
                roots = {find(c) for c in gates}
                if len(roots) == 1:
                    break
                # one join per pass: try every unjoined ordered pair,
                # first the same-track wire, then the L-join (the track
                # change through a vertical stripe); the nearest pair
                # and the smallest tracks win
                joined = None
                for c1 in gates:
                    for c2 in gates:
                        if find(c1) == find(c2) or c2 <= c1:
                            continue
                        tracks = sorted(
                            set(self.gate_tracks.get((net.name, c1), ()))
                            & set(self.gate_tracks.get((net.name, c2), ())))
                        for t in tracks:
                            pts = range(c1, c2 + 2)
                            if not all(met_free(t, cc, net) for cc in pts):
                                continue
                            slots = range(c1, c2 + 1)
                            if any(
                                    hseg.get((t, cc)) not in (None,
                                                              net.name)
                                    or (pj.get((t, cc))
                                        and hseg.get((t, cc)) != net.name)
                                    for cc in slots):
                                continue    # a FOREIGN slot mid-wire
                                            # would short; the net's own
                                            # poly merge is replaced by
                                            # the M1 wire (emit_seg
                                            # clears the poly flag)
                            if not all(m1_joinable(t, cc, net.name)
                                       for cc in slots):
                                continue
                            joined = ("wire", c1, t, c2)
                            break
                        if joined is not None:
                            break
                    if joined is not None:
                        break
                if joined is None:
                    # the L-join: a horizontal wire at t1 from c1, a
                    # vertical M1 run at column c2 down/up to t2, and
                    # the crossing stub at (t2, c2) -- two drawable
                    # bands that do not overlap, tied through a free
                    # stripe column
                    for c1 in gates:
                        for c2 in gates:
                            if find(c1) == find(c2) or c2 <= c1:
                                continue
                            lbest = None
                            for t1 in sorted(set(self.gate_tracks.get(
                                    (net.name, c1), ()))):
                                hpts = range(c1, c2 + 1)
                                if not all(met_free(t1, cc, net)
                                           for cc in hpts):
                                    continue
                                hslots = range(c1, c2)
                                if any(hseg.get((t1, cc))
                                       not in (None, net.name)
                                       or (pj.get((t1, cc))
                                           and hseg.get((t1, cc))
                                           != net.name)
                                       for cc in hslots):
                                    continue
                                for t2 in sorted(set(self.gate_tracks.get(
                                        (net.name, c2), ()))):
                                    lo, hi = min(t1, t2), max(t1, t2)
                                    if not all(met_free(tt, c2, net)
                                               for tt in range(lo, hi + 1)):
                                        continue
                                    if not met_free(t2, c2 + 1, net):
                                        continue
                                    if (hseg.get((t2, c2))
                                            not in (None, net.name)
                                            or (pj.get((t2, c2))
                                                and hseg.get((t2, c2))
                                                != net.name)):
                                        continue
                                    if not m1_joinable(t2, c2, net.name):
                                        continue
                                    bad = False
                                    for tt in range(lo, hi + 1):
                                        if tt <= self.boundary_t:
                                            if owner_n[c2] not in (None,
                                                                   net.name):
                                                bad = True
                                        else:
                                            if owner_p[c2] not in (None,
                                                                   net.name):
                                                bad = True
                                    if bad:
                                        continue
                                    lbest = (t1, t2)
                                    break
                                if lbest is not None:
                                    break
                            if lbest is not None:
                                joined = ("ljoin", c1, lbest, c2)
                                break
                        if joined is not None:
                            break
                if joined is None:
                    break               # no join at all: verify reports
                                        # the honest disconnect
                kindj, c1, payload, c2 = joined
                if kindj == "wire":
                    t = payload
                    for cc in range(c1, c2 + 1):
                        st = emit_seg(t, cc, net)
                        if st == "fail":
                            return self._fail(
                                "vocabulary: gate-join slot (%d, %d) "
                                "contested between %s and %s"
                                % (t, cc, hseg[(t, cc)], net.name))
                else:
                    t1, t2 = payload
                    for cc in range(c1, c2):
                        st = emit_seg(t1, cc, net)
                        if st == "fail":
                            return self._fail(
                                "vocabulary: gate-join slot (%d, %d) "
                                "contested between %s and %s"
                                % (t1, cc, hseg[(t1, cc)], net.name))
                    st = emit_seg(t2, c2, net)
                    if st == "fail":
                        return self._fail(
                            "vocabulary: gate-join slot (%d, %d) contested "
                            "between %s and %s" % (t2, c2, hseg[(t2, c2)],
                                                   net.name))
                    lo, hi = min(t1, t2), max(t1, t2)
                    for tt in range(lo, hi + 1):
                        m1_users.setdefault((tt, c2), set()).add(net.index)
                    side_n = [tt for tt in range(lo, hi + 1)
                              if tt <= self.boundary_t]
                    side_p = [tt for tt in range(lo, hi + 1)
                              if tt >= self.boundary_t]
                    if side_n:
                        slo = side_n[0] + 1
                        shi = side_n[-1] + 1
                        if owner_n[c2] is None:
                            owner_n[c2], lo_n[c2], hi_n[c2] = \
                                net.name, slo, shi
                            reachB_n[c2] = shi == self.boundary_t + 1
                        else:
                            lo_n[c2] = min(lo_n[c2], slo)
                            hi_n[c2] = max(hi_n[c2], shi)
                    if side_p:
                        slo = side_p[0] + 1
                        shi = side_p[-1] + 1
                        if owner_p[c2] is None:
                            owner_p[c2], lo_p[c2], hi_p[c2] = \
                                net.name, slo, shi
                            reachB_p[c2] = slo == self.boundary_t + 1
                        else:
                            lo_p[c2] = min(lo_p[c2], slo)
                            hi_p[c2] = max(hi_p[c2], shi)
                parent[find(c1)] = find(c2)

        # ---- the access coverage (verify's rule: the stripe covers
        # the access track -- the fills above guarantee it; re-check) ----
        for (name, c), rails in sorted(access_rail.items()):
            for rail in rails:
                covered = False
                if owner_n[c] == name and lo_n[c] <= rail + 1 <= hi_n[c]:
                    covered = True
                if owner_p[c] == name and lo_p[c] <= rail + 1 <= hi_p[c]:
                    covered = True
                if not covered:
                    return self._fail(
                        "vocabulary: access %s@%d loses its rail track %d"
                        % (name, c, rail))

        # ---- the final via fixup: the adjacent-segment via forms must
        # hold at the END (later emissions can flip a slot's layer),
        # and every same-net M1|M2 adjacency needs its via square
        # (verify's rule: the layer switch is legal only through one)
        for (t, c) in sorted(via):
            left = hseg.get((t, c - 1))
            right = hseg.get((t, c))
            ok_form = (
                left is not None and right is not None and left == right
                and not pj.get((t, c - 1)) and not pj.get((t, c))
                and (bool(m2flag.get((t, c - 1)))
                     != bool(m2flag.get((t, c)))))
            if not ok_form and (t, c) not in m2via:
                del via[(t, c)]
        for (t, c) in sorted(hseg):
            if not m2flag.get((t, c)) or pj.get((t, c)):
                continue
            for other, vcol in (((t, c - 1), c), ((t, c + 1), c + 1)):
                if (hseg.get(other) == hseg[(t, c)]
                        and not pj.get(other)
                        and not m2flag.get(other)):
                    via[(t, vcol)] = True

        vseg = sum(1 for o in owner_n if o is not None) \
            + sum(1 for o in owner_p if o is not None) \
            + len(extra_stripes)
        result = RouteResult(
            "FEASIBLE", owner_n, owner_p, lo_n, hi_n, lo_p, hi_p,
            hseg, pj, m2flag, via, reachB_n, reachB_p, W + 1,
            len(hseg), vseg, len(pj), len(m2flag), len(via),
            m2v=m2v, m2via=m2via, extra_stripes=tuple(extra_stripes))
        result.route_cost = (
            sum(1 for k in hseg if not m2flag.get(k) and not pj.get(k))
            * H_MET_COST
            + sum(1 for k in hseg if m2flag.get(k)) * M2_H_COST
            + sum(1 for k in hseg if pj.get(k)) * POLY_ARC_COST
            + len(via) * VIA_COST + len(m2via) * VIA_COST
            + sum(t2 - t1 for (_c, t1, t2) in m2v) * M2_V_COST)
        result.attempts_used = self.attempts_used
        result.dual_merge = dual_merge
        return result

    def _fail(self, note):
        self._fail_note = note
        return self.failed_result()

    def failed_result(self):
        """RouteResult-shaped failure with the real width (consumers
        derive columns from the placement)."""
        W = self.width_cols
        result = RouteResult(
            "UNKNOWN", [None] * (W + 1), [None] * (W + 1),
            [0] * (W + 1), [0] * (W + 1),
            [self.bar_levels - 1] * (W + 1), [self.bar_levels - 1] * (W + 1),
            {}, {}, {}, {}, [False] * (W + 1), [False] * (W + 1),
            W + 1, 0, 0, 0, 0, 0)
        result.fail_note = self._fail_note
        result.attempts_used = self.attempts_used
        return result


def route_cell_ported(netlist, placement, width_cols, leg_widths=None,
                      height_um=2.47, grid_um=0.19,
                      max_attempts=MAX_ATTEMPTS, blocks=None,
                      tracks="astran13", optimize=True,
                      vocab_rounds=VOCAB_ROUNDS):
    """Route one placed cell with the ported ASTRAN router.

    Same signature and contract as route_grid.route_cell (a RouteResult
    consumable by smt_engine.verify / gds_cells unchanged; the result
    covers every placement column + the trailing escape).  Two phases:
    phase 1 is the C++ configuration exactly (the element graph has no
    metal2 -- AutoCell::route is a 2.5-layer router), phase 2 adds the
    3-layer directional freedom (M2 h=4 / v=11 / via 4,
    Router::setup's table) when phase 1 stalls or its solution cannot
    be expressed in the RouteResult vocabulary.

    The vocabulary feedback: the C++ solution is node-exclusive but the
    RouteResult contract is narrower (one stripe per half-column,
    margin-legal gate contacts, anchored poly runs).  When a routed
    solution cannot be expressed, the conversion reports the blocker
    NODES and the router re-routes with their congestion history bumped
    -- GraphRouter's own negotiated-congestion mechanism
    (graphrouter.cpp:135-138) applied to the vocabulary layer -- for at
    most ``vocab_rounds`` rounds per phase, then the next phase runs.
    Deterministic throughout: the bump set, the round count and the
    re-entry order are fixed.

    Provenance rides the result: ``router_phase``, ``router_attempts``,
    ``router_rounds`` and ``phase1_note`` (the phase-1 failure note
    when phase 2 ran).
    """
    del leg_widths                        # the fold lives in the placement
    width_cols = max(width_cols,
                     max((p.end_col for p in placement.values()), default=0))
    from smt_engine.verify import verify_cell

    def finish(grid, phase, note, rounds):
        """Build the result; on a verify-dirty conversion retry once
        with the dual merge (the same-net dual columns' boundary fill,
        route_grid's solidify rule).  Deterministic: verify_cell is
        pure, and the retry order is fixed."""
        result = grid.build_result()
        if not result.ok:
            result.router_phase = phase
            result.router_attempts = grid.attempts_used
            result.router_rounds = rounds
            if note is not None:
                result.phase1_note = note
            return result, None
        report = verify_cell(netlist, placement, result, blocks=blocks,
                             tracks=tracks)
        if not report.ok() and any("not connected" in v
                                   for v in report.violations):
            merged = grid.build_result(dual_merge=True)
            merged_report = verify_cell(netlist, placement, merged,
                                        blocks=blocks, tracks=tracks)
            if (len(merged_report.violations)
                    < len(report.violations)):
                result = merged
                report = merged_report
        result.router_phase = phase
        result.router_attempts = grid.attempts_used
        result.router_rounds = rounds
        result.router_verify = report.violations[:8]
        if note is not None:
            result.phase1_note = note
        return result, report

    def run_phase(metal2, phase, note):
        """One phase: up to vocab_rounds route->convert->verify rounds,
        bumping the conversion's blocker nodes between them.  Returns
        (result, report) of the best round (a clean one ends the
        phase)."""
        grid = _ElementRouter(netlist, placement, width_cols,
                              blocks=blocks, height_um=height_um,
                              grid_um=grid_um, metal2=metal2,
                              tracks=tracks)
        # the cumulative vocabulary price per node (kept OUTSIDE the
        # graph: the C++'s optimize clears the graph's history every
        # sweep, so the feedback re-applies its own bookkeeping at
        # each re-entry)
        bumps = {}
        best = None
        best_report = None
        for rnd in range(vocab_rounds):
            routed = grid.route(max_attempts=max_attempts,
                                optimize=optimize,
                                keep_history=rnd > 0)
            if not routed:
                # a routing failure (no path / stalled negotiation):
                # the conflicted nets' contested nodes carry the price
                coll = set(getattr(grid, "_collisions", ()) or ())
                for net in grid.nets:
                    if net.conflict:
                        for nid in net.tree:
                            if grid.graph[nid].nr_nets > 1:
                                coll.add(nid)
                if not coll or rnd + 1 >= vocab_rounds:
                    result = grid.failed_result()
                    result.router_phase = phase
                    result.router_attempts = grid.attempts_used
                    result.router_rounds = rnd + 1
                    if note is not None:
                        result.phase1_note = note
                    return result, None
                for nid in coll:
                    bumps[nid] = bumps.get(nid, 0) + VOCAB_BUMP
                for nid, h in bumps.items():
                    grid.graph[nid].history = h
                grid._fail_note = None
                continue
            result, report = finish(grid, phase, note, rnd + 1)
            if result.ok and report is not None and report.ok():
                return result, report
            clean = (result.ok
                     and not getattr(result, "router_verify", ()))
            if best is None or (clean and best is not None
                                and getattr(best, "router_verify", ())):
                best, best_report = result, report
            # the feedback: the conversion's blocker nodes (the fills'
            # collisions, the two-stripe runs, the dropped unanchored
            # poly runs) take a CUMULATIVE price -- the next routeNets
            # trades them away (the dropped wires' nodes are exactly
            # what the vocabulary could not express)
            coll = set(getattr(grid, "_collisions", ()) or ())
            if not coll or rnd + 1 >= vocab_rounds:
                break
            for nid in coll:
                bumps[nid] = bumps.get(nid, 0) + VOCAB_BUMP
            for nid, h in bumps.items():
                grid.graph[nid].history = h
            grid._fail_note = None      # the conversion's note must not
                                        # block the next routeNets entry
        if best is not None:
            return best, best_report
        result = grid.failed_result()
        result.router_phase = phase
        result.router_attempts = grid.attempts_used
        if note is not None:
            result.phase1_note = note
        return result, None

    phase1_note = None
    result, report = run_phase(False, 1, None)
    if result.ok and report is not None and report.ok():
        return result
    phase1_note = getattr(result, "fail_note", None)         or "; ".join(getattr(result, "router_verify", ())) or None
    result, report = run_phase(True, 2, phase1_note)
    return result
