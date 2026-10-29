"""The ported ASTRAN router (bigcell_engine.router_port) tests.

Pins the port's three contracts:

- **the graph**: the element graph's node kinds and the verbatim C++
  arc-cost table (the createElement three-way vertical rule, the 495/500
  hub costs, the gate contacts, the M2 directional triple);
- **the solver**: GraphRouter's negotiated-congestion semantics on a
  hand-checkable cell (the unconditional re-claim steal, the
  attempts/stall caps, the pure-C++ phase closing a captured cell);
- **determinism** (AGENTS.md invariants 8/9): identical results in and
  across processes.
"""

import os
import re
import subprocess
import sys

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.verify import verify_cell

from bigcell_engine import router_port
from bigcell_engine.gds_seeds import (EXTRACTED_TABLE, seed_geometry,
                                      seed_orderings)
from bigcell_engine.geometry import layout_cell
from bigcell_engine.router_port import (_ElementRouter, MAX_ATTEMPTS,
                                         STALL_ATTEMPTS, route_cell_ported)

LIB_DECK = os.path.join("..", "std_celllib", "cellsAstranFriendly.sp")


def _load_cell(entry, flow_dir):
    gds = os.path.join(flow_dir, entry["source"])
    if entry["source"].startswith("outputs/"):
        text = open(gds[:-4] + ".sp", errors="ignore").read()
        return CellNetlist(parse_spice_subckt(text))
    name = os.path.basename(entry["source"])[:-4]
    text = open(os.path.join(flow_dir, LIB_DECK), errors="ignore").read()
    blk = re.split(r"\.subckt\s+%s\b" % name, text)[1].split(".ends")[0]
    return CellNetlist(parse_spice_subckt(
        ".subckt %s x\n%s.ends" % (name, blk)))


def _seed_setup(flow_dir, key):
    """(netlist, placement, width, blocks) of one extracted cell's
    arrangement with its measured geometry."""
    entry = EXTRACTED_TABLE[key]
    nl = _load_cell(entry, flow_dir)
    op, on = seed_orderings(nl, entry)
    lws, offs = seed_geometry(entry, None)
    placements, w = layout_cell(op, on, lws, x_offsets=offs)
    return nl, placements, w, list(op) + list(on)


CLKBUF1 = ("CLKBUF1", "8cf4a81927d7")


# --------------------------------------------------------------------------
# the C++'s own budgets and the verbatim cost table
# --------------------------------------------------------------------------

def test_the_cpp_budgets_and_costs_are_verbatim():
    assert MAX_ATTEMPTS == 8000          # autocell2.cpp:470
    assert STALL_ATTEMPTS == 50000       # graphrouter.cpp:165
    assert router_port.STEINER_SWEEPS == 2    # autocell2.cpp:472
    assert router_port.H_MET_COST == 4         # autocell2.cpp:36-38
    assert router_port.VCOST_DIFF == 4         # autocell2.cpp:333/:428
    assert router_port.VCOST_GATE == 16        # autocell2.cpp:304/:375/:463
    assert router_port.V_OUTSIDE_DISCOUNT == 1  # autocell2.cpp:28
    assert router_port.V_CORRIDOR_SURCHARGE == 1  # autocell2.cpp:31
    assert router_port.POLY_ARC_COST == 6      # autocell2.cpp:42/:51
    assert router_port.GATE_CONTACT_COST == 20  # autocell2.cpp:48
    assert router_port.DIFF_CONTACT_COST == 20  # autocell2.cpp:277
    assert router_port.HUB_CORRIDOR_COST == 495  # autocell2.cpp:62
    assert router_port.HUB_COST == 500          # autocell2.cpp:62
    # Router::setup's directional layer-2 triple (router.cpp:54-55)
    assert router_port.M2_H_COST == 4
    assert router_port.M2_V_COST == 11
    assert router_port.VIA_COST == 4


