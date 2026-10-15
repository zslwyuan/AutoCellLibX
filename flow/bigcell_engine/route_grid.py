"""Negotiated-congestion grid router (stage 3, doc section 2.4 rung 2).

A faithful port of ASTRAN's GraphRouter scheme (graphrouter.cpp:92-282)
onto the per-column element graph of AutoCell::route (autocell2.cpp:243-474)
with GridRouter's 3-layer structure (gridrouter.cpp:33-47; layer costs from
Router::setup, router.cpp:23-24/53-55).

Grid
----
- x = the placement columns on the 0.19 um grid (invariant 2); routing
  points sit on the column *edges* (x = c*g), exactly where
  smt_engine.route_model's vertical stripes and smt_engine/gds.py's
  ``_track_x`` put them;
- y = the routing tracks and supply rails of the shared track model:
  ``track_positions`` re-uses smt_engine/gds.track_geometry -- the 7 signal
  tracks T0..T6 plus the GND/VCC rail levels (the 9-level bar domain the
  RouteResult contract speaks).  ASTRAN's calcArea derives ~13 M1 tracks
  from the .rul rules; the RouteResult/verify/gds contract fixed in stage 2
  speaks exactly 7 tracks and 9 bar levels, so this router routes on that
  domain.  It is track-count parametric: widening ``N_TRACKS`` here and in
  route_model/gds together extends the grid (doc section 7 open question 1);
- z in {M1, poly, M2} with via1 junctions -- the smt_engine route vocabulary.

Nodes ("points")
----------------
The router's resource model is the *point* graph: one node per
(track, column) metal1 position.  A horizontal wire from column c to c+1 on
track t occupies both endpoints; a vertical stripe occupies the points of
every track it covers.  This makes every geometric short a node conflict:
two nets touching anywhere share a point.  After routing, each net's
per-column occupancy is *solidified* (filled contiguously per slot) so the
emitted stripe interval equals the occupied set, matching the bar-coverage
semantics of smt_engine.verify's BFS exactly.

Slot geometry (doc/BIGCELL_SLOT_GEOMETRY.md section 8)
------------------------------------------------------
Placements whose every leg is one column wide (die_view.is_slot_placement,
the fold/slot chain's signature) route on the SLOT grid:

- the grid runs on the EDGE axis: member columns 0..W-1 plus the right
  terminal edge W (which doubles as ASTRAN's trailing lateral GAP
  escape column; the leading one's role is played by the per-column
  pin hubs) -- width_cols = W + 1, so route column c draws at die x
  0.2375 + c*0.19 (gds_cells' edge_x), in line with every contact;
- diffusion terminals come from the SHARED die view
  (smt_engine.die_view.die_slot_access_points): left access at the
  member's start_col edge, right access at start_col + legs*leg_width_cols
  (the exact engine's walk insets a width-1 leg's right access into its
  own column), every slot of a multi-region net exposed so its regions
  stay tied;
- diffusion coverage / vertical costs realign to the W-tall strips, and
  gate contact tracks are restricted to the strip x row-band
  intersection, plus the corridor track T3 where an aligned P/N gate
  pair makes the drawn merged poly continuous (verify's row-band spans
  accept every track allowed here);
- a gate-only net (no diffusion access) owns no pin terminal -- the
  RouteResult vocabulary has no pin geometry -- and its crossing is
  materialized directly by _complete_junctions (poly jump preferred,
  M1 crossing last resort), ASTRAN's gate-element turn expressed in
  this vocabulary;
- exact-engine placements (any leg wider than one column) keep the
  historical graph byte-for-byte: inset accesses via
  _oriented_diffusion_access_points, row-band coverage, pins on every
  external net.

Diffusion access points are derived **orientation-aware** (die_view,
lifted from this module): the heuristic placement mirrors diffusion
blocks (netlist_ext.mirror_block -- members reversed, each member's
edge nets swapped), and the base smt_engine.netlist walk
extrapolates a mirrored block from its base-first member's column, which
scrambles net->column and once built power stripes on columns where other
signals' diffusions actually sit ("terminal clash at ('M1', 4, 8): cl0#Y
and VCC").  A block is mirrored exactly when its members' placement
start_cols descend in the block's own member order; a single-member
block's flip is recovered from place_row's abutment gaps (gap 0 <=> the
facing end nets are equal, one break column <=> they differ), defaulting
to pristine when no constraint pins it -- the one case the die cannot
distinguish, where every consumer of die_view makes the same assumption.

Per column there are also: a poly node per gate stripe (contacted by M1
crossings, merged by poly jumps), a 0-cost ``inoutCnt`` hub wired to every
track (autocell2.cpp:58-62) feeding one pin node per external signal net,
and pre-built power stripes for every power diffusion access (the
RouteResult contract demands stripes reaching the power ends, which the
rails already draw).

Solver
------
GraphRouter::routeNets verbatim: route every net permitting overlap,
``history += 1`` on contested nodes, next-round cost =
``arc.cost + history*(users+1)`` (graphrouter.cpp:429-434), rip up and
re-route conflicted nets, <= MAX_ATTEMPTS attempts with the C++ stall break,
then <= STEINER_SWEEPS Steiner-point optimization sweeps
(graphrouter.cpp:185-282) with restore-on-failure.

On top of the node conflicts, the router negotiates the vocabulary
constraints the exact engine encodes algebraically (one stripe per
(slot, column), via both-side segments, gate crossings, poly jump field
legality): each violation found in the per-attempt pass marks the involved
nets conflicted and bumps history on the involved nodes, so the negotiated
loop converges to contract-clean geometry.  Two router-specific devices
keep the search tied to the geometry: *_solidify* and *_complete_junctions*
extend each net's tree so the occupied set equals the drawn geometry
(stripe intervals, gate crossings, via sides), and their collision bumps
price the *triggering* routing choice.  The pin-hub network is pinned to a
single stub per net (post-pass (h)): the BFS has no pin geometry, so a
tree path hopping point -> hub -> pin -> hub -> point would be connected
in the tree but not on the die.

Determinism (AGENTS.md invariants 8/9): nets are routed in sorted-name
order; the priority queue breaks cost ties by (node id, insertion counter);
all loops terminate on fixed counts; no wall-clock anywhere.  Identical
inputs produce a byte-identical RouteResult.

Arc costs are the verbatim ASTRAN table -- see the constants below with
their file:line provenance.  Output is a RouteResult exactly as
smt_engine.route_model.solve_routing returns it, consumable by
smt_engine/verify.py and smt_engine/gds.py unchanged.
"""

import heapq

from bigcell_engine.geometry import (BREAK_GAP_COLS, MID_UM, WELL_GAP_UM)
from smt_engine import die_view
from smt_engine.gds import (CONTACT_S, POLY_OVERHANG, row_geometry,
                            track_geometry)
from smt_engine.netlist import (build_diffusion_blocks, exposed_net_set,
                                gate_access_points)
from smt_engine.route_model import (BAR_LEVELS, BOUNDARY_T, N_TRACKS,
                                    ROW_TRACK, ROW_TRACKS, RouteResult,
                                    device_rail)

MAX_ATTEMPTS = 8000             # autocell2.cpp:470 routeNets(8000)
STEINER_SWEEPS = 2              # autocell2.cpp:472 rt->optimize() && ..()
STALL_ATTEMPTS = 50000          # graphrouter.cpp:165 cntConflict stall break

# ---- verbatim arc-cost table (AutoCell::route / GraphRouter) ----
H_MET_COST = 4              # autocell2.cpp:38 horizontal met-met arc
VCOST_DIFF = 4              # autocell2.cpp:333/428 createElement(4, ...):
                            # diffusion/gap/break columns
VCOST_GATE = 16             # autocell2.cpp:304/375/463 createElement(16,...):
                            # gate and lateral columns
V_OUTSIDE_DISCOUNT = 1      # autocell2.cpp:29 vertical arc = vcost-1 outside
                            # the diffusion spans
V_CORRIDOR_SURCHARGE = 1    # autocell2.cpp:31 vertical arc = vcost+1 in the
                            # N<->P well-boundary corridor (non-gate columns)
