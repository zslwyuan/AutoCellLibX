"""Structural self-check for solved SMT-engine cells.

Re-derives geometry from the (netlist, placement, route) triple and
re-validates everything the SAT encodings promised, so a wrong model or
a solver bug cannot silently ship a bad cell:

- layout: block members abut and share the row; diffusion blocks do not
  overlap; different-net block ends respect the break gap;
- routing (on the 7-track model: four row-centre tracks, two row-edge
  tracks and the well-boundary corridor T3): every diffusion access
  column carries the right stripe (in the slot of its half) and the
  stripe's index interval covers the access track; every gate column has
  a horizontal M1/poly segment of the gate net crossing it on a track
  the stripe's y-range actually spans (M2 floats above the gate and does
  not count); no M1 horizontal segment crosses a foreign stripe covering
  its track (either slot); power stripes reach the power end of the bar
  domain and cover the diffusion end track; dual columns hold one net
  (or, for different nets, neither bar may reach T3); same-net dual bars
  reach the boundary and merge; poly jumps stay on the row tracks, lie
  over field oxide, never cross a foreign gate, and every maximal poly
  run is anchored at a same-net gate; adjacent segments on a track never
  switch between poly and a metal layer for one net, switch between M1
  and M2 only through a via, and never touch in the same layer for
  different nets;
- connectivity is physical: an exact BFS over the M1 / M2 / poly / gate
  graphs (M2 joins M1 only at vias; bars join the tracks their interval
  covers -- the T3 merge of a dual pair falls out of coverage; gates
  join only crossings on tracks their y-range spans).

The metal2 vertical freedom (route_grid's node-level vias + M2 track
changes) extends the checked geometry additively: an ``m2v`` span
((col, t_lo, t_hi) -> net) is claimed M2 across a track range on one
column (no foreign M2 span overlap, no foreign M2 segment endpoint and
no foreign node via inside the range -- M2 over M1/poly/gates is the
freedom itself); an ``m2via`` node via ((track, col) -> bool) joins the
net's M1 point (stripe coverage or M1 segment endpoint) to the same
net's metal2 at that point (span member or M2 segment endpoint).  Both
default to absent, so routes without the freedom verify exactly as
before.

Deterministic and pure: no solver, no randomness.
"""

from . import die_view
from .netlist import (build_diffusion_blocks, diffusion_access_points,
                      gate_access_points)
from .route_model import (BOUNDARY_T, N_TRACKS, ROW_TRACK, ROW_TRACKS,
                          device_rail, track_domain_local)
from .gds import (CONTACT_S, POLY_OVERHANG, row_geometry,
                  track_geometry)

ROW_OF_TRACK = {0: (False, 0), 2: (False, 1), 4: (True, 0), 6: (True, 1)}


class VerifyReport(object):
    def __init__(self, violations):
        self.violations = list(violations)

    def ok(self):
        return not self.violations

    def as_dict(self):
        return {"ok": self.ok(), "violations": list(self.violations)}


def _gate_spans(netlist, placement, height_um=2.47, grid_um=0.19, dom=None):
    """(gate_net, col) -> (y0, y1) the poly stripe spans (incl. overhang).

    bar9 (dom None / not strip_anchored): the four sub-row bands.  The
    astran13 domain spans the slot model's W-tall well-anchored strips
    (the drawn poly; the union over the (net, col) devices covers the
    well corridor for an aligned P/N pair -- exactly the merged stripe
    gds_cells draws there)."""
    if dom is None:
        dom = track_domain_local("bar9", height_um, grid_um)
    _, rows = row_geometry(height_um, grid_um)
    spans = {}
    for dev in netlist.devices:
        p = placement[dev]
        if dom.strip_anchored:
            y0, y1 = dom.strip_y(dev.is_p, dev.width_um, height_um)
        else:
            y0, y1 = rows[(dev.is_p, p.row)]
        for j in range(p.legs):
            c = p.start_col + j * p.leg_width_cols + p.leg_width_cols // 2
            key = (dev.gate, c)
            if (key in spans):
                o0, o1 = spans[key]
                spans[key] = (min(o0, y0), max(o1, y1))
            else:
                spans[key] = (y0, y1)
    return {k: (y0 - POLY_OVERHANG, y1 + POLY_OVERHANG)
            for k, (y0, y1) in spans.items()}


