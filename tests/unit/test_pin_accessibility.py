"""Unit tests for pySrc/pin_accessibility.py."""
import gdstk
import pytest

from pin_accessibility import cell_pin_accessibility, load_cell_geometry


def _writeSyntheticGds(path):
    """5 metal1 pins (A-C on-grid, D/E same column), one poly crossing B."""
    cell = gdstk.Cell("T")
    cell.add(gdstk.rectangle((0, 0), (3.04, 2.47), layer=235))       # outline
    cell.add(gdstk.rectangle((0.38, 1.0), (0.76, 1.4), layer=49))    # A
    cell.add(gdstk.Label("A", origin=(0.57, 1.2), layer=49))
    cell.add(gdstk.rectangle((0.95, 1.0), (1.33, 1.4), layer=49))    # B
    cell.add(gdstk.Label("B", origin=(1.14, 1.2), layer=49))
    cell.add(gdstk.rectangle((1.52, 1.0), (1.90, 1.4), layer=49))    # C
    cell.add(gdstk.Label("C", origin=(1.71, 1.2), layer=49))
    cell.add(gdstk.rectangle((2.09, 0.2), (2.47, 0.6), layer=49))    # D
    cell.add(gdstk.Label("D", origin=(2.28, 0.4), layer=49))
    cell.add(gdstk.rectangle((2.09, 1.9), (2.47, 2.3), layer=49))    # E
    cell.add(gdstk.Label("E", origin=(2.28, 2.1), layer=49))
    cell.add(gdstk.rectangle((0.9, 0.7), (1.4, 1.8), layer=9))       # poly
    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    lib.add(cell)
    lib.write_gds(path)


def test_synthetic_pin_scores(tmp_path):
    gds = str(tmp_path / "T.gds")
    _writeSyntheticGds(gds)
    rep = cell_pin_accessibility(gds, grid_um=0.19)
    assert rep.units_per_um == 1.0            # sane header trusted
    by_pin = {p["pin"]: p for p in rep.pins}
    assert set(by_pin) == {"A", "B", "C", "D", "E"}
    assert by_pin["A"]["score"] == pytest.approx(1.0)   # on grid, free
    assert by_pin["B"]["score"] == pytest.approx(0.5)   # on grid, poly-blocked
    assert by_pin["C"]["score"] == pytest.approx(1.0)
    assert by_pin["D"]["score"] == pytest.approx(0.9)   # crowded with E
    assert by_pin["E"]["score"] == pytest.approx(0.9)
    assert rep.score == pytest.approx(0.86)


def test_synthetic_is_deterministic(tmp_path):
    gds = str(tmp_path / "T.gds")
    _writeSyntheticGds(gds)
    a = cell_pin_accessibility(gds, grid_um=0.19).as_dict()
    b = cell_pin_accessibility(gds, grid_um=0.19).as_dict()
    assert a == b


def test_offgrid_pin_loses_half_point(tmp_path):
    gds = str(tmp_path / "T.gds")
    _writeSyntheticGds(gds)
    # rebuild with an off-grid A
    cell = gdstk.Cell("T")
    cell.add(gdstk.rectangle((0, 0), (3.04, 2.47), layer=235))
    cell.add(gdstk.rectangle((0.48, 1.0), (0.86, 1.4), layer=49))    # off-grid
    cell.add(gdstk.Label("A", origin=(0.67, 1.2), layer=49))
    cell.add(gdstk.rectangle((0.95, 1.0), (1.33, 1.4), layer=49))
    cell.add(gdstk.Label("B", origin=(1.14, 1.2), layer=49))
    cell.add(gdstk.rectangle((1.52, 1.0), (1.90, 1.4), layer=49))
    cell.add(gdstk.Label("C", origin=(1.71, 1.2), layer=49))
    cell.add(gdstk.rectangle((2.09, 0.2), (2.47, 0.6), layer=49))
    cell.add(gdstk.Label("D", origin=(2.28, 0.4), layer=49))
    cell.add(gdstk.rectangle((2.09, 1.9), (2.47, 2.3), layer=49))
    cell.add(gdstk.Label("E", origin=(2.28, 2.1), layer=49))
    cell.add(gdstk.rectangle((0.9, 0.7), (1.4, 1.8), layer=9))
    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    lib.add(cell)
    off = str(tmp_path / "off.gds")
    lib.write_gds(off)
    rep2 = cell_pin_accessibility(off, grid_um=0.19)
    assert rep2.pins[0]["pin"] == "A"
    assert rep2.pins[0]["on_track"] is False
    assert rep2.pins[0]["score"] == pytest.approx(0.5)


def test_real_complex0_smoke(in_pysrc):
    rep = cell_pin_accessibility("outputs/adder/COMPLEX0.gds",
                               "outputs/adder/COMPLEX0.Astranlog",
                               grid_um=0.19)
    assert 0.0 <= rep.score <= 1.0
    assert len(rep.pins) >= 5            # CL0#Y, CL1#A/B, CL2#A/B/Y, GND, VCC
    a = cell_pin_accessibility("outputs/adder/COMPLEX0.gds",
                             "outputs/adder/COMPLEX0.Astranlog",
                             grid_um=0.19).as_dict()
    b = cell_pin_accessibility("outputs/adder/COMPLEX0.gds",
                             "outputs/adder/COMPLEX0.Astranlog",
                             grid_um=0.19).as_dict()
    assert a == b


def test_load_geometry_calibrates_from_log(tmp_path):
    gds = str(tmp_path / "T.gds")
    _writeSyntheticGds(gds)
    polys, labels, units = load_cell_geometry(gds)
    assert units == 1.0
    assert len(labels) == 5 and all(l[0] == 49 for l in labels)
    assert len(polys) == 7
