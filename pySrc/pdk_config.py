"""Per-PDK geometry configuration (roadmap P1-8).

The ASTRAN run script hard-codes the cell geometry (AGENTS.md invariant
2): row height, routing grid, supply-rail width, nwell position, cell
template.  Those six numbers *are* the PDK binding -- CPCell (arXiv
2026) shows the CPP:metal-pitch "gear ratio" is a first-class design
variable, not a constant to bury in code.

This module collects each PDK's geometry and technology-file pointers
into one registry.  ``freepdk45`` reproduces the validated GSCL45
constants in astran.py (the test suite pins the equivalence).  The
``sky130`` / ``gf180`` entries have their .rul rule files written
(status ``draft``) from primary LEF sources -- geometry is real, but no
DRC deck has been run on generated cells yet, so they still require the
explicit ``allow_scaffold=True`` opt-in and the registry marks them
``draft``, not ``validated``.  Finishing a PDK means: run a few cells,
check them against the PDK's own DRC deck (ASTRAN's internal rules are
placeholders for unverified rows -- see the .rul headers), then flip the
status.

Usage:
    from pdk_config import get_pdk, pdk_geometry_dict, load_technology_rul
    pdk = get_pdk("freepdk45")
    script = build_astran_commands(..., geometry=pdk_geometry_dict(pdk))
"""

import os

_REPO_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."))


class PdkProfile(object):
    def __init__(self, name, cells_height, h_grid, v_grid, supply_size,
                 cell_template, technology_rul, gds_map=None,
                 status="validated", notes=""):
        self.name = name
        self.cells_height = cells_height
        self.h_grid = h_grid
        self.v_grid = v_grid
        self.supply_size = supply_size
        self.cell_template = cell_template
        self.technology_rul = technology_rul
        self.gds_map = gds_map
        self.status = status            # "validated" | "draft" | "scaffold"
        self.notes = notes

    @property
    def row_height_um(self):
        return self.cells_height * self.v_grid

    @property
    def nwell_pos(self):
        """N-well bottom edge: always H/2 so P/N diffusion heights match
        (the 1.0825 incident -- see AUDIT_REPORT -- is what an asymmetric
        value costs)."""
        return self.row_height_um / 2.0


_PDK_REGISTRY = {
    "freepdk45": PdkProfile(
        name="freepdk45",
        cells_height=13, h_grid=0.19, v_grid=0.19,
        supply_size=0.26, cell_template="Tapless",
        technology_rul=os.path.join(
            _REPO_DIR, "tools", "astran", "build", "Work",
            "tech_freePDK45.rul"),
        gds_map=os.path.join(_REPO_DIR, "stdCelllib", "gds2_encounter.map"),
        status="validated",
        notes="GSCL45: row = 13 x 0.19 = 2.47um = CoreSite height; "
              "M1-pitch grid; abutment supply rails 2 x 0.13um."),
    # --- second PDKs: .rul written from primary LEF sources (2026-10-09,
    # see doc/RESEARCH_AND_OPTIMIZATION.md P1-8), DRC deck not yet run --
    # status "draft": geometry is real, cells are not yet validated.
    "sky130": PdkProfile(
        name="sky130",
        cells_height=8, h_grid=0.34, v_grid=0.34,
        supply_size=0.48, cell_template="Tapless",
        technology_rul=os.path.join(
            _REPO_DIR, "tools", "astran", "build", "Work",
            "tech_sky130.rul"),
        status="draft",
        notes="sky130_fd_sc_hd: row 2.72um = 8 x 0.34um (SITE unithd); "
              "met1 w/s 0.14/0.14; rails VPWR/VGND met1 0.48 + li1 0.17. "
              "NEEDS PDK DRC validation."),
    "gf180": PdkProfile(
        name="gf180",
        cells_height=7, h_grid=0.56, v_grid=0.56,
        supply_size=0.60, cell_template="Tapless",
        technology_rul=os.path.join(
            _REPO_DIR, "tools", "astran", "build", "Work",
            "tech_gf180.rul"),
        status="draft",
        notes="gf180mcu 7T: row 3.92um = 7 x 0.56um (SITE "
              "GF018hv5v_mcu_sc7); met1 w/s 0.230/0.230; rails VDD/VSS "
              "met1 0.60. NEEDS PDK DRC validation."),
}


def get_pdk(name, allow_scaffold=False):
    """Look up a PDK profile by name; non-validated PDKs are opt-in."""
    if (name not in _PDK_REGISTRY):
        raise KeyError(
            "unknown PDK %r; available: %s"
            % (name, sorted(_PDK_REGISTRY.keys())))
    pdk = _PDK_REGISTRY[name]
    if (pdk.status != "validated" and not allow_scaffold):
        raise RuntimeError(
            "PDK %r is %s (no DRC-validated cells yet); pass "
            "allow_scaffold=True to experiment. %s"
            % (name, pdk.status, pdk.notes))
    return pdk


def list_pdks():
    return {name: pdk.status for name, pdk in _PDK_REGISTRY.items()}


def pdk_geometry_dict(pdk):
    """Geometry dict for astran.build_astran_commands(..., geometry=...)."""
    return {
        "cells_height": pdk.cells_height,
        "h_grid": pdk.h_grid,
        "v_grid": pdk.v_grid,
        "supply_size": pdk.supply_size,
        "nwell_pos": pdk.nwell_pos,
        "cell_template": pdk.cell_template,
    }


def load_technology_rul(path):
    """Parse an ASTRAN .rul file; dict with tech_name/minstep/vdd/mlayers
    and a {name: (cif, gds, tech)} layer map.  Deterministic; a corrupt
    or missing file raises so a wrong PDK cannot be silently enabled.
    """
    tech = {"tech_name": None, "minstep": None, "vdd": None,
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
                tech["tech_name"] = parts[1]
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


def multi_row_variant(pdk, row_multiplier=2):
    """Multi-row-height variant of a profile (roadmap P1-11).

    Complexes past ~20 transistors can trade doubled row height for a
    much smaller width (Optimal Layout Synthesis of Multi-Row Standard
    Cells, ICCAD'24; the ASP-DAC'25 follow-up adds intra-cell
    routability to the objective).  nwell_pos stays H/2 automatically, so
    the equal-well invariant holds at any multiplier.  Width comparisons
    against single-row cells are only meaningful as area (width x
    height) -- AGENTS.md invariant 10 applies.
    """
    return PdkProfile(
        name="%s_x%drows" % (pdk.name, row_multiplier),
        cells_height=pdk.cells_height * row_multiplier,
        h_grid=pdk.h_grid, v_grid=pdk.v_grid,
        supply_size=pdk.supply_size, cell_template=pdk.cell_template,
        technology_rul=pdk.technology_rul, gds_map=pdk.gds_map,
        status=pdk.status,
        notes="multi-row variant of %s (%d rows); %s"
              % (pdk.name, row_multiplier, pdk.notes))
