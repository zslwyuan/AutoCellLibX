"""Layout sanity gate for generated cells (P2 merge plan, phase 0).

Every engine-level change (CP-SAT compaction, SMT placement, ...) needs
an independent way to answer "is this layout even sane?" -- that question
cannot be delegated to the engine that produced the layout.  The checks
here are structural and cheap (gdstk only), calibrated the same way the
GUI's viewer is (AGENTS.md: ASTRAN's GDS UNITS record is bogus, use
16.5 units/µm):

* degenerate     -- empty/zero-area bbox (the classic failed-solve cell);
* height         -- metal1 extent height must match the row height
                    (guards wrong-geometry runs; wells overhang the bbox,
                    so H is measured on metal1 like the GUI viewer does);
* grid           -- width must be (close to) a routing-grid multiple;
* layers         -- active / poly / metal1 polygons must exist;
* labels         -- VDD and GND labels must be present (supply rails).

Violations are *structural* breakage, not style; the flow may gate on
them (``layoutSanityGate``) or just report.
"""

import os

import gdstk

ASTRAN_GDS_UNITS_PER_UM = 16.5     # empirical; see gui/gds_model.py
DEFAULT_LAYERS = {"active": 1, "poly": 9, "metal1": 49}


class LayoutSanityReport(object):
    def __init__(self, name):
        self.name = name
        self.violations = []          # list of (code, detail)
        self.metrics = {}

    def add(self, code, detail):
        self.violations.append((code, detail))

    def ok(self):
        return len(self.violations) == 0

    def asDict(self):
        return {"name": self.name, "ok": self.ok(),
                "violations": list(self.violations),
                "metrics": dict(self.metrics)}


def _extent(polygons):
    xs = [p[0] for p in polygons]
    ys = [p[1] for p in polygons]
    return min(xs), min(ys), max(xs), max(ys)


def checkLayout(gdsPath, logPath=None, expectedHeightUm=2.47,
                gridUm=0.19, unitsPerUm=ASTRAN_GDS_UNITS_PER_UM,
                layers=DEFAULT_LAYERS, groundLabels=("GND",),
                supplyLabels=("VDD", "VCC"),
                heightTol=0.05, gridTol=0.25):
    """Structurally check one generated cell GDS; return a report."""
    name = os.path.splitext(os.path.basename(gdsPath))[0]
    report = LayoutSanityReport(name)

    if (not os.path.exists(gdsPath)):
        report.add("missing", "no such file: %s" % gdsPath)
        return report
    try:
        lib = gdstk.read_gds(gdsPath)
    except Exception as exc:                       # noqa: BLE001
        report.add("unreadable", str(exc))
        return report
    if (len(lib.cells) == 0):
        report.add("degenerate", "GDS contains no cells")
        return report

    cell = lib.cells[0]
    if (len(cell.polygons) == 0):
        report.add("degenerate", "cell has no polygons")
        return report

    # Height/width on the metal1 layer (supply rails span the row; the
    # all-layer bbox includes the well overhang and reads ~19% tall).
    m1Layer = layers.get("metal1", 49)
    m1Points = [pt for poly in cell.polygons
                if poly.layer == m1Layer for pt in poly.points]
    if (len(m1Points) == 0):
        report.add("layers", "no metal1 (layer %d) polygons" % m1Layer)
        return report
    x0, y0, x1, y1 = _extent(m1Points)
    widthUm = (x1 - x0) / unitsPerUm
    heightUm = (y1 - y0) / unitsPerUm
    report.metrics.update({"width_um": round(widthUm, 4),
                           "height_um": round(heightUm, 4)})

    if (widthUm <= 0 or heightUm <= 0):
        report.add("degenerate",
                   "zero extent (%.3f x %.3f um)" % (widthUm, heightUm))

    expectedH = expectedHeightUm
    if (logPath is not None and os.path.exists(logPath)):
        # The log's Cell Size is the authoritative target (same source as
        # Astran.loadAstranArea).
        for line in open(logPath, 'r', errors="ignore"):
            if (line.find("-> Cell Size (W x H): ") >= 0):
                parts = line.replace(
                    "-> Cell Size (W x H): ", "").split("x")
                expectedH = float(parts[1])
                report.metrics["log_width_um"] = float(parts[0])
                break
    if (abs(heightUm - expectedH) > heightTol * expectedH):
        report.add("height", "metal1 height %.3f um != row height %.3f um"
                   % (heightUm, expectedH))

    gridRaw = gridUm * unitsPerUm
    ratio = (x1 - x0) / gridRaw
    if (abs(ratio - round(ratio)) > gridTol):
        report.add("grid", "width %.3f um is not a %.3f um grid multiple "
                   "(ratio %.3f)" % (widthUm, gridUm, ratio))

    present = set(poly.layer for poly in cell.polygons)
    for lname, lnum in layers.items():
        if (lnum not in present):
            report.add("layers", "no %s (layer %d) polygons" % (lname, lnum))

    labelTexts = set(label.text.upper() for label in cell.labels)
    report.metrics["labels"] = sorted(labelTexts)
    for req in groundLabels:
        if (req.upper() not in labelTexts):
            report.add("labels", "missing ground label %s" % req)
    if (not any(s.upper() in labelTexts for s in supplyLabels)):
        report.add("labels", "missing supply label (any of %s)"
                   % (supplyLabels,))

    return report
