"""Parsing layer (core/parse): liberty / BLIF / SPICE readers.

Extracted verbatim (AST) from BLIFPreProc.py (load_liberty_file,
load_bool_gate_from_blif, gen_graph_from_liberty_and_blif) and spice.py
(SPSubcircuit, load_spice_subcircuits).  Orchestration helpers built on
top of parsing (loadDataAndPreprocess, dataset conversion, getArea)
stay in the BLIFPreProc shim -- they are pipeline layers, not readers
(see doc/ARCHITECTURE.md).
"""

import os
import time
import networkx as nx
import blifparser.blifparser as blifparser
from liberty.parser import parse_liberty
from globalVariables import *
from BLIFGraphUtil import *


_liberty_cache = {}

def load_liberty_file(fileName):
    key = (os.path.abspath(fileName), os.path.getmtime(fileName))
    if key in _liberty_cache:
        # Shallow copy: callers may add bool-* gate types for their own BLIF
        # (load_bool_gate_from_blif), which must not leak into the shared cache.
        return dict(_liberty_cache[key])

    # Read and parse a library.
    library = parse_liberty(open(fileName).read())

    stdCellLib = dict()

    # Loop through all cells.
    for cell_group in library.get_groups('cell'):
        name = str(cell_group.args[0]).replace(
            "\"", "").replace(" ", "").replace("\'", "")
        # print(name)
        newStdCellType = StdCellType(name)

        # Loop through all pins of the cell.
        for pin_group in cell_group.get_groups('pin'):
            pin_name = str(pin_group.args[0]).replace(
                "\"", "").replace("\'", "")
            # print(pin_name, "->", str(pin_group['direction']).replace("\"","").replace("\'",""))
            newStdCellType.addPin(pin_name, str(
                pin_group['direction']).replace("\"", "").replace(" ", "").replace("\'", ""))

        stdCellLib[name] = newStdCellType

    _liberty_cache[key] = stdCellLib
    return stdCellLib


def load_bool_gate_from_blif(blif, stdCellLib):
    for boolFunc in blif.booleanfunctions:
        truthTableStr = "bool-"+str(boolFunc.truthtable)
        if (not truthTableStr in stdCellLib.keys()):
            newStdCellType = StdCellType(truthTableStr)
            for i in range(0, len(boolFunc.v_params)-1):
                newStdCellType.addPin("IN"+str(i), 'input')
            newStdCellType.addPin("OUT0", 'output')
            stdCellLib[truthTableStr] = newStdCellType


def gen_graph_from_liberty_and_blif(libFileName, blifFileName):

    stdCellLib = load_liberty_file(libFileName)

    # get the file path and pass it to the parser
    filepath = os.path.abspath(blifFileName)
    parser = blifparser.BlifParser(filepath)

    # get the object that contains the parsed data
    # from the parser
    blif = parser.blif
    load_bool_gate_from_blif(blif, stdCellLib)

    # get the dictionary with the number of occurrencies of each keyword
    print(blif.nkeywords, "\n")

    cellName2Obj = dict()
    cells = []
    netName2Obj = dict()
    nets = []
    idCnt = 0
    for tmpCircuit in blif.subcircuits:
        refType = tmpCircuit.modelname
        if (refType in stdCellLib.keys()):
            name = str(tmpCircuit)
            curCell = DesignCell(idCnt, name, stdCellLib[refType])
            idCnt += 1
            for pin in tmpCircuit.params:
                pinInfo = pin.split("=")
                if (len(pinInfo) != 2):
                    raise ValueError(
                        "malformed pin mapping %r in .subckt instance %r "
                        "(expected PIN=net)" % (pin, name))
                curCell.addCellPin(pinInfo[0], pinInfo[1])
            cellName2Obj[name] = curCell
            cells.append(curCell)
        else:
            # An assert(False) is stripped under `python -O`; fail loudly
            # instead of building a graph with silently dropped instances.
            raise ValueError(
                "cell type %r of instance %r is not in the liberty file %s"
                % (refType, str(tmpCircuit), libFileName))

    for logicGate in blif.booleanfunctions:
        refType = "bool-"+str(logicGate.truthtable)
        if (refType in stdCellLib.keys()):
            name = str(logicGate)
            curCell = DesignCell(idCnt, name, stdCellLib[refType])
            idCnt += 1
            if (len(logicGate.v_params) > 1):
                for pinId, pin in enumerate(logicGate.v_params[:-1]):
                    curCell.addCellPin("IN"+str(pinId), pin)
            curCell.addCellPin("OUT", logicGate.v_params[-1])
            cellName2Obj[name] = curCell
            cells.append(curCell)
        else:
            raise ValueError(
                "boolean-gate type %r is not in the liberty file %s"
                % (refType, libFileName))

    idCnt = 0
    stdCellType2Cells = dict()
    for designCell in cells:
        if (not designCell.stdCellType.typeName in stdCellType2Cells.keys()):
            stdCellType2Cells[designCell.stdCellType.typeName] = []
        stdCellType2Cells[designCell.stdCellType.typeName].append(designCell)
        for refPin, inputNet in zip(designCell.inputPinRefNames, designCell.inputNetNames):
            if (not inputNet in netName2Obj.keys()):
                curNet = DesignNet(idCnt, inputNet)
                netName2Obj[inputNet] = curNet
                nets.append(curNet)
                idCnt += 1
            else:
                curNet = netName2Obj[inputNet]
            designCell.addInputNet(curNet)
            curNet.addPin(refPin, designCell, True)
        for refPin, outputNet in zip(designCell.outputPinRefNames, designCell.outputNetNames):
            if (not outputNet in netName2Obj.keys()):
                curNet = DesignNet(idCnt, outputNet)
                netName2Obj[outputNet] = curNet
                nets.append(curNet)
                idCnt += 1
            else:
                curNet = netName2Obj[outputNet]
            designCell.addOutputNet(curNet)
            curNet.addPin(refPin, designCell, False)

    stdCellType2Cnt = []
    for key in stdCellType2Cells.keys():
        stdCellType2Cnt.append((key, len(stdCellType2Cells[key])))
    sorted_by_second = sorted(stdCellType2Cnt, key=lambda tup: -tup[1])
    print("top std cell types: ", sorted_by_second[1:30])

    stdCellTypesForFeature = []
    for tmpType in sorted_by_second:
        stdCellTypesForFeature.append(tmpType[0])
    print("top std cell type names: ", stdCellTypesForFeature)

    print("creating networkx graph with ", len(cells), " nodes")
    BLIFGraph = nx.DiGraph()
    nodeType = dict()
    netlist = []
    for designCell in cells:
        if (designCell.stdCellType.typeName in stdCellTypesForFeature):
            nodeType[designCell.id] = designCell.stdCellType.typeName
        else:
            nodeType[designCell.id] = "minorType"
        BLIFGraph.add_node(
            designCell.id, type=nodeType[designCell.id], nodeLabel=-1, name=designCell.name)

        for inputNet in designCell.inputNets:
            if (not inputNet.predCell is None):
                netlist.append((inputNet.predCell.id, designCell.id))

        for outputNet in designCell.outputNets:
            if (len(outputNet.succCells) < 10000):
                for succCell in outputNet.succCells:
                    netlist.append((designCell.id, succCell.id))

    BLIFGraph.add_edges_from(netlist)
    print("created networkx graph with ", len(cells), " nodes")

    for cell in cells:
        for tmpType in bypassTypes:
            if (cell.stdCellType.typeName.find(tmpType) >= 0):
                cell.stopType = True

    return BLIFGraph, cells, netlist, stdCellTypesForFeature


