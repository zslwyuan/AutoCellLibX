"""Netlist layer of the SMT cell-synthesis engine.

Builds the structural model the SAT encodings consume: devices with their
terminal nets, series chains (degree-2 internal nodes, the ASTRAN
diffusion-sharing unit), parallel groups (same drain/source net pair, the
second diffusion-sharing unit), and per-net access-point requirements
(the terminals that must be wired after placement).

Parsing reuses ``smt_cell_placer.parse_spice_subckt`` (single source of
truth for the M<name> d g s b TYPE W=xu format); everything beyond that
is this engine's own model.

Determinism: all iterations are over sorted structures (AGENTS.md
invariant 9).
"""

from smt_cell_placer import Device, parse_spice_subckt

# ASTRAN model (LAYER7_ASTRAN.md §4): a node with exactly two device
# terminals that is not a subcircuit port is a diffusion-sharing point --
# the two devices on it are in series.  Parallel groups are recognised
# separately by terminal-net equality (same drain AND same source AND same
# type): their diffusions can also merge when adjacent.
_SERIES_KIND = "series"
_PARALLEL_KIND = "parallel"


class NetTerminal(object):
    """One terminal of a device on a net: 's'|'d'|'g'."""

    __slots__ = ("device", "kind")

    def __init__(self, device, kind):
        self.device = device
        self.kind = kind        # "s" source, "d" drain, "g" gate

    def __repr__(self):
        return "NetTerminal(%s:%s)" % (self.device.name, self.kind)


class CellNetlist(object):
    """Subckt + device graph + chains/groups + per-net terminals."""

    def __init__(self, subckt):
        self.subckt = subckt
        self.devices = list(subckt.devices)
        self.external = set(subckt.ports)
        # net name -> list of NetTerminal, insertion-ordered by device
        # order (deterministic: the .sp file order is canonical)
        self.net_terms = {}
        for dev in self.devices:
            for kind, net in (("s", dev.source), ("d", dev.drain),
                              ("g", dev.gate)):
                self.net_terms.setdefault(net, []).append(
                    NetTerminal(dev, kind))

    @property
    def nets(self):
        """All nets except the substrate/bulk node (never wired)."""
        return [n for n in sorted(self.net_terms) if n != "BULK"]

    def signal_nets(self, powerNets=("VCC", "GND", "VDD", "VSS")):
        return [n for n in self.nets if n not in powerNets]

    def terminal_devices(self, net):
        return self.net_terms[net]


def find_series_chains(netlist):
    """Series chains via degree-2 internal nodes (deterministic order).

    Returns a list of chains (each a list of Device in walking order,
    longest first, ties by first-device name) plus the set of internal
    nodes used.  Mirrors smt_cell_placer.find_series_chains; kept here so
    the engine owns its structural model.
    """
    from collections import defaultdict
    node_terms = defaultdict(list)
    for dev in netlist.devices:
        node_terms[dev.source].append((dev, "s"))
        node_terms[dev.drain].append((dev, "d"))
    # a diffusion-sharing point must be a *pure* internal node: exactly
    # two source/drain terminals and NO gate terminal.  A net that also
    # feeds a gate (poly) cannot be shared by diffusion -- the poly
    # stripe separates the two diffusion regions (COMPLEX0's
    # cl2#a_2_54# is both cl2#0's source net, cl2#3's drain net and
    # cl2#2's gate net: sharing it as a chain would force three devices
    # to abut under one poly, which is not a real layout).
    internal = set()
    for node, terms in node_terms.items():
        if (node in netlist.external):
            continue
        gateCount = sum(1 for dev in netlist.devices if dev.gate == node)
        if (len(terms) == 2 and gateCount == 0
                and terms[0][0] is not terms[1][0]):
            internal.add(node)

    chains = []
    used = set()
    for dev in sorted(netlist.devices, key=lambda d: d.name):
        if (dev in used):
            continue
        chain = [dev]
        used.add(dev)

        def walk_next(last):
            for node in (last.drain, last.source):
                if (node in internal):
                    for other, _ in node_terms[node]:
                        if (other is not last and other not in used):
                            return other
            return None

        while (True):
            nxt = walk_next(chain[-1])
            if (nxt is None):
                break
            chain.append(nxt)
            used.add(nxt)
        while (True):
            nxt = walk_next(chain[0])
            if (nxt is None):
                break
            chain.insert(0, nxt)
            used.add(nxt)
        chains.append(chain)
    chains.sort(key=lambda c: (-len(c), c[0].name))
    return chains, internal


