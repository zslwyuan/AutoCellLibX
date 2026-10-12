""".lib fragments for ad-hoc merged blocks + design-level closure.

``verilog2cells`` produces blocks that only exist as transistor-level
SPICE; this module gives each block a Boolean identity a logic
synthesiser can map against:

* **function** -- composed from the member cells' liberty functions by
  substitution through the block's internal nets (same AST machinery as
  logic_verify), rendered back to liberty infix syntax;
* **area** -- the measured ASTRAN width x row height (never estimated);
* **pin capacitances** -- summed base-cell pin caps of the members that
  read each input port; ``max_capacitance`` copied from the driving
  member's output pin.

``closure_remap`` then proves the point end to end: merge the fragments
into the base library and let abc re-map the original (unmapped) design
-- the area difference is the design-level benefit the tool itself can
find, not our estimate (same honesty principle as yosys_eval).
"""

import os
import re
import subprocess

import gate_flatten as gf
import logic_verify as lv
from yosys_eval import build_extended_liberty
from yosys_import import find_yosys, parse_stat_json


# --------------------------------------------------------------------------
# Boolean function composition
# --------------------------------------------------------------------------

def _sanitize(name):
    """Net name -> liberty-safe identifier (deterministic)."""
    clean = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return clean if clean else "n_"


def _substitute(ast, env):
    kind = ast[0]
    if kind == "net":
        return env.get(ast[1], ast)
    if kind == "const":
        return ast
    if kind == "not":
        return ("not", _substitute(ast[1], env))
    return (kind, _substitute(ast[1], env), _substitute(ast[2], env))


def compose_block_functions(members, insts, lib_funcs, outputs):
    """{output_net: AST} for one block, in terms of its input nets.

    members: instance names (in block order); insts: all Instance objects
    of the mapped netlist; lib_funcs: {cell: {pin: AST}}; outputs: the
    block's output nets (from gate_flatten.block_ports).
    """
    by_name = {i.name: i for i in insts}
    member_set = set(members)
    # net -> (instance, out_pin) for nets driven inside the block
    driver = {}
    for name in members:
        inst = by_name[name]
        for pin, net in inst.pins.items():
            if pin in gf.OUTPUT_PINS:
                driver[net] = (inst, pin)

    def expr_of(net, visiting=()):
        if net in visiting:
            raise ValueError("combinational loop at net " + net)
        drv = driver.get(net)
        if drv is None or drv[0].name not in member_set:
            return ("net", _sanitize(net))
        inst, out_pin = drv
        func = lib_funcs.get(inst.cell_type, {}).get(out_pin)
        if func is None:
            raise ValueError("no liberty function for %s:%s"
                             % (inst.cell_type, out_pin))
        env = {}
        for pin, in_net in inst.pins.items():
            if pin not in gf.OUTPUT_PINS:
                env[pin] = expr_of(in_net, visiting + (net,))
        return _substitute(func, env)

    return {out: expr_of(out) for out in outputs}


def ast_to_liberty(ast):
    """AST -> liberty infix string (adjacency AND, matching gscl45 style)."""
    kind = ast[0]
    if kind == "net":
        return ast[1]
    if kind == "const":
        return str(ast[1])
    if kind == "not":
        return "(!%s)" % ast_to_liberty(ast[1])
    if kind == "and":
        return "(%s %s)" % (ast_to_liberty(ast[1]), ast_to_liberty(ast[2]))
    if kind == "or":
        return "(%s + %s)" % (ast_to_liberty(ast[1]), ast_to_liberty(ast[2]))
    if kind == "xor":
        return "(%s ^ %s)" % (ast_to_liberty(ast[1]), ast_to_liberty(ast[2]))
    raise ValueError("unknown ast node " + kind)


# --------------------------------------------------------------------------
# pin capacitances from the base library
# --------------------------------------------------------------------------

def parse_pin_caps(lib_text):
    """{(cell, pin): {"capacitance": f, "max_capacitance": f}}."""
    caps = {}
    for m in re.finditer(r"cell \((\w+)\)\s*\{", lib_text):
        cell = m.group(1)
        body = lib_text[m.start():lv._brace_block(
            lib_text, lib_text.index("{", m.start()))]
        for pm in re.finditer(r"pin\((\w+)\)\s*\{", body):
            pin = pm.group(1)
            pin_body = body[pm.start():lv._brace_block(
                body, body.index("{", pm.start()))]

            def grab(key):
                m2 = re.search(key + r"\s*:\s*([\d.eE+-]+)", pin_body)
                return float(m2.group(1)) if m2 else 0.0

            caps[(cell, pin)] = {
                "capacitance": grab("capacitance"),
                "max_capacitance": grab("max_capacitance"),
            }
    return caps


