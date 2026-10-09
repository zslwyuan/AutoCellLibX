"""Per-PDK geometry configuration (roadmap P1-8).

The ASTRAN run script hard-codes the cell geometry (AGENTS.md invariant
2): row height, routing grid, supply-rail width, nwell position, cell
template.  Those six numbers *are* the PDK binding -- CPCell (arXiv
2026) shows the CPP:metal-pitch "gear ratio" is a first-class design
variable, not a constant to bury in code.

This module collects each PDK's geometry and technology-file pointers
into one registry.  ``freepdk45`` reproduces the validated GSCL45
constants in Astran.py (the test suite pins the equivalence).  The
``sky130`` / ``gf180`` entries have their .rul rule files written
(status ``draft``) from primary LEF sources -- geometry is real, but no
DRC deck has been run on generated cells yet, so they still require the
explicit ``allowScaffold=True`` opt-in and the registry marks them
``draft``, not ``validated``.  Finishing a PDK means: run a few cells,
check them against the PDK's own DRC deck (ASTRAN's internal rules are
placeholders for unverified rows -- see the .rul headers), then flip the
status.

Usage:
    from pdk_config import getPdk, pdkGeometryDict, loadTechnologyRul
    pdk = getPdk("freepdk45")
    script = buildAstranCommands(..., geometry=pdkGeometryDict(pdk))
"""

import os

_REPO_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."))


class PdkProfile(object):
    def __init__(self, name, cellsHeight, hGrid, vGrid, supplySize,
                 cellTemplate, technologyRul, gdsMap=None,
                 status="validated", notes=""):
        self.name = name
        self.cellsHeight = cellsHeight
        self.hGrid = hGrid
        self.vGrid = vGrid
        self.supplySize = supplySize
        self.cellTemplate = cellTemplate
        self.technologyRul = technologyRul
        self.gdsMap = gdsMap
        self.status = status            # "validated" | "draft" | "scaffold"
        self.notes = notes

    @property
    def rowHeightUm(self):
        return self.cellsHeight * self.vGrid

    @property
    def nwellPos(self):
        """N-well bottom edge: always H/2 so P/N diffusion heights match
        (the 1.0825 incident -- see AUDIT_REPORT -- is what an asymmetric
        value costs)."""
        return self.rowHeightUm / 2.0


_PDK_REGISTRY = {
    "freepdk45": PdkProfile(
        name="freepdk45",
        cellsHeight=13, hGrid=0.19, vGrid=0.19,
        supplySize=0.26, cellTemplate="Tapless",
        technologyRul=os.path.join(
            _REPO_DIR, "tools", "astran", "build", "Work",
            "tech_freePDK45.rul"),
        gdsMap=os.path.join(_REPO_DIR, "stdCelllib", "gds2_encounter.map"),
        status="validated",
        notes="GSCL45: row = 13 x 0.19 = 2.47um = CoreSite height; "
              "M1-pitch grid; abutment supply rails 2 x 0.13um."),
    # --- second PDKs: .rul written from primary LEF sources (2026-10-09,
    # see doc/RESEARCH_AND_OPTIMIZATION.md P1-8), DRC deck not yet run --
    # status "draft": geometry is real, cells are not yet validated.
    "sky130": PdkProfile(
        name="sky130",
        cellsHeight=8, hGrid=0.34, vGrid=0.34,
        supplySize=0.48, cellTemplate="Tapless",
        technologyRul=os.path.join(
            _REPO_DIR, "tools", "astran", "build", "Work",
            "tech_sky130.rul"),
        status="draft",
        notes="sky130_fd_sc_hd: row 2.72um = 8 x 0.34um (SITE unithd); "
              "met1 w/s 0.14/0.14; rails VPWR/VGND met1 0.48 + li1 0.17. "
              "NEEDS PDK DRC validation."),
    "gf180": PdkProfile(
        name="gf180",
        cellsHeight=7, hGrid=0.56, vGrid=0.56,
        supplySize=0.60, cellTemplate="Tapless",
        technologyRul=os.path.join(
            _REPO_DIR, "tools", "astran", "build", "Work",
            "tech_gf180.rul"),
        status="draft",
        notes="gf180mcu 7T: row 3.92um = 7 x 0.56um (SITE "
              "GF018hv5v_mcu_sc7); met1 w/s 0.230/0.230; rails VDD/VSS "
              "met1 0.60. NEEDS PDK DRC validation."),
}


