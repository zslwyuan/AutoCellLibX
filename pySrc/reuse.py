"""Synthesis-reuse eligibility for generated cells (user request).

ABC's liberty mapping is cone-driven (AUDIT 5.25): a library cell is
only ever used when its Boolean function matches a cone of the network
abc re-synthesises.  Adder's COMPLEX0/1/9/10 are all multi-output with
compound functions, so abc never touches them (complex_used=0).  To
make complex cells genuinely reusable in logic synthesis they must be

  * **single-output** -- one escaping member output pin (all others
    internalised), and
  * **simple, common functions** -- support <= max_support inputs and
    depth <= max_depth levels, ideally 2-level forms the base library
    cannot already cover ((ab+cd), (a+b)(c+d), a^b^c, ...).

This module scores a cluster for that property.  ``_clusterInterface``
(liberty_gen) and ``_composeFunction`` provide the primitives; the
growth side gains an ``internalize_only`` bias (blif_pattern_growth) so
patterns can *grow* without gaining outputs.
"""

from liberty_gen import _clusterInterface, _composeFunction, liberty_pin_name


def interface_output_count(members):
    """Number of escaping member output pins (== cell output pins)."""
    inputs, outputs, edges, net_driver = _clusterInterface(
        members, {})
    return len(outputs)


def output_functions(members, lib_functions):
    """{liberty_pin_name(cl<k>#pin): composed function} for escaping pins."""
    inputs, outputs, edges, net_driver = _clusterInterface(
        members, {})
    inside = set(c.id for c in members)
    port_name_of = lambda k, p: liberty_pin_name("cl%d#%s" % (k, p))
    result = {}
    for out_pin in outputs:
        func = _composeFunction(out_pin, members, net_driver,
                                lib_functions, port_name_of)
        if (func is not None):
            result[port_name_of(*out_pin)] = func
    return result


def function_complexity(func_str):
    """(support, logical-depth) of a fully parenthesised liberty
    function.  support = distinct input names; logical-depth counts only
    parentheses that enclose an operator or >=2 operands -- the single-
    operand wraps added by composition ((cl0_A)) are ignored, so a two-
    level function like OR-of-NANDs reads depth 3, not 5."""
    if (func_str is None):
        return None
    toks = (func_str.replace("(", " ( ").replace(")", " ) ")
            .replace("+", " + ").replace("^", " ^ ").split())
    stack, pairs = [], {}
    for i, t in enumerate(toks):
        if (t == "("):
            stack.append(i)
        elif (t == ")"):
            pairs[stack.pop()] = i
    is_logical = {}
    for o, c in pairs.items():
        seg = toks[o + 1:c]
        inputs = [t for t in seg if t not in ("(", ")", "!", "+", "^")]
        is_logical[o] = (len(inputs) >= 2
                        or "!" in seg or "+" in seg or "^" in seg)
    depth, max_depth, st = 0, 0, []
    for i, t in enumerate(toks):
        if (t == "("):
            st.append(is_logical.get(i, False))
            if (st[-1]):
                depth += 1
                max_depth = max(max_depth, depth)
        elif (t == ")"):
            if (st and st.pop()):
                depth -= 1
    support = {t for t in toks if t not in ("(", ")", "!", "+", "^")}
    return (len(support), max_depth)


def reuse_eligible(members, lib_functions, max_support=4, max_depth=4):
    """Eligibility dict: single output + simple common function.

    Returns {"eligible": bool, "outputs": n, "functions": {pin: (func,
    support, depth)}, "reason": str} -- the functions dict always lists
    escaping pins with their composed functions, so callers can pick.
    """
    inputs, outputs, edges, net_driver = _clusterInterface(
        members, {})
    port_name_of = lambda k, p: liberty_pin_name("cl%d#%s" % (k, p))
    funcs = {}
    for out_pin in outputs:
        func = _composeFunction(out_pin, members, net_driver,
                                lib_functions, port_name_of)
        if (func is not None):
            funcs[port_name_of(*out_pin)] = func
    reasons = []
    if (len(outputs) != 1):
        reasons.append("outputs=%d (need 1)" % len(outputs))
    simple = True
    for pin, func in funcs.items():
        cx = function_complexity(func)
        if (cx is None):
            reasons.append("%s: function uncomposable" % pin)
            simple = False
            continue
        support, depth = cx
        if (support > max_support or depth > max_depth):
            reasons.append("%s: support=%d depth=%d (need <=%d/%d)"
                           % (pin, support, depth, max_support, max_depth))
            simple = False
    return {
        "eligible": len(outputs) == 1 and simple,
        "outputs": len(outputs),
        "functions": funcs,
        "reason": "; ".join(reasons) if reasons else "ok",
    }


def function_to_verilog(func_str, port_map):
    """Translate a fully parenthesised liberty function to a Verilog
    expression.  Parens are preserved (safe precedence) and '&' is
    inserted between adjacent operands -- either as name-name or as
    ')' followed by '(' -- because liberty's juxtaposition means AND."""
    if (func_str is None):
        return None
    toks = (func_str.replace("(", " ( ").replace(")", " ) ")
            .replace("+", " + ").replace("^", " ^ ").split())
    out = []
    prev_out = ""
    for tok in toks:
        if (tok == "!"):
            out.append("~")
        elif (tok == "+"):
            out.append("|")
        elif (tok == "^"):
            out.append("^")
        elif (tok == "("):
            if (prev_out in (")",) or (prev_out and prev_out not in
                                      ("(", "~", "|", "^"))):
                out.append("&")
            out.append("(")
        elif (tok == ")"):
            out.append(")")
        else:
            if (prev_out in (")",) or (prev_out and prev_out not in
                                      ("(", "~", "|", "^"))):
                out.append("&")
            out.append(port_map.get(tok, tok))
        prev_out = out[-1]
    return " ".join(out)


def verilog_design_for_function(func_str, module_name="top",
                             output_name="y", port_names=None):
    """A Verilog module whose output implements ``func_str``.  port_names
    maps the function's input names to a,b,c,d,... in first-appearance
    order when not provided."""
    import re as _re
    inputs = [t for t in _re.findall(r"[A-Za-z0-9_]+", func_str or "")
              if t not in ("!",)]
    if (port_names is None):
        letters = "abcdefghijklmnop"
        seen = {}
        ordered = []
        for name in inputs:
            if (name not in seen):
                seen[name] = letters[len(seen)]
                ordered.append(name)
        port_names = seen
        in_decl = ", ".join(seen.values())
    else:
        in_decl = ", ".join(port_names.values())
    body = function_to_verilog(func_str, port_names)
    if (body is None):
        return None
    return ("module %s(input %s, output %s); assign %s = %s; endmodule\n"
            % (module_name, in_decl, output_name, output_name, body))