def _field_map(netlist, placement, width_cols, dom=None, height_um=2.47):
    """Row tracks with no active diffusion (poly-jump legality).

    bar9: the historical column form.  astran13 (strip_anchored): y-aware
    per track -- a strip blocks only the tracks its y-range covers
    (ASTRAN's per-column pol-node existence, autocell2.cpp:41/:50)."""
    if dom is None:
        dom = track_domain_local("bar9", height_um, 0.19)
    if dom.strip_anchored:
        return route_model_field_map(netlist, placement, width_cols, dom,
                                      height_um)
    active = {}
    for dev in netlist.devices:
        p = placement[dev]
        active.setdefault((dev.is_p, p.row), set()).update(
            range(p.start_col, p.end_col))
    field = {}
    for t in dom.row_tracks:
        is_p, row = dom.row_of_track[t]
        field[t] = set(range(width_cols)) - active.get((is_p, row), set())
    return field


def route_model_field_map(netlist, placement, width_cols, dom, height_um):
    """The y-aware field map (route_model._field_map's strip-anchored
    branch, shared so the verifier and the model agree exactly)."""
    from .route_model import _field_map as _rm_field
    return _rm_field(netlist, placement, width_cols, dom, height_um)


def verify_cell(netlist, placement, route, grid_um=0.19, height_um=2.47,
                break_um=0.19, blocks=None, slot_model=False,
                tracks="bar9"):
    """Structural verification; returns VerifyReport.

    ``tracks`` selects the route's track domain (gds.TRACK_DOMAINS):
    the RouteResult's hseg keys and bar endpoint indices speak that
    domain, so the verifier derives its trackY/barY, rail->track map,
    field map and gate spans from the same record (default bar9 keeps
    the historical verification byte-identical; astran13 verifies
    ASTRAN's own 16-signal-track grid with strip-anchored gate spans
    and the y-aware poly field).

    ``blocks`` optionally supplies the diffusion-block view the placement
    was built from (an iterable of DiffusionBlock-compatible objects with
    members/first/last/kind).  bigcell_engine's tree-block decomposition
    keeps coupled degree-3 units in ONE block; verifying such a placement
    against the base build_diffusion_blocks view would split the unit and
    report a false "diffusion break missing".  Default (None) keeps the
    historical base-decomposition behaviour.

    ``slot_model`` switches the diffusion access-point derivation to the
    shared slot-model die view (doc/BIGCELL_SLOT_GEOMETRY.md): member
    terminals sit on the member's EDGE columns (the exact engine insets a
    width-1 leg's right access into its own column) and multi-region nets
    (one net occupying several edge slots of a row) are access points
    everywhere so their regions stay tied.  The derivation is the shared
    smt_engine.die_view reconstruction, so it also activates implicitly
    whenever ``blocks`` (the orientation-aware view bigcell passes) is
    supplied for a slot-model placement -- and the supplied view is then
    FORWARDED into the reconstruction, so on a tree arrangement (where
    the pristine model fails and the reconstruction falls back) the
    verifier derives its requirements from the exact die state the
    router was given, not from the trail guess -- the router and the
    verifier see the same view even there (bigcell_engine.route_grid
    wires the same ``blocks`` into its grids).  The default path
    (``blocks`` None) stays byte-identical to the historical behaviour.
    """
    violations = []
    dom = track_domain_local(tracks, height_um, grid_um)
    # bar9: every value equals the historical module constant
    # (byte-identical verification); astran13 re-generalizes them
    N_TRACKS = dom.n_tracks
    ROW_TRACK = dom.row_track
    ROW_TRACKS = dom.row_tracks
    trackY, barY = dom.trackY, dom.barY
    width_cols = route.width_cols
    pj = getattr(route, "pj", {})
    m2 = getattr(route, "m2", {})
    via = getattr(route, "via", {})
    reachB_n = getattr(route, "reachB_n", [False] * width_cols)
    reachB_p = getattr(route, "reachB_p", [False] * width_cols)
    m2v = getattr(route, "m2v", {}) or {}
    m2via = getattr(route, "m2via", {}) or {}

    def stripes(c):
        return route.stripes(c)

    def net_has_stripe(net, c):
        for net2, lo, hi, slot in stripes(c):
            if (net2 == net):
                return True
        return False

    def _slot_covers(net, c, t):
        """The net's stripe at column c covers track t (index rule)."""
        for net2, lo, hi, slot in stripes(c):
            if (net2 == net and lo <= t + 1 <= hi):
                return True
        return False

    def _m1_owner_at(t, c):
        """Net owning M1 metal at the point (t, c), or None: a stripe
        covering the track, a gate stub (the via-anchored form lands
        on the stub), else an M1 (not poly/M2) segment endpoint."""
        for net2, lo, hi, _slot in stripes(c):
            if (lo <= t + 1 <= hi):
                return net2
        if (getattr(route, "gate_stub", {}).get((t, c))):
            n2 = route.stub_net(t, c)
            if (n2 is not None):
                return n2
        for cseg in (c - 1, c):
            n2 = route.hseg.get((t, cseg))
            if (n2 is not None and not pj.get((t, cseg))
                    and not m2.get((t, cseg))):
                return n2
        return None

    def _m2_owner_at(t, c):
        """Net owning metal2 at the point (t, c), or None: an m2v span
        covering the track, an over-foreign-slot extra segment, else an
        M2 segment endpoint."""
        for (cc, t1, t2), net2 in m2v.items():
            if (cc == c and t1 <= t <= t2):
                return net2
        for (et, ec, en) in (getattr(route, "extra_m2", ()) or ()):
            if (et == t and ec in (c - 1, c)):
                return en
        for cseg in (c - 1, c):
            n2 = route.hseg.get((t, cseg))
            if (n2 is not None and m2.get((t, cseg))):
                return n2
        return None

    def _layer(t, c):
        if (pj.get((t, c))):
            return "poly"
        if (m2.get((t, c))):
            return "M2"
        return "M1"

    # ---- layout invariants ----
    # the caller's ``blocks`` argument is captured before materialisation:
    # the routing invariants below forward it (the caller's VIEW, None
    # included) into the slot-model access derivation, while the layout
    # checks here consume the materialised block list.
    blocks_arg = blocks
    if blocks is None:
        blocks = build_diffusion_blocks(netlist)
    block_objs = blocks          # kept for orientation-aware _nets_touch
    for block in blocks:
        for a, b in zip(block.members, block.members[1:]):
            pa, pb = placement[a.device], placement[b.device]
            if (pa.row != pb.row or pa.end_col != pb.start_col):
                violations.append("block %s: %s and %s do not abut"
                                  % (block.kind, a.name, b.name))
    rects = []
    for block in blocks:
        p = placement[block.first]
        end = placement[block.last].end_col
        rects.append((block.first.is_p, p.row, p.start_col, end,
                      block.first.name))
    blocks = rects
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            a, b = blocks[i], blocks[j]
            if (a[0] != b[0]):
                continue
            if (a[1] == b[1] and a[2] < b[3] and b[2] < a[3]):
                violations.append("diffusion overlap: %s vs %s"
                                  % (a[4], b[4]))
    breakCols = max(1, int(round(break_um / grid_um)))
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            a, b = blocks[i], blocks[j]
            if (a[0] != b[0] or a[1] != b[1]):
                continue
            if (b[2] < a[3]):
                a, b = b, a
            if (a[3] + breakCols > b[2]
                    and not _nets_touch(netlist, a, b, block_objs)):
                violations.append("diffusion break missing: %s|%s"
                                  % (a[4], b[4]))

    # ---- routing invariants ----
    # Access-point derivation (doc/BIGCELL_SLOT_GEOMETRY.md sections 7-8):
    # the bigcell slot chain's placement (every leg one column wide) is
    # verified against the SHARED die view (smt_engine.die_view) -- the
    # same orientation-aware, edge-column derivation route_grid routes
    # with, so the router's terminals and the verifier's requirements
    # agree even where the die cannot distinguish a single block's flip.
    # The supplied ``blocks`` stay authoritative for the LAYOUT
    # invariants above (abutment, breaks, overlap) and are FORWARDED into
    # the slot derivation, so its tree-arrangement fallback resolves the
    # die from the exact view the placement was built from -- the same
    # view route_grid's grids consume -- instead of the trail guess
    # (router == verifier is the binding contract).  A ``blocks`` view on
    # a non-slot placement instead only re-orients the historical inset
    # walk (diffusion_access_points' blocks parameter); no ``blocks`` at
    # all keeps the byte-identical base behaviour.
    if slot_model or die_view.is_slot_placement(placement, blocks_arg):
        sig_diff, power_diff = die_view.die_slot_access_points(
            netlist, placement, blocks=blocks_arg)
    elif blocks_arg is not None:
        sig_diff, power_diff = diffusion_access_points(
            netlist, placement, blocks_arg)
    else:
        sig_diff, power_diff = diffusion_access_points(netlist, placement)
    gate = gate_access_points(netlist, placement)
    field = _field_map(netlist, placement, width_cols, dom, height_um)
    spans = _gate_spans(netlist, placement, height_um, grid_um, dom)
    gateNetsAt = {}
    for net, cols in gate.items():
        for c in cols:
            gateNetsAt.setdefault(c, set()).add(net)

    for net, pts in sig_diff.items():
        for c, dev in pts:
            if (not net_has_stripe(net, c)):
                violations.append("diffusion access %s@%d: no stripe"
                                  % (net, c))
                continue
            t = ROW_TRACK[device_rail(dev, placement[dev].row)]
            if (not _slot_covers(net, c, t)):
                violations.append("diffusion access %s@%d: stripe "
                                  "misses track %d" % (net, c, t))
    for net, pts in power_diff.items():
        pEnd = len(barY) - 1 if net in ("VCC", "VDD") else 0
        for c, dev in pts:
            if (not net_has_stripe(net, c)):
                violations.append("power access %s@%d: no stripe"
                                  % (net, c))
                continue
            ok = False
            for net2, lo, hi, slot in stripes(c):
                if (net2 == net
                        and (lo == pEnd or hi == pEnd)):
                    ok = True
            if (not ok):
                violations.append("power access %s@%d: stripe does not "
                                  "reach power level %d" % (net, c, pEnd))
    # signal bars must stay clear of the power rails: a bar drawn to the
    # power end of the bar domain overlaps the full-width power rail
    powerNames = ("VCC", "VDD", "GND", "VSS")
    for c in range(width_cols):
        for net2, lo, hi, slot in stripes(c):
            if (net2 in powerNames):
                continue
            if ((slot == "N" and lo == 0)
                    or (slot == "P" and hi == len(barY) - 1)):
                violations.append("signal bar %s@%d (%s) reaches the "
                                  "power rail" % (net2, c, slot))
    for net, cols in gate.items():
        for c in cols:
            crossed = False
            for t in range(N_TRACKS):
                if (c > route.width_cols - 2):
                    continue
                if ((t, c) in route.hseg and route.hseg[(t, c)] == net
                        and not m2.get((t, c))
                        and _touches_gate(spans, net, c, t, trackY)):
                    # M1 contacts the stripe, a poly jump merges with it;
                    # M2 floats above and never touches; a track outside
                    # the stripe's y-range would leave the contact
                    # floating
                    crossed = True
                if (getattr(route, "gate_stub", {}).get((t, c))
                        and route.stub_net(t, c) == net
                        and _touches_gate(spans, net, c, t, trackY)):
                    # the half-slot stub: the net's M1 run ends at the
                    # gate column (or the node via lands on the stub)
                    # and the stub piece reaches the contact square at
                    # the slot centre
                    crossed = True
            if (not crossed):
                violations.append("gate %s@%d: no segment crosses the "
                                  "column" % (net, c))
    for (t, c), net in route.hseg.items():
        if (pj.get((t, c)) or m2.get((t, c))):
            continue            # poly / M2: no M1 crossing (checked below)
        for side in (c, c + 1):
            for net2, lo, hi, slot in stripes(side):
                if (net2 != net and lo <= t + 1 <= hi):
                    violations.append("segment %s@%d track %d crosses "
                                      "foreign stripe %s"
                                      % (net, c, t, net2))
    # dual columns: different nets must not both reach the boundary
    # (their bars would overlap at y = H/2 -- a short).  A same-net dual
    # no longer REQUIRES the T3 merge: the metal2 vertical freedom is a
    # second N<->P crossover, so the halves may meet through an M2 span
    # instead -- physical connectivity is the exact BFS's verdict below
    # (a disconnected net is reported there), which subsumes the old
    # same-net merge check.  Routes without M2 geometry always merge
    # (the exact model forces it; the router's solidify keeps the fill),
    # so this loosening changes nothing for them.
    for c in range(width_cols):
        nOwn, pOwn = route.owners(c)
        if (nOwn is None or pOwn is None):
            continue
        if (nOwn != pOwn):
            if (reachB_n[c] and reachB_p[c]):
                violations.append("column %d: bars of %s and %s both "
                                  "reach the well boundary"
                                  % (c, nOwn, pOwn))
    # gate-contact half-slot stubs: the M1 piece from the gate column's
    # node to just past the contact square at the slot centre (the C++'s
    # own centre-anchored contact form).  Two anchors: the net's M1 run
    # ending at the node, or -- the via-anchored form -- the net's M2
    # segment the node vias climbs into (a contact landing on a bare M1
    # point with no horizontal run).  The stub overlaps its own column's
    # bar band and the slot's left half on M1, so a foreign bar covering
    # the track or a foreign M1 slot would short it.  It never reaches
    # column c+1's bar band.
    for (t, c), on in getattr(route, "gate_stub", {}).items():
        if (not on):
            continue
        net = route.stub_net(t, c)
        if (net is None):
            violations.append("gate stub (%d, %d): no anchoring segment"
                              % (t, c))
            continue
        for net2, lo, hi, _slot in stripes(c):
            if (net2 != net and lo <= t + 1 <= hi):
                violations.append("gate stub (%d, %d) of %s crosses the "
                                  "stripe of %s" % (t, c, net, net2))
        left = route.hseg.get((t, c - 1))
        if (left is not None and left != net
                and not route.pj.get((t, c - 1))
                and not route.m2.get((t, c - 1))):
            violations.append("gate stub (%d, %d) of %s crosses the "
                              "segment of %s" % (t, c, net, left))
        if (route.hseg.get((t, c)) is not None
                and route.hseg.get((t, c)) != net
                and not route.pj.get((t, c))
                and not route.m2.get((t, c))):
            violations.append("gate stub (%d, %d) of %s crosses the "
                              "segment of %s"
                              % (t, c, net, route.hseg.get((t, c))))
    # poly jump legality: row tracks only, field oxide, no foreign gate,
    # anchored runs
    for (t, c), isPoly in pj.items():
        if (not isPoly):
            continue
        net = route.hseg.get((t, c))
        if (net is None):
            continue
        if (t not in ROW_TRACKS):
            violations.append("poly jump %s@%d on non-row track %d"
                              % (net, c, t))
            continue
        if (c + 1 not in field[t]):
            violations.append("poly jump %s@%d track %d crosses active"
                              % (net, c, t))
        if (c not in field[t] and net not in gateNetsAt.get(c, ())):
            violations.append("poly jump %s@%d track %d over active "
                              "without a same-net gate" % (net, c, t))
        for gn in sorted(gateNetsAt.get(c, ())):
            gy0, gy1 = spans[(gn, c)]
            if (gy0 <= trackY[t] <= gy1 and gn != net):
                violations.append("poly jump %s@%d track %d crosses "
                                  "foreign gate %s" % (net, c, t, gn))
    for t in ROW_TRACKS:
        run = []
        for c in range(width_cols - 1):
            net = route.hseg.get((t, c)) if pj.get((t, c)) else None
            if (net is None):
                if (run):
                    anchored = any(
                        route.hseg[(t, cc)] in gateNetsAt.get(cc, ())
                        and _touches_gate(
                            spans, route.hseg[(t, cc)], cc, t, trackY)
                        for cc in run)
                    if (not anchored):
                        violations.append(
                            "poly run track %d cols %d..%d has no gate"
                            % (t, run[0], run[-1]))
                    run = []
            else:
                run.append(c)
        if (run):
            anchored = any(
                route.hseg[(t, cc)] in gateNetsAt.get(cc, ())
                and _touches_gate(spans, route.hseg[(t, cc)], cc, t,
                                  trackY)
                for cc in run)
            if (not anchored):
                violations.append("poly run track %d cols %d..%d has no "
                                  "gate" % (t, run[0], run[-1]))
    # adjacent segments: same net keeps one layer (an M1<->M2 switch is
    # legal only through a via; a poly<->metal switch has no contact);
    # different nets never touch in the same layer
    for t in range(N_TRACKS):
        for c in range(1, width_cols - 1):
            left = route.hseg.get((t, c - 1))
            right = route.hseg.get((t, c))
            if (left is None or right is None):
                continue
            lL, lR = _layer(t, c - 1), _layer(t, c)
            if (left == right):
                if (lL != lR):
                    if (set((lL, lR)) == set(("M1", "M2"))):
                        if (not via.get((t, c))):
                            violations.append(
                                "segment %s track %d: M1<->M2 switch at "
                                "col %d without via" % (left, t, c))
                    else:
                        violations.append(
                            "segment %s@%d track %d switches layer at "
                            "col %d" % (left, c - 1, t, c))
            else:
                if (lL == lR):
                    violations.append("segments %s/%s@%d track %d touch "
                                      "in one layer"
                                      % (left, right, c - 1, t))
    # vias join exactly one net's M1 and M2 segments
    for (t, c), on in via.items():
        if (not on):
            continue
        left = route.hseg.get((t, c - 1))
        right = route.hseg.get((t, c))
        if (left is None or left != right):
            violations.append("via track %d col %d does not join one net"
                              % (t, c))
            continue
        lL, lR = _layer(t, c - 1), _layer(t, c)
        if (set((lL, lR)) != set(("M1", "M2"))):
            violations.append("via track %d col %d joins %s-%s (need "
                              "M1-M2)" % (t, c, lL, lR))

    # ---- metal2 vertical freedom: spans + node vias ----
    # A span is claimed M2 across a track range on one column: no foreign
    # span overlap at its column, no foreign M2 segment endpoint and no
    # foreign node via inside its range (M2 over M1/poly/gates is the
    # freedom itself, not a short).  A node via joins exactly one net's
    # M1 point (stripe coverage or M1 segment endpoint) to the same
    # net's metal2 at that point (span member or M2 segment endpoint).
    for (c, t1, t2), net in sorted(m2v.items()):
        if (t1 >= t2):
            violations.append("M2 span %s@col %d is not a track range "
                              "(%d..%d)" % (net, c, t1, t2))
    spansByCol = {}
    for (c, t1, t2), net in m2v.items():
        spansByCol.setdefault(c, []).append((t1, t2, net))
    for c, colSpans in spansByCol.items():
        for i, (a1, a2, na) in enumerate(colSpans):
            for b1, b2, nb in colSpans[i + 1:]:
                if (na != nb and a1 <= b2 and b1 <= a2):
                    violations.append(
                        "M2 spans %s and %s overlap at column %d"
                        % (na, nb, c))
    for (c, t1, t2), net in sorted(m2v.items()):
        for t in range(t1, t2 + 1):
            for cseg in (c - 1, c):
                n2 = route.hseg.get((t, cseg))
                if (n2 is not None and n2 != net and m2.get((t, cseg))):
                    violations.append(
                        "M2 span %s@col %d track %d touches M2 segment "
                        "of %s" % (net, c, t, n2))
    for (t, c), on in sorted(m2via.items()):
        if (not on):
            continue
        m1_owner = _m1_owner_at(t, c)
        m2_owner = _m2_owner_at(t, c)
        if (m1_owner is None or m2_owner is None or m1_owner != m2_owner):
            violations.append(
                "node via track %d col %d does not join one net's M1 "
                "and M2 (%s vs %s)"
                % (t, c, m1_owner, m2_owner))
    # the over-foreign-slot M2 segments: same-layer conflicts only --
    # the slot's own M1/poly is a different layer and coexists by
    # design; a foreign M2 segment touching the rectangle (its own
    # slot or an adjacent one), or a foreign span's x-band overlapping
    # it on a covered track, is a short
    extras_all = getattr(route, "extra_m2", ()) or ()
    for (t, c, n) in extras_all:
        prev = route.hseg.get((t, c))
        if (prev is not None and prev != n and m2.get((t, c))):
            violations.append("extra M2 %s@(%d, %d) sits on the M2 of %s"
                              % (n, t, c, prev))
        for cc in (c - 1, c + 1):
            n2 = route.hseg.get((t, cc))
            if (n2 is not None and n2 != n and m2.get((t, cc))):
                violations.append("extra M2 %s@(%d, %d) touches the M2 "
                                  "of %s at col %d" % (n, t, c, n2, cc))
        for (et2, ec2, en2) in extras_all:
            if (et2 == t and ec2 in (c - 1, c + 1) and en2 != n):
                violations.append("extra M2 %s@(%d, %d) touches the "
                                  "extra M2 of %s" % (n, t, c, en2))
        for (cc, t1, t2), n2 in m2v.items():
            if (cc in (c, c + 1) and t1 <= t <= t2 and n2 != n):
                violations.append("extra M2 %s@(%d, %d) overlaps the M2 "
                                  "span of %s" % (n, t, c, n2))

    # ---- physical connectivity: exact BFS over layers ----
    nets = set(sig_diff) | set(gate)
    for net in sorted(nets):
        if (not _net_connected_exact(netlist, placement, route, net,
                                     sig_diff.get(net, set()),
                                     gate.get(net, []), trackY, spans,
                                     pj, m2, via, m2v, m2via,
                                     n_tracks=N_TRACKS)):
            violations.append("net %s is not connected" % net)
    return VerifyReport(violations)


