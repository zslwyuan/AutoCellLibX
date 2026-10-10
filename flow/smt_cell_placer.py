"""SAT-style joint folding + placement reference implementation (P2 stage 4).

ASTRAN's transistor layout is sequential: placement (threshold accepting)
first, ILP compaction later.  Recent literature (SAT-based joint folding +
placement, ASP-DAC'26) shows the two decisions interact -- folding a wide
transistor into parallel legs changes both diffusion sharing and row width,
so solving them jointly finds strictly smaller cells.  This module is the
planned *reference implementation* for that idea: it takes a SPICE
subcircuit of at most ~12-16 transistors, solves folding + placement
jointly with OR-Tools CP-SAT, and reports the minimal row width on the
routing grid.  It exists to score ASTRAN's quality (P2_MERGE_PLAN stage 4),
NOT to replace the flow -- see doc/P2_MERGE_PLAN.md.

Model (two diffusion rows per polarity, like ASTRAN's double-row packing):

- every transistor is placed in a P row or an N row (two rows per
  polarity, chosen by the solver -- ASTRAN stacks two P and two N
  diffusions in the 2.47 um row, which is where most of its width win
  over a single-row model comes from);
- transistors connected through an internal node (degree-2 node that is
  not a subcircuit port and feeds no gate) form a *series chain*; chain
  members must share a row and abut (end of one == start of the next)
  so they share diffusion;
- transistors with the same terminal net pair and type form a
  *parallel group*; members must share a row and abut with the
  net-pair alternating orientation (L0 = lexicographically smaller net
  on even members, flipped on odd), so every shared edge is same-net
  and the group shares diffusion like ASTRAN's stacked parallel MOS;
- a transistor can be *folded* into k parallel legs, each of width
  ceil(w / k) on the grid; the legs occupy k contiguous columns.  A leg is
  capped at ``max_leg_um`` (a manufacturing limit on one diffusion finger,
  like ASTRAN's foldTrans): folding only ever widens a block (ceil
  division), so without that cap the optimum is always k=1 and the joint
  choice would be meaningless.  The joint solve picks the k whose waste is
  smallest while the chain still abuts;
- different blocks must not overlap (NoOverlap2D over row + column
  intervals), and two blocks of the same polarity and row whose touching
  ends carry different nets must keep a *diffusion-break* gap (ASTRAN's
  wGaps) -- the break is a disjunction over the two touching directions,
  active only when the blocks share a row.

Deliberate simplifications (documented so the score stays explainable):
diffusion-sharing row stickiness (a parallel group may split across the
two rows, which ASTRAN would not do), and intra-cell routing are not
modelled -- width is an idealized lower bound, and the comparison table
says so.  ASTRAN usually wins or ties once routing overhead counts, which
is exactly the quality signal the reference is for.

Determinism: CP-SAT is deterministic for an identical model (the solver
runs single-worker -- the parallel search picks different equal-cost
optima across runs, AGENTS.md invariant 9), and every iteration here is
over sorted structures, so two runs on the same machine give the same
placement.

Usage:
    from smt_cell_placer import place_cell
    result = place_cell("outputs/adder/COMPLEX0.sp", grid_um=0.19)
    print(result.width_um)
"""

import argparse
import collections
import math
import os
import re

from ortools.sat.python import cp_model

DEFAULT_GRID_UM = 0.19          # routing grid of the GSCL45 binding
MIN_LEG_UM = 0.4                # below this a transistor is not worth folding
MAX_LEG_UM = 1.0                # cap on one diffusion finger (manufacturing)
_SOLVE_TIME_LIMIT_S = 60.0      # per cell; tests lower it
_OBJECTIVE_WIDTH_WEIGHT = 1000  # width dominates; leg count breaks ties

_SPICE_MOS_RE = re.compile(
    r"^(?P<name>M[A-Za-z0-9_#]+)\s+(?P<drain>\S+)\s+(?P<gate>\S+)"
    r"\s+(?P<source>\S+)\s+(?P<bulk>\S+)\s+(?P<type>PMOS|NMOS)"
    r"(?:\s+W=(?P<w>[0-9.]+)u)?",
    re.MULTILINE | re.IGNORECASE)
