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


def legacyPatternCode(code):
    """The pre-P0-1 encoding string: children in net-enumeration order."""
    return str(code).replace(
        "\'", "").replace("\\", "").replace("\"", "").replace(" ", "")


def canonicalizationImpact(cells, depth=1):
    """Group root cells by legacy vs canonical codes; report the merges.

    Returns a dict with counts and a few example merges (canonical key ->
    the legacy keys it absorbs).  ``mergedGroups`` is how many spurious
    groups the order-sensitive encoding invented; ``recoveredInstances``
    how many extra instances the largest canonical group gains.
    """
    legacyGroups = {}
    canonGroups = {}
    legacy2canon = {}
    for cell in cells:
        if (cell.stopType):
            continue
        tree, code = extract_and_encode_subgraph_tree(cells, cell.id, depth)
        if (len(tree) < 2):
            continue
        legacyKey = legacyPatternCode(code)
        canonKey = canonical_pattern_code(code)
        if (canonKey.find("bool-") >= 0):
            continue
        legacyGroups.setdefault(legacyKey, set()).add(cell.id)
        canonGroups.setdefault(canonKey, set()).add(cell.id)
        legacy2canon[legacyKey] = canonKey

    canon2legacy = {}
    for legacyKey, canonKey in legacy2canon.items():
        canon2legacy.setdefault(canonKey, []).append(legacyKey)
    merges = {c: sorted(ls) for c, ls in canon2legacy.items() if len(ls) > 1}

    recovered = 0
    for canonKey, legacyKeys in merges.items():
        canonSize = len(canonGroups[canonKey])
        biggestLegacy = max(len(legacyGroups[k]) for k in legacyKeys)
        recovered += canonSize - biggestLegacy

    return {
        "codedCells": sum(len(v) for v in canonGroups.values()),
        "legacyGroups": len(legacyGroups),
        "canonicalGroups": len(canonGroups),
        "mergedGroups": len(merges),
        "recoveredInstances": recovered,
        "examples": dict(list(merges.items())[:5]),
    }


if __name__ == "__main__":
    blifDir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "benchmark", "blif")
    for path in sorted(glob.glob(os.path.join(blifDir, "*.blif"))):
        name = os.path.splitext(os.path.basename(path))[0]
        libPath = os.path.join(blifDir, "..", "..", "stdCelllib",
                               "gscl45nm.lib")
        _g, cells, _n, _t = gen_graph_from_liberty_and_blif(libPath, path)
        report = canonicalizationImpact(cells)
        print("%-24s groups %3d -> %-3d merged %2d, recovered instances %d"
              % (name, report["legacyGroups"], report["canonicalGroups"],
                 report["mergedGroups"], report["recoveredInstances"]))
