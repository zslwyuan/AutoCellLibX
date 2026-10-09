"""Unit tests for flow/pdk_config.py (P1-8)."""
import os

import pytest

import astran
from pdk_config import (PdkProfile, get_pdk, list_pdks, load_technology_rul,
                        pdk_geometry_dict)

_REQUIRED_LAYERS = ("CONT", "POLY", "NDIF", "PDIF", "NWEL", "PWEL",
                    "VIA1", "MET1", "MET2", "MET1P", "CELLBOX")


def test_freepdk45_matches_astran_constants():
    """The registry's validated profile must reproduce the constants in
    astran.py bit for bit (AGENTS.md invariant 2 keeps one source of
    truth -- this test pins the sync)."""
    pdk = get_pdk("freepdk45")
    assert pdk.cells_height == astran.ASTRAN_CELLS_HEIGHT
    assert pdk.h_grid == astran.ASTRAN_HGRID
    assert pdk.v_grid == astran.ASTRAN_VGRID
    assert pdk.supply_size == astran.ASTRAN_SUPPLY_SIZE
    assert pdk.cell_template == astran.ASTRAN_CELL_TEMPLATE
    assert pdk.nwell_pos == pytest.approx(astran.ASTRAN_NWELL_POS)


def test_nwell_pos_is_always_half_row_height():
    for name in list_pdks():
        pdk = get_pdk(name, allow_scaffold=True)
        assert pdk.nwell_pos == pytest.approx(pdk.row_height_um / 2.0)


def test_geometry_dict_feeds_build_astran_commands():
    pdk = get_pdk("freepdk45")
    script = astran.build_astran_commands(
        "gurobi", "tech.rul", "cell.sp", "C0", ".",
        geometry=pdk_geometry_dict(pdk))
    default = astran.build_astran_commands(
        "gurobi", "tech.rul", "cell.sp", "C0", ".")
    assert script == default            # validated profile == defaults
    assert 'set nwellpos 1.235' in script
    assert 'set celltemplate "Tapless"' in script


def test_draft_pdks_require_opt_in():
    for name, status in list_pdks().items():
        if status == "validated":
            continue
        with pytest.raises(RuntimeError):
            get_pdk(name)
        pdk = get_pdk(name, allow_scaffold=True)
        assert pdk.row_height_um > 0


def test_second_pdk_geometry_matches_verified_lef():
    """Corrected against primary LEF sources (2026-10-09): sky130 SITE
    unithd 0.46 x 2.72 (8 tracks x 0.34); gf180 SITE GF018hv5v_mcu_sc7
    0.56 x 3.92 (7 tracks x 0.56); rails 0.48 / 0.60."""
    sky = get_pdk("sky130", allow_scaffold=True)
    assert (sky.cells_height, sky.h_grid, sky.supply_size) == (8, 0.34, 0.48)
    assert sky.row_height_um == pytest.approx(2.72)
    gf = get_pdk("gf180", allow_scaffold=True)
    assert (gf.cells_height, gf.h_grid, gf.supply_size) == (7, 0.56, 0.60)
    assert gf.row_height_um == pytest.approx(3.92)


def test_second_pdk_rul_files_exist_and_parse():
    for name in ("sky130", "gf180"):
        pdk = get_pdk(name, allow_scaffold=True)
        assert os.path.exists(pdk.technology_rul), name
        tech = load_technology_rul(pdk.technology_rul)
        assert tech["tech_name"], name
        assert tech["minstep"] == pytest.approx(0.005), name
        assert tech["vdd"] == pytest.approx(1.8), name
        assert tech["mlayers"] >= 4, name
        for layer in _REQUIRED_LAYERS:
            assert layer in tech["layers"], (name, layer)
        # the layer map keeps the GSCL45 streams ASTRAN's writer expects
        assert tech["layers"]["MET1"][1] == 49, name


def test_unknown_pdk_raises():
    with pytest.raises(KeyError):
        get_pdk("no-such-pdk")


def test_multi_row_variant_geometry():
    from pdk_config import multi_row_variant
    base = get_pdk("freepdk45")
    dbl = multi_row_variant(base, 2)
    assert dbl.cells_height == 26
    assert dbl.row_height_um == pytest.approx(4.94)
    assert dbl.nwell_pos == pytest.approx(2.47)     # equal wells at any H
    geom = pdk_geometry_dict(dbl)
    script = astran.build_astran_commands(
        "g", "t", "n", "C0", ".", geometry=geom)
    assert "set rowheight 26" in script
    assert "set nwellpos 2.47" in script
