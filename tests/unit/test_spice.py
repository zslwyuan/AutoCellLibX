"""Unit tests for SPICE parsing/export (pySrc/spice.py)."""
import os

from spice import SPSubcircuit, loadSpiceSubcircuits, exportSpiceNetlist


def test_load_subcircuits(in_pysrc):
    subs = loadSpiceSubcircuits("../stdCelllib/cellsAstranFriendly.sp")
    assert len(subs) > 20
    assert "AND2X1" in subs
    s = subs["AND2X1"]
    assert "Y" in s.interfaces
    assert "A" in s.interfaces and "B" in s.interfaces
    assert "VCC" in s.interfaces and "GND" in s.interfaces


def test_rename_prefix_keeps_power_nets():
    sp = SPSubcircuit([
        ".subckt INVX1 Y A VCC GND",
        "M0 Y A VCC VCC PMOS W=0.5u L=0.05u",
        ".ends INVX1",
    ])
    sp.renamePrefix("cl0#")
    joined = " ".join(sp.texts)
    assert "cl0#Y" in joined and "cl0#A" in joined
    assert "Mcl0#0" in joined
    # power/ground nets must not be renamed
    assert "cl0#VCC" not in joined
    assert "cl0#GND" not in joined


def test_replace_input_pin():
    sp = SPSubcircuit([
        ".subckt INVX1 Y A VCC GND",
        "M0 Y A VCC VCC PMOS W=0.5u L=0.05u",
        ".ends INVX1",
    ])
    sp.renamePrefix("cl1#")
    sp.replaceInputPin("cl1#A", "cl0#Y")
    joined = " ".join(sp.texts)
    assert "cl0#Y" in joined
    assert "cl1#A" not in joined


def test_export_spice_netlist(in_pysrc, tmp_path):
    from BLIFPreProc import loadDataAndPreprocess
    from BLIFGraphUtil import sortPatternClusterSeqs

    G, cells, netlist, types, ds, ml, seqs, cn = loadDataAndPreprocess(
        libFileName="../stdCelllib/gscl45nm.lib",
        blifFileName="../benchmark/blif/adder.blif", startTime=0)
    seqs = sortPatternClusterSeqs(seqs)
    subs = loadSpiceSubcircuits("../stdCelllib/cellsAstranFriendly.sp")

    exportSpiceNetlist(seqs[0], subs, 0, str(tmp_path))
    out = os.path.join(str(tmp_path), "COMPLEX0.sp")
    assert os.path.exists(out)

    text = open(out).read()
    assert text.startswith(".subckt COMPLEX0")
    assert ".ends COMPLEX0" in text
    assert "* pattern code: " in text
