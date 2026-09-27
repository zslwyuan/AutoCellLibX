"""Content-level quality gates on the committed ASTRAN-generated GDS files.

These guard the GDS export contracts that the PDK review of the adder dataset
found broken once and that are invisible unless the file bytes are inspected:

1. the UNITS record must declare DBU = MINSTEP/2 = 1.25nm so the drawn
   geometry equals the designed geometry (the record used to be hardcoded to
   garbage bytes, which made every reader that fell back to 1nm draw the cells
   at 80% of the intended size);
2. the drawn cell outline must match the "Cell Size (W x H)" line of the
   ASTRAN log next to it (the area metrics read the log, so any drift between
   log and GDS silently corrupts every width comparison);
3. every port of the netlist -- VCC and GND included -- must carry a pin label
   on the metal1 pin layer (18); power labels used to be missing entirely;
4. contacts and metal/poly shapes must respect the FreePDK45 minimum widths
   of the technology file the cell was compiled with.

All checks are pure GDS/netlist parsing (stdlib only) and run against the
committed artifacts, so they work on a fresh checkout without ASTRAN.
"""
import glob
import os
import re
import struct

import pytest

# GDS record types
UNITS, BOUNDARY, BOX, TEXT = 0x03, 0x08, 0x2D, 0x0C
LAYER, XY, ENDEL, STRING = 0x0D, 0x10, 0x11, 0x19

# tech_freePDK45.rul: MINSTEP 0.0025um -> internal unit 2.5nm; the GDS writer
# emits 2x internal coordinates, so one database unit is 1.25nm.
DBU_UM = 0.00125
MET1, POLY, CONT, PRB, MET1_PIN = 11, 9, 10, 235, 18
W1M1_UM, W2P1_UM, W2CT_UM = 0.065, 0.05, 0.065

REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def _gds_files():
    out = sorted(glob.glob(os.path.join(REPO_DIR, "pySrc", "outputs", "adder",
                                        "COMPLEX*.gds")))
    out += sorted(glob.glob(os.path.join(REPO_DIR, "pySrc",
                                         "originalAstranStdCells", "*.gds")))
    return out


GDS_FILES = _gds_files()


def _records(data):
    pos = 0
    while pos + 4 <= len(data):
        ln = int.from_bytes(data[pos:pos + 2], "big")
        if ln < 4:
            return
        yield data[pos + 2], data[pos + 4:pos + ln]
        pos += ln


