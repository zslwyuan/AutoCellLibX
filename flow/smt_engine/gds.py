"""GDS emission for solved SMT-engine cells.

Geometry follows the ASTRAN convention probed from generated cells
(LAYER7_ASTRAN.md + real COMPLEX*.gds): transistors sit in columns on the
routing grid, poly stripes are vertical at the leg centres, diffusion
blocks fill the (row, column) rectangle, M1 stripes are vertical in
columns / horizontal on rails, power rails run along the row edges.
Layer/stream numbers match tech_freePDK45.rul (active 1, poly 9, contact
10, metal1 49, via1 50, metal2 51, nwell 3, pwell 2, prBoundary 235) so
the output is consumable by the existing sanity and pin-accessibility
checkers.

The GDS header is honest (1 um user units, 1 nm precision): unlike
ASTRAN's bogus UNITS record there is nothing to calibrate around -- the
log-free loading path in gui/gds_model and pin_accessibility trusts it.

Geometry (all um):
    H      = cellsHeight * vGrid (13 x 0.19 = 2.47)
    rails  = 0.13 tall M1 power strips at the row edges
    N rows = [railW, H/2), P rows = [H/2, H - railW), two rows each
    poly   = 0.05 wide vertical stripe, centred on the leg column
    M1     = 0.07 wide stripes / 0.07 tall segments
    M2     = 0.07 tall escape segments above M1; a via1 squares the
             M1<->M2 junction at the segment boundary
    contact= 0.07 x 0.07 squares
"""

import os

import gdstk

LAYER = {
    "active": 1, "pwell": 2, "nwell": 3, "poly": 9, "contact": 10,
    "metal1": 49, "via1": 50, "metal2": 51, "prBoundary": 235,
}

POLY_W = 0.05
M1_W = 0.07
M2_W = 0.07
VIA_S = 0.06
CONTACT_S = 0.07
RAIL_W = 0.13
POLY_OVERHANG = 0.05        # poly sticks past the diffusion edge

GND_RAIL = 4
VCC_RAIL = 5

# ---------------------------------------------------------------------------
# The track domains (the RouteResult vocabulary's vertical axis)
# ---------------------------------------------------------------------------
#
# The bar9 domain is the historical 7-track / 9-bar-level model (T0..T6 +
# the two rail levels -- see track_geometry below).  The astran13 domain is
# the faithful port of ASTRAN's own rule-derived track list, calcArea's
# trackPos (tools/astran/src/autocell2.cpp:68-100), at the production
# geometry of AGENTS.md invariant 2 (set rowheight 13 / grid 0.19 0.19 /
# supplysize 0.26 / nwellpos 1.235, tools/astran/build/Work/
# tech_freePDK45.rul, resolution 400 internal units/um):
#
# - the track pitch is S1M1M1 + W1M1 = 0.065 + 0.065 = 0.13 um
#   (autocell2.cpp:91/:98; rules.cpp getIntValue = ceil(f*resolution) so
#   the internal pitch is the exact integer 52/400);
# - the central track sits at center*vGrid with
#   center = round(posNWell/vGrid - 0.5) = round(1.235/0.19 - 0.5) = 6,
#   i.e. y = 1.14 um (autocell2.cpp:85-86) -- the level every measured
#   GDS shows as the busiest M1 row (NAND2X1's 1.14 stripe);
# - tracks below descend by the pitch while next >= supWidth =
#   max(0.26, W1M1)/2 = 0.13 (autocell2.cpp:79/:89-93): 1.01, 0.88, ...,
#   and one final 0.10 level is inserted before the guard rejects it
#   (the do-while inserts first);
# - tracks above ascend while next + S2M1M1(0.090) <= height - supWidth =
#   2.34 (autocell2.cpp:96-100): 1.27 .. 2.18 accepted, plus one final
#   2.31 level (the do-while's last insert).
#
# That is 18 rule-derived levels: the two END levels (0.10 / 2.31) are
# the POWER nets' own tracks -- autocell2.cpp:55-56 does
# addNodetoNet(gnd, met[0]) / addNodetoNet(vdd, met[17]) for EVERY column,
# so no signal can ever occupy them -- and the 16 interior levels
# (0.23 .. 2.18) are the signal tracks.  This port folds the power end
# levels into the bar domain's rail ends (a power bar reaching level 0 /
# level 17 draws through exactly that y range, ASTRAN's gnd/vdd tree on
# their end track subsumed), and keeps the 16 signal tracks verbatim:
# trackY = [0.23, 0.36, 0.49, 0.62, 0.75, 0.88, 1.01, 1.14, 1.27, 1.40,
#           1.53, 1.66, 1.79, 1.92, 2.05, 2.18]
# barY   = [0.065 (GND rail), trackY..., 2.405 (VCC rail)]  (18 levels).
#
# (The "~13" of AUDIT 5.60-5.62 / route_grid's docstring counts the 0.19
# grid rows the 18-level list SPANS; the C++ derivation itself is exact
# and yields 18 levels / 16 signal tracks.  The corridor pair straddling
# the nwell is 1.14 / 1.27 -- ASTRAN's createElement central-cost region
# nDiffIni < x <= pDiffIni -- and this domain's boundary track is the
# upper one, 1.27: the N-half slot reaches it from below and the P-half
# from above, the same single shared merge level bar9's T3 provides.)
#
# The astran13 diffusion row-track map mirrors ASTRAN's own terminal
# bands: the N diffusion's terminal track is the topmost track below
# nDif_iniY = posNWell - S1DNWN = 1.18 (autocell2.cpp:268 stops at
# trackPos[7] = 1.01), the P diffusion's the bottom-most track at or
# above pDif_iniY = posNWell + E1WNDP = 1.29 (autocell2.cpp:255 stops at
# trackPos[10] = 1.40).  On the slot model those are rails 1 (N row,
# y-top anchored) and 2 (P row); rails 0/3 (the exact engine's two
# sub-rows per polarity) keep the same spread over the sub-bands.
#
# The slot model's diffusion strips (bigcell_engine.geometry._strip_y) are
# W tall, anchored WELL_GAP = 0.0725 from the nwell boundary -- the
# anchors below mirror them so smt_engine stays layering-clean.

