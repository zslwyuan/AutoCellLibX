"""GDSII -> display geometry.  Qt-free so it can be unit-tested.

Why this module exists instead of "just read the file in the widget": ASTRAN
writes a **bogus GDS UNITS record** (it claims ``0.00125`` user units per
database unit and ``1.25e-9`` m/database-unit, which would make the cells
kilometres wide).  The coordinates themselves are perfectly consistent though:
empirically every generated cell comes out at exactly **16.5 GDS units per
micron**, so ``log height`` / ``bbox height`` is a safe calibration.  The log's
``Cell Size (W x H)`` line stays the authoritative dimension (it is what the
area comparison uses, AGENTS.md invariant 1); this module only needs a scale so
the viewer's ruler reads in real microns.
"""
import os

import gdstk

from . import theme

# Empirically exact for the vendored ASTRAN build + tech_freePDK45.rul:
# a 2.47 um (13 x 0.19) row height is 40.755 GDS units.  Used only when the
# log is unavailable; the log-derived calibration always wins.
ASTRAN_GDS_UNITS_PER_UM = 16.5

# A normal (non-ASTRAN) GDS declares 1 um user units and 1 nm precision; gdstk
# already returns microns for it.
_PLAUSIBLE_USER_UNIT = 1e-6
_PLAUSIBLE_PRECISION = 1e-9


class LayerData(object):
    """Polygons of one (layer, datatype), already converted to microns."""

    __slots__ = ("layer", "datatype", "name", "purpose", "colour", "order",
                 "visible", "polygons", "area_um2")

    def __init__(self, layer, datatype, layer_map=None):
        self.layer = layer
        self.datatype = datatype
        info = theme.layer_info(layer, datatype)
        self.name, self.purpose, self.colour, self.order, self.visible = info
        if layer_map and layer in layer_map:
            # A custom PDK's layer map names the stream; recolor unknown
            # streams deterministically so they stay distinguishable.
            self.name = layer_map[layer]
            if not theme.has_layer(layer, datatype):
                self.colour = theme.fallback_colour(self.name)
        self.polygons = []
        self.area_um2 = 0.0

    @property
    def count(self):
        return len(self.polygons)

    @property
    def label(self):
        return "%s/%s" % (self.layer, self.datatype)

    def __repr__(self):
        return "<LayerData %s %s n=%d>" % (self.label, self.name, self.count)


class LayoutModel(object):
    """One GDS file, flattened and scaled to microns."""

    def __init__(self, path):
        self.path = path
        self.cells = []
        self.layers = {}          # (layer, datatype) -> LayerData
        self.bbox = (0.0, 0.0, 0.0, 0.0)        # cell outline (row boundary)
        self.full_bbox = (0.0, 0.0, 0.0, 0.0)   # incl. well/implant overhang
        self.outline_layer = None
        self.units_per_um = ASTRAN_GDS_UNITS_PER_UM
        self.calibrated = False
        self.log_width_um = None
        self.log_height_um = None

    # -- derived geometry ---------------------------------------------------
    @property
    def width_um(self):
        if self.log_width_um:
            return self.log_width_um
        return self.bbox[2] - self.bbox[0]

    @property
    def height_um(self):
        if self.log_height_um:
            return self.log_height_um
        return self.bbox[3] - self.bbox[1]

    @property
    def polygon_count(self):
        return sum(layer.count for layer in self.layers.values())

    def ordered_layers(self):
        return sorted(self.layers.values(), key=lambda l: (l.order, l.layer))

    def visible_layers(self):
        return [l for l in self.ordered_layers() if l.visible]

    def summary_rows(self):
        """(label, name, purpose, count, area_um2, colour) per layer, draw order."""
        return [(l.label, l.name, l.purpose, l.count, l.area_um2, l.colour)
                for l in self.ordered_layers()]


def _read_log_size(log_path):
    """(width, height) in microns from an ASTRAN log, or (None, None)."""
    if not log_path or not os.path.exists(log_path):
        return None, None
    for line in open(log_path, "r", errors="replace"):
        if "-> Cell Size (W x H): " in line:
            try:
                wh = line.split("-> Cell Size (W x H): ")[1].strip().split("x")
                return float(wh[0]), float(wh[1])
            except (IndexError, ValueError):
                return None, None
    return None, None


