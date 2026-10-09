"""Shim (ARCHITECTURE): the SPICE reader (SPSubcircuit,
load_spice_subcircuits) lives in core/parse; this module keeps the
netlist exporter (export_spice_netlist).
"""

from core.parse import SPSubcircuit, load_spice_subcircuits

import sys
import os
from matplotlib.pyplot import text
def export_spice_netlist(cluster_seq, subckts, merge_cell_type_id,  output_dir):

    cells_in_cluster = cluster_seq.pattern_clusters[0].cells
    spice_list = []
    cell_to_order_id = dict()

    # rename signals and transistors
    for order_id, cell in enumerate(cells_in_cluster):
        spice_list.append(SPSubcircuit(
            subckts[cell.std_cell_type.type_name].texts))
        spice_list[-1].rename_prefix("cl"+str(order_id)+"#")
        cell_to_order_id[cell] = order_id

    # connect each input pins of each subcircuit
    for order_id, cur_cell in enumerate(cells_in_cluster):
        for input_net, input_pin_name in zip(cur_cell.input_nets, cur_cell.input_pin_ref_names):
            pred_cell = input_net.pred_cell
            pred_pin_name = input_net.pred_pin
            if (pred_cell in cell_to_order_id.keys()):
                spice_list[order_id].replace_input_pin(
                    "cl"+str(order_id)+"#"+input_pin_name, "cl"+str(cell_to_order_id[pred_cell])+"#"+pred_pin_name)

    # merge spice netlists
    # A dict is used as an insertion-ordered set.  A plain set iterates in hash
    # order, which changes between processes (PYTHONHASHSEED), so the exported
    # netlist -- and with it the layout cache key -- was different on every run.
    interface_set = {}
    internal_signals = []
    for spice_obj in spice_list:
        for pin in spice_obj.interfaces:
            interface_set[pin] = None
        internal_signals = internal_signals + spice_obj.internal_signals

    # remove internal signals from interfaces
    for order_id, cur_cell in enumerate(cells_in_cluster):
        for output_net, output_pin_name in zip(cur_cell.output_nets, cur_cell.output_pin_ref_names):
            all_succ_cells_internal = True
            for succ_cell in output_net.succ_cells:
                if (not succ_cell in cell_to_order_id.keys()):
                    all_succ_cells_internal = False
            if (all_succ_cells_internal):
                assert("cl"+str(order_id)+"#"+output_pin_name in interface_set)
                del interface_set["cl"+str(order_id)+"#"+output_pin_name]

    merge_cell_name = "COMPLEX"+str(merge_cell_type_id)
    interface_list = list(interface_set)
    first_line = ".subckt "+merge_cell_name+" " + " ".join(interface_list)
    internal_lines = [first_line]
    for ele in spice_list:
        internal_lines = internal_lines + ele.texts[1:-1]
    last_line = ".ends "+merge_cell_name

    internal_lines.append(last_line)
    internal_lines.append("* pattern code: "+cluster_seq.pattern_extension_trace)
    internal_lines.append(
        "* "+str(len(cluster_seq.pattern_clusters))+" occurrences in design ")
    internal_lines.append(
        "* each contains "+str(len(cells_in_cluster))+" cells")
    internal_lines.append(
        "* Example occurence:")
    for cell in cells_in_cluster:
        internal_lines.append("*   "+cell.name)

    # Write only when the content actually changes, so the netlist's mtime is a
    # reliable "inputs changed" signal for the layout cache in main.py.
    content = '\n'.join(internal_lines) + '\n'
    sp_path = output_dir+"/"+merge_cell_name+'.sp'
    if ((not os.path.exists(sp_path)) or (open(sp_path).read() != content)):
        out_fh = open(sp_path, 'w')
        out_fh.write(content)
        out_fh.close()
