"""Port-order variants for a generated COMPLEX cell (roadmap P1-9).

The .subckt port order changes ASTRAN's layout -- not just cosmetically:
a "canonical" order (VCC GND first, signals sorted) moved COMPLEX0
2.4 -> 2.0 um but COMPLEX10 3.8 -> 8.4 um (AGENTS.md).  The order is
therefore a small, cheap optimisation variable per cell.  This module
generates a deterministic handful of port orders and rewrites only the
.subckt header line (transistor lines reference net names, not
positions); evaluating them means running ASTRAN per variant (slow --
kept out of the default flow).

Variant set (deterministic, no wall-clock or hash randomness):
  v0 identity (the flow's insertion order),
  v1 canonical (supply pins first, signals sorted),
  v2 reversed identity,
  v3.. seeded shuffles (seed = md5 of the port list).
"""

import hashlib
import os
import random

SUPPLY_NAMES = {"VCC", "GND", "VDD", "VSS"}


def parseSubcktHeader(lines):
    """(name, ports) from the single-line .subckt header at lines[0]."""
    parts = lines[0].split()
    if (len(parts) < 2 or parts[0] != ".subckt"):
        raise ValueError("first line is not a .subckt header: %r"
                         % (lines[0],))
    return parts[1], parts[2:]


def generatePortOrders(ports, maxVariants=4, pinSupply=False):
    """Deterministic list of port-order variants (first is identity)."""
    variants = [list(ports)]

    def isSupply(p):
        return p.upper() in SUPPLY_NAMES

    if (pinSupply):
        canonical = sorted(ports)
    else:
        supply = [p for p in ports if isSupply(p)]
        signals = [p for p in ports if not isSupply(p)]
        canonical = sorted(supply) + sorted(signals)
    variants.append(canonical)
    variants.append(list(reversed(ports)))

    seed = int(hashlib.md5("|".join(ports).encode()).hexdigest(), 16)
    rng = random.Random(seed)
    while (len(variants) < maxVariants):
        cand = list(ports)
        rng.shuffle(cand)
        if (cand not in variants):
            variants.append(cand)

    # drop duplicates while preserving order (identity may equal canonical)
    seen = set()
    unique = []
    for v in variants:
        key = tuple(v)
        if (key not in seen):
            seen.add(key)
            unique.append(v)
    return unique[:maxVariants]


def writePortOrderVariants(spPath, outDir, maxVariants=4):
    """Write <stem>.v<k>.sp variants of spPath into outDir; return paths."""
    lines = open(spPath).read().split("\n")
    name, ports = parseSubcktHeader(lines)
    os.makedirs(outDir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(spPath))[0]
    paths = []
    for k, order in enumerate(generatePortOrders(ports, maxVariants)):
        variant = list(lines)
        variant[0] = ".subckt %s %s" % (name, " ".join(order))
        out = os.path.join(outDir, "%s.v%d.sp" % (stem, k))
        with open(out, "w") as f:
            f.write("\n".join(variant))
        paths.append(out)
    return paths


def evaluatePortOrderVariants(spPath, outDir, runLayout, maxVariants=4):
    """Run a layout for each variant; return [(variantPath, widthOrNone)].

    ``runLayout`` is injected so the CLI can pass astran.runAstranForNetlist
    (slow) while tests pass a stub.  The callable receives
    (variantSpPath, cellName, outDir) and returns the cell width in um.
    """
    results = []
    variants = writePortOrderVariants(spPath, outDir, maxVariants)
    for variantPath in variants:
        stem = os.path.splitext(os.path.basename(variantPath))[0]
        width = runLayout(variantPath, stem, outDir)
        results.append((variantPath, width))
    return results


if __name__ == "__main__":
    import sys
    if (len(sys.argv) < 2):
        print("usage: python portorder.py <COMPLEX.sp> [maxVariants] "
              "[outDir]\n"
              "  writes header-only variants; evaluate them with "
              "regenerate_cells.py + ASTRAN (slow)")
        sys.exit(1)
    target = sys.argv[1]
    maxV = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    outD = sys.argv[3] if len(sys.argv) > 3 else \
        os.path.join(os.path.dirname(target), "portorder")
    for path in writePortOrderVariants(target, outD, maxV):
        print("wrote", path)
    print("Next: run ASTRAN on each variant (e.g. via regenerate_cells.py "
          "with the variant .sp), compare widths in the .Astranlog files.")
