"""Unit tests for smt_engine.die_view -- the shared die-orientation view.

The die view reconstructs, from (netlist, placement) alone, the member
order and edge nets the die actually carries: multi-member blocks are
mirrored exactly when their placement start_cols descend, single-member
blocks recover their flip from place_row's abutment gaps (fixpoint), and
singles no constraint pins stay pristine -- the one convention every
consumer (route_grid, verify) must share.  Pure and deterministic
(AGENTS.md invariants 8/9).
"""
import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.die_view import (DEFAULT_BREAK_COLS, die_orientation,
                                 die_orientation_map, die_slot_access_points,
                                 is_slot_placement)
from smt_engine.layout_model import PlacedTransistor
from smt_engine.netlist import CellNetlist

INV = """\
.subckt INV VCC Y A GND
Mp Y A VCC VCC PMOS W=0.5u L=0.05u
Mn Y A GND GND NMOS W=0.5u L=0.05u
.ends INV
"""

# two stacked inverters: the P pair is one parallel block, placed in
# REVERSE die order (MpB left of MpA) = mirrored
MIRROPAR = """\
.subckt MIRROPAR VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB Y B VCC VCC PMOS W=0.5u L=0.05u
MnA Y A GND GND NMOS W=0.5u L=0.05u
MnB Y B GND GND NMOS W=0.5u L=0.05u
.ends MIRROPAR
"""

# Mp1 is a single whose pristine right net (Y) cannot face the
# neighbour block's left net (VCC) across a zero gap -- the abutment
# gap pins it FLIPPED (die Y|VCC)
FLIPSINGLE = """\
.subckt FLIPSINGLE VCC Y W A GND
Mp1 Y A VCC VCC PMOS W=0.5u L=0.05u
Mp2 W A VCC VCC PMOS W=0.5u L=0.05u
Mp3 W A VCC VCC PMOS W=0.5u L=0.05u
Mn1 Y A GND GND NMOS W=0.5u L=0.05u
Mn2 W A GND GND NMOS W=0.5u L=0.05u
Mn3 W A GND GND NMOS W=0.5u L=0.05u
.ends FLIPSINGLE
"""

# a parallel TRIO: the shared output Y occupies two interior slots
# (multi-region) although it is no block end anywhere
TRIO = """\
.subckt TRIO VCC Y A B C GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB Y B VCC VCC PMOS W=0.5u L=0.05u
MpC Y C VCC VCC PMOS W=0.5u L=0.05u
MnA Y A GND GND NMOS W=0.5u L=0.05u
MnB Y B GND GND NMOS W=0.5u L=0.05u
MnC Y C GND GND NMOS W=0.5u L=0.05u
.ends TRIO
"""

# B is a PORT with two diffusion terminals, so Mn1/Mn2 stay separate
# singles; placed one break column apart, the gap-1 "facing nets
# differ" constraint pins Mn2 FLIPPED (pristine would face B against B)
GAPSYM = """\
.subckt GAPSYM VCC A B C P GND
Mp1 A P VCC VCC PMOS W=0.5u L=0.05u
Mn1 B P A GND NMOS W=0.5u L=0.05u
Mn2 C P B GND NMOS W=0.5u L=0.05u
.ends GAPSYM
"""


def _netlist(sp):
    return CellNetlist(parse_spice_subckt(sp))


def _placed(nl, spec):
    """{Device: PlacedTransistor} from {device name: (row, start, legs, lw)}."""
    by = {d.name: d for d in nl.devices}
    return {by[name]: PlacedTransistor(row, start, legs, lw)
            for name, (row, start, legs, lw) in spec.items()}


def _shape(views):
    return tuple((v.kind, v.flipped,
                  tuple((m.device.name, m.left_net, m.right_net)
                        for m in v.members))
                 for v in views)


# ---------------- is_slot_placement ----------------

def test_slot_placement_discriminator():
    nl = _netlist(INV)
    slot = _placed(nl, {"Mp": (0, 0, 1, 1), "Mn": (1, 0, 1, 1)})
    assert is_slot_placement(slot) is True
    exact = _placed(nl, {"Mp": (0, 0, 1, 3), "Mn": (1, 0, 1, 3)})
    assert is_slot_placement(exact) is False
    mixed = _placed(nl, {"Mp": (0, 0, 1, 1), "Mn": (1, 0, 1, 2)})
    assert is_slot_placement(mixed) is False
    assert is_slot_placement({}) is False


# ---------------- die_orientation ----------------

def test_pristine_blocks_keep_their_member_nets():
    nl = _netlist(INV)
    placement = _placed(nl, {"Mp": (0, 0, 1, 1), "Mn": (1, 0, 1, 1)})
    views = die_orientation(nl, placement)
    # build_diffusion_blocks order: singles sorted by first-device name
    assert _shape(views) == (
        ("single", None, (("Mn", "GND", "Y"),)),
        ("single", None, (("Mp", "VCC", "Y"),)))
    assert die_orientation_map(nl, placement) == {
        "Mp": ("VCC", "Y"), "Mn": ("GND", "Y")}


