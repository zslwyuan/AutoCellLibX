"""Unit tests for pySrc/smt_cell_placer.py (P2 stage 4 reference impl)."""
import pytest

from smt_cell_placer import (DEFAULT_GRID_UM, astran_width_from_log,
                             build_smt_model, compare_with_astran,
                             find_series_chains, parse_spice_subckt, place_cell)

NAND2_SP = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.end
"""

FOLD_SP = """\
.subckt FOLD Y GND
MnA Y A n1 GND NMOS W=1.6u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.end
"""


def test_parse_spice_subckt():
    nl = parse_spice_subckt(NAND2_SP)
    assert nl.subckt_name == "NAND2"
    assert set(nl.ports) == {"VCC", "Y", "A", "B", "GND"}
    assert len(nl.devices) == 4
    assert {d.name for d in nl.devices} == {"MpA", "MpB", "MnA", "MnB"}
    assert nl.devices[0].is_p and not nl.devices[2].is_p
    assert nl.devices[0].width_um == pytest.approx(0.5)


def test_parse_rejects_bad_input():
    with pytest.raises(ValueError):
        parse_spice_subckt("no subckt here\n")


def test_find_series_chains_nand2():
    nl = parse_spice_subckt(NAND2_SP)
    chains = find_series_chains(nl)
    nmos = [c for c in chains if c[0].name.startswith("Mn")]
    assert len(nmos) == 1 and len(nmos[0]) == 2
    assert [d.name for d in nmos[0]] == ["MnA", "MnB"]     # walking order
    pmos = [c for c in chains if c[0].name.startswith("Mp")]
    assert len(pmos) == 2 and all(len(c) == 1 for c in pmos)


def _check_validity(result, netlist):
    """Re-derive intervals: no overlap within a (polarity, row), chain
    members share a row and abut."""
    placed = {d.name: d for d in result.devices}
    rows = {"P": {}, "N": {}}
    for d in result.devices:
        rows["P" if d.is_p else "N"].setdefault(d.row, []).append(d)
    for polarity, by_row in rows.items():
        for row, devs in by_row.items():
            devs.sort(key=lambda d: d.start_col)
            for a, b in zip(devs, devs[1:]):
                assert a.end_col <= b.start_col, (polarity, row, a.name, b.name)
    for chain in find_series_chains(netlist):
        for a, b in zip(chain, chain[1:]):
            assert placed[a.name].row == placed[b.name].row, chain
            assert placed[a.name].end_col == placed[b.name].start_col, chain
    for d in result.devices:
        assert d.end_col - d.start_col == d.legs * d.leg_width_cols, d.name


def test_solve_nand2_minimal_width(tmp_path):
    """NAND2: both rows need 6 cols (3+3) -> provably optimal width 6."""
    sp = tmp_path / "nand2.sp"
    sp.write_text(NAND2_SP)
    result = place_cell(str(sp), time_limit_s=10)
    assert result.status_name == "OPTIMAL"
    assert result.width_cols == 6
    assert result.width_um == pytest.approx(6 * DEFAULT_GRID_UM)
    _check_validity(result, parse_spice_subckt(NAND2_SP))
    assert all(d.legs == 1 for d in result.devices)


def test_folding_obeys_manufacturing_leg_cap(tmp_path):
    """1.6um NMOS cannot stay a single leg (cap 1.0um) -> folds into 2x4."""
    sp = tmp_path / "fold.sp"
    sp.write_text(FOLD_SP)
    result = place_cell(str(sp), time_limit_s=10)
    assert result.status_name == "OPTIMAL"
    by_name = {d.name: d for d in result.devices}
    assert by_name["MnA"].legs == 2 and by_name["MnA"].leg_width_cols == 4
    assert by_name["MnB"].legs == 1 and by_name["MnB"].leg_width_cols == 3
    assert result.width_cols == 11            # 4+4+3 chain, 0 P-side
    _check_validity(result, parse_spice_subckt(FOLD_SP))


def test_place_cell_is_deterministic(tmp_path):
    sp = tmp_path / "nand2.sp"
    sp.write_text(NAND2_SP)
    a = place_cell(str(sp), time_limit_s=10)
    b = place_cell(str(sp), time_limit_s=10)
    assert a.as_dict() == b.as_dict()


def test_astran_width_from_log(tmp_path):
    log = tmp_path / "C0.Astranlog"
    log.write_text("-> Cell Size (W x H): 2.28 x 2.47\n")
    assert astran_width_from_log(str(log)) == pytest.approx(2.28)
    assert astran_width_from_log(str(tmp_path / "missing.log")) is None


def test_compare_with_astran(tmp_path):
    sp = tmp_path / "C0.sp"
    sp.write_text(NAND2_SP)
    log = tmp_path / "C0.Astranlog"
    log.write_text("-> Cell Size (W x H): 2.28 x 2.47\n")
    row = compare_with_astran(str(sp), str(log), time_limit_s=10)
    assert row["cell"] == "C0"
    assert row["astran_width_um"] == pytest.approx(2.28)
    assert row["smt_width_um"] == pytest.approx(6 * DEFAULT_GRID_UM)
    assert row["ratio"] == pytest.approx(6 * DEFAULT_GRID_UM / 2.28)
