import gdspy


def loadOrignalGSCL45nmGDS():
    stdCellNames = ["AND2X1", "AOI22X1", "CLKBUF1",  "DFFNEGX1",
                    "FAX1", "INVX2", "LATCH", "NAND3X1", "OAI21X1", "OR2X2",
                    "XNOR2X1", "AND2X2", "BUFX2", "CLKBUF2", "DFFPOSX1", "HAX1",
                    "INVX4", "MUX2X1", "NOR2X1", "OAI22X1", "TBUFX1", "XOR2X1",
                    "AOI21X1", "BUFX4", "CLKBUF3", "DFFSR", "INVX1", "INVX8",
                    "NAND2X1", "NOR3X1", "OR2X1", "TBUFX2"]

    gsclName2GDSSize = dict()
    for name in stdCellNames:
        gdsii = gdspy.GdsLibrary(infile='./originalAstranStdCells'+name+'.gds')
        gsclName2GDSSize[name] = gdsii.cells[name].area(True)[(6, 0)]

    return gsclName2GDSSize
