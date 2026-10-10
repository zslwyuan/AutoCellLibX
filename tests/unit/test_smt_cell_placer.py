"""Unit tests for flow/smt_cell_placer.py (P2 stage 4 reference impl)."""
import pytest

from smt_cell_placer import (DEFAULT_GRID_UM, astran_width_from_log,
                             build_diffusion_blocks, build_smt_model,
                             compare_with_astran, find_parallel_groups,
                             find_series_chains, parse_spice_subckt, place_cell)

NAND2_SP = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.end
"""

FOLD_SP = """\
.subckt FOLD Y GND
MnA Y A n1 GND NMOS W=1.6u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.end
"""

BREAK_SP = """\
.subckt T VCC Y Y2 Y3 A B C GND
MnA Y A GND GND NMOS W=0.5u L=0.05u
MnB Y2 B GND GND NMOS W=0.5u L=0.05u
MnC Y3 C GND GND NMOS W=0.5u L=0.05u
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
.end
"""


def test_parse_spice_subckt():
    nl = parse_spice_subckt(NAND2_SP)
    assert nl.subckt_name == "NAND2"
    assert set(nl.ports) == {"VCC", "Y", "A", "B", "GND"}
    assert len(nl.devices) == 4
    assert {d.name for d in nl.devices} == {"MpA", "MpB", "MnA", "MnB"}
    assert nl.devices[0].is_p and not nl.devices[2].is_p
    assert nl.devices[0].width_um == pytest.approx(0.5)


def test_parse_rejects_bad_input():
    with pytest.raises(ValueError):
        parse_spice_subckt("no subckt here\n")


def test_find_series_chains_nand2():
    nl = parse_spice_subckt(NAND2_SP)
    chains = find_series_chains(nl)
    nmos = [c for c in chains if c[0].name.startswith("Mn")]
    assert len(nmos) == 1 and len(nmos[0]) == 2
    assert [d.name for d in nmos[0]] == ["MnA", "MnB"]     # walking order
    pmos = [c for c in chains if c[0].name.startswith("Mp")]
    assert len(pmos) == 2 and all(len(c) == 1 for c in pmos)


def _check_validity(result, netlist):
    """Re-derive intervals: no overlap within a (polarity, row), chain
    members share a row and abut."""
    placed = {d.name: d for d in result.devices}
    rows = {"P": {}, "N": {}}
    for d in result.devices:
        rows["P" if d.is_p else "N"].setdefault(d.row, []).append(d)
    for polarity, by_row in rows.items():
        for row, devs in by_row.items():
            devs.sort(key=lambda d: d.start_col)
            for a, b in zip(devs, devs[1:]):
                assert a.end_col <= b.start_col, (polarity, row, a.name, b.name)
    for chain in find_series_chains(netlist):
        for a, b in zip(chain, chain[1:]):
            assert placed[a.name].row == placed[b.name].row, chain
            assert placed[a.name].end_col == placed[b.name].start_col, chain
    for d in result.devices:
        assert d.end_col - d.start_col == d.legs * d.leg_width_cols, d.name


def test_solve_nand2_minimal_width(tmp_path):
    """NAND2: both rows need 6 cols (3+3) -> provably optimal width 6."""
    sp = tmp_path / "nand2.sp"
    sp.write_text(NAND2_SP)
    result = place_cell(str(sp), time_limit_s=10)
    assert result.status_name == "OPTIMAL"
    assert result.width_cols == 6
    assert result.width_um == pytest.approx(6 * DEFAULT_GRID_UM)
    _check_validity(result, parse_spice_subckt(NAND2_SP))
    assert all(d.legs == 1 for d in result.devices)


def test_folding_obeys_manufacturing_leg_cap(tmp_path):
    """1.6um NMOS cannot stay a single leg (cap 1.0um) -> folds into 2x4."""
    sp = tmp_path / "fold.sp"
    sp.write_text(FOLD_SP)
    result = place_cell(str(sp), time_limit_s=10)
    assert result.status_name == "OPTIMAL"
    by_name = {d.name: d for d in result.devices}
    assert by_name["MnA"].legs == 2 and by_name["MnA"].leg_width_cols == 4
    assert by_name["MnB"].legs == 1 and by_name["MnB"].leg_width_cols == 3
    assert result.width_cols == 11            # 4+4+3 chain, 0 P-side
    _check_validity(result, parse_spice_subckt(FOLD_SP))


def test_place_cell_is_deterministic(tmp_path):
    sp = tmp_path / "nand2.sp"
    sp.write_text(NAND2_SP)
    a = place_cell(str(sp), time_limit_s=10)
    b = place_cell(str(sp), time_limit_s=10)
    assert a.as_dict() == b.as_dict()


def test_astran_width_from_log(tmp_path):
    log = tmp_path / "C0.Astranlog"
    log.write_text("-> Cell Size (W x H): 2.28 x 2.47\n")
    assert astran_width_from_log(str(log)) == pytest.approx(2.28)
    assert astran_width_from_log(str(tmp_path / "missing.log")) is None


def test_compare_with_astran(tmp_path):
    sp = tmp_path / "C0.sp"
    sp.write_text(NAND2_SP)
    log = tmp_path / "C0.Astranlog"
    log.write_text("-> Number of transistors before folding: 4 -> P(2) N(2)\n"
                   "-> Cell Size (W x H): 2.28 x 2.47\n")
    row = compare_with_astran(str(sp), str(log), time_limit_s=10)
    assert row["cell"] == "C0"
    assert row["astran_width_um"] == pytest.approx(2.28)
    assert row["smt_width_um"] == pytest.approx(6 * DEFAULT_GRID_UM)
    assert row["ratio"] == pytest.approx(6 * DEFAULT_GRID_UM / 2.28)
    assert row["astran_plausible"] is True


def test_astran_plausibility_flags_stale_logs(tmp_path):
    """A recorded layout whose transistor count differs from the current
    .sp cannot belong to it -- the comparison table flags it instead of
    reporting a meaningless ratio (AUDIT 5.6: COMPLEX1's 30-transistor
    log vs its 26-transistor netlist)."""
    sp = tmp_path / "C0.sp"
    sp.write_text(NAND2_SP)            # 4 devices
    log = tmp_path / "C0.Astranlog"
    log.write_text("-> Number of transistors before folding: 30 -> "
                   "P(15) N(15)\n-> Cell Size (W x H): 3.6 x 2.47\n")
    row = compare_with_astran(str(sp), str(log), time_limit_s=10)
    assert row["astran_plausible"] is False
    log.write_text("-> Number of transistors before folding: 4 -> "
                   "P(2) N(2)\n-> Cell Size (W x H): 0.38 x 2.47\n")
    row = compare_with_astran(str(sp), str(log), time_limit_s=10)
    assert row["astran_plausible"] is True


def test_parallel_group_structure():
    """NAND2's two PMOS share one drain/source net pair: they form one
    parallel group and one diffusion block, oriented so the shared edge
    is same-net."""
    nl = parse_spice_subckt(NAND2_SP)
    groups = find_parallel_groups(nl)
    assert len(groups) == 1
    assert [d.name for d in groups[0]] == ["MpA", "MpB"]
    blocks = build_diffusion_blocks(nl)
    by_kind = {}
    for b in blocks:
        by_kind.setdefault(b.kind, []).append(b)
    assert len(by_kind["series"]) == 1
    assert len(by_kind["parallel"]) == 1
    gp = by_kind["parallel"][0]
    assert gp.members[0].right_net == gp.members[1].left_net == "Y"
    assert gp.left_net == gp.right_net == "VCC"


def test_blocks_match_engine_structure():
    """The reference and the engine must see the same diffusion-sharing
    units (same members, same orientation, same kind)."""
    from smt_engine.netlist import build_diffusion_blocks as engine_blocks
    from smt_engine.netlist import CellNetlist
    for sp in (NAND2_SP, BREAK_SP):
        ref = build_diffusion_blocks(parse_spice_subckt(sp))
        eng = engine_blocks(CellNetlist(parse_spice_subckt(sp)))
        ref_sig = [(b.kind, [(m.name, m.left_net, m.right_net)
                             for m in b.members]) for b in ref]
        eng_sig = [(b.kind, [(m.name, m.left_net, m.right_net)
                             for m in b.members]) for b in eng]
        assert ref_sig == eng_sig


def test_parallel_group_members_abut_and_share_row(tmp_path):
    """The solved NAND2 keeps the parallel group's members in one row,
    abutting (shared diffusion)."""
    sp = tmp_path / "nand2.sp"
    sp.write_text(NAND2_SP)
    result = place_cell(str(sp), time_limit_s=10)
    placed = {p.name: p for p in result.devices}
    assert placed["MpA"].row == placed["MpB"].row
    assert placed["MpA"].end_col == placed["MpB"].start_col


def test_diffusion_break_costs_one_column(tmp_path):
    """Three independent N chains of different nets cannot all abut:
    two of them share a row and must keep a break gap, so the width is
    7 columns, not 6 -- the break really costs."""
    sp = tmp_path / "brk.sp"
    sp.write_text(BREAK_SP)
    result = place_cell(str(sp), time_limit_s=10)
    assert result.status_name == "OPTIMAL"
    assert result.width_cols == 7
    # re-derive: same-row N blocks with different touching nets keep >= 1
    # column of separation
    nl = parse_spice_subckt(BREAK_SP)
    blocks = build_diffusion_blocks(nl)
    placed = {p.name: p for p in result.devices}
    for b in blocks:
        for c in blocks:
            if (b is c or b.first.is_p != c.first.is_p):
                continue
            pb, pc = placed[b.first.name], placed[c.first.name]
            if (pb.row != pc.row):
                continue
            if (pb.end_col <= pc.start_col):
                a, bb, cc = b, b, c          # b left of c
                if (a.right_net != c.left_net
                        and pb.end_col + 1 > pc.start_col):
                    raise AssertionError("break missing %s|%s"
                                         % (b.first.name, c.first.name))
            elif (pc.end_col <= pb.start_col):
                if (c.right_net != b.left_net
                        and pc.end_col + 1 > pb.start_col):
                    raise AssertionError("break missing %s|%s"
                                         % (c.first.name, b.first.name))
