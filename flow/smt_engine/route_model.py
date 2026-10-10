"""Stage 2 of the SMT engine: grid routing SAT encoding.

With the placement fixed (stage 1), every net's terminals are a set of
(column, rail) access points.  Routing is a grid model over the cell:

- every column carries up to **two** vertical M1 stripes -- one in the N
  half (rails 0..4, GND rail 4) and one in the P half (rails 2..5, VCC
  rail 5).  A real cell puts a P-end stripe and an N-end stripe in the
  same column because their y-ranges do not overlap (the well boundary
  separates them); a net whose terminals span both halves occupies both
  slots and the stripes merge into one continuous vertical bar.
  (Probed from the real GSCL45 NAND2X1: 4 columns, P/N ends sharing
  columns.)
- a *diffusion* access point (net, c, rail) forces the owning slot in
  column c to carry the net, and the stripe must *geometrically* cover
  the rail (rail indices are not y-ordered: GND rail 4 sits below the N
  rows, so an index range [0,4] spans only the bottom two rails);
- a *gate* access point (net, c) is a contact between the vertical poly
  stripe and a *horizontal* M1 segment crossing column c -- vertical
  stripes run parallel to poly and cannot touch it, so a gate contact
  requires a horizontal segment of the net through column c;
- horizontal segments hseg[t][c] (rail t, between columns c and c+1):
  * if an end column carries a same-net stripe it must geometrically
    cover rail t (otherwise the segment floats there); an end without a
    stripe is a legal stub -- a gate contact or a pin end;
  * crossing safety: no foreign stripe (signal or power) in either slot
    of an end column may geometrically cover rail t (that would short
    the segment);
- connectivity: a net's stripes + segments must cover every column
  between its leftmost and rightmost access column, and every pair of
  covered adjacent columns must be bridged by a segment (segments only
  join adjacent columns, so coverage + bridges = connected);
- power nets: their access columns get a stripe reaching the fixed power
  rail; no connectivity needed (the rail is the net).

Objective: minimize horizontal segments (wirelength proxy) plus 3 per
vertical stripe -- short nets first, few contacts second.

Deterministic: all iterations are over sorted structures.
"""

from ortools.sat.python import cp_model

from .netlist import diffusion_access_points, gate_access_points

N_RAILS = 6                     # 0/1 N rows, 2/3 P rows, 4=GND, 5=VCC
GND_RAIL = 4
VCC_RAIL = 5
HSEG_WEIGHT = 10
VSEG_WEIGHT = 3
SOLVE_TIME_LIMIT_S = 60.0


def _status_name(status):
    return {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE"}.get(status, "UNKNOWN")


def device_rail(dev, row):
    """Diffusion rail of a device: N rows 0/1, P rows 2/3."""
    return row + (0 if not dev.is_p else 2)


class RouteResult(object):
    def __init__(self, status_name, col_owner_n, col_owner_p, lo_n, hi_n,
                 lo_p, hi_p, hseg, width_cols, hseg_count, vseg_count):
        self.status_name = status_name
        self.col_owner_n = col_owner_n      # N-half stripe per column
        self.col_owner_p = col_owner_p      # P-half stripe per column
        self.lo_n = lo_n
        self.hi_n = hi_n
        self.lo_p = lo_p
        self.hi_p = hi_p
        self.hseg = hseg                    # dict (rail, col) -> net
        self.width_cols = width_cols
        self.hseg_count = hseg_count
        self.vseg_count = vseg_count

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
                 hseg, access, width_cols, nets):
        self.model = model
        self.owner_n = owner_n
        self.owner_p = owner_p
        self.lo_n = lo_n
        self.hi_n = hi_n
        self.lo_p = lo_p
        self.hi_p = hi_p
        self.hseg = hseg
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


