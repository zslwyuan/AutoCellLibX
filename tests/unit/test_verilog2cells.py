"""Unit tests for flow/verilog2cells.py.

The end-to-end smoke test synthesises a toy module with the vendored
yosys (skipped when no yosys is available) and stops before ASTRAN --
that leg is covered by test_astran_queue.py's fake runner and by the
slow integration tier.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "flow"))

import verilog2cells as v2c        # noqa: E402
from yosys_import import find_yosys                     # noqa: E402

REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
GSCL_LIB = os.path.join(REPO, "std_celllib", "gscl45nm.lib")

TOY_V = """\
module toy(input a, input b, input c, output y, output z);
  wire n1;
  assign n1 = a ^ b;
  assign y = (n1 & c) | (a & ~c);
  assign z = n1 ^ c;
endmodule
"""


def test_parse_liberty_areas():
    areas = v2c.parse_liberty_areas(GSCL_LIB)
    assert abs(areas["XOR2X1"] - 4.693) < 1e-6
    assert abs(areas["INVX1"] - 1.4079) < 1e-6
    assert abs(areas["FAX1"] - 8.9167) < 1e-6
    # row height proxy used for widths
    assert abs(v2c.ROW_HEIGHT - 2.47) < 1e-9


@pytest.mark.skipif(find_yosys() is None, reason="no yosys executable")
def test_driver_end_to_end_without_astran(tmp_path):
    src = tmp_path / "toy.v"
    src.write_text(TOY_V)
    outdir = tmp_path / "out"
    rc = v2c.main([str(src), "--top", "toy", "--out", str(outdir),
                   "--skip-astran", "--no-png"])
    assert rc == 0

    report = (outdir / "report.md").read_text()
    assert "PASS" in report                       # equivalence evidence
    assert "**total**" in report

    blocks = sorted(outdir.glob("BLK*.sp"))
    assert blocks                                  # at least one block
    for sp in blocks:
        text = sp.read_text()
        # every transistor line starts with M (the ASTRAN parser contract)
        assert all(ln.startswith("M")
                   for ln in text.splitlines()
                   if ln and not ln.startswith((".", "*")))
    # gold/gate BLIF pair kept for auditing
    assert (outdir / "gold.blif").exists()
    assert (outdir / "gates.blif").exists()


@pytest.mark.skipif(find_yosys() is None, reason="no yosys executable")
def test_driver_progress_hook_and_cancel(tmp_path):
    src = tmp_path / "toy.v"
    src.write_text(TOY_V)
    outdir = tmp_path / "out"
    notes = []
    rc = v2c.main([str(src), "--top", "toy", "--out", str(outdir),
                   "--skip-astran", "--no-png"], on_note=notes.append)
    assert rc == 0
    assert any("synthesising" in n for n in notes)
    assert any("PASS" in n for n in notes)

    from astran_queue import CancelledError
    with pytest.raises(CancelledError):
        v2c.main([str(src), "--top", "toy", "--out", str(outdir),
                  "--skip-astran"], should_cancel=lambda: True)


def test_block_areas_use_measured_height_not_constant():
    from astran_queue import CellResult
    results = [
        CellResult(name="A", ok=True, width=2.0, height=3.04),   # 16x0.19
        CellResult(name="B", ok=True, width=1.0, height=None),   # log lacked H
        CellResult(name="C", ok=False, width=0.0, height=2.47),  # failed run
    ]
    areas = v2c.block_areas(results)
    assert abs(areas["A"] - 2.0 * 3.04) < 1e-9
    assert abs(areas["B"] - 1.0 * v2c.ROW_HEIGHT) < 1e-9         # fallback
    assert "C" not in areas
