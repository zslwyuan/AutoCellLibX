"""Combinational equivalence between a gold design and its mapped netlist.

The hand-written, per-module truth-table checker used so far does not
scale to the next module.  This module replaces it with a generic one:
yosys emits the pre-mapping design as plain BLIF (``.names`` tables) and
the mapped design as gate-level BLIF (``.gate TYPE pin=net`` referencing
liberty cells); both are simulated exactly -- the ``.gate`` cells through
their liberty ``function`` strings (the same semantics abc mapped
against) -- and compared over every input vector (exhaustive up to
2**20 inputs, then seeded random sampling).

No SAT solver, no third-party dependency: deterministic and offline.
"""

import itertools
import random
import re
from dataclasses import dataclass, field

MAX_EXHAUSTIVE_INPUTS = 20
RANDOM_VECTORS = 1 << 17


# --------------------------------------------------------------------------
# liberty function parsing
# --------------------------------------------------------------------------

def _tokenize_expr(text):
    tokens = []
    for m in re.finditer(r"[A-Za-z_][\w$.\[\]/]*|[!*+^()]", text):
        tokens.append(m.group(0))
    return tokens


def _parse_expr(tokens):
    """Liberty function string -> AST.  Precedence: ! > AND (implicit or
    '*') > '^' > '+'.  Adjacency is AND ("(A B)" == "A*B")."""
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def take():
        tok = tokens[pos[0]]
        pos[0] += 1
        return tok

    def parse_or():
        node = parse_xor()
        while peek() == "+":
            take()
            node = ("or", node, parse_xor())
        return node

    def parse_xor():
        node = parse_and()
        while peek() == "^":
            take()
            node = ("xor", node, parse_and())
        return node

    def parse_and():
        node = parse_unary()
        while True:
            tok = peek()
            if tok == "*":
                take()
                node = ("and", node, parse_unary())
            elif tok is not None and (tok == "(" or
                                      tok[0].isalnum() or tok == "!"):
                node = ("and", node, parse_unary())      # implicit AND
            else:
                break
        return node

    def parse_unary():
        if peek() == "!":
            take()
            return ("not", parse_unary())
        return parse_primary()

    def parse_primary():
        tok = take()
        if tok == "(":
            node = parse_or()
            if take() != ")":
                raise ValueError("unbalanced parentheses in function")
            return node
        if tok in ("0", "1"):
            return ("const", int(tok))
        return ("net", tok)

    ast = parse_or()
    if pos[0] != len(tokens):
        raise ValueError("trailing tokens in function string")
    return ast


def _eval_ast(node, env):
    kind = node[0]
    if kind == "net":
        return env[node[1]]
    if kind == "const":
        return node[1]
    if kind == "not":
        return 1 - _eval_ast(node[1], env)
    if kind == "and":
        return _eval_ast(node[1], env) & _eval_ast(node[2], env)
    if kind == "or":
        return _eval_ast(node[1], env) | _eval_ast(node[2], env)
    if kind == "xor":
        return _eval_ast(node[1], env) ^ _eval_ast(node[2], env)
    raise ValueError("unknown node " + kind)


def _brace_block(text, start):
    """text[start] is '{'; return index just past the matching '}'."""
    depth, i = 1, start + 1
    while depth and i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return i


def parse_liberty_functions(text):
    """{cell: {output_pin: AST}} from a liberty file's function strings.
    Blocks are matched by brace counting -- pin bodies nest timing()
    tables, so a regex cannot find their ends."""
    funcs = {}
    for m in re.finditer(r"cell \((\w+)\) \{", text):
        name = m.group(1)
        body = text[m.start():_brace_block(text, text.index("{", m.start()))]
        for pm in re.finditer(r"pin\((\w+)\)\s*\{", body):
            pin = pm.group(1)
            pin_body = body[pm.start():_brace_block(
                body, body.index("{", pm.start()))]
            fm = re.search(r'function\s*:\s*"([^"]*)"', pin_body)
            if fm:
                funcs.setdefault(name, {})[pin] = \
                    _parse_expr(_tokenize_expr(fm.group(1)))
    return funcs


# --------------------------------------------------------------------------
# BLIF parsing & simulation
# --------------------------------------------------------------------------

@dataclass
class Blif:
    model: str
    inputs: list
    outputs: list
    nodes: dict = field(default_factory=dict)   # out_net -> node tuple


