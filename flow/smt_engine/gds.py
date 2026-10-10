"""GDS emission for solved SMT-engine cells.

Geometry follows the ASTRAN convention probed from generated cells
(LAYER7_ASTRAN.md + real COMPLEX*.gds): transistors sit in columns on the
routing grid, poly stripes are vertical at the leg centres, diffusion
blocks fill the (row, column) rectangle, M1 stripes are vertical in
columns / horizontal on rails, power rails run along the row edges.
Layer/stream numbers match tech_freePDK45.rul (active 1, poly 9, contact
10, metal1 49, nwell 3, pwell 2, prBoundary 235) so the output is
consumable by the existing sanity and pin-accessibility checkers.

The GDS header is honest (1 um user units, 1 nm precision): unlike
ASTRAN's bogus UNITS record there is nothing to calibrate around -- the
log-free loading path in gui/gds_model and pin_accessibility trusts it.

Geometry (all um):
    H      = cellsHeight * vGrid (13 x 0.19 = 2.47)
    rails  = 0.13 tall M1 power strips at the row edges
    N rows = [railW, H/2), P rows = [H/2, H - railW), two rows each
    poly   = 0.05 wide vertical stripe, centred on the leg column
    M1     = 0.07 wide stripes / 0.07 tall segments
    contact= 0.07 x 0.07 squares
"""

import os

import gdstk

LAYER = {
    "active": 1, "pwell": 2, "nwell": 3, "poly": 9, "contact": 10,
    "metal1": 49, "prBoundary": 235,
}

POLY_W = 0.05
M1_W = 0.07
CONTACT_S = 0.07
RAIL_W = 0.13
POLY_OVERHANG = 0.05        # poly sticks past the diffusion edge

GND_RAIL = 4
VCC_RAIL = 5


def row_geometry(height_um, grid_um, rail_w=RAIL_W):
    """Rail y-centres and per-row rectangles for a row height.

    Returns (railY, rows) where railY[r] is the centre y of rail r
    (0/1 N rows, 2/3 P rows, 4 GND, 5 VCC) and rows maps (is_p, row) to
    (y0, y1) diffusion rectangles.
    """
    n_lo = rail_w
    n_hi = height_um / 2.0
    p_lo = height_um / 2.0
    p_hi = height_um - rail_w
    dh = (n_hi - n_lo) / 2.0
    rows = {}
    for r in range(2):
        rows[(False, r)] = (n_lo + r * dh, n_lo + (r + 1) * dh)
        rows[(True, r)] = (p_lo + r * dh, p_lo + (r + 1) * dh)
    railY = [0.0] * 6
    for r in range(2):
        y0, y1 = rows[(False, r)]
        railY[r] = (y0 + y1) / 2.0
        y0, y1 = rows[(True, r)]
        railY[r + 2] = (y0 + y1) / 2.0
    railY[GND_RAIL] = rail_w / 2.0
    railY[VCC_RAIL] = height_um - rail_w / 2.0
    return railY, rows


def _track_x(col, grid_um):
    """x of the routing track in column col (column edge: c*g)."""
    return col * grid_um


def _col_x(col, grid_um):
    """x of the column centre (poly stripes, gate contacts)."""
    return (col + 0.5) * grid_um