POLY_ARC_COST = 6           # autocell2.cpp:42/:51 poly-poly arcs
GATE_CONTACT_COST = 20      # autocell2.cpp:48 pol<->met at gate columns
HUB_CORRIDOR_COST = 495     # autocell2.cpp:62 inoutCnt->met, corridor tracks
HUB_COST = 500              # autocell2.cpp:62 inoutCnt->met, elsewhere
DIFF_CONTACT_COST = 20      # autocell2.cpp:277 COST_CNT_INSIDE_DIFF; in this
                            # vocabulary every diffusion access draws its
                            # contact unconditionally, so the cost carries no
                            # routing choice and is documented, not wired
POLY_MET_OVER_DIFF = 200    # autocell2.cpp:47; likewise unmodeled: the only
                            # poly<->M1 junction the RouteResult contract
                            # has is the gate crossing itself
M2_H_COST = 4               # Router::setup, router.cpp:24/:55 (M2 h-cost of
                            # the GridRouter cost triples)
VIA_COST = 4                # Router::setup, router.cpp:23-24 (up-cost)

GND_NAMES = ("GND", "VSS")
VCC_NAMES = ("VCC", "VDD")
POWER_NAMES = GND_NAMES + VCC_NAMES

# row of each diffusion row-track (verify.py:40 ROW_OF_TRACK)
_ROW_OF_TRACK = {0: (False, 0), 2: (False, 1), 4: (True, 0), 6: (True, 1)}

_M1, _M2, _PJ, _G, _HUB, _PIN = "M1", "M2", "PJ", "G", "HUB", "PIN"


def track_positions(height_um=2.47, grid_um=0.19):
    """(trackY, barY): y-centres of the routing tracks and the bar domain.

    Re-uses smt_engine/gds.track_geometry -- the shared 7-track model's
    positions extended by the two supply-rail levels (barY = [GND] + trackY
    + [VCC], 9 levels).  This is the vertical domain of the RouteResult
    contract; ASTRAN's rule-derived ~13-track list is the documented
    extension path (doc/STAGE3_BIGCELL_ENGINE.md section 7.1).
    """
    return track_geometry(height_um, grid_um)


def _row_track_ranges(height_um, grid_um):
    """{(is_p, row): tracks whose y lies inside the diffusion rectangle}."""
    trackY, _ = track_geometry(height_um, grid_um)
    _, rows = row_geometry(height_um, grid_um)
    return {key: tuple(t for t in range(N_TRACKS) if y0 <= trackY[t] <= y1)
            for key, (y0, y1) in rows.items()}


def _die_orientation(netlist, placement, break_cols=BREAK_GAP_COLS):
    """Per-device die orientation: {device name: (left_net, right_net)}.

    The reconstruction (multi-member mirror detection + the
    abutment-gap fixpoint for singles, pristine where the die cannot
    distinguish) lives in smt_engine.die_view -- the SHARED view the
    verifier's access derivation consumes too, so both engines always
    agree on which net sits at which terminal column.  This adapter
    keeps the router-local signature.
    """
    return die_view.die_orientation_map(netlist, placement, break_cols)


def _oriented_diffusion_access_points(netlist, placement, orientation):
    """(signal, power) diffusion access points, EXACT-ENGINE column form.

    diffusion_access_points' exact contract (same exposed-net filter,
    same sort, right access inset into the member's last own column),
    but walked in each block's DIE member order with the die edge nets.
    The base walk starts at the base-first member's column and
    accumulates widths in base member order, so a mirrored block's nets
    are extrapolated onto the columns where the *next* block's diffusions
    actually sit -- the scrambled view that once pre-built power stripes
    on foreign signal columns ("terminal clash").  For pristine blocks
    (the exact-engine placements) the two walks coincide.

    Slot-model placements route through die_view.die_slot_access_points
    instead (true EDGE columns, multi-region slots exposed, doc
    /BIGCELL_SLOT_GEOMETRY.md section 8.1-8.2).
    """
    exposed = exposed_net_set(netlist)
    signal = {}
    power = {}
    powerNames = ("VCC", "GND", "VDD", "VSS")
    for block in build_diffusion_blocks(netlist):
        die = sorted(block.members,
                     key=lambda m: (placement[m.device].start_col,
                                    m.device.name))
        for member in die:
            p = placement[member.device]
            width = p.legs * p.leg_width_cols
            lnet, rnet = orientation[member.device.name]
            for net, col in ((lnet, p.start_col),
                             (rnet, p.start_col + width - 1)):
                if (net in exposed):
                    dst = power if net in powerNames else signal
                    dst.setdefault(net, []).append((col, member.device))
    key = lambda t: (t[0], t[1].name)
    return ({n: sorted(set(pts), key=key) for n, pts in signal.items()},
            {n: sorted(set(pts), key=key) for n, pts in power.items()})


class _Node(object):
    __slots__ = ("kind", "net", "nr_nets", "history", "source", "arcs")

    def __init__(self, kind):
        self.kind = kind            # (kind-tag, ...) geometry tuple
        self.net = -1               # owning net index, -1 = free
        self.nr_nets = 0
        self.history = 0
        self.source = 0             # 1 = terminal, 2 = added Steiner point
        self.arcs = []


class _Arc(object):
    __slots__ = ("cost", "label", "n1", "n2", "lock_net")

    def __init__(self, n1, n2, cost):
        self.cost = cost
        self.label = -1
        self.n1 = n1
        self.n2 = n2
        self.lock_net = -1          # graphrouter.h t_arc, unused here


class _Net(object):
    __slots__ = ("index", "name", "nodes", "tree", "conflict")

    def __init__(self, index, name):
        self.index = index
        self.name = name
        self.nodes = []             # terminals (+ Steiner points), fixed order
        self.tree = []              # current routing tree
        self.conflict = False