def _xy_list(body):
    # each point is two 4-byte integers (x, y); read every int, not every
    # 8-byte window (single-point TEXT records hold just one pair)
    vals = [struct.unpack(">i", body[4 * k:4 * k + 4])[0]
            for k in range(len(body) // 4)]
    return list(zip(vals[0::2], vals[1::2]))


def parse_gds(path):
    """Return (units, boxes, labels).

    boxes: {layer: [(minx, miny, maxx, maxy), ...]} in database units
    labels: [(text, layer, x, y)]
    """
    units = None
    boxes = {}
    labels = []
    layer = None
    xy = None
    text = None
    in_text = False
    for rtype, body in _records(open(path, "rb").read()):
        if rtype == UNITS and len(body) == 16:
            units = (struct.unpack(">d", body[0:8])[0],
                     struct.unpack(">d", body[8:16])[0])
        elif rtype in (BOUNDARY, BOX, TEXT):
            layer, xy, text, in_text = None, None, None, (rtype == TEXT)
        elif rtype == LAYER and len(body) >= 2:
            layer = body[1]
        elif rtype == XY:
            xy = _xy_list(body)
        elif rtype == STRING:
            text = body.decode("ascii", "replace").rstrip("\0")
        elif rtype == ENDEL:
            if xy is not None and layer is not None:
                if in_text:
                    labels.append((text, layer, xy[0][0], xy[0][1]))
                else:
                    xs = [p[0] for p in xy]
                    ys = [p[1] for p in xy]
                    boxes.setdefault(layer, []).append(
                        (min(xs), min(ys), max(xs), max(ys)))
            layer, xy, text, in_text = None, None, None, False
    return units, boxes, labels


def _cell_size_from_log(log_path):
    for line in open(log_path, errors="replace"):
        if "Cell Size (W x H): " in line:
            w, h = line.split("Cell Size (W x H): ")[1].split(" x ")
            return float(w), float(h)
    return None


def _ports_from_netlist(sp_path, cell):
    for line in open(sp_path, errors="replace"):
        m = re.match(r"\.subckt\s+%s\s+(.*)" % re.escape(cell), line, re.I)
        if m:
            return m.group(1).split()
    return None


def test_gds_files_exist():
    assert len(GDS_FILES) >= 16, "committed GDS artifacts missing"


@pytest.mark.skipif(not GDS_FILES, reason="no committed GDS artifacts")
@pytest.mark.parametrize("path", GDS_FILES)
def test_units_record_declares_the_dbu_the_writer_uses(path):
    units, _, _ = parse_gds(path)
    assert units == pytest.approx((DBU_UM, DBU_UM * 1e-6), rel=1e-9), \
        os.path.basename(path)


@pytest.mark.skipif(not GDS_FILES, reason="no committed GDS artifacts")
@pytest.mark.parametrize("path", GDS_FILES)
def test_drawn_cell_size_matches_the_log(path):
    rel = os.path.basename(path)
    log = os.path.splitext(path)[0] + ".Astranlog"
    if not os.path.exists(log):
        pytest.skip("no log for %s" % rel)
    size = _cell_size_from_log(log)
    assert size, "no Cell Size line in %s" % log
    _, boxes, _ = parse_gds(path)
    assert PRB in boxes and len(boxes[PRB]) == 1, rel
    x0, y0, x1, y1 = boxes[PRB][0]
    w = (x1 - x0) * DBU_UM
    h = (y1 - y0) * DBU_UM
    assert w == pytest.approx(size[0], abs=1e-6), (
        "%s: GDS width %.4f vs log %.4f" % (rel, w, size[0]))
    assert h == pytest.approx(size[1], abs=1e-6), (
        "%s: GDS height %.4f vs log %.4f" % (rel, h, size[1]))


@pytest.mark.skipif(not GDS_FILES, reason="no committed GDS artifacts")
@pytest.mark.parametrize("path", GDS_FILES)
def test_every_port_including_power_is_labelled(path):
    name = os.path.splitext(os.path.basename(path))[0]
    if os.path.basename(os.path.dirname(path)) == "originalAstranStdCells":
        sp = os.path.join(REPO_DIR, "stdCelllib", "cellsAstranFriendly.sp")
    else:
        sp = os.path.splitext(path)[0] + ".sp"
    ports = _ports_from_netlist(sp, name)
    assert ports, "no .subckt %s found in %s" % (name, sp)
    _, _, labels = parse_gds(path)
    # ASTRAN upper-cases net names internally, so the GDS text for port
    # "cl1#A" reads "CL1#A"; compare case-insensitively
    labelled = {text.upper() for text, layer, _, _ in labels}
    missing = [p for p in ports if p.upper() not in labelled]
    assert not missing, "%s: ports without a pin label: %s" % (name, missing)
    for text, layer, _, _ in labels:
        if text.upper() in {p.upper() for p in ports}:
            assert layer == MET1_PIN, (
                "%s: label %s sits on layer %d, expected metal1 pin %d"
                % (name, text, layer, MET1_PIN))


@pytest.mark.skipif(not GDS_FILES, reason="no committed GDS artifacts")
@pytest.mark.parametrize("path", GDS_FILES)
def test_contact_and_metal_widths_meet_the_technology_rules(path):
    rel = os.path.basename(path)
    _, boxes, _ = parse_gds(path)
    for (x0, y0, x1, y1) in boxes.get(CONT, []):
        w = (x1 - x0) * DBU_UM
        assert w == pytest.approx(W2CT_UM, abs=1e-9), (
            "%s: contact width %.4f" % (rel, w))
    for layer, min_um, what in ((MET1, W1M1_UM, "metal1"),
                                (POLY, W2P1_UM, "poly")):
        for (x0, y0, x1, y1) in boxes.get(layer, []):
            w, h = (x1 - x0) * DBU_UM, (y1 - y0) * DBU_UM
            assert min(w, h) >= min_um - 1e-9, (
                "%s: %s shape %.4f x %.4f below minimum %.4f"
                % (rel, what, w, h, min_um))