def build_routing_model(netlist, placement, width_cols=None,
                        grid_um=0.19, height_um=2.47):
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

    # --- diffusion access points: slot by rail, geometric coverage ---
    for net, pts in diffusion.items():
        idx = net_index[net]
        for c, r in pts:
            if (r <= 1):                     # N half
                model.Add(owner_n[c] == idx)
                model.Add(cov_n[(c, r)] == 1)
            else:                            # P half
                model.Add(owner_p[c] == idx)
                model.Add(cov_p[(c, r)] == 1)

    # --- power access points: stripe reaches the power rail ---
    for net, pts in power.items():
        idx = power_index[net]
        for c, r, pRail in pts:
            if (pRail == GND_RAIL):
                model.Add(owner_n[c] == idx)
                model.Add(hi_n[c] == GND_RAIL)
                model.Add(cov_n[(c, r)] == 1)
            else:
                model.Add(owner_p[c] == idx)
                model.Add(hi_p[c] == VCC_RAIL)
                model.Add(cov_p[(c, r)] == 1)

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
                # end column covers the rail
                for other in nets + sorted(power_index):
                    if (other == n):
                        continue
                    for cSide in (c, c + 1):
                        if (t in nCover):
                            model.Add(lit + is_owner_n[(other, cSide)]
                                      + cov_n[(cSide, t)] <= 2)
                        if (t in pCover):
                            model.Add(lit + is_owner_p[(other, cSide)]
                                      + cov_p[(cSide, t)] <= 2)

    # --- gate access points: a horizontal segment crosses the column ---
    for net, cols in gate.items():
        if (net not in net_index):
            continue
        for c in cols:
            lits = []
            for t in range(4):
                if (c - 1 >= 0):
                    lits.append(h_lit[(net, t, c - 1)])
                if (c <= width_cols - 2):
                    lits.append(h_lit[(net, t, c)])
            if (lits):
                model.Add(sum(lits) >= 1)

    # --- connectivity: full coverage + per-pair bridge segments ---
    for n in nets:
        cols = set(c for c, r in diffusion.get(n, set()))
        cols |= set(gate.get(n, set()))
        if (not cols):
            continue
        cmin, cmax = min(cols), max(cols)
        cov = {}
        for c in range(cmin, cmax + 1):
            b = model.NewBoolVar("cov_%s_%d" % (n, c))
            lits = [is_owner_n[(n, c)], is_owner_p[(n, c)]]
            for t in range(4):
                if (c - 1 >= 0):
                    lits.append(h_lit[(n, t, c - 1)])
                if (c <= width_cols - 2):
                    lits.append(h_lit[(n, t, c)])
            model.Add(b >= is_owner_n[(n, c)])
            model.Add(b >= is_owner_p[(n, c)])
            for lit in lits[2:]:
                model.Add(b >= lit)
            model.Add(b <= sum(lits))
            cov[c] = b
        for c in range(cmin, cmax + 1):
            model.Add(cov[c] == 1)
        for c in range(cmin, cmax):
            model.Add(sum(h_lit[(n, t, c)] for t in range(4)) >= 1) \
                .OnlyEnforceIf(cov[c], cov[c + 1])

    # --- objective: active horizontal segments / vertical stripes ---
    h_active = {}
    for key, v in hseg.items():
        b = model.NewBoolVar("act_h_%d_%d" % key)
        model.Add(v != -1).OnlyEnforceIf(b)
        model.Add(v == -1).OnlyEnforceIf(b.Not())
        h_active[key] = b
    v_active = []
    for c in range(width_cols):
        b = model.NewBoolVar("act_v_%d" % c)
        model.Add(owner_n[c] != -1).OnlyEnforceIf(b)
        model.Add(owner_n[c] == -1).OnlyEnforceIf(b.Not())
        v_active.append(b)
        b = model.NewBoolVar("act_vp_%d" % c)
        model.Add(owner_p[c] != -1).OnlyEnforceIf(b)
        model.Add(owner_p[c] == -1).OnlyEnforceIf(b.Not())
        v_active.append(b)
    h_count = model.NewIntVar(0, 4 * (width_cols - 1) * max(1, len(nets)),
                              "h_count")
    if (len(nets)):
        model.Add(h_count == sum(h_active.values()))
    v_count = model.NewIntVar(0, 2 * width_cols, "v_count")
    model.Add(v_count == sum(v_active))
    model.Minimize(h_count * HSEG_WEIGHT + v_count * VSEG_WEIGHT)

    return RoutingModel(model, owner_n, owner_p, lo_n, hi_n, lo_p, hi_p,
                        hseg, (diffusion, gate, power), width_cols, nets)


def solve_routing(netlist, placement, width_cols=None,
                  time_limit_s=SOLVE_TIME_LIMIT_S):
    """Stage-2 solve; returns RouteResult (UNKNOWN on failure)."""
    rm = build_routing_model(netlist, placement, width_cols=width_cols)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    status = solver.Solve(rm.model)
    if (status not in (cp_model.OPTIMAL, cp_model.FEASIBLE)):
        return RouteResult(_status_name(status), [], [], [], [], [], [],
                           {}, 0, 0, 0)
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
    vseg = sum(1 for o in owner_n if o is not None) \
        + sum(1 for o in owner_p if o is not None)
    return RouteResult(
        _status_name(status), owner_n, owner_p, lo_n, hi_n, lo_p, hi_p,
        hseg, rm.width_cols, len(hseg), vseg)
