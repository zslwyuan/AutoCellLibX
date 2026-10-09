"""Unit tests for GDS area readers (pySrc/gds_analysis.py)."""
from gds_analysis import loadOrignalGSCL45nmGDS, loadAstranGDS


def test_gscl_area_reader(in_pysrc):
    areas = loadOrignalGSCL45nmGDS()
    assert len(areas) >= 30
    assert "INVX1" in areas and "NAND2X1" in areas
    for name, a in areas.items():
        assert a > 0, name


def test_astran_area_reader(in_pysrc):
    areas = loadAstranGDS()
    assert len(areas) > 0
    for name, a in areas.items():
        assert a > 0, name


def test_astran_cells_are_smaller_than_design(in_pysrc):
    """Sanity: individual cell footprints are far below the whole-design area."""
    from blif_preproc import loadDataAndPreprocess, getArea

    G, cells, netlist, types, ds, ml, seqs, cn = loadDataAndPreprocess(
        libFileName="../stdCelllib/gscl45nm.lib",
        blifFileName="../benchmark/blif/adder.blif", startTime=0)
    type2area = loadAstranGDS()
    total = getArea(cells, type2area)
    assert total > 0
    assert max(type2area.values()) < total
