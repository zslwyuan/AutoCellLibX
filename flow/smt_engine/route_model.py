"""Stage 2 of the SMT engine: grid routing SAT encoding.

With the placement fixed (stage 1), every net's terminals are a set of
(column, track) access points.  Routing is a grid model over the cell:

- the cell has **7 horizontal tracks**: the four diffusion-row centre
  rails (T0, T2, T4, T6 -- the old "rails 0..3"), the two row-edge levels
  (T1, T5) and the well-boundary corridor (T3).  The ASTRAN comparison
  (doc/AUDIT_REPORT.md) showed a real router uses ~13 M1 levels; the
  four-row model boxed every rail change into columns already walled by
  power stripes, which is what made COMPLEX0 unroutable -- the boundary
  track T3 is the N<->P corridor that dissolves those walls;
- every column carries up to **two** vertical M1 stripes -- one in the N
  half (spanning y of [GND, T3]) and one in the P half ([T3, VCC]).  Bar
  endpoints are indices into the y-sorted 9-level bar domain
  [GND, T0, T1, T2, T3, T4, T5, T6, VCC] with lo <= hi enforced, so a
  bar's coverage is a pure index interval (the old rail-index domain
  allowed inverted (lo, hi) mega-bars spanning half the cell);
- a same-net pair of bars in one column joins the N and P halves by
  *both reaching T3* (hi_n == lo_p == boundary index); bars of different
  nets may not both reach T3 (they would overlap at the boundary).  The
  old explicit reachB booleans are gone -- the reach is the endpoint;
- a *diffusion* access point (net, c, track) forces the owning slot in
  column c to carry the net, and the stripe must cover the track
  (coverage is the index interval rule above);
- a *gate* access point (net, c) is a contact between the vertical poly
  stripe and a *horizontal* segment crossing column c **at a y the
  stripe actually spans**: the stripe covers only the rows of its
  devices (plus overhang), so a single-row gate can be contacted only on
  tracks inside its y-range (the old model accepted any rail -- a
  contact beside the stripe floats);
- horizontal segments hseg[t][c] (track t, between columns c and c+1):
  * if an end column carries a same-net stripe it must cover the track;
    an end without a stripe is a legal stub -- a gate contact or a pin;
  * crossing safety: no foreign M1 stripe in either slot of an end
    column may cover the track -- **unless the segment is a poly jump or
    on M2** (different layers, no short);
- **poly jumps**: a segment may be routed on poly instead of M1, but only
  on the four row tracks (poly between rows would land on the diffusion
  edge).  The jump is legal only over field oxide and only where every
  gate stripe it geometrically crosses belongs to the segment's net
  (poly-poly crossing shorts; same-net merges).  Every maximal poly run
  must contain a segment crossing a same-net gate (a CP-SAT automaton
  per (net, track)); the gate merge is the only junction between the M1
  and poly parts of a net (there is no M1-poly contact in the model);
- **M2 escapes**: a segment may instead be routed on metal2.  M2 runs
  above M1, so an M2 segment may cross foreign M1 stripes -- the escape
  hatch when every track is blocked on M1 and poly is illegal.  An M2
  segment never touches gates or stripes, never changes track, and joins
  the M1 part of its net only through a **via** forced at every same-net
  M1|M2 junction; every maximal M2 run must end in a via on both sides
  (otherwise it is dead metal the sweep would miscount as presence);
- connectivity is **track-aware**: the sweep forces each column between
  the leftmost and rightmost access to carry N or P presence, each gap
  to be bridged, and each track change to happen at a join -- a same-net
  bar covering both tracks, a merged T3 pair for N<->P changes, or a
  gate whose stripe spans both tracks (with an M1 relay crossing on the
  left track: a segment merely ENDING at the gate column stops short of
  the stripe);
- power nets: their access columns get a stripe reaching the fixed power
  end of the bar domain (GND=0, VCC=8); no connectivity needed.

Objective: minimize horizontal segments (wirelength proxy) plus 3 per
vertical stripe plus 15 per poly jump plus 12 per M2 segment plus 5 per
via -- short nets first, few contacts second, M1 preferred over the
escape layers.

Deterministic: all iterations are over sorted structures.
"""

import time

from ortools.sat.python import cp_model

from .netlist import diffusion_access_points, gate_access_points

N_RAILS = 6                     # legacy: 0/1 N rows, 2/3 P, 4=GND, 5=VCC
GND_RAIL = 4
VCC_RAIL = 5
N_TRACKS = 7                    # T0..T6 (T3 is the well boundary)
BOUNDARY_T = 3
ROW_TRACK = {0: 0, 1: 2, 2: 4, 3: 6}    # diffusion rail -> track index
BAR_LEVELS = 9                  # [GND, T0..T6, VCC]
HSEG_WEIGHT = 10
VSEG_WEIGHT = 3
PJUMP_WEIGHT = 15
M2_WEIGHT = 12
VIA_WEIGHT = 5
SOLVE_TIME_LIMIT_S = 60.0

N_TRACKS_SET = (0, 1, 2, 3)
P_TRACKS_SET = (3, 4, 5, 6)
ROW_TRACKS = (0, 2, 4, 6)


