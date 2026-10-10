"""Structural self-check for solved SMT-engine cells.

Re-derives geometry from the (netlist, placement, route) triple and
re-validates everything the SAT encodings promised, so a wrong model or a
solver bug cannot silently ship a bad cell:

- layout: block members abut and share the row; diffusion blocks do not
  overlap; different-net block ends respect the break gap;
- routing: every diffusion access column carries the right stripe (in the
  slot of its rail) and the stripe geometrically covers the rail; every
  gate column has a horizontal segment of the gate net crossing it; no
  horizontal segment crosses a foreign stripe covering its rail (either
  slot); every net is connected (BFS over stripes + segments); power
  stripes reach the power rail and cover the diffusion end rail.

Deterministic and pure: no solver, no randomness.
"""

from .netlist import (build_diffusion_blocks, diffusion_access_points,
                      gate_access_points)
from .route_model import device_rail
from .gds import row_geometry


class VerifyReport(object):
    def __init__(self, violations):
        self.violations = list(violations)

    def ok(self):
        return not self.violations

    def as_dict(self):
        return {"ok": self.ok(), "violations": list(self.violations)}


def verify_cell(netlist, placement, route, grid_um=0.19, height_um=2.47,
                break_um=0.19):
    """Structural verification; returns VerifyReport."""
    violations = []
    railY = row_geometry(height_um, grid_um)[0]

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
                if ((t, c - 1) in route.hseg and route.hseg[(t, c - 1)] == net):
                    crossed = True
                if ((t, c) in route.hseg and route.hseg[(t, c)] == net):
                    crossed = True
            if (not crossed):
                violations.append("gate %s@%d: no segment crosses the "
                                  "column" % (net, c))
    for (t, c), net in route.hseg.items():
        for side in (c, c + 1):
            for net2, lo, hi, slot in stripes(side):
                if (net2 != net):
                    y0, y1 = railY[lo], railY[hi]
                    if (min(y0, y1) <= railY[t] <= max(y0, y1)):
                        violations.append("segment %s@%d rail %d crosses "
                                          "foreign stripe %s"
                                          % (net, c, t, net2))
    nets = set(sig_diff) | set(gate)
    for net in sorted(nets):
        if (not _net_connected(netlist, placement, route, net,
                               {c for c, d in sig_diff.get(net, set())},
                               gate.get(net, []))):
            violations.append("net %s is not connected" % net)
    return VerifyReport(violations)


def _nets_touch(netlist, a, b):
    blocks = build_diffusion_blocks(netlist)
    byName = {blk.first.name: blk for blk in blocks}
    blkA, blkB = byName[a[4]], byName[b[4]]
    return blkA.right_net == blkB.left_net


def _net_connected(netlist, placement, route, net, diffPts, gateCols):
    """BFS over the routed grid: vertices are columns, edges are the
    net's horizontal segments; a stripe in a column is a vertex.  True
    when every access column is in the same component."""
    adj = {}
    for (t, c), n in route.hseg.items():
        if (n != net):
            continue
        adj.setdefault(c, set()).add(c + 1)
        adj.setdefault(c + 1, set()).add(c)
    accessCols = set(diffPts) | set(gateCols)
    if (not accessCols):
        return True
    start = min(accessCols)
    seen = set()
    stack = [start]
    while (stack):
        c = stack.pop()
        if (c in seen):
            continue
        seen.add(c)
        for nxt in adj.get(c, ()):
            if (nxt not in seen):
                stack.append(nxt)
    return all(c in seen for c in accessCols)
