"""Stage 1 of the SMT engine: joint folding + placement SAT encoding.

Exactly what the reference implementation (smt_cell_placer) encodes, plus
the two diffusion-sharing rules a complete engine must have:

- **parallel groups** abut (strong adjacency): members with the same
  (type, drain, source) nets form a block whose members are consecutive
  columns sharing diffusion (alternating orientation -- see netlist.py);
- **diffusion breaks**: two super-blocks whose touching ends carry
  different nets must be separated by a minimum gap (ASTRAN's wGaps cost
  -- every break widens the cell).  The break constraint is a disjunction
  over each touching direction, active only when the blocks share a row.

Also kept from the reference: series chains abut (end == start), folding
is capped by a manufacturing leg width (otherwise it never pays), two
rows per polarity, NoOverlap2D, objective min(1000*width + legs).  New
soft objective: **gate alignment** (P/N devices with the same gate net
overlapping in columns can share one straight poly stripe -- ASTRAN's
mismatchesGate cost), 10 points per aligned same-gate pair.

The encoding operates on *diffusion blocks* (chains/groups/standalone):
only blocks enter NoOverlap2D and the break constraints.
"""

import math

from ortools.sat.python import cp_model

from .netlist import build_diffusion_blocks

DEFAULT_GRID_UM = 0.19
MIN_LEG_UM = 0.4
MAX_LEG_UM = 1.0
DIFF_BREAK_UM = 0.19          # diffusion-break gap (one grid column)
WIDTH_WEIGHT = 1000
GATE_ALIGN_WEIGHT = 10
SOLVE_TIME_LIMIT_S = 60.0


class PlacementSolution(object):
    def __init__(self, status_name, width_cols, width_um, devices, aligned):
        self.status_name = status_name
        self.width_cols = width_cols
        self.width_um = width_um
        self.devices = devices        # Device -> PlacedTransistor
        self.aligned = aligned        # number of aligned P/N gate pairs


class PlacedTransistor(object):
    __slots__ = ("row", "start_col", "legs", "leg_width_cols")

    def __init__(self, row, start_col, legs, leg_width_cols):
        self.row = row
        self.start_col = start_col
        self.legs = legs
        self.leg_width_cols = leg_width_cols

    @property
    def end_col(self):
        return self.start_col + self.legs * self.leg_width_cols


