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


def parse_subckt_header(lines):
    """(name, ports) from the single-line .subckt header at lines[0]."""
    parts = lines[0].split()
    if (len(parts) < 2 or parts[0] != ".subckt"):
        raise ValueError("first line is not a .subckt header: %r"
                         % (lines[0],))
    return parts[1], parts[2:]


def generate_port_orders(ports, max_variants=4, pin_supply=False):
    """Deterministic list of port-order variants (first is identity)."""
    variants = [list(ports)]

    def is_supply(p):
        return p.upper() in SUPPLY_NAMES

    if (pin_supply):
        canonical = sorted(ports)
    else:
        supply = [p for p in ports if is_supply(p)]
        signals = [p for p in ports if not is_supply(p)]
        canonical = sorted(supply) + sorted(signals)
    variants.append(canonical)
    variants.append(list(reversed(ports)))

    seed = int(hashlib.md5("|".join(ports).encode()).hexdigest(), 16)
    rng = random.Random(seed)
    while (len(variants) < max_variants):
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
    return unique[:max_variants]


def write_port_order_variants(sp_path, out_dir, max_variants=4):
    """Write <stem>.v<k>.sp variants of sp_path into out_dir; return paths."""
    lines = open(sp_path).read().split("\n")
    name, ports = parse_subckt_header(lines)
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(sp_path))[0]
    paths = []
    for k, order in enumerate(generate_port_orders(ports, max_variants)):
        variant = list(lines)
        variant[0] = ".subckt %s %s" % (name, " ".join(order))
        out = os.path.join(out_dir, "%s.v%d.sp" % (stem, k))
        with open(out, "w") as f:
            f.write("\n".join(variant))
        paths.append(out)
    return paths


def evaluate_port_order_variants(sp_path, out_dir, run_layout, max_variants=4):
    """Run a layout for each variant; return [(variant_path, width_or_none)].

    ``run_layout`` is injected so the CLI can pass astran.run_astran_for_netlist
    (slow) while tests pass a stub.  The callable receives
    (variant_sp_path, cell_name, out_dir) and returns the cell width in um.
    """
    results = []
    variants = write_port_order_variants(sp_path, out_dir, max_variants)
    for variant_path in variants:
        stem = os.path.splitext(os.path.basename(variant_path))[0]
        width = run_layout(variant_path, stem, out_dir)
        results.append((variant_path, width))
    return results


if __name__ == "__main__":
    import sys
    if (len(sys.argv) < 2):
        print("usage: python portorder.py <COMPLEX.sp> [max_variants] "
              "[out_dir]\n"
              "  writes header-only variants; evaluate them with "
              "regenerate_cells.py + ASTRAN (slow)")
        sys.exit(1)
    target = sys.argv[1]
    max_v = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    out_d = sys.argv[3] if len(sys.argv) > 3 else \
        os.path.join(os.path.dirname(target), "portorder")
    for path in write_port_order_variants(target, out_d, max_v):
        print("wrote", path)
    print("Next: run ASTRAN on each variant (e.g. via regenerate_cells.py "
          "with the variant .sp), compare widths in the .Astranlog files.")
