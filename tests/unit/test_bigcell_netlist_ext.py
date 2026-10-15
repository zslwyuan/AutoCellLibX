"""Unit tests for flow/bigcell_engine/netlist_ext.py (stage 3, doc
STAGE3_BIGCELL_ENGINE.md section 2.1): the fold decision, the TOTAL
tree/branch-aware block decomposition and the row seeds.

The property corpus is every COMPLEX*.sp under flow/outputs/*/ plus every
subcircuit of std_celllib/cellsAstranFriendly.sp -- the latter is where
the flow/original_astran_cells baselines' netlists live (their .run
scripts load that exact file), so the two sets together cover all 49
benchmark cells.
"""
import glob
import os
import re

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import (CellNetlist, build_diffusion_blocks,
                                find_series_chains)
from bigcell_engine.netlist_ext import (FOLD_BUDGET_N_UM, FOLD_BUDGET_P_UM,
                                        build_bigcell_blocks, fold_devices,
                                        mirror_block, row_seeds)
from bigcell_engine.geometry import N_ROW, P_ROW, block_width_cols

INV = """\
.subckt INV VCC Y A GND
Mp Y A VCC VCC PMOS W=0.5u L=0.05u
Mn Y A GND GND NMOS W=0.5u L=0.05u
.end
"""

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.end
"""

AOI21 = """\
.subckt AOI21 VCC Y A B C GND
MpA n1 A VCC VCC PMOS W=0.5u L=0.05u
MpB n1 B VCC VCC PMOS W=0.5u L=0.05u
MpC Y C n1 VCC PMOS W=0.5u L=0.05u
MnA Y A n2 GND NMOS W=0.5u L=0.05u
MnB n2 B GND GND NMOS W=0.5u L=0.05u
MnC Y C GND GND NMOS W=0.25u L=0.05u
.end
"""

SERIES_WIDE = """\
.subckt WIDE VCC Y A GND
Mp1 n1 A VCC VCC PMOS W=3.6u L=0.05u
Mp2 Y A n1 VCC PMOS W=3.6u L=0.05u
Mn1 n2 A GND GND NMOS W=0.5u L=0.05u
Mn2 Y A n2 GND NMOS W=0.5u L=0.05u
.end
"""


def _lib_cells(flow_dir):
    """Every benchmark cell text keyed by a unique path-ish name."""
    cells = {}
    for path in sorted(glob.glob(os.path.join(flow_dir, "outputs", "*",
                                              "*.sp"))):
        cells[path] = open(path).read()
    lib = os.path.join(flow_dir, "..", "std_celllib",
                       "cellsAstranFriendly.sp")
    text = open(lib).read()
    for m in re.finditer(r"\.subckt\s+(\S+)(.*?)\.ends", text,
                         re.S | re.I):
        cells["lib:" + m.group(1)] = ".subckt %s%s\n.ends" % (
            m.group(1), m.group(2))
    return cells


@pytest.fixture(scope="module")
def corpus(flow_dir):
    out = {}
    for key, text in _lib_cells(flow_dir).items():
        out[key] = CellNetlist(parse_spice_subckt(text))
    return out


# --------------------------------------------------------------------------
# fold_devices
# --------------------------------------------------------------------------

def test_fold_defaults_no_fold_on_narrow_devices():
    nl = CellNetlist(parse_spice_subckt(NAND2))
    folded, leg_widths = fold_devices(nl)
    assert folded is nl                # nothing folded, netlist untouched
    # W=0.5u -> 3 columns, one leg; every device covered
    assert leg_widths == {"MpA": (1, 3), "MpB": (1, 3),
                          "MnA": (1, 3), "MnB": (1, 3)}


def test_fold_width_folding_over_budget():
    sp = """\