def test_descending_start_cols_mean_mirrored():
    nl = _netlist(MIRROPAR)
    # the P parallel block placed in REVERSE die order (MpB, MpA);
    # the N block pristine
    placement = _placed(nl, {"MpA": (0, 3, 1, 3), "MpB": (0, 0, 1, 3),
                             "MnA": (1, 0, 1, 3), "MnB": (1, 3, 1, 3)})
    views = die_orientation(nl, placement)
    by_first = {v.members[0].device.name: v for v in views}
    assert by_first["MpB"].flipped is True
    assert by_first["MnA"].flipped is False
    # the die edge nets follow the flip
    mapping = die_orientation_map(nl, placement)
    assert mapping["MpA"] == ("Y", "VCC")
    assert mapping["MpB"] == ("VCC", "Y")


def test_flipped_single_recovered_from_the_abutment_gap():
    nl = _netlist(FLIPSINGLE)
    placement = _placed(nl, {"Mp1": (0, 0, 1, 3), "Mp2": (0, 3, 1, 3),
                             "Mp3": (0, 6, 1, 3),
                             "Mn1": (1, 0, 1, 3), "Mn2": (1, 4, 1, 3),
                             "Mn3": (1, 7, 1, 3)})
    mapping = die_orientation_map(nl, placement)
    # Mp1's pristine die-right (Y) cannot face the neighbour's VCC
    # across a zero gap: the fixpoint flips it
    assert mapping["Mp1"] == ("Y", "VCC")
    # the N row: Mn1 is a single (pristine, break gap faces GND vs Y),
    # Mn2/Mn3 are one parallel block placed abutting (pristine)
    assert mapping["Mn1"] == ("GND", "Y")
    assert mapping["Mn2"] == ("GND", "W")


def test_gap_constraint_pins_a_single_flip():
    nl = _netlist(GAPSYM)
    placement = _placed(nl, {"Mp1": (0, 0, 1, 1),
                             "Mn1": (1, 0, 1, 1), "Mn2": (1, 2, 1, 1)})
    mapping = die_orientation_map(nl, placement)
    # pristine Mn2 would face B against B across a break gap: flipped
    assert mapping["Mn2"] == ("C", "B")
    assert mapping["Mn1"] == ("A", "B")


def test_unpinned_singles_default_pristine_deterministically():
    # two abutting singles whose pristine facing nets differ: no single
    # view can be pinned from one side, so the joint enumeration takes
    # the FIRST satisfying vector in pristine-first order -- here
    # (flipped, pristine)
    nl = _netlist("""\
.subckt SYM VCC P Q GND
Mp1 Q P VCC VCC PMOS W=0.5u L=0.05u
Mp2 P Q VCC VCC PMOS W=0.5u L=0.05u
Mn1 Q P GND GND NMOS W=0.5u L=0.05u
Mn2 P Q GND GND NMOS W=0.5u L=0.05u
.ends SYM
""")
    placement = _placed(nl, {"Mp1": (0, 0, 1, 1), "Mp2": (0, 1, 1, 1),
                             "Mn1": (1, 0, 1, 1), "Mn2": (1, 1, 1, 1)})
    views = die_orientation(nl, placement)
    by_first = {v.members[0].device.name: v for v in views}
    assert by_first["Mp1"].flipped is True
    assert by_first["Mp2"].flipped is False
    mapping = die_orientation_map(nl, placement)
    assert mapping["Mp1"] == ("Q", "VCC")
    assert mapping["Mp2"] == ("VCC", "P")
    assert (_shape(die_orientation(nl, placement)) == _shape(views))


def test_die_orientation_is_deterministic():
    nl = _netlist(FLIPSINGLE)
    placement = _placed(nl, {"Mp1": (0, 0, 1, 3), "Mp2": (0, 3, 1, 3),
                             "Mp3": (0, 6, 1, 3),
                             "Mn1": (1, 0, 1, 3), "Mn2": (1, 4, 1, 3),
                             "Mn3": (1, 7, 1, 3)})
    assert (_shape(die_orientation(nl, placement))
            == _shape(die_orientation(nl, placement)))
    assert (die_orientation_map(nl, placement)
            == die_orientation_map(nl, placement))


def test_break_cols_parameter_feeds_the_gap_constraints():
    nl = _netlist(GAPSYM)
    placement = _placed(nl, {"Mp1": (0, 0, 1, 1),
                             "Mn1": (1, 0, 1, 1), "Mn2": (1, 2, 1, 1)})
    # with a two-column break convention the gap of 1 encodes no
    # constraint, so Mn2 keeps its pristine orientation
    loose = die_orientation_map(nl, placement, break_cols=2)
    assert loose["Mn2"] == ("B", "C")
    assert DEFAULT_BREAK_COLS == 1


# ---------------- die_slot_access_points ----------------