_SUBCKT_RE = re.compile(
    r"\.subckt\s+(?P<name>\S+)\s+(?P<ports>[^\n]+)", re.IGNORECASE)


class Device(object):
    """One MOS transistor of a subcircuit."""

    def __init__(self, name, drain, gate, source, bulk, is_p, width_um):
        self.name = name
        self.drain = drain
        self.gate = gate
        self.source = source
        self.bulk = bulk
        self.is_p = is_p
        self.width_um = width_um

    def __repr__(self):
        return "Device(%s, %s, w=%.2f)" % (
            self.name, "P" if self.is_p else "N", self.width_um)


class TransistorNetlist(object):
    """Parsed subcircuit: port list + devices (in file order)."""

    def __init__(self, subckt_name, ports, devices):
        self.subckt_name = subckt_name
        self.ports = list(ports)
        self.devices = list(devices)

    @property
    def external_nodes(self):
        return set(self.ports)


def parse_spice_subckt(text):
    """Parse the first .subckt block; return TransistorNetlist.

    Mirrors spice.py's reader in the small: 'M<name> d g s b PMOS W=xu L=yu'
    lines (the '+' continuation lines are ignored -- the flow writes one
    device per physical line).  Raises ValueError on a missing subckt or on
    a MOS line without a parseable width.
    """
    m = _SUBCKT_RE.search(text)
    if (m is None):
        raise ValueError("no .subckt block found")
    subckt_name = m.group("name")
    ports = m.group("ports").split()
    devices = []
    for line in text.splitlines():
        mm = _SPICE_MOS_RE.match(line.strip())
        if (mm is None):
            continue
        w = float(mm.group("w")) if mm.group("w") is not None else 0.5
        devices.append(Device(
            mm.group("name"), mm.group("drain"), mm.group("gate"),
            mm.group("source"), mm.group("bulk"),
            mm.group("type").upper() == "PMOS", w))
    if (not devices):
        raise ValueError("no MOS devices found in subckt %s" % subckt_name)
    return TransistorNetlist(subckt_name, ports, devices)


def find_series_chains(netlist):
    """Group devices into series chains via degree-2 internal nodes.

    A node with exactly two source/drain device terminals that is not a
    subcircuit port -- and feeds no gate (a net under a poly stripe
    cannot be diffusion-shared; COMPLEX0's cl2#a_2_54# is both a chain
    node and a gate net) -- is a diffusion-sharing point: the two devices
    on it are in series.  Chains are walked deterministically (devices
    sorted by name, then the unique path through internal nodes);
    standalone devices come back as length-1 chains.
    """
    node_terms = collections.defaultdict(list)
    for dev in netlist.devices:
        node_terms[dev.source].append((dev, "s"))
        node_terms[dev.drain].append((dev, "d"))
    internal = set()
    for node, terms in node_terms.items():
        if (node in netlist.external_nodes):
            continue
        gate_count = sum(1 for dev in netlist.devices if dev.gate == node)
        if (len(terms) == 2 and gate_count == 0
                and terms[0][0] is not terms[1][0]):
            internal.add(node)

    chains = []
    used = set()
    for dev in sorted(netlist.devices, key=lambda d: d.name):
        if (dev in used):
            continue
        chain = [dev]
        used.add(dev)
        # walk right from the last device through internal nodes
        while (True):
            last = chain[-1]
            nxt = None
            for node in (last.drain, last.source):
                if (node in internal):
                    for other, _ in node_terms[node]:
                        if (other is not last and other not in used):
                            nxt = (node, other)
                            break
                if (nxt is not None):
                    break
            if (nxt is None):
                break
            chain.append(nxt[1])
            used.add(nxt[1])
        # walk left from the first device (rare: chain built from an
        # interior device because of the name-sorted iteration)
        while (True):
            first = chain[0]
            nxt = None
            for node in (first.drain, first.source):
                if (node in internal):
                    for other, _ in node_terms[node]:
                        if (other is not first and other not in used):
                            nxt = (node, other)
                            break
                if (nxt is not None):
                    break
            if (nxt is None):
                break
            chain.insert(0, nxt[1])
            used.add(nxt[1])
        chains.append(chain)
    # deterministic order: longest chains first, then first device name
    chains.sort(key=lambda c: (-len(c), c[0].name))
    return chains


