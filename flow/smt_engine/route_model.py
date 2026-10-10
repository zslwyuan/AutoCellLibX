"""Stage 2 of the SMT engine: grid routing SAT encoding.

With the placement fixed (stage 1), every net's terminals are a set of
(column, rail) access points.  Routing is a grid model over the cell:

- every column carries up to **two** vertical M1 stripes -- one in the N
  half (rails 0..4, GND rail 4) and one in the P half (rails 2..5, VCC
  rail 5).  A real cell puts a P-end stripe and an N-end stripe in the
  same column because their y-ranges do not overlap (the well boundary
  separates them); when the SAME net owns both slots of a column the two
  bars are forced to extend to the well boundary (``reachB``) and merge
  into one continuous vertical bar -- that is the only place where the P
  and N halves of a net join (probed from the real GSCL45 NAND2X1);
- a *diffusion* access point (net, c, rail) forces the owning slot in
  column c to carry the net, and the stripe must *geometrically* cover
  the rail (rail indices are not y-ordered: GND rail 4 sits below the N
  rows, so an index range [0,4] spans only the bottom two rails);
- a *gate* access point (net, c) is a contact between the vertical poly
  stripe and a *horizontal* segment crossing column c -- vertical M1
  stripes run parallel to poly and cannot touch it, so a gate contact
  requires a horizontal segment of the net through column c (M1: drawn
  contact; poly jump: direct same-layer merge);
- horizontal segments hseg[t][c] (rail t, between columns c and c+1):
  * if an end column carries a same-net stripe it must geometrically
    cover rail t (otherwise the segment floats there); an end without a
    stripe is a legal stub -- a gate contact or a pin end;
  * crossing safety: no foreign M1 stripe in either slot of an end
    column may geometrically cover rail t (that would short the
    segment) -- **unless the segment is a poly jump** (different layer,
    no short);
- **poly jumps**: a segment may be routed on poly instead of M1.  This
  is legal only over field oxide (no active in the segment's row at its
  end columns -- poly over active is a transistor) and only where every
  gate stripe at the crossed (left) end column belongs to the segment's
  net (poly-poly crossing shorts).  Every maximal run of poly segments
  must contain a segment crossing a same-net gate (a CP-SAT automaton
  over each (net, rail)); the gate merge is the only junction between
  the M1 and poly parts of a net (there is no M1-poly contact in the
  model).  Adjacent segments on a rail must not switch layers for the
  same net (the wire would break) and must not touch in the same layer
  for different nets (a short);
- connectivity is **layer-aware**: an N-side presence (bar, N-rail M1
  segment, N-rail poly jump) and a P-side presence only meet at a
  *dual* column (same net owns both slots, both bars reach the well
  boundary) or at a gate column (the poly stripe joins every crossing);
  the sweep therefore forces each column between the leftmost and
  rightmost access to carry N or P presence, each gap to be bridged in a
  layer present on both sides, each access bar to be connected by a
  same-rail M1 segment (or be at a dual column), and each net with
  accesses in both halves to have at least one dual column;
- power nets: their access columns get a stripe reaching the fixed power
  rail; no connectivity needed (the rail is the net).

Objective: minimize horizontal segments (wirelength proxy) plus 3 per
vertical stripe plus 15 per poly jump -- short nets first, few contacts
second, M1 preferred over poly.

Deterministic: all iterations are over sorted structures.
"""

from ortools.sat.python import cp_model

from .netlist import diffusion_access_points, gate_access_points

N_RAILS = 6                     # 0/1 N rows, 2/3 P rows, 4=GND, 5=VCC
GND_RAIL = 4
VCC_RAIL = 5
HSEG_WEIGHT = 10
VSEG_WEIGHT = 3
PJUMP_WEIGHT = 15
SOLVE_TIME_LIMIT_S = 60.0