def parse_blif(text):
    blif = None
    current_table = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        words = line.split()
        if words[0] == ".model":
            blif = Blif(words[1], [], [])
            current_table = None
        elif words[0] == ".inputs":
            blif.inputs.extend(words[1:])
            current_table = None
        elif words[0] == ".outputs":
            blif.outputs.extend(words[1:])
            current_table = None
        elif words[0] == ".names":
            current_table = []
            blif.nodes[words[-1]] = ("names", words[1:-1], current_table)
        elif words[0] == ".gate":
            current_table = None
            celltype = words[1]
            pins = dict(p.split("=", 1) for p in words[2:])
            for pin, net in pins.items():
                if pin in ("Y", "YS", "YC"):
                    blif.nodes[net] = ("gate", celltype, pins, pin)
        elif words[0] == ".latch":
            raise ValueError("sequential logic (.latch) is not supported "
                             "-- verify combinational designs only")
        elif words[0][0] == ".":
            current_table = None            # .end, .subckt, ... (unused)
        elif current_table is not None:
            pattern = words[0]
            value = int(words[1]) if len(words) > 1 else 1
            current_table.append((pattern, value))
    if blif is None or not blif.inputs or not blif.outputs:
        raise ValueError("not a BLIF netlist (missing .model/.inputs/.outputs)")
    return blif


def _eval_names(table, values):
    """BLIF cover semantics: first matching row decides, default 0."""
    result = 0
    for pattern, value in table:
        if all(p == "-" or int(p) == v for p, v in zip(pattern, values)):
            result = value
    return result


class _PinEnv(dict):
    """Pin values resolved lazily -- a liberty function only forces the
    pins it actually references, so multi-output cells (FAX1: YS/YC) do
    not fake a combinational loop through each other's pins."""

    def __init__(self, pins, resolve):
        super().__init__()
        self._pins = pins
        self._resolve = resolve

    def __missing__(self, pin):
        value = self._resolve(self._pins[pin])
        self[pin] = value
        return value


def simulate(blif, vector, lib_funcs=None):
    """vector: {input: 0/1} -> {output: 0/1}.  Nets are memoised; the
    producer graph must be acyclic (combinational)."""
    nets = {"$false": 0, "$true": 1, "$undef": 0}
    nets.update(vector)

    def value(net, visiting=()):
        if net in nets:
            return nets[net]
        if net in visiting:
            raise ValueError("combinational loop through net " + net)
        node = blif.nodes[net]
        if node[0] == "names":
            vals = [value(n, visiting + (net,)) for n in node[1]]
            out = _eval_names(node[2], vals)
        else:
            _, celltype, pins, out_pin = node
            env = _PinEnv(pins, lambda n: value(n, visiting + (net,)))
            out = _eval_ast(lib_funcs[celltype][out_pin], env)
        nets[net] = out
        return out

    return {out: value(out) for out in blif.outputs}


# --------------------------------------------------------------------------
# equivalence driver
# --------------------------------------------------------------------------

@dataclass
class VerifyReport:
    ok: bool
    mode: str                    # "exhaustive" | "random"
    vectors_checked: int
    mismatches: list = field(default_factory=list)

    def __str__(self):
        status = "PASS" if self.ok else "FAIL"
        return ("%s: %d input vectors checked (%s), %d mismatch(es)"
                % (status, self.vectors_checked, self.mode,
                   len(self.mismatches)))


def verify(gold_blif_path, gate_blif_path, lib_funcs=None,
           max_input_bits=MAX_EXHAUSTIVE_INPUTS,
           random_vectors=RANDOM_VECTORS, seed=1):
    """Exhaustive (or seeded-random) equivalence of two combinational
    BLIFs.  Returns a VerifyReport; mismatches are (vector, gold, gate)."""
    gold = parse_blif(open(gold_blif_path).read())
    gate = parse_blif(open(gate_blif_path).read())
    if set(gold.inputs) != set(gate.inputs):
        raise ValueError("input mismatch: gold %s vs gate %s"
                         % (gold.inputs, gate.inputs))
    if set(gold.outputs) != set(gate.outputs):
        raise ValueError("output mismatch: gold %s vs gate %s"
                         % (gold.outputs, gate.outputs))

    n = len(gold.inputs)
    if n <= max_input_bits:
        mode = "exhaustive"
        vectors = (dict(zip(gold.inputs, bits))
                   for bits in itertools.product([0, 1], repeat=n))
        total = 1 << n
    else:
        mode = "random"
        rng = random.Random(seed)
        vectors = ({name: rng.getrandbits(1) for name in gold.inputs}
                   for _ in range(random_vectors))
        total = random_vectors

    mismatches = []
    checked = 0
    for vector in vectors:
        g_out = simulate(gold, vector)
        m_out = simulate(gate, vector, lib_funcs)
        checked += 1
        if g_out != m_out:
            mismatches.append((vector, g_out, m_out))
            if len(mismatches) >= 8:
                break
    return VerifyReport(ok=not mismatches, mode=mode,
                        vectors_checked=checked, mismatches=mismatches)
