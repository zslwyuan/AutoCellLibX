"""Parsing layer (core/parse): liberty / BLIF / SPICE readers.

Extracted verbatim (AST) from blif_preproc.py (load_liberty_file,
load_bool_gate_from_blif, gen_graph_from_liberty_and_blif) and spice.py
(SPSubcircuit, load_spice_subcircuits).  Orchestration helpers built on
top of parsing (load_data_and_preprocess, dataset conversion, get_area)
stay in the blif_preproc shim -- they are pipeline layers, not readers
(see doc/ARCHITECTURE.md).
"""

import os
import time
import networkx as nx
import blifparser.blifparser as blifparser
from liberty.parser import parse_liberty
from global_variables import *
from blif_graph_util import *


_liberty_cache = {}

def load_liberty_file(file_name):
    key = (os.path.abspath(file_name), os.path.getmtime(file_name))
    if key in _liberty_cache:
        # Shallow copy: callers may add bool-* gate types for their own BLIF
        # (load_bool_gate_from_blif), which must not leak into the shared cache.
        return dict(_liberty_cache[key])

    # Read and parse a library.
    library = parse_liberty(open(file_name).read())

    std_cell_lib = dict()

    # Loop through all cells.
    for cell_group in library.get_groups('cell'):
        name = str(cell_group.args[0]).replace(
            "\"", "").replace(" ", "").replace("\'", "")
        # print(name)
        new_std_cell_type = StdCellType(name)

        # Loop through all pins of the cell.
        for pin_group in cell_group.get_groups('pin'):
            pin_name = str(pin_group.args[0]).replace(
                "\"", "").replace("\'", "")
            # print(pin_name, "->", str(pin_group['direction']).replace("\"","").replace("\'",""))
            new_std_cell_type.add_pin(pin_name, str(
                pin_group['direction']).replace("\"", "").replace(" ", "").replace("\'", ""))

        std_cell_lib[name] = new_std_cell_type

    _liberty_cache[key] = std_cell_lib
    return std_cell_lib


def load_bool_gate_from_blif(blif, std_cell_lib):
    for bool_func in blif.booleanfunctions:
        truth_table_str = "bool-"+str(bool_func.truthtable)
        if (not truth_table_str in std_cell_lib.keys()):
            new_std_cell_type = StdCellType(truth_table_str)
            for i in range(0, len(bool_func.v_params)-1):
                new_std_cell_type.add_pin("IN"+str(i), 'input')
            new_std_cell_type.add_pin("OUT0", 'output')
            std_cell_lib[truth_table_str] = new_std_cell_type


def gen_graph_from_liberty_and_blif(lib_file_name, blif_file_name):

    std_cell_lib = load_liberty_file(lib_file_name)

    # get the file path and pass it to the parser
    filepath = os.path.abspath(blif_file_name)
    parser = blifparser.BlifParser(filepath)

    # get the object that contains the parsed data
    # from the parser
    blif = parser.blif
    load_bool_gate_from_blif(blif, std_cell_lib)

    # get the dictionary with the number of occurrencies of each keyword
    print(blif.nkeywords, "\n")

    cell_by_name = dict()
    cells = []
    net_by_name = dict()
    nets = []
    id_cnt = 0
    for tmp_circuit in blif.subcircuits:
        ref_type = tmp_circuit.modelname
        if (ref_type in std_cell_lib.keys()):
            name = str(tmp_circuit)
            cur_cell = DesignCell(id_cnt, name, std_cell_lib[ref_type])
            id_cnt += 1
            for pin in tmp_circuit.params:
                pin_info = pin.split("=")
                if (len(pin_info) != 2):
                    raise ValueError(
                        "malformed pin mapping %r in .subckt instance %r "
                        "(expected PIN=net)" % (pin, name))
                cur_cell.add_cell_pin(pin_info[0], pin_info[1])
            cell_by_name[name] = cur_cell
            cells.append(cur_cell)
        else:
            # An assert(False) is stripped under `python -O`; fail loudly
            # instead of building a graph with silently dropped instances.
            raise ValueError(
                "cell type %r of instance %r is not in the liberty file %s"
                % (ref_type, str(tmp_circuit), lib_file_name))

    for logic_gate in blif.booleanfunctions:
        ref_type = "bool-"+str(logic_gate.truthtable)
        if (ref_type in std_cell_lib.keys()):
            name = str(logic_gate)
            cur_cell = DesignCell(id_cnt, name, std_cell_lib[ref_type])
            id_cnt += 1
            if (len(logic_gate.v_params) > 1):
                for pin_id, pin in enumerate(logic_gate.v_params[:-1]):
                    cur_cell.add_cell_pin("IN"+str(pin_id), pin)
            cur_cell.add_cell_pin("OUT", logic_gate.v_params[-1])
            cell_by_name[name] = cur_cell
            cells.append(cur_cell)
        else:
            raise ValueError(
                "boolean-gate type %r is not in the liberty file %s"
                % (ref_type, lib_file_name))

    id_cnt = 0
    cells_by_type = dict()
    for design_cell in cells:
        if (not design_cell.std_cell_type.type_name in cells_by_type.keys()):
            cells_by_type[design_cell.std_cell_type.type_name] = []
        cells_by_type[design_cell.std_cell_type.type_name].append(design_cell)
        for ref_pin, input_net in zip(design_cell.input_pin_ref_names, design_cell.input_net_names):
            if (not input_net in net_by_name.keys()):
                cur_net = DesignNet(id_cnt, input_net)
                net_by_name[input_net] = cur_net
                nets.append(cur_net)
                id_cnt += 1
            else:
                cur_net = net_by_name[input_net]
            design_cell.add_input_net(cur_net)
            cur_net.add_pin(ref_pin, design_cell, True)
        for ref_pin, output_net in zip(design_cell.output_pin_ref_names, design_cell.output_net_names):
            if (not output_net in net_by_name.keys()):
                cur_net = DesignNet(id_cnt, output_net)
                net_by_name[output_net] = cur_net
                nets.append(cur_net)
                id_cnt += 1
            else:
                cur_net = net_by_name[output_net]
            design_cell.add_output_net(cur_net)
            cur_net.add_pin(ref_pin, design_cell, False)

    count_by_type = []
    for key in cells_by_type.keys():
        count_by_type.append((key, len(cells_by_type[key])))
    sorted_by_second = sorted(count_by_type, key=lambda tup: -tup[1])
    print("top std cell types: ", sorted_by_second[1:30])

    std_cell_types_for_feature = []
    for tmp_type in sorted_by_second:
        std_cell_types_for_feature.append(tmp_type[0])
    print("top std cell type names: ", std_cell_types_for_feature)

    print("creating networkx graph with ", len(cells), " nodes")
    blif_graph = nx.DiGraph()
    node_type = dict()
    netlist = []
    for design_cell in cells:
        if (design_cell.std_cell_type.type_name in std_cell_types_for_feature):
            node_type[design_cell.id] = design_cell.std_cell_type.type_name
        else:
            node_type[design_cell.id] = "minor_type"
        blif_graph.add_node(
            design_cell.id, type=node_type[design_cell.id], node_label=-1, name=design_cell.name)

        for input_net in design_cell.input_nets:
            if (not input_net.pred_cell is None):
                netlist.append((input_net.pred_cell.id, design_cell.id))

        for output_net in design_cell.output_nets:
            if (len(output_net.succ_cells) < 10000):
                for succ_cell in output_net.succ_cells:
                    netlist.append((design_cell.id, succ_cell.id))

    blif_graph.add_edges_from(netlist)
    print("created networkx graph with ", len(cells), " nodes")

    for cell in cells:
        for tmp_type in bypass_types:
            if (cell.std_cell_type.type_name.find(tmp_type) >= 0):
                cell.stop_type = True

    return blif_graph, cells, netlist, std_cell_types_for_feature