def _status_name(status):
    return {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE"}.get(status, "UNKNOWN")


def device_rail(dev, row):
    """Diffusion rail of a device: N rows 0/1, P rows 2/3."""
    return row + (0 if not dev.is_p else 2)


def well_boundary_y(height_um):
    """The N/P well boundary -- the y at which merged bars join."""
    return height_um / 2.0


class RouteResult(object):
    def __init__(self, status_name, col_owner_n, col_owner_p, lo_n, hi_n,
                 lo_p, hi_p, hseg, pj, reachB_n, reachB_p, width_cols,
                 hseg_count, vseg_count, pj_count):
        self.status_name = status_name
        self.col_owner_n = col_owner_n      # N-half stripe per column
        self.col_owner_p = col_owner_p      # P-half stripe per column
        self.lo_n = lo_n
        self.hi_n = hi_n
        self.lo_p = lo_p
        self.hi_p = hi_p
        self.hseg = hseg                    # dict (rail, col) -> net
        self.pj = pj                        # dict (rail, col) -> bool
        self.reachB_n = reachB_n            # N bars extending to boundary
        self.reachB_p = reachB_p
        self.width_cols = width_cols
        self.hseg_count = hseg_count
        self.vseg_count = vseg_count
        self.pj_count = pj_count

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
                 hseg, pj, reachB_n, reachB_p, access, width_cols, nets):
        self.model = model
        self.owner_n = owner_n
        self.owner_p = owner_p
        self.lo_n = lo_n
        self.hi_n = hi_n
        self.lo_p = lo_p
        self.hi_p = hi_p
        self.hseg = hseg
        self.pj = pj
        self.reachB_n = reachB_n
        self.reachB_p = reachB_p
        self.access = access
        self.width_cols = width_cols
        self.nets = nets


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


def _rail_covers_table(height_um, grid_um, rail_w=0.13):
    """For each rail t, the (lo, hi) pairs whose *geometric* stripe
    (min..max rail-centre y) covers rail t."""
    from .gds import row_geometry
    railY = row_geometry(height_um, grid_um, rail_w)[0]
    table = {}
    for t in range(N_RAILS):
        valid = []
        for lo in range(N_RAILS):
            for hi in range(N_RAILS):
                y0, y1 = railY[lo], railY[hi]
                if (min(y0, y1) <= railY[t] <= max(y0, y1)):
                    valid.append((lo, hi))
        table[t] = valid
    return table


def _field_and_gate_maps(netlist, placement, width_cols):
    """Static legality maps for poly jumps.

    Returns (field, gateNetsAt): field[t] is the set of columns with NO
    active diffusion in the row of rail t; gateNetsAt[c] is the sorted
    list of gate nets whose poly stripe sits at column c.
    """
    active = {}
    for dev in netlist.devices:
        p = placement[dev]
        active.setdefault((dev.is_p, p.row), set()).update(
            range(p.start_col, p.end_col))
    field = {}
    for t in range(4):
        is_p = t >= 2
        row = t - 2 if is_p else t
        field[t] = set(range(width_cols)) - active.get((is_p, row), set())
    gateNetsAt = {}
    for net, cols in gate_access_points(netlist, placement).items():
        for c in cols:
            if (c >= width_cols):
                continue
            gateNetsAt.setdefault(c, set()).add(net)
    return field, gateNetsAt


def _m1_lit(model, h_lit, pj, n, t, c, memo):
    """Bool: the segment (t, c) is an M1 segment of net n."""
    key = (n, t, c)
    if (key in memo):
        return memo[key]
    lit = model.NewBoolVar("m1_%s_%d_%d" % (n, t, c))
    hl = h_lit[(n, t, c)]
    model.Add(lit == 1).OnlyEnforceIf(hl, pj[(t, c)].Not())
    model.Add(lit == 0).OnlyEnforceIf(hl.Not())
    model.Add(lit == 0).OnlyEnforceIf(pj[(t, c)])
    memo[key] = lit
    return lit