def _united_bbox(polys):
    boxes = [b for b in (p.bounding_box() for p in polys) if b is not None]
    if not boxes:
        return None
    return (min(b[0][0] for b in boxes), min(b[0][1] for b in boxes),
            max(b[1][0] for b in boxes), max(b[1][1] for b in boxes))


def _flatten(lib):
    """Polygons of every top-level cell, in file coordinates."""
    out = []
    for cell in lib.top_level():
        try:
            cell.flatten(apply_repetitions=True)
        except Exception:       # pragma: no cover - older gdstk signatures
            pass
        out.extend(cell.get_polygons(apply_repetitions=True))
    if not out:                 # no top-level cell (odd file): take everything
        for cell in lib.cells:
            out.extend(cell.get_polygons(apply_repetitions=True))
    return out


# Layers that trace the *cell outline* (row height), as opposed to the wells
# and implants that bleed past it.  pr_boundary is exact; metal1 is the fallback.
_OUTLINE_LAYERS = (235, 49, 51)


def _outline_bbox(polys):
    for layer in _OUTLINE_LAYERS:
        box = _united_bbox([p for p in polys if p.layer == layer])
        if box and box[2] > box[0] and box[3] > box[1]:
            return box, layer
    return _united_bbox(polys), None


def load_layout(gds_path, log_path=None, units_per_um=None, layer_map=None):
    """Read a GDS and return a LayoutModel in microns.

    ``units_per_um`` overrides the automatic calibration.  Otherwise the
    ASTRAN log (when given and readable) provides the true row height, and a
    standard GDS header is trusted at 1 um/unit; anything else falls back to
    ``ASTRAN_GDS_UNITS_PER_UM``.  ``layer_map`` ({stream: name}) labels the
    GDS layers of a custom PDK.

    Calibration deliberately uses the *cell outline* (pr_boundary / metal1), not
    the file bounding box: the wells overhang the row boundary by ~0.24 um on
    each side, and calibrating on that inflated the block by 19 %.
    """
    lib = gdstk.read_gds(gds_path)
    model = LayoutModel(gds_path)
    model.cells = [c.name for c in lib.cells]

    polys = _flatten(lib)
    full_box = _united_bbox(polys)
    outline_box, outline_layer = _outline_bbox(polys)
    model.outline_layer = outline_layer

    raw_w = (outline_box[2] - outline_box[0]) if outline_box else 1.0
    raw_h = (outline_box[3] - outline_box[1]) if outline_box else 1.0

    log_w, log_h = _read_log_size(log_path)
    model.log_width_um, model.log_height_um = log_w, log_h

    if units_per_um:
        model.units_per_um = units_per_um
        model.calibrated = True
    elif log_h and raw_h > 0:
        model.units_per_um = raw_h / log_h
        model.calibrated = True
    elif (abs(lib.unit - _PLAUSIBLE_USER_UNIT) < 1e-12 and
          abs(lib.precision - _PLAUSIBLE_PRECISION) < 1e-15):
        model.units_per_um = 1.0
        model.calibrated = True
    else:
        model.units_per_um = ASTRAN_GDS_UNITS_PER_UM
        model.calibrated = False

    inv = 1.0 / model.units_per_um
    inv2 = inv * inv

    # --- bucket by layer ---
    for p in polys:
        key = (p.layer, p.datatype)
        layer = model.layers.get(key)
        if layer is None:
            layer = model.layers[key] = LayerData(p.layer, p.datatype, layer_map)
        pts = [(float(x) * inv, float(y) * inv) for x, y in p.points]
        layer.polygons.append(pts)
        layer.area_um2 += float(p.area()) * inv2

    def scaled(box):
        if box is None:
            return (0.0, 0.0, 0.0, 0.0)
        return (box[0] * inv, box[1] * inv, box[2] * inv, box[3] * inv)

    model.full_bbox = scaled(full_box)
    model.bbox = scaled(outline_box or full_box)
    return model
