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
The reconstruction CHECKS itself against the die's device-level
adjacency and, for TREE arrangements no orientation of the pristine
decomposition explains (bigcell_engine.netlist_ext's tree blocks, which
rearrange which device sits at which block boundary), rebuilds the view
from the device trails -- the phantom "terminal clash at ('M1', 4, 1):
cl3#Y and VCC" class that blocked the 22-36T COMPLEX cells came from
exactly this gap.  ``blocks`` (the orientation-aware view the placement
was built from, engine meta["blocks"]) can be forwarded to
route_cell/die_view to override the trail where the die is ambiguous --
but ONLY do so once the verifier consumes the same view
(smt_engine.verify derives its slot-model requirements from a
blocks-less die_view call, so a blocks-wired router could disagree with
its verifier on a die-ambiguous single's flip); the production engine
therefore routes without blocks and stays in exact agreement.

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

route_cell runs the negotiation in TWO phases: phase 1 is this router
byte for byte as it was before the metal2 freedom (no M2 vertical arcs,
the both-side via rule, the forced dual fill), so every cell that closed
before keeps its exact route; only a phase-1 stall rebuilds the grid
with the freedom (below) and re-routes from scratch.  Since the 2026-10
runtime tuning, the static diagnosis below ALSO gates phase 1: when it
reports a contested corridor column or a caged terminal on the phase-1
grid (a proven floor of the pre-freedom vocabulary), the doomed
phase-1 negotiation is skipped and phase 2 runs directly -- provenance
lands on the RouteResult (``phase1_skipped`` / ``phase1_skip_reason``),
never in the fail_note.

Residual structural class: the corridor-locked terminal
-------------------------------------------------------
The slot-router residuals that survive every mirror/decomposition
variant (measured on the benchmark's COMPLEX plateau cells) share one
anatomy.  The 9-level bar domain gives each column exactly ONE N<->P
crossover level: the boundary track T3.  Every power stripe is forced to
an interval that spans its half of the domain (a GND access on row rail
1 covers T0-T2, a VCC access on rail 2 covers T4-T6 -- the power-end
contract leaves no choice), so at every power-access column T3 is the
only free track.  A diffusion access whose left/right/up/down M1
neighbours are all power-walled then has exactly one escape -- the
corridor node (T3, c) -- and a gate-only net whose crossing tracks are
power-walled except T3 has its crossing endpoints forced there too.
When two nets' forced demands land on the same corridor node, one of
them must yield a negotiated conflict per contested node; that count is
the domain's floor for the placement, not a search failure -- the exact
CP-SAT model (smt_engine.route_model, the same RouteResult vocabulary)
returns INFEASIBLE on all three plateau placements under the shared
die-slot accesses, and adding a second corridor track (8 tracks / 10
bar levels, probed) does NOT lift it: the yielding-free transition's
solidified stripe sweeps the whole corridor band at its transition
column, so the drawn metal -- not the node count -- is the wall.

The freedom ASTRAN uses here is its metal2 z-layer, and this router now
has it: the C++ router is a 3D grid (designmng.cpp:454 setup(..., 3))
whose layer costs (router.cpp:53-55) are M1 h=11/v=4, M2 h=4/**v=11**
and via-up 4 at any node -- M2 track changes and node-level vias are
first-class moves.  The graph carries M1<->M2 via arcs at every node
(they always did) plus M2 vertical arcs (M2_V_COST, appended after the
M1 arcs so pre-existing arc order -- the A* tie-break -- is preserved),
and the vocabulary was extended to match: a node via (m2via) joins the
net's M1 point (stripe landing, segment endpoint or terminal) to its
metal2 at one point, and an M2 span (m2v) occupies one column across a
track range -- the via-up/M2-hop/via-down track change.  The negotiated
post-pass rule (d) accepts both via forms and bumps dead-side pairs; a
power-walled access point lifts onto M2 through its own stripe and
crosses the wall above the metal that walled it.  When the negotiation
still plateaus, :meth:`structural_diagnosis` names the contested
corridor nodes and the walled terminals on every failure so the plateau
note says WHICH freedom is still missing (the residual class is now a
contest M2 cannot dissolve -- e.g. a gate contact whose only crossing
tracks are foreign power metal, which M2 cannot lift because M2 never
touches gates).

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
M2_V_COST = 11              # Router::setup, router.cpp:53-55 (M2 v-cost):
                            # the metal2 track-change arcs -- via-up at any
                            # node (4), M2 vertical hop (11), via-down (4)
VIA_COST = 4                # Router::setup, router.cpp:23-24 (up-cost)

GND_NAMES = ("GND", "VSS")
VCC_NAMES = ("VCC", "VDD")
POWER_NAMES = GND_NAMES + VCC_NAMES

# row of each diffusion row-track (verify.py:40 ROW_OF_TRACK)
_ROW_OF_TRACK = {0: (False, 0), 2: (False, 1), 4: (True, 0), 6: (True, 1)}

_M1, _M2, _PJ, _G, _HUB, _PIN = "M1", "M2", "PJ", "G", "HUB", "PIN"

#: default for the per-net precomputed _allow image (a net with no denied
#: poly-jump point): one shared empty frozenset, never mutated
_EMPTY_FROZEN = frozenset()


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


def _die_orientation(netlist, placement, break_cols=BREAK_GAP_COLS,
                     blocks=None):
    """Per-device die orientation: {device name: (left_net, right_net)}.

    The reconstruction (multi-member mirror detection + the
    abutment-gap fixpoint for singles, pristine where the die cannot
    distinguish) lives in smt_engine.die_view -- the SHARED view the
    verifier's access derivation consumes too, so both engines always
    agree on which net sits at which terminal column.  This adapter
    keeps the router-local signature.  ``blocks`` (the orientation-aware
    block view the placement was built from, bigcell_engine.engine's
    meta["blocks"]) is forwarded for die_view's tree-arrangement
    fallback; on every placement the pristine model explains it changes
    nothing (byte-identical).
    """
    return die_view.die_orientation_map(netlist, placement, break_cols,
                                        blocks)


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
                 height_um=2.47, grid_um=0.19, metal2_verticals=True,
                 blocks=None):
        self.netlist = netlist
        self.placement = placement
        # the orientation-aware block view the placement was built from
        # (bigcell_engine.engine meta["blocks"]), forwarded to die_view's
        # tree-arrangement fallback; None keeps the pure reconstruction
        self.blocks = blocks
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
        # the metal2 vertical freedom (router.cpp:53-55): via-up at any
        # node, M2 vertical hops, via-down -- plus the negotiated rules
        # that consume it (the node-via via form, the M2-bridge dual
        # fill skip).  Phase 1 of route_cell runs WITHOUT it: the graph
        # and the negotiation are then byte-for-byte the pre-freedom
        # router, so every cell that closed before keeps its exact
        # route (AGENTS.md invariant 8/9 determinism discipline).
        self.metal2_verticals = metal2_verticals
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
        # reverse tree-membership index (performance only; see
        # _index_add/_index_discard): {node id: {net index}} -- the exact
        # reverse of {net: net.tree} over self.nets + self.power, kept in
        # lockstep with every tree mutation so the foreign-tree membership
        # tests in _complete_junctions/_claimable are O(1) instead of a
        # full scan of every other net's tree per net per attempt.  Trees
        # are duplicate-free lists (every append is guarded by a seen-set:
        # _bfs_route's visited, _complete_junctions' mine, _solidify's
        # have), so add/discard pairs stay balanced; the trees themselves
        # remain the only truth -- the index never feeds a decision the
        # trees contradict, so behaviour is byte-identical.
        self._rev = {}
        for net in self.nets + self.power:
            for nid in net.tree:
                self._index_add(nid, net.index)
        # static power-tree sets for _post_pass (built lazily on first
        # use; power trees never change after _build)
        self._power_tree_sets = None
        self._net_by_idx = {net.index: net for net in self.nets}
        self._prepare_hot()

    def _prepare_hot(self):
        """Precomputed lookup structures for the negotiation's hot loops.

        Pure images of build-time state -- nodes and arcs are never
        created or rewired after _build -- so every table read below is
        exactly the dict lookup it replaces and the solver's decisions
        (arc order = the A* tie-break, pushed heap tuples, bump
        multisets) stay byte-for-byte the pre-tuning ones:

        - _m1_tab/_m2_tab: [track][col] -> node id (the full (t, c)
          domain is materialized by _build);
        - _pj_tab: {row track: [col] -> node id} (same);
        - _adj: node id -> tuple of (neighbour, arc cost, arc index) in
          the node's own arc order -- the BFS arc loop with the neighbour
          side pre-resolved;
        - _pj_denied: net name -> frozenset of PJ node ids _allow rejects
          for it (poly-span blocks and field/gate legality are static
          per (net, point));
        - _name_by_index: net index -> name (the _net_name linear scan,
          cached).
        """
        width = self.width_cols
        idmap = self._id
        self._m1_tab = [[idmap[(_M1, t, c)] for c in range(width)]
                        for t in range(N_TRACKS)]
        self._m2_tab = [[idmap[(_M2, t, c)] for c in range(width)]
                        for t in range(N_TRACKS)]
        self._pj_tab = {t: [idmap[(_PJ, t, c)] for c in range(width)]
                        for t in sorted(ROW_TRACKS)}
        adj = [None] * len(self.graph)
        arcs = self.arcs
        for nid, node in enumerate(self.graph):
            row = []
            for ai in node.arcs:
                arc = arcs[ai]
                row.append((arc.n2 if arc.n1 == nid else arc.n1,
                            arc.cost, ai))
            adj[nid] = tuple(row)
        self._adj = adj
        # _allow's per-net verdict for every poly-jump point, precomputed:
        # denied(net, pj) <=> (spanning and spanning != {net}) or
        # (not field and not (net has a gate at the column)).  The
        # ``(t, c) not in _poly_span`` arm of _allow is dead -- the PJ
        # node domain IS _poly_span's domain -- and the assert pins it.
        assert len(self._poly_span) == len(ROW_TRACKS) * width
        gate_at = set()
        for gname, cols in self.gate_nets_at.items():
            for c in cols:
                gate_at.add((gname, c))
        denied = {}
        for (t, c), spanning in self._poly_span.items():
            pid = idmap[(_PJ, t, c)]
            field_ok = c in self.field[t]
            for net in self.nets:
                if ((spanning and spanning != frozenset((net.name,)))
                        or (not field_ok and (net.name, c) not in gate_at)):
                    s = denied.get(net.name)
                    if (s is None):
                        denied[net.name] = {pid}
                    else:
                        s.add(pid)
        for net in self.nets:
            denied.setdefault(net.name, ())
        self._pj_denied = {name: frozenset(s)
                           for name, s in denied.items()}
        self._name_by_index = {net.index: net.name
                               for net in self.nets + self.power}

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
        # the linear scan over nets+power is cached in _name_by_index
        # (identical outputs: indexes are unique across both registries)
        name = self._name_by_index.get(index)
        return name if (name is not None) else "?%d" % index

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
                netlist, placement, break_cols=BREAK_GAP_COLS,
                blocks=self.blocks)
        else:
            orientation = _die_orientation(netlist, placement,
                                           blocks=self.blocks)
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
        # M2 vertical arcs (router.cpp:53-55, M2 v-cost): the metal2
        # track-change freedom -- via-up at any node (the M1<->M2 arcs
        # above), M2 vertical hops, via-down anywhere.  Appended after
        # the M1 arcs so every pre-existing arc index (and the per-node
        # arc order the A* tie-break consumed) is preserved: routes that
        # cannot profit from metal2 stay byte-identical.  Phase 1
        # (metal2_verticals=False) builds the pre-freedom graph.
        if self.metal2_verticals:
            for t in range(1, N_TRACKS):
                for c in range(width):
                    self._add_arc(self._node((_M2, t - 1, c)),
                                  self._node((_M2, t, c)), M2_V_COST)
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
        # its last route -- the share is with that tree either way.  The
        # reverse index (self._rev, maintained at every tree mutation)
        # answers the same membership in O(1): _foreign_member(nid,
        # net.index) is exactly the old foreign_tree's ``nid in ...`` over
        # a fresh scan of every other net's tree.
        adds = []
        crossed_g = set()
        m1_tab, m2_tab = self._m1_tab, self._m2_tab
        pj_tab = self._pj_tab
        width = self.width_cols
        for nid in net.tree:
            kind = self.graph[nid].kind
            if (kind[0] != _G):
                continue
            c, gname = kind[1], kind[2]
            for t in self.gate_tracks.get((gname, c), ()):
                if (m1_tab[t][c] in mine):
                    adds.append((m1_tab[t][c + 1], m1_tab[t][c]))
                    crossed_g.add(nid)
                    break
                if (t in ROW_TRACKS
                        and pj_tab[t][c] in mine):
                    adds.append((pj_tab[t][c + 1], pj_tab[t][c]))
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
                    net, kind[2], kind[1], mine)
                if (fallback is not None):
                    adds.extend(fallback)
        # via completion (tree-collected M2 points, sorted -- the exact
        # (t, c) order the full-grid scan enumerated, which fixes which
        # triggering pair credits a doubly-demanded endpoint first; the
        # id tables replace the tuple-dict lookups)
        pts = []
        for nid in net.tree:
            kind = self.graph[nid].kind
            if (kind[0] == _M2):
                pts.append((kind[1], kind[2]))
        for t, c in sorted(pts):
            m1c, m2c = m1_tab[t][c], m2_tab[t][c]
            if (m1c not in mine):
                continue
            if (c > 0 and m1_tab[t][c - 1] in mine
                    and c + 1 < width):
                adds.append((m2_tab[t][c + 1], m1c))
            elif (c > 0 and m2_tab[t][c - 1] in mine
                  and c + 1 < width):
                adds.append((m1_tab[t][c + 1], m2c))
            elif (c + 1 < width and m1_tab[t][c + 1] in mine
                  and c > 0):
                adds.append((m2_tab[t][c - 1], m1c))
            elif (c + 1 < width
                  and m2_tab[t][c + 1] in mine and c > 0):
                adds.append((m1_tab[t][c - 1], m2c))
        bumps = []
        for nid, trigger in adds:
            if (nid in mine):
                continue
            mine.add(nid)
            net.tree.append(nid)
            self._index_add(nid, net.index)
            onet = self.graph[nid].net
            if (onet not in (-1, net.index)
                    or self._foreign_member(nid, net.index)):
                bumps.append(trigger)
        return bumps

    def _gate_crossing_fallback(self, net, gname, c, mine):
        """Crossing endpoints for one un-crossed tree gate (slot model).

        Returns [(new_node, trigger_node), ...] or None.  Poly jump
        first, M1 second; the smallest qualifying track wins.  Both
        endpoints must be claimable by ``net`` (unowned or already its
        own, and not living in another net's tree -- _claimable, served
        from the reverse index).
        """
        for t in self.gate_tracks.get((gname, c), ()):
            if (t in ROW_TRACKS and c + 1 < self.width_cols
                    and (c + 1) in self.field[t]
                    and self._poly_span[(t, c)] <= frozenset((net.name,))
                    and self._claimable(self._node((_PJ, t, c)), net, mine)
                    and self._claimable(self._node((_PJ, t, c + 1)), net,
                                        mine)):
                g = self._node((_G, c, gname))
                return [(self._node((_PJ, t, c + 1)), g),
                        (self._node((_PJ, t, c)), g)]
        for t in self.gate_tracks.get((gname, c), ()):
            if (c + 1 < self.width_cols
                    and self._claimable(self._m1(t, c), net, mine)
                    and self._claimable(self._m1(t, c + 1), net, mine)):
                g = self._node((_G, c, gname))
                return [(self._m1(t, c), g), (self._m1(t, c + 1), g)]
        return None

    def _index_add(self, nid, nidx):
        """Record nid as a member of net nidx's tree (see __init__)."""
        members = self._rev.get(nid)
        if (members is None):
            self._rev[nid] = {nidx}
        else:
            members.add(nidx)

    def _index_discard(self, nid, nidx):
        """Drop nid from net nidx's tree membership (see __init__)."""
        members = self._rev.get(nid)
        if (members is not None):
            members.discard(nidx)
            if (not members):
                del self._rev[nid]

    def _index_rebuild(self):
        """Recompute the reverse tree-membership index from the trees."""
        rev = {}
        for net in self.nets + self.power:
            nidx = net.index
            for nid in net.tree:
                members = rev.get(nid)
                if (members is None):
                    rev[nid] = {nidx}
                else:
                    members.add(nidx)
        self._rev = rev

    def _foreign_member(self, nid, nidx):
        """Whether some OTHER net's tree contains nid (the old
        foreign_tree membership test, served from the reverse index)."""
        members = self._rev.get(nid)
        return (members is not None
                and (len(members) > 1 or nidx not in members))

    def _claimable(self, nid, net, mine):
        """Whether ``net`` may take ``nid`` without a permanent conflict.

        Unowned-or-own point that lives in no other net's tree (the
        reverse-index form of the old foreign_tree membership test)."""
        node = self.graph[nid]
        if (node.net not in (-1, net.index)):
            return False
        members = self._rev.get(nid)
        return (members is None
                or (len(members) == 1 and net.index in members))

    def _bfs_route(self, net, tree, label, attempt, max_cost=0,
                   definitive=True, strict=False):
        """GraphRouter::bfsRoute / bfsRoute2 (graphrouter.cpp:285-426).

        Multi-source A* from the current tree to the closest not-yet-tree
        terminal.  Deterministic priority queue: (cost, node id, insertion
        counter).  Returns the path cost or -1 when no path exists.

        Performance: this is the negotiation's inner loop (one search per
        terminal per re-routed net per attempt), so the relaxation runs on
        the precomputed neighbour tuples (self._adj), the inlined
        GraphRouter::calcCost and the precomputed _allow image
        (self._pj_denied) -- all pure build-time data, so the pushed
        tuples, and with them the pop order and the resulting paths, are
        exactly the pre-tuning ones.
        """
        graph = self.graph
        adj = self._adj
        target = net.index
        denied = self._pj_denied.get(net.name, _EMPTY_FROZEN)
        attempt1 = attempt == 1
        # local bindings for the ~1e8-iteration inner loop: pure accessor
        # aliases, no behavioural change (the heap discipline -- seed
        # heapify, then append + heappop -- is kept EXACTLY; it is not a
        # min-first queue, and the whole solver's byte-identity rides on
        # its precise pop sequence)
        heappop = heapq.heappop
        trace = {}                          # node -> (father, arc)
        visited = set(tree)
        heap = []
        push = heap.append
        seq = 0
        for nd in tree:
            push((0, nd, seq, -1, -1))
            seq += 1
        heapq.heapify(heap)
        found = -1
        found_cost = 0
        while heap:
            cost, node, _seq, father, arc_id = heappop(heap)
            gnode = graph[node]
            if (father != -1 and node in visited):
                # stale duplicate: the C++ loop condition still tests it
                if (gnode.net == target):
                    found, found_cost = node, cost
                    break
                continue
            if (father != -1):
                visited.add(node)
                trace[node] = (father, arc_id)
                if (gnode.net == target):
                    found, found_cost = node, cost
                    break
            for other, acost, arc_idx in adj[node]:
                if (other in visited):
                    continue
                onode = graph[other]
                onet = onode.net
                if (onode.source and onet != target):
                    continue                # foreign terminal: always blocked
                if (strict and onet != -1 and onet != target):
                    continue                # bfsRoute2: overlap-free
                # arc.lock_net is never assigned anywhere (graphrouter.h
                # t_arc, unused here), so the C++ lock filter is a
                # constant pass-through -- no branch needed
                if (other in denied):
                    continue                # the _allow rule, precomputed
                if (attempt1):
                    ncost = cost + acost + onode.history
                else:
                    ncost = (cost + acost
                             + onode.history * (onode.nr_nets + 1))
                if (max_cost and ncost > max_cost):
                    continue
                push((ncost, other, seq, node, arc_idx))
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
            if (tree is net.tree):
                # a definitive grow appends to the net's own tree: the
                # reverse index must follow (_prim passes a LOCAL tree and
                # is excluded by the identity test)
                self._index_add(node, target)
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
        A same-net dual (both slots) historically merged through the T3
        boundary track (verify.py's dual-column rule); with the metal2
        vertical freedom a column whose own M2 run already bridges the
        slots (a contiguous M2 run covering tracks on both sides of T3)
        is a SECOND N<->P crossover, so the forced T3 sweep is skipped --
        it would only consume the corridor node another net's gate
        contact needs.  Nets without M2 geometry keep the historical
        fill byte for byte.
        """
        cols = {}
        m2cols = {}
        for nid in net.tree:
            kind = self.graph[nid].kind
            if (kind[0] == _M1):
                cols.setdefault(kind[2], set()).add(kind[1])
            elif (kind[0] == _M2):
                m2cols.setdefault(kind[2], set()).add(kind[1])
        have = set(net.tree)
        for c in sorted(cols):
            tracks = cols[c]
            n_side = sorted(t for t in tracks if t <= BOUNDARY_T)
            p_side = sorted(t for t in tracks if t >= BOUNDARY_T)
            fill = []
            if (n_side and p_side):
                if (self.metal2_verticals
                        and self._m2_bridges_slots(m2cols.get(c, ()), net)):
                    # the column's own M2 run joins the halves: keep the
                    # corridor node free (phase 2 only -- phase 1 keeps
                    # the historical forced sweep byte for byte)
                    fill.extend(range(n_side[0], n_side[-1] + 1))
                    fill.extend(range(p_side[0], p_side[-1] + 1))
                else:
                    fill.extend(range(n_side[0], BOUNDARY_T + 1))
                    fill.extend(range(BOUNDARY_T, p_side[-1] + 1))
            elif (n_side):
                fill.extend(range(n_side[0], n_side[-1] + 1))
            elif (p_side):
                fill.extend(range(p_side[0], p_side[-1] + 1))
            m1_tab = self._m1_tab
            for t in fill:
                nid = m1_tab[t][c]
                if (nid not in have):
                    have.add(nid)
                    net.tree.append(nid)
                    self._index_add(nid, net.index)

    def _m2_bridges_slots(self, tracks, net):
        """Whether the net's M2 nodes at one column form a contiguous run
        covering tracks on both sides of the T3 boundary -- a drawn M2
        crossover between the N and P halves."""
        m2t = sorted(tracks)
        if (not m2t):
            return False
        start = prev = m2t[0]
        for t in m2t[1:] + [None]:
            if (t == prev + 1):
                prev = t
                continue
            if (start < prev and start <= BOUNDARY_T <= prev):
                return True
            if (t is None):
                break
            start = prev = t
        return False


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
        self._index_rebuild()

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
                        self._index_discard(nid, net.index)
                    net.tree = []
                    if (len(net.nodes) > 2):
                        nr_steiners += self._add_steiner(net, self._label)
                    net.tree = [net.nodes[0]]
                    self._index_add(net.nodes[0], net.index)
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
        # power stripes participate in node conflicts (immovable
        # occupancy); their trees are static after _build, so the sets
        # are built once and reused (identical content; every consumer
        # below is membership-only or order-independent -- rule (a)
        # iterates the sorted index keys)
        if (self._power_tree_sets is None):
            self._power_tree_sets = {net.index: frozenset(net.tree)
                                     for net in self.power}
        tree_set.update(self._power_tree_sets)

        def bump(nid):
            bumps.append(nid)

        # the precomputed id tables serve every rule below (pure images
        # of _build; same node ids the _m1/_node lookups returned)
        width = self.width_cols
        m1_tab, m2_tab = self._m1_tab, self._m2_tab
        pj_tab = self._pj_tab

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
                bump(m1_tab[t][c])

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
                    if (m1_tab[t][c] in mine
                            and m1_tab[t][c + 1] in mine):
                        ok = True
                        break
                    if (t in ROW_TRACKS
                            and pj_tab[t][c] in mine
                            and pj_tab[t][c + 1] in mine):
                        ok = True
                        break
                if (not ok):
                    conflicts += 1
                    conflicted.add(net.index)
                    # bump the merge points the net actually used at the
                    # gate column so the negotiation moves the crossing
                    for t in self.gate_tracks.get((gname, c), ()):
                        if (m1_tab[t][c] in mine):
                            bump(m1_tab[t][c])
                        if (t in ROW_TRACKS
                                and pj_tab[t][c] in mine):
                            bump(pj_tab[t][c])
                    # a gate-only net's tree holds no crossing points at
                    # all (its only terminal is the gate node), so the
                    # bumps above price nothing; without pricing the
                    # BLOCKERS the occupying net never yields and the
                    # crossing stalls forever.  Bump every candidate
                    # contact point another net occupies or parks in,
                    # and mark those nets conflicted: GraphRouter rips
                    # up only conflicted nets, so a blocker that shares
                    # no node with the violating net would otherwise
                    # keep its tree (and its parked points) forever.
                    # Phase 2 only: the pre-freedom negotiation never
                    # marked blockers, and previously-closing cells must
                    # keep their exact dynamics.
                    if (not self.metal2_verticals):
                        continue
                    for t in self.gate_tracks.get((gname, c), ()):
                        for cc in (c, c + 1):
                            if (not (0 <= cc < self.width_cols)):
                                continue
                            cands = [m1_tab[t][cc]]
                            if (t in ROW_TRACKS):
                                cands.append(pj_tab[t][cc])
                            for nid in cands:
                                blockers = [u for u in
                                            owner_nets.get(nid, ())
                                            if (u != net.index)]
                                if (blockers):
                                    conflicted.update(blockers)
                                    bump(nid)

        # (d) an M1|M2 pair at one point is a real via in one of two
        # forms: the BOTH-SIDE segment form (the old vocabulary -- M1
        # segment on one side of the column, M2 segment on the other,
        # edge columns excluded) or the NODE-VIA form (the metal2
        # freedom, router.cpp:53-55 via-up at any node -- both sides own
        # drawable metal at the point: M1 stripe coverage via a vertical
        # neighbour, an M1 segment endpoint or a terminal; an M2 span
        # via a vertical neighbour or an M2 segment endpoint).  A pair
        # with a dead side is dead metal: violation, bumped on both
        # endpoints so the negotiation extends or drops it.
        # Performance: the candidate (t, c) pairs are collected from the
        # net's TREE (a pair needs both points in the tree) and walked in
        # sorted (t, c) order -- the identical enumeration the full-grid
        # scan produced -- with the precomputed id tables replacing the
        # tuple-dict lookups; the violation set is unchanged.
        for net in self.nets:
            mine = tree_set[net.index]
            node_m1 = set(nid for nid in net.nodes
                          if self.graph[nid].kind[0] == _M1)
            pairs = []
            for nid in net.tree:
                kind = self.graph[nid].kind
                if (kind[0] == _M2):
                    pairs.append((kind[1], kind[2]))
            for t, c in sorted(pairs):
                m2c = m2_tab[t][c]
                m1c = m1_tab[t][c]
                if (m1c not in mine):
                    continue
                if (c > 0 and c < width - 1
                        and ((m1_tab[t][c - 1] in mine
                              and m2_tab[t][c + 1] in mine)
                             or (m2_tab[t][c - 1] in mine
                                 and m1_tab[t][c + 1] in mine))):
                    continue            # both-side segment via
                if (not self.metal2_verticals):
                    # phase 1: the pre-freedom rule -- an M1|M2 pair
                    # must be a both-side segment via
                    conflicts += 1
                    conflicted.add(net.index)
                    bump(m2c)
                    continue
                m1_real = (
                    (c > 0 and m1_tab[t][c - 1] in mine)
                    or (c + 1 < width and m1_tab[t][c + 1] in mine)
                    or (t > 0 and m1_tab[t - 1][c] in mine)
                    or (t + 1 < N_TRACKS and m1_tab[t + 1][c] in mine)
                    or m1c in node_m1)
                m2_real = (
                    (c > 0 and m2_tab[t][c - 1] in mine)
                    or (c + 1 < width and m2_tab[t][c + 1] in mine)
                    or (t > 0 and m2_tab[t - 1][c] in mine)
                    or (t + 1 < N_TRACKS and m2_tab[t + 1][c] in mine))
                if (m1_real and m2_real):
                    continue            # node via: both sides real
                conflicts += 1
                conflicted.add(net.index)
                bump(m1c)
                bump(m2c)

        # (e) poly jump pairs: right end over field oxide (tree-collected
        # PJ points, sorted -- the identical enumeration; see (d))
        field = self.field
        for net in self.nets:
            mine = tree_set[net.index]
            pts = []
            for nid in net.tree:
                kind = self.graph[nid].kind
                if (kind[0] == _PJ):
                    pts.append((kind[1], kind[2]))
            for t, c in sorted(pts):
                right = pj_tab[t][c + 1] if (c + 1 < width) else None
                if (right is not None and right in mine
                        and c + 1 not in field[t]):
                    conflicts += 1
                    conflicted.add(net.index)
                    bump(pj_tab[t][c])
                    bump(right)

        # (f) no M1|M2 double-layer segment (one hseg slot per (t, c));
        # tree-collected M2 points, sorted -- the identical enumeration
        for net in self.nets:
            mine = tree_set[net.index]
            pts = []
            for nid in net.tree:
                kind = self.graph[nid].kind
                if (kind[0] == _M2):
                    pts.append((kind[1], kind[2]))
            for t, c in sorted(pts):
                if (c + 1 < width
                        and m1_tab[t][c] in mine
                        and m1_tab[t][c + 1] in mine
                        and m2_tab[t][c + 1] in mine):
                    conflicts += 1
                    conflicted.add(net.index)
                    bump(m2_tab[t][c])

        # (g) one hseg slot per (t, c): the vocabulary cannot express an
        # M1 segment and a poly/M2 segment of *different* nets in the same
        # slot (same-net double layers are (f); same-layer sharing shows
        # up as point conflicts).  The layer of a net's (t, c) slot keeps
        # the original if/elif priority (M1, then PJ, then M2) via the
        # set differences below, so each net appends at most one entry
        # per slot and the per-slot user lists are exactly the scan's.
        slots = {}
        for net in self.nets:
            mine = tree_set[net.index]
            m1s = set()
            pjs = set()
            m2s = set()
            for nid in net.tree:
                kind = self.graph[nid].kind
                tag = kind[0]
                if (tag == _M1):
                    tc = (kind[1], kind[2])
                    if (tc[1] + 1 < width
                            and m1_tab[tc[0]][tc[1] + 1] in mine):
                        m1s.add(tc)
                elif (tag == _PJ):
                    tc = (kind[1], kind[2])
                    if (tc[1] + 1 < width
                            and pj_tab[tc[0]][tc[1] + 1] in mine):
                        pjs.add(tc)
                elif (tag == _M2):
                    tc = (kind[1], kind[2])
                    if (tc[1] + 1 < width
                            and m2_tab[tc[0]][tc[1] + 1] in mine):
                        m2s.add(tc)
            for tc in m1s:
                slots.setdefault(tc, []).append((net.index, "M1"))
            for tc in pjs - m1s:
                slots.setdefault(tc, []).append((net.index, "PJ"))
            for tc in m2s - m1s - pjs:
                slots.setdefault(tc, []).append((net.index, "M2"))
        for (t, c), users in sorted(slots.items()):
            if (len(users) > 1
                    and len(set(lay for _n, lay in users)) > 1):
                conflicts += 1
                conflicted.update(n for n, _lay in users)
                bump(m1_tab[t][c])

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
        # cached net lookup (the linear scan over self.nets, indexed --
        # identical result; only signal nets are ever requested here)
        return self._net_by_idx.get(index)

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
        self._index_rebuild()
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
                        self._index_discard(nid, net.index)
                    net.tree = [net.nodes[0]]
                    self._index_add(net.nodes[0], net.index)
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
                        self._fail_note += self._structural_note()
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
                self._fail_note += self._structural_note()
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
                        self._m1_tab[t][c] in access[nidx] for t in run)):
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

    # ---------------- structural freedom diagnosis ----------------

    def _static_term_owner(self):
        """{node id: net index} for every BUILD-TIME terminal (diffusion
        accesses, gates, pins, power stripes) -- net.nodes holds
        source==1 nodes only and survives the solver's resets, so this
        is negotiation-independent static geometry."""
        owner = {}
        for net in self.nets + self.power:
            for nid in net.nodes:
                owner[nid] = net.index
        return owner

    def _m1_landing_real(self, nid, seen):
        """Whether the M1 point ``nid`` can host a node via's landing in
        the over-approximated cage: a build-time terminal (its access
        stripe is drawn) or an M1 neighbour already reached (a segment
        endpoint or a solidified stripe run) -- the same realness rule
        the negotiated post-pass's node-via form uses."""
        if (nid in self._term_owner):
            return True
        kind = self.graph[nid].kind
        t, c = kind[1], kind[2]
        for dc in (-1, 1):
            side = self._id.get((_M1, t, c + dc))
            if (side is not None and side in seen):
                return True
        for dt in (-1, 1):
            side = self._id.get((_M1, t + dt, c))
            if (side is not None and side in seen):
                return True
        return False

    def _cage(self, xidx, start, banned=frozenset()):
        """Least fixpoint of the nodes net ``xidx`` can physically occupy
        starting from ``start``: M1 / M2 / poly / gate arcs over nodes
        that are no foreign build-time terminal and not ``banned``.

        Hubs and pins are excluded: a hub hop is either the pin stub or
        a same-column vertical whose drawn stripe consumes the corridor
        node anyway, so it never substitutes for a corridor crossing.
        Metal2 moves within the layer are free (horizontal segments and
        vertical spans are always drawable); entering the layer through
        a node via requires the M1 landing to be real (terminal, segment
        endpoint or stripe run -- :meth:`_m1_landing_real`).  This can
        only OVER-state reachability -- the diagnosis may miss a contest
        but never invents one.  The fixpoint is monotone, hence unique
        and independent of the work order (determinism, invariant 9)."""
        owner = self._term_owner
        seen = {start}
        work = [start]
        while work:
            nid = work.pop()
            for ai in self.graph[nid].arcs:
                arc = self.arcs[ai]
                other = arc.n2 if arc.n1 == nid else arc.n1
                if (other in seen or other in banned):
                    continue
                kind = self.graph[other].kind
                if (kind[0] in (_HUB, _PIN)):
                    continue
                if (owner.get(other, xidx) != xidx):
                    continue            # foreign terminal (static)
                if (kind[0] == _M2 and nid == self._id.get(
                        (_M1, kind[1], kind[2]))
                        and not self._m1_landing_real(nid, seen)):
                    continue            # via door: landing not drawable
                seen.add(other)
                work.append(other)
                if (kind[0] == _M1):
                    # entering an M1 node can open the via door of
                    # already-seen same-track M2 nodes
                    twin = self._id.get((_M2, kind[1], kind[2]))
                    if (twin is not None and twin in seen
                            and twin != nid):
                        work.append(twin)
        return seen

    def _term_label(self, nid):
        """Human-readable terminal descriptor for the diagnosis notes."""
        kind = self.graph[nid].kind
        if (kind[0] == _G):
            return "gate contact @col %d" % kind[1]
        if (kind[0] == _M1):
            return "diffusion access @col %d track %d" % (kind[2], kind[1])
        return str(kind)

    def _gate_forced(self, xidx, name):
        """Corridor demands of a net's gate contacts: for each gate node,
        the crossing tracks that survive the static walls (M1: both
        endpoint nodes unowned by foreign nets; poly: row track over
        field with no foreign gate stripe).  Only when the corridor is
        the sole survivor is the crossing forced.  Applied to EVERY
        net's gates (verify's rule (c) demands a crossing for each):
        the crossing segment claims both endpoint nodes, and M2 cannot
        lift it -- a gate contact is an M1/poly touch."""
        demands = {}
        mine = sorted(nid for nid, o in self._term_owner.items()
                      if o == xidx)
        for nid in mine:
            kind = self.graph[nid].kind
            if (kind[0] != _G):
                continue
            c, gname = kind[1], kind[2]
            if (c + 1 >= self.width_cols):
                continue
            legal = []
            for t in self.gate_tracks.get((gname, c), ()):
                m1_ok = all(
                    self._term_owner.get(self._id.get((_M1, t, cc)),
                                         xidx) == xidx
                    for cc in (c, c + 1))
                pj_ok = (t in ROW_TRACKS
                         and (c + 1) in self.field[t]
                         and self._poly_span[(t, c)]
                         <= frozenset((gname,)))
                if (m1_ok or pj_ok):
                    legal.append(t)
            if (legal == [BOUNDARY_T]):
                demands[BOUNDARY_T, c] = (name,
                                          "gate contact @col %d" % c)
                demands[BOUNDARY_T, c + 1] = (name,
                                              "gate contact @col %d" % c)
        return demands

    def structural_diagnosis(self):
        """Static forced-demand analysis of the well-boundary corridor.

        For every signal net, the terminals' free-space cages (see
        :meth:`_cage`) decide which corridor nodes (T3, c) are forced:
        a corridor node is forced for a terminal pair when removing it
        disconnects the pair in the free graph.  Returns
        ``(contests, walled)`` where ``contests`` maps corridor column
        -> {net name: reason} for nodes demanded by >= 2 nets and
        ``walled`` lists (net name, label) for terminals caged away
        from all their net's other terminals.  Pure function of the
        build-time geometry; deterministic; the forced set is
        deliberately under-approximated so a contest is never
        invented.
        """
        self._term_owner = self._static_term_owner()
        demands = {}                    # (T3, c) -> {net name: reason}
        walled = []
        for net in self.nets:
            terms = sorted(nid for nid in net.nodes
                           if self.graph[nid].kind[0] in (_M1, _G))
            # every gate node needs a crossing; when the corridor is the
            # sole surviving crossing track, its endpoint nodes are
            # forced (M2 cannot lift a gate contact)
            net_demands = self._gate_forced(net.index, net.name)
            if (len(terms) < 2):
                # a single-terminal net (gate-only) has no pairwise
                # connectivity requirement -- its demand is the gate
                # crossing, handled above
                for key, entry in net_demands.items():
                    demands.setdefault(key, {})[entry[0]] = entry[1]
                continue
            for i, t1 in enumerate(terms):
                cage1 = self._cage(net.index, t1)
                if (not any(t2 in cage1 for t2 in terms if t2 != t1)):
                    # statically caged from its own net (hub-mediated
                    # or hard-fail territory): report, don't cut-test
                    walled.append((net.name, self._term_label(t1)))
                    continue
                # the corridor cut candidates, once per t1 (cage1's set
                # order); each banned-cage is a pure function of
                # (net, t1, nid), so it is computed once and shared by
                # every t2 -- the same fixpoint the per-t2 recomputation
                # produced, O(corridor) instead of O(terms x corridor)
                corridor = []
                for nid in cage1:
                    kind = self.graph[nid].kind
                    if (kind[0] == _M1 and kind[1] == BOUNDARY_T):
                        corridor.append(nid)
                banned_cache = {}
                for t2 in terms:
                    if (t2 <= t1 or t2 not in cage1):
                        continue
                    for nid in corridor:
                        cage2 = banned_cache.get(nid)
                        if (cage2 is None):
                            cage2 = self._cage(net.index, t1,
                                               banned=frozenset((nid,)))
                            banned_cache[nid] = cage2
                        if (t2 not in cage2):
                            kind = self.graph[nid].kind
                            net_demands.setdefault(
                                (kind[1], kind[2]),
                                (net.name, self._term_label(t1)))
            for key, entry in net_demands.items():
                demands.setdefault(key, {})[entry[0]] = entry[1]
        contests = {c: users for (t, c), users in sorted(demands.items())
                    if t == BOUNDARY_T and len(users) > 1}
        return contests, walled

    def _structural_note(self):
        """The failure-note fragment naming the missing freedom."""
        contests, walled = self.structural_diagnosis()
        self.structural_contests = contests
        self.structural_walled = walled
        parts = []
        if (walled):
            parts.append("; structural: " + "; ".join(
                "%s %s is statically caged" % (name, label)
                for name, label in walled))
        if (contests):
            detail = "; ".join(
                "col %d: %s" % (c, " vs ".join(
                    "%s (%s)" % (name, reason)
                    for name, reason in sorted(users.items())))
                for c, users in sorted(contests.items()))
            parts.append(
                "; structural: corridor T3 over-subscribed at %s -- "
                "the metal2 freedom (node-level vias + M2 track changes, "
                "router.cpp:53-55) does not dissolve these demands: a "
                "gate contact's crossing must be M1/poly (M2 never "
                "touches gates) and power stripes are pinned, so the "
                "remaining freedom is the placement itself" % detail)
        return "".join(parts)
    def build_result(self):
        """Build the RouteResult-compatible solution from the trees."""
        width = self.width_cols
        hseg = {}
        pj = {}
        m2 = {}
        via = {}
        m2v = {}
        m2via = {}
        m1_tab, m2_tab = self._m1_tab, self._m2_tab
        for net in self.nets:               # sorted-name order
            mine = set(net.tree)
            # the (t, c) candidates are collected from the tree -- every
            # emitted key needs both points in the tree, so one pass over
            # it replaces the full grid scans.  The per-slot layer keeps
            # the scan's if/elif priority (M1, then M2, then poly) via
            # the own/m2own skips, and all emitted dicts have disjoint
            # keys, so the result is identical to the scan's.
            m1s = set()
            pjs = set()
            m2s = set()
            for nid in net.tree:
                kind = self.graph[nid].kind
                if (kind[0] == _M1):
                    m1s.add((kind[1], kind[2]))
                elif (kind[0] == _PJ):
                    pjs.add((kind[1], kind[2]))
                elif (kind[0] == _M2):
                    m2s.add((kind[1], kind[2]))
            own = set()
            for tc in sorted(m1s):
                t, c = tc
                if (c + 1 < width and (t, c + 1) in m1s):
                    hseg[tc] = net.name
                    own.add(tc)
            m2own = set()
            for tc in sorted(m2s):
                t, c = tc
                if ((c + 1 < width and (t, c + 1) in m2s)
                        and tc not in own):
                    hseg[tc] = net.name
                    m2[tc] = True
                    m2own.add(tc)
            for tc in sorted(pjs):
                t, c = tc
                if ((c + 1 < width and (t, c + 1) in pjs)
                        and tc not in own and tc not in m2own):
                    hseg[tc] = net.name
                    pj[tc] = True
            # M1<->M2 junctions: the both-side segment pairs emit the
            # old via form; every other real pair (both sides own
            # drawable metal at the point -- the post-pass's node-via
            # rule) emits a node via (tree-collected M2 points; the
            # via/m2via keys are disjoint, order-independent)
            for t, c in sorted(m2s):
                if (m1_tab[t][c] not in mine):
                    continue
                if (c > 0 and c < width - 1
                        and ((m1_tab[t][c - 1] in mine
                              and m2_tab[t][c + 1] in mine)
                             or (m2_tab[t][c - 1] in mine
                                 and m1_tab[t][c + 1] in mine))):
                    via[(t, c)] = True
                else:
                    m2via[(t, c)] = True
            # metal2 vertical spans: maximal contiguous M2 runs per
            # column (a run of one track is a segment endpoint or a
            # dead point -- never a span)
            cols = {}
            for nid in mine:
                kind = self.graph[nid].kind
                if (kind[0] == _M2):
                    cols.setdefault(kind[2], set()).add(kind[1])
            for c in sorted(cols):
                tracks = sorted(cols[c])
                runs = []
                start = prev = None
                for t in tracks:
                    if (start is None):
                        start = t
                    elif (t != prev + 1):
                        runs.append((start, prev))
                        start = t
                    prev = t
                if (start is not None):
                    runs.append((start, prev))
                for t1, t2 in runs:
                    if (t2 > t1):
                        m2v[(c, t1, t2)] = net.name
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
                + len(via) * VIA_COST
                + len(m2via) * VIA_COST
                + sum(t2 - t1 for (_c, t1, t2) in m2v) * M2_V_COST)
        result = RouteResult(
            "FEASIBLE", owner_n, owner_p, lo_n, hi_n, lo_p, hi_p,
            hseg, pj, m2, via, reachB_n, reachB_p, width, len(hseg),
            vseg, len(pj), len(m2), len(via), m2v=m2v, m2via=m2via)
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


def _phase1_skip_reason(contests, walled):
    """Deterministic provenance string for a phase-1 skip decision.

    Built from sorted structures only (invariant 9); recorded on the
    RouteResult as ``phase1_skip_reason`` when route_cell skipped
    phase 1 on the static diagnosis.
    """
    parts = []
    if (contests):
        cols = ", ".join(str(c) for c in sorted(contests))
        names = sorted({name for users in contests.values()
                        for name in users})
        parts.append("contested corridor cols [%s] (%s)"
                     % (cols, ", ".join(names)))
    if (walled):
        names = sorted({name for name, _label in walled})
        parts.append("%d statically caged terminal(s) (%s)"
                     % (len(walled), ", ".join(names)))
    return "; ".join(parts)


def route_cell(netlist, placement, width_cols, leg_widths=None,
               height_um=2.47, grid_um=0.19, max_attempts=MAX_ATTEMPTS,
               blocks=None):
    """Route one placed cell; returns a RouteResult (solve_routing's type).

    ``netlist`` is a smt_engine CellNetlist, ``placement`` maps
    Device -> PlacedTransistor (smt_engine's IR), ``width_cols`` is the
    placement width in 0.19 um columns and ``leg_widths`` the fold map
    (device name -> (legs, leg_width_cols)); the fold is already realized
    in the placement, so the router consumes it for provenance only.
    ``blocks`` optionally supplies the orientation-aware block view the
    placement was built from (bigcell_engine.engine's meta["blocks"]);
    it feeds die_view's tree-arrangement fallback -- see
    :meth:`_RouteGrid.__init__`.  None (the default, and every
    exact-engine placement) keeps the pure reconstruction byte-identical.

    Two phases (AGENTS.md invariants 8/9 discipline): phase 1 is the
    pre-freedom router -- graph, negotiation and emitted vocabulary are
    byte-for-byte the historical ones, so every cell that closed before
    keeps its exact route.  Only on a phase-1 stall does phase 2 rebuild
    the grid WITH the metal2 vertical freedom (via-up at any node, M2
    vertical hops, node-level vias, M2-bridge dual fills) and re-route
    from scratch; its failure note (with the metal2-aware structural
    diagnosis) is the honest residual.

    Phase-1 skip gate (runtime tuning 2026-10): BEFORE phase 1, the
    static forced-demand diagnosis (:meth:`structural_diagnosis`) runs
    on the PHASE-1 grid.  The phase-1 cage graph is a sub-graph of the
    phase-2 one (no M2 vertical arcs, node vias forbidden by the phase-1
    post-pass rule (d)), and the diagnosis only ever over-states
    reachability, so a contested corridor column or a statically caged
    terminal it reports is a PROVEN floor for the phase-1 vocabulary --
    the pre-freedom negotiation cannot reach zero conflicts (a
    phase-1-closing route implies a clean diagnosis, so a clean gate
    keeps the exact two-phase order and every closing route stays
    byte-identical).  On a dirty diagnosis phase 1 is skipped entirely
    (it could only burn its full attempt budget on a proven stall) and
    phase 2 -- whose negotiation is independent of phase 1's -- runs
    unchanged, producing byte-identical results and notes.  The skip is
    recorded in the route's provenance: ``result.phase1_skipped`` (bool,
    always set on route_cell results) and ``result.phase1_skip_reason``
    (the diagnosis summary, only when skipped).  The fail_note is NOT
    modified: the window fixer (engine.parse_fail_nets) and the pinned
    note fragments see exactly the pre-tuning payloads.

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
                      height_um=height_um, grid_um=grid_um,
                      metal2_verticals=False, blocks=blocks)
    # the phase-1 skip gate: a build-time failure needs no diagnosis
    # (route() fails on it deterministically and phase 2 repeats it), so
    # the diagnosis only runs where a negotiation could actually start
    skip_reason = None
    if (grid._fail_note is None):
        contests, walled = grid.structural_diagnosis()
        if (contests or walled):
            skip_reason = _phase1_skip_reason(contests, walled)
    if (skip_reason is None and grid.route(max_attempts=max_attempts)):
        result = grid.build_result()
        result.phase1_skipped = False
        return result
    # phase 2: the metal2 vertical freedom (router.cpp:53-55) on a
    # fresh grid -- the negotiation restarts, nothing carries over
    grid = _RouteGrid(netlist, placement, width_cols,
                      height_um=height_um, grid_um=grid_um,
                      metal2_verticals=True, blocks=blocks)
    if (grid.route(max_attempts=max_attempts)):
        result = grid.build_result()
    else:
        result = grid.failed_result()
    result.phase1_skipped = skip_reason is not None
    if (skip_reason is not None):
        result.phase1_skip_reason = skip_reason
    return result


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
    # the metal2 vertical freedom: spans + node vias join the signature
    # only when present, so routes without them serialize byte-identically
    for key in sorted(getattr(route, "m2v", {}) or {}):
        parts.append("s%s=%s" % (key, route.m2v[key]))
    for key in sorted(getattr(route, "m2via", {}) or {}):
        if (route.m2via[key]):
            parts.append("n%s" % (key,))
    return "\n".join(parts)
