"""ASTRAN-style GDS emission for slot-model bigcell placements.

Geometry per doc/BIGCELL_SLOT_GEOMETRY.md (reverse-engineered from
flow/original_astran_cells + autocell2.cpp): W is drawn VERTICALLY (one
diffusion strip per member, y-extent = W), the horizontal footprint is
the terminal/gate slot sequence (terminal contacts on the column edges,
poly stripes at the column centres), and the supply rails are drawn
inside the cell (invariant 2).  Layer/stream numbers come from
smt_engine.gds (active 1, poly 9, contact 10, metal1 49, ...), imported
-- not forked.

Frame: die x 0 is the outline's left edge; the routing grid's column c
lives at ESCAPE_L_UM + c * GRID_UM (the left pin-escape margin ASTRAN
compacts around).  The GDS header is honest (1 um user units, 1 nm
precision), like smt_engine.gds -- layout_sanity reads it with
units_per_um=1.0.

Without a RouteResult the emitter draws the geometry evidence (strips,
gates, contacts, rails, power stubs) and no signal wiring; with one,
the route's stripes/segments/vias/poly-jumps are drawn shifted into the
die frame (best effort -- route_grid's slot-model adaptation is
pending, design note section 8).
"""

import gdstk

from smt_engine.gds import (CONTACT_S, LAYER, M1_W, M2_W, POLY_OVERHANG,
                            POLY_W, row_geometry, track_geometry)

from bigcell_engine.geometry import (BREAK_GAP_COLS, ESCAPE_L_UM, GRID_UM,
                                     HEIGHT_UM, MID_UM, N_ROW, P_ROW,
                                     POWER_NETS, STRIP_ENC_UM, WELL_GAP_UM,
                                     contact_nets, row_gate_columns,
                                     slot_diffusion_access, width_um)

#: the supply-rail width, measured 0.13 um on every reference cell
RAIL_W_UM = 0.13

#: contacts stacked vertically once the strip is tall enough (ASTRAN
#: draws two per terminal column at W = 0.5, one at W = 0.25)
TWO_CONTACT_W_UM = 0.45

CONTACT_PITCH = 0.14            # measured stack pitch (INVX1: 1.5425/1.6825)


def _strip_y(is_p, w_dev, height_um=HEIGHT_UM):
    """(y0, y1) of a member's diffusion strip: W tall, anchored at the
    well boundary (N grows down from MID - WELL_GAP, P grows up)."""
    if is_p:
        y0 = MID_UM + WELL_GAP_UM
        return y0, y0 + w_dev
    y1 = MID_UM - WELL_GAP_UM
    return y1 - w_dev, y1


def _gate_entries_by_col(ordering_p, ordering_n, leg_widths):
    """Column -> {row: (gate_net, device)}: the poly-stripe pass's map,
    shared by the stripe drawing, the gate-contact tracks and the
    gate-only pin labels."""
    gates = {P_ROW: row_gate_columns(ordering_p, leg_widths),
             N_ROW: row_gate_columns(ordering_n, leg_widths)}
    by_col = {}
    for row, items in gates.items():
        for c, net, dev in items:
            by_col.setdefault(c, {})[row] = (net, dev)
    return by_col


