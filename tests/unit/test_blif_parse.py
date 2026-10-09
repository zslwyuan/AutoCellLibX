"""Unit tests for liberty/BLIF parsing and graph construction."""
from blif_preproc import load_liberty_file, gen_graph_from_liberty_and_blif


def test_load_liberty_library(in_pysrc):
    lib = load_liberty_file("../stdCelllib/gscl45nm.lib")
    assert "NAND2X1" in lib
    assert lib["NAND2X1"].input_pins, "NAND2X1 must have input pins"
    assert lib["NAND2X1"].output_pins, "NAND2X1 must have an output pin"
    # every cell must have at least one output
    for name, t in lib.items():
        assert t.output_pins or t.input_pins, name


def test_graph_construction_on_adder(in_pysrc):
    G, cells, netlist, types = gen_graph_from_liberty_and_blif(
        "../stdCelllib/gscl45nm.lib", "../benchmark/blif/adder.blif")

    assert len(cells) == 710
    assert G.number_of_nodes() == len(cells)
    assert G.number_of_edges() > 0
    assert len(types) > 5

    # nodes carry a type and a name
    for n in list(G.nodes())[:10]:
        assert G.nodes[n]["type"]
        assert "name" in G.nodes[n]
        assert G.nodes[n]["node_label"] == -1


def test_edge_direction_follows_signal_flow(in_pysrc):
    G, cells, netlist, types = gen_graph_from_liberty_and_blif(
        "../stdCelllib/gscl45nm.lib", "../benchmark/blif/adder.blif")
    # every edge (u, v) must correspond to u driving an input net of v
    for u, v in list(G.edges())[:200]:
        assert any(net.pred_cell is cells[u] for net in cells[v].input_nets)


def test_bypass_types_are_marked(in_pysrc):
    from global_variables import bypass_types

    G, cells, netlist, types = gen_graph_from_liberty_and_blif(
        "../stdCelllib/gscl45nm.lib", "../benchmark/blif/adder.blif")
    for cell in cells:
        expected = any(k in cell.std_cell_type.type_name for k in bypass_types)
        assert cell.stop_type == expected
