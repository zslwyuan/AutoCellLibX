"""Pin accessibility metric for generated cells, measured on the GDS.

Motivation (survey integrated into doc/RESEARCH_AND_OPTIMIZATION.md): a
cell whose pins cannot be reached from the routing tracks loses its area
win in detailed routing.  Recent results translate to three checkable
properties of a *generated* cell's metal1 pins:

- **on-track**: the pin centre sits on the routing-track grid.  With a
  non-1:1 gate/metal pitch "gear ratio" off-grid pins cost DRCs and
  detours (DATE'23 gear-ratio study; Sub-10nm on-grid access, ISCAS'24);
- **not blocked**: no polysilicon stripe crosses the pin metal -- a poly
  under the pin blocks the via landing and forces a jog (FastPass,
  TCAD'23: DRC-clean pin access routes);
- **not crowded**: how many other pins share the same track column --
  column saturation is what the concurrent-routing pin-access papers
  (ISPD'23/DAC'24) actually optimise away.

The metric is structural and deterministic: it reads the ASTRAN GDS
(pin text labels on layer 49 = MET1P, metal1 polygons on 49, poly on 9)
and the log for calibration, with the same outline/log calibration rule
as gui/gds_model.py (ASTRAN's UNITS record is bogus; the log height
wins).  Score per pin in [0, 1]; the cell score is the mean, so 1.0 is
"every pin on a free, unblocked track".

    from pin_accessibility import cell_pin_accessibility
    report = cell_pin_accessibility("outputs/adder/COMPLEX0.gds",
                                  "outputs/adder/COMPLEX0.Astranlog")
"""

import os

import gdstk

# Same layers as gui/gds_model.py + tech_freePDK45.rul: metal1 drawing and
# pin text share stream 49; poly is 9; the cell outline is pr_boundary 235.
_METAL1 = 49
_POLY = 9
_OUTLINE_LAYERS = (235, 49, 51)
_ASTRAN_GDS_UNITS_PER_UM = 16.5
_TRACK_EPS_FRAC = 0.15           # |x - round(x/g)*g| <= 0.15*g => on track


def _readLogHeight(log_path):
    if (not log_path or not os.path.exists(log_path)):
        return None
    for line in open(log_path, 'r', errors="ignore"):
        if ("-> Cell Size (W x H): " in line):
            try:
                return float(line.split("-> Cell Size (W x H): ")[1]
                             .split("x")[1])
            except (IndexError, ValueError):
                return None
    return None


def _flatten(lib):
    polys = []
    labels = []
    for cell in lib.top_level():
        try:
            cell.flatten(apply_repetitions=True)
        except Exception:
            pass
        polys.extend(cell.get_polygons(apply_repetitions=True))
        labels.extend(cell.get_labels(apply_repetitions=True))
    if (not polys and not labels):           # odd file: take every cell
        for cell in lib.cells:
            polys.extend(cell.get_polygons(apply_repetitions=True))
            labels.extend(cell.get_labels(apply_repetitions=True))
    return polys, labels


def _unitedBbox(boxes):
    boxes = [b for b in boxes if b is not None]
    if (not boxes):
        return None
    return (min(b[0][0] for b in boxes), min(b[0][1] for b in boxes),
            max(b[1][0] for b in boxes), max(b[1][1] for b in boxes))


def load_cell_geometry(gds_path, log_path=None):
    """Flattened geometry in microns + calibrated scale.

    Returns (polys, labels, units_per_um) where polys/labels are already
    scaled to microns.  Calibration: the log row height vs the outline
    bbox (pr_boundary/metal1), exactly like the GDS viewer; a sane GDS
    header (1 um / 1 nm) is trusted at 1.0; anything else falls back to
    the empirical ASTRAN constant.
    """
    lib = gdstk.read_gds(gds_path)
    polys, labels = _flatten(lib)
    log_h = _readLogHeight(log_path)
    outline = None
    for layer in _OUTLINE_LAYERS:
        box = _unitedBbox([p.bounding_box() for p in polys
                           if p.layer == layer])
        if (box and box[2] > box[0] and box[3] > box[1]):
            outline = box
            break
    raw_h = (outline[3] - outline[1]) if outline else 1.0
    if (log_h and raw_h > 0):
        units_per_um = raw_h / log_h
    elif (abs(lib.unit - 1e-6) < 1e-12 and abs(lib.precision - 1e-9) < 1e-15):
        units_per_um = 1.0
    else:
        units_per_um = _ASTRAN_GDS_UNITS_PER_UM
    inv = 1.0 / units_per_um
    scaled = []
    for p in polys:
        scaled.append((p.layer, [
            (float(x) * inv, float(y) * inv) for x, y in p.points]))
    scaled_labels = []
    for lbl in labels:
        x, y = lbl.origin
        scaled_labels.append((lbl.layer, float(x) * inv, float(y) * inv,
                             lbl.text))
    return scaled, scaled_labels, units_per_um