def cell_gds(netlist, placement, width_cols, ordering_p, ordering_n,
             leg_widths, route=None, cell_name="SYNTH", grid_um=GRID_UM,
             height_um=HEIGHT_UM):
    """Build a gdstk Library for one slot-model cell.

    ``placement`` maps Device -> PlacedTransistor (slot IR); the two
    orderings are the orientation-aware block sequences the placement
    was built from.  Returns (library, pin_labels); pin_labels is
    [(x, y, net)] (signal labels only when a route is supplied).
    """
    if not ordering_p or not ordering_n:
        raise ValueError("both rows need at least one diffusion block")
    orderings = {P_ROW: list(ordering_p), N_ROW: list(ordering_n)}
    w_um = width_um(width_cols, grid_um)
    edge_x = lambda e: ESCAPE_L_UM + e * grid_um          # noqa: E731
    trackY, barY = track_geometry(height_um, grid_um)

    cell = gdstk.Cell(cell_name)

    def rect(x0, y0, x1, y1, layer):
        cell.add(gdstk.rectangle((x0, y0), (x1, y1), layer=layer))

    # --- outline + wells (ASTRAN's 0.235 overhang) ---
    rect(0.0, 0.0, w_um, height_um, LAYER["prBoundary"])
    ovh = 0.235
    rect(-ovh, MID_UM, w_um + ovh, height_um + ovh, LAYER["nwell"])
    rect(-ovh, -ovh, w_um + ovh, MID_UM, LAYER["pwell"])

    # --- diffusion strips: one per member, y-extent = W (the model) ---
    for row_ordering in (ordering_p, ordering_n):
        col = 0
        prev_right = None
        first_edge = last_edge = None
        spans = []
        for block in row_ordering:
            if prev_right is not None \
                    and block.members[0].left_net != prev_right:
                col += BREAK_GAP_COLS
            for member in block.members:
                p = placement[member.device]
                w = p.legs * p.leg_width_cols
                spans.append((member, col, col + w))
                if first_edge is None:
                    first_edge = col
                last_edge = col + w
                col += w
            prev_right = block.members[-1].right_net
        for member, c0, c1 in spans:
            y0, y1 = _strip_y(member.device.is_p, member.device.width_um,
                              height_um)
            x0 = edge_x(c0) - (STRIP_ENC_UM / 2 if c0 == first_edge else 0.0)
            x1 = edge_x(c1) + (STRIP_ENC_UM / 2 if c1 == last_edge else 0.0)
            rect(x0, y0, x1, y1, LAYER["active"])

    # --- poly stripes at the gate slots, merged where P/N gates align ---
    by_col = _gate_entries_by_col(ordering_p, ordering_n, leg_widths)
    for c in sorted(by_col):
        entries = by_col[c]
        xc = edge_x(c) + grid_um / 2.0
        p_entry = entries.get(P_ROW)
        n_entry = entries.get(N_ROW)
        if (p_entry is not None and n_entry is not None
                and p_entry[0] == n_entry[0]):
            # aligned P/N gates share one straight poly stripe (ASTRAN
            # style) spanning both devices' strips
            ny0, _ = _strip_y(False, n_entry[1].width_um, height_um)
            _, py1 = _strip_y(True, p_entry[1].width_um, height_um)
            rect(xc - POLY_W / 2, ny0 - POLY_OVERHANG,
                 xc + POLY_W / 2, py1 + POLY_OVERHANG, LAYER["poly"])
            continue
        for row, (net, dev) in sorted(entries.items()):
            y0, y1 = _strip_y(row == P_ROW, dev.width_um, height_um)
            rect(xc - POLY_W / 2, y0 - POLY_OVERHANG,
                 xc + POLY_W / 2, y1 + POLY_OVERHANG, LAYER["poly"])

    # --- supply rails (drawn inside the cell, invariant 2) + labels ---
    rect(0.0, 0.0, w_um, RAIL_W_UM, LAYER["metal1"])
    rect(0.0, height_um - RAIL_W_UM, w_um, height_um, LAYER["metal1"])
    cell.add(gdstk.Label("GND", origin=(w_um / 2.0, RAIL_W_UM / 2.0),
                         layer=LAYER["metal1"]))
    cell.add(gdstk.Label("VCC", origin=(w_um / 2.0,
                                        height_um - RAIL_W_UM / 2.0),
                         layer=LAYER["metal1"]))

    # --- diffusion contacts + power stubs ---
    contactable = (contact_nets(ordering_p, netlist, leg_widths)
                   | contact_nets(ordering_n, netlist, leg_widths))
    drawn = set()
    for row_ordering in (ordering_p, ordering_n):
        col = 0
        prev_right = None
        for block in row_ordering:
            if prev_right is not None \
                    and block.members[0].left_net != prev_right:
                col += BREAK_GAP_COLS
            for member in block.members:
                p = placement[member.device]
                w = p.legs * p.leg_width_cols
                y0, y1 = _strip_y(member.device.is_p,
                                  member.device.width_um, height_um)
                for net, e in ((member.left_net, col),
                               (member.right_net, col + w)):
                    if net not in contactable:
                        continue
                    xc = edge_x(e)
                    is_power = net in POWER_NETS
                    k = 2 if (y1 - y0) >= TWO_CONTACT_W_UM else 1
                    cy = (y0 + y1) / 2.0
                    centers = [cy] if k == 1 else \
                        [cy - CONTACT_PITCH / 2.0, cy + CONTACT_PITCH / 2.0]
                    for y in centers:
                        key = (round(xc, 4), round(y, 4))
                        if key in drawn:
                            continue
                        drawn.add(key)
                        rect(xc - CONTACT_S / 2, y - CONTACT_S / 2,
                             xc + CONTACT_S / 2, y + CONTACT_S / 2,
                             LAYER["contact"])
                        if is_power:
                            # M1 stub from the contact to its rail
                            if member.device.is_p:
                                rect(xc - M1_W / 2, y - CONTACT_S / 2,
                                     xc + M1_W / 2, height_um,
                                     LAYER["metal1"])
                            else:
                                rect(xc - M1_W / 2, 0.0,
                                     xc + M1_W / 2, y + CONTACT_S / 2,
                                     LAYER["metal1"])
                col += w
            prev_right = block.members[-1].right_net

    # --- routing layers when a route is supplied (best effort) ---
    pin_labels = []
    if route is not None and getattr(route, "ok", False):
        pin_labels = _draw_route(cell, route, edge_x, trackY, barY,
                                 grid_um, height_um, netlist, placement,
                                 ordering_p, ordering_n, leg_widths,
                                 by_col)

    lib = gdstk.Library("BIGCELL", unit=1e-6, precision=1e-9)
    lib.add(cell)
    return lib, pin_labels