class SPSubcircuit(object):
    def __init__(self, texts):
        self.name = texts[0].split(" ")[1]
        self.interfaces = []
        self.internalSignals = []
        self.texts = [line.replace('\n', '') for line in texts]

        # Parse the interface names from the newline-normalised header; using
        # the raw ``texts[0]`` left a trailing "\n" on the last pin name.
        for interface in self.texts[0].split(" ")[2:]:
            self.interfaces.append(interface)

        for line in self.texts[1:-1]:
            if (line.find('M') == 0):
                eles = line.split(' ')[1:5]
                for ele in eles:
                    if ((not ele in self.interfaces) and (not ele in self.internalSignals)):
                        self.internalSignals.append(ele)

    def addInterface(self, ifName):
        self.interfaces.append(ifName)

    def addInternalSignal(self, innerName):
        self.internalSignals.append(innerName)

    def renamePrefix(self, prefix):
        for signal in self.interfaces+self.internalSignals:
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

        for i in range(0, len(self.internalSignals)):
            if (self.internalSignals[i] == 'VCC' or self.internalSignals[i] == 'GND'):
                continue
            self.internalSignals[i] = prefix+self.internalSignals[i]

        for i in range(0, len(self.texts)):
            eles = self.texts[i].split(" ")
            if (len(eles) > 0):
                if (eles[0].find('M') == 0):
                    eles[0] = 'M'+prefix+eles[0][1:]
                self.texts[i] = ' '.join(eles)

    def replaceInputPin(self, oriPinName, newPinName):
        replaced = False
        for i in range(0, len(self.texts)):
            eles = self.texts[i].split(" ")
            for j in range(0, len(eles)):
                if (eles[j] == oriPinName):
                    eles[j] = newPinName
                    replaced = True
            self.texts[i] = ' '.join(eles)
        assert(replaced)
        for i in range(0, len(self.interfaces)):
            if (self.interfaces[i] == 'VCC' or self.interfaces[i] == 'GND'):
                continue
            if (self.interfaces[i] == oriPinName):
                self.interfaces[i] = newPinName

    def print(self):
        for line in self.texts:
            print(line)


def load_spice_subcircuits(filePath):
    spFile = open(filePath, 'r')
    lines = spFile.readlines()

    spiceSubcircuits = dict()

    lineId = 0
    while (lineId < len(lines)):
        if (lines[lineId].find(".subckt ") >= 0):
            beginLineId = lineId
            while (lines[lineId].find(".ends ") < 0):
                lineId += 1
            endLineId = lineId
            newSubckt = SPSubcircuit(lines[beginLineId:endLineId+1])
            spiceSubcircuits[newSubckt.name] = newSubckt

        lineId += 1

    return spiceSubcircuits
