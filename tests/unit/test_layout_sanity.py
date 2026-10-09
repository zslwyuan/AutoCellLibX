"""Unit tests for pySrc/layout_sanity.py (P2 phase 0)."""
import gdstk
import pytest

from layout_sanity import (ASTRAN_GDS_UNITS_PER_UM, DEFAULT_LAYERS,
                           checkLayout)

U = ASTRAN_GDS_UNITS_PER_UM          # raw units per um (ASTRAN writes x2)


def _rect(cell, x0, y0, x1, y1, layer):
    cell.add(gdstk.rectangle((x0, y0), (x1, y1), layer=layer))


def _write_cell(path, height_um=2.47, width_um=3.8, labels=("VCC", "GND"),
                layers=(1, 9, 49)):
    lib = gdstk.Library("t")
    cell = lib.new_cell("C0")
    for layer in layers:
        if layer == 49:
            # metal1 spans the full row height and the cell width
            _rect(cell, 0, 0, width_um * U, height_um * U, layer)
        else:
            _rect(cell, 0.5 * U, 0.5 * U, 1.0 * U, 1.0 * U, layer)
    for i, text in enumerate(labels):
        cell.add(gdstk.Label(text, (i * U, 0.1 * U), layer=49))
    lib.write_gds(str(path))


def test_good_cell_passes(tmp_path):
    gds = tmp_path / "C0.gds"
    _write_cell(gds)
    report = checkLayout(str(gds))
    assert report.ok(), report.asDict()
    assert report.metrics["height_um"] == pytest.approx(2.47)
    assert report.metrics["width_um"] == pytest.approx(3.8)


def test_degenerate_cell_fails(tmp_path):
    lib = gdstk.Library("t")
    lib.new_cell("EMPTY")
    gds = tmp_path / "EMPTY.gds"
    lib.write_gds(str(gds))
    report = checkLayout(str(gds))
    assert not report.ok()
    assert any(code == "degenerate" for code, _ in report.violations)


def test_wrong_height_fails(tmp_path):
    gds = tmp_path / "C0.gds"
    _write_cell(gds, height_um=4.94)        # double-height, not the row
    report = checkLayout(str(gds))
    codes = [c for c, _ in report.violations]
    assert "height" in codes


def test_missing_label_fails(tmp_path):
    gds = tmp_path / "C0.gds"
    _write_cell(gds, labels=("GND",))
    report = checkLayout(str(gds))
    codes = [c for c, _ in report.violations]
    assert "labels" in codes


def test_missing_layer_fails(tmp_path):
    gds = tmp_path / "C0.gds"
    _write_cell(gds, layers=(9, 49))        # no active
    report = checkLayout(str(gds))
    codes = [c for c, _ in report.violations]
    assert "layers" in codes


def test_missing_file_fails(tmp_path):
    report = checkLayout(str(tmp_path / "nope.gds"))
    assert not report.ok()


@pytest.mark.parametrize("cell", ["COMPLEX0", "COMPLEX1", "COMPLEX9"])
def test_real_adder_layouts_are_sane(in_pysrc, cell):
    import os
    gds = "./outputs/adder/%s.gds" % cell
    if not os.path.exists(gds):
        pytest.skip("outputs snapshot not present")
    report = checkLayout(gds, logPath="./outputs/adder/%s.Astranlog" % cell)
    assert report.ok(), report.asDict()