def _gate_contact_tracks(gate_entries, placement, grid_um, height_um,
                         trackY):
    """(gate_net, column) -> sorted tracks where a gate contact square is
    drawable on the drawn poly.

    The router's slot-model gate-track rule (route_grid._gate_maps, doc
    section 8.4), which verify's row-band spans accept: every same-net
    strip clipped to the verify row band and expanded by the poly
    overhang less the contact half-size, plus the well-boundary corridor
    T3 where an aligned P/N gate pair makes the drawn merged poly stripe
    continuous over the boundary (the drawn merged rect spans
    [n-strip y0, p-strip y1] +/- POLY_OVERHANG, so a contact square at
    MID +/- WELL_GAP - CONTACT_S/2 sits fully on poly).  A crossing on
    one of these tracks is a real poly/M1 contact; without the T3 clause
    a corridor crossing verifies but draws nothing (honest-gaps round).
    """
    _, rows = row_geometry(height_um, grid_um)
    by_net = {}
    for c, entries in gate_entries.items():
        for _row, (net, dev) in entries.items():
            by_net.setdefault((net, c), []).append(dev)
    out = {}
    for (net, c), devs in by_net.items():
        band = [rows[(dev.is_p, placement[dev].row)] for dev in devs]
        y0 = min(b[0] for b in band)
        y1 = max(b[1] for b in band)
        tracks = set()
        for dev in devs:
            sy0, sy1 = _strip_y(dev.is_p, dev.width_um, height_um)
            lo = max(sy0, y0) - POLY_OVERHANG + CONTACT_S / 2.0
            hi = min(sy1, y1) + POLY_OVERHANG - CONTACT_S / 2.0
            tracks.update(t for t in range(len(trackY))
                          if lo <= trackY[t] <= hi)
        if any(dev.is_p for dev in devs) \
                and any(not dev.is_p for dev in devs):
            lo = MID_UM - WELL_GAP_UM + CONTACT_S / 2.0
            hi = MID_UM + WELL_GAP_UM - CONTACT_S / 2.0
            tracks.update(t for t in range(len(trackY))
                          if lo <= trackY[t] <= hi)
        out[(net, c)] = sorted(tracks)
    return out


