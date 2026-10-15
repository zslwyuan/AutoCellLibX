#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert a CPLEX-LP model (an ASTRAN ``ILPmodel.lp``) into the stage-1 JSON
model schema consumed by tools/gurobi_cl/model_json.py.

This is the validation bridge for the ASTRAN -> Python compaction port: the
JSON path can be exercised end to end (and checked for solution parity
against the legacy LP path) before the in-ASTRAN dump hook
(tools/astran/src/modeldump.cpp) is compiled in.

The conversion deliberately reuses the shim's own parser
(``gurobi_cl._read_cplex_lp`` / ``gurobi_cl._parse_terms``) so the JSON is
semantically identical to what the legacy path would build from the LP text:

- ``_parse_terms`` provides the exact term semantics, including dropping
  non-finite (inf) coefficient terms ("no bound", never a big-M clamp);
- expression columns are already plain ``astranExprN`` variables in the LP
  and their ``CexprN`` definition constraints are kept as ordinary
  constraints;
- constraint bodies without a <=/>=/= operator are dropped, exactly like the
  legacy builder's regex (which knows only those three operators);
- variables are listed in the legacy builder's creation order.

One extra pass over the LP records the constraint *names*, which the legacy
reader discards; the JSON keeps them verbatim.

Usage:  python lp_to_json.py <model.lp> <model.json>
"""
import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gurobi_cl  # noqa: E402  (reuse the shim's exact LP parser)

# same body split as gurobi_cl.main's build()
_BODY_OP_RE = re.compile(r"^(.*?)(<=|>=|=)(.*)$")


def _constraint_names(path):
    """Second scan over the LP that returns the constraint names in the same
    order as ``gurobi_cl._read_cplex_lp`` returns constraint bodies.  The
    line classification must mirror that reader exactly."""
    names = []
    mode = None
    for raw in open(path, "r", errors="replace"):
        t = raw.strip()
        if not t:
            continue
        low = t.lower()
        if low in ("minimize", "maximize"):
            mode = "obj"; continue
        if low in ("subject to", "st", "s.t.", "such that"):
            mode = "cons"; continue
        if low in ("generals", "general", "gen", "integers"):
            mode = "int"; continue
        if low in ("binary", "binaries", "bin"):
            mode = "bin"; continue
        if low in ("semi-continuous", "semi", "semis"):
            mode = "semi"; continue
        if low in ("end",):
            break
        if low.startswith("sos"):
            mode = "sos"; continue
        if mode == "cons":
            names.append(t.split(":", 1)[0].strip() if ":" in t else "")
    return names


def _count_nonfinite(text):
    """Number of tokens that parse to a non-finite float (the terms
    gurobi_cl._parse_terms drops)."""
    n = 0
    for tok in text.replace("+", " + ").replace("-", " - ").split():
        try:
            v = float(tok)
        except ValueError:
            continue
        if not math.isfinite(v):
            n += 1
    return n


def convert_lp_to_json(lp_path, generator="lp_to_json.py 1.0 (AutoCellLibX stage 1)"):
    """Return the JSON model (as a dict) for the given CPLEX-LP file."""
    obj_text, cons, int_vars, bin_vars, semi_vars = gurobi_cl._read_cplex_lp(lp_path)
    names = _constraint_names(lp_path)
    if len(names) != len(cons):
        raise RuntimeError("LP name pass desynchronised (%d names vs %d "
                           "bodies) -- lp_to_json bug" % (len(names), len(cons)))

    dropped_no_operator = 0
    dropped_nonfinite = _count_nonfinite(obj_text)
    constraints = []
    for name, body in zip(names, cons):
        dropped_nonfinite += _count_nonfinite(body)
        m = _BODY_OP_RE.match(body)
        if not m:
            # no <=, >= or = in the body: the legacy builder drops it
            dropped_no_operator += 1
            continue
        lhs, op, rhs = m.group(1), m.group(2), m.group(3)
        lt = gurobi_cl._parse_terms(lhs)
        rt = gurobi_cl._parse_terms(rhs)
        lhs_const = sum(c for c, n in lt if n is None)
        rhs_const = sum(c for c, n in rt if n is None)
        terms = [{"var": n, "coef": c} for c, n in lt if n is not None]
        terms += [{"var": n, "coef": -c} for c, n in rt if n is not None]
        constraints.append({"name": name, "terms": terms,
                            "sense": op, "rhs": rhs_const - lhs_const})

    # variables in the legacy builder's creation order; int_vars first (so an
    # int+bin clash keeps INTEGER, like the legacy declaration sequence)
    ordered, seen = [], set()

    def add(name, integer, ub=None):
        if name not in seen:
            seen.add(name)
            ordered.append({"name": name, "lb": 0, "ub": ub, "integer": integer})

    for n in int_vars:
        add(n, True)
    for n in bin_vars:
        add(n, True, ub=1)
    for n in semi_vars:
        add(n, False)   # legacy shim declares semi vars CONTINUOUS
    for c, n in gurobi_cl._parse_terms(obj_text):
        if n is not None:
            add(n, False)
    for con in constraints:
        for t in con["terms"]:
            add(t["var"], False)

    obj_terms = [{"var": n, "coef": c}
                 for c, n in gurobi_cl._parse_terms(obj_text) if n is not None]
    return {
        "meta": {
            "format_version": 1,
            "generator": generator,
            "source_lp": os.path.basename(lp_path),
            # the legacy path always minimises the parsed objective
            "objective": {"sense": "min", "terms": obj_terms},
            "dropped_no_operator": dropped_no_operator,
            "dropped_nonfinite_terms": dropped_nonfinite,
        },
        "variables": ordered,
        "constraints": constraints,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert an ASTRAN ILPmodel.lp into the stage-1 JSON model schema")
    parser.add_argument("lp", help="input CPLEX-LP file (ILPmodel.lp)")
    parser.add_argument("json", help="output JSON model file")
    args = parser.parse_args(argv)

    data = convert_lp_to_json(args.lp)
    with open(args.json, "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    meta = data["meta"]
    print("wrote %s: %d variables, %d constraints "
          "(dropped: %d no-operator bodies, %d inf terms)"
          % (args.json, len(data["variables"]), len(data["constraints"]),
             meta["dropped_no_operator"], meta["dropped_nonfinite_terms"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