def cell_gds(netlist, placement, route, grid_um=0.19, height_um=2.47,
             rail_w=RAIL_W):
    """Build a gdstk Library for a solved cell (layout + route).

    Returns (library, pin_labels) where pin_labels is [(x, y, net)] for
    the M1 pin texts.  Raises ValueError when the route is not usable.
    """
    if (not route.ok):
        raise ValueError("cannot emit GDS: route status %s" % route.status_name)
    railY, rows = row_geometry(height_um, grid_um, rail_w)
    width_um = route.width_cols * grid_um
    cell = gdstk.Cell("SYNTH")
    g = grid_um

    def rect(x0, y0, x1, y1, layer):
        cell.add(gdstk.rectangle((x0, y0), (x1, y1), layer=layer))

    # --- outline and wells ---
    rect(0, 0, width_um, height_um, LAYER["prBoundary"])
    rect(0, height_um / 2.0, width_um, height_um, LAYER["nwell"])
    rect(0, 0, width_um, height_um / 2.0, LAYER["pwell"])

    # --- diffusion blocks (one per device, its own row rectangle) ---
    for dev in netlist.devices:
        p = placement[dev]
        y0, y1 = rows[(dev.is_p, p.row)]
        rect(p.start_col * g, y0, p.end_col * g, y1, LAYER["active"])

    # --- poly stripes, one per leg, merged per (column, gate net) so
    # aligned P/N gates share one straight stripe (ASTRAN style) ---
    polyCols = {}
    for dev in netlist.devices:
        p = placement[dev]
        for j in range(p.legs):
            c = p.start_col + j * p.leg_width_cols + p.leg_width_cols // 2
            polyCols.setdefault((c, dev.gate), []).append((dev.is_p, p.row))
    for (c, net), entries in sorted(polyCols.items()):
        y0 = min(rows[(is_p, r)][0] for is_p, r in entries)
        y1 = max(rows[(is_p, r)][1] for is_p, r in entries)
        xc = _col_x(c, g)
        rect(xc - POLY_W / 2, y0 - POLY_OVERHANG,
             xc + POLY_W / 2, y1 + POLY_OVERHANG, LAYER["poly"])

    # --- power rails ---
    rect(0, 0, width_um, rail_w, LAYER["metal1"])
    rect(0, height_um - rail_w, width_um, height_um, LAYER["metal1"])

    # --- vertical M1 stripes (one per occupied slot: N and P halves can
    # share a column because their y-ranges do not overlap; a same-net
    # pair merges when both bars reach the well boundary) ---
    bY = height_um / 2.0
    for c in range(route.width_cols):
        for net, lo, hi, slot in route.stripes(c):
            xc = _track_x(c, g)
            # rail indices are not y-ordered (GND rail 4 sits below N
            # rows): the stripe spans the min..max rail centre
            ya, yb = railY[lo], railY[hi]
            y0 = min(ya, yb) - M1_W / 2
            y1 = max(ya, yb) + M1_W / 2
            if (slot == "N" and route.reachB_n[c]):
                y1 = max(y1, bY + M1_W / 2)
            if (slot == "P" and route.reachB_p[c]):
                y0 = min(y0, bY - M1_W / 2)
            rect(xc - M1_W / 2, y0, xc + M1_W / 2, y1, LAYER["metal1"])

    # --- horizontal M1 segments ---
    for (t, c), net in sorted(route.hseg.items()):
        rect(c * g, railY[t] - M1_W / 2, (c + 1) * g, railY[t] + M1_W / 2,
             LAYER["metal1"])

    # --- poly jumps: horizontal poly wires on the rails (they cross
    # foreign M1 stripes in a different layer and merge with same-net
    # gate stripes) ---
    for (t, c), net in sorted(route.pj.items()):
        if (net and route.hseg.get((t, c)) is not None):
            rect(c * g, railY[t] - POLY_W / 2, (c + 1) * g,
                 railY[t] + POLY_W / 2, LAYER["poly"])

    # --- contacts: diffusion access points, power ends, gate crossings ---
    for dev in netlist.devices:
        p = placement[dev]
        y0, y1 = rows[(dev.is_p, p.row)]
        for j in range(p.legs):
            c = p.start_col + j * p.leg_width_cols + p.leg_width_cols // 2
            xc = _col_x(c, g)
            # gate contact: an M1 segment of the gate net crossing this
            # column (the model's gate access semantics); a poly jump
            # crossing merges with the gate stripe directly (no contact)
            gateNet = dev.gate
            touched = False
            for t in range(4):
                left = route.hseg.get((t, c - 1)) if c - 1 >= 0 else None
                right = route.hseg.get((t, c)) if c <= route.width_cols - 2 \
                    else None
                if (left == gateNet and not route.pj.get((t, c - 1))):
                    rect(xc - CONTACT_S / 2, railY[t] - CONTACT_S / 2,
                         xc + CONTACT_S / 2, railY[t] + CONTACT_S / 2,
                         LAYER["contact"])
                    touched = True
                    break
                if (right == gateNet and not route.pj.get((t, c))):
                    rect(xc - CONTACT_S / 2, railY[t] - CONTACT_S / 2,
                         xc + CONTACT_S / 2, railY[t] + CONTACT_S / 2,
                         LAYER["contact"])
                    touched = True
                    break
            if (not touched):
                # poly-only gate connection: the jump merges with the gate
                # stripe (same layer); no contact is drawn.  The model
                # guarantees an M1 or poly crossing for every gate.
                for t in range(4):
                    right = route.hseg.get((t, c)) \
                        if c <= route.width_cols - 2 else None
                    if (right == gateNet and route.pj.get((t, c))):
                        touched = True
                        break
                if (not touched):
                    raise ValueError(
                        "gate %s@%d has no crossing segment"
                        % (gateNet, c))
    # diffusion-end contacts: block ends whose net is routed
    from .netlist import diffusion_access_points
    sig, _ = diffusion_access_points(netlist, placement)
    for net, pts in sig.items():
        for c, dev in pts:
            if (route.col_owner_n[c] != net
                    and route.col_owner_p[c] != net):
                continue
            xc = _track_x(c, g)
            p = placement[dev]
            y0, y1 = rows[(dev.is_p, p.row)]
            rect(xc - CONTACT_S / 2, (y0 + y1) / 2 - CONTACT_S / 2,
                 xc + CONTACT_S / 2, (y0 + y1) / 2 + CONTACT_S / 2,
                 LAYER["contact"])

    # --- pin labels on M1 ---
    pin_labels = []
    for net, pts in sig.items():
        if (not pts):
            continue
        c = pts[0][0]
        lo = None
        for cc, _dev in pts:
            for net2, lo2, hi2, _slot in route.stripes(cc):
                if (net2 == net):
                    c, lo = cc, lo2
                    break
            if (lo is not None):
                break
        xc = _track_x(c, g)
        y = railY[lo] if lo is not None else height_um / 2
        pin_labels.append((xc, y, net))
        cell.add(gdstk.Label(net, origin=(xc, y), layer=LAYER["metal1"]))
    for net in ("VCC", "VDD", "GND", "VSS"):
        lo = None
        c = None
        for cc in range(route.width_cols):
            for net2, lo2, hi2, _slot in route.stripes(cc):
                if (net2 == net):
                    c, lo = cc, lo2
                    break
            if (c is not None):
                break
        if (c is None):
            continue
        xc = _track_x(c, g)
        # label the stripe, not the rail: the checker resolves the pin
        # bbox from the metal around the label, and a rail label picks up
        # the whole rail (and any poly crossing it)
        y = railY[lo]
        pin_labels.append((xc, y, net))
        cell.add(gdstk.Label(net, origin=(xc, y), layer=LAYER["metal1"]))
    lib = gdstk.Library("SYNTH", unit=1e-6, precision=1e-9)
    lib.add(cell)
    return lib, pin_labels