def _status_name(status):
    return {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE"}.get(status, "UNKNOWN")


def build_layout_model(netlist, grid_um=DEFAULT_GRID_UM,
                       min_leg_um=MIN_LEG_UM, max_leg_um=MAX_LEG_UM,
                       break_um=DIFF_BREAK_UM, max_width_um=None):
    """Stage-1 CP-SAT model.

    Returns (model, width, blocks, dev_vars, align_count); dev_vars maps
    Device -> (start, row, k, legw, block, end, xInterval, rowInterval).
    Exposed for tests; solve_layout wraps it.
    """
    model = cp_model.CpModel()
    # ceil, not round: a 1.0um device on a 0.19 grid is 5.26 -> 6 cols;
    # round would give 5 cols = 0.95um < the device width (illegal).
    # The reference scorer may stay loose; the engine must be legal.
    w_cols = {dev: max(1, int(math.ceil(dev.width_um / grid_um)))
             for dev in netlist.devices}
    blocks = build_diffusion_blocks(netlist)
    min_leg_cols = max(1, int(math.ceil(min_leg_um / grid_um)))
    max_leg_cols = max(1, int(math.ceil(max_leg_um / grid_um)))
    break_cols = max(1, int(math.ceil(break_um / grid_um)))
    if (max_width_um is None):
        # each block is at least the sum of its members' widths (they
        # abut); using the single narrowest member under-estimates badly
        # for multi-member blocks
        min_width = sum(sum(w_cols[m.device] for m in b.members)
                        for b in blocks)
        max_width_um = (min_width + len(blocks) * break_cols + 8) * grid_um
    width_ub = max(1, int(math.ceil(max_width_um / grid_um)))

    dev_vars = {}
    end_vars = []
    for dev in netlist.devices:
        maxFold = max(1, int(math.ceil(w_cols[dev] / min_leg_cols)))
        start = model.NewIntVar(0, width_ub, "start_%s" % dev.name)
        row = model.NewIntVar(0, 1, "row_%s" % dev.name)
        k = model.NewIntVar(1, maxFold, "k_%s" % dev.name)
        num = model.NewIntVar(0, w_cols[dev] + maxFold, "num_%s" % dev.name)
        legw = model.NewIntVar(1, w_cols[dev], "legw_%s" % dev.name)
        block = model.NewIntVar(1, width_ub + 1, "block_%s" % dev.name)
        end = model.NewIntVar(1, width_ub + 1, "end_%s" % dev.name)
        model.Add(num == w_cols[dev] + k - 1)
        model.AddDivisionEquality(legw, num, k)
        model.Add(legw <= max_leg_cols)
        model.AddMultiplicationEquality(block, k, legw)
        model.Add(end == start + block)
        xiv = model.NewIntervalVar(start, block, end, "xiv_%s" % dev.name)
        riv = model.NewIntervalVar(row, 1, row + 1, "riv_%s" % dev.name)
        dev_vars[dev] = (start, row, k, legw, block, end, xiv, riv)
        end_vars.append(end)

    # --- intra-block: members abut and share the row ---
    for block in blocks:
        for a, b in zip(block.members, block.members[1:]):
            model.Add(dev_vars[a.device][1] == dev_vars[b.device][1])
            model.Add(dev_vars[a.device][5] == dev_vars[b.device][0])

    # --- block intervals for NoOverlap2D, per polarity ---
    # P/N devices live in physically separate halves of the row: overlap
    # and diffusion-break rules only apply within one polarity.
    byPolarity = {"P": [], "N": []}
    block_start = {}
    block_end = {}
    for block in blocks:
        start = dev_vars[block.first][0]
        end = dev_vars[block.last][5]
        row = dev_vars[block.first][1]
        key = "P" if block.first.is_p else "N"
        block_start[block] = start
        block_end[block] = end
        byPolarity[key].append((start, end, row, block))
    for key, entries in byPolarity.items():
        if (len(entries) > 1):
            xs = []
            ys = []
            for s, e, r, b in entries:
                size = model.NewIntVar(0, width_ub,
                                       "sbw_%s_%s" % (key, b.first.name))
                model.Add(size == e - s)     # affine size (not a 2-var diff)
                xs.append(model.NewIntervalVar(
                    s, size, e, "sbx_%s_%s" % (key, b.first.name)))
                ys.append(model.NewIntervalVar(
                    r, 1, r + 1, "sby_%s_%s" % (key, b.first.name)))
            model.AddNoOverlap2D(xs, ys)

    # --- diffusion breaks: touching ends with different nets need a gap,
    # per direction, active only when the blocks share a row (same
    # polarity by construction) ---
    for key, entries in byPolarity.items():
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                a = entries[i][3]
                b = entries[j][3]
                same_row = model.NewBoolVar("same_row_%s_%s"
                                           % (a.first.name, b.first.name))
                model.Add(dev_vars[a.first][1] == dev_vars[b.first][1]) \
                    .OnlyEnforceIf(same_row)
                model.Add(dev_vars[a.first][1] != dev_vars[b.first][1]) \
                    .OnlyEnforceIf(same_row.Not())
                u1 = model.NewBoolVar("brk_%s_%s_a"
                                      % (a.first.name, b.first.name))
                u2 = model.NewBoolVar("brk_%s_%s_b"
                                      % (a.first.name, b.first.name))
                # direction a-left-of-b: touching nets a.right, b.left
                if (a.right_net != b.left_net):
                    model.Add(block_end[a] + break_cols <= block_start[b]) \
                        .OnlyEnforceIf(u1)
                # direction b-left-of-a: touching nets b.right, a.left
                if (b.right_net != a.left_net):
                    model.Add(block_end[b] + break_cols <= block_start[a]) \
                        .OnlyEnforceIf(u2)
                model.Add(u1 + u2 >= 1).OnlyEnforceIf(same_row)

    # --- access-point column exclusivity: one column carries at most one
    # vertical M1 stripe, so two different nets may not place access
    # points (diffusion block ends or gate stripes) in the same column.
    # Gate stripes only exist for leg indices j < k (k is a variable), so
    # those pairs are guarded by the jlt literal. ---
    from .netlist import exposed_net_set
    exposed_nets = exposed_net_set(netlist)
    # access spots carry a zone: "P"/"N" diffusion ends (vertical stripes
    # in that half) and "G" gate stripes (poly -- no vertical stripe, but
    # a gate column next to a foreign stripe makes routing hard, so
    # gates stay exclusive too).  P vs N spots in the same column are
    # LEGAL (their stripes live in disjoint y-ranges -- the well
    # boundary separates them), which is exactly how the real GSCL45
    # NAND2X1 packs P and N ends into the same columns.
    spots = []
    for block in blocks:
        zone = "P" if block.first.is_p else "N"
        spots.append((dev_vars[block.first][0], block.left_net, None,
                     block.first, zone))
        spots.append((dev_vars[block.last][5] - 1, block.right_net, None,
                     block.last, zone))
        # shared edges are access columns too (a contact may sit on the
        # shared diffusion) -- but ONLY for nets that are exposed
        # elsewhere (a pure internal node like a series-chain mid node is
        # electrically complete through diffusion and carries no stripe,
        # mirroring diffusion_access_points' filter)
        for a, b in zip(block.members, block.members[1:]):
            if (a.right_net in exposed_nets):
                spots.append((dev_vars[a.device][5] - 1, a.right_net, None,
                             a.device, zone))
            if (b.left_net in exposed_nets):
                spots.append((dev_vars[b.device][0], b.left_net, None,
                             b.device, zone))
    for dev in netlist.devices:
        start = dev_vars[dev][0]
        k = dev_vars[dev][2]
        legw = dev_vars[dev][3]
        half = model.NewIntVar(0, w_cols[dev], "half_%s" % dev.name)
        model.AddDivisionEquality(half, legw, 2)
        max_fold = max(1, int(math.ceil(w_cols[dev] / min_leg_cols)))
        for j in range(max_fold):
            jlt = model.NewBoolVar("jlt_%s_%d" % (dev.name, j))
            model.Add(k >= j + 1).OnlyEnforceIf(jlt)
            model.Add(k <= j).OnlyEnforceIf(jlt.Not())
            spots.append((start + j * legw + half, dev.gate, jlt, dev, "G"))
    for i in range(len(spots)):
        for j2 in range(i + 1, len(spots)):
            a, b = spots[i], spots[j2]
            if (a[1] == b[1] or a[3] == b[3]):
                continue
            if (a[4] == "G" and b[4] == "G"):
                continue            # poly stripes may share a column
            if ((a[4] == "P" and b[4] == "N")
                    or (a[4] == "N" and b[4] == "P")):
                continue            # P/N stripes live in disjoint y-ranges
            if (a[2] is None and b[2] is None):
                model.Add(a[0] != b[0])
            elif (a[2] is None):
                model.Add(a[0] != b[0]).OnlyEnforceIf(b[2])
            elif (b[2] is None):
                model.Add(a[0] != b[0]).OnlyEnforceIf(a[2])
            else:
                both = model.NewBoolVar("both_%d_%d" % (i, j2))
                model.Add(both == 1).OnlyEnforceIf(a[2], b[2])
                model.Add(both == 0).OnlyEnforceIf(a[2].Not())
                model.Add(both == 0).OnlyEnforceIf(b[2].Not())
                model.Add(a[0] != b[0]).OnlyEnforceIf(both)

    # --- gate alignment soft objective: same-gate P/N device pairs whose
    # column intervals overlap can share one straight poly stripe ---
    aligned_pairs = []
    by_gate = {}
    for dev in netlist.devices:
        by_gate.setdefault(dev.gate, []).append(dev)
    for gate, devs in by_gate.items():
        p_devs = [d for d in devs if d.is_p]
        n_devs = [d for d in devs if not d.is_p]
        for p in p_devs:
            for n in n_devs:
                # overlap <-> neither lies fully to one side; encode as
                # u1 + u2 + overlap == 1 with u1/u2 the two separation
                # directions (mutually exclusive for non-empty intervals,
                # so the equation is exact; a separated pair gets overlap=0)
                u1 = model.NewBoolVar("sep_%s_%s_a" % (p.name, n.name))
                u2 = model.NewBoolVar("sep_%s_%s_b" % (p.name, n.name))
                overlap = model.NewBoolVar("align_%s_%s" % (p.name, n.name))
                model.Add(dev_vars[p][5] <= dev_vars[n][0]).OnlyEnforceIf(u1)
                model.Add(dev_vars[n][5] <= dev_vars[p][0]).OnlyEnforceIf(u2)
                model.Add(u1 + u2 + overlap == 1)
                aligned_pairs.append(overlap)
    align_count = model.NewIntVar(0, len(aligned_pairs), "align_count")
    if (aligned_pairs):
        model.Add(sum(aligned_pairs) == align_count)

    width = model.NewIntVar(1, width_ub + 1, "width")
    model.AddMaxEquality(width, end_vars)
    totalLegs = model.NewIntVar(1, sum(
        max(1, int(math.ceil(w_cols[dev] / min_leg_cols)))
        for dev in netlist.devices), "totalLegs")
    model.Add(sum(dev_vars[dev][2] for dev in netlist.devices) == totalLegs)
    model.Minimize(width * WIDTH_WEIGHT
                   - align_count * GATE_ALIGN_WEIGHT
                   + totalLegs)
    return model, width, blocks, dev_vars, align_count


def solve_layout(netlist, grid_um=DEFAULT_GRID_UM, min_leg_um=MIN_LEG_UM,
                 max_leg_um=MAX_LEG_UM, break_um=DIFF_BREAK_UM,
                 time_limit_s=SOLVE_TIME_LIMIT_S):
    """Stage-1 solve; returns PlacementSolution (UNKNOWN on failure)."""
    model, width, blocks, dev_vars, align_count = build_layout_model(
        netlist, grid_um=grid_um, min_leg_um=min_leg_um, max_leg_um=max_leg_um,
        break_um=break_um)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    status = solver.Solve(model)
    if (status not in (cp_model.OPTIMAL, cp_model.FEASIBLE)):
        return PlacementSolution(_status_name(status), None, None, {}, 0)
    placed = {}
    for dev in netlist.devices:
        start, row, k, legw, block, end, _, _ = dev_vars[dev]
        placed[dev] = PlacedTransistor(
            solver.Value(row), solver.Value(start),
            solver.Value(k), solver.Value(legw))
    return PlacementSolution(
        _status_name(status), solver.Value(width),
        solver.Value(width) * grid_um, placed,
        solver.Value(align_count))