def _draw_route(cell, route, edge_x, trackY, barY, grid_um, height_um,
                netlist, placement, ordering_p, ordering_n, leg_widths,
                gate_entries):
    """Draw a RouteResult shifted into the die frame; return pin labels."""
    m2 = getattr(route, "m2", {}) or {}
    via = getattr(route, "via", {}) or {}
    pj = getattr(route, "pj", {}) or {}
    m2v = getattr(route, "m2v", {}) or {}
    m2via = getattr(route, "m2via", {}) or {}

    def rect(x0, y0, x1, y1, layer):
        cell.add(gdstk.rectangle((x0, y0), (x1, y1), layer=layer))

    for c in range(route.width_cols):
        for net, lo, hi, _slot in route.stripes(c):
            xc = edge_x(c)
            rect(xc - M1_W / 2, barY[lo] - M1_W / 2,
                 xc + M1_W / 2, barY[hi] + M1_W / 2, LAYER["metal1"])
    for (t, c), net in sorted(route.hseg.items()):
        layer = LAYER["metal2"] if m2.get((t, c)) else LAYER["metal1"]
        w = M1_W
        rect(edge_x(c), trackY[t] - w / 2, edge_x(c + 1), trackY[t] + w / 2,
             layer)
    for (t, c), on in sorted(via.items()):
        if not on:
            continue
        xc = edge_x(c)
        rect(xc - CONTACT_S / 2, trackY[t] - CONTACT_S / 2,
             xc + CONTACT_S / 2, trackY[t] + CONTACT_S / 2, LAYER["via1"])
    # the metal2 vertical freedom (additive): a span is the column-
    # stripe primitive on metal2 (one column across a track range --
    # the via-up / M2 / via-down track change); a node via squares the
    # M1<->M2 junction at a single point
    for (c, t1, t2), _net in sorted(m2v.items()):
        xc = edge_x(c)
        rect(xc - M2_W / 2, trackY[t1] - M2_W / 2,
             xc + M2_W / 2, trackY[t2] + M2_W / 2, LAYER["metal2"])
    for (t, c), on in sorted(m2via.items()):
        if not on:
            continue
        xc = edge_x(c)
        rect(xc - CONTACT_S / 2, trackY[t] - CONTACT_S / 2,
             xc + CONTACT_S / 2, trackY[t] + CONTACT_S / 2, LAYER["via1"])
    for (t, c), net in sorted(pj.items()):
        if not net:
            continue
        rect(edge_x(c), trackY[t] - POLY_W / 2,
             edge_x(c + 1), trackY[t] + POLY_W / 2, LAYER["poly"])

    # gate contacts: an M1 (or poly) crossing of the gate net on a track
    # inside the stripe's y-range, at the gate column centre.  Drawable
    # tracks: the member's own W-tall strip (the historical rule) union
    # the router/verify contact range -- the corridor track T3 of an
    # aligned P/N gate pair draws its square on the merged poly over the
    # well boundary (route_grid._gate_maps slot rule; without it a
    # verifying corridor crossing emitted no contact square).
    contact_tracks = _gate_contact_tracks(gate_entries, placement,
                                          grid_um, height_um, trackY)
    drawn = set()
    for row_ordering in (ordering_p, ordering_n):
        col = 0
        prev_right = None
        for block in row_ordering:
            if prev_right is not None \
                    and block.members[0].left_net != prev_right:
                col += BREAK_GAP_COLS
            for member in block.members:
                p = placement[member.device]
                for j in range(p.legs):
                    c = col + j * p.leg_width_cols
                    xc = edge_x(c) + grid_um / 2.0
                    y0, y1 = _strip_y(member.device.is_p,
                                      member.device.width_um, height_um)
                    for t in range(len(trackY)):
                        right = route.hseg.get((t, c)) \
                            if c <= route.width_cols - 2 else None
                        if right != member.device.gate:
                            continue
                        if not (y0 <= trackY[t] <= y1
                                or t in contact_tracks.get(
                                    (member.device.gate, c), ())):
                            continue
                        key = (round(xc, 4), round(trackY[t], 4))
                        if key in drawn:
                            break
                        drawn.add(key)
                        rect(xc - CONTACT_S / 2, trackY[t] - CONTACT_S / 2,
                             xc + CONTACT_S / 2, trackY[t] + CONTACT_S / 2,
                             LAYER["contact"])
                        break
                col += p.legs * p.leg_width_cols
            prev_right = block.members[-1].right_net

    # pin labels on each signal net's first diffusion access column
    sig, _pow = slot_diffusion_access(netlist, placement,
                                      (ordering_p, ordering_n), leg_widths)
    labels = []
    for net in sorted(sig):
        pts = sig[net]
        if not pts:
            continue
        c = pts[0][0]
        lo = None
        for net2, lo2, _hi2, _slot in route.stripes(c):
            if net2 == net:
                lo = lo2
                break
        x = edge_x(c) if lo is None else edge_x(c)
        y = barY[lo] if lo is not None else height_um / 2.0
        labels.append((x, y, net))
        cell.add(gdstk.Label(net, origin=(x, y), layer=LAYER["metal1"]))

    # gate-only nets (no diffusion access anywhere): their terminal is
    # the poly stripe at the gate column -- the terminal the router
    # exposes for them (route_grid materializes their crossing straight
    # onto the gate node).  Label the first sorted gate column on the
    # drawn poly, the way the diffusion labels label the first
    # edge-column contact.  Only external nets: an internal gate-only
    # node is no pin.
    ports = getattr(netlist, "external", set())
    labeled = set(t[2] for t in labels)
    gate_nets = set(net2 for entries in gate_entries.values()
                    for _row, (net2, _dev) in entries.items())
    for net in sorted(gate_nets):
        if net in sig or net in POWER_NETS or net in labeled \
                or net not in ports:
            continue
        span = None
        for c in sorted(gate_entries):
            own = [dev for _row, (net2, dev)
                   in gate_entries[c].items() if net2 == net]
            if not own:
                continue
            if len(own) > 1:
                # aligned pair: the drawn merged stripe over the boundary
                ny0, _ = _strip_y(False,
                                  next(d.width_um for d in own
                                       if not d.is_p), height_um)
                _, py1 = _strip_y(True,
                                  next(d.width_um for d in own
                                       if d.is_p), height_um)
                span = (ny0 - POLY_OVERHANG, py1 + POLY_OVERHANG)
            else:
                y0, y1 = _strip_y(own[0].is_p, own[0].width_um, height_um)
                span = (y0 - POLY_OVERHANG, y1 + POLY_OVERHANG)
            x = edge_x(c) + grid_um / 2.0
            break
        if span is None:
            continue
        y = (span[0] + span[1]) / 2.0
        labels.append((x, y, net))
        cell.add(gdstk.Label(net, origin=(x, y), layer=LAYER["poly"]))
    return labels


def write_cell_gds(path, netlist, placement, width_cols, ordering_p,
                   ordering_n, leg_widths, route=None, **kw):
    """Write one slot-model cell to ``path``; returns pin_labels.

    The GDS timestamp is pinned (invariant 9: identical inputs give
    byte-identical GDS files, cross-process).
    """
    import datetime
    lib, pins = cell_gds(netlist, placement, width_cols, ordering_p,
                         ordering_n, leg_widths, route=route, **kw)
    lib.write_gds(path, timestamp=datetime.datetime(1970, 1, 1))
    return pins