def find_parallel_groups(netlist):
    """Parallel groups: >=2 devices, same type, same drain/source net
    pair -- terminal *order* ignored (a group's members may list the pair
    either way).  These share diffusion when adjacent (both terminal nets
    equal, so the touching edges are same-net).  Groups are sorted by
    (first device name); members keep netlist order (deterministic block
    order)."""
    from collections import defaultdict
    groups = defaultdict(list)
    for dev in netlist.devices:
        key = (dev.is_p, min(dev.drain, dev.source),
               max(dev.drain, dev.source))
        groups[key].append(dev)
    result = [g for g in groups.values() if len(g) > 1]
    result.sort(key=lambda g: g[0].name)
    return result


def device_nets(dev):
    """Terminal nets of one device in (drain, gate, source) order."""
    return dev.drain, dev.gate, dev.source


class BlockMember(object):
    """One device inside a DiffusionBlock with its orientation.

    Orientation follows the structure: series chains walk from the outer
    net through the internal nodes; parallel groups alternate (even
    member: source left / drain right; odd: flipped) so shared edges are
    always same-net; standalone devices expose source left / drain right.
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
    then singles, each sorted by first-device name)."""
    chains, internal = find_series_chains(netlist)
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
        for node, kind in ((chain[0].source, "s"), (chain[0].drain, "d")):
            if (node != shared[0]):
                left = node
        members.append(BlockMember(chain[0], left, shared[0]))
        for i in range(1, len(chain) - 1):
            members.append(BlockMember(chain[i], shared[i - 1], shared[i]))
        right = None
        for node, kind in ((chain[-1].source, "s"), (chain[-1].drain, "d")):
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


def exposed_net_set(netlist):
    """Nets that have at least one *block-end* diffusion terminal.

    A net whose terminals are all on shared (internal) edges -- e.g. a
    series-chain internal node -- is electrically complete through
    diffusion sharing and needs no M1 access; only nets that touch a block
    end (or a standalone device's ends) are wired.  Power nets are
    included (their ends go to the rails).
    """
    nets = set()
    for block in build_diffusion_blocks(netlist):
        nets.add(block.left_net)
        nets.add(block.right_net)
    return nets


def diffusion_access_points(netlist, placement):
    """Per-net access columns on diffusion, per *terminal device*.

    placement maps Device -> object with start_col, legs, leg_width_cols.
    For every block member, its left edge column carries left_net and its
    right edge column right_net; the access point is (col, device) so the
    caller can derive the diffusion rail from the device.  Block-end
    columns are always access points; shared edges (member i right ==
    member i+1 left, same net) are access points *only for nets that also
    have a block-end terminal elsewhere* (an internal node shared in a
    chain is complete through diffusion and needs no contact).

    Returns ({signal_net: [(col, device)]}, {power_net: [(col, device)]}).
    """
    from collections import defaultdict
    signal = defaultdict(list)
    power = defaultdict(list)
    powerNames = ("VCC", "GND", "VDD", "VSS")
    exposed = exposed_net_set(netlist)
    for block in build_diffusion_blocks(netlist):
        col = placement[block.first].start_col
        for member in block.members:
            p = placement[member.device]
            width = p.legs * p.leg_width_cols
            if (member.left_net in exposed):
                dst = power if member.left_net in powerNames else signal
                dst[member.left_net].append((col, member.device))
            col += width
            if (member.right_net in exposed):
                dst = power if member.right_net in powerNames else signal
                dst[member.right_net].append((col - 1, member.device))
    key = lambda t: (t[0], t[1].name)
    return ({n: sorted(set(pts), key=key) for n, pts in signal.items()},
            {n: sorted(set(pts), key=key) for n, pts in power.items()})


def gate_access_points(netlist, placement):
    """Per-net gate columns: one poly stripe per leg, at the leg centre."""
    from collections import defaultdict
    points = defaultdict(set)
    for dev in netlist.devices:
        p = placement[dev]
        for j in range(p.legs):
            points[dev.gate].add(p.start_col + j * p.leg_width_cols
                                 + p.leg_width_cols // 2)
    return {n: sorted(c) for n, c in points.items()}