def _pinBBox(polys, label):
    """Metal1 polygon bbox containing the label point, else a unit box."""
    layer, x, y, text = label
    best = None
    for pts in polys:
        xs = [pt[0] for pt in pts]
        ys = [pt[1] for pt in pts]
        if (min(xs) <= x <= max(xs) and min(ys) <= y <= max(ys)):
            box = (min(xs), min(ys), max(xs), max(ys))
            if (best is None or _boxArea(box) < _boxArea(best)):
                best = box
    if (best is None):
        return (x - 0.5, y - 0.5, x + 0.5, y + 0.5)
    return best


def _boxArea(box):
    return (box[2] - box[0]) * (box[3] - box[1])


def _boxesOverlap(a, b):
    return (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3])


def _polyCrossing(pts, box):
    """Any poly polygon overlapping the pin bbox (gate under the pin)."""
    for p in pts:
        xs = [pt[0] for pt in p]
        ys = [pt[1] for pt in p]
        if (max(xs) > box[0] and min(xs) < box[2]
                and max(ys) > box[1] and min(ys) < box[3]):
            return True
    return False


class PinAccessReport(object):
    def __init__(self, grid_um, pins, score, units_per_um):
        self.grid_um = grid_um
        self.pins = pins                    # list of per-pin dicts
        self.score = score                  # mean pin score in [0, 1]
        self.units_per_um = units_per_um

    def as_dict(self):
        return {"grid_um": self.grid_um, "score": round(self.score, 3),
                "units_per_um": self.units_per_um,
                "pins": [dict(p) for p in self.pins]}


def cell_pin_accessibility(gds_path, log_path=None, grid_um=0.19):
    """Score every metal1 pin of a generated cell; deterministic.

    Returns PinAccessReport; a cell with no pin labels gets score 0.0
    (no accessible pins is the worst case, and a missing label set is a
    layout defect the sanity checker already flags).
    """
    polys, labels, units_per_um = load_cell_geometry(gds_path, log_path)
    pins = [lbl for lbl in labels if lbl[0] == _METAL1]
    metal1 = [pts for layer, pts in polys if layer == _METAL1]
    poly = [pts for layer, pts in polys if layer == _POLY]
    if (not pins):
        return PinAccessReport(grid_um, [], 0.0, units_per_um)
    row = []
    for layer, x, y, text in pins:
        box = _pinBBox(metal1, (layer, x, y, text))
        cx = (box[0] + box[2]) / 2.0
        col = round(cx / grid_um)
        on_track = abs(cx - col * grid_um) <= _TRACK_EPS_FRAC * grid_um
        blocked = _polyCrossing(poly, box)
        crowd = 0
        for other in pins:
            if (other is not None and other[1:] != (x, y, text)):
                o_box = _pinBBox(metal1, other)
                if (abs((o_box[0] + o_box[2]) / 2.0 - cx) < grid_um):
                    crowd += 1
        score = (0.5 if on_track else 0.0) + (0.5 if not blocked else 0.0) \
            - 0.1 * min(crowd, 3)
        score = max(0.0, min(1.0, score))
        row.append({
            "pin": text, "x_um": round(x, 3), "y_um": round(y, 3),
            "on_track": on_track, "blocked": blocked, "crowd": crowd,
            "score": round(score, 3)})
    mean = sum(r["score"] for r in row) / len(row)
    return PinAccessReport(grid_um, row, mean, units_per_um)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="Pin accessibility metric for generated cells")
    ap.add_argument("--gds", required=True)
    ap.add_argument("--log", default=None)
    ap.add_argument("--grid", type=float, default=0.19)
    args = ap.parse_args(argv)
    rep = cell_pin_accessibility(args.gds, args.log, grid_um=args.grid)
    print("cell score = %.3f (grid %.2f um)" % (rep.score, rep.grid_um))
    for p in rep.pins:
        print("  %-8s x=%-7s on_track=%-5s blocked=%-5s crowd=%d score=%.2f"
              % (p["pin"], p["x_um"], p["on_track"], p["blocked"],
                 p["crowd"], p["score"]))


if (__name__ == "__main__"):
    main()