def getPdk(name, allowScaffold=False):
    """Look up a PDK profile by name; non-validated PDKs are opt-in."""
    if (name not in _PDK_REGISTRY):
        raise KeyError(
            "unknown PDK %r; available: %s"
            % (name, sorted(_PDK_REGISTRY.keys())))
    pdk = _PDK_REGISTRY[name]
    if (pdk.status != "validated" and not allowScaffold):
        raise RuntimeError(
            "PDK %r is %s (no DRC-validated cells yet); pass "
            "allowScaffold=True to experiment. %s"
            % (name, pdk.status, pdk.notes))
    return pdk


def listPdks():
    return {name: pdk.status for name, pdk in _PDK_REGISTRY.items()}


def pdkGeometryDict(pdk):
    """Geometry dict for Astran.buildAstranCommands(..., geometry=...)."""
    return {
        "cellsHeight": pdk.cellsHeight,
        "hGrid": pdk.hGrid,
        "vGrid": pdk.vGrid,
        "supplySize": pdk.supplySize,
        "nwellPos": pdk.nwellPos,
        "cellTemplate": pdk.cellTemplate,
    }


def loadTechnologyRul(path):
    """Parse an ASTRAN .rul file; dict with techName/minstep/vdd/mlayers
    and a {name: (cif, gds, tech)} layer map.  Deterministic; a corrupt
    or missing file raises so a wrong PDK cannot be silently enabled.
    """
    tech = {"techName": None, "minstep": None, "vdd": None,
            "mlayers": None, "layers": {}}
    with open(path, 'r', errors="ignore") as f:
        for line in f:
            line = line.strip()
            if (not line or line.startswith("*")):
                continue
            parts = line.split()
            if (not parts):
                continue
            if (parts[0] == "TECHNAME"):
                tech["techName"] = parts[1]
            elif (parts[0] == "MINSTEP"):
                tech["minstep"] = float(parts[1])
            elif (parts[0] == "VDD"):
                tech["vdd"] = float(parts[1])
            elif (parts[0] == "MLAYERS"):
                tech["mlayers"] = int(parts[1])
            elif (len(parts) >= 4):
                # layer-map rows: NAME CIF GDSII TECH (rule rows are 2-token)
                tech["layers"][parts[0]] = (parts[1], int(parts[2]),
                                            parts[3])
    return tech


def multiRowVariant(pdk, rowMultiplier=2):
    """Multi-row-height variant of a profile (roadmap P1-11).

    Complexes past ~20 transistors can trade doubled row height for a
    much smaller width (Optimal Layout Synthesis of Multi-Row Standard
    Cells, ICCAD'24; the ASP-DAC'25 follow-up adds intra-cell
    routability to the objective).  nwellPos stays H/2 automatically, so
    the equal-well invariant holds at any multiplier.  Width comparisons
    against single-row cells are only meaningful as area (width x
    height) -- AGENTS.md invariant 10 applies.
    """
    return PdkProfile(
        name="%s_x%drows" % (pdk.name, rowMultiplier),
        cellsHeight=pdk.cellsHeight * rowMultiplier,
        hGrid=pdk.hGrid, vGrid=pdk.vGrid,
        supplySize=pdk.supplySize, cellTemplate=pdk.cellTemplate,
        technologyRul=pdk.technologyRul, gdsMap=pdk.gdsMap,
        status=pdk.status,
        notes="multi-row variant of %s (%d rows); %s"
              % (pdk.name, rowMultiplier, pdk.notes))
