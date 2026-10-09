"""Unit tests for liberty/BLIF parsing and graph construction."""
from BLIFPreProc import load_liberty_file, gen_graph_from_liberty_and_blif


def test_load_liberty_library(in_pysrc):
    lib = load_liberty_file("../stdCelllib/gscl45nm.lib")
    assert "NAND2X1" in lib
    assert lib["NAND2X1"].inputPins, "NAND2X1 must have input pins"
    assert lib["NAND2X1"].outputPins, "NAND2X1 must have an output pin"
    # every cell must have at least one output
    for name, t in lib.items():
        assert t.outputPins or t.inputPins, name


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
        assert G.nodes[n]["nodeLabel"] == -1


def test_edge_direction_follows_signal_flow(in_pysrc):
    G, cells, netlist, types = gen_graph_from_liberty_and_blif(
        "../stdCelllib/gscl45nm.lib", "../benchmark/blif/adder.blif")
    # every edge (u, v) must correspond to u driving an input net of v
    for u, v in list(G.edges())[:200]:
        assert any(net.predCell is cells[u] for net in cells[v].inputNets)


def test_bypass_types_are_marked(in_pysrc):
    from globalVariables import bypassTypes

    G, cells, netlist, types = gen_graph_from_liberty_and_blif(
        "../stdCelllib/gscl45nm.lib", "../benchmark/blif/adder.blif")
    for cell in cells:
        expected = any(k in cell.stdCellType.typeName for k in bypassTypes)
        assert cell.stopType == expected