#: the registered track domains
TRACK_DOMAINS = ("bar9", "astran13")

#: ASTRAN's rule values for the track derivation (tech_freePDK45.rul, um)
ASTRAN_S1M1M1 = 0.065             # rul:51 -- the track pitch below/above
ASTRAN_W1M1 = 0.065               # rul:64
ASTRAN_S2M1M1 = 0.090             # rul:52 -- the above-loop stop guard
ASTRAN_SUPPLY_VSIZE = 0.26        # set supplysize 0.26 (astran.py)
#: the slot-model strip anchor: the strip edge's distance from the nwell
#: boundary (bigcell_engine.geometry.WELL_GAP_UM, measured S1DNWN band)
ASTRAN_WELL_GAP_UM = 0.0725


def astran_track_positions(height_um=2.47, grid_um=0.19):
    """ASTRAN calcArea's rule-derived trackPos list (autocell2.cpp:83-100),
    in um: the 18 levels from the do-while descents around the central
    track.  Pure function of (height_um, grid_um) -- the run-script
    geometry is posNWell = height/2 (``set nwellpos 1.235`` at H 2.47) and
    supWidth = max(0.26, W1M1)/2.  Deterministic (invariant 9)."""
    pos_nwell = height_um / 2.0
    sup = max(ASTRAN_SUPPLY_VSIZE, ASTRAN_W1M1) / 2.0
    pitch = ASTRAN_S1M1M1 + ASTRAN_W1M1
    center = int(round(pos_nwell / grid_um - 0.5))
    pos = [center * grid_um]
    # below the central track (autocell2.cpp:89-93): insert, then guard
    while True:
        nxt = pos[0] - pitch
        pos.insert(0, nxt)
        if not (nxt >= sup):
            break
    # above (autocell2.cpp:96-100)
    while True:
        nxt = pos[-1] + pitch
        pos.append(nxt)
        if not (nxt + ASTRAN_S2M1M1 <= height_um - sup):
            break
    return pos


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


