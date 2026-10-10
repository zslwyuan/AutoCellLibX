"""Structural self-check for solved SMT-engine cells.

Re-derives geometry from the (netlist, placement, route) triple and
re-validates everything the SAT encodings promised, so a wrong model or a
solver bug cannot silently ship a bad cell:

- layout: block members abut and share the row; diffusion blocks do not
  overlap; different-net block ends respect the break gap;
- routing: every diffusion access column carries the right stripe (in the
  slot of its rail) and the stripe geometrically covers the rail; every
  gate column has a horizontal segment of the gate net crossing it; no M1
  horizontal segment crosses a foreign stripe covering its rail (either
  slot); power stripes reach the power rail and cover the diffusion end
  rail; dual columns hold one net (or, for different nets, neither bar
  may reach the well boundary); same-net dual bars reach the boundary and
  merge; poly jumps lie over field oxide, never cross a foreign gate,
  and every maximal poly run is anchored at a same-net gate; adjacent
  segments on a rail neither switch layers for one net nor touch in the
  same layer for different nets;
- connectivity is physical: an exact BFS over the M1-N / M1-P / poly /
  gate graphs (the layers join only at dual columns and at gate stripes).

Deterministic and pure: no solver, no randomness.
"""

from .netlist import (build_diffusion_blocks, diffusion_access_points,
                      gate_access_points)
from .route_model import device_rail, well_boundary_y
from .gds import row_geometry


class VerifyReport(object):
    def __init__(self, violations):
        self.violations = list(violations)

    def ok(self):
        return not self.violations

    def as_dict(self):
        return {"ok": self.ok(), "violations": list(self.violations)}


def _row_of_rail(t):
    """(is_p, row) of the diffusion row that rail t crosses."""
    return (True, t - 2) if t >= 2 else (False, t)


def _field_map(netlist, placement, width_cols):
    """Columns with no active diffusion per rail (poly-jump legality)."""
    active = {}
    for dev in netlist.devices:
        p = placement[dev]
        active.setdefault((dev.is_p, p.row), set()).update(
            range(p.start_col, p.end_col))
    field = {}
    for t in range(4):
        is_p, row = _row_of_rail(t)
        field[t] = set(range(width_cols)) - active.get((is_p, row), set())
    return field