def _touches_gate(spans, net, c, t, trackY):
    """Track t lies inside the y-range the (net, c) gate stripe spans."""
    gy0, gy1 = spans[(net, c)]
    return gy0 + CONTACT_S / 2 <= trackY[t] <= gy1 - CONTACT_S / 2


def _nets_touch(netlist, a, b, blocks=None):
    """Whether rect a's right edge shares its net with rect b's left edge.

    Orientation matters: bigcell's SA mirrors blocks (swapping which net
    faces which side), so the answer must come from the block view the
    placement was built from when one is supplied.  Default (None) keeps
    the historical base-decomposition behaviour (fixed orientations).
    """
    if blocks is None:
        blocks = build_diffusion_blocks(netlist)
    byName = {blk.first.name: blk for blk in blocks}
    blkA, blkB = byName[a[4]], byName[b[4]]
    return blkA.members[-1].right_net == blkB.members[0].left_net


def _net_connected_exact(netlist, placement, route, net, diffPts, gateCols,
                         trackY, spans, pj, m2, via, m2v=None, m2via=None,
                         n_tracks=N_TRACKS):
    """Exact physical connectivity.

    Nodes: (t, c) for M1 segments, (M2, (t, c)) for M2 segments,
    (PJ, (t, c)) for poly jumps, (G, c) for gate stripes,
    (NB, c)/(PB, c) for the slot bars, (M2V, (c, t1, t2)) for the net's
    metal2 vertical spans.  Edges: same-track same-layer segments merge
    across a column boundary; a via joins the M1 and M2 ends of two
    adjacent same-net segments; a bar joins the (t, c) nodes of the
    tracks its index interval covers (so a same-net dual pair reaching
    T3 merges through the (T3, c) node); the gate stripe at c joins
    every M1/poly segment crossing it on a track inside its y-range
    (M1 via contact, poly via merge; M2 floats above and never joins);
    an M2 span joins the same-net M2 segment endpoints on its column
    and, through a node via, the net's M1 point at every via'd track of
    its range.  True when every access is in one component.
    """
    nodes = set()
    adj = {}
    m2v = m2v or {}
    m2via = m2via or {}
    extras = getattr(route, "extra_m2", ()) or ()

    def node(kind, c):
        n = (kind, c)
        nodes.add(n)
        return n

    def edge(a, b):
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)

    def _seg_kind(t, c):
        """Extra node kind for segment (t, c): 'PJ' / 'M2' / None (M1)."""
        if (pj.get((t, c))):
            return "PJ"
        if (m2.get((t, c))):
            return "M2"
        return None

    def _end(t, c, col):
        k = _seg_kind(t, c)
        return node(t, col) if k is None else node(k, (t, col))

    for c in range(route.width_cols):
        nOwn, pOwn = route.owners(c)
        if (nOwn == net):
            node("NB", c)
        if (pOwn == net):
            node("PB", c)
    for (t, c), n in route.hseg.items():
        if (n != net):
            continue
        edge(_end(t, c, c), _end(t, c, c + 1))
    # the over-foreign-slot M2 segments: one rectangle per entry, the
    # same end nodes an hseg M2 segment of the net would have
    for (et, ec, en) in extras:
        if (en != net):
            continue
        edge(node("M2", (et, ec)), node("M2", (et, ec + 1)))
    # vias join the adjacent same-net segments' M1 and M2 ends
    for (t, c), on in via.items():
        if (not on):
            continue
        if (route.hseg.get((t, c - 1)) != net
                or route.hseg.get((t, c)) != net):
            continue
        edge(_end(t, c - 1, c), _end(t, c, c))
    # metal2 vertical freedom: a span joins the same-net M2 segment
    # endpoints on its column (M2-M2 merge at the shared point) and,
    # through a node via, the net's M1 point at every via'd track of
    # its range (the M1-side ownership is the validity check's business;
    # guarding here keeps phantom points out of the graph)
    for (c, t1, t2), n2 in sorted(m2v.items()):
        if (n2 != net):
            continue
        sn = node("M2V", (c, t1, t2))
        for t in range(t1, t2 + 1):
            for cseg in (c - 1, c):
                if ((route.hseg.get((t, cseg)) == net
                        and m2.get((t, cseg)))
                        or any(et == t and ec == cseg and en == net
                               for (et, ec, en) in extras)):
                    edge(sn, node("M2", (t, c)))
                    break
            if (m2via.get((t, c))):
                on_stripe = any(
                    n3 == net and lo <= t + 1 <= hi
                    for n3, lo, hi, _slot in route.stripes(c))
                on_m1seg = any(
                    route.hseg.get((t, cseg)) == net
                    and not pj.get((t, cseg)) and not m2.get((t, cseg))
                    for cseg in (c - 1, c)) \
                    or (getattr(route, "gate_stub", {}).get((t, c))
                        and route.stub_net(t, c) == net)
                if (on_stripe or on_m1seg):
                    edge(sn, node(t, c))
    # a node via joins the net's M2 segment ENDPOINT to the M1 point at
    # the same (t, c) -- the exact model's accm access form (an M2 wire
    # ending over the net's own bar); the span loop above covers the
    # span members, this covers the segment endpoints
    for (t, c), on in (m2via or {}).items():
        if (not on):
            continue
        if (not any((route.hseg.get((t, cseg)) == net
                     and m2.get((t, cseg)))
                    or any(et == t and ec == cseg and en == net
                           for (et, ec, en) in extras)
                    for cseg in (c - 1, c))):
            continue          # no M2 segment endpoint at the point
        on_stripe = any(
            n3 == net and lo <= t + 1 <= hi
            for n3, lo, hi, _slot in route.stripes(c))
        on_m1seg = any(
            route.hseg.get((t, cseg)) == net
            and not pj.get((t, cseg)) and not m2.get((t, cseg))
            for cseg in (c - 1, c)) \
            or (getattr(route, "gate_stub", {}).get((t, c))
                and route.stub_net(t, c) == net)
        if (on_stripe or on_m1seg):
            edge(node("M2", (t, c)), node(t, c))
    # bars join the tracks their interval covers (index rule); a dual
    # pair both reaching T3 merges through the (T3, c) node
    for c in range(route.width_cols):
        for net2, lo, hi, slot in route.stripes(c):
            if (net2 != net):
                continue
            bar = "NB" if slot == "N" else "PB"
            for t in range(n_tracks):
                if (lo <= t + 1 <= hi):
                    edge(node(bar, c), node(t, c))
    # gate stripes join every crossing inside their y-range (M1 contact,
    # poly merge); M2 floats above the gate and never joins
    for cg in gateCols:
        g = node("G", cg)
        for (t, cc), n in route.hseg.items():
            if (n != net or cc != cg):
                continue
            if (pj.get((t, cc))):
                # the poly jump merges where the stripe spans its track
                gy0, gy1 = spans[(net, cg)]
                if (gy0 <= trackY[t] <= gy1):
                    edge(g, node("PJ", (t, cc)))
            elif (m2.get((t, cc))):
                continue
            else:
                # the M1 segment crosses the stripe only on a track
                # inside its y-range (cc == cg spans the gate centre)
                if (_touches_gate(spans, net, cg, t, trackY)):
                    edge(g, node(t, cc))
                    edge(g, node(t, cc + 1))
    # the half-slot stubs: the net's M1 run ends at the gate column (or
    # the node via lands on the stub) and the stub reaches the contact
    # square at the slot centre -- the stripe joins that node through it
    for (t, c), on in (getattr(route, "gate_stub", {}) or {}).items():
        if (not on or route.stub_net(t, c) != net):
            continue          # not this net's stub
        if (c in gateCols):
            edge(node("G", c), node(t, c))
    access = set()
    for c, dev in diffPts:
        r = device_rail(dev, placement[dev].row)
        access.add(node("NB" if r <= 1 else "PB", c))
    for cg in gateCols:
        access.add(node("G", cg))
    if (not access):
        return True
    start = min(access)
    seen = set()
    stack = [start]
    while (stack):
        k = stack.pop()
        if (k in seen):
            continue
        seen.add(k)
        for nxt in adj.get(k, ()):
            if (nxt not in seen):
                stack.append(nxt)
    return all(a in seen for a in access)