def track_geometry(height_um, grid_um, rail_w=RAIL_W, tracks="bar9"):
    """(trackY, barY): the routing tracks and bar-domain levels of the
    selected track domain.

    bar9 (default): y-centres of the 7 routing tracks (the four row
    centres, the two row edges and the well-boundary corridor) and the 9
    bar-domain levels [GND, T0..T6, VCC]; barY = [GND] + trackY + [VCC],
    so a bar's (lo, hi) covers track t iff lo <= t+1 <= hi (one sorted
    list -- no inverted ranges).

    astran13: ASTRAN's own rule-derived list (see the module header and
    :func:`astran_track_positions`): the 16 interior signal tracks of the
    18-level trackPos list plus the two rail levels, same
    ``barY = [GND] + trackY + [VCC]`` index discipline.  rail_w is
    accepted for signature compatibility and only positions the bar9
    rails (astran13's rails sit at RAIL_W from the die edges, the same
    0.13 -- the values coincide at the production geometry)."""
    if tracks == "bar9":
        railY, rows = row_geometry(height_um, grid_um, rail_w)
        trackY = [railY[0], rows[(False, 0)][1], railY[1],
                  height_um / 2.0,
                  railY[2], rows[(True, 0)][1], railY[3]]
        barY = [railY[GND_RAIL]] + trackY + [railY[VCC_RAIL]]
        return trackY, barY
    if tracks == "astran13":
        pos = astran_track_positions(height_um, grid_um)
        sup = max(ASTRAN_SUPPLY_VSIZE, ASTRAN_W1M1) / 2.0
        # the signal tracks: the levels the two guards ACCEPT (the two
        # rejected end inserts are the power nets' own tracks -- folded
        # into the bar domain's rail ends below)
        trackY = [y for y in pos
                  if y >= sup and y + ASTRAN_S2M1M1 <= height_um - sup]
        gnd_c = rail_w / 2.0
        vcc_c = height_um - rail_w / 2.0
        barY = [gnd_c] + trackY + [vcc_c]
        return trackY, barY
    raise ValueError("unknown track domain %r (TRACK_DOMAINS=%r)"
                     % (tracks, TRACK_DOMAINS))


class TrackDomain(object):
    """One track domain's complete parameter record -- everything the
    route model, the verifier, the router and the renderers need to speak
    the same vertical vocabulary (the bar9 defaults reproduce the
    historical module constants exactly, so default-domain behaviour is
    byte-identical).

    Fields:

    - ``name``;
    - ``n_tracks`` / ``bar_levels``: the signal track count and the bar
      domain level count (barY = [GND] + trackY + [VCC]);
    - ``boundary_t``: the boundary TRACK index -- the one track both
      column slots may cover (bar9's T3, astran13's 1.27 track), i.e. the
      merge level of a same-net dual pair; always n_tracks // 2;
    - ``row_track``: diffusion rail (0/1 N, 2/3 P) -> its access track;
    - ``row_tracks``: the tracks poly jumps run on (bar9: the four row
      centres; astran13: every track -- ASTRAN's pol nodes exist wherever
      the diffusion bands leave room, per column);
    - ``row_of_track``: track -> (is_p, row) for the field/poly legality
      maps (astran13: y-aware, below/above the nwell boundary);
    - ``strip_anchored``: whether the gate spans / diffusion geometry
      follow the slot model's W-tall well-anchored strips (astran13)
      instead of the four sub-row bands (bar9);
    - ``trackY`` / ``barY``: the y positions themselves.
    """

    def __init__(self, name, n_tracks, bar_levels, boundary_t, row_track,
                 row_tracks, row_of_track, strip_anchored, trackY, barY):
        self.name = name
        self.n_tracks = n_tracks
        self.bar_levels = bar_levels
        self.boundary_t = boundary_t
        self.row_track = dict(row_track)
        self.row_tracks = tuple(row_tracks)
        self.row_of_track = dict(row_of_track)
        self.strip_anchored = strip_anchored
        self.trackY = list(trackY)
        self.barY = list(barY)

    @property
    def n_tracks_set(self):
        """Tracks the N-half slot may cover (t <= boundary)."""
        return tuple(range(0, self.boundary_t + 1))

    @property
    def p_tracks_set(self):
        """Tracks the P-half slot may cover (t >= boundary)."""
        return tuple(range(self.boundary_t, self.n_tracks))

    def strip_y(self, is_p, width_um, height_um):
        """(y0, y1) of a W-tall well-anchored diffusion strip (the slot
        model's drawing convention, bigcell_engine.geometry._strip_y --
        N grows down from MID-WELL_GAP, P grows up from MID+WELL_GAP)."""
        mid = height_um / 2.0
        if is_p:
            y0 = mid + ASTRAN_WELL_GAP_UM
            return y0, y0 + width_um
        y1 = mid - ASTRAN_WELL_GAP_UM
        return y1 - width_um, y1