def _status_name(status):
    return {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE"}.get(status, "UNKNOWN")


def device_rail(dev, row):
    """Diffusion rail of a device: N rows 0/1, P rows 2/3."""
    return row + (0 if not dev.is_p else 2)


def track_geometry(height_um, grid_um, rail_w=0.13):
    """(trackY, barY): y-centres of the 7 routing tracks and the 9 bar
    domain levels [GND, T0..T6, VCC] -- defined in gds.py."""
    from .gds import track_geometry as _tg
    return _tg(height_um, grid_um, rail_w)


class RouteResult(object):
    def __init__(self, status_name, col_owner_n, col_owner_p, lo_n, hi_n,
                 lo_p, hi_p, hseg, pj, m2, via, reachB_n, reachB_p,
                 width_cols, hseg_count, vseg_count, pj_count, m2_count,
                 via_count):
        self.status_name = status_name
        self.col_owner_n = col_owner_n      # N-half stripe per column
        self.col_owner_p = col_owner_p      # P-half stripe per column
        self.lo_n = lo_n                    # bar-domain indices (0..4)
        self.hi_n = hi_n
        self.lo_p = lo_p                    # bar-domain indices (4..8)
        self.hi_p = hi_p
        self.hseg = hseg                    # dict (track, col) -> net
        self.pj = pj                        # dict (track, col) -> bool
        self.m2 = m2                        # dict (track, col) -> bool
        self.via = via                      # dict (track, col) -> bool
        self.reachB_n = reachB_n            # N bars reaching the boundary
        self.reachB_p = reachB_p
        self.width_cols = width_cols
        self.hseg_count = hseg_count
        self.vseg_count = vseg_count
        self.pj_count = pj_count
        self.m2_count = m2_count
        self.via_count = via_count

    @property
    def ok(self):
        return self.status_name in ("OPTIMAL", "FEASIBLE")

    def owners(self, c):
        """Both slot owners of a column (net names or None)."""
        return self.col_owner_n[c], self.col_owner_p[c]

    def stripes(self, c):
        """(net, lo, hi, slot) tuples for the column's stripes."""
        out = []
        if (self.col_owner_n[c] is not None):
            out.append((self.col_owner_n[c], self.lo_n[c], self.hi_n[c],
                        "N"))
        if (self.col_owner_p[c] is not None):
            out.append((self.col_owner_p[c], self.lo_p[c], self.hi_p[c],
                        "P"))
        return out


class RoutingModel(object):
    """Exposes the model + solution structures for tests and GDS."""

    def __init__(self, model, owner_n, owner_p, lo_n, hi_n, lo_p, hi_p,
                 hseg, pj, m2, via, reachT3_n, reachT3_p, access,
                 width_cols, nets, gate_tracks):
        self.model = model
        self.owner_n = owner_n
        self.owner_p = owner_p
        self.lo_n = lo_n
        self.hi_n = hi_n
        self.lo_p = lo_p
        self.hi_p = hi_p
        self.hseg = hseg
        self.pj = pj
        self.m2 = m2
        self.via = via
        self.reachT3_n = reachT3_n
        self.reachT3_p = reachT3_p
        self.access = access
        self.width_cols = width_cols
        self.nets = nets
        self.gate_tracks = gate_tracks


def _access_points(netlist, placement):
    """(diffusion, gate, power) access maps for a placement.

    diffusion: net -> set of (col, rail); gate: net -> set of cols;
    power: net -> set of (col, diffusion_rail, power_rail).
    The diffusion rail is that of the *terminal device* -- a chain
    member's internal columns carry the neighbour's net, not this net
    (the classic false-access-point trap: column 2 of MnA belongs to n1,
    not to Y, even though Y's P-end block also covers it).
    """
    sig_diff, power_diff = diffusion_access_points(netlist, placement)
    gate = gate_access_points(netlist, placement)
    diffusion = {}
    for net, pts in sig_diff.items():
        for c, dev in pts:
            diffusion.setdefault(net, set()).add(
                (c, device_rail(dev, placement[dev].row)))
    power = {}
    for net, pts in power_diff.items():
        pRail = VCC_RAIL if net in ("VCC", "VDD") else GND_RAIL
        for c, dev in pts:
            power.setdefault(net, set()).add(
                (c, device_rail(dev, placement[dev].row), pRail))
    return diffusion, gate, power


def _gate_track_maps(netlist, placement, width_cols, height_um, grid_um):
    """Per (gate_net, col): the sorted tracks whose y lies inside the
    gate stripe's y-range (its devices' rows plus overhang), so a
    crossing segment actually touches the stripe.

    Also returns gateNetsAt: col -> {gate nets} (any row).
    """
    from .gds import row_geometry, POLY_OVERHANG, CONTACT_S
    _, rows = row_geometry(height_um, grid_um)
    trackY, _ = track_geometry(height_um, grid_um)
    spans = {}
    for dev in netlist.devices:
        p = placement[dev]
        y0, y1 = rows[(dev.is_p, p.row)]
        for j in range(p.legs):
            c = p.start_col + j * p.leg_width_cols + p.leg_width_cols // 2
            if (c >= width_cols):
                continue
            key = (dev.gate, c)
            if (key in spans):
                old0, old1 = spans[key]
                spans[key] = (min(old0, y0), max(old1, y1))
            else:
                spans[key] = (y0, y1)
    gate_tracks = {}
    gateNetsAt = {}
    for (net, c), (y0, y1) in spans.items():
        y0 -= POLY_OVERHANG
        y1 += POLY_OVERHANG
        gateNetsAt.setdefault(c, set()).add(net)
        gate_tracks[(net, c)] = sorted(
            t for t in range(N_TRACKS)
            if (y0 + CONTACT_S / 2 <= trackY[t] <= y1 - CONTACT_S / 2))
    return gate_tracks, gateNetsAt


def _field_map(netlist, placement, width_cols):
    """Row tracks with no active diffusion per row (poly-jump legality):
    returns field[r] = set of columns free in the row of track 2r."""
    active = {}
    for dev in netlist.devices:
        p = placement[dev]
        active.setdefault((dev.is_p, p.row), set()).update(
            range(p.start_col, p.end_col))
    field = {}
    for t in ROW_TRACKS:
        # track 2r is diffusion row r: t=0/2 are N rows 0/1, t=4/6 are
        # P rows 0/1 (the old t//2-1 mapped P tracks to rows 1/2 -- row 2
        # does not exist, so P-row-1 active was invisible to poly
        # legality while P-row-0 jumps were checked against the wrong
        # row; verify.py's ROW_OF_TRACK has the correct mapping)
        is_p, row = (True, t // 2 - 2) if t >= 4 else (False, t // 2)
        field[t] = set(range(width_cols)) - active.get((is_p, row), set())
    return field


def _m1_lit(model, h_lit, pj, m2, n, t, c, memo):
    """Bool: the segment (t, c) is an M1 segment of net n."""
    key = (n, t, c)
    if (key in memo):
        return memo[key]
    lit = model.NewBoolVar("m1_%s_%d_%d" % (n, t, c))
    hl = h_lit[(n, t, c)]
    model.Add(lit == 1).OnlyEnforceIf(hl, pj[(t, c)].Not(),
                                      m2[(t, c)].Not())
    model.Add(lit == 0).OnlyEnforceIf(hl.Not())
    model.Add(lit == 0).OnlyEnforceIf(pj[(t, c)])
    model.Add(lit == 0).OnlyEnforceIf(m2[(t, c)])
    memo[key] = lit
    return lit


def _gm_lit(model, h_lit, m2, n, t, c, memo):
    """Bool: the segment (t, c) of net n is gate-touching metal -- M1 or
    poly, i.e. anything but M2 (M2 floats above the gate; no contact)."""
    key = (n, t, c)
    if (key in memo):
        return memo[key]
    lit = model.NewBoolVar("gm_%s_%d_%d" % (n, t, c))
    hl = h_lit[(n, t, c)]
    model.Add(lit == 1).OnlyEnforceIf(hl, m2[(t, c)].Not())
    model.Add(lit == 0).OnlyEnforceIf(hl.Not())
    model.Add(lit == 0).OnlyEnforceIf(m2[(t, c)])
    memo[key] = lit
    return lit


def build_routing_model(netlist, placement, width_cols=None,
                        grid_um=0.19, height_um=2.47, poly_jumps=True,
                        metal2=True, accesses=None):
    """Stage-2 CP-SAT model over the fixed placement.

    ``accesses`` optionally supplies the (diffusion, gate, power) access
    maps in :func:`_access_points`' rail form instead of deriving them
    from the base netlist walk -- the window-fixing mode
    (:func:`solve_window_routing`) encodes the same access requirements
    smt_engine.verify checks, which for slot-model placements is the
    shared die view rather than the base walk.  Default None keeps the
    historical behaviour byte-identical.

    Returns RoutingModel; solve_routing wraps it.
    """
    if (width_cols is None):
        width_cols = max(p.end_col for p in placement.values())
    model = cp_model.CpModel()

    if (accesses is None):
        diffusion, gate, power = _access_points(netlist, placement)
    else:
        diffusion, gate, power = accesses
    nets = sorted(n for n in (set(diffusion) | set(gate))
                  if n not in ("VCC", "GND", "VDD", "VSS"))
    net_index = {n: i for i, n in enumerate(nets)}
    power_index = {n: len(nets) + i
                   for i, n in enumerate(sorted(power))}
    gate_tracks, gateNetsAt = _gate_track_maps(
        netlist, placement, width_cols, height_um, grid_um)

    # two slots per column: N half (bar domain 0..4) and P half (4..8)
    owner_n = [model.NewIntVar(-1, len(nets) + len(power_index) - 1,
                               "on_%d" % c) for c in range(width_cols)]
    owner_p = [model.NewIntVar(-1, len(nets) + len(power_index) - 1,
                               "op_%d" % c) for c in range(width_cols)]
    lo_n = [model.NewIntVar(0, BOUNDARY_T + 1, "lon_%d" % c)
            for c in range(width_cols)]
    hi_n = [model.NewIntVar(0, BOUNDARY_T + 1, "hin_%d" % c)
            for c in range(width_cols)]
    lo_p = [model.NewIntVar(BOUNDARY_T + 1, BAR_LEVELS - 1, "lop_%d" % c)
            for c in range(width_cols)]
    hi_p = [model.NewIntVar(BOUNDARY_T + 1, BAR_LEVELS - 1, "hip_%d" % c)
            for c in range(width_cols)]
    hseg = {}
    for t in range(N_TRACKS):
        for c in range(width_cols - 1):
            hseg[(t, c)] = model.NewIntVar(
                -1, len(nets) - 1, "hseg_%d_%d" % (t, c))
    pj = {}
    for t in range(N_TRACKS):
        for c in range(width_cols - 1):
            pj[(t, c)] = model.NewBoolVar("pj_%d_%d" % (t, c))
    # M2 escape layer + vias: m2[(t,c)] puts the segment on metal2;
    # via_l[(t,c)] is the M1<->M2 connection between the adjacent
    # segments (t, c-1) and (t, c).  A segment sits on exactly one layer.
    m2 = {}
    for t in range(N_TRACKS):
        for c in range(width_cols - 1):
            m2[(t, c)] = model.NewBoolVar("m2_%d_%d" % (t, c))
    via_l = {}
    for t in range(N_TRACKS):
        for c in range(1, width_cols - 1):
            via_l[(t, c)] = model.NewBoolVar("via_%d_%d" % (t, c))
    for k in m2:
        model.Add(m2[k] + pj[k] <= 1)
    if (not poly_jumps):
        for v in pj.values():
            model.Add(v == 0)
    if (not metal2):
        for v in m2.values():
            model.Add(v == 0)
        for v in via_l.values():
            model.Add(v == 0)

    # bar endpoints are y-ordered: lo <= hi (the old rail-index domain
    # allowed inverted (lo, hi) bars spanning half the cell)
    for c in range(width_cols):
        model.Add(lo_n[c] <= hi_n[c])
        model.Add(lo_p[c] <= hi_p[c])

    # coverage booleans: bar (lo, hi) covers track t iff the index
    # interval contains t+1 (barY and trackY share one sorted list).
    # N slots cover tracks {0..3}, P slots {3..6}.
    def _covers_table(lo_d, hi_d):
        table = {}
        for t in range(N_TRACKS):
            valid = []
            for lo in range(lo_d, hi_d + 1):
                for hi in range(lo, hi_d + 1):
                    if (lo <= t + 1 <= hi):
                        valid.append((lo, hi))
            table[t] = valid
        return table

    nTable = _covers_table(0, BOUNDARY_T + 1)
    pTable = _covers_table(BOUNDARY_T + 1, BAR_LEVELS - 1)
    nCover = sorted(t for t in range(N_TRACKS) if nTable[t])
    pCover = sorted(t for t in range(N_TRACKS) if pTable[t])
    cov_n = {}
    cov_p = {}
    for c in range(width_cols):
        for t in nCover:
            bn = model.NewBoolVar("covN_%d_%d" % (c, t))
            model.AddAllowedAssignments([lo_n[c], hi_n[c]],
                                        nTable[t]).OnlyEnforceIf(bn)
            model.AddForbiddenAssignments([lo_n[c], hi_n[c]],
                                          nTable[t]).OnlyEnforceIf(bn.Not())
            cov_n[(c, t)] = bn
        for t in pCover:
            bp = model.NewBoolVar("covP_%d_%d" % (c, t))
            model.AddAllowedAssignments([lo_p[c], hi_p[c]],
                                        pTable[t]).OnlyEnforceIf(bp)
            model.AddForbiddenAssignments([lo_p[c], hi_p[c]],
                                          pTable[t]).OnlyEnforceIf(bp.Not())
            cov_p[(c, t)] = bp

    # ownership booleans (both slots)
    is_owner_n = {}
    is_owner_p = {}
    for n in nets:
        idx = net_index[n]
        for c in range(width_cols):
            b = model.NewBoolVar("ownN_%s_%d" % (n, c))
            model.Add(owner_n[c] == idx).OnlyEnforceIf(b)
            model.Add(owner_n[c] != idx).OnlyEnforceIf(b.Not())
            is_owner_n[(n, c)] = b
            b = model.NewBoolVar("ownP_%s_%d" % (n, c))
            model.Add(owner_p[c] == idx).OnlyEnforceIf(b)
            model.Add(owner_p[c] != idx).OnlyEnforceIf(b.Not())
            is_owner_p[(n, c)] = b
    for net, idx in power_index.items():
        for c in range(width_cols):
            b = model.NewBoolVar("ownPN_%s_%d" % (net, c))
            model.Add(owner_n[c] == idx).OnlyEnforceIf(b)
            model.Add(owner_n[c] != idx).OnlyEnforceIf(b.Not())
            is_owner_n[(net, c)] = b
            b = model.NewBoolVar("ownPP_%s_%d" % (net, c))
            model.Add(owner_p[c] == idx).OnlyEnforceIf(b)
            model.Add(owner_p[c] != idx).OnlyEnforceIf(b.Not())
            is_owner_p[(net, c)] = b

    # a signal bar must not reach the power ENDS of the bar domain (level
    # 0 = the GND rail, level BAR_LEVELS-1 = the VCC rail): the drawn
    # stripe would overlap the full-width power rail -- a metal short
    # (observed on NAND2 before the rule: the solver was indifferent to
    # signal bar heights and happily drew Y's bar up into the VCC rail)
    for n in nets:
        for c in range(width_cols):
            model.Add(lo_n[c] >= 1).OnlyEnforceIf(is_owner_n[(n, c)])
            model.Add(hi_p[c] <= BAR_LEVELS - 2).OnlyEnforceIf(
                is_owner_p[(n, c)])

    # slot active booleans (for reachT3 channeling and the objective)
    v_active_n = {}
    v_active_p = {}
    for c in range(width_cols):
        b = model.NewBoolVar("vacN_%d" % c)
        model.Add(owner_n[c] != -1).OnlyEnforceIf(b)
        model.Add(owner_n[c] == -1).OnlyEnforceIf(b.Not())
        v_active_n[c] = b
        b = model.NewBoolVar("vacP_%d" % c)
        model.Add(owner_p[c] != -1).OnlyEnforceIf(b)
        model.Add(owner_p[c] == -1).OnlyEnforceIf(b.Not())
        v_active_p[c] = b
    # reachT3: the slot is occupied and its bar reaches the boundary
    reachT3_n = {}
    reachT3_p = {}
    for c in range(width_cols):
        b = model.NewBoolVar("rt3N_%d" % c)
        model.Add(hi_n[c] == BOUNDARY_T + 1).OnlyEnforceIf(b)
        model.Add(hi_n[c] != BOUNDARY_T + 1).OnlyEnforceIf(b.Not())
        model.Add(b <= v_active_n[c])
        reachT3_n[c] = b
        b = model.NewBoolVar("rt3P_%d" % c)
        model.Add(lo_p[c] == BOUNDARY_T + 1).OnlyEnforceIf(b)
        model.Add(lo_p[c] != BOUNDARY_T + 1).OnlyEnforceIf(b.Not())
        model.Add(b <= v_active_p[c])
        reachT3_p[c] = b

    # --- diffusion access points: slot by track, index coverage ---
    for net, pts in diffusion.items():
        idx = net_index[net]
        for c, r in sorted(pts):
            t = ROW_TRACK[r]
            if (r <= 1):                     # N half
                model.Add(owner_n[c] == idx)
                model.Add(cov_n[(c, t)] == 1)
            else:                            # P half
                model.Add(owner_p[c] == idx)
                model.Add(cov_p[(c, t)] == 1)

    # --- power access points: stripe reaches the power end ---
    for net, pts in power.items():
        idx = power_index[net]
        for c, r, pRail in sorted(pts):
            if (pRail == GND_RAIL):
                model.Add(owner_n[c] == idx)
                model.Add(lo_n[c] == 0)
                model.Add(cov_n[(c, ROW_TRACK[r])] == 1)
            else:
                model.Add(owner_p[c] == idx)
                model.Add(hi_p[c] == BAR_LEVELS - 1)
                model.Add(cov_p[(c, ROW_TRACK[r])] == 1)

    # --- dual-column rules: the two bars of one column ---
    # A dual column occupied by the SAME net merges at the boundary (both
    # bars forced to reach T3).  A dual column of DIFFERENT nets is legal
    # (their y-ranges are disjoint) but neither bar may reach T3 -- at
    # the boundary they would overlap and short.
    dual = {}
    for n in nets:
        for c in range(width_cols):
            b = model.NewBoolVar("dual_%s_%d" % (n, c))
            model.Add(b >= is_owner_n[(n, c)] + is_owner_p[(n, c)] - 1)
            model.Add(b <= is_owner_n[(n, c)])
            model.Add(b <= is_owner_p[(n, c)])
            dual[(n, c)] = b
    for n in nets:
        for c in range(width_cols):
            model.Add(reachT3_n[c] >= dual[(n, c)])
            model.Add(reachT3_p[c] >= dual[(n, c)])
    for c in range(width_cols):
        for n1 in nets:
            for n2 in nets:
                if (n1 == n2):
                    continue
                model.Add(reachT3_n[c] + reachT3_p[c]
                          + is_owner_n[(n1, c)] + is_owner_p[(n2, c)] <= 3)

    # --- horizontal segments ---
    h_lit = {}
    for n in nets:
        idx = net_index[n]
        for t in range(N_TRACKS):
            for c in range(width_cols - 1):
                lit = model.NewBoolVar("h_%s_%d_%d" % (n, t, c))
                model.Add(hseg[(t, c)] == idx).OnlyEnforceIf(lit)
                model.Add(hseg[(t, c)] != idx).OnlyEnforceIf(lit.Not())
                h_lit[(n, t, c)] = lit
    h_active = {}
    for (t, c), v in hseg.items():
        b = model.NewBoolVar("act_h_%d_%d" % (t, c))
        model.Add(v != -1).OnlyEnforceIf(b)
        model.Add(v == -1).OnlyEnforceIf(b.Not())
        h_active[(t, c)] = b
    m1_memo = {}
    gm_memo = {}
    for n in nets:
        for t in range(N_TRACKS):
            for c in range(width_cols - 1):
                lit = h_lit[(n, t, c)]
                # same-net stripe at an end must cover the track -- only
                # when that slot can physically reach this track (a P-half
                # stripe never covers T0; a segment on T0 merely floats
                # past it, which is legal), and only for M1/poly ends: an
                # M2 segment runs above the stripe without touching it
                if (t in nCover):
                    model.Add(cov_n[(c, t)] == 1).OnlyEnforceIf(
                        lit, m2[(t, c)].Not(), is_owner_n[(n, c)])
                    model.Add(cov_n[(c + 1, t)] == 1).OnlyEnforceIf(
                        lit, m2[(t, c)].Not(), is_owner_n[(n, c + 1)])
                if (t in pCover):
                    model.Add(cov_p[(c, t)] == 1).OnlyEnforceIf(
                        lit, m2[(t, c)].Not(), is_owner_p[(n, c)])
                    model.Add(cov_p[(c + 1, t)] == 1).OnlyEnforceIf(
                        lit, m2[(t, c)].Not(), is_owner_p[(n, c + 1)])
                # crossing safety: no foreign stripe in either slot of an
                # end column covers the track -- an M1 segment shorts; a
                # poly jump or an M2 segment crosses in a different layer
                for other in nets + sorted(power_index):
                    if (other == n):
                        continue
                    for cSide in (c, c + 1):
                        if (t in nCover):
                            model.Add(lit + pj[(t, c)].Not()
                                      + m2[(t, c)].Not()
                                      + is_owner_n[(other, cSide)]
                                      + cov_n[(cSide, t)] <= 4)
                        if (t in pCover):
                            model.Add(lit + pj[(t, c)].Not()
                                      + m2[(t, c)].Not()
                                      + is_owner_p[(other, cSide)]
                                      + cov_p[(cSide, t)] <= 4)

    # --- poly jump legality (row tracks only, y-aware gate crossing) ---
    field = _field_map(netlist, placement, width_cols)
    trackY, _ = track_geometry(height_um, grid_um)
    from .gds import row_geometry, POLY_OVERHANG
    _, rowsGeom = row_geometry(height_um, grid_um)
    gateSpanY = {}
    for dev in netlist.devices:
        p = placement[dev]
        y0, y1 = rowsGeom[(dev.is_p, p.row)]
        for j in range(p.legs):
            c = p.start_col + j * p.leg_width_cols + p.leg_width_cols // 2
            key = (dev.gate, c)
            if (key in gateSpanY):
                o0, o1 = gateSpanY[key]
                gateSpanY[key] = (min(o0, y0), max(o1, y1))
            else:
                gateSpanY[key] = (y0, y1)
    for t in range(N_TRACKS):
        for c in range(width_cols - 1):
            if (t not in ROW_TRACKS):
                # poly between rows would land on the diffusion edge
                model.Add(pj[(t, c)] == 0)
                continue
            # poly over active at either end column is a transistor; the
            # only exception is the row's own gate at the *crossed* (left)
            # column, handled by the gate-merge rules below
            if (c + 1 not in field[t]):
                model.Add(pj[(t, c)] == 0)
            if (c not in field[t] and c not in gateNetsAt):
                model.Add(pj[(t, c)] == 0)
            # every gate stripe the jump geometrically crosses (the stripe
            # spans trackY[t]) must belong to the segment's net
            for gn in sorted(gateNetsAt.get(c, ())):
                gy0, gy1 = gateSpanY[(gn, c)]
                gy0 -= POLY_OVERHANG
                gy1 += POLY_OVERHANG
                if (not (gy0 <= trackY[t] <= gy1)):
                    continue
                if (gn in net_index):
                    model.Add(hseg[(t, c)] == net_index[gn]) \
                        .OnlyEnforceIf(pj[(t, c)])
                else:
                    model.Add(pj[(t, c)] == 0)
            # a poly jump is a segment: it cannot be "on poly" and empty
            model.Add(h_active[(t, c)] >= pj[(t, c)])

    # --- layer rules at adjacent segments (E5), three layers ---
    # same net: poly state must match (a poly<->metal switch has no
    # contact and breaks the wire); an M1<->M2 switch is legal only
    # through a via (forced below).  different nets: NOT the same layer
    # (touching M1, touching poly or touching M2 all short).
    for t in range(N_TRACKS):
        for c in range(1, width_cols - 1):
            for n in nets:
                model.Add(pj[(t, c - 1)] == pj[(t, c)]).OnlyEnforceIf(
                    h_lit[(n, t, c - 1)], h_lit[(n, t, c)])
            for n1 in nets:
                for n2 in nets:
                    if (n1 == n2):
                        continue
                    a1, a2 = h_lit[(n1, t, c - 1)], h_lit[(n2, t, c)]
                    # both M1 / both poly / both M2: a short
                    model.Add(a1 + a2
                              + pj[(t, c - 1)].Not() + pj[(t, c)].Not()
                              + m2[(t, c - 1)].Not() + m2[(t, c)].Not()
                              <= 5)
                    model.Add(a1 + a2
                              + pj[(t, c - 1)] + pj[(t, c)] <= 3)
                    model.Add(a1 + a2
                              + m2[(t, c - 1)] + m2[(t, c)] <= 3)

    # --- vias: a vertical M1<->M2 connection between two adjacent
    # same-net segments on a track.  A via exists iff exactly one of the
    # two segments is M2 (both M1 merge directly, both M2 merge
    # directly, and poly never meets a via). ---
    for t in range(N_TRACKS):
        for c in range(1, width_cols - 1):
            v = via_l[(t, c)]
            model.Add(v <= h_active[(t, c - 1)])
            model.Add(v <= h_active[(t, c)])
            model.Add(hseg[(t, c - 1)] == hseg[(t, c)]).OnlyEnforceIf(v)
            model.Add(v <= m2[(t, c - 1)] + m2[(t, c)])
            model.Add(v + m2[(t, c - 1)] + m2[(t, c)] <= 2)
            model.Add(v <= pj[(t, c - 1)].Not())
            model.Add(v <= pj[(t, c)].Not())
            # a same-net M1|M2 junction REQUIRES the via
            for n in nets:
                a = h_lit[(n, t, c - 1)]
                b = h_lit[(n, t, c)]
                model.Add(v == 1).OnlyEnforceIf(
                    a, b, pj[(t, c - 1)].Not(), pj[(t, c)].Not(),
                    m2[(t, c - 1)], m2[(t, c)].Not())
                model.Add(v == 1).OnlyEnforceIf(
                    a, b, pj[(t, c - 1)].Not(), pj[(t, c)].Not(),
                    m2[(t, c - 1)].Not(), m2[(t, c)])
    # an M2 segment never touches a bar or a gate -- its only junctions
    # are vias to adjacent M1 segments.  So every maximal M2 run must end
    # in a via on BOTH sides; without this the sweep counts dead M2 metal
    # as connected presence (bars only join M1 ends).  Edge columns can
    # never host a via on one side, so no M2 there.
    if (width_cols >= 2):
        for t in range(N_TRACKS):
            model.Add(m2[(t, 0)] == 0)
            model.Add(m2[(t, width_cols - 2)] == 0)
            for c in range(1, width_cols - 2):
                model.Add(via_l[(t, c)] >= m2[(t, c)] - m2[(t, c - 1)])
                model.Add(via_l[(t, c + 1)] >= m2[(t, c)] - m2[(t, c + 1)])

    # --- poly jump anchoring (E4): every maximal poly run of a net must
    # cross a same-net gate.  CP-SAT automaton per (net, row track): the
    # letter at column c is 0 (no poly segment of n), 1 (poly, no gate at
    # c) or 2 (poly, same-net gate at c); a run that ends without ever
    # seeing a 2 is rejected. ---
    if (poly_jumps):
        for n in nets:
            for t in ROW_TRACKS:
                seq = []
                for c in range(width_cols - 1):
                    v = model.NewIntVar(0, 2, "pjrun_%s_%d_%d" % (n, t, c))
                    hasGate = (c in gateNetsAt and n in gateNetsAt[c]
                               and t in gate_tracks.get((n, c), ()))
                    model.Add(v == 0).OnlyEnforceIf(h_lit[(n, t, c)].Not())
                    model.Add(v == 0).OnlyEnforceIf(pj[(t, c)].Not())
                    if (hasGate):
                        model.Add(v == 2).OnlyEnforceIf(
                            h_lit[(n, t, c)], pj[(t, c)])
                    else:
                        model.Add(v == 1).OnlyEnforceIf(
                            h_lit[(n, t, c)], pj[(t, c)])
                    seq.append(v)
                if (not seq):
                    continue            # width-1 window: no poly runs
                model.AddAutomaton(
                    seq, 0, [0, 2],
                    [(0, 0, 0), (0, 1, 1), (0, 2, 2),
                     (1, 1, 1), (1, 2, 2),
                     (2, 0, 0), (2, 1, 2), (2, 2, 2)])

    # --- gate access points: a horizontal segment crosses the column on
    # a track the stripe spans ---
    # The gate stripe sits at the column CENTRE, so only a segment at
    # (t, c) -- spanning [c*g, (c+1)*g] -- actually crosses it.  The
    # stripe covers only the rows of its devices, so the track must lie
    # inside the stripe's y-range (gate_tracks).  M1 contacts the gate, a
    # poly jump merges with it; M2 floats above it and does NOT count.
    for net, cols in gate.items():
        if (net not in net_index):
            continue
        for c in cols:
            lits = []
            for t in gate_tracks.get((net, c), ()):
                if (c <= width_cols - 2):
                    lits.append(_gm_lit(model, h_lit, m2, net, t, c,
                                        gm_memo))
            if (lits):
                model.Add(sum(lits) >= 1)
            else:
                # no candidate crossing track (the column is past the
                # last segment column, or the stripe is too shallow to
                # carry a contact): the gate can never be contacted, so
                # the model must REFUSE -- an empty clause is always
                # false.  Silently skipping here produced a "solved"
                # route the verify then rejected (mixed-width INV).
                model.AddBoolOr([])

    # --- connectivity: track-aware sweep + transitions at joins ---
    # A net's wire is a chain of segments; adjacent segments on the SAME
    # track merge, and a track change (segment ending at column c on
    # track t1 followed by one starting at column c on track t2 != t1)
    # must happen at a join: a same-net bar at c covering both tracks
    # (for an N<->P change, the two bars merged at T3) or a gate of the
    # net at c whose stripe spans both tracks (with an M1 relay).
    for n in nets:
        nPts = set(diffusion.get(n, set()))
        cols = set(c for c, r in nPts)
        cols |= set(gate.get(n, set()))
        if (not cols):
            continue
        cmin, cmax = min(cols), max(cols)
        covN = {}
        covP = {}
        for c in range(cmin, cmax + 1):
            bn = model.NewBoolVar("covN_%s_%d" % (n, c))
            lits = [is_owner_n[(n, c)]]
            for t in N_TRACKS_SET:
                if (c - 1 >= 0):
                    lits.append(h_lit[(n, t, c - 1)])
                if (c <= width_cols - 2):
                    lits.append(h_lit[(n, t, c)])
            for lit in lits:
                model.Add(bn >= lit)
            model.Add(bn <= sum(lits))
            covN[c] = bn
            bp = model.NewBoolVar("covP_%s_%d" % (n, c))
            lits = [is_owner_p[(n, c)]]
            for t in P_TRACKS_SET:
                if (c - 1 >= 0):
                    lits.append(h_lit[(n, t, c - 1)])
                if (c <= width_cols - 2):
                    lits.append(h_lit[(n, t, c)])
            for lit in lits:
                model.Add(bp >= lit)
            model.Add(bp <= sum(lits))
            covP[c] = bp
        for c in range(cmin, cmax + 1):
            model.Add(covN[c] + covP[c] >= 1)
        for c in range(cmin, cmax):
            lits = [h_lit[(n, t, c)] for t in range(N_TRACKS)]
            model.Add(sum(lits) >= 1)
        # track transitions at column c: a segment ending on track t1
        # (from c-1) and a segment starting on track t2 (to c+1)
        pairs = [(t1, t2) for t1 in range(N_TRACKS)
                 for t2 in range(N_TRACKS) if (t1 != t2)]
        for c in range(cmin + 1, cmax + 1):
            if (c > width_cols - 2):
                continue            # no segment can start at column c
            gateJoin = c in gate.get(n, ())
            allowed = gate_tracks.get((n, c), ()) if gateJoin else ()
            for t1, t2 in pairs:
                if (gateJoin and t1 in allowed and t2 in allowed):
                    # a gate stripe joins only the segments that CROSS it
                    # (spanning [c*g, (c+1)*g]); a segment ending at c
                    # stops short of the stripe.  A track change t1->t2 at
                    # the gate is therefore physical only when the left
                    # track ALSO carries an M1 crossing at c (relaying the
                    # left bridge's end node to the gate stripe) and the
                    # right bridge touches the gate (M1 or poly; M2 floats
                    # above and cannot).
                    m1a = _m1_lit(model, h_lit, pj, m2, n, t1, c - 1,
                                  m1_memo)
                    m1x = _m1_lit(model, h_lit, pj, m2, n, t1, c, m1_memo)
                    gmb = _gm_lit(model, h_lit, m2, n, t2, c, gm_memo)
                    both = model.NewBoolVar(
                        "gj_%s_%d_%d_%d" % (n, c, t1, t2))
                    model.Add(both <= m1a)
                    model.Add(both <= m1x)
                    model.Add(both <= gmb)
                    model.Add(both >= m1a + m1x + gmb - 2)
                    model.Add(h_lit[(n, t1, c - 1)] + h_lit[(n, t2, c)]
                              <= 1 + both)
                    continue
                # NOT a (fully gate-spanned) gate join: the change must
                # happen through a same-net BAR at c -- which the exact
                # BFS accepts at gate columns too.  (The old code skipped
                # gate columns whose stripe misses one of the tracks,
                # leaving the track change unconstrained and unphysical;
                # the mixed-width INV unravelled exactly that.)
                join = model.NewBoolVar("join_%s_%d_%d_%d" % (n, c, t1, t2))
                # the joining bar pair only touches M1 ends (a poly or M2
                # end is a different layer), so both bridges must be M1
                m1a = _m1_lit(model, h_lit, pj, m2, n, t1, c - 1, m1_memo)
                m1b = _m1_lit(model, h_lit, pj, m2, n, t2, c, m1_memo)
                if (t1 <= BOUNDARY_T and t2 <= BOUNDARY_T):
                    lits = [is_owner_n[(n, c)], cov_n[(c, t1)],
                            cov_n[(c, t2)], m1a, m1b]
                elif (t1 >= BOUNDARY_T and t2 >= BOUNDARY_T):
                    lits = [is_owner_p[(n, c)], cov_p[(c, t1)],
                            cov_p[(c, t2)], m1a, m1b]
                elif (t1 < BOUNDARY_T):
                    # N side ends, P side starts: the merged T3 bars
                    lits = [is_owner_n[(n, c)], is_owner_p[(n, c)],
                            reachT3_n[c], reachT3_p[c],
                            cov_n[(c, t1)], cov_p[(c, t2)], m1a, m1b]
                else:
                    # P side ends, N side starts: the merged T3 bars
                    lits = [is_owner_n[(n, c)], is_owner_p[(n, c)],
                            reachT3_n[c], reachT3_p[c],
                            cov_p[(c, t1)], cov_n[(c, t2)], m1a, m1b]
                model.Add(join >= sum(lits) - (len(lits) - 1))
                for lit in lits:
                    model.Add(join <= lit)
                model.Add(h_lit[(n, t1, c - 1)] + h_lit[(n, t2, c)]
                          <= 1 + join)
        # every diffusion access bar must connect: a same-track M1
        # segment touching it, a T3 segment touching a bar that reaches
        # the boundary, or a merged T3 pair
        for c, r in sorted(nPts):
            t = ROW_TRACK[r]
            lits = []
            if (c - 1 >= 0):
                lits.append(_m1_lit(model, h_lit, pj, m2, n, t, c - 1,
                                    m1_memo))
            if (c <= width_cols - 2):
                lits.append(_m1_lit(model, h_lit, pj, m2, n, t, c,
                                    m1_memo))
            reach = reachT3_n[c] if r <= 1 else reachT3_p[c]
            for t3c in (c - 1, c):
                if (0 <= t3c <= width_cols - 2):
                    both = model.NewBoolVar(
                        "aT3_%s_%d_%d" % (n, c, t3c))
                    model.Add(both <= reach)
                    model.Add(both <= _m1_lit(model, h_lit, pj, m2, n,
                                              BOUNDARY_T, t3c, m1_memo))
                    model.Add(both >= reach
                              + _m1_lit(model, h_lit, pj, m2, n,
                                        BOUNDARY_T, t3c, m1_memo) - 1)
                    lits.append(both)
            model.Add(dual[(n, c)] + sum(lits) >= 1)

    # --- objective: active horizontal segments / vertical stripes ---
    h_count = model.NewIntVar(
        0, N_TRACKS * (width_cols - 1) * max(1, len(nets)), "h_count")
    if (len(nets)):
        model.Add(h_count == sum(h_active.values()))
    v_count = model.NewIntVar(0, 2 * width_cols, "v_count")
    model.Add(v_count == sum(v_active_n[c] for c in range(width_cols))
              + sum(v_active_p[c] for c in range(width_cols)))
    pj_count = model.NewIntVar(0, N_TRACKS * (width_cols - 1), "pj_count")
    model.Add(pj_count == sum(pj.values()))
    m2_count = model.NewIntVar(0, N_TRACKS * (width_cols - 1), "m2_count")
    model.Add(m2_count == sum(m2.values()))
    via_count = model.NewIntVar(0, N_TRACKS * (width_cols - 1),
                                "via_count")
    model.Add(via_count == sum(via_l.values()))
    model.Minimize(h_count * HSEG_WEIGHT + v_count * VSEG_WEIGHT
                   + pj_count * PJUMP_WEIGHT + m2_count * M2_WEIGHT
                   + via_count * VIA_WEIGHT)

    return RoutingModel(model, owner_n, owner_p, lo_n, hi_n, lo_p, hi_p,
                        hseg, pj, m2, via_l, reachT3_n, reachT3_p,
                        (diffusion, gate, power), width_cols, nets,
                        gate_tracks)


def solve_routing(netlist, placement, width_cols=None, poly_jumps=True,
                  metal2=True, time_limit_s=SOLVE_TIME_LIMIT_S):
    """Stage-2 solve; returns RouteResult (UNKNOWN on failure)."""
    rm = build_routing_model(netlist, placement, width_cols=width_cols,
                             poly_jumps=poly_jumps, metal2=metal2)
    solver = cp_model.CpSolver()
    # single worker: parallel search picks different equal-cost optima
    # across runs (AGENTS.md invariant 9 -- the engine must be
    # deterministic)
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = time_limit_s
    status = solver.Solve(rm.model)
    if (status not in (cp_model.OPTIMAL, cp_model.FEASIBLE)):
        return RouteResult(_status_name(status), [], [], [], [], [], [],
                           {}, {}, {}, {}, [], [], 0, 0, 0, 0, 0, 0)
    names = rm.nets + sorted(rm.access[2])

    def decode(v):
        return names[v] if 0 <= v < len(names) else None

    owner_n = [decode(solver.Value(v)) for v in rm.owner_n]
    owner_p = [decode(solver.Value(v)) for v in rm.owner_p]
    lo_n = [solver.Value(v) for v in rm.lo_n]
    hi_n = [solver.Value(v) for v in rm.hi_n]
    lo_p = [solver.Value(v) for v in rm.lo_p]
    hi_p = [solver.Value(v) for v in rm.hi_p]
    hseg = {}
    for (t, c), var in rm.hseg.items():
        val = solver.Value(var)
        if (0 <= val < len(rm.nets)):
            hseg[(t, c)] = rm.nets[val]
    pj = {}
    for (t, c), var in rm.pj.items():
        pj[(t, c)] = solver.Value(var) == 1
    m2 = {}
    for (t, c), var in rm.m2.items():
        m2[(t, c)] = solver.Value(var) == 1
    via = {}
    for (t, c), var in rm.via.items():
        via[(t, c)] = solver.Value(var) == 1
    reachB_n = [solver.Value(rm.reachT3_n[c]) == 1
                for c in range(rm.width_cols)]
    reachB_p = [solver.Value(rm.reachT3_p[c]) == 1
                for c in range(rm.width_cols)]
    vseg = sum(1 for o in owner_n if o is not None) \
        + sum(1 for o in owner_p if o is not None)
    return RouteResult(
        _status_name(status), owner_n, owner_p, lo_n, hi_n, lo_p, hi_p,
        hseg, pj, m2, via, reachB_n, reachB_p, rm.width_cols, len(hseg),
        vseg, sum(pj.values()), sum(m2.values()), sum(via.values()))


# ---------------------------------------------------------------------------
# Window-fixing mode (doc/STAGE3_BIGCELL_ENGINE.md section 2.4, rung 1's
# narrowed role): after the negotiated-congestion router leaves a LOCAL
# region conflicted, re-run the exact model on a <=12-column sub-window
# with everything outside the window fixed as blockages.
#
# The window model is the exact engine's own encoding
# (build_routing_model) over the window columns, in window coordinates,
# with three additive layers:
#
# - **blockages**: outside-window geometry is untouchable.  Stripes of
#   nets without window accesses are kept (their slots are banned for
#   window nets, their covered tracks price the adjacent M1 segments,
#   and a boundary-reaching kept stripe silences the opposite slot's T3
#   reach); segments of pre-routed nets crossing the window reserve
#   their hseg slots (forced empty for the window solve, restored on
#   merge) and block the endpoint points; the two boundary segments
#   (t, w0-1) / (t, w1-1) constrain the edge columns' stripes (no
#   foreign coverage of their tracks), the adjacent window segments
#   (no same-layer touch, same-net layer continuity / derived via), and
#   supply the connectivity channels;
# - **ties**: a window net that also has accesses outside the window
#   must link its window part to the kept outside part through at least
#   one boundary junction the verify BFS actually joins (a same-net
#   stripe covering the boundary track, a same-net M1 segment, a poly
#   pair, or an M1|M2 pair whose via is derived at merge time);
# - **merge**: the window solution replaces exactly the window columns
#   (stripes) and window segment slots; kept geometry is restored, and
#   the two boundary vias are re-derived from the merged layers.
#
# Access requirements are derived the way smt_engine.verify derives
# them (die view for slot-model placements, the orientation-aware walk
# when a block view is supplied), so what the model satisfies is what
# verify_cell will check.  Determinism: sorted iteration throughout,
# single-worker CP-SAT, fixed budget as the documented safety net.
# ---------------------------------------------------------------------------

WINDOW_MAX_COLS = 12            # doc section 2.4: "<=12-column sub-window"
WINDOW_SOLVE_TIME_LIMIT_S = 60.0

_POWER_NAMES = ("VCC", "GND", "VDD", "VSS")


class WindowFixResult(object):
    """Outcome of one window-fix attempt.

    ``route`` is the merged RouteResult (window solution + untouched
    outside region) when the window solve found a route, else None --
    INFEASIBLE (the window is exactly-unroutable: decisive evidence the
    blocker is the placement/vocabulary, not the router's heuristic) and
    UNKNOWN (budget exhausted; a time-limited incumbent is not
    reproducible and is never shipped) both report honestly without a
    route.  ``status_name`` is the window solve's own verdict.
    """

    def __init__(self, status_name, route=None, window=None, seconds=0.0,
                 note=None, window_nets=0):
        self.status_name = status_name
        self.route = route
        self.window = window
        self.seconds = seconds
        self.note = note
        self.window_nets = window_nets


class _ShiftedPlacement(object):
    """A placed device viewed in window coordinates (x shifted by -w0).

    Only the geometry the routing model reads is exposed (row, legs,
    leg_width_cols, start_col, end_col); y geometry is shift-invariant.
    """

    __slots__ = ("_p", "_w0")

    def __init__(self, p, w0):
        self._p = p
        self._w0 = w0

    @property
    def row(self):
        return self._p.row

    @property
    def legs(self):
        return self._p.legs

    @property
    def leg_width_cols(self):
        return self._p.leg_width_cols

    @property
    def start_col(self):
        return self._p.start_col - self._w0

    @property
    def end_col(self):
        return self._p.end_col - self._w0


def verify_style_access_points(netlist, placement, blocks=None):
    """(diffusion, gate, power) in the exact model's rail form, derived
    the way smt_engine.verify derives its access requirements.

    Slot-model placements use the shared die view
    (die_view.die_slot_access_points -- true edge columns, multi-region
    nets exposed); a supplied orientation-aware block view re-orients
    the historical walk; otherwise the base walk.  The window fixer's
    merged result is gated by verify_cell, so the model must encode
    verify's requirement set, not _access_points' base walk.
    """
    from . import die_view
    if (die_view.is_slot_placement(placement)):
        sig_diff, power_diff = die_view.die_slot_access_points(
            netlist, placement)
    elif (blocks is not None):
        sig_diff, power_diff = diffusion_access_points(
            netlist, placement, blocks)
    else:
        sig_diff, power_diff = diffusion_access_points(netlist, placement)
    gate = gate_access_points(netlist, placement)
    diffusion = {}
    for net, pts in sig_diff.items():
        for c, dev in pts:
            diffusion.setdefault(net, set()).add(
                (c, device_rail(dev, placement[dev].row)))
    power = {}
    for net, pts in power_diff.items():
        pRail = VCC_RAIL if net in ("VCC", "VDD") else GND_RAIL
        for c, dev in pts:
            power.setdefault(net, set()).add(
                (c, device_rail(dev, placement[dev].row), pRail))
    return diffusion, gate, power


def _win_index(rm, name):
    """Owner-domain index of a net (signal or power) in the window model."""
    if (name in rm.nets):
        return rm.nets.index(name)
    power_names = sorted(rm.access[2])
    return len(rm.nets) + power_names.index(name)


class _WindowChanneling(object):
    """Reified literals over the window model's integer variables.

    build_routing_model keeps its per-net booleans private; the blockage
    and tie layers re-channel the few they need (owner==net, segment
    layer, bar coverage) with the same OnlyEnforceIf pattern the model
    itself uses.
    """

    def __init__(self, model, rm):
        self.model = model
        self.rm = rm
        self._memo = {}

    def owner_lit(self, c, name, slot):
        """Bool: the slot's stripe at column c is owned by ``name``."""
        key = ("own", c, name, slot)
        if (key in self._memo):
            return self._memo[key]
        var = self.rm.owner_n[c] if slot == "N" else self.rm.owner_p[c]
        idx = _win_index(self.rm, name)
        b = self.model.NewBoolVar("wown_%s_%d_%s" % (name, c, slot))
        self.model.Add(var == idx).OnlyEnforceIf(b)
        self.model.Add(var != idx).OnlyEnforceIf(b.Not())
        self._memo[key] = b
        return b

    def active_lit(self, c, slot):
        """Bool: the slot's stripe at column c exists."""
        key = ("act", c, slot)
        if (key in self._memo):
            return self._memo[key]
        var = self.rm.owner_n[c] if slot == "N" else self.rm.owner_p[c]
        b = self.model.NewBoolVar("wact_%d_%s" % (c, slot))
        self.model.Add(var != -1).OnlyEnforceIf(b)
        self.model.Add(var == -1).OnlyEnforceIf(b.Not())
        self._memo[key] = b
        return b

    def hseg_lit(self, name, t, c):
        """Bool: segment (t, c) belongs to ``name`` (any layer)."""
        key = ("h", name, t, c)
        if (key in self._memo):
            return self._memo[key]
        var = self.rm.hseg[(t, c)]
        idx = _win_index(self.rm, name)
        b = self.model.NewBoolVar("wh_%s_%d_%d" % (name, t, c))
        self.model.Add(var == idx).OnlyEnforceIf(b)
        self.model.Add(var != idx).OnlyEnforceIf(b.Not())
        self._memo[key] = b
        return b

    def _layer_lit(self, key, name, t, c, want):
        """Bool: segment (t, c) is ``name``'s on layer ``want``."""
        if (key in self._memo):
            return self._memo[key]
        lit = self.hseg_lit(name, t, c)
        pj = self.rm.pj[(t, c)]
        m2 = self.rm.m2[(t, c)]
        b = self.model.NewBoolVar("wlay_%s_%s_%d_%d" % (want, name, t, c))
        if (want == "M1"):
            self.model.Add(b == 1).OnlyEnforceIf(
                lit, pj.Not(), m2.Not())
        elif (want == "M2"):
            self.model.Add(b == 1).OnlyEnforceIf(lit, m2)
        else:                                   # poly jump
            self.model.Add(b == 1).OnlyEnforceIf(lit, pj)
        self.model.Add(b == 0).OnlyEnforceIf(lit.Not())
        if (want == "M1"):
            self.model.Add(b == 0).OnlyEnforceIf(pj)
            self.model.Add(b == 0).OnlyEnforceIf(m2)
        elif (want == "M2"):
            self.model.Add(b == 0).OnlyEnforceIf(m2.Not())
        else:
            self.model.Add(b == 0).OnlyEnforceIf(pj.Not())
        self._memo[key] = b
        return b

    def m1_lit(self, name, t, c):
        return self._layer_lit(("m1", name, t, c), name, t, c, "M1")

    def m2_lit(self, name, t, c):
        return self._layer_lit(("m2", name, t, c), name, t, c, "M2")

    def pj_lit(self, name, t, c):
        return self._layer_lit(("pj", name, t, c), name, t, c, "PJ")

    def covers_lit(self, c, t, slot):
        """Bool: the slot's bar interval at column c covers track t.

        Mirrors build_routing_model's index-coverage channeling: the bar
        covers t iff lo <= t+1 <= hi in the slot's endpoint domain.
        """
        key = ("cov", c, t, slot)
        if (key in self._memo):
            return self._memo[key]
        if (slot == "N"):
            lo_d, hi_d = 0, BOUNDARY_T + 1
        else:
            lo_d, hi_d = BOUNDARY_T + 1, BAR_LEVELS - 1
        cover = [(l, h) for l in range(lo_d, hi_d + 1)
                 for h in range(l, hi_d + 1) if (l <= t + 1 <= h)]
        if (not cover):
            self._memo[key] = None
            return None
        lo_v = self.rm.lo_n[c] if slot == "N" else self.rm.lo_p[c]
        hi_v = self.rm.hi_n[c] if slot == "N" else self.rm.hi_p[c]
        b = self.model.NewBoolVar("wcov_%d_%d_%s" % (c, t, slot))
        self.model.AddAllowedAssignments([lo_v, hi_v], cover).OnlyEnforceIf(b)
        self.model.AddForbiddenAssignments(
            [lo_v, hi_v], cover).OnlyEnforceIf(b.Not())
        self._memo[key] = b
        return b

    def and_lit(self, a, b):
        """Bool: a AND b (fresh variable, standard channeling)."""
        key = ("and", a.Index(), b.Index())
        if (key in self._memo):
            return self._memo[key]
        v = self.model.NewBoolVar("wand_%d" % len(self._memo))
        self.model.Add(v <= a)
        self.model.Add(v <= b)
        self.model.Add(v >= a + b - 1)
        self._memo[key] = v
        return v


def _win_segment_layer(partial, t, c):
    """(net, layer) of the partial's fixed segment (t, c), or None."""
    name = partial.hseg.get((t, c))
    if (name is None):
        return None
    if (partial.pj.get((t, c))):
        return (name, "PJ")
    if (partial.m2.get((t, c))):
        return (name, "M2")
    return (name, "M1")


def _win_forbid_segment_layer(ch, name, t, c, layer):
    """Forbid ``name``'s segment (t, c) on ``layer`` (blockage form)."""
    model, rm = ch.model, ch.rm
    lit = ch.hseg_lit(name, t, c)
    pj = rm.pj[(t, c)]
    m2 = rm.m2[(t, c)]
    if (layer == "M1"):
        # no M1 segment: any segment of name here must be poly or M2
        model.Add(lit <= pj + m2)
    elif (layer == "PJ"):
        model.Add(lit + pj <= 1)
    else:
        model.Add(lit + m2 <= 1)


def _win_boundary_facts(partial, w0, w1, width):
    """[(fact, col, gap)] for the fixed L/R boundary segments, in window
    coordinates: fact = (t, net, layer) of the outside segment whose
    endpoint touches window column ``col``; ``gap`` is the adjacent
    window segment slot (-1 when a one-column window hosts no segment).
    A fixed segment interacts with the window only on its OWN track
    (its endpoint point and same-track adjacency).
    """
    facts = []
    if (w0 > 0):
        gap = 0 if width >= 2 else -1
        for t in range(N_TRACKS):
            seg = _win_segment_layer(partial, t, w0 - 1)
            if (seg is not None):
                facts.append(((t,) + seg, 0, gap))
    if (w1 - 1 <= partial.width_cols - 2):
        gap = width - 2 if width >= 2 else -1
        for t in range(N_TRACKS):
            seg = _win_segment_layer(partial, t, w1 - 1)
            if (seg is not None):
                facts.append(((t,) + seg, width - 1, gap))
    return facts


def _win_boundary_constraints(ch, fact, col, gap, width):
    """C1/C2/C3 for one fixed boundary segment (window coordinates).

    ``fact`` is (t, net, layer) of the outside segment touching window
    column ``col``; ``gap`` is the adjacent window segment slot (-1 when
    the window is one column wide and hosts no segment).  All three
    rules act on the segment's own track only: the endpoint point
    (t, col) is what window stripes could short, and only the same-track
    window segment (t, gap) is adjacent to it.
    """
    model, rm = ch.model, ch.rm
    t, net, layer = fact
    # C1: no window stripe of a foreign net covers the boundary track
    for slot in ("N", "P"):
        cov = ch.covers_lit(col, t, slot)
        if (cov is None):
            continue
        for name in rm.nets + sorted(rm.access[2]):
            if (name == net):
                continue
            own = ch.owner_lit(col, name, slot)
            ch.model.Add(own + cov <= 1)
    if (gap < 0 or gap >= width - 1):
        return
    # C2: a foreign window segment must not touch the fixed segment in
    # the same layer; C3: a same-net window segment must keep its layer
    # (matching, or the M1|M2 pair whose via is derived at merge time)
    if (net in rm.nets):
        # same-net channel: layer continuity with the fixed segment
        if (layer == "PJ"):
            model.Add(ch.hseg_lit(net, t, gap) <= rm.pj[(t, gap)])
        else:                       # M1 or M2: poly is never legal
            model.Add(ch.hseg_lit(net, t, gap) + rm.pj[(t, gap)] <= 1)
    for name in rm.nets:
        if (name == net):
            continue
        _win_forbid_segment_layer(ch, name, t, gap, layer)


def _win_blockage_layer(model, rm, ch, partial, w0, w1, kept_stripes,
                        kept_segments):
    """Add the kept-geometry blockage constraints to the window model.

    Kept stripes at window columns (owners without window accesses,
    precomputed by _win_kept_geometry) ban window ownership of their
    slot, price the adjacent M1 segments over their covered tracks, and
    silence the opposite slot's T3 reach when they touch the boundary.
    Reserved segment slots (pre-routed nets crossing the window) are
    forced empty for the window solve and block their endpoint points
    and the adjacent same-layer segments.  The two fixed boundary
    segments are handled by _win_boundary_constraints.
    """
    width = w1 - w0
    # ---- kept stripes at window columns (pre-routed owners) ----
    for (c, slot), (net, lo, hi) in sorted(kept_stripes.items()):
        cw = c - w0
        # the slot is the kept stripe's: no window net may claim it
        for name in window_owners:
            own = ch.owner_lit(cw, name, slot)
            model.Add(own == 0)
        # M1 segments over the kept stripe's covered tracks are shorts
        for t in range(max(0, lo - 1), min(N_TRACKS - 1, hi - 1) + 1):
            for g in (cw - 1, cw):
                if (0 <= g < width - 1):
                    for name in rm.nets:
                        _win_forbid_segment_layer(ch, name, t, g, "M1")
        # a kept stripe reaching the boundary silences the opposite
        # slot's T3 reach (the dual-column rule, verify-side)
        if (slot == "N" and hi == BOUNDARY_T + 1):
            model.Add(rm.reachT3_p[cw] == 0)
        if (slot == "P" and lo == BOUNDARY_T + 1):
            model.Add(rm.reachT3_n[cw] == 0)
    # ---- reserved segment slots (pre-routed nets crossing the window) ----
    for (t, c) in sorted(kept_segments):
        cw = c - w0
        model.Add(rm.hseg[(t, cw)] == -1)
        model.Add(rm.pj[(t, cw)] == 0)
        model.Add(rm.m2[(t, cw)] == 0)
        seg = _win_segment_layer(partial, t, c)
        _net, layer = seg
        if (layer == "M1"):
            # the fixed segment's endpoint points are M1: no window
            # stripe may cover the track at either end column
            for colw in (cw, cw + 1):
                if (not (0 <= colw < width)):
                    continue
                for slot in ("N", "P"):
                    cov = ch.covers_lit(colw, t, slot)
                    if (cov is None):
                        continue
                    act = ch.active_lit(colw, slot)
                    model.Add(act + cov <= 1)
        for g in (cw - 1, cw + 1):
            if (not (0 <= g < width - 1)):
                continue
            for name in rm.nets:
                _win_forbid_segment_layer(ch, name, t, g, layer)


def _win_kept_geometry(partial, w0, w1, window_owners):
    """The partial geometry the merge must keep, from the plateaued
    router solution alone (no model needed): stripes at window columns
    whose owner has no window access, and segments of pre-routed nets
    crossing the window's segment range.  Keyed in ABSOLUTE columns.
    """
    kept_stripes = {}
    for c in range(w0, w1):
        for net, lo, hi, slot in partial.stripes(c):
            if (net in window_owners):
                continue            # a window net re-routes its own stripe
            kept_stripes[(c, slot)] = (net, lo, hi)
    kept_segments = set()
    for (t, c), net in partial.hseg.items():
        if (w0 <= c < w1 - 1 and net not in window_owners):
            kept_segments.add((t, c))
    return kept_stripes, kept_segments


def _win_pseudo_access(t):
    """(rail, slot, extension) expressing "bar covers track t" as a
    diffusion access on a row rail plus one interval constraint.

    A bar covering track t covers every row track the rail's interval
    spans; the extension forces the remaining index.  t=1 -> rail 0
    (covers T0; hi >= 2 adds T1), t=3 -> N rail 1 with hi == 4 or P
    rail 2 with lo == 4 (both cover T3), t=5 -> rail 3 (covers T6;
    lo <= 6 adds T5).
    """
    if (t == 0):
        return (0, "N", None)
    if (t == 1):
        return (0, "N", "hi_ge_2")
    if (t == 2):
        return (1, "N", None)
    if (t == 3):
        return (1, "N", "hi_eq_boundary")       # N reaching T3
    if (t == 4):
        return (2, "P", None)
    if (t == 5):
        return (3, "P", "lo_le_boundary_p1")
    return (3, "P", None)                       # t == 6


def _win_plan_ties(diffusion, gate, power, diffusion_full, gate_full,
                   partial, w0, w1, width, window_owners, kept_stripes,
                   kept_segments):
    """Give every window net with outside accesses a junction to them.

    The junction must be connected to the net's window component, so it
    is planned BEFORE the model build and expressed through the access
    maps the exact sweep consumes:

    - **bar junction**: a pseudo diffusion access at the boundary
      column, on the rail whose bar covers the kept boundary segment's
      track -- the model forces the bar (owner + coverage), includes
      the column in the connectivity sweep, and its access-connection
      rule anchors the bar inward; the bar joins the kept segment's
      endpoint node (the junction verify's BFS merges);
    - **segment junction**: the kept boundary segment's M1 track is
      claimed as a forced M1 window segment at the boundary gap, with
      the pseudo access one column inward anchoring the sweep -- the
      segment's outer endpoint node is the junction.

    Selection is deterministic (left side first, bar before segment,
    smallest track), each candidate only when its slot/slot-segment is
    not claimed by another net's forced access or kept geometry.  A
    tied net with no expressible junction yields an empty clause at
    apply time -- an honest infeasibility (documented conservatism:
    poly/M2-boundary junctions are not planned).
    """
    Lseg = {}
    Rseg = {}
    if (w0 > 0):
        for t in range(N_TRACKS):
            seg = _win_segment_layer(partial, t, w0 - 1)
            if (seg is not None):
                Lseg[t] = seg
    if (w1 - 1 <= partial.width_cols - 2):
        for t in range(N_TRACKS):
            seg = _win_segment_layer(partial, t, w1 - 1)
            if (seg is not None):
                Rseg[t] = seg
    slot_claims = {}                    # (abs col, slot) -> {nets}
    for net, pts in diffusion.items():
        for c, r in pts:
            slot_claims.setdefault((c + w0, "N" if r <= 1 else "P"),
                                   set()).add(net)
    for net, pts in power.items():
        for c, _r, pRail in pts:
            slot_claims.setdefault((c + w0, "N" if pRail == GND_RAIL
                                    else "P"), set()).add(net)
    kept_slots = {(c, slot) for (c, slot) in kept_stripes}
    directives = []                     # ("bar"/"seg", ...) post-build work
    refused = []
    for net in sorted(window_owners & (set(diffusion) | set(gate))):
        outside = [c for c, _r in sorted(diffusion_full.get(net, set()))
                   if (c < w0 or c >= w1)]
        outside += [c for c in sorted(gate_full.get(net, ()))
                    if (c < w0 or c >= w1)]
        if (not outside):
            continue
        candidates = []
        for side, segs, cB, gapB in (("L", Lseg, w0, w0),
                                     ("R", Rseg, w1 - 1, w1 - 2)):
            for t in sorted(segs):
                if (segs[t] != (net, "M1")):
                    continue            # M1 junctions only (conservative)
                if (not (0 <= cB - w0 < width)):
                    continue            # boundary column outside the window
                candidates.append((side == "R", 0, t, side, cB, gapB, "bar"))
                if (width >= 2 and 0 <= gapB - w0 < width - 1
                        and (t, gapB) not in kept_segments):
                    candidates.append((side == "R", 1, t, side, cB, gapB,
                                       "seg"))
        candidates.sort()
        chosen = None
        for _r, _k, t, side, cB, gapB, kind in candidates:
            if (kind == "bar"):
                rail, slot, _ext = _win_pseudo_access(t)
                col = cB if side == "L" else cB
                claims = slot_claims.get((col, slot), set())
                if (claims and claims != {net}):
                    continue            # the slot serves another net
                if ((col, slot) in kept_slots):
                    continue            # kept stripe owns the slot
                chosen = (kind, t, col, rail, slot, None)
            else:
                rail, slot, _ext = _win_pseudo_access(t)
                col = cB + 1 if side == "L" else cB - 1
                if (not (w0 <= col < w1)):
                    continue
                claims = slot_claims.get((col, slot), set())
                if (claims and claims != {net}):
                    continue
                if ((col, slot) in kept_slots):
                    continue
                chosen = (kind, t, col, rail, slot, gapB)
            if (chosen is not None):
                break
        if (chosen is None):
            refused.append(net)
            continue
        kind, t, col, rail, slot, gapB = chosen
        # claim the pseudo access (map is consumed by build_routing_model;
        # the sweep anchors the junction inward)
        diffusion.setdefault(net, set()).add((col - w0, rail))
        slot_claims.setdefault((col, slot), set()).add(net)
        if (kind == "seg"):
            directives.append(("seg", net, t, gapB))
        _rail2, _slot2, ext = _win_pseudo_access(t)
        if (ext is not None):
            # the anchor bar must also cover the junction track (T1/T3/T5)
            directives.append(("ext", net, col, ext))
    return directives, refused


def _win_apply_ties(model, rm, directives, refused, w0):
    """Post-build constraints of the planned junctions."""
    for net in refused:
        # no expressible junction: the kept outside part can never be
        # tied to the window solution
        model.AddBoolOr([])
    for item in directives:
        if (item[0] == "seg"):
            _tag, net, t, gapB = item
            idx = rm.nets.index(net)
            cw = gapB - w0
            model.Add(rm.hseg[(t, cw)] == idx)
            model.Add(rm.pj[(t, cw)] == 0)
            model.Add(rm.m2[(t, cw)] == 0)
            continue
        _tag, _net, col, ext = item
        cw = col - w0
        if (ext == "hi_ge_2"):
            model.Add(rm.hi_n[cw] >= 2)
        elif (ext == "hi_eq_boundary"):
            model.Add(rm.hi_n[cw] == BOUNDARY_T + 1)
        elif (ext == "lo_le_boundary_p1"):
            model.Add(rm.lo_p[cw] <= BOUNDARY_T + 2)


def _win_decode(rm, solver, status_name):
    """Decode the window solution (solve_routing's decode, window-wide)."""
    names = rm.nets + sorted(rm.access[2])

    def decode(v):
        return names[v] if 0 <= v < len(names) else None

    owner_n = [decode(solver.Value(v)) for v in rm.owner_n]
    owner_p = [decode(solver.Value(v)) for v in rm.owner_p]
    lo_n = [solver.Value(v) for v in rm.lo_n]
    hi_n = [solver.Value(v) for v in rm.hi_n]
    lo_p = [solver.Value(v) for v in rm.lo_p]
    hi_p = [solver.Value(v) for v in rm.hi_p]
    hseg = {}
    for (t, c), var in rm.hseg.items():
        val = solver.Value(var)
        if (0 <= val < len(rm.nets)):
            hseg[(t, c)] = rm.nets[val]
    pj = {}
    for (t, c), var in rm.pj.items():
        pj[(t, c)] = solver.Value(var) == 1
    m2 = {}
    for (t, c), var in rm.m2.items():
        m2[(t, c)] = solver.Value(var) == 1
    via = {}
    for (t, c), var in rm.via.items():
        via[(t, c)] = solver.Value(var) == 1
    reachB_n = [solver.Value(rm.reachT3_n[c]) == 1
                for c in range(rm.width_cols)]
    reachB_p = [solver.Value(rm.reachT3_p[c]) == 1
                for c in range(rm.width_cols)]
    vseg = sum(1 for o in owner_n if o is not None) \
        + sum(1 for o in owner_p if o is not None)
    return RouteResult(
        status_name, owner_n, owner_p, lo_n, hi_n, lo_p, hi_p,
        hseg, pj, m2, via, reachB_n, reachB_p, rm.width_cols, len(hseg),
        vseg, sum(pj.values()), sum(m2.values()), sum(via.values()))


def _merge_window_route(partial, window, win, kept_stripes, kept_segments):
    """Window solution + untouched outside region -> one RouteResult.

    The window replaces exactly the window columns' stripes and the
    window segment slots (hseg/pj/m2/via); kept pre-routed geometry is
    restored; the two boundary vias are re-derived from the merged
    layers (a via joins one net's M1 and M2 segments on both sides).
    """
    w0, w1 = window
    W = partial.width_cols
    owner_n = list(partial.col_owner_n)
    owner_p = list(partial.col_owner_p)
    lo_n = list(partial.lo_n)
    hi_n = list(partial.hi_n)
    lo_p = list(partial.lo_p)
    hi_p = list(partial.hi_p)
    reachB_n = list(partial.reachB_n)
    reachB_p = list(partial.reachB_p)
    for c in range(w0, w1):
        j = c - w0
        owner_n[c] = win.col_owner_n[j]
        lo_n[c] = win.lo_n[j]
        hi_n[c] = win.hi_n[j]
        owner_p[c] = win.col_owner_p[j]
        lo_p[c] = win.lo_p[j]
        hi_p[c] = win.hi_p[j]
        reachB_n[c] = win.reachB_n[j]
        reachB_p[c] = win.reachB_p[j]
    for (c, slot), (net, lo, hi) in sorted(kept_stripes.items()):
        if (slot == "N"):
            owner_n[c], lo_n[c], hi_n[c] = net, lo, hi
            reachB_n[c] = (hi == BOUNDARY_T + 1)
        else:
            owner_p[c], lo_p[c], hi_p[c] = net, lo, hi
            reachB_p[c] = (lo == BOUNDARY_T + 1)
    hseg = dict(partial.hseg)
    pj = dict(partial.pj)
    m2 = dict(partial.m2)
    via = dict(partial.via)
    for key in (hseg, pj, m2):
        for (t, c) in sorted(key):
            if (w0 <= c < w1 - 1 and (t, c) not in kept_segments):
                del key[(t, c)]
    for (t, c), net in sorted(win.hseg.items()):
        hseg[(t, c + w0)] = net
    for (t, c), on in sorted(win.pj.items()):
        if (on):
            pj[(t, c + w0)] = True
    for (t, c), on in sorted(win.m2.items()):
        if (on):
            m2[(t, c + w0)] = True
    for (t, c) in sorted(via):
        if (w0 <= c <= w1 - 1):
            del via[(t, c)]
    for (t, c), on in sorted(win.via.items()):
        if (on):
            via[(t, c + w0)] = True
    for cB in (w0, w1 - 1):
        if (not (1 <= cB <= W - 2)):
            continue
        for t in range(N_TRACKS):
            a = hseg.get((t, cB - 1))
            b = hseg.get((t, cB))
            if (a is None or b is None or a != b):
                continue
            lA = "PJ" if pj.get((t, cB - 1)) \
                else ("M2" if m2.get((t, cB - 1)) else "M1")
            lB = "PJ" if pj.get((t, cB)) \
                else ("M2" if m2.get((t, cB)) else "M1")
            if (set((lA, lB)) == set(("M1", "M2"))):
                via[(t, cB)] = True
    vseg = sum(1 for o in owner_n if o is not None) \
        + sum(1 for o in owner_p if o is not None)
    return RouteResult(
        "FEASIBLE", owner_n, owner_p, lo_n, hi_n, lo_p, hi_p,
        hseg, pj, m2, via, reachB_n, reachB_p, W, len(hseg),
        vseg, sum(pj.values()), sum(m2.values()), len(via))


def solve_window_routing(netlist, placement, width_cols, window,
                         partial=None, blocks=None, poly_jumps=True,
                         metal2=True,
                         time_limit_s=WINDOW_SOLVE_TIME_LIMIT_S):
    """The exact engine as a window fixer (doc section 2.4, rung 1's
    narrowed role).

    Rebuilds the exact routing model restricted to ``window`` =
    (w0, w1), columns of the router's route grid (``width_cols``
    columns), with everything outside fixed as blockages taken from
    ``partial`` -- the router's plateaued solution, a RouteResult in the
    same vocabulary; None when the window spans the whole cell and
    there is no outside region.  Nets with all accesses outside the
    window are pre-routed: their stripes are untouchable blockages and
    their segments crossing the window reserve their hseg slots.  Nets
    with accesses inside the window are re-routed by the exact model;
    one with accesses on both sides must tie the two parts through a
    boundary junction verify's BFS joins.

    Access requirements are derived the way smt_engine.verify derives
    them (``blocks`` is the orientation-aware block view for non-slot
    placements), so what the model satisfies is what verify_cell checks.

    Returns a WindowFixResult: ``route`` is the merged RouteResult (the
    same class solve_routing returns, so verify.py and the GDS emitters
    consume it unchanged) or None when the window solve was refused.
    The merged route is NOT verified here -- the ladder gates it with
    verify_cell like every other rung.

    Determinism: sorted iteration throughout, single-worker CP-SAT, the
    time limit only as the documented safety net (an UNKNOWN verdict is
    refused, never shipped).
    """
    t0 = time.time()
    w0, w1 = window
    width = w1 - w0
    if (w0 < 0 or w1 > width_cols or width <= 0
            or width > WINDOW_MAX_COLS):
        return WindowFixResult(
            "SKIPPED", window=(w0, w1),
            note="window [%d,%d) invalid for route width %d (max %d "
                 "columns)" % (w0, w1, width_cols, WINDOW_MAX_COLS))
    diffusion_full, gate_full, power_full = verify_style_access_points(
        netlist, placement, blocks)

    def _in(c):
        return w0 <= c < w1

    diffusion = {}
    for net, pts in diffusion_full.items():
        if (net in _POWER_NAMES):
            continue
        pts = set((c - w0, r) for c, r in pts if _in(c))
        if (pts):
            diffusion[net] = pts
    gate = {}
    for net, cols in gate_full.items():
        if (net in _POWER_NAMES):
            continue
        cols = sorted(c - w0 for c in cols if _in(c))
        if (cols):
            gate[net] = cols
    power = {}
    for net, pts in power_full.items():
        pts = set((c - w0, r, p) for c, r, p in pts if _in(c))
        if (pts):
            power[net] = pts
    window_nets = sorted(n for n in (set(diffusion) | set(gate))
                         if n not in _POWER_NAMES)

    # --- plan the boundary junctions BEFORE the model build: tied nets
    # express them through pseudo diffusion accesses, so the exact
    # engine's own sweep anchors the junction inward (soundness: the
    # junction must be connected to the net's window component)
    kept_stripes = {}
    kept_segments = set()
    directives = []
    refused = []
    if (partial is not None):
        window_owners = set(window_nets) | set(power)
        kept_stripes, kept_segments = _win_kept_geometry(
            partial, w0, w1, window_owners)
        directives, refused = _win_plan_ties(
            diffusion, gate, power, diffusion_full, gate_full, partial,
            w0, w1, width, window_owners, kept_stripes, kept_segments)

    shifted = {dev: _ShiftedPlacement(p, w0)
               for dev, p in placement.items()}
    rm = build_routing_model(netlist, shifted, width_cols=width,
                             accesses=(diffusion, gate, power),
                             poly_jumps=poly_jumps, metal2=metal2)
    if (partial is not None):
        model = rm.model
        ch = _WindowChanneling(model, rm)
        facts = _win_boundary_facts(partial, w0, w1, width)
        for seg, col, gap in facts:
            _win_boundary_constraints(ch, seg, col, gap, width)
        _win_apply_ties(model, rm, directives, refused, w0)
        _win_blockage_layer(model, rm, ch, partial, w0, w1, kept_stripes,
                            kept_segments)
    solver = cp_model.CpSolver()
    # single worker: parallel search picks different equal-cost optima
    # across runs (AGENTS.md invariant 9)
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = time_limit_s
    status = solver.Solve(rm.model)
    seconds = time.time() - t0
    status_name = _status_name(status)
    if (status not in (cp_model.OPTIMAL, cp_model.FEASIBLE)):
        if (status == cp_model.INFEASIBLE):
            note = ("window [%d,%d) of %d route columns is "
                    "exactly-unroutable in the %d-track vocabulary "
                    "(CP-SAT proof, %.1fs, %d window nets) -- the "
                    "blocker is the placement/vocabulary, not the "
                    "router's heuristic"
                    % (w0, w1, width_cols, N_TRACKS, seconds,
                       len(window_nets)))
        else:
            note = ("window [%d,%d) solve hit the %.0fs budget (%s): "
                    "a time-limited incumbent is not reproducible and "
                    "is never shipped" % (w0, w1, time_limit_s,
                                          status_name))
        return WindowFixResult(status_name, window=(w0, w1),
                               seconds=seconds, note=note,
                               window_nets=len(window_nets))
    win = _win_decode(rm, solver, status_name)
    if (partial is None):
        merged = win
    else:
        merged = _merge_window_route(partial, (w0, w1), win, kept_stripes,
                                     kept_segments)
        merged.status_name = status_name
    merged.window = (w0, w1)
    merged.window_status = status_name
    merged.window_seconds = seconds
    merged.window_nets = len(window_nets)
    return WindowFixResult(status_name, route=merged, window=(w0, w1),
                           seconds=seconds, window_nets=len(window_nets))