class _RouteGrid(object):
    """The routing graph + Pathfinder solver for one cell."""

    def __init__(self, netlist, placement, width_cols,
                 height_um=2.47, grid_um=0.19):
        self.netlist = netlist
        self.placement = placement
        self.slot = die_view.is_slot_placement(placement)
        if self.slot:
            # slot geometry (doc/BIGCELL_SLOT_GEOMETRY.md section 8): the
            # grid runs on the EDGE axis -- member columns 0..W-1 plus the
            # right terminal edge W, which doubles as the trailing lateral
            # escape column of ASTRAN's route() (its leading lateral GAP
            # role is played by the per-column pin hubs).  Edge e is the
            # left boundary of column e, so the die frame (gds_cells)
            # draws route column c at x = ESCAPE_L_UM + c*0.19, in line
            # with every contact.
            width_cols += 1
        self.width_cols = width_cols
        self.height_um = height_um
        self.grid_um = grid_um
        self.trackY, self.barY = track_geometry(height_um, grid_um)
        self.graph = []             # node id -> _Node
        self.arcs = []
        self._id = {}               # geometry tuple -> node id
        self.nets = []              # routed signal nets, sorted-name order
        self.power = []             # _Net for pre-built power stripes
        self._fail_note = None
        self._label = 0
        self._final_label = 0
        self.attempts_used = 0
        self.conflict_trace = []    # (attempt, conflicts, conflicted names)
        self._build()

    # ---------------- graph construction ----------------

    def _node(self, kind):
        nid = self._id.get(kind)
        if (nid is None):
            nid = len(self.graph)
            self.graph.append(_Node(kind))
            self._id[kind] = nid
        return nid

    def _m1(self, t, c):
        return self._node((_M1, t, c))

    def _add_arc(self, a, b, cost):
        self.arcs.append(_Arc(a, b, cost))
        self.graph[a].arcs.append(len(self.arcs) - 1)
        self.graph[b].arcs.append(len(self.arcs) - 1)

    def _claim(self, nid, net):
        """addNodetoNet port: mark ``nid`` a terminal of ``net``."""
        node = self.graph[nid]
        if (node.net != -1 and node.net != net.index):
            # a power stripe already covers this access point: the signal
            # contact would sit inside the power metal -- the placement is
            # unrouteable in this vocabulary (observed on folded netlists
            # where two block ends share a column); fail honestly
            self._fail_note = (
                "terminal clash at %s: %s and %s"
                % (node.kind, self._net_name(node.net), net.name))
            return
        if (node.net == -1):
            node.net = net.index
            node.nr_nets = 0
            node.source = 1
            net.nodes.append(nid)

    def _net_name(self, index):
        for net in self.nets + self.power:
            if (net.index == index):
                return net.name
        return "?%d" % index

    def _build(self):
        netlist, placement, width = (self.netlist, self.placement,
                                     self.width_cols)
        height, grid = self.height_um, self.grid_um

        # ---- static per-column geometry ----
        self.gate_tracks, self.gate_nets_at, self.gate_span = \
            self._gate_maps()
        self.field = self._field_map()
        # diffusion coverage per (column, half): the tracks of the devices
        # whose rectangle covers the column edge (ASTRAN's nDiff/pDiff
        # span per element, autocell2.cpp:319-329).  Slot model: the
        # coverage comes from the W-tall strips (section 8.4); exact
        # engine: the row_geometry sub-bands.
        self.diff_tracks = {c: {False: set(), True: set()}
                            for c in range(width)}
        if self.slot:
            for dev in netlist.devices:
                tracks = self._strip_tracks(dev)
                p = placement[dev]
                for c in range(p.start_col, p.end_col):
                    if (c < width):
                        self.diff_tracks[c][dev.is_p].update(tracks)
        else:
            row_tracks = _row_track_ranges(height, grid)
            for dev in netlist.devices:
                p = placement[dev]
                for c in range(p.start_col, p.end_col + 1):
                    if (c < width):
                        self.diff_tracks[c][dev.is_p].update(
                            row_tracks[(dev.is_p, p.row)])
        self.gate_cols = set()
        for cols in self.gate_nets_at.values():
            self.gate_cols.update(cols)

        # ---- net registry (sorted names; determinism) ----
        # only nets with a routing requirement are routed: a diffusion
        # access or a gate.  A net whose terminals are all shared
        # (internal) diffusion edges is electrically complete through the
        # shared diffusion and needs no wire (netlist.exposed_net_set).
        signal = [n for n in netlist.nets if n not in POWER_NAMES]
        if self.slot:
            # slot geometry (doc/BIGCELL_SLOT_GEOMETRY.md section 8.1-8.2):
            # terminals on the TRUE edge columns (left = start_col, right
            # = start_col + legs*leg_width_cols -- the exact engine's walk
            # insets a width-1 leg's right access into its own column) and
            # every slot of a multi-region net exposed so its regions stay
            # tied.  The shared die view -- smt_engine.verify derives its
            # access requirements from the same function.
            diff_sig, diff_pow = die_view.die_slot_access_points(
                netlist, placement, break_cols=BREAK_GAP_COLS)
        else:
            orientation = _die_orientation(netlist, placement)
            diff_sig, diff_pow = _oriented_diffusion_access_points(
                netlist, placement, orientation)
        gate_pts = gate_access_points(netlist, placement)
        routed = sorted(n for n in signal
                        if diff_sig.get(n) or gate_pts.get(n))
        index = 0
        for name in routed:
            self.nets.append(_Net(index, name))
            index += 1
        for name in sorted(diff_pow):
            self.power.append(_Net(index, name))
            index += 1
        self.power_index = {net.name: net.index for net in self.power}
        self.by_name = {net.name: net for net in self.nets + self.power}

        # ---- M1/M2 point grids ----
        for t in range(N_TRACKS):
            for c in range(width):
                self._m1(t, c)
                self._node((_M2, t, c))
        # poly jump points on the row tracks
        for t in sorted(ROW_TRACKS):
            for c in range(width):
                self._node((_PJ, t, c))
        # poly-jump foreign-gate blocking: gates spanning the track at the
        # column (raw y-span -- verify.py's foreign-gate rule)
        self._poly_span = {}
        for t in sorted(ROW_TRACKS):
            for c in range(width):
                spanning = frozenset(
                    g for g in self.gate_nets_at
                    if c in self.gate_nets_at[g]
                    and self._spans_track(g, c, t))
                self._poly_span[(t, c)] = spanning

        # ---- arcs ----
        for t in range(N_TRACKS):
            for c in range(width - 1):
                self._add_arc(self._m1(t, c), self._m1(t, c + 1),
                              H_MET_COST)
                self._add_arc(self._node((_M2, t, c)),
                              self._node((_M2, t, c + 1)), M2_H_COST)
                self._add_arc(self._m1(t, c), self._node((_M2, t, c)),
                              VIA_COST)
        for t in range(1, N_TRACKS):
            for c in range(width):
                self._add_arc(self._m1(t - 1, c), self._m1(t, c),
                              self._v_cost(c, t))
        for t in sorted(ROW_TRACKS):
            for c in range(width - 1):
                # the jump segment (t, c) must leave field oxide at its
                # right end (verify.py: unconditional c+1 in field[t])
                if (c + 1 in self.field[t]):
                    self._add_arc(self._node((_PJ, t, c)),
                                  self._node((_PJ, t, c + 1)),
                                  POLY_ARC_COST)

        # ---- gate nodes + contact arcs ----
        for net in sorted(self.gate_nets_at):
            for c in sorted(self.gate_nets_at[net]):
                g = self._node((_G, c, net))
                for t in self.gate_tracks[(net, c)]:
                    self._add_arc(g, self._m1(t, c), GATE_CONTACT_COST)
                    if (t in ROW_TRACKS):
                        # poly jumps run on the row tracks only; the poly
                        # merge of the gate stripe uses the same tracks
                        self._add_arc(g, self._node((_PJ, t, c)), 0)

        # ---- I/O pin hubs (autocell2.cpp:58-62, 303-309) ----
        for c in range(width):
            hub = self._node((_HUB, c))
            n_ini, p_ini = self._diff_ini(c)
            for t in range(N_TRACKS):
                cost = HUB_CORRIDOR_COST if (n_ini < t < p_ini) else HUB_COST
                self._add_arc(hub, self._m1(t, c), cost)
        ports = getattr(netlist, "external", set())
        for name in routed:
            if (name in ports and (not self.slot or diff_sig.get(name))):
                # slot model: a gate-only net (no diffusion access anywhere)
                # gets NO pin terminal -- the RouteResult vocabulary has no
                # pin geometry and gds_cells labels pins at diffusion
                # accesses only, so the pin would be a phantom requirement
                # whose M1 escape can structurally deadlock the negotiation
                # (the poly crossing at the gate is the net's whole wire).
                # Exact-engine placements keep the historical behaviour.
                pin = self._node((_PIN, name))
                for c in range(width):
                    self._add_arc(pin, self._node((_HUB, c)), 0)

        # ---- terminals: diffusion accesses + gates + pins ----
        for net in self.nets:
            for c, dev in diff_sig.get(net.name, ()):
                t_star = ROW_TRACK[device_rail(dev, placement[dev].row)]
                self._claim(self._m1(t_star, c), net)
            for c in sorted(gate_access_points(netlist, placement).get(
                    net.name, ())):
                if (c > width - 2):
                    # no segment (t, c) exists past the last segment column
                    # -- the gate can never be contacted (the exact engine
                    # refuses the same placement with an empty clause)
                    self._fail_note = (
                        "gate %s@%d sits past the last segment column %d"
                        % (net.name, c, width - 2))
                    return
                self._claim(self._node((_G, c, net.name)), net)
            if (net.name in ports and (not self.slot
                                       or diff_sig.get(net.name))):
                # every external net with a diffusion access owns its pin
                # node (the ASTRAN getInouts() semantics: all I/O nets
                # route to their pin); gate-only slot-model nets are
                # excluded (see the pin-hub note above); the single-stub
                # rule in the post-pass keeps the pin-hub network a leaf,
                # never a phantom connector
                self._claim(self._node((_PIN, net.name)), net)

        # ---- pre-built power stripes (route_model's power-end rule) ----
        for net in self.power:
            is_vcc = net.name in VCC_NAMES
            for c, dev in diff_pow.get(net.name, ()):
                t_star = ROW_TRACK[device_rail(dev, placement[dev].row)]
                span = range(t_star, N_TRACKS) if is_vcc \
                    else range(0, t_star + 1)
                for t in span:
                    self._claim(self._m1(t, c), net)
            # power stripes are static geometry, never routed: the tree is
            # the terminal list from the start
            net.tree = list(net.nodes)

    def _gate_maps(self):
        """(gate_tracks, gate_nets_at, gate_span) like route_model's
        _gate_track_maps: the margin tracks a crossing must use and the
        raw y-spans for poly-jump legality."""
        netlist, placement = self.netlist, self.placement
        height, grid = self.height_um, self.grid_um
        _, rows = row_geometry(height, grid)
        trackY = self.trackY
        spans = {}
        strip_ranges = {}             # (gate, c) -> [(strip y0, strip y1)]
        strip_pol = {}                # (gate, c) -> [has_p, has_n]
        for dev in netlist.devices:
            p = placement[dev]
            y0, y1 = rows[(dev.is_p, p.row)]
            sy0, sy1 = self._strip_y(dev)
            for j in range(p.legs):
                c = p.start_col + j * p.leg_width_cols + p.leg_width_cols // 2
                if (c >= self.width_cols):
                    continue
                key = (dev.gate, c)
                if (key in spans):
                    o0, o1 = spans[key]
                    spans[key] = (min(o0, y0), max(o1, y1))
                else:
                    spans[key] = (y0, y1)
                strip_ranges.setdefault(key, []).append((sy0, sy1))
                pol = strip_pol.setdefault(key, [False, False])
                pol[0 if dev.is_p else 1] = True
        gate_tracks = {}
        gate_nets_at = {}
        gate_span = {}
        for (net, c), (y0, y1) in spans.items():
            gate_nets_at.setdefault(net, set()).add(c)
            gate_span[(net, c)] = (y0 - POLY_OVERHANG, y1 + POLY_OVERHANG)
            if (self.slot):
                # section 8.4, router-local track alignment: a gate
                # contact must land on a track the DRAWN W-tall strip
                # spans (gds_cells draws the contact square only inside
                # the strip) AND on a track verify's row-band contact
                # range accepts -- the drawn poly overhang can reach
                # past the row band, so the two ranges are intersected.
                # The well-boundary corridor track joins in only where
                # an aligned P/N gate pair makes the drawn merged poly
                # stripe continuous over the boundary.
                tracks = set()
                for sy0, sy1 in strip_ranges.get((net, c), ()):
                    lo = max(sy0, y0) - POLY_OVERHANG + CONTACT_S / 2.0
                    hi = min(sy1, y1) + POLY_OVERHANG - CONTACT_S / 2.0
                    tracks.update(t for t in range(N_TRACKS)
                                  if lo <= trackY[t] <= hi)
                pol = strip_pol.get((net, c), (False, False))
                if (pol[0] and pol[1]):
                    lo = MID_UM - WELL_GAP_UM + CONTACT_S / 2.0
                    hi = MID_UM + WELL_GAP_UM - CONTACT_S / 2.0
                    tracks.update(t for t in range(N_TRACKS)
                                  if lo <= trackY[t] <= hi)
                gate_tracks[(net, c)] = sorted(tracks)
            else:
                lo = y0 - POLY_OVERHANG + CONTACT_S / 2.0
                hi = y1 + POLY_OVERHANG - CONTACT_S / 2.0
                gate_tracks[(net, c)] = sorted(
                    t for t in range(N_TRACKS) if lo <= trackY[t] <= hi)
        return gate_tracks, gate_nets_at, gate_span

    def _strip_y(self, dev):
        """(y0, y1) of the device's W-tall diffusion strip -- the slot
        model's drawing convention (W vertical, anchored at the well
        boundary, growing away from it by the electrical width; the
        fold already divided multi-leg devices' width)."""
        w = dev.width_um
        if dev.is_p:
            y0 = MID_UM + WELL_GAP_UM
            return y0, y0 + w
        y1 = MID_UM - WELL_GAP_UM
        return y1 - w, y1

    def _strip_tracks(self, dev):
        """Tracks the device's drawn strip physically spans (section 8.4:
        the vertical cost / corridor model realigned to the W-tall
        strips; the shared 7-track domain itself is the RouteResult
        contract with smt_engine.verify/gds and stays untouched)."""
        y0, y1 = self._strip_y(dev)
        return set(t for t in range(N_TRACKS)
                   if y0 <= self.trackY[t] <= y1)

    def _spans_track(self, gate_net, c, t):
        y0, y1 = self.gate_span[(gate_net, c)]
        return y0 <= self.trackY[t] <= y1

    def _field_map(self):
        """Row tracks with no active diffusion (verify.py _field_map)."""
        active = {}
        for dev in self.netlist.devices:
            p = self.placement[dev]
            active.setdefault((dev.is_p, p.row), set()).update(
                range(p.start_col, p.end_col))
        field = {}
        for t, (is_p, row) in _ROW_OF_TRACK.items():
            field[t] = set(range(self.width_cols)) \
                - active.get((is_p, row), set())
        return field

    def _diff_ini(self, c):
        """(nDiffIni, pDiffIni) track indices of column c for the hub cost
        (autocell2.cpp:62); virtual centre track when no device sits there
        (ASTRAN's lateral GAP elements, autocell2.cpp:304)."""
        nts = self.diff_tracks[c][False]
        pts = self.diff_tracks[c][True]
        centre = N_TRACKS // 2
        return (max(nts) if nts else centre, min(pts) if pts else centre)

    def _v_cost(self, c, t):
        """Vertical M1 arc cost between tracks t-1 and t at column c --
        the three-way rule of createElement (autocell2.cpp:26-33)."""
        nts = self.diff_tracks[c][False]
        pts = self.diff_tracks[c][True]
        centre = N_TRACKS // 2
        n_end, n_ini = (min(nts), max(nts)) if nts else (centre, centre)
        p_ini, p_end = (min(pts), max(pts)) if pts else (centre, centre)
        vcost = VCOST_GATE if c in self.gate_cols else VCOST_DIFF
        if (t <= n_end or t > p_end):
            return vcost - V_OUTSIDE_DISCOUNT
        if (t > n_ini and t <= p_ini and c not in self.gate_cols):
            return vcost + V_CORRIDOR_SURCHARGE
        return vcost

    # ---------------- Pathfinder solver (graphrouter.cpp port) ----------------

    def _calc_cost(self, arc, target_node, attempt):
        """GraphRouter::calcCost (graphrouter.cpp:429-434)."""
        node = self.graph[target_node]
        if (attempt != 1):
            return arc.cost + node.history * (node.nr_nets + 1)
        return arc.cost + node.history

    def _allow(self, net, other, cur):
        """Static per-net node allowance on top of the C++ filters.

        Only geometrically-impossible usage is pruned here; everything the
        vocabulary makes *dynamic* (slot uniqueness, via and gate junction
        legality) is negotiated by the post-pass instead, so the early
        attempts keep Pathfinder's route-everything-permitting-overlap
        freedom.
        """
        kind = self.graph[other].kind
        if (kind[0] == _PJ):
            t, c = kind[1], kind[2]
            if ((t, c) not in self._poly_span):
                return False            # PJ nodes exist on row tracks only
            spanning = self._poly_span[(t, c)]
            if (spanning and spanning != frozenset((net.name,))):
                return False       # would cross a foreign gate stripe
            if (c in self.field[t]):
                return True
            return net.name in self.gate_nets_at \
                and c in self.gate_nets_at[net.name]
        return True

    def _complete_junctions(self, net):
        """Make every gate merge and via in the tree geometrically real.

        A gate contact is a *crossing*: the wire must span [c, c+1] to
        reach the stripe (verify.py's BFS joins only segments at the gate
        column), and a via joins M1 and M2 *segments* on both sides.  The
        A* paths stop at junction nodes without necessarily shaping the
        crossing, so this pass adds the missing segment endpoints to the
        tree -- the same "make occupancy match geometry" move as
        _solidify.  Added points may collide with foreign nets; the
        node-conflict machinery negotiates those, and the *triggering*
        junction point gets a history bump so the next attempt prices the
        colliding merge choice.  Deterministic: the smallest candidate
        track / first matching side wins.  Returns the bumped node ids.

        Slot model, second role: a tree gate node with NO crossing at all
        (the gate-only nets -- no diffusion terminal gives the BFS a
        second endpoint to grow towards) gets its crossing materialized
        directly.  A poly jump on an in-strip row track is preferred (the
        gate merge is a 0-cost same-layer junction and poly claims no
        diffusion-side metal); the M1 crossing is the last resort.  A
        candidate whose endpoints sit on foreign metal is skipped, so the
        post-pass reports the honest violation instead of manufacturing
        a permanent conflict.
        """
        mine = set(net.tree)
        # foreign tree membership: a point can be free (net == -1, e.g. the
        # owner ripped up) while still living in another net's tree from
        # its last route -- the share is with that tree either way
        foreign_tree = {}
        for other in self.nets + self.power:
            if (other is net):
                continue
            for nid in other.tree:
                foreign_tree[nid] = other.index
        adds = []
        crossed_g = set()
        for nid in net.tree:
            kind = self.graph[nid].kind
            if (kind[0] != _G):
                continue
            c, gname = kind[1], kind[2]
            for t in self.gate_tracks.get((gname, c), ()):
                if (self._m1(t, c) in mine):
                    adds.append((self._m1(t, c + 1), self._m1(t, c)))
                    crossed_g.add(nid)
                    break
                if (t in ROW_TRACKS
                        and self._node((_PJ, t, c)) in mine):
                    adds.append((self._node((_PJ, t, c + 1)),
                                 self._node((_PJ, t, c))))
                    crossed_g.add(nid)
                    break
        if (self.slot):
            for nid in net.tree:
                if (nid in crossed_g):
                    continue
                kind = self.graph[nid].kind
                if (kind[0] != _G):
                    continue
                fallback = self._gate_crossing_fallback(
                    net, kind[2], kind[1], mine, foreign_tree)
                if (fallback is not None):
                    adds.extend(fallback)
        for t in range(N_TRACKS):
            for c in range(self.width_cols):
                m1c, m2c = self._m1(t, c), self._node((_M2, t, c))
                if (m1c not in mine or m2c not in mine):
                    continue
                if (c > 0 and self._m1(t, c - 1) in mine
                        and c + 1 < self.width_cols):
                    adds.append((self._node((_M2, t, c + 1)), m1c))
                elif (c > 0 and self._node((_M2, t, c - 1)) in mine
                      and c + 1 < self.width_cols):
                    adds.append((self._m1(t, c + 1), m2c))
                elif (c + 1 < self.width_cols and self._m1(t, c + 1) in mine
                      and c > 0):
                    adds.append((self._node((_M2, t, c - 1)), m1c))
                elif (c + 1 < self.width_cols
                      and self._node((_M2, t, c + 1)) in mine and c > 0):
                    adds.append((self._m1(t, c - 1), m2c))
        bumps = []
        for nid, trigger in adds:
            if (nid in mine):
                continue
            mine.add(nid)
            net.tree.append(nid)
            onet = self.graph[nid].net
            if (onet not in (-1, net.index) or nid in foreign_tree):
                bumps.append(trigger)
        return bumps

    def _gate_crossing_fallback(self, net, gname, c, mine, foreign_tree):
        """Crossing endpoints for one un-crossed tree gate (slot model).

        Returns [(new_node, trigger_node), ...] or None.  Poly jump
        first, M1 second; the smallest qualifying track wins.  Both
        endpoints must be claimable by ``net`` (unowned or already its
        own, and not living in another net's tree).
        """
        for t in self.gate_tracks.get((gname, c), ()):
            if (t in ROW_TRACKS and c + 1 < self.width_cols
                    and (c + 1) in self.field[t]
                    and self._poly_span[(t, c)] <= frozenset((net.name,))
                    and self._claimable(self._node((_PJ, t, c)), net,
                                        mine, foreign_tree)
                    and self._claimable(self._node((_PJ, t, c + 1)), net,
                                        mine, foreign_tree)):
                g = self._node((_G, c, gname))
                return [(self._node((_PJ, t, c + 1)), g),
                        (self._node((_PJ, t, c)), g)]
        for t in self.gate_tracks.get((gname, c), ()):
            if (c + 1 < self.width_cols
                    and self._claimable(self._m1(t, c), net, mine,
                                        foreign_tree)
                    and self._claimable(self._m1(t, c + 1), net, mine,
                                        foreign_tree)):
                g = self._node((_G, c, gname))
                return [(self._m1(t, c), g), (self._m1(t, c + 1), g)]
        return None

    def _claimable(self, nid, net, mine, foreign_tree):
        """Whether ``net`` may take ``nid`` without a permanent conflict."""
        node = self.graph[nid]
        return (node.net in (-1, net.index) and nid not in foreign_tree)

    def _bfs_route(self, net, tree, label, attempt, max_cost=0,
                   definitive=True, strict=False):
        """GraphRouter::bfsRoute / bfsRoute2 (graphrouter.cpp:285-426).

        Multi-source A* from the current tree to the closest not-yet-tree
        terminal.  Deterministic priority queue: (cost, node id, insertion
        counter).  Returns the path cost or -1 when no path exists.
        """
        graph = self.graph
        target = net.index
        trace = {}                          # node -> (father, arc)
        visited = set(tree)
        heap = []
        seq = 0
        for nd in tree:
            heap.append((0, nd, seq, -1, -1))
            seq += 1
        heapq.heapify(heap)
        found = -1
        found_cost = 0
        while heap:
            cost, node, _seq, father, arc_id = heapq.heappop(heap)
            if (father != -1 and node in visited):
                # stale duplicate: the C++ loop condition still tests it
                if (graph[node].net == target):
                    found, found_cost = node, cost
                    break
                continue
            if (father != -1):
                visited.add(node)
                trace[node] = (father, arc_id)
                if (graph[node].net == target):
                    found, found_cost = node, cost
                    break
            for arc_idx in graph[node].arcs:
                arc = self.arcs[arc_idx]
                other = arc.n2 if arc.n1 == node else arc.n1
                if (other in visited):
                    continue
                onode = graph[other]
                if (onode.source and onode.net != target):
                    continue                # foreign terminal: always blocked
                if (strict and onode.net not in (-1, target)):
                    continue                # bfsRoute2: overlap-free
                if (arc.lock_net not in (-1, target)):
                    continue
                if (not self._allow(net, other, node)):
                    continue
                ncost = self._calc_cost(arc, other, attempt) + cost
                if (max_cost and ncost > max_cost):
                    continue
                heap.append((ncost, other, seq, node, arc_idx))
                seq += 1
        if (found == -1):
            return -1
        node = found
        while (True):
            # C++ trace is a node-indexed vector: unvisited/tree slots read
            # father == -1 and end the walk; init tree nodes have no entry
            entry = trace.get(node)
            if (entry is None or entry[0] == -1):
                break
            father, arc_idx = entry
            tree.append(node)
            if (definitive):
                self.arcs[arc_idx].label = label
                if (strict):
                    graph[node].net = target
            node = father
        return found_cost

    def _solidify(self, net):
        """Fill each column's occupied tracks contiguously per slot.

        The emitted stripe is one rectangle per (slot, column) spanning
        [min, max] of the occupied levels; the fill makes the occupied set
        equal that interval, so verify.py's bar-coverage BFS and the
        crossing-safety rule see exactly the geometry the router built.
        A same-net dual (both slots) must merge through the T3 boundary
        track (verify.py's dual-column rule), so both slots extend to it.
        """
        cols = {}
        for nid in net.tree:
            kind = self.graph[nid].kind
            if (kind[0] == _M1):
                cols.setdefault(kind[2], set()).add(kind[1])
        have = set(net.tree)
        for c in sorted(cols):
            tracks = cols[c]
            n_side = sorted(t for t in tracks if t <= BOUNDARY_T)
            p_side = sorted(t for t in tracks if t >= BOUNDARY_T)
            fill = []
            if (n_side and p_side):
                fill.extend(range(n_side[0], BOUNDARY_T + 1))
                fill.extend(range(BOUNDARY_T, p_side[-1] + 1))
            elif (n_side):
                fill.extend(range(n_side[0], n_side[-1] + 1))
            elif (p_side):
                fill.extend(range(p_side[0], p_side[-1] + 1))
            for t in fill:
                nid = self._m1(t, c)
                if (nid not in have):
                    have.add(nid)
                    net.tree.append(nid)


    def _prim(self, net, nodes, attempt):
        """GraphRouter::prim (graphrouter.cpp:75-90): greedy tree cost."""
        tree = [nodes[0]]
        cost = 0
        for _ in range(len(nodes) - 1):
            ok = self._bfs_route(net, tree, attempt, attempt,
                                 definitive=False, strict=True)
            if (ok == -1):
                return -1
            cost += ok
        return cost

    def _add_steiner(self, net, attempt):
        """GraphRouter::addSteiner (graphrouter.cpp:185-227): greedily add
        unowned degree>2 nodes while they reduce the Prim cost."""
        candidates = [nid for nid in range(len(self.graph))
                      if self.graph[nid].net == -1
                      and len(self.graph[nid].arcs) > 2]
        best_cost = self._prim(net, list(net.nodes), attempt)
        added = 0
        improved = True
        while (improved):
            improved = False
            best_candidate = None
            for cand in candidates:
                if (self.graph[cand].net != -1):
                    continue
                self.graph[cand].net = net.index
                cost = self._prim(net, list(net.nodes) + [cand], attempt)
                self.graph[cand].net = -1
                if (cost != -1 and (best_cost == -1 or cost < best_cost)):
                    best_candidate, best_cost = cand, cost
            if (best_candidate is not None):
                self.graph[best_candidate].net = net.index
                self.graph[best_candidate].source = 2
                net.nodes.append(best_candidate)
                candidates.remove(best_candidate)
                added += 1
                improved = True
        return added

    def _snapshot(self):
        """Full solver state for restore-on-failure of the sweeps."""
        nodes = [(n.net, n.nr_nets, n.history, n.source) for n in self.graph]
        nets = [(net.nodes[:], net.tree[:], net.conflict)
                for net in self.nets]
        labels = [arc.label for arc in self.arcs]
        return nodes, nets, labels

    def _restore(self, snap):
        nodes, nets, labels = snap
        for node, state in zip(self.graph, nodes):
            node.net, node.nr_nets, node.history, node.source = state
        for net, state in zip(self.nets, nets):
            net.nodes, net.tree, net.conflict = state
        for arc, label in zip(self.arcs, labels):
            arc.label = label

    def _optimize_sweeps(self):
        """GraphRouter::optimize x STEINER_SWEEPS (autocell2.cpp:472).

        Clears history and re-routes every net overlap-free, greedily
        adding Steiner points while they reduce the Prim cost.  Aborts and
        restores the conflict-free solution when the strict re-route cannot
        find a path or reintroduces a vocabulary violation (the C++ would
        silently keep a partial tree there).
        """
        snap = self._snapshot()
        for _sweep in range(STEINER_SWEEPS):
            for node in self.graph:
                node.history = 0            # graphrouter.cpp:243-245
            self._label += 1
            budget = 4 * len(self.graph) + 8   # fixed safety cap (never
            passes = 0                          # binds on real cells)
            while (True):
                passes += 1
                if (passes > budget):
                    self._restore(snap)
                    return
                nr_steiners = 0
                for net in self.nets:
                    # rip up (graphrouter.cpp:252-258)
                    for nid in net.tree:
                        node = self.graph[nid]
                        node.nr_nets -= 1
                        if (not node.source):
                            node.net = -1
                    net.tree = []
                    if (len(net.nodes) > 2):
                        nr_steiners += self._add_steiner(net, self._label)
                    net.tree = [net.nodes[0]]
                    ok = 0
                    for _ in range(len(net.nodes) - 1):
                        ok = self._bfs_route(net, net.tree, self._label,
                                             1, definitive=True,
                                             strict=True)
                        if (ok == -1):
                            break
                    if (ok == -1):
                        self._restore(snap)
                        return
                    for nid in self._complete_junctions(net):
                        self.graph[nid].history += 1
                    self._solidify(net)
                    for nid in net.tree:
                        node = self.graph[nid]
                        node.nr_nets += 1
                        if (node.net in (-1, net.index)):
                            node.net = net.index
                if (not nr_steiners):
                    break
        conflicts, _nets, _bumps = self._post_pass()
        if (conflicts):
            self._restore(snap)

    def _post_pass(self):
        """Per-attempt vocabulary check (the negotiated extension).

        Beyond GraphRouter's node conflicts this detects the constraints
        the exact engine encodes algebraically: one stripe per (slot,
        column), gate crossings, via both-side segments, poly jump field
        legality and no M1|M2 double-layer segments.  Returns
        (conflict_count, conflicted net indexes, bumped node ids).
        """
        conflicts = 0
        conflicted = set()
        bumps = []
        tree_set = {}
        for net in self.nets:
            tree_set[net.index] = set(net.tree)
        # power stripes participate in node conflicts (immovable occupancy)
        for net in self.power:
            tree_set[net.index] = set(net.tree)

        def bump(nid):
            bumps.append(nid)

        # (a) node conflicts (graphrouter.cpp:145-154)
        owner_nets = {}
        for index in sorted(tree_set):
            for nid in tree_set[index]:
                owner_nets.setdefault(nid, set()).add(index)
        for nid in sorted(owner_nets):
            users = owner_nets[nid]
            if (len(users) > 1):
                conflicts += len(users)
                conflicted.update(users)
                bump(nid)

        # (b) one qualifying stripe per (slot, column): the RouteResult
        # vocabulary has a single owner_n/owner_p slot per column.  The
        # plan counts the contested pairs; bump every point of a contested
        # slot so the negotiation pushes one of the stripes away.
        plan, contested, plan_conflicted = self._stripe_plan()
        conflicts += len(contested)
        conflicted.update(plan_conflicted)
        for (c, slot) in sorted(contested):
            lo_t, hi_t = ((0, BOUNDARY_T) if slot == 0
                          else (BOUNDARY_T, N_TRACKS - 1))
            for t in range(lo_t, hi_t + 1):
                bump(self._m1(t, c))

        # (c) every tree gate node needs a crossing segment (t, c):
        # points (t, c) and (t, c+1) of the gate net, on M1 or poly
        for net in self.nets:
            mine = tree_set[net.index]
            for nid in net.tree:
                kind = self.graph[nid].kind
                if (kind[0] != _G):
                    continue
                c, gname = kind[1], kind[2]
                ok = False
                for t in self.gate_tracks.get((gname, c), ()):
                    if (self._m1(t, c) in mine and self._m1(t, c + 1) in mine):
                        ok = True
                        break
                    if (t in ROW_TRACKS
                            and self._node((_PJ, t, c)) in mine
                            and self._node((_PJ, t, c + 1)) in mine):
                        ok = True
                        break
                if (not ok):
                    conflicts += 1
                    conflicted.add(net.index)
                    # bump the merge points the net actually used at the
                    # gate column so the negotiation moves the crossing
                    for t in self.gate_tracks.get((gname, c), ()):
                        if (self._m1(t, c) in mine):
                            bump(self._m1(t, c))
                        if (t in ROW_TRACKS
                                and self._node((_PJ, t, c)) in mine):
                            bump(self._node((_PJ, t, c)))

        # (d) vias join one net's M1 and M2 segments on both sides; on the
        # edge columns no via can be emitted at all, so an M1|M2 pair there
        # is always a violation
        for net in self.nets:
            mine = tree_set[net.index]
            for t in range(N_TRACKS):
                for c in range(self.width_cols):
                    m1c, m2c = self._m1(t, c), self._node((_M2, t, c))
                    if (m1c not in mine or m2c not in mine):
                        continue
                    legal = (
                        c > 0 and c < self.width_cols - 1
                        and ((self._m1(t, c - 1) in mine
                              and self._node((_M2, t, c + 1)) in mine)
                             or (self._node((_M2, t, c - 1)) in mine
                                 and self._m1(t, c + 1) in mine)))
                    if (not legal):
                        conflicts += 1
                        conflicted.add(net.index)
                        bump(m2c)

        # (e) poly jump pairs: right end over field oxide
        for net in self.nets:
            mine = tree_set[net.index]
            for t in sorted(ROW_TRACKS):
                for c in range(self.width_cols - 1):
                    if (self._node((_PJ, t, c)) in mine
                            and self._node((_PJ, t, c + 1)) in mine
                            and c + 1 not in self.field[t]):
                        conflicts += 1
                        conflicted.add(net.index)
                        bump(self._node((_PJ, t, c)))
                        bump(self._node((_PJ, t, c + 1)))

        # (f) no M1|M2 double-layer segment (one hseg slot per (t, c))
        for net in self.nets:
            mine = tree_set[net.index]
            for t in range(N_TRACKS):
                for c in range(self.width_cols - 1):
                    if (all(self._node(k) in mine for k in
                            ((_M1, t, c), (_M1, t, c + 1),
                             (_M2, t, c), (_M2, t, c + 1)))):
                        conflicts += 1
                        conflicted.add(net.index)
                        bump(self._node((_M2, t, c)))

        # (g) one hseg slot per (t, c): the vocabulary cannot express an
        # M1 segment and a poly/M2 segment of *different* nets in the same
        # slot (same-net double layers are (f); same-layer sharing shows
        # up as point conflicts)
        slots = {}
        for net in self.nets:
            mine = tree_set[net.index]
            for t in range(N_TRACKS):
                for c in range(self.width_cols - 1):
                    if (self._m1(t, c) in mine
                            and self._m1(t, c + 1) in mine):
                        lay = "M1"
                    elif (t in ROW_TRACKS
                          and self._node((_PJ, t, c)) in mine
                          and self._node((_PJ, t, c + 1)) in mine):
                        lay = "PJ"
                    elif (self._node((_M2, t, c)) in mine
                          and self._node((_M2, t, c + 1)) in mine):
                        lay = "M2"
                    else:
                        continue
                    slots.setdefault((t, c), []).append((net.index, lay))
        for (t, c), users in sorted(slots.items()):
            if (len(users) > 1
                    and len(set(lay for _n, lay in users)) > 1):
                conflicts += 1
                conflicted.update(n for n, _lay in users)
                bump(self._m1(t, c))

        # (h) the pin-hub network is a single stub, never a connector: the
        # BFS has no hub or pin geometry, so a tree path hopping
        # point -> hub -> pin -> hub -> point would be connected in the
        # tree but not on the die.  The pin joins at most one hub (labeled
        # arcs of this attempt only) and every used hub joins at most one
        # landing point; a used hub without the net's pin is a dead dangle.
        pin_of = {}
        for net in self.nets:
            for nid in net.nodes:
                if (self.graph[nid].kind[0] == _PIN):
                    pin_of[net.index] = nid
        for net in self.nets:
            mine = tree_set[net.index]
            pin = pin_of.get(net.index)
            used_hubs = []
            if (pin is not None and pin in mine):
                for ai in self.graph[pin].arcs:
                    arc = self.arcs[ai]
                    if (arc.label != self._label):
                        continue
                    o = arc.n2 if arc.n1 == pin else arc.n1
                    if (o in mine
                            and self.graph[o].kind[0] == _HUB):
                        used_hubs.append(o)
            if (len(used_hubs) > 1):
                conflicts += 1
                conflicted.add(net.index)
                bump(pin)
                for o in used_hubs:
                    bump(o)
            for hub in used_hubs:
                landings = []
                for ai in self.graph[hub].arcs:
                    arc = self.arcs[ai]
                    if (arc.label != self._label):
                        continue
                    o = arc.n2 if arc.n1 == hub else arc.n1
                    if (o in mine
                            and self.graph[o].kind[0] != _PIN
                            and self.graph[o].kind[0] != _HUB):
                        landings.append(o)
                if (len(landings) > 1):
                    conflicts += 1
                    conflicted.add(net.index)
                    bump(hub)
                    for o in landings:
                        bump(o)
            # a hub in the tree whose arcs were all labeled by *other*
            # attempts is a leftover: it must be pinned by this attempt
            for nid in net.tree:
                if (self.graph[nid].kind[0] != _HUB):
                    continue
                used = [self.arcs[ai] for ai in self.graph[nid].arcs
                        if self.arcs[ai].label == self._label]
                if (not used):
                    continue
                touches_pin = any(
                    (arc.n2 if arc.n1 == nid else arc.n1) == pin
                    for arc in used)
                if (not touches_pin):
                    conflicts += 1
                    conflicted.add(net.index)
                    bump(nid)

        for nid in bumps:
            self.graph[nid].history += 1
        return conflicts, conflicted, bumps

    def _net_by_index(self, index):
        for net in self.nets:
            if (net.index == index):
                return net
        return None

    def route(self, max_attempts=MAX_ATTEMPTS):
        """GraphRouter::routeNets port (graphrouter.cpp:92-184).

        Returns True when the cell routed with zero conflicts.
        """
        if (self._fail_note is not None):
            return False
        # reset() (graphrouter.cpp:533-549): Steiner points are dropped
        for node in self.graph:
            node.history = 0
            node.source = 1 if node.source == 1 else 0
            if (not node.source):
                node.net = -1
            node.nr_nets = 0
        for net in self.nets:
            net.nodes = [nid for nid in net.nodes
                         if self.graph[nid].source == 1]
            net.tree = []
            net.conflict = False
        for arc in self.arcs:
            arc.label = -1

        attempt = 0
        ok = 0
        conflicts = 0
        min_conflict = 0
        cnt_conflict = -1
        solved = {}
        while (True):
            attempt += 1
            self._label = attempt
            ok = 0
            for net in self.nets:           # sorted-name order
                if (net.conflict or attempt == 1):
                    # rip up (graphrouter.cpp:120-125)
                    for nid in net.tree:
                        node = self.graph[nid]
                        node.nr_nets -= 1
                        if (not node.source and node.net == net.index):
                            node.net = -1
                    net.tree = [net.nodes[0]]
                    # grow to all terminals (graphrouter.cpp:128-134)
                    ok = 0
                    for _ in range(len(net.nodes) - 1):
                        ok = self._bfs_route(net, net.tree, attempt,
                                             attempt, definitive=True)
                        if (ok == -1):
                            break
                    if (ok == -1):
                        self._fail_note = ("impossible to find a path for "
                                           "net %s" % net.name)
                        break
                    for nid in self._complete_junctions(net):
                        self.graph[nid].history += 1
                    self._solidify(net)
                    for nid in net.tree:    # graphrouter.cpp:135-139
                        node = self.graph[nid]
                        node.nr_nets += 1
                        if (node.net in (-1, net.index)):
                            # never steal a foreign-owned node: an overlap
                            # stays owned by its first claimant and shows up
                            # as a tree conflict in the post-pass
                            node.net = net.index
                        if (node.nr_nets > 1):
                            node.history += 1
            if (ok == -1):
                break
            # conflict pass (graphrouter.cpp:145-158) + vocabulary pass
            conflicts = 0
            for net in self.nets:
                ant = net.conflict
                net.conflict = False
                for nid in net.tree:
                    if (self.graph[nid].nr_nets > 1):
                        conflicts += self.graph[nid].nr_nets
                        net.conflict = True
                if (not net.conflict and (ant or attempt == 1)):
                    solved[net.index] = attempt
            vocab, vocab_nets, _bumps = self._post_pass()
            conflicts += vocab
            for index in sorted(vocab_nets):
                net = self._net_by_index(index)
                if (net is not None):
                    net.conflict = True
            # per-attempt diagnosis record (stagnation analysis): the
            # conflict total and the nets the next attempt will rip up
            self.conflict_trace.append((
                attempt, conflicts,
                tuple(net.name for net in self.nets if net.conflict)))
            if (conflicts < min_conflict or cnt_conflict == -1):
                cnt_conflict = 0
                min_conflict = conflicts
            else:
                cnt_conflict += 1
            if (cnt_conflict > STALL_ATTEMPTS):
                break
            if (not conflicts or attempt >= max_attempts):
                break
        self.attempts_used = attempt
        if (ok == -1 or conflicts):
            if (ok != -1 and conflicts and self._fail_note is None):
                # honest stagnation note: the negotiation plateaued
                best = min(self.conflict_trace,
                           key=lambda t: (t[1], t[0]))
                self._fail_note = (
                    "no conflict-free routing after %d attempts (best %d "
                    "conflicts at attempt %d; unresolved: %s)"
                    % (attempt, best[1], best[0],
                       ", ".join(best[2]) if best[2] else "-"))
            return False
        # arcs of solved nets become the final solution's arcs
        # (graphrouter.cpp:169-171)
        for arc in self.arcs:
            owner = self.graph[arc.n1].net
            if (owner in solved and arc.label == solved[owner]):
                arc.label = attempt
        self._final_label = attempt
        return True

    # ---------------- RouteResult construction ----------------

    def _stripe_plan(self):
        """(plan, conflicts, conflicted): the per-(slot, column) stripes.

        A net's occupied tracks at a column become a *stripe* (vertical
        metal) only when they form a run of >= 2 tracks or the run touches
        one of the net's diffusion/power access points; a lone point is
        just a horizontal segment endpoint and draws no vertical metal.
        The emitted interval is the solidified occupied run (levels =
        track+1); a GND-family stripe reaches level 0 and a VCC-family
        stripe level BAR_LEVELS-1 (the power ends the contract demands).
        Two qualifying stripes in one slot are inexpressible in the
        RouteResult vocabulary (one owner per slot) and count as conflicts.

        Returns (plan, contested, conflicted): plan maps (c, slot) ->
        (net_index, lo, hi); contested is the set of (c, slot) pairs that
        had competing stripes.
        """
        access = {}
        for net in self.nets + self.power:
            access[net.index] = set(
                nid for nid in net.nodes
                if self.graph[nid].kind[0] == _M1)
        occ = {}
        for net in self.nets + self.power:
            for nid in net.tree:
                kind = self.graph[nid].kind
                if (kind[0] == _M1):
                    occ.setdefault((net.index, kind[2]), set()).add(kind[1])
        plan = {}
        contested = set()
        conflicted = set()
        for nidx, c in sorted(occ):
            tracks = occ[(nidx, c)]
            for slot, (lo_t, hi_t) in enumerate(
                    ((0, BOUNDARY_T), (BOUNDARY_T, N_TRACKS - 1))):
                run = sorted(t for t in tracks if lo_t <= t <= hi_t)
                if (not run):
                    continue
                if (len(run) < 2 and not any(
                        self._m1(t, c) in access[nidx] for t in run)):
                    continue
                name = self._net_name(nidx)
                lo = 0 if name in GND_NAMES else run[0] + 1
                hi = BAR_LEVELS - 1 if name in VCC_NAMES else run[-1] + 1
                prev = plan.get((c, slot))
                if (prev is None):
                    plan[(c, slot)] = (nidx, lo, hi)
                elif (prev[0] != nidx):
                    contested.add((c, slot))
                    conflicted.update((prev[0], nidx))
                    if (nidx < prev[0]):
                        plan[(c, slot)] = (nidx, lo, hi)
        return plan, contested, conflicted


    def build_result(self):
        """Build the RouteResult-compatible solution from the trees."""
        width = self.width_cols
        hseg = {}
        pj = {}
        m2 = {}
        via = {}
        for net in self.nets:               # sorted-name order
            mine = set(net.tree)
            for t in range(N_TRACKS):
                for c in range(width - 1):
                    if (self._m1(t, c) in mine
                            and self._m1(t, c + 1) in mine):
                        hseg[(t, c)] = net.name
                    elif (self._node((_M2, t, c)) in mine
                          and self._node((_M2, t, c + 1)) in mine):
                        hseg[(t, c)] = net.name
                        m2[(t, c)] = True
                    elif (t in ROW_TRACKS
                          and self._node((_PJ, t, c)) in mine
                          and self._node((_PJ, t, c + 1)) in mine):
                        hseg[(t, c)] = net.name
                        pj[(t, c)] = True
            for t in range(N_TRACKS):
                for c in range(1, width - 1):
                    if (self._m1(t, c) in mine
                            and self._node((_M2, t, c)) in mine):
                        via[(t, c)] = True
        owner_n = [None] * width
        owner_p = [None] * width
        lo_n = [0] * width
        hi_n = [0] * width
        lo_p = [BAR_LEVELS - 1] * width
        hi_p = [BAR_LEVELS - 1] * width
        reachB_n = [False] * width
        reachB_p = [False] * width
        plan, _contested, _conflicted = self._stripe_plan()
        for (c, slot), (nidx, lo, hi) in sorted(plan.items()):
            name = self._net_name(nidx)
            if (slot == 0):
                owner_n[c], lo_n[c], hi_n[c] = name, lo, hi
                reachB_n[c] = hi == BOUNDARY_T + 1
            else:
                owner_p[c], lo_p[c], hi_p[c] = name, lo, hi
                reachB_p[c] = lo == BOUNDARY_T + 1
        vseg = sum(1 for o in owner_n if o is not None) \
            + sum(1 for o in owner_p if o is not None)
        cost = (sum(1 for k in hseg if not m2.get(k) and not pj.get(k))
                * H_MET_COST
                + sum(1 for k in hseg if m2.get(k)) * M2_H_COST
                + sum(1 for k in hseg if pj.get(k)) * POLY_ARC_COST
                + len(via) * VIA_COST)
        result = RouteResult(
            "FEASIBLE", owner_n, owner_p, lo_n, hi_n, lo_p, hi_p,
            hseg, pj, m2, via, reachB_n, reachB_p, width, len(hseg),
            vseg, len(pj), len(m2), len(via))
        result.route_cost = cost
        result.attempts_used = getattr(self, "attempts_used", 0)
        return result

    def failed_result(self):
        """RouteResult-shaped failure, mirroring solve_routing's.

        Unlike solve_routing's empty-shell failure the width is the real
        placement width: verify and the benchmark derive access columns
        from the PLACEMENT, so a 0-width result crashes them with an
        IndexError instead of letting them report the honest violations
        (route_model RouteResult.stripes indexes col_owner_n[c]).  Every
        column is reported unrouted (no stripes, no segments).
        """
        width = self.width_cols
        result = RouteResult(
            "UNKNOWN",
            [None] * width, [None] * width,
            [0] * width, [0] * width,
            [BAR_LEVELS - 1] * width, [BAR_LEVELS - 1] * width,
            {}, {}, {}, {},
            [False] * width, [False] * width,
            width, 0, 0, 0, 0, 0)
        result.fail_note = self._fail_note
        result.attempts_used = getattr(self, "attempts_used", 0)
        return result