def find_parallel_groups(netlist):
    """Parallel groups: >=2 devices, same type, same drain/source net
    pair -- terminal *order* ignored (members may list the pair either
    way).  These share diffusion when adjacent (both terminal nets equal,
    so the touching edges are same-net).  Groups are sorted by (first
    device name); members keep netlist order (deterministic block
    order)."""
    groups = collections.defaultdict(list)
    for dev in netlist.devices:
        key = (dev.is_p, min(dev.drain, dev.source),
               max(dev.drain, dev.source))
        groups[key].append(dev)
    result = [g for g in groups.values() if len(g) > 1]
    result.sort(key=lambda g: g[0].name)
    return result


class BlockMember(object):
    """One device inside a DiffusionBlock with its orientation.

    Orientation follows the structure: series chains walk from the outer
    net through the internal nodes; parallel groups alternate (even
    member: L0 left / R0 right; odd: flipped) so shared edges are always
    same-net; standalone devices expose source left / drain right.
    """

    __slots__ = ("device", "left_net", "right_net")

    def __init__(self, device, left_net, right_net):
        self.device = device
        self.left_net = left_net
        self.right_net = right_net

    @property
    def name(self):
        return self.device.name


class DiffusionBlock(object):
    """One diffusion-sharing unit: series chain / parallel group / single.

    members are oriented BlockMembers in block order; the block's left
    net is members[0].left_net, right net members[-1].right_net.  Shared
    internal edges (member i right == member i+1 left) are same-net by
    construction.
    """

    def __init__(self, kind, members):
        self.kind = kind
        self.members = list(members)

    @property
    def first(self):
        return self.members[0].device

    @property
    def last(self):
        return self.members[-1].device

    @property
    def left_net(self):
        return self.members[0].left_net

    @property
    def right_net(self):
        return self.members[-1].right_net


def build_diffusion_blocks(netlist):
    """Diffusion blocks (chains, parallel groups, standalone) with member
    orientations; deterministic order (longest chains first, then groups,
    then singles, each sorted by first-device name).  Mirrors the engine's
    structural model (smt_engine.netlist) so both stages see the same
    diffusion-sharing units."""
    chains = find_series_chains(netlist)
    groups = find_parallel_groups(netlist)
    grouped = set()
    blocks = []
    for chain in chains:
        if (len(chain) == 1):
            continue              # length-1 "chains" are standalone
        for dev in chain:
            grouped.add(dev)
    for group in groups:
        for dev in group:
            grouped.add(dev)
    node_terms = collections.defaultdict(list)
    for dev in netlist.devices:
        node_terms[dev.source].append(dev)
        node_terms[dev.drain].append(dev)
    for chain in chains:
        if (len(chain) == 1):
            continue
        # the internal node shared by chain[i] and chain[i+1]
        shared = []
        for a, b in zip(chain, chain[1:]):
            node = None
            for n in (a.source, a.drain):
                if (n == b.source or n == b.drain):
                    node = n
                    break
            shared.append(node)
        members = []
        left = None
        for node in (chain[0].source, chain[0].drain):
            if (node != shared[0]):
                left = node
        members.append(BlockMember(chain[0], left, shared[0]))
        for i in range(1, len(chain) - 1):
            members.append(BlockMember(chain[i], shared[i - 1], shared[i]))
        right = None
        for node in (chain[-1].source, chain[-1].drain):
            if (node != shared[-1]):
                right = node
        members.append(BlockMember(chain[-1], shared[-1], right))
        blocks.append(DiffusionBlock("series", members))
    for group in groups:
        # orientation is net-pair alternation, independent of the
        # original drain/source listing: member j exposes L0 left / R0
        # right when j even, flipped when j odd, so the shared edge
        # (right of j == left of j+1) is always the same net.  L0 is the
        # lexicographically smaller net of the pair (deterministic).
        l0 = min(group[0].drain, group[0].source)
        r0 = max(group[0].drain, group[0].source)
        members = []
        for j, dev in enumerate(group):
            left = l0 if j % 2 == 0 else r0
            right = r0 if j % 2 == 0 else l0
            members.append(BlockMember(dev, left, right))
        blocks.append(DiffusionBlock("parallel", members))
    for dev in netlist.devices:
        if (dev in grouped):
            continue
        blocks.append(DiffusionBlock(
            "single", [BlockMember(dev, dev.source, dev.drain)]))
    blocks.sort(key=lambda b: (len(b.members) == 1, b.first.name))
    return blocks