def build_routing_model(netlist, placement, width_cols=None,
                        grid_um=0.19, height_um=2.47, poly_jumps=True):
    """Stage-2 CP-SAT model over the fixed placement.

    Returns RoutingModel; solve_routing wraps it.
    """
    if (width_cols is None):
        width_cols = max(p.end_col for p in placement.values())
    model = cp_model.CpModel()

    diffusion, gate, power = _access_points(netlist, placement)
    nets = sorted(n for n in (set(diffusion) | set(gate))
                  if n not in ("VCC", "GND", "VDD", "VSS"))
    net_index = {n: i for i, n in enumerate(nets)}
    power_index = {n: len(nets) + i
                   for i, n in enumerate(sorted(power))}

    # two slots per column: N half (rails 0..4) and P half (rails 2..5)
    owner_n = [model.NewIntVar(-1, len(nets) + len(power_index) - 1,
                               "on_%d" % c) for c in range(width_cols)]
    owner_p = [model.NewIntVar(-1, len(nets) + len(power_index) - 1,
                               "op_%d" % c) for c in range(width_cols)]
    lo_n = [model.NewIntVar(0, GND_RAIL, "lon_%d" % c)
            for c in range(width_cols)]
    hi_n = [model.NewIntVar(0, GND_RAIL, "hin_%d" % c)
            for c in range(width_cols)]
    lo_p = [model.NewIntVar(2, VCC_RAIL, "lop_%d" % c)
            for c in range(width_cols)]
    hi_p = [model.NewIntVar(2, VCC_RAIL, "hip_%d" % c)
            for c in range(width_cols)]
    hseg = {}
    for t in range(4):
        for c in range(width_cols - 1):
            hseg[(t, c)] = model.NewIntVar(
                -1, len(nets) - 1, "hseg_%d_%d" % (t, c))
    pj = {}
    for t in range(4):
        for c in range(width_cols - 1):
            pj[(t, c)] = model.NewBoolVar("pj_%d_%d" % (t, c))
    if (not poly_jumps):
        for v in pj.values():
            model.Add(v == 0)
    # reachB: the slot's bar extends to the well boundary
    reachB_n = [model.NewBoolVar("rbN_%d" % c) for c in range(width_cols)]
    reachB_p = [model.NewBoolVar("rbP_%d" % c) for c in range(width_cols)]

    # geometric coverage booleans per slot, restricted to the rails the
    # slot can physically cover: an N-half stripe (lo/hi in 0..4) spans
    # y [0.065, 0.959] -> covers rails 0/1/4; a P-half stripe (2..5)
    # spans [1.511, 2.405] -> covers 2/3/5.  For pairs the slot cannot
    # cover, no cov variable exists (it is always false) -- creating one
    # with an empty allowed table would forbid every (lo, hi) and make
    # the model trivially infeasible.
    coversTable = _rail_covers_table(height_um, grid_um)
    nCover = set()
    pCover = set()
    for t in range(N_RAILS):
        for lo, hi in coversTable[t]:
            if (lo <= GND_RAIL and hi <= GND_RAIL):
                nCover.add(t)
            if (lo >= 2 and hi >= 2):
                pCover.add(t)
    cov_n = {}
    cov_p = {}
    for c in range(width_cols):
        for t in nCover:
            bn = model.NewBoolVar("covN_%d_%d" % (c, t))
            model.AddAllowedAssignments([lo_n[c], hi_n[c]],
                                        coversTable[t]).OnlyEnforceIf(bn)
            model.AddForbiddenAssignments([lo_n[c], hi_n[c]],
                                          coversTable[t]).OnlyEnforceIf(bn.Not())
            cov_n[(c, t)] = bn
        for t in pCover:
            bp = model.NewBoolVar("covP_%d_%d" % (c, t))
            model.AddAllowedAssignments([lo_p[c], hi_p[c]],
                                        coversTable[t]).OnlyEnforceIf(bp)
            model.AddForbiddenAssignments([lo_p[c], hi_p[c]],
                                          coversTable[t]).OnlyEnforceIf(bp.Not())
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

    # slot active booleans (for reachB channeling and the objective)
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
    # reachB implies the slot is occupied
    for c in range(width_cols):
        model.Add(reachB_n[c] <= v_active_n[c])
        model.Add(reachB_p[c] <= v_active_p[c])

    # --- diffusion access points: slot by rail, geometric coverage ---
    for net, pts in diffusion.items():
        idx = net_index[net]
        for c, r in sorted(pts):
            if (r <= 1):                     # N half
                model.Add(owner_n[c] == idx)
                model.Add(cov_n[(c, r)] == 1)
            else:                            # P half
                model.Add(owner_p[c] == idx)
                model.Add(cov_p[(c, r)] == 1)

    # --- power access points: stripe reaches the power rail ---
    for net, pts in power.items():
        idx = power_index[net]
        for c, r, pRail in sorted(pts):
            if (pRail == GND_RAIL):
                model.Add(owner_n[c] == idx)
                model.Add(hi_n[c] == GND_RAIL)
                model.Add(cov_n[(c, r)] == 1)
            else:
                model.Add(owner_p[c] == idx)
                model.Add(hi_p[c] == VCC_RAIL)
                model.Add(cov_p[(c, r)] == 1)

    # --- dual-column rules: the two bars of one column ---
    # A dual column occupied by the SAME net merges at the well boundary
    # (both bars forced to reachB).  A dual column of DIFFERENT nets is
    # legal (their y-ranges are disjoint) but neither bar may reach the
    # boundary -- at y = H/2 they would overlap and short.
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
            model.Add(reachB_n[c] >= dual[(n, c)])
            model.Add(reachB_p[c] >= dual[(n, c)])
    for c in range(width_cols):
        for n1 in nets:
            for n2 in nets:
                if (n1 == n2):
                    continue
                model.Add(reachB_n[c] + reachB_p[c]
                          + is_owner_n[(n1, c)] + is_owner_p[(n2, c)] <= 3)

    # --- horizontal segments ---
    h_lit = {}
    for n in nets:
        idx = net_index[n]
        for t in range(4):
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
    for n in nets:
        for t in range(4):
            for c in range(width_cols - 1):
                lit = h_lit[(n, t, c)]
                # same-net stripe at an end must cover the rail -- only
                # when that slot can physically reach this rail (a P-half
                # stripe never covers rail 0; a segment on rail 0 merely
                # floats past it, which is legal)
                if (t in nCover):
                    model.Add(cov_n[(c, t)] == 1).OnlyEnforceIf(
                        lit, is_owner_n[(n, c)])
                    model.Add(cov_n[(c + 1, t)] == 1).OnlyEnforceIf(
                        lit, is_owner_n[(n, c + 1)])
                if (t in pCover):
                    model.Add(cov_p[(c, t)] == 1).OnlyEnforceIf(
                        lit, is_owner_p[(n, c)])
                    model.Add(cov_p[(c + 1, t)] == 1).OnlyEnforceIf(
                        lit, is_owner_p[(n, c + 1)])
                # crossing safety: no foreign stripe in either slot of an
                # end column covers the rail -- an M1 segment shorts; a
                # poly jump crosses in a different layer and is safe
                for other in nets + sorted(power_index):
                    if (other == n):
                        continue
                    for cSide in (c, c + 1):
                        if (t in nCover):
                            model.Add(lit + pj[(t, c)].Not()
                                      + is_owner_n[(other, cSide)]
                                      + cov_n[(cSide, t)] <= 3)
                        if (t in pCover):
                            model.Add(lit + pj[(t, c)].Not()
                                      + is_owner_p[(other, cSide)]
                                      + cov_p[(cSide, t)] <= 3)

    # --- poly jump legality (static geometry) ---
    field, gateNetsAt = _field_and_gate_maps(netlist, placement,
                                             width_cols)
    for t in range(4):
        for c in range(width_cols - 1):
            # poly over active at either end column is a transistor; the
            # only exception is the row's own gate at the *crossed* (left)
            # column, handled by the gate-merge rules below
            if (c + 1 not in field[t]):
                model.Add(pj[(t, c)] == 0)
            if (c not in field[t] and c not in gateNetsAt):
                model.Add(pj[(t, c)] == 0)
            # every gate stripe at the crossed column must belong to the
            # segment's net (poly-poly crossing shorts; same-net merges)
            for gn in sorted(gateNetsAt.get(c, ())):
                if (gn in net_index):
                    model.Add(hseg[(t, c)] == net_index[gn]) \
                        .OnlyEnforceIf(pj[(t, c)])
                else:
                    model.Add(pj[(t, c)] == 0)
            # a poly jump is a segment: it cannot be "on poly" and empty
            model.Add(h_active[(t, c)] >= pj[(t, c)])

    # --- poly jump layer rules (E5): adjacent segments ---
    # same net: same layer (a layer switch has no contact and breaks the
    # wire); different nets: NOT the same layer (touching M1 or touching
    # poly shorts)
    for t in range(4):
        for c in range(1, width_cols - 1):
            for n in nets:
                model.Add(pj[(t, c - 1)] == pj[(t, c)]).OnlyEnforceIf(
                    h_lit[(n, t, c - 1)], h_lit[(n, t, c)])
            for n1 in nets:
                for n2 in nets:
                    if (n1 == n2):
                        continue
                    model.Add(h_lit[(n1, t, c - 1)] + h_lit[(n2, t, c)]
                              + pj[(t, c - 1)].Not() + pj[(t, c)].Not()
                              <= 3)
                    model.Add(h_lit[(n1, t, c - 1)] + h_lit[(n2, t, c)]
                              + pj[(t, c - 1)] + pj[(t, c)] <= 3)

    # --- poly jump anchoring (E4): every maximal poly run of a net must
    # cross a same-net gate.  CP-SAT automaton per (net, rail): the
    # letter at column c is 0 (no poly segment of n), 1 (poly, no gate at
    # c) or 2 (poly, same-net gate at c); a run that ends without ever
    # seeing a 2 is rejected. ---
    if (poly_jumps):
        for n in nets:
            for t in range(4):
                seq = []
                for c in range(width_cols - 1):
                    v = model.NewIntVar(0, 2, "pjrun_%s_%d_%d" % (n, t, c))
                    hasGate = c in gateNetsAt and n in gateNetsAt[c]
                    model.Add(v == 0).OnlyEnforceIf(h_lit[(n, t, c)].Not())
                    model.Add(v == 0).OnlyEnforceIf(pj[(t, c)].Not())
                    if (hasGate):
                        model.Add(v == 2).OnlyEnforceIf(
                            h_lit[(n, t, c)], pj[(t, c)])
                    else:
                        model.Add(v == 1).OnlyEnforceIf(
                            h_lit[(n, t, c)], pj[(t, c)])
                    seq.append(v)
                model.AddAutomaton(
                    seq, 0, [0, 2],
                    [(0, 0, 0), (0, 1, 1), (0, 2, 2),
                     (1, 1, 1), (1, 2, 2),
                     (2, 0, 0), (2, 1, 2), (2, 2, 2)])

    # --- gate access points: a horizontal segment crosses the column ---
    # An M1 segment at (t, c-1) or (t, c) contacts the gate; a poly jump
    # only merges when it actually crosses the column (its left column),
    # so the (t, c-1) side must be an M1 segment.
    for net, cols in gate.items():
        if (net not in net_index):
            continue
        for c in cols:
            lits = []
            for t in range(4):
                if (c - 1 >= 0):
                    lits.append(_m1_lit(model, h_lit, pj, net, t, c - 1,
                                        m1_memo))
                if (c <= width_cols - 2):
                    lits.append(h_lit[(net, t, c)])
            if (lits):
                model.Add(sum(lits) >= 1)

    # --- connectivity: layer/rail-aware sweep + transitions at joins ---
    # A net's wire is a chain of segments; adjacent segments on the SAME
    # rail merge, and a rail or layer change (segment ending at column c
    # on rail t1 followed by one starting at column c on rail t2 != t1)
    # must happen at a join: a gate of the net at c (the poly stripe
    # joins every crossing) or a same-net bar at c whose range covers
    # both rails (the merged dual bars for an N<->P change).
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
            for t in (0, 1):
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
            for t in (2, 3):
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
            lits = [h_lit[(n, t, c)] for t in range(4)]
            model.Add(sum(lits) >= 1)
        # rail/layer transitions at column c: a segment ending on rail t1
        # (from c-1) and a segment starting on rail t2 (to c+1)
        pairs = [(0, 1), (1, 0), (2, 3), (3, 2),
                 (0, 2), (0, 3), (1, 2), (1, 3),
                 (2, 0), (3, 0), (2, 1), (3, 1)]
        for c in range(cmin + 1, cmax + 1):
            if (c > width_cols - 2):
                continue            # no segment can start at column c
            gateJoin = c in gate.get(n, ())
            for t1, t2 in pairs:
                if (gateJoin):
                    # the gate at c joins every segment crossing it (M1
                    # contact, poly merge), but a segment ENDING at c
                    # only touches it via the loose M1 edge -- the left
                    # (ending) bridge must therefore be M1
                    model.Add(h_lit[(n, t1, c - 1)] + h_lit[(n, t2, c)]
                              <= 1 + _m1_lit(model, h_lit, pj, n, t1,
                                             c - 1, m1_memo))
                    continue
                join = model.NewBoolVar("join_%s_%d_%d_%d" % (n, c, t1, t2))
                # the joining bar/dual pair only touches M1 ends (a poly
                # end is a different layer), so both bridges must be M1
                m1a = _m1_lit(model, h_lit, pj, n, t1, c - 1, m1_memo)
                m1b = _m1_lit(model, h_lit, pj, n, t2, c, m1_memo)
                if (t1 <= 1 and t2 <= 1):
                    lits = [is_owner_n[(n, c)], cov_n[(c, t1)],
                            cov_n[(c, t2)], m1a, m1b]
                elif (t1 >= 2 and t2 >= 2):
                    lits = [is_owner_p[(n, c)], cov_p[(c, t1)],
                            cov_p[(c, t2)], m1a, m1b]
                elif (t1 <= 1 and t2 >= 2):
                    # N side ends, P side starts: the merged dual bars
                    lits = [is_owner_n[(n, c)], is_owner_p[(n, c)],
                            reachB_n[c], reachB_p[c],
                            cov_n[(c, t1)], cov_p[(c, t2)], m1a, m1b]
                else:
                    # P side ends, N side starts: the merged dual bars
                    lits = [is_owner_n[(n, c)], is_owner_p[(n, c)],
                            reachB_n[c], reachB_p[c],
                            cov_p[(c, t1)], cov_n[(c, t2)], m1a, m1b]
                model.Add(join >= sum(lits) - (len(lits) - 1))
                for lit in lits:
                    model.Add(join <= lit)
                model.Add(h_lit[(n, t1, c - 1)] + h_lit[(n, t2, c)]
                          <= 1 + join)
        # every diffusion access bar must connect: a same-rail M1 segment
        # touching it, or a dual column (the bars merge at the boundary)
        for c, r in sorted(nPts):
            m1lits = []
            if (c - 1 >= 0):
                m1lits.append(_m1_lit(model, h_lit, pj, n, r, c - 1,
                                      m1_memo))
            if (c <= width_cols - 2):
                m1lits.append(_m1_lit(model, h_lit, pj, n, r, c, m1_memo))
            model.Add(dual[(n, c)] + sum(m1lits) >= 1)

    # --- objective: active horizontal segments / vertical stripes ---
    h_count = model.NewIntVar(0, 4 * (width_cols - 1) * max(1, len(nets)),
                              "h_count")
    if (len(nets)):
        model.Add(h_count == sum(h_active.values()))
    v_count = model.NewIntVar(0, 2 * width_cols, "v_count")
    model.Add(v_count == sum(v_active_n[c] for c in range(width_cols))
              + sum(v_active_p[c] for c in range(width_cols)))
    pj_count = model.NewIntVar(0, 4 * (width_cols - 1), "pj_count")
    model.Add(pj_count == sum(pj.values()))
    model.Minimize(h_count * HSEG_WEIGHT + v_count * VSEG_WEIGHT
                   + pj_count * PJUMP_WEIGHT)

    return RoutingModel(model, owner_n, owner_p, lo_n, hi_n, lo_p, hi_p,
                        hseg, pj, reachB_n, reachB_p,
                        (diffusion, gate, power), width_cols, nets)


