"""Unit tests for GDS area readers (pySrc/gds_analysis.py)."""
from gds_analysis import load_original_gscl45_gds, load_astran_gds


def test_gscl_area_reader(in_pysrc):
    areas = load_original_gscl45_gds()
    assert len(areas) >= 30
    assert "INVX1" in areas and "NAND2X1" in areas
    for name, a in areas.items():
        assert a > 0, name


def test_astran_area_reader(in_pysrc):
    areas = load_astran_gds()
    assert len(areas) > 0
    for name, a in areas.items():
        assert a > 0, name


def test_astran_cells_are_smaller_than_design(in_pysrc):
    """Sanity: individual cell footprints are far below the whole-design area."""
    from blif_preproc import load_data_and_preprocess, get_area

    G, cells, netlist, types, ds, ml, seqs, cn = load_data_and_preprocess(
        lib_file_name="../stdCelllib/gscl45nm.lib",
        blif_file_name="../benchmark/blif/adder.blif", start_time=0)
    type2area = load_astran_gds()
    total = get_area(cells, type2area)
    assert total > 0
    assert max(type2area.values()) < total
