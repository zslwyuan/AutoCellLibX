"""Unit tests for pySrc/pdk_config.py (P1-8)."""
import os

import pytest

import Astran
from pdk_config import (PdkProfile, getPdk, listPdks, loadTechnologyRul,
                        pdkGeometryDict)

_REQUIRED_LAYERS = ("CONT", "POLY", "NDIF", "PDIF", "NWEL", "PWEL",
                    "VIA1", "MET1", "MET2", "MET1P", "CELLBOX")


def test_freepdk45_matches_astran_constants():
    """The registry's validated profile must reproduce the constants in
    Astran.py bit for bit (AGENTS.md invariant 2 keeps one source of
    truth -- this test pins the sync)."""
    pdk = getPdk("freepdk45")
    assert pdk.cellsHeight == Astran.ASTRAN_CELLS_HEIGHT
    assert pdk.hGrid == Astran.ASTRAN_HGRID
    assert pdk.vGrid == Astran.ASTRAN_VGRID
    assert pdk.supplySize == Astran.ASTRAN_SUPPLY_SIZE
    assert pdk.cellTemplate == Astran.ASTRAN_CELL_TEMPLATE
    assert pdk.nwellPos == pytest.approx(Astran.ASTRAN_NWELL_POS)


def test_nwell_pos_is_always_half_row_height():
    for name in listPdks():
        pdk = getPdk(name, allowScaffold=True)
        assert pdk.nwellPos == pytest.approx(pdk.rowHeightUm / 2.0)


def test_geometry_dict_feeds_build_astran_commands():
    pdk = getPdk("freepdk45")
    script = Astran.buildAstranCommands(
        "gurobi", "tech.rul", "cell.sp", "C0", ".",
        geometry=pdkGeometryDict(pdk))
    default = Astran.buildAstranCommands(
        "gurobi", "tech.rul", "cell.sp", "C0", ".")
    assert script == default            # validated profile == defaults
    assert 'set nwellpos 1.235' in script
    assert 'set celltemplate "Tapless"' in script


def test_draft_pdks_require_opt_in():
    for name, status in listPdks().items():
        if status == "validated":
            continue
        with pytest.raises(RuntimeError):
            getPdk(name)
        pdk = getPdk(name, allowScaffold=True)
        assert pdk.rowHeightUm > 0


def test_second_pdk_geometry_matches_verified_lef():
    """Corrected against primary LEF sources (2026-10-09): sky130 SITE
    unithd 0.46 x 2.72 (8 tracks x 0.34); gf180 SITE GF018hv5v_mcu_sc7
    0.56 x 3.92 (7 tracks x 0.56); rails 0.48 / 0.60."""
    sky = getPdk("sky130", allowScaffold=True)
    assert (sky.cellsHeight, sky.hGrid, sky.supplySize) == (8, 0.34, 0.48)
    assert sky.rowHeightUm == pytest.approx(2.72)
    gf = getPdk("gf180", allowScaffold=True)
    assert (gf.cellsHeight, gf.hGrid, gf.supplySize) == (7, 0.56, 0.60)
    assert gf.rowHeightUm == pytest.approx(3.92)


def test_second_pdk_rul_files_exist_and_parse():
    for name in ("sky130", "gf180"):
        pdk = getPdk(name, allowScaffold=True)
        assert os.path.exists(pdk.technologyRul), name
        tech = loadTechnologyRul(pdk.technologyRul)
        assert tech["techName"], name
        assert tech["minstep"] == pytest.approx(0.005), name
        assert tech["vdd"] == pytest.approx(1.8), name
        assert tech["mlayers"] >= 4, name
        for layer in _REQUIRED_LAYERS:
            assert layer in tech["layers"], (name, layer)
        # the layer map keeps the GSCL45 streams ASTRAN's writer expects
        assert tech["layers"]["MET1"][1] == 49, name


def test_unknown_pdk_raises():
    with pytest.raises(KeyError):
        getPdk("no-such-pdk")


def test_multi_row_variant_geometry():
    from pdk_config import multiRowVariant
    base = getPdk("freepdk45")
    dbl = multiRowVariant(base, 2)
    assert dbl.cellsHeight == 26
    assert dbl.rowHeightUm == pytest.approx(4.94)
    assert dbl.nwellPos == pytest.approx(2.47)     # equal wells at any H
    geom = pdkGeometryDict(dbl)
    script = Astran.buildAstranCommands(
        "g", "t", "n", "C0", ".", geometry=geom)
    assert "set rowheight 26" in script
    assert "set nwellpos 2.47" in script