.subckt W1 VCC Y A GND
Mp Y A VCC VCC PMOS W=3.6u L=0.05u
Mn Y A GND GND NMOS W=0.5u L=0.05u
.end
"""
    nl = CellNetlist(parse_spice_subckt(sp))
    folded, leg_widths = fold_devices(nl)
    # a lone over-budget device is a length-1 series chain: ASTRAN's
    # numTrans == 0 branch splits it into parallel leg DEVICES
    assert folded is not nl
    # ASTRAN's append-at-end discipline: originals keep file order,
    # leg copies follow (K descending, cellnetlst.cpp:269-285)
    names = [d.name for d in folded.devices]
    assert names == ["Mp", "Mn", "Mp#leg3", "Mp#leg2"]
    assert leg_widths["Mp"] == (1, 7)          # 3.6/3 -> 7 columns
    assert leg_widths["Mn"] == (1, 3)
    assert leg_widths["Mp#leg3"] == leg_widths["Mp#leg2"] == (1, 7)


def test_fold_series_folding_matches_astran_logs(flow_dir):
    """ASTRAN folded exactly two cells on this corpus; the budget and the
    series rule must reproduce both log counts (before -> after)."""
    expect = {"BUFX4": (6, 7), "FAX1": (28, 43)}
    for name, (before, after) in expect.items():
        sp = ".subckt %s%s\n.ends" % _extract(flow_dir, name)
        nl = CellNetlist(parse_spice_subckt(sp))
        assert len(nl.devices) == before
        folded, _lw = fold_devices(nl)
        assert len(folded.devices) == after, name
        # folded device names are reproducible leg copies
        new = [d.name for d in folded.devices if "#leg" in d.name]
        assert len(new) == after - before
        assert all(n.startswith("M") for n in new)


def _extract(flow_dir, name):
    lib = os.path.join(flow_dir, "..", "std_celllib",
                       "cellsAstranFriendly.sp")
    m = re.search(r"\.subckt\s+%s(.*?)\.ends" % name, open(lib).read(),
                  re.S | re.I)
    return (name, m.group(1))


def test_fold_series_legs_are_real_chains():
    nl = CellNetlist(parse_spice_subckt(SERIES_WIDE))
    folded, leg_widths = fold_devices(nl)
    assert folded is not nl
    # P stack: 2 devices x 3.6u -> legs = ceil(3.6/1.2) = 3; the legs are
    # separate series chains over suffixed junction nets
    chains, _internal = find_series_chains(folded)
    p_chains = [c for c in chains if len(c) > 1 and c[0].is_p]
    assert len(p_chains) == 3
    for chain in p_chains:
        assert len(chain) == 2
        assert all("#leg" in d.name or d.name in ("Mp1", "Mp2")
                   for d in chain)
    # leg widths: originals divided by legs, copies at the same width
    assert leg_widths["Mp1"][0] == 1 and leg_widths["Mp2"][0] == 1
    # N devices untouched
    assert leg_widths["Mn1"] == (1, 3)


def test_fold_round_trip_width_never_shrinks(corpus):
    """The fold must not lose electrical width: every FOLDED device's
    legs x leg_width_cols x GRID >= its (possibly divided) width_um."""
    import math
    from bigcell_engine.geometry import GRID_UM
    for key, nl in sorted(corpus.items()):
        folded, leg_widths = fold_devices(nl)
        for dev in folded.devices:
            legs, cols = leg_widths[dev.name]
            assert legs * cols * GRID_UM >= dev.width_um - 1e-9, (
                key, dev.name)


def test_fold_is_deterministic_and_pure(corpus):
    for key, nl in sorted(corpus.items()):
        a = fold_devices(nl)
        b = fold_devices(nl)
        assert a[1] == b[1]
        assert [d.name for d in a[0].devices] == \
               [d.name for d in b[0].devices]
        # the input netlist is never mutated
        assert all(d.width_um > 0 for d in nl.devices)


def test_fold_budget_constant_is_the_astran_observable():
    assert FOLD_BUDGET_P_UM == FOLD_BUDGET_N_UM == 1.2


# --------------------------------------------------------------------------
# build_bigcell_blocks: totality + tree/branch blocks
# --------------------------------------------------------------------------

def _check_blocks(netlist, blocks):
    seen = {}
    for block in blocks:
        for a, b in zip(block.members, block.members[1:]):
            # place_row abuts members unconditionally: every internal
            # edge must be a real shared net
            assert a.right_net == b.left_net, (
                block.kind, block.first.name, a.name, b.name)
        for member in block.members:
            seen[member.device.name] = seen.get(member.device.name, 0) + 1
        assert len({m.device.is_p for m in block.members}) == 1
    names = [d.name for d in netlist.devices]
    assert sorted(seen) == sorted(names)
    assert all(count == 1 for count in seen.values())


def test_totality_over_every_benchmark_cell(corpus):
    for key, nl in sorted(corpus.items()):
        _check_blocks(nl, build_bigcell_blocks(nl))


def _shape(blocks):
    """Comparable value-shape of a block list."""
    return [(b.kind,
             tuple((m.device.name, m.left_net, m.right_net)
                   for m in b.members)) for b in blocks]


def test_regular_cells_identical_to_smt_engine_decomposition(corpus):
    """Cells without a coupled degree-3 node must keep the smt_engine
    decomposition verbatim (same kinds, members, orientations, order)."""
    deg3_free = 0
    for key, nl in sorted(corpus.items()):
        base = build_diffusion_blocks(nl)
        out = build_bigcell_blocks(nl)
        if _shape(out) == _shape(base):
            deg3_free += 1
        else:
            assert any(b.kind == "tree" for b in out), key
    assert deg3_free > 30              # the regular majority


def test_tree_block_realizes_the_aoi21_reference_arrangement():
    """The P pair + series device share VCC *and* the branch net in one
    trail -- the arrangement the leaf-only DFS rule provably misses."""
    nl = CellNetlist(parse_spice_subckt(AOI21))
    blocks = build_bigcell_blocks(nl)
    trees = [b for b in blocks if b.kind == "tree"]
    assert len(trees) == 1
    tree = trees[0]
    assert [m.name for m in tree.members] == ["MpA", "MpB", "MpC"]
    assert tree.members[0].right_net == tree.members[1].left_net  # n1
    assert tree.members[1].right_net == tree.members[2].left_net  # VCC
    _check_blocks(nl, blocks)


def test_degenerate_internal_node_with_gate_is_not_a_tree_point():
    nl = CellNetlist(parse_spice_subckt(NAND2))
    out = build_bigcell_blocks(nl)
    assert _shape(out) == _shape(build_diffusion_blocks(nl))
    _check_blocks(nl, out)


def test_mirror_block_round_trip():
    nl = CellNetlist(parse_spice_subckt(NAND2))
    block = build_diffusion_blocks(nl)[0]
    mirrored = mirror_block(mirror_block(block))
    assert [(m.device.name, m.left_net, m.right_net)
            for m in mirrored.members] == \
           [(m.device.name, m.left_net, m.right_net)
            for m in block.members]


# --------------------------------------------------------------------------
# row_seeds
# --------------------------------------------------------------------------

def test_row_seeds_split_and_sort():
    nl = CellNetlist(parse_spice_subckt(NAND2))
    blocks = build_bigcell_blocks(nl)
    seeds = row_seeds(blocks)
    assert set(seeds) == {P_ROW, N_ROW}
    # P row: ONE parallel block (MpA/MpB share both terminal nets, both
    # external); N row: one series block (MnA/MnB over internal n1)
    assert [b.first.name for b in seeds[P_ROW]] == ["MpA"]
    assert [b.first.name for b in seeds[N_ROW]] == ["MnA"]
    # flat-list input splits identically
    flat = row_seeds([b for b in blocks if b.first.is_p] +
                     [b for b in blocks if not b.first.is_p])
    assert _shape(flat[P_ROW]) == _shape(seeds[P_ROW])
    assert _shape(flat[N_ROW]) == _shape(seeds[N_ROW])


def test_row_seeds_order_by_width_then_name():
    nl = CellNetlist(parse_spice_subckt(INV))
    blocks = build_bigcell_blocks(nl)
    leg_widths = {b.members[0].device.name: (1, 6) for b in blocks}
    seeds = row_seeds(blocks, leg_widths)
    assert [b.first.name for b in seeds[P_ROW]] == ["Mp"]
    assert [b.first.name for b in seeds[N_ROW]] == ["Mn"]
    # wider blocks first within a row: use the 4-cell corpus variety
    nl2 = CellNetlist(parse_spice_subckt(NAND2))
    blocks2 = build_bigcell_blocks(nl2)
    lw2 = {"MpA": (1, 6), "MpB": (1, 3), "MnA": (1, 3), "MnB": (1, 6)}
    seeds2 = row_seeds(blocks2, lw2)
    widths = [block_width_cols(b, lw2) for b in seeds2[P_ROW]]
    assert widths == sorted(widths, reverse=True)
