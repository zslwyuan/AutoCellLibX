"""Synthesis-reuse eligibility for generated cells (user request).

ABC's liberty mapping is cone-driven (AUDIT 5.25): a library cell is
only ever used when its Boolean function matches a cone of the network
abc re-synthesises.  Adder's COMPLEX0/1/9/10 are all multi-output with
compound functions, so abc never touches them (complex_used=0).  To
make complex cells genuinely reusable in logic synthesis they must be

  * **single-output** -- one escaping member output pin (all others
    internalised), and
  * **simple, common functions** -- support <= maxSupport inputs and
    depth <= maxDepth levels, ideally 2-level forms the base library
    cannot already cover ((ab+cd), (a+b)(c+d), a^b^c, ...).

This module scores a cluster for that property.  ``_clusterInterface``
(liberty_gen) and ``_composeFunction`` provide the primitives; the
growth side gains an ``internalizeOnly`` bias (BLIFPatternGrowth) so
patterns can *grow* without gaining outputs.
"""

from liberty_gen import _clusterInterface, _composeFunction, libertyPinName


def interfaceOutputCount(members):
    """Number of escaping member output pins (== cell output pins)."""
    inputs, outputs, edges, netDriver = _clusterInterface(
        members, {})
    return len(outputs)


def outputFunctions(members, libFunctions):
    """{libertyPinName(cl<k>#pin): composed function} for escaping pins."""
    inputs, outputs, edges, netDriver = _clusterInterface(
        members, {})
    inside = set(c.id for c in members)
    portNameOf = lambda k, p: libertyPinName("cl%d#%s" % (k, p))
    result = {}
    for outPin in outputs:
        func = _composeFunction(outPin, members, netDriver,
                                libFunctions, portNameOf)
        if (func is not None):
            result[portNameOf(*outPin)] = func
    return result


def functionComplexity(funcStr):
    """(support, logical-depth) of a fully parenthesised liberty
    function.  support = distinct input names; logical-depth counts only
    parentheses that enclose an operator or >=2 operands -- the single-
    operand wraps added by composition ((cl0_A)) are ignored, so a two-
    level function like OR-of-NANDs reads depth 3, not 5."""
    if (funcStr is None):
        return None
    toks = funcStr.replace("(", " ( ").replace(")", " ) ").split()
    stack, pairs = [], {}
    for i, t in enumerate(toks):
        if (t == "("):
            stack.append(i)
        elif (t == ")"):
            pairs[stack.pop()] = i
    isLogical = {}
    for o, c in pairs.items():
        seg = toks[o + 1:c]
        inputs = [t for t in seg if t not in ("(", ")", "!", "+", "^")]
        isLogical[o] = (len(inputs) >= 2
                        or "!" in seg or "+" in seg or "^" in seg)
    depth, maxDepth, st = 0, 0, []
    for i, t in enumerate(toks):
        if (t == "("):
            st.append(isLogical.get(i, False))
            if (st[-1]):
                depth += 1
                maxDepth = max(maxDepth, depth)
        elif (t == ")"):
            if (st and st.pop()):
                depth -= 1
    support = {t for t in toks if t not in ("(", ")", "!", "+", "^")}
    return (len(support), maxDepth)


def reuseEligible(members, libFunctions, maxSupport=4, maxDepth=4):
    """Eligibility dict: single output + simple common function.

    Returns {"eligible": bool, "outputs": n, "functions": {pin: (func,
    support, depth)}, "reason": str} -- the functions dict always lists
    escaping pins with their composed functions, so callers can pick.
    """
    inputs, outputs, edges, netDriver = _clusterInterface(
        members, {})
    portNameOf = lambda k, p: libertyPinName("cl%d#%s" % (k, p))
    funcs = {}
    for outPin in outputs:
        func = _composeFunction(outPin, members, netDriver,
                                libFunctions, portNameOf)
        if (func is not None):
            funcs[portNameOf(*outPin)] = func
    reasons = []
    if (len(outputs) != 1):
        reasons.append("outputs=%d (need 1)" % len(outputs))
    simple = True
    for pin, func in funcs.items():
        cx = functionComplexity(func)
        if (cx is None):
            reasons.append("%s: function uncomposable" % pin)
            simple = False
            continue
        support, depth = cx
        if (support > maxSupport or depth > maxDepth):
            reasons.append("%s: support=%d depth=%d (need <=%d/%d)"
                           % (pin, support, depth, maxSupport, maxDepth))
            simple = False
    return {
        "eligible": len(outputs) == 1 and simple,
        "outputs": len(outputs),
        "functions": funcs,
        "reason": "; ".join(reasons) if reasons else "ok",
    }