def track_domain(tracks, height_um=2.47, grid_um=0.19, rail_w=RAIL_W):
    """The :class:`TrackDomain` record of a registered domain.

    bar9's record reproduces route_model's historical module constants
    (N_TRACKS 7, BAR_LEVELS 9, BOUNDARY_T 3, ROW_TRACK {0:0,1:2,2:4,3:6},
    ROW_TRACKS (0,2,4,6)) and verify's ROW_OF_TRACK verbatim.  astran13's
    row_track mirrors ASTRAN's terminal bands (N rail 1 -> 1.01, P rail 2
    -> 1.40; rails 0/3 keep the spread over the exact engine's sub-bands),
    and its row_of_track splits the 16 tracks at the nwell boundary onto
    the slot model's two rows (P row 0, N row 1 -- the split the strip
    anchors define).  Pure; deterministic (invariant 9)."""
    trackY, barY = track_geometry(height_um, grid_um, rail_w, tracks)
    if tracks == "bar9":
        return TrackDomain(
            "bar9", 7, 9, 3,
            {0: 0, 1: 2, 2: 4, 3: 6},
            (0, 2, 4, 6),
            {0: (False, 0), 2: (False, 1), 4: (True, 0), 6: (True, 1)},
            False, trackY, barY)
    # astran13: locate ASTRAN's terminal bands on the signal list.  The
    # N slot row (rail 1) rides ASTRAN's nDiffTrackIni -- the topmost
    # track of the central-cost region's low side, 1.01 (autocell2.cpp:
    # 268) -- and the P slot row (rail 2) its pDiffTrackIni, 1.40
    # (autocell2.cpp:255): both drawable on the slot strips for every
    # real W (the strip anchors at MID +/- WELL_GAP).  Rails 0/3 (the
    # exact engine's sub-rows) keep the spread, anchored toward the well.
    n_well_track = max(t for t in range(len(trackY))
                       if trackY[t] < height_um / 2.0)
    p_well_track = n_well_track + 1
    n_term = n_well_track - 1 if n_well_track > 0 else 0
    p_term = min(p_well_track + 1, len(trackY) - 1)
    _, rows = row_geometry(height_um, grid_um, rail_w)
    lo0 = max((t for t in range(len(trackY))
               if trackY[t] <= rows[(False, 0)][1]), default=0)
    hi3 = min((t for t in range(len(trackY))
               if trackY[t] >= rows[(True, 1)][0]), default=len(trackY) - 1)
    return TrackDomain(
        "astran13", len(trackY), len(barY), p_well_track,
        {0: lo0, 1: n_term, 2: p_term, 3: hi3},
        tuple(range(len(trackY))),
        dict((t, (False, 1) if t <= n_well_track else (True, 0))
             for t in range(len(trackY))),
        True, trackY, barY)


def _track_x(col, grid_um):
    """x of the routing track in column col (column edge: c*g)."""
    return col * grid_um


def _col_x(col, grid_um):
    """x of the column centre (poly stripes, gate contacts)."""
    return (col + 0.5) * grid_um


