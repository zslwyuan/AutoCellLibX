"""Canonicalisation impact measurement (roadmap P1-10 prototype).

CellE (arXiv 2026) replaces frequency mining with e-graph equality
saturation.  A faithful e-graph is out of prototype scope, but the
*first-order* effect of "see equivalent instances as one" is measurable
today: it is exactly what canonical_pattern_code (P0-1) does versus the
legacy order-sensitive encoding.  This module quantifies that effect
per netlist -- how many pattern groups the legacy encoding split apart
-- which is the honest lower bound of what richer equivalence (pin
commutativity, functional equivalence) would recover on top.

    python canon_impact.py            # runs over ../benchmark/blif/*.blif
"""

import glob
import os

from blif_preproc import (canonical_pattern_code,
                         extract_and_encode_subgraph_tree,
                         gen_graph_from_liberty_and_blif)


def legacy_pattern_code(code):
    """The pre-P0-1 encoding string: children in net-enumeration order."""
    return str(code).replace(
        "\'", "").replace("\\", "").replace("\"", "").replace(" ", "")


def canonicalization_impact(cells, depth=1):
    """Group root cells by legacy vs canonical codes; report the merges.

    Returns a dict with counts and a few example merges (canonical key ->
    the legacy keys it absorbs).  ``merged_groups`` is how many spurious
    groups the order-sensitive encoding invented; ``recovered_instances``
    how many extra instances the largest canonical group gains.
    """
    legacy_groups = {}
    canon_groups = {}
    legacy2canon = {}
    for cell in cells:
        if (cell.stop_type):
            continue
        tree, code = extract_and_encode_subgraph_tree(cells, cell.id, depth)
        if (len(tree) < 2):
            continue
        legacy_key = legacy_pattern_code(code)
        canon_key = canonical_pattern_code(code)
        if (canon_key.find("bool-") >= 0):
            continue
        legacy_groups.setdefault(legacy_key, set()).add(cell.id)
        canon_groups.setdefault(canon_key, set()).add(cell.id)
        legacy2canon[legacy_key] = canon_key

    canon2legacy = {}
    for legacy_key, canon_key in legacy2canon.items():
        canon2legacy.setdefault(canon_key, []).append(legacy_key)
    merges = {c: sorted(ls) for c, ls in canon2legacy.items() if len(ls) > 1}

    recovered = 0
    for canon_key, legacy_keys in merges.items():
        canon_size = len(canon_groups[canon_key])
        biggest_legacy = max(len(legacy_groups[k]) for k in legacy_keys)
        recovered += canon_size - biggest_legacy

    return {
        "coded_cells": sum(len(v) for v in canon_groups.values()),
        "legacy_groups": len(legacy_groups),
        "canonical_groups": len(canon_groups),
        "merged_groups": len(merges),
        "recovered_instances": recovered,
        "examples": dict(list(merges.items())[:5]),
    }


if __name__ == "__main__":
    blif_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "benchmark", "blif")
    for path in sorted(glob.glob(os.path.join(blif_dir, "*.blif"))):
        name = os.path.splitext(os.path.basename(path))[0]
        lib_path = os.path.join(blif_dir, "..", "..", "std_celllib",
                               "gscl45nm.lib")
        _g, cells, _n, _t = gen_graph_from_liberty_and_blif(lib_path, path)
        report = canonicalization_impact(cells)
        print("%-24s groups %3d -> %-3d merged %2d, recovered instances %d"
              % (name, report["legacy_groups"], report["canonical_groups"],
                 report["merged_groups"], report["recovered_instances"]))