def lo_hi_inverted(route, c):
    return route.lo[c] > route.hi[c]


def write_cell_gds(path, netlist, placement, route, **kw):
    """Write the solved cell to ``path``; returns pin_labels."""
    lib, pins = cell_gds(netlist, placement, route, **kw)
    lib.write_gds(path)
    return pins


def main(argv=None):
    import argparse
    from . import synth
    ap = argparse.ArgumentParser(description="SMT engine: synth -> GDS")
    ap.add_argument("--sp", required=True, help="SPICE subcircuit file")
    ap.add_argument("--out", default="synth.gds")
    ap.add_argument("--grid", type=float, default=0.19)
    ap.add_argument("--height", type=float, default=2.47)
    ap.add_argument("--layout-time", type=float, default=60.0)
    ap.add_argument("--route-time", type=float, default=60.0)
    args = ap.parse_args(argv)
    with open(args.sp, 'r', errors="ignore") as f:
        text = f.read()
    result = synth.synth_cell(text, grid_um=args.grid,
                              height_um=args.height,
                              layout_time_s=args.layout_time,
                              route_time_s=args.route_time)
    if (result.route is None):
        print("synth failed: layout=%s route=%s"
              % (result.layout.status_name,
                 result.route.status_name if result.route else "n/a"))
        return 1
    write_cell_gds(args.out, result.netlist, result.layout.devices,
                   result.route, grid_um=args.grid, height_um=args.height)
    print("synth OK: width=%.3f um (%d cols) route=%s hseg=%d vseg=%d"
          % (result.route.width_cols * args.grid, result.route.width_cols,
             result.route.status_name, result.route.hseg_count,
             result.route.vseg_count))
    print("gds written:", args.out)
    return 0


if (__name__ == "__main__"):
    raise SystemExit(main())
