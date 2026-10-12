"""Flatten a (partitioned) mapped gate netlist into ASTRAN-ready SPICE.

Given a yosys ``write_verilog`` technology-mapped netlist and a
transistor-level cell library (``std_celllib/cellsAstranFriendly.sp``),
this module

* parses both sides,
* partitions the instances into connected blocks under a transistor
  budget (the "high-frequency sub-block merge" step: each block becomes
  one custom complex cell; blocks stay inside ASTRAN's proven range), and
* emits one flattened ``.subckt`` per block with the renaming scheme the
  flow has always used (per-instance prefix, pins rewired, '+'-line
  parameters dropped) -- with transistor names guaranteed to start with
  'M', because ASTRAN's parser silently drops anything else
  (see astran_lint).

Everything is deterministic: partition order follows netlist order, port
order follows the module header, and no set iteration reaches the output
(AGENTS.md invariant 9).
"""

import re
from dataclasses import dataclass


@dataclass
class Instance:
    cell_type: str
    name: str
    pins: dict                 # pin name -> net


_KEYWORDS = {"module", "endmodule", "assign", "wire", "input", "output",
             "inout", "reg", "supply0", "supply1", "parameter"}

# Output pins across the GSCL45 combinational cell set (single-output cells
# use Y; the adder cells add YS/YC, flops Q/QN).  Driving nets are found by
# matching these pin names; everything else on an instance is an input.
OUTPUT_PINS = {"Y", "YS", "YC", "Q", "QN", "YN"}


def parse_library_spice(path):
    """cell -> (ports, body M-lines), continuation lines dropped."""
    text = open(path, "r", errors="replace").read()
    lib = {}
    for m in re.finditer(
            r"\.subckt\s+(\w+)\s+([\w\s]+?)\n(.*?)\.ends", text, re.S):
        body = [ln.strip() for ln in m.group(3).splitlines()
                if ln.strip().startswith("M")]
        lib[m.group(1)] = (m.group(2).split(), body)
    return lib


def library_transistor_counts(lib):
    """cell -> transistor count (M-lines in its body)."""
    return {name: len(body) for name, (_, body) in lib.items()}


def parse_mapped_verilog(text, known_cells=None):
    """Instances of a yosys write_verilog(-noattr) mapped netlist, in
    netlist order.  ``known_cells`` (library names) filters false matches
    like 'module'-header lookalikes; None keeps everything non-keyword."""
    insts = []
    for m in re.finditer(r"(\S+)\s+(\S+)\s*\((.*?)\);", text, re.S):
        cell_type, name, pin_blob = m.group(1), m.group(2), m.group(3)
        if cell_type in _KEYWORDS or name in _KEYWORDS:
            continue
        if known_cells is not None and cell_type not in known_cells:
            continue
        # net tokens may be yosys-escaped (\foo[0]) or carry $ separators
        pins = dict(re.findall(r"\.(\w+)\(([^\s)]+)\)", pin_blob))
        if pins:
            insts.append(Instance(cell_type, name, pins))
    return insts


def parse_module_ports(text):
    """(inputs, outputs) in module-header order."""
    header = re.search(r"module\s+\w+\s*\(([^)]*)\)", text, re.S)
    names = [n.strip() for n in header.group(1).split(",") if n.strip()]
    inputs, outputs = [], []
    for m in re.finditer(r"\b(input|output)\b\s+((?:wire|reg)\s+)?([^;]+);",
                         text):
        direction = m.group(1)
        for n in re.split(r"[,\s]+", m.group(3).strip()):
            if not n:
                continue
            (inputs if direction == "input" else outputs).append(n)
    ordered_inputs = [n for n in names if n in inputs]
    ordered_outputs = [n for n in names if n in outputs]
    return ordered_inputs, ordered_outputs


def _driver_consumer_maps(insts):
    driver, consumers = {}, {}
    for inst in insts:
        for pin, net in inst.pins.items():
            if pin in OUTPUT_PINS:
                driver[net] = inst.name
    for inst in insts:
        for pin, net in inst.pins.items():
            if driver.get(net) != inst.name:
                consumers.setdefault(net, []).append(inst.name)
    return driver, consumers