def test_element_graph_builds_the_cpp_node_kinds(flow_dir):
    """The graph carries the C++ kinds: the MET/POL point grids at every
    (track, column), one DIFF per (edge, side) with signal accesses, one
    HUB per column, and M2 only in the metal2 phase."""
    nl, pl, w, blocks = _seed_setup(flow_dir, CLKBUF1)
    grid = _ElementRouter(nl, pl, w, blocks=blocks, tracks="astran13")
    kinds = {}
    for node in grid.graph:
        kinds.setdefault(node.kind[0], 0)
        kinds[node.kind[0]] += 1
    n_tracks = grid.n_tracks
    # the astran13 domain: 16 signal tracks
    assert n_tracks == 16
    assert kinds["MET"] == n_tracks * grid.n_cols
    assert kinds["POL"] == n_tracks * grid.n_cols
    assert kinds["HUB"] == grid.n_cols
    assert "M2" not in kinds          # phase 1 has no metal2
    # DIFF nodes ride the die view's signal accesses: CLKBUF1's
    # parallel pairs internalize every junction (an honest property of
    # the shared access derivation), MUX2X1's series pair exposes Y
    assert "DIFF" not in kinds
    nl2, pl2, w2, blocks2 = _seed_setup(
        flow_dir, ("MUX2X1", "6028a7b039e2"))
    grid2 = _ElementRouter(nl2, pl2, w2, blocks=blocks2,
                           tracks="astran13", metal2=True)
    kinds2 = {}
    for node in grid2.graph:
        kinds2.setdefault(node.kind[0], 0)
        kinds2[node.kind[0]] += 1
    assert kinds2["M2"] == n_tracks * grid2.n_cols
    assert kinds2["DIFF"] >= 2        # Y's P and N junction accesses



def test_vertical_arc_costs_follow_the_createelement_rule(flow_dir):
    """The three-way vertical rule (autocell2.cpp:26-33): outside the
    diffusion spans vcost-1, the well-boundary corridor vcost+1 (non-
    gate columns), else vcost -- with vcost 16 at gate columns, 4
    elsewhere."""
    nl, pl, w, blocks = _seed_setup(flow_dir, CLKBUF1)
    grid = _ElementRouter(nl, pl, w, blocks=blocks, tracks="astran13")
    arcs = grid.arcs
    vcosts = {}
    for arc in arcs:
        k1 = grid.graph[arc.n1].kind
        k2 = grid.graph[arc.n2].kind
        if (k1[0] == "MET" and k2[0] == "MET"
                and k1[2] == k2[2] and abs(k1[1] - k2[1]) == 1):
            vcosts.setdefault((arc.cost, k1[2]), 0)
            vcosts[(arc.cost, k1[2])] += 1
    # vcost 16 gate columns and vcost 4 diffusion columns exist, with
    # the -1 outside variant for both; the +1 corridor variant applies
    # to NON-gate columns only (autocell2.cpp:31 tests type!=GATE), so
    # 5 exists and 17 does not
    assert {c for (c, _col) in vcosts} >= {3, 4, 5, 15, 16}
    assert 5 in {c for (c, _col) in vcosts}    # 4 + 1, a diffusion column
    assert 17 not in {c for (c, _col) in vcosts}


def test_hub_costs_are_495_in_the_corridor(flow_dir):
    """autocell2.cpp:62: the inoutCnt->met arcs cost 495 strictly
    between the N span top and the P span bottom, 500 elsewhere."""
    nl, pl, w, blocks = _seed_setup(flow_dir, CLKBUF1)
    grid = _ElementRouter(nl, pl, w, blocks=blocks, tracks="astran13")
    costs = [a.cost for a in grid.arcs
             if grid.graph[a.n1].kind[0] == "HUB"
             or grid.graph[a.n2].kind[0] == "HUB"]
    assert costs and set(costs) <= {495, 500}
    assert 495 in costs               # the well-boundary corridor


# --------------------------------------------------------------------------
# the solver
# --------------------------------------------------------------------------

def test_routenets_reclaims_by_stealing_like_the_cpp(flow_dir):
    """graphrouter.cpp:135-139 sets graph[node].net UNCONDITIONALLY on
    the re-claim (the C++ steals overlapping nodes back); the port's
    trees therefore match the letter of the C++."""
    nl, pl, w, blocks = _seed_setup(flow_dir, CLKBUF1)
    grid = _ElementRouter(nl, pl, w, blocks=blocks, tracks="astran13")
    assert grid.route(max_attempts=100, optimize=False)
    for net in grid.nets:
        for nid in net.tree:
            # every tree node is owned by its net after the re-claim
            assert grid.graph[nid].net == net.index