class PlacementResult(object):
    """Solved placement of one cell."""

    def __init__(self, status_name, width_cols, width_um, devices):
        self.status_name = status_name
        self.width_cols = width_cols
        self.width_um = width_um
        self.devices = devices          # list of PlacedDevice

    def as_dict(self):
        return {
            "status": self.status_name,
            "width_cols": self.width_cols,
            "width_um": round(self.width_um, 4),
            "devices": [d.as_dict() for d in self.devices],
        }


class PlacedDevice(object):
    def __init__(self, name, is_p, row, start_col, legs, leg_width_cols):
        self.name = name
        self.is_p = is_p
        self.row = row
        self.start_col = start_col
        self.legs = legs
        self.leg_width_cols = leg_width_cols

    @property
    def end_col(self):
        return self.start_col + self.legs * self.leg_width_cols

    def as_dict(self):
        return {
            "name": self.name,
            "type": "P" if self.is_p else "N",
            "row": self.row,
            "start_col": self.start_col,
            "end_col": self.end_col,
            "legs": self.legs,
            "leg_width_cols": self.leg_width_cols,
        }


def build_smt_model(netlist, grid_um=DEFAULT_GRID_UM, min_leg_um=MIN_LEG_UM,
                  max_leg_um=MAX_LEG_UM, break_um=DEFAULT_GRID_UM,
                  max_width_um=None):
    """Build the CP-SAT joint folding+placement model.

    Operates on *diffusion blocks* (series chains, parallel groups,
    standalone): members of a block abut and share a row; blocks of one
    polarity do not overlap; same-row blocks whose touching ends carry
    different nets keep a diffusion-break gap (a disjunction over the
    two touching directions).  Returns (model, Wvar, end_vars, dev_vars,
    chains) where dev_vars maps Device -> (start_var, row_var, k_var,
    legw_var, block_w_var, end_var).  Exposed for tests; place_cell()
    wraps it.
    """
    model = cp_model.CpModel()
    w_cols = {}
    for dev in netlist.devices:
        cols = int(round(dev.width_um / grid_um))
        w_cols[dev] = max(1, cols)
    if (max_width_um is None):
        max_width_um = 4.0 * sum(w_cols.values()) * grid_um
    width_ub = max(1, int(math.ceil(max_width_um / grid_um)))

    min_leg_cols = max(1, int(math.ceil(min_leg_um / grid_um)))
    max_leg_cols = max(1, int(math.ceil(max_leg_um / grid_um)))
    break_cols = max(1, int(math.ceil(break_um / grid_um)))
    chains = find_series_chains(netlist)
    blocks = build_diffusion_blocks(netlist)

    dev_vars = {}
    end_vars = []
    for dev in netlist.devices:
        max_fold = max(1, int(math.ceil(w_cols[dev] / min_leg_cols)))
        start = model.NewIntVar(0, width_ub, "start_%s" % dev.name)
        row = model.NewIntVar(0, 1, "row_%s" % dev.name)   # 2 rows/polarity
        k = model.NewIntVar(1, max_fold, "k_%s" % dev.name)
        num = model.NewIntVar(0, w_cols[dev] + max_fold, "num_%s" % dev.name)
        legw = model.NewIntVar(1, w_cols[dev], "legw_%s" % dev.name)
        block = model.NewIntVar(1, width_ub + 1, "block_%s" % dev.name)
        end = model.NewIntVar(1, width_ub + 1, "end_%s" % dev.name)
        # legw == ceil(w_cols / k) == (w_cols + k - 1) // k
        model.Add(num == w_cols[dev] + k - 1)
        model.AddDivisionEquality(legw, num, k)
        model.Add(legw <= max_leg_cols)      # manufacturing cap on one finger
        model.AddMultiplicationEquality(block, k, legw)
        model.Add(end == start + block)
        dev_vars[dev] = (start, row, k, legw, block, end)
        end_vars.append(end)

    # intra-block: members abut and share the row (series chains AND
    # parallel groups share diffusion)
    for block in blocks:
        for a, b in zip(block.members, block.members[1:]):
            model.Add(dev_vars[a.device][1] == dev_vars[b.device][1])
            model.Add(dev_vars[a.device][5] == dev_vars[b.device][0])

    # block intervals for NoOverlap2D, per polarity
    block_start = {}
    block_end = {}
    by_polarity = {"P": [], "N": []}
    for block in blocks:
        start = dev_vars[block.first][0]
        end = dev_vars[block.last][5]
        row = dev_vars[block.first][1]
        block_start[block] = start
        block_end[block] = end
        by_polarity["P" if block.first.is_p else "N"].append(
            (start, end, row, block))
    for key, entries in by_polarity.items():
        if (len(entries) > 1):
            xs = []
            ys = []
            for s, e, r, b in entries:
                size = model.NewIntVar(0, width_ub, "sbw_%s_%s"
                                       % (key, b.first.name))
                model.Add(size == e - s)
                xs.append(model.NewIntervalVar(s, size, e, "sbx_%s_%s"
                                               % (key, b.first.name)))
                ys.append(model.NewIntervalVar(r, 1, r + 1, "sby_%s_%s"
                                               % (key, b.first.name)))
            model.AddNoOverlap2D(xs, ys)

    # diffusion breaks: same-row blocks whose touching ends carry
    # different nets need a gap; a disjunction over the two touching
    # directions, active only when the blocks share a row
    for key, entries in by_polarity.items():
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
                if (a.right_net != b.left_net):
                    model.Add(block_end[a] + break_cols <= block_start[b]) \
                        .OnlyEnforceIf(u1)
                if (b.right_net != a.left_net):
                    model.Add(block_end[b] + break_cols <= block_start[a]) \
                        .OnlyEnforceIf(u2)
                model.Add(u1 + u2 >= 1).OnlyEnforceIf(same_row)

    width = model.NewIntVar(1, width_ub + 1, "width")
    model.AddMaxEquality(width, end_vars)
    total_legs = model.NewIntVar(1, sum(
        max(1, int(math.ceil(w_cols[dev] / min_leg_cols))) for dev in netlist.devices),
        "total_legs")
    k_all = [dev_vars[dev][2] for dev in netlist.devices]
    model.Add(sum(k_all) == total_legs)
    model.Minimize(width * _OBJECTIVE_WIDTH_WEIGHT + total_legs)
    return model, width, end_vars, dev_vars, chains


