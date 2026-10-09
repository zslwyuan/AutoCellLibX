"""Unit tests for SPICE parsing/export (flow/spice.py)."""
import os

from spice import SPSubcircuit, load_spice_subcircuits, export_spice_netlist


def test_load_subcircuits(in_flow):
    subs = load_spice_subcircuits("../std_celllib/cellsAstranFriendly.sp")
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
    sp.rename_prefix("cl0#")
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
    sp.rename_prefix("cl1#")
    sp.replace_input_pin("cl1#A", "cl0#Y")
    joined = " ".join(sp.texts)
    assert "cl0#Y" in joined
    assert "cl1#A" not in joined


def test_export_spice_netlist(in_flow, tmp_path):
    from blif_preproc import load_data_and_preprocess
    from blif_graph_util import sort_pattern_cluster_seqs

    G, cells, netlist, types, ds, ml, seqs, cn = load_data_and_preprocess(
        lib_file_name="../std_celllib/gscl45nm.lib",
        blif_file_name="../benchmark/blif/adder.blif", start_time=0)
    seqs = sort_pattern_cluster_seqs(seqs)
    subs = load_spice_subcircuits("../std_celllib/cellsAstranFriendly.sp")

    export_spice_netlist(seqs[0], subs, 0, str(tmp_path))
    out = os.path.join(str(tmp_path), "COMPLEX0.sp")
    assert os.path.exists(out)

    text = open(out).read()
    assert text.startswith(".subckt COMPLEX0")
    assert ".ends COMPLEX0" in text
    assert "* pattern code: " in text


def test_export_spice_netlist_only_writes_on_change(in_flow, tmp_path):
    """An unchanged netlist must not be rewritten.

    main.py uses the netlist mtime to decide whether a cached ASTRAN layout is
    stale, so re-running the pipeline must not touch an unchanged .sp file.
    """
    from blif_preproc import load_data_and_preprocess
    from blif_graph_util import sort_pattern_cluster_seqs

    G, cells, netlist, types, ds, ml, seqs, cn = load_data_and_preprocess(
        lib_file_name="../std_celllib/gscl45nm.lib",
        blif_file_name="../benchmark/blif/adder.blif", start_time=0)
    seqs = sort_pattern_cluster_seqs(seqs)
    subs = load_spice_subcircuits("../std_celllib/cellsAstranFriendly.sp")

    out = os.path.join(str(tmp_path), "COMPLEX0.sp")
    export_spice_netlist(seqs[0], subs, 0, str(tmp_path))
    export_spice_netlist(seqs[0], subs, 0, str(tmp_path))

    # Backdate the file, then re-export identical content: it must be left alone.
    old = os.path.getmtime(out) - 100
    os.utime(out, (old, old))
    export_spice_netlist(seqs[0], subs, 0, str(tmp_path))
    assert os.path.getmtime(out) == old

    # Different content must be written through.
    seqs[0].pattern_extension_trace = seqs[0].pattern_extension_trace + "+X"
    export_spice_netlist(seqs[0], subs, 0, str(tmp_path))
    assert os.path.getmtime(out) != old