def solve_routing(netlist, placement, width_cols=None, poly_jumps=True,
                  time_limit_s=SOLVE_TIME_LIMIT_S):
    """Stage-2 solve; returns RouteResult (UNKNOWN on failure)."""
    rm = build_routing_model(netlist, placement, width_cols=width_cols,
                             poly_jumps=poly_jumps)
    solver = cp_model.CpSolver()
    # single worker: parallel search picks different equal-cost optima
    # across runs (AGENTS.md invariant 9 -- the engine must be
    # deterministic)
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = time_limit_s
    status = solver.Solve(rm.model)
    if (status not in (cp_model.OPTIMAL, cp_model.FEASIBLE)):
        return RouteResult(_status_name(status), [], [], [], [], [], [],
                           {}, {}, [], [], 0, 0, 0, 0)
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
    reachB_n = [solver.Value(v) == 1 for v in rm.reachB_n]
    reachB_p = [solver.Value(v) == 1 for v in rm.reachB_p]
    vseg = sum(1 for o in owner_n if o is not None) \
        + sum(1 for o in owner_p if o is not None)
    return RouteResult(
        _status_name(status), owner_n, owner_p, lo_n, hi_n, lo_p, hi_p,
        hseg, pj, reachB_n, reachB_p, rm.width_cols, len(hseg), vseg,
        sum(pj.values()))