def cell_gds(netlist, placement, route, grid_um=0.19, height_um=2.47,
             rail_w=RAIL_W, tracks="bar9"):
    """Build a gdstk Library for a solved cell (layout + route).

    ``tracks`` selects the route's track domain (TRACK_DOMAINS): the
    RouteResult's hseg keys and bar endpoints speak that domain's
    trackY/barY, so the renderer must draw on the same list.  Default
    bar9 keeps the historical drawing byte-identical.

    Returns (library, pin_labels) where pin_labels is [(x, y, net)] for
    the M1 pin texts.  Raises ValueError when the route is not usable.
    """
    if (not route.ok):
        raise ValueError("cannot emit GDS: route status %s" % route.status_name)
    railY, rows = row_geometry(height_um, grid_um, rail_w)
    trackY, barY = track_geometry(height_um, grid_um, rail_w, tracks)
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
    # pair merges when both bars reach the boundary -- the reach is the
    # bar endpoint itself in the y-sorted bar domain) ---
    for c in range(route.width_cols):
        for net, lo, hi, slot in route.stripes(c):
            xc = _track_x(c, g)
            y0 = barY[lo] - M1_W / 2
            y1 = barY[hi] + M1_W / 2
            rect(xc - M1_W / 2, y0, xc + M1_W / 2, y1, LAYER["metal1"])

    # --- horizontal M1 segments (M2 segments are drawn on metal2) ---
    route_m2 = getattr(route, "m2", {}) or {}
    route_via = getattr(route, "via", {}) or {}
    for (t, c), net in sorted(route.hseg.items()):
        if (route_m2.get((t, c))):
            continue
        rect(c * g, trackY[t] - M1_W / 2, (c + 1) * g,
             trackY[t] + M1_W / 2, LAYER["metal1"])

    # --- M2 escape segments: horizontal metal2 wires on the tracks,
    # crossing foreign M1 stripes without a short ---
    for (t, c), net in sorted(route.hseg.items()):
        if (not route_m2.get((t, c))):
            continue
        rect(c * g, trackY[t] - M2_W / 2, (c + 1) * g,
             trackY[t] + M2_W / 2, LAYER["metal2"])

    # --- vias: an M1<->M2 connection at the boundary between two
    # adjacent segments (t, c-1) and (t, c) ---
    for (t, c), on in sorted(route_via.items()):
        if (not on):
            continue
        rect(c * g - VIA_S / 2, trackY[t] - VIA_S / 2,
             c * g + VIA_S / 2, trackY[t] + VIA_S / 2, LAYER["via1"])

    # --- metal2 vertical freedom (additive: routes without it draw
    # exactly as before): a span is metal2 occupying one COLUMN across a
    # track range (the column-stripe primitive on metal2, enabling track
    # changes via-up -> M2 span -> via-down); a node via squares the
    # M1<->M2 junction at a single (track, column) point ---
    route_m2v = getattr(route, "m2v", {}) or {}
    route_m2via = getattr(route, "m2via", {}) or {}
    for (c, t1, t2), _net in sorted(route_m2v.items()):
        rect(c * g - M2_W / 2, trackY[t1] - M2_W / 2,
             c * g + M2_W / 2, trackY[t2] + M2_W / 2, LAYER["metal2"])
    for (t, c), on in sorted(route_m2via.items()):
        if (on):
            rect(c * g - VIA_S / 2, trackY[t] - VIA_S / 2,
                 c * g + VIA_S / 2, trackY[t] + VIA_S / 2, LAYER["via1"])

    # --- poly jumps: horizontal poly wires on the row tracks (they cross
    # foreign M1 stripes in a different layer and merge with same-net
    # gate stripes) ---
    for (t, c), net in sorted(route.pj.items()):
        if (net and route.hseg.get((t, c)) is not None):
            rect(c * g, trackY[t] - POLY_W / 2, (c + 1) * g,
                 trackY[t] + POLY_W / 2, LAYER["poly"])

    # --- contacts: diffusion access points, power ends, gate crossings ---
    for dev in netlist.devices:
        p = placement[dev]
        y0, y1 = rows[(dev.is_p, p.row)]
        for j in range(p.legs):
            c = p.start_col + j * p.leg_width_cols + p.leg_width_cols // 2
            xc = _col_x(c, g)
            # gate contact: an M1 segment of the gate net CROSSING this
            # column (spanning [c*g, (c+1)*g] -- a segment at (t, c-1)
            # ends at the column edge and would leave the contact
            # floating); a poly jump crossing merges directly (no contact)
            gateNet = dev.gate
            touched = False
            for t in range(len(trackY)):
                right = route.hseg.get((t, c)) if c <= route.width_cols - 2 \
                    else None
                if (right == gateNet and not route.pj.get((t, c))
                        and not route_m2.get((t, c))):
                    rect(xc - CONTACT_S / 2, trackY[t] - CONTACT_S / 2,
                         xc + CONTACT_S / 2, trackY[t] + CONTACT_S / 2,
                         LAYER["contact"])
                    touched = True
                    break
            if (not touched):
                # poly-only gate connection: the jump merges with the gate
                # stripe (same layer); no contact is drawn.  The model
                # guarantees an M1 or poly crossing for every gate.
                for t in range(len(trackY)):
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
        y = barY[lo] if lo is not None else height_um / 2
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
        y = barY[lo]
        pin_labels.append((xc, y, net))
        cell.add(gdstk.Label(net, origin=(xc, y), layer=LAYER["metal1"]))
    lib = gdstk.Library("SYNTH", unit=1e-6, precision=1e-9)
    lib.add(cell)
    return lib, pin_labels


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
