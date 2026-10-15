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

Deterministic and pure: no solver, no randomness.
"""

from .netlist import (build_diffusion_blocks, diffusion_access_points,
                      gate_access_points)
from .route_model import (BOUNDARY_T, N_TRACKS, ROW_TRACK, ROW_TRACKS,
                          device_rail)
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


def _gate_spans(netlist, placement, height_um=2.47, grid_um=0.19):
    """(gate_net, col) -> (y0, y1) the poly stripe spans (incl. overhang)."""
    _, rows = row_geometry(height_um, grid_um)
    spans = {}
    for dev in netlist.devices:
        p = placement[dev]
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


def _field_map(netlist, placement, width_cols):
    """Row tracks with no active diffusion (poly-jump legality)."""
    active = {}
    for dev in netlist.devices:
        p = placement[dev]
        active.setdefault((dev.is_p, p.row), set()).update(
            range(p.start_col, p.end_col))
    field = {}
    for t in ROW_TRACKS:
        is_p, row = ROW_OF_TRACK[t]
        field[t] = set(range(width_cols)) - active.get((is_p, row), set())
    return field


def verify_cell(netlist, placement, route, grid_um=0.19, height_um=2.47,
                break_um=0.19):
    """Structural verification; returns VerifyReport."""
    violations = []
    trackY, barY = track_geometry(height_um, grid_um)
    width_cols = route.width_cols
    pj = getattr(route, "pj", {})
    m2 = getattr(route, "m2", {})
    via = getattr(route, "via", {})
    reachB_n = getattr(route, "reachB_n", [False] * width_cols)
    reachB_p = getattr(route, "reachB_p", [False] * width_cols)

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

    def _layer(t, c):
        if (pj.get((t, c))):
            return "poly"
        if (m2.get((t, c))):
            return "M2"
        return "M1"

    # ---- layout invariants ----
    for block in build_diffusion_blocks(netlist):
        for a, b in zip(block.members, block.members[1:]):
            pa, pb = placement[a.device], placement[b.device]
            if (pa.row != pb.row or pa.end_col != pb.start_col):
                violations.append("block %s: %s and %s do not abut"
                                  % (block.kind, a.name, b.name))
    blocks = []
    for block in build_diffusion_blocks(netlist):
        p = placement[block.first]
        end = placement[block.last].end_col
        blocks.append((block.first.is_p, p.row, p.start_col, end,
                       block.first.name))
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
            if (a[3] + breakCols > b[2] and not _nets_touch(netlist, a, b)):
                violations.append("diffusion break missing: %s|%s"
                                  % (a[4], b[4]))

    # ---- routing invariants ----
    sig_diff, power_diff = diffusion_access_points(netlist, placement)
    gate = gate_access_points(netlist, placement)
    field = _field_map(netlist, placement, width_cols)
    spans = _gate_spans(netlist, placement, height_um, grid_um)
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
    # dual columns: same net merges at the boundary; different nets must
    # not both reach it (their bars would overlap at y = H/2)
    for c in range(width_cols):
        nOwn, pOwn = route.owners(c)
        if (nOwn is None or pOwn is None):
            continue
        if (nOwn != pOwn):
            if (reachB_n[c] and reachB_p[c]):
                violations.append("column %d: bars of %s and %s both "
                                  "reach the well boundary"
                                  % (c, nOwn, pOwn))
        else:
            if (not (reachB_n[c] and reachB_p[c])):
                violations.append("column %d: same-net bars %s do not "
                                  "merge at the boundary" % (c, nOwn))
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

    # ---- physical connectivity: exact BFS over layers ----
    nets = set(sig_diff) | set(gate)
    for net in sorted(nets):
        if (not _net_connected_exact(netlist, placement, route, net,
                                     sig_diff.get(net, set()),
                                     gate.get(net, []), trackY, spans,
                                     pj, m2, via)):
            violations.append("net %s is not connected" % net)
    return VerifyReport(violations)


def _touches_gate(spans, net, c, t, trackY):
    """Track t lies inside the y-range the (net, c) gate stripe spans."""
    gy0, gy1 = spans[(net, c)]
    return gy0 + CONTACT_S / 2 <= trackY[t] <= gy1 - CONTACT_S / 2


def _nets_touch(netlist, a, b):
    blocks = build_diffusion_blocks(netlist)
    byName = {blk.first.name: blk for blk in blocks}
    blkA, blkB = byName[a[4]], byName[b[4]]
    return blkA.right_net == blkB.left_net


def _net_connected_exact(netlist, placement, route, net, diffPts, gateCols,
                         trackY, spans, pj, m2, via):
    """Exact physical connectivity.

    Nodes: (t, c) for M1 segments, (M2, (t, c)) for M2 segments,
    (PJ, (t, c)) for poly jumps, (G, c) for gate stripes,
    (NB, c)/(PB, c) for the slot bars.  Edges: same-track same-layer
    segments merge across a column boundary; a via joins the M1 and M2
    ends of two adjacent same-net segments; a bar joins the (t, c) nodes
    of the tracks its index interval covers (so a same-net dual pair
    reaching T3 merges through the (T3, c) node); the gate stripe at c
    joins every M1/poly segment crossing it on a track inside its
    y-range (M1 via contact, poly via merge; M2 floats above and never
    joins).  True when every access is in one component.
    """
    nodes = set()
    adj = {}

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
    # vias join the adjacent same-net segments' M1 and M2 ends
    for (t, c), on in via.items():
        if (not on):
            continue
        if (route.hseg.get((t, c - 1)) != net
                or route.hseg.get((t, c)) != net):
            continue
        edge(_end(t, c - 1, c), _end(t, c, c))
    # bars join the tracks their interval covers (index rule); a dual
    # pair both reaching T3 merges through the (T3, c) node
    for c in range(route.width_cols):
        for net2, lo, hi, slot in route.stripes(c):
            if (net2 != net):
                continue
            bar = "NB" if slot == "N" else "PB"
            for t in range(N_TRACKS):
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