def route_cell(netlist, placement, width_cols, leg_widths=None,
               height_um=2.47, grid_um=0.19, max_attempts=MAX_ATTEMPTS):
    """Route one placed cell; returns a RouteResult (solve_routing's type).

    ``netlist`` is a smt_engine CellNetlist, ``placement`` maps
    Device -> PlacedTransistor (smt_engine's IR), ``width_cols`` is the
    placement width in 0.19 um columns and ``leg_widths`` the fold map
    (device name -> (legs, leg_width_cols)); the fold is already realized
    in the placement, so the router consumes it for provenance only.

    Invariant: the returned RouteResult always covers every placement
    column -- ``width_cols >= max(p.end_col for p in placement.values())``
    -- success and failure alike, so consumers deriving columns from the
    placement (verify_cell, the benchmark) never index past the result.
    """
    del leg_widths                        # the fold lives in the placement
    # the route must cover every placement column (verify derives its
    # access columns from the placement): never route on a narrower grid
    # than the widest device end
    width_cols = max(width_cols,
                     max((p.end_col for p in placement.values()), default=0))
    grid = _RouteGrid(netlist, placement, width_cols,
                      height_um=height_um, grid_um=grid_um)
    if (grid.route(max_attempts=max_attempts)):
        return grid.build_result()
    return grid.failed_result()


def route_signature(route):
    """Canonical serialization of a RouteResult for determinism checks."""
    parts = [route.status_name, str(route.width_cols)]
    for c in range(route.width_cols):
        parts.append("%s|%s|%s|%s|%s|%s|%s" % (
            route.col_owner_n[c], route.lo_n[c], route.hi_n[c],
            route.col_owner_p[c], route.lo_p[c], route.hi_p[c],
            route.reachB_n[c] if c < len(route.reachB_n) else "-"))
    for key in sorted(route.hseg):
        parts.append("h%s=%s" % (key, route.hseg[key]))
    for key in sorted(route.pj):
        if (route.pj[key]):
            parts.append("p%s" % (key,))
    for key in sorted(route.m2):
        if (route.m2[key]):
            parts.append("m%s" % (key,))
    for key in sorted(route.via):
        if (route.via[key]):
            parts.append("v%s" % (key,))
    return "\n".join(parts)
