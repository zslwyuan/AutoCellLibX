"""Shim (ARCHITECTURE): the SPICE reader (SPSubcircuit,
loadSpiceSubcircuits) lives in core/parse; this module keeps the
netlist exporter (exportSpiceNetlist).
"""

from core.parse import SPSubcircuit, loadSpiceSubcircuits

import sys
import os
from matplotlib.pyplot import text
def exportSpiceNetlist(cluserSeq, subckts, mergeCellTypeId,  outputDir):

    cellsInCluster = cluserSeq.patternClusters[0].cellsContained
    spiceList = []
    cell2orderId = dict()

    # rename signals and transistors
    for orderId, cell in enumerate(cellsInCluster):
        spiceList.append(SPSubcircuit(
            subckts[cell.stdCellType.typeName].texts))
        spiceList[-1].renamePrefix("cl"+str(orderId)+"#")
        cell2orderId[cell] = orderId

    # connect each input pins of each subcircuit
    for orderId, curCell in enumerate(cellsInCluster):
        for inputNet, inputPinName in zip(curCell.inputNets, curCell.inputPinRefNames):
            predCell = inputNet.predCell
            predPinName = inputNet.predPin
            if (predCell in cell2orderId.keys()):
                spiceList[orderId].replaceInputPin(
                    "cl"+str(orderId)+"#"+inputPinName, "cl"+str(cell2orderId[predCell])+"#"+predPinName)

    # merge spice netlists
    # A dict is used as an insertion-ordered set.  A plain set iterates in hash
    # order, which changes between processes (PYTHONHASHSEED), so the exported
    # netlist -- and with it the layout cache key -- was different on every run.
    interfaceSet = {}
    internalSignals = []
    for spiceObj in spiceList:
        for pin in spiceObj.interfaces:
            interfaceSet[pin] = None
        internalSignals = internalSignals + spiceObj.internalSignals

    # remove internal signals from interfaces
    for orderId, curCell in enumerate(cellsInCluster):
        for outputNet, outputPinName in zip(curCell.outputNets, curCell.outputPinRefNames):
            allSuccCellsInternal = True
            for succCell in outputNet.succCells:
                if (not succCell in cell2orderId.keys()):
                    allSuccCellsInternal = False
            if (allSuccCellsInternal):
                assert("cl"+str(orderId)+"#"+outputPinName in interfaceSet)
                del interfaceSet["cl"+str(orderId)+"#"+outputPinName]

    mergeCellName = "COMPLEX"+str(mergeCellTypeId)
    interfaceList = list(interfaceSet)
    firstLine = ".subckt "+mergeCellName+" " + " ".join(interfaceList)
    internalLines = [firstLine]
    for ele in spiceList:
        internalLines = internalLines + ele.texts[1:-1]
    lastLine = ".ends "+mergeCellName

    internalLines.append(lastLine)
    internalLines.append("* pattern code: "+cluserSeq.patternExtensionTrace)
    internalLines.append(
        "* "+str(len(cluserSeq.patternClusters))+" occurrences in design ")
    internalLines.append(
        "* each contains "+str(len(cellsInCluster))+" cells")
    internalLines.append(
        "* Example occurence:")
    for cell in cellsInCluster:
        internalLines.append("*   "+cell.name)

    # Write only when the content actually changes, so the netlist's mtime is a
    # reliable "inputs changed" signal for the layout cache in main.py.
    content = '\n'.join(internalLines) + '\n'
    spPath = outputDir+"/"+mergeCellName+'.sp'
    if ((not os.path.exists(spPath)) or (open(spPath).read() != content)):
        outputSP = open(spPath, 'w')
        outputSP.write(content)
        outputSP.close()
