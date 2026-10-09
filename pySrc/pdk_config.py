"""Per-PDK geometry configuration (roadmap P1-8).

The ASTRAN run script hard-codes the cell geometry (AGENTS.md invariant
2): row height, routing grid, supply-rail width, nwell position, cell
template.  Those six numbers *are* the PDK binding -- CPCell (arXiv
2026) shows the CPP:metal-pitch "gear ratio" is a first-class design
variable, not a constant to bury in code.

This module collects each PDK's geometry and technology-file pointers
into one registry.  ``freepdk45`` reproduces the validated GSCL45
constants in Astran.py (the test suite pins the equivalence); the
``sky130`` / ``gf180`` entries are SCAFFOLDS: library geometry taken
from the public PDK documentation, but the ASTRAN .rul rule files for
them do not exist yet, so they raise unless explicitly enabled.  Adding
a real PDK means: write its .rul + .map, calibrate the geometry here,
then re-validate DRC on a few cells.

Usage:
    from pdk_config import getPdk, pdkGeometryDict
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
        self.status = status            # "validated" | "scaffold"
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
    # --- scaffolds: geometry from the public docs, .rul/.map NOT yet
    # written -- enabling requires authoring the technology files and
    # re-validating DRC (see doc/RESEARCH_AND_OPTIMIZATION.md P1-8).
    "sky130": PdkProfile(
        name="sky130",
        cellsHeight=8, hGrid=0.34, vGrid=0.34,
        supplySize=0.48, cellTemplate="Tapless",
        technologyRul=os.path.join(
            _REPO_DIR, "tools", "astran", "build", "Work",
            "tech_sky130.rul"),          # TODO: does not exist yet
        status="scaffold",
        notes="sky130_fd_sc_hd: row 2.72um = 8 x 0.34um (li1 pitch "
              "0.34um); supply per hd library convention. NEEDS .rul."),
    "gf180": PdkProfile(
        name="gf180",
        cellsHeight=14, hGrid=0.28, vGrid=0.28,
        supplySize=0.44, cellTemplate="Tapless",
        technologyRul=os.path.join(
            _REPO_DIR, "tools", "astran", "build", "Work",
            "tech_gf180.rul"),           # TODO: does not exist yet
        status="scaffold",
        notes="gf180mcu 7-track: row 3.92um = 14 x 0.28um (met1 pitch "
              "0.28um per PDK docs). NEEDS .rul."),
}


def getPdk(name, allowScaffold=False):
    """Look up a PDK profile by name; scaffolds are opt-in."""
    if (name not in _PDK_REGISTRY):
        raise KeyError(
            "unknown PDK %r; available: %s"
            % (name, sorted(_PDK_REGISTRY.keys())))
    pdk = _PDK_REGISTRY[name]
    if (pdk.status != "validated" and not allowScaffold):
        raise RuntimeError(
            "PDK %r is a %s (no validated .rul yet); pass "
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
