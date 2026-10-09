"""Unit tests for pySrc/pdk_config.py (P1-8)."""
import pytest

import Astran
from pdk_config import (PdkProfile, getPdk, listPdks, pdkGeometryDict)


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


def test_scaffold_pdks_require_opt_in():
    for name, status in listPdks().items():
        if status == "validated":
            continue
        with pytest.raises(RuntimeError):
            getPdk(name)
        pdk = getPdk(name, allowScaffold=True)
        assert pdk.rowHeightUm > 0


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