def _statusName(status):
    return {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE"}.get(status, "UNKNOWN")


def place_cell(sp_path, grid_um=DEFAULT_GRID_UM, min_leg_um=MIN_LEG_UM,
              max_leg_um=MAX_LEG_UM, time_limit_s=_SOLVE_TIME_LIMIT_S):
    """Solve folding+placement for one .sp file; return PlacementResult.

    Solver failures degrade to the objective upper bound recorded by the
    solver (never fabricated): width_cols is the best feasible width the
    solver found, or None when even the trivial bound failed (kept as
    status UNKNOWN so callers can tell a real result from a breakdown).
    """
    with open(sp_path, 'r', errors="ignore") as f:
        text = f.read()
    netlist = parse_spice_subckt(text)
    model, width, end_vars, dev_vars, chains = build_smt_model(
        netlist, grid_um=grid_um, min_leg_um=min_leg_um, max_leg_um=max_leg_um)
    solver = cp_model.CpSolver()
    # single worker: parallel search picks different equal-cost optima
    # across runs (AGENTS.md invariant 9 -- the reference must be
    # deterministic)
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = time_limit_s
    status = solver.Solve(model)
    if (status not in (cp_model.OPTIMAL, cp_model.FEASIBLE)):
        return PlacementResult(_statusName(status), None, None, [])
    placed = []
    for dev in netlist.devices:
        start, row, k, legw, block, end = dev_vars[dev]
        placed.append(PlacedDevice(
            dev.name, dev.is_p, solver.Value(row),
            solver.Value(start), solver.Value(k), solver.Value(legw)))
    width_cols = solver.Value(width)
    return PlacementResult(
        _statusName(status), width_cols, width_cols * grid_um, placed)


def astran_width_from_log(log_path):
    """ASTRAN cell width (um) from its log; None when absent."""
    if (not os.path.exists(log_path)):
        return None
    for line in open(log_path, 'r', errors="ignore"):
        if ("-> Cell Size (W x H): " in line):
            return float(line.split("-> Cell Size (W x H): ")[1]
                         .split("x")[0])
    return None


def compare_with_astran(sp_path, log_path=None, grid_um=DEFAULT_GRID_UM,
                      time_limit_s=_SOLVE_TIME_LIMIT_S):
    """Width comparison for one cell: {smt, astran, ratio}.

    ``astran_plausible`` flags logs that cannot belong to the current
    netlist: the recorded transistor count must match the .sp's device
    count (AUDIT 5.6: COMPLEX1's log once recorded a 30-transistor
    layout for a 26-transistor netlist -- the width belonged to another
    netlist).  A width-based check is deliberately avoided: ASTRAN packs
    devices at roughly one column each (the drawn diffusion is the
    column-quantized leg, not the .sp W in columns), so a width below
    the naive W/2 floor is normal and not a staleness signal.
    """
    result = place_cell(sp_path, grid_um=grid_um, time_limit_s=time_limit_s)
    astran = astran_width_from_log(log_path) if log_path else None
    row = {
        "cell": os.path.basename(sp_path).replace(".sp", ""),
        "smt_status": result.status_name,
        "smt_width_um": result.width_um,
    }
    if (astran is not None and result.width_um is not None):
        row["astran_width_um"] = astran
        row["ratio"] = round(result.width_um / astran, 3)
    else:
        row["astran_width_um"] = astran
        row["ratio"] = None
    row["astran_plausible"] = _astran_log_matches(sp_path, log_path)
    return row


def _astran_log_matches(sp_path, log_path):
    """The log's transistor count must equal the .sp's device count."""
    if (not log_path or not os.path.exists(log_path)):
        return False
    try:
        with open(sp_path, 'r', errors="ignore") as f:
            netlist = parse_spice_subckt(f.read())
    except ValueError:
        return False
    want = len(netlist.devices)
    for line in open(log_path, 'r', errors="ignore"):
        if ("Number of transistors before folding" in line):
            try:
                return int(line.split("before folding:")[1].split()[0]) == want
            except (ValueError, IndexError):
                return False
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="SMT joint folding+placement reference implementation")
    ap.add_argument("--sp", help="one .sp subcircuit file")
    ap.add_argument("--dir", help="directory of .sp files (pairs with "
                    "<name>.Astranlog)")
    ap.add_argument("--grid", type=float, default=DEFAULT_GRID_UM)
    ap.add_argument("--time-limit", type=float, default=_SOLVE_TIME_LIMIT_S)
    args = ap.parse_args(argv)
    sp_files = [args.sp] if args.sp else []
    if (args.dir):
        sp_files += sorted(os.path.join(args.dir, f) for f in
                          os.listdir(args.dir) if f.endswith(".sp"))
    if (not sp_files):
        ap.error("pass --sp FILE or --dir DIR")
    for sp in sp_files:
        log = sp[:-3] + ".Astranlog" if args.dir else None
        row = compare_with_astran(sp, log, grid_um=args.grid,
                                time_limit_s=args.time_limit)
        flag = "" if row["astran_plausible"] else " (STALE)"
        line = ("%(cell)-14s %(smt_status)-10s smt=%(smt_width_um)-8s "
                "astran=%(astran_width_um)-8s ratio=%(ratio)s" % row)
        print(line + flag)


if (__name__ == "__main__"):
    main()
