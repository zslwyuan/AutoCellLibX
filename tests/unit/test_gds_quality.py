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
   of the technology file the cell was compiled with;
5. the compaction "spacing repair" loop must converge to zero violating pairs
   (its keep-away constraints each need their own big-M relaxation term, or
   the re-solve is infeasible and the loop spins without ever fixing a pair);
6. metal shapes belonging to *different* nets must respect the S1M1M1 corner
   spacing.

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
# stream numbers follow the GSCL45 map (stdCelllib/gds2_encounter.map):
# metal1 drawing and metal1 pin are both 49; poly 9, contact 10, pr_boundary 235
MET1, POLY, CONT, PRB, MET1_PIN = 49, 9, 10, 235, 49
W1M1_UM, W2P1_UM, W2CT_UM = 0.065, 0.05, 0.065
# same-layer spacing from tech_freePDK45.rul (um)
S1M1M1_UM, S1P1P1_UM = 0.065, 0.075

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


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _met1_components(boxes):
    """Group MET1 shapes into nets via the MET1-CONT-POLY overlap graph.

    Returns [(net_root, box), ...] for every MET1 box: two boxes are on the
    same net iff they share a root.  Used to tell a legal same-net merge from a
    spacing violation between two different nets.
    """
    shapes = ([(MET1, b) for b in boxes.get(MET1, [])] +
              [(CONT, b) for b in boxes.get(CONT, [])] +
              [(POLY, b) for b in boxes.get(POLY, [])])
    n = len(shapes)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    touching = {frozenset(p) for p in
                ((MET1, MET1), (MET1, CONT), (CONT, POLY), (POLY, POLY))}
    for i in range(n):
        for j in range(i + 1, n):
            if (frozenset((shapes[i][0], shapes[j][0])) in touching and
                    _overlap(shapes[i][1], shapes[j][1])):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    return [(find(i), shapes[i][1]) for i in range(n) if shapes[i][0] == MET1]


@pytest.mark.skipif(not GDS_FILES, reason="no committed GDS artifacts")
@pytest.mark.parametrize("path", GDS_FILES)
def test_spacing_repair_loop_converged(path):
    # The compaction repair loop only rewrites the layout when a pass reports
    # violations, so a non-zero final count means the exported cell still
    # breaks a spacing rule.  This is what a missing big-M term in the
    # keep-away constraints used to cause: the re-solve was infeasible, so the
    # loop spun to its pass budget without ever fixing a pair.
    log = os.path.splitext(path)[0] + ".Astranlog"
    if not os.path.exists(log):
        pytest.skip("no log for %s" % os.path.basename(path))
    passes = [(int(m.group(1)), int(m.group(2)))
              for m in (re.match(r"-> Spacing repair pass (\d+): (\d+) violating", l)
                        for l in open(log, errors="replace")) if m]
    assert passes, "%s: no spacing repair pass recorded" % os.path.basename(path)
    last_pass, violations = passes[-1]
    assert violations == 0, (
        "%s: repair loop stopped at pass %d with %d violating pair(s)"
        % (os.path.basename(path), last_pass, violations))


@pytest.mark.skipif(not GDS_FILES, reason="no committed GDS artifacts")
@pytest.mark.parametrize("path", GDS_FILES)
def test_different_net_metal_spacing_meets_the_rule(path):
    rel = os.path.basename(path)
    _, boxes, _ = parse_gds(path)
    items = _met1_components(boxes)
    rule = S1M1M1_UM / DBU_UM
    offenders = []
    for i in range(len(items)):
        ci, a = items[i]
        for j in range(i + 1, len(items)):
            cj, b = items[j]
            if ci == cj:
                continue
            dx = max(a[0], b[0]) - min(a[2], b[2])
            dy = max(a[1], b[1]) - min(a[3], b[3])
            if dx < 0 and dy < 0:
                continue  # overlapping: same net merged by abutting shapes
            cdx, cdy = max(dx, 0), max(dy, 0)
            if cdx * cdx + cdy * cdy < rule * rule:
                offenders.append((a, b, dx, dy))
    assert not offenders, (
        "%s: %d metal pair(s) closer than S1M1M1, e.g. %s"
        % (rel, len(offenders), offenders[0]))