def test_the_clkbuf1_capture_closes_through_the_port(flow_dir):
    """The ported router reproduces the first astran13 capture:
    ASTRAN's own CLKBUF1 arrangement routes verify-clean in the pure
    C++ configuration (phase 1, no metal2)."""
    nl, pl, w, blocks = _seed_setup(flow_dir, CLKBUF1)
    route = route_cell_ported(nl, pl, w, blocks=blocks, tracks="astran13")
    assert route.ok, route.fail_note
    assert getattr(route, "router_phase", None) == 1
    report = verify_cell(nl, pl, route, blocks=blocks, tracks="astran13")
    assert report.ok(), report.violations
    # the result covers every placement column + the trailing escape
    assert route.width_cols == w + 1


def test_failed_routes_carry_the_real_width(flow_dir):
    """The failure shape mirrors solve_routing's: UNKNOWN status with
    the real placement width so the consumers never index past it."""
    from bigcell_engine.router_port import _ElementRouter
    nl, pl, w, blocks = _seed_setup(flow_dir, CLKBUF1)
    grid = _ElementRouter(nl, pl, w, blocks=blocks, tracks="astran13")
    grid._fail_note = "synthetic"
    res = grid.failed_result()
    assert res.status_name == "UNKNOWN"
    assert res.width_cols == w + 1
    assert res.fail_note == "synthetic"


# --------------------------------------------------------------------------
# determinism (invariant 9)
# --------------------------------------------------------------------------

_XPROC_HELPER = """
import os, sys
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), ".."))
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.verify import verify_cell
from bigcell_engine.gds_seeds import (EXTRACTED_TABLE, seed_geometry,
                                      seed_orderings)
from bigcell_engine.geometry import layout_cell
from bigcell_engine.router_port import route_cell_ported
from bigcell_engine.route_grid import route_signature
import re
entry = EXTRACTED_TABLE[%(key)r]
text0 = open(os.path.join("..", "std_celllib",
                          "cellsAstranFriendly.sp"),
             errors="ignore").read()
name = os.path.basename(entry["source"])[:-4]
blk = re.split(r"\\s*\\.subckt\\s+%%s\\b" %% name, text0)[1].split(".ends")[0]
nl = CellNetlist(parse_spice_subckt(
    ".subckt %%s x\\n%%s.ends" %% (name, blk)))
op, on = seed_orderings(nl, entry)
lws, offs = seed_geometry(entry, None)
pl, w = layout_cell(op, on, lws, x_offsets=offs)
route = route_cell_ported(nl, pl, w, blocks=list(op) + list(on),
                          tracks="astran13")
print(route.status_name)
print(getattr(route, "router_phase", None))
print(route_signature(route))
print(getattr(route, "fail_note", None))
"""


def test_port_is_deterministic_in_process(flow_dir):
    nl, pl, w, blocks = _seed_setup(flow_dir, CLKBUF1)
    r1 = route_cell_ported(nl, pl, w, blocks=blocks, tracks="astran13")
    r2 = route_cell_ported(nl, pl, w, blocks=blocks, tracks="astran13")
    from bigcell_engine.route_grid import route_signature
    assert route_signature(r1) == route_signature(r2)
    assert getattr(r1, "router_phase", None) == \
        getattr(r2, "router_phase", None)


def test_port_is_deterministic_across_processes(flow_dir, tmp_path):
    """PYTHONHASHSEED 0 vs 1: byte-identical routes (the whole chain --
    seed placement, ported router, conversion)."""
    helper = tmp_path / "port_hash_helper.py"
    helper.write_text(_XPROC_HELPER % {"key": CLKBUF1})
    outs = []
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        res = subprocess.run([sys.executable, str(helper)], cwd=flow_dir,
                             env=env, capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        outs.append(res.stdout)
    assert outs[0] == outs[1]
    assert outs[0].splitlines()[0] == "FEASIBLE"