def emit_fragment(cell_name, functions_ast, ports, area_um2,
                  pin_caps, leakage=0.0):
    """One ``cell (...) {...}`` liberty fragment.

    functions_ast: {output_net: AST}; ports: block port list (with the
    VCC/GND entries already removed by the caller); pin_caps: {port:
    capacitance} for inputs (outputs get capacitance 0 and the driving
    member's max_capacitance via {"__max__": {...}}).
    """
    max_cap = pin_caps.get("__max__", {})
    lines = ["  cell (%s) {" % cell_name,
             "    area : %.6f;" % area_um2,
             "    cell_leakage_power : %.6f;" % leakage]
    for port in ports:
        if port in functions_ast:
            lines += [
                "    pin(%s) {" % port,
                "      direction : output;",
                "      capacitance : 0;",
                "      max_capacitance : %.6f;" % max_cap.get(port, 0.229396),
                '      function : "%s";' % ast_to_liberty(functions_ast[port]),
                "    }"]
        else:
            lines += [
                "    pin(%s) {" % port,
                "      direction : input;",
                "      capacitance : %.6f;" % pin_caps.get(port, 0.002),
                "    }"]
    lines.append("  }")
    return "\n".join(lines)


def block_pin_caps(members, insts, ports, lib_caps):
    """Input capacitance per port = summed caps of the member pins it
    feeds; output max_capacitance = driver member's output pin value."""
    by_name = {i.name: i for i in insts}
    caps = {}
    max_cap = {}
    driver = {}
    for name in members:
        inst = by_name[name]
        for pin, net in inst.pins.items():
            if pin in gf.OUTPUT_PINS:
                driver[net] = (inst, pin)
    for port in ports:
        fed = 0.0
        for name in members:
            inst = by_name[name]
            for pin, net in inst.pins.items():
                if pin not in gf.OUTPUT_PINS and net == port:
                    fed += lib_caps.get((inst.cell_type, pin),
                                        {}).get("capacitance", 0.0)
        if fed:
            caps[port] = fed
        if port in driver:
            inst, pin = driver[port]
            max_cap[port] = lib_caps.get((inst.cell_type, pin),
                                         {}).get("max_capacitance", 0.0)
    caps["__max__"] = max_cap
    return caps


# --------------------------------------------------------------------------
# design-level closure
# --------------------------------------------------------------------------

def _abc_histogram(verilog_path, top, lib_path, yosys_exe):
    """synth + abc -liberty -> the mapped cell histogram (or raise)."""
    steps = ["read_verilog %s" % verilog_path]
    if top:
        steps.append("synth -top %s" % top)
    else:
        steps += ["hierarchy -auto-top", "synth"]
    steps += ["abc -liberty %s" % lib_path, "opt_clean", "stat -json"]
    proc = subprocess.run([yosys_exe, "-Q", "-T", "-p", "; ".join(steps)],
                          capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError("yosys/abc failed (rc=%d): %s"
                           % (proc.returncode, (proc.stderr or "")[-300:]))
    return parse_stat_json(proc.stdout or "")["histogram"]


def closure_remap(fragments, verilog_path, top, base_lib_path, outdir,
                  yosys_exe=None):
    """Re-map the ORIGINAL Verilog with the extended library.

    Returns {"ok", "extended_lib", "histogram"} -- the caller computes
    areas from the histograms (base histogram comes from the main
    synthesis pass, so only the extended remap runs here).  The BLIF
    round-trip is deliberately avoided: reading the pre-mapping BLIF
    yields $lut cells that abc silently refuses to map.
    """
    yosys_exe = yosys_exe or find_yosys()
    if yosys_exe is None:
        return {"ok": False, "reason": "no yosys executable found"}
    base_text = open(base_lib_path, "r", errors="replace").read()
    merged = build_extended_liberty(base_text, fragments)
    ext_path = os.path.join(outdir, "extended.lib")
    with open(ext_path, "w") as fh:
        fh.write(merged)
    try:
        histogram = _abc_histogram(verilog_path, top, ext_path, yosys_exe)
    except RuntimeError as exc:
        return {"ok": False, "reason": str(exc)}
    return {"ok": True, "extended_lib": ext_path, "histogram": histogram}