def test_slot_access_points_sit_on_true_edge_columns():
    nl = _netlist(INV)
    placement = _placed(nl, {"Mp": (0, 0, 1, 1), "Mn": (1, 0, 1, 1)})
    sig, power = die_slot_access_points(nl, placement)
    # the right terminal sits at start_col + width (its right EDGE),
    # never inset into its own column; points sort by (column, name)
    by = {d.name: d for d in nl.devices}
    assert sig == {"Y": [(1, by["Mn"]), (1, by["Mp"])]}
    assert set(power) == {"VCC", "GND"}
    assert power["VCC"] == [(0, by["Mp"])]
    assert power["GND"] == [(0, by["Mn"])]


def test_multi_region_net_exposed_at_every_slot():
    nl = _netlist(TRIO)
    placement = _placed(nl, {"MpA": (0, 0, 1, 1), "MpB": (0, 1, 1, 1),
                             "MpC": (0, 2, 1, 1),
                             "MnA": (1, 0, 1, 1), "MnB": (1, 1, 1, 1),
                             "MnC": (1, 2, 1, 1)})
    sig, _power = die_slot_access_points(nl, placement)
    by = {d.name: d for d in nl.devices}
    # Y occupies slots 1 and 3 of each row: both are access points even
    # though Y is no block end anywhere (points sort by (column, name))
    assert sig["Y"] == [(1, by["MnA"]), (1, by["MpA"]),
                        (3, by["MnC"]), (3, by["MpC"])]


def test_internal_single_region_junction_gets_no_access():
    nl = _netlist("""\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB Y B VCC VCC PMOS W=0.5u L=0.05u
MnA n1 A GND GND NMOS W=0.5u L=0.05u
MnB Y B n1 GND NMOS W=0.5u L=0.05u
.ends NAND2
""")
    placement = _placed(nl, {"MpA": (0, 0, 1, 1), "MpB": (0, 1, 1, 1),
                             "MnA": (1, 0, 1, 1), "MnB": (1, 1, 1, 1)})
    sig, power = die_slot_access_points(nl, placement)
    # the series junction n1 occupies one interior slot and is complete
    # through diffusion: no contact (matching geometry.contact_nets)
    assert "n1" not in sig
    assert "n1" not in power
    assert "Y" in sig
    assert {"VCC", "GND"} <= set(power)


def test_slot_access_points_follow_the_die_orientation():
    nl = _netlist(MIRROPAR)
    placement = _placed(nl, {"MpA": (0, 3, 1, 3), "MpB": (0, 0, 1, 3),
                             "MnA": (1, 0, 1, 3), "MnB": (1, 3, 1, 3)})
    sig, power = die_slot_access_points(nl, placement)
    by = {d.name: d for d in nl.devices}
    # the mirrored P block's die edges: VCC@0, Y@3 (shared), VCC@6 --
    # the pristine walk would have claimed VCC@3 / VCC@6 on foreign
    # columns ("terminal clash")
    assert power["VCC"] == [(0, by["MpB"]), (6, by["MpA"])]
    # Y is the block's internal shared edge (one slot per row, not a
    # block end): electrically complete through diffusion, no access
    assert "Y" not in sig


def test_slot_access_points_are_deterministic():
    nl = _netlist(TRIO)
    placement = _placed(nl, {"MpA": (0, 0, 1, 1), "MpB": (0, 1, 1, 1),
                             "MpC": (0, 2, 1, 1),
                             "MnA": (1, 0, 1, 1), "MnB": (1, 1, 1, 1),
                             "MnC": (1, 2, 1, 1)})
    assert (die_slot_access_points(nl, placement)
            == die_slot_access_points(nl, placement))


@pytest.mark.parametrize("netlist_sp,spec", [
    (INV, {"Mp": (0, 0, 1, 1), "Mn": (1, 0, 1, 1)}),
    (TRIO, {"MpA": (0, 0, 1, 1), "MpB": (0, 1, 1, 1), "MpC": (0, 2, 1, 1),
            "MnA": (1, 0, 1, 1), "MnB": (1, 1, 1, 1), "MnC": (1, 2, 1, 1)}),
])
def test_access_edges_agree_with_geometry_row_edges(netlist_sp, spec):
    # the die-view walk reproduces geometry.row_edges' slot sequence on
    # pristine placements (the shared contract with gds_contacts)
    from bigcell_engine.geometry import N_ROW, P_ROW, row_edges
    from smt_engine.netlist import build_diffusion_blocks
    nl = _netlist(netlist_sp)
    placement = _placed(nl, spec)
    leg_widths = {d.name: (placement[d].legs, placement[d].leg_width_cols)
                  for d in nl.devices}
    sig, power = die_slot_access_points(nl, placement)
    got = {}
    for net, pts in list(sig.items()) + list(power.items()):
        got[net] = sorted(c for c, _d in pts)
    # the orderings the geometry module would see: the REAL block
    # decomposition (parallel groups for the shared-drain pairs)
    orderings = {P_ROW: [], N_ROW: []}
    for block in build_diffusion_blocks(nl):
        orderings[P_ROW if block.first.is_p else N_ROW].append(block)
    expected = {}
    for row in (P_ROW, N_ROW):
        for edge, net, _w in row_edges(orderings[row], leg_widths):
            expected.setdefault(net, []).append(edge)
    for net, edges in expected.items():
        assert sorted(edges) == got[net], (net, edges, got[net])