class SPSubcircuit(object):
    def __init__(self, texts):
        self.name = texts[0].split(" ")[1]
        self.interfaces = []
        self.internal_signals = []
        self.texts = [line.replace('\n', '') for line in texts]

        # Parse the interface names from the newline-normalised header; using
        # the raw ``texts[0]`` left a trailing "\n" on the last pin name.
        for interface in self.texts[0].split(" ")[2:]:
            self.interfaces.append(interface)

        for line in self.texts[1:-1]:
            if (line.find('M') == 0):
                eles = line.split(' ')[1:5]
                for ele in eles:
                    if ((not ele in self.interfaces) and (not ele in self.internal_signals)):
                        self.internal_signals.append(ele)

    def add_interface(self, if_name):
        self.interfaces.append(if_name)

    def add_internal_signal(self, inner_name):
        self.internal_signals.append(inner_name)

    def rename_prefix(self, prefix):
        for signal in self.interfaces+self.internal_signals:
            if (signal == 'VCC' or signal == 'GND'):
                continue
            for i in range(0, len(self.texts)):
                eles = self.texts[i].split(" ")
                for j in range(0, len(eles)):
                    if (eles[j] == signal):
                        eles[j] = prefix+signal
                self.texts[i] = ' '.join(eles)

        for i in range(0, len(self.interfaces)):
            if (self.interfaces[i] == 'VCC' or self.interfaces[i] == 'GND'):
                continue
            self.interfaces[i] = prefix+self.interfaces[i]

        for i in range(0, len(self.internal_signals)):
            if (self.internal_signals[i] == 'VCC' or self.internal_signals[i] == 'GND'):
                continue
            self.internal_signals[i] = prefix+self.internal_signals[i]

        for i in range(0, len(self.texts)):
            eles = self.texts[i].split(" ")
            if (len(eles) > 0):
                if (eles[0].find('M') == 0):
                    eles[0] = 'M'+prefix+eles[0][1:]
                self.texts[i] = ' '.join(eles)

    def replace_input_pin(self, orig_pin_name, new_pin_name):
        replaced = False
        for i in range(0, len(self.texts)):
            eles = self.texts[i].split(" ")
            for j in range(0, len(eles)):
                if (eles[j] == orig_pin_name):
                    eles[j] = new_pin_name
                    replaced = True
            self.texts[i] = ' '.join(eles)
        assert(replaced)
        for i in range(0, len(self.interfaces)):
            if (self.interfaces[i] == 'VCC' or self.interfaces[i] == 'GND'):
                continue
            if (self.interfaces[i] == orig_pin_name):
                self.interfaces[i] = new_pin_name

    def print(self):
        for line in self.texts:
            print(line)


def load_spice_subcircuits(file_path):
    sp_file = open(file_path, 'r')
    lines = sp_file.readlines()

    spice_subcircuits = dict()

    line_id = 0
    while (line_id < len(lines)):
        if (lines[line_id].find(".subckt ") >= 0):
            begin_line_id = line_id
            while (lines[line_id].find(".ends ") < 0):
                line_id += 1
            end_line_id = line_id
            new_subckt = SPSubcircuit(lines[begin_line_id:end_line_id+1])
            spice_subcircuits[new_subckt.name] = new_subckt

        line_id += 1

    return spice_subcircuits
