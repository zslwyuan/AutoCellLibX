import os

from os import listdir
from os.path import isfile, join

GSCL_LEF = "../std_celllib/gscl45nm.lef"

GSCL_CELL_NAMES = ["AND2X1", "AOI22X1", "CLKBUF1",  "DFFNEGX1",
                   "FAX1", "INVX2", "LATCH", "NAND3X1", "OAI21X1", "OR2X2",
                   "XNOR2X1", "AND2X2", "BUFX2", "CLKBUF2", "DFFPOSX1", "HAX1",
                   "INVX4", "MUX2X1", "NOR2X1", "OAI22X1", "TBUFX1", "XOR2X1",
                   "AOI21X1", "BUFX4", "CLKBUF3", "DFFSR", "INVX1", "INVX8",
                   "NAND2X1", "NOR3X1", "OR2X1", "TBUFX2"]

# --- Why width is used as the area metric ---------------------------------
# Every cell of one standard-cell library occupies the same row height, so the
# cell footprint area is proportional to its width.  Comparing widths is
# therefore equivalent to comparing areas, and it avoids a systematic error
# when the two sides were generated at different row heights (the ASTRAN
# baseline in original_astran_cells/ was generated at H = 3.2 um, while cells
# generated locally come out at H = 2.6 um).  Multiplying each side by its own
# height would distort the comparison, so the nominal width is used instead.
# ---------------------------------------------------------------------------


def _readLefCellWidths(lef_path):
    """Nominal width of each LEF MACRO, from its SIZE statement."""
    widths = dict()
    macro = None
    for line in open(lef_path, 'r'):
        t = line.strip()
        if (t.startswith("MACRO ")):
            macro = t.split()[1]
        elif (t.startswith("SIZE ") and macro is not None):
            parts = t.replace(";", "").split()   # SIZE <width> BY <height>
            if (len(parts) >= 4):
                widths[macro] = float(parts[1])
        elif (t.startswith("END ") and macro is not None):
            macro = None
    return widths


def load_original_gscl45_gds():
    widths = _readLefCellWidths(GSCL_LEF)
    width_by_name = dict()
    for name in GSCL_CELL_NAMES:
        assert name in widths, "cell %s not found in %s" % (name, GSCL_LEF)
        width_by_name[name] = widths[name]
    return width_by_name


def _readAstranCellWidth(log_file_name):
    for line in open(log_file_name, 'r'):
        if (line.find("-> Cell Size (W x H): ") >= 0):
            return float(line.replace("-> Cell Size (W x H): ", "").split("x")[0])
    return None


def load_astran_gds():
    """Nominal width of each ASTRAN-generated original cell, from its log.

    Same metric as load_original_gscl45_gds and astran.load_astran_area (nominal
    width) so the ASTRAN baseline, the generated complex cells and the GSCL
    library are all compared consistently.
    """
    width_by_type = dict()
    gds_path = "./original_astran_cells/"
    for f in listdir(gds_path):
        if (not f.endswith(".Astranlog")):
            continue
        name = f.replace(".Astranlog", "")
        w = _readAstranCellWidth(join(gds_path, f))
        if (w is not None):
            width_by_type[name] = w
    return width_by_type