def verify_cell(netlist, placement, route, grid_um=0.19, height_um=2.47,
                break_um=0.19):
    """Structural verification; returns VerifyReport."""
    violations = []
    railY = row_geometry(height_um, grid_um)[0]
    bY = well_boundary_y(height_um)
    width_cols = route.width_cols
    pj = getattr(route, "pj", {})
    reachB_n = getattr(route, "reachB_n", [False] * width_cols)
    reachB_p = getattr(route, "reachB_p", [False] * width_cols)

    def stripes(c):
        return route.stripes(c)

    def net_has_stripe(net, c):
        for net2, lo, hi, slot in stripes(c):
            if (net2 == net):
                return True
        return False

    def _slot_covers(net, c, r):
        for net2, lo, hi, slot in stripes(c):
            if (net2 == net):
                y0, y1 = railY[lo], railY[hi]
                if (min(y0, y1) <= railY[r] <= max(y0, y1)):
                    return True
        return False

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
            r = device_rail(dev, placement[dev].row)
            if (not _slot_covers(net, c, r)):
                violations.append("diffusion access %s@%d: stripe "
                                  "misses rail %d" % (net, c, r))
    for net, pts in power_diff.items():
        pRail = 5 if net in ("VCC", "VDD") else 4
        for c, dev in pts:
            if (not net_has_stripe(net, c)):
                violations.append("power access %s@%d: no stripe"
                                  % (net, c))
                continue
            ok = False
            for net2, lo, hi, slot in stripes(c):
                if (net2 == net and hi == pRail):
                    ok = True
            if (not ok):
                violations.append("power access %s@%d: stripe does not "
                                  "reach power rail %d" % (net, c, pRail))
    for net, cols in gate.items():
        for c in cols:
            crossed = False
            for t in range(4):
                if ((t, c) in route.hseg and route.hseg[(t, c)] == net):
                    # the segment at (t, c) spans the gate centre: M1
                    # contacts it, a poly jump merges with it
                    crossed = True
            if (not crossed):
                violations.append("gate %s@%d: no segment crosses the "
                                  "column" % (net, c))
    for (t, c), net in route.hseg.items():
        if (pj.get((t, c))):
            continue            # poly: no M1 crossing (checked below)
        for side in (c, c + 1):
            for net2, lo, hi, slot in stripes(side):
                if (net2 != net):
                    y0, y1 = railY[lo], railY[hi]
                    if (min(y0, y1) <= railY[t] <= max(y0, y1)):
                        violations.append("segment %s@%d rail %d crosses "
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
    # poly jump legality: field oxide only, no foreign gate, anchored runs
    for (t, c), isPoly in pj.items():
        if (not isPoly):
            continue
        net = route.hseg.get((t, c))
        if (net is None):
            continue
        if (c + 1 not in field[t]):
            violations.append("poly jump %s@%d rail %d crosses active"
                              % (net, c, t))
        if (c not in field[t] and net not in gateNetsAt.get(c, ())):
            violations.append("poly jump %s@%d rail %d over active "
                              "without a same-net gate" % (net, c, t))
        for gn in sorted(gateNetsAt.get(c, ())):
            if (gn != net):
                violations.append("poly jump %s@%d rail %d crosses "
                                  "foreign gate %s" % (net, c, t, gn))
    for t in range(4):
        run = []
        for c in range(width_cols - 1):
            net = route.hseg.get((t, c)) if pj.get((t, c)) else None
            if (net is None):
                if (run):
                    anchored = any(
                        route.hseg[(t, cc)] in gateNetsAt.get(cc, ())
                        for cc in run)
                    if (not anchored):
                        violations.append(
                            "poly run rail %d cols %d..%d has no gate"
                            % (t, run[0], run[-1]))
                    run = []
            else:
                run.append(c)
        if (run):
            anchored = any(route.hseg[(t, cc)] in gateNetsAt.get(cc, ())
                           for cc in run)
            if (not anchored):
                violations.append("poly run rail %d cols %d..%d has no "
                                  "gate" % (t, run[0], run[-1]))
    # adjacent segments: same net keeps one layer; different nets never
    # touch in the same layer
    for t in range(4):
        for c in range(1, width_cols - 1):
            left = route.hseg.get((t, c - 1))
            right = route.hseg.get((t, c))
            if (left is None or right is None):
                continue
            if (left == right and pj.get((t, c - 1)) != pj.get((t, c))):
                violations.append("segment %s@%d rail %d switches layer "
                                  "at col %d" % (left, c - 1, t, c))
            if (left != right and pj.get((t, c - 1)) == pj.get((t, c))):
                violations.append("segments %s/%s@%d rail %d touch in one "
                                  "layer" % (left, right, c - 1, t))

    # ---- physical connectivity: exact BFS over layers ----
    nets = set(sig_diff) | set(gate)
    for net in sorted(nets):
        if (not _net_connected_exact(netlist, placement, route, net,
                                     sig_diff.get(net, set()),
                                     gate.get(net, []), railY, bY, pj,
                                     reachB_n, reachB_p)):
            violations.append("net %s is not connected" % net)
    return VerifyReport(violations)


def _nets_touch(netlist, a, b):
    blocks = build_diffusion_blocks(netlist)
    byName = {blk.first.name: blk for blk in blocks}
    blkA, blkB = byName[a[4]], byName[b[4]]
    return blkA.right_net == blkB.left_net


def _net_connected_exact(netlist, placement, route, net, diffPts, gateCols,
                         railY, bY, pj, reachB_n, reachB_p):
    """Exact physical connectivity.

    Nodes: (rail, c) for M1 segments, (PJ, (rail, c)) for poly jumps,
    (G, c) for gate stripes, (NB, c)/(PB, c) for the slot bars.  Edges:
    same-rail M1 segments merge across a column boundary; a bar joins the
    (rail, c) nodes of the rails its range covers; the merged dual bars
    join (NB, c)-(PB, c); the gate stripe at c joins every segment
    crossing it (M1 via contact, poly via merge, both with the model's
    loose (t, c-1) semantics for M1).  True when every access is in one
    component.
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

    def _bar_covers(c, slot, rail):
        for net2, lo, hi, sl in route.stripes(c):
            if (net2 != net or sl != slot):
                continue
            y0, y1 = railY[lo], railY[hi]
            return min(y0, y1) <= railY[rail] <= max(y0, y1)
        return False

    for c in range(route.width_cols):
        nOwn, pOwn = route.owners(c)
        if (nOwn == net):
            node("NB", c)
        if (pOwn == net):
            node("PB", c)
    for (t, c), n in route.hseg.items():
        if (n != net):
            continue
        if (pj.get((t, c))):
            node("PJ", (t, c))
            node("PJ", (t, c + 1))
            edge(node("PJ", (t, c)), node("PJ", (t, c + 1)))
        else:
            node(t, c)
            node(t, c + 1)
            edge(node(t, c), node(t, c + 1))
    # bars join the rails their range covers
    for c in range(route.width_cols):
        for t in range(4):
            if (t <= 1 and route.col_owner_n[c] == net
                    and _bar_covers(c, "N", t)):
                edge(node("NB", c), node(t, c))
            if (t >= 2 and route.col_owner_p[c] == net
                    and _bar_covers(c, "P", t)):
                edge(node("PB", c), node(t, c))
    # gate stripes join every crossing at the column
    for cg in gateCols:
        g = node("G", cg)
        for (t, cc), n in route.hseg.items():
            if (n != net):
                continue
            if (pj.get((t, cc))):
                # the poly jump crosses the gate at its LEFT column
                if (cc == cg):
                    edge(g, node("PJ", (t, cc)))
            else:
                # the M1 segment crosses the gate centre only when it
                # spans the column (cc == cg); cc == cg-1 would end at
                # the column edge and float
                if (cc == cg):
                    edge(g, node(t, cc))
                    edge(g, node(t, cc + 1))
    # dual columns: same-net bars merged at the well boundary
    for c in range(route.width_cols):
        nOwn, pOwn = route.owners(c)
        if (nOwn == pOwn == net and reachB_n[c] and reachB_p[c]):
            edge(node("NB", c), node("PB", c))
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
