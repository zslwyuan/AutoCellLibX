"""Unit tests for the SMT cell-synthesis engine (flow/smt_engine)."""
import pytest

from smt_engine import synth_cell
from smt_engine.gds import cell_gds, row_geometry
from smt_engine.layout_model import solve_layout
from smt_engine.netlist import (CellNetlist, build_diffusion_blocks,
                                diffusion_access_points, exposed_net_set,
                                find_parallel_groups, find_series_chains,
                                gate_access_points)
from smt_engine.route_model import _access_points, solve_routing
from smt_cell_placer import parse_spice_subckt

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


def test_chain_and_group_structure():
    nl = CellNetlist(parse_spice_subckt(NAND2))
    chains, internal = find_series_chains(nl)
    assert [d.name for d in chains[0]] == ["MnA", "MnB"]
    assert internal == {"n1"}
    groups = find_parallel_groups(nl)
    assert len(groups) == 1
    assert [d.name for d in groups[0]] == ["MpA", "MpB"]
    blocks = build_diffusion_blocks(nl)
    byKind = {}
    for b in blocks:
        byKind.setdefault(b.kind, []).append(b)
    assert len(byKind["series"]) == 1 and len(byKind["parallel"]) == 1
    # alternating orientation: shared edges same-net
    gp = byKind["parallel"][0]
    assert gp.members[0].right_net == gp.members[1].left_net == "Y"


def test_internal_node_with_gate_is_not_a_chain():
    # a net that is also a gate cannot be a diffusion-sharing point
    sp = """\
.subckt T VCC Y A B GND
M1 Y A n1 GND NMOS W=0.5u L=0.05u
M2 n1 B GND GND NMOS W=0.5u L=0.05u
M3 Y n1 VCC VCC PMOS W=0.5u L=0.05u
.end
"""
    nl = CellNetlist(parse_spice_subckt(sp))
    chains, internal = find_series_chains(nl)
    assert internal == set()        # n1 feeds a gate -> not shareable
    assert len(chains) == 3 and all(len(c) == 1 for c in chains)


def test_exposed_nets_exclude_pure_internal_nodes():
    nl = CellNetlist(parse_spice_subckt(NAND2))
    exposed = exposed_net_set(nl)
    assert "n1" not in exposed
    assert {"VCC", "GND", "Y"} <= exposed


def test_inv_full_chain(tmp_path):
    r = synth_cell(INV, layout_time_s=10, route_time_s=15)
    assert r.ok
    assert r.layout.width_cols == 3
    assert r.route.hseg_count == 1
    lib, pins = cell_gds(r.netlist, r.layout.devices, r.route)
    assert pins and all(p[2] in ("Y", "A", "VCC", "GND") for p in pins)


def test_nand2_full_chain():
    r = synth_cell(NAND2, layout_time_s=15, route_time_s=25)
    assert r.ok, "violations: %s" % (r.report.violations if r.report else None)
    assert r.layout.width_cols == 6
    assert r.route.hseg_count >= 3
    assert r.route.vseg_count >= 4


def test_nand2_deterministic():
    a = synth_cell(NAND2, layout_time_s=15, route_time_s=25)
    b = synth_cell(NAND2, layout_time_s=15, route_time_s=25)
    assert a.layout.width_cols == b.layout.width_cols
    assert a.route.hseg == b.route.hseg
    assert a.route.col_owner_n == b.route.col_owner_n


def test_power_ends_reach_power_rails():
    nl = CellNetlist(parse_spice_subckt(NAND2))
    sol = solve_layout(nl, time_limit_s=15)
    rt = solve_routing(nl, sol.devices, time_limit_s=25)
    assert rt.ok
    for c in range(rt.width_cols):
        for net, lo, hi, slot in rt.stripes(c):
            if (net in ("VCC", "VDD")):
                assert hi == 5
            if (net in ("GND", "VSS")):
                assert hi == 4


def test_pn_stripes_may_share_a_column():
    """NAND2 packs P and N ends into the same columns (real GSCL45
    NAND2X1 behaviour): both slots of one column may be occupied."""
    nl = CellNetlist(parse_spice_subckt(NAND2))
    sol = solve_layout(nl, time_limit_s=15)
    rt = solve_routing(nl, sol.devices, time_limit_s=25)
    shared = [c for c in range(rt.width_cols)
              if rt.col_owner_n[c] is not None
              and rt.col_owner_p[c] is not None]
    assert shared, "expected at least one P/N shared column"


def test_row_geometry_rails_are_y_ordered():
    railY, rows = row_geometry(2.47, 0.19)
    assert railY[4] < railY[0] < railY[1] < railY[2] < railY[3] < railY[5]


def test_engine_gds_consumed_by_existing_checkers(in_flow, tmp_path):
    """The emitted GDS must pass the repo's own layout-sanity checker
    (with units_per_um=1.0: the engine writes an honest header)."""
    from layout_sanity import check_layout
    r = synth_cell(NAND2, layout_time_s=15, route_time_s=25)
    assert r.ok
    gds = str(tmp_path / "nand2.gds")
    lib, pins = cell_gds(r.netlist, r.layout.devices, r.route)
    lib.write_gds(gds)
    report = check_layout(gds, units_per_um=1.0)
    assert report.ok(), report.as_dict()


def test_unroutable_cell_reports_cleanly():
    """A cell the model cannot route must fail loudly, not silently."""
    sp = """\
.subckt BIG VCC Y A B C GND
Mp Y A n1 VCC PMOS W=1.0u L=0.05u
Mn n1 B GND GND NMOS W=1.0u L=0.05u
.end
"""
    r = synth_cell(sp, layout_time_s=5, route_time_s=5)
    # either the model routes it, or the failure is loud and clean
    assert (r.ok
            or (r.route is not None and not r.route.ok
                and r.report is None))