def partition_instances(insts, lib, max_transistors=36):
    """Greedy connected blocks under a transistor budget.

    Seeds with the first unplaced instance (netlist order), then keeps
    adding the first still-unplaced instance that shares a net with the
    block and fits the budget.  An instance that alone exceeds the budget
    forms its own (flagged) block -- the caller decides what to do with it.
    """
    counts = library_transistor_counts(lib)
    driver, consumers = _driver_consumer_maps(insts)
    by_name = {i.name: i for i in insts}
    remaining = {i.name: None for i in insts}          # ordered
    blocks = []

    while remaining:
        seed = next(iter(remaining))
        block = [seed]
        remaining.pop(seed)
        size = counts.get(by_name[seed].cell_type, 0)

        while True:
            boundary_nets = []
            for member in block:
                for net in by_name[member].pins.values():
                    boundary_nets.append(net)
            candidate = None
            for name in remaining:
                inst = by_name[name]
                shares = any(net in inst.pins.values()
                             for net in boundary_nets)
                if shares and size + counts.get(inst.cell_type, 0) <= \
                        max_transistors:
                    candidate = name
                    break
            if candidate is None:
                break
            block.append(candidate)
            remaining.pop(candidate)
            size += counts.get(by_name[candidate].cell_type, 0)
        blocks.append(block)
    return blocks


def block_ports(members, insts, module_inputs, module_outputs):
    """Port list for one block: VCC, inputs (module order, then internal
    nets alphabetically), outputs (module order, then alphabetical), GND.
    A net produced inside the block is an output iff it leaves the block
    or is a module output; every net consumed but not produced inside is
    an input."""
    by_name = {i.name: i for i in insts}
    member_set = set(members)
    driver, consumers = _driver_consumer_maps(insts)
    module_inputs = module_inputs or []
    module_outputs = module_outputs or []

    used, produced = set(), set()
    for name in members:
        for pin, net in by_name[name].pins.items():
            (produced if driver.get(net) == name else used).add(net)

    ins = {n for n in used
           if n in module_inputs or driver.get(n) not in member_set}
    outs = {n for n in produced
            if n in module_outputs
            or any(c not in member_set for c in consumers.get(n, []))}

    def order(nets, module_order):
        front = [n for n in module_order if n in nets]
        rest = sorted(n for n in nets if n not in module_order)
        return front + rest

    return (["VCC"] + order(ins, module_inputs)
            + order(outs, module_outputs) + ["GND"])


def emit_subckt(cell_name, members, insts, lib, ports):
    """Flatten the instances into one .subckt body of transistor lines."""
    by_name = {i.name: i for i in insts}
    lines = [".subckt %s %s" % (cell_name, " ".join(ports))]
    n_trans = 0
    for idx, name in enumerate(members):
        inst = by_name[name]
        ports_lib, body = lib[inst.cell_type]
        # supply pins are implicit in the logical netlist: connect by name
        portmap = {p: inst.pins.get(p, p) for p in ports_lib}
        for body_ln in body:
            tok = body_ln.split()
            nets = [portmap.get(t, "g%d#%s" % (idx, t)) for t in tok[1:5]]
            # transistor names must start with 'M' (astran_lint knows why)
            lines.append("Mg%d_%s %s %s"
                         % (idx, tok[0], " ".join(nets), " ".join(tok[5:])))
            n_trans += 1
    lines.append(".ends %s" % cell_name)
    return "\n".join(lines) + "\n", n_trans


def flatten_blocks(blocks, insts, lib, module_inputs=None,
                   module_outputs=None, name_prefix="BLK"):
    """block list -> {cell_name: (spice_text, transistor_count)}."""
    out = {}
    for idx, members in enumerate(blocks):
        name = "%s%d" % (name_prefix, idx)
        ports = block_ports(members, insts, module_inputs, module_outputs)
        text, n_trans = emit_subckt(name, members, insts, lib, ports)
        out[name] = (text, n_trans)
    return out
