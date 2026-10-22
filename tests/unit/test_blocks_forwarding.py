"""Unit tests for the blocks-forwarding contract (router == verifier).

The bigcell ladder holds an ORIENTATION-AWARE block view (``blocks`` --
the refined orderings the slot placement was built from, engine
``meta["blocks"]``).  Every derivation that turns a placement into
access requirements must consume THAT view when the caller holds it, so
the router's terminals and the verifier's demands are derived from the
same die state.  The forwarding matrix pinned here:

- smt_engine.verify_cell's slot-model derivation forwards ``blocks``
  into die_view.die_slot_access_points (the tree-arrangement fallback
  resolves the die from the exact view, not the trail guess);
- the non-slot derivation (diffusion_access_points' blocks parameter)
  and the blocks-less default keep their historical behaviour;
- bigcell_engine.engine forwards ``blocks=blocks3`` into the rung-3
  router call (route_grid threads it into both phase grids) and into
  _plateau_partial's deterministic re-run, while rung 2's injected
  router keeps its fixed 4-parameter contract (exact placement: the
  pristine view is correct).

The differential case is a tree arrangement (test_die_view's AMBTREE):
the trail reconstruction leaves a die-ambiguous single pristine while
the true block view knows its flip -- the two views demand the access
on DIFFERENT columns, so a route built on one view cannot satisfy a
verifier derived from the other.

Determinism pins (AGENTS.md invariants 8/9) close the file: the full
ladder's outcome is identical in-process and across PYTHONHASHSEED.
"""
import os
import subprocess
import sys

import pytest

from bigcell_engine import engine as eng
from bigcell_engine.engine import synth_cell
from smt_cell_placer import parse_spice_subckt
from smt_engine import die_view
from smt_engine.layout_model import PlacedTransistor
from smt_engine.netlist import BlockMember, CellNetlist, DiffusionBlock
from smt_engine.route_model import BAR_LEVELS, RouteResult
from smt_engine.verify import verify_cell

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.ends NAND2
"""

# the tree-arranged strip from test_die_view.test_blocks_view_resolves_
# a_die_ambiguous_single: the pristine model cannot orient it, the trail
# leaves MpX pristine (S left), the true block view knows the flip
# (VCC left)
AMBTREE = """\
.subckt AMBTREE VCC Q S Y A GND
Mp0 a A VCC VCC PMOS W=0.5u L=0.05u
Mp1 VCC A a VCC PMOS W=0.5u L=0.05u
Ms Y A a VCC PMOS W=0.5u L=0.05u
MpX VCC A S VCC PMOS W=0.5u L=0.05u
Mn Y A GND GND NMOS W=0.5u L=0.05u
.ends AMBTREE
"""


def _netlist(sp):
    return CellNetlist(parse_spice_subckt(sp))


def _ambtree_state():
    nl = _netlist(AMBTREE)
    by = {d.name: d for d in nl.devices}
    placement = {by["Ms"]: PlacedTransistor(0, 0, 1, 1),
                 by["Mp1"]: PlacedTransistor(0, 1, 1, 1),
                 by["Mp0"]: PlacedTransistor(0, 2, 1, 1),
                 by["MpX"]: PlacedTransistor(0, 4, 1, 1),
                 by["Mn"]: PlacedTransistor(1, 0, 1, 1)}
    true_blocks = [
        DiffusionBlock("single", [BlockMember(by["Ms"], "Y", "a")]),
        DiffusionBlock("single", [BlockMember(by["Mp1"], "a", "VCC")]),
        DiffusionBlock("single", [BlockMember(by["Mp0"], "VCC", "a")]),
        DiffusionBlock("single", [BlockMember(by["MpX"], "VCC", "S")]),
        DiffusionBlock("single", [BlockMember(by["Mn"], "GND", "Y")]),
    ]
    return nl, placement, true_blocks


def _empty_route(width_cols):
    """A stripe-less/segment-less RouteResult: verify_cell reports one
    "no stripe" violation per demanded access, so the violation list
    enumerates the derivation's requirement set exactly."""
    return RouteResult(
        "UNKNOWN", [None] * width_cols, [None] * width_cols,
        [0] * width_cols, [0] * width_cols, [BAR_LEVELS - 1] * width_cols,
        [BAR_LEVELS - 1] * width_cols, {}, {}, {}, {},
        [False] * width_cols, [False] * width_cols, width_cols,
        0, 0, 0, 0, 0)


def _demands(report):
    """{(net, col)} demanded on diffusion, parsed from the violations."""
    out = set()
    for v in report.violations:
        for prefix in ("diffusion access ", "power access "):
            if (v.startswith(prefix)):
                head = v[len(prefix):].split(":")[0]
                net, col = head.rsplit("@", 1)
                out.add((net, int(col)))
    return out


# ------------- the verify-side derivation matrix ------------------------

def test_verify_slot_derivation_forwards_blocks():
    """verify_cell's slot-model derivation consumes the supplied view:
    with ``blocks`` the demanded accesses are the TRUE view's (the
    die-ambiguous single's flip applied), without them the trail guess's.
    The two views differ here, so the forwarding is observable."""
    nl, placement, true_blocks = _ambtree_state()
    assert die_view.is_slot_placement(placement)
    # the blocks-less die view (slot_model=True selects the derivation;
    # no blocks -> the trail reconstruction resolves the tree)
    trail = _demands(verify_cell(nl, placement, _empty_route(6),
                                 slot_model=True))
    true = _demands(verify_cell(nl, placement, _empty_route(6),
                                blocks=true_blocks))
    # the differential: the two views demand DIFFERENT access columns
    assert trail != true
    # each matches the die_view derivation it must agree with
    sig_t, pow_t = die_view.die_slot_access_points(nl, placement)
    sig_b, pow_b = die_view.die_slot_access_points(nl, placement,
                                                   blocks=true_blocks)
    assert trail == ({(n, c) for n, pts in sig_t.items()
                      for c, _d in pts}
                     | {(n, c) for n, pts in pow_t.items()
                        for c, _d in pts})
    assert true == ({(n, c) for n, pts in sig_b.items()
                     for c, _d in pts}
                    | {(n, c) for n, pts in pow_b.items()
                       for c, _d in pts})
    # and the flip is the only difference: MpX's edge slot carries
    # S@4/VCC@5 on the trail guess, VCC@4/S@5 on the true view
    assert ("S", 4) in trail and ("VCC", 5) in trail
    assert ("VCC", 4) in true and ("S", 5) in true


def test_verify_slot_model_flag_keeps_forwarding():
    """An explicit slot_model=True derives from the same die view -- the
    forwarded blocks apply there too (the flag only selects the
    derivation, never a different view)."""
    nl, placement, true_blocks = _ambtree_state()
    flagged = _demands(verify_cell(nl, placement, _empty_route(6),
                                   slot_model=True))
    flagged_blocks = _demands(verify_cell(nl, placement, _empty_route(6),
                                          blocks=true_blocks,
                                          slot_model=True))
    # the flag alone never changes the view: two blocks-less runs agree
    assert flagged == _demands(
        verify_cell(nl, placement, _empty_route(6), slot_model=True))
    assert flagged_blocks != flagged


def test_verify_default_path_without_blocks_unchanged():
    """No ``blocks``: the historical behaviour, byte for byte -- a slot
    placement derives via the blocks-less die view (the trail resolves a
    tree), a non-slot placement via the pristine inset walk."""
    nl, placement, _true_blocks = _ambtree_state()
    # slot placement, no blocks: the blocks-less die view (== the direct
    # blocks-less derivation; the forwarding passes None through)
    trail_direct = die_view.die_slot_access_points(nl, placement)
    expected = ({(n, c) for n, pts in trail_direct[0].items()
                 for c, _d in pts}
                | {(n, c) for n, pts in trail_direct[1].items()
                   for c, _d in pts})
    assert _demands(verify_cell(nl, placement, _empty_route(6))) == expected
    # non-slot placement, no blocks: the base walk's requirement set
    from smt_engine.netlist import diffusion_access_points
    nonslot = {d: PlacedTransistor(p.row, p.start_col, p.legs, 3)
               for d, p in placement.items()}
    base_sig, base_pow = diffusion_access_points(nl, nonslot)
    expected = ({(n, c) for n, pts in base_sig.items()
                 for c, _d in pts}
                | {(n, c) for n, pts in base_pow.items()
                   for c, _d in pts})
    assert _demands(verify_cell(nl, nonslot, _empty_route(8))) == expected


def test_verify_partial_blocks_view_falls_back_to_trail():
    """A view that does not cover the netlist exactly is refused
    wholesale (die_view._check_blocks_arg) -- the blocks-less die-view
    derivation (the trail) comes back, never a half-applied view."""
    nl, placement, true_blocks = _ambtree_state()
    partial = _demands(verify_cell(nl, placement, _empty_route(6),
                                   blocks=true_blocks[:4]))
    assert partial == _demands(
        verify_cell(nl, placement, _empty_route(6), slot_model=True))
    assert partial != _demands(verify_cell(nl, placement, _empty_route(6),
                                           blocks=true_blocks))


# ------------- the engine-side wiring -----------------------------------

def test_engine_rung3_forwards_blocks_and_rung2_keeps_contract(
        monkeypatch):
    """The rung-3 router call receives blocks=blocks3 (the same object
    recorded in meta), while rung 2's injected router keeps its fixed
    (netlist, placement, width_cols, leg_widths) signature."""
    captured = {}

    def rung3_router(netlist, placement, width_cols, leg_widths,
                     blocks=None):
        captured["args"] = (netlist, placement, width_cols, leg_widths)
        captured["blocks"] = blocks
        width = max(width_cols,
                    max(p.end_col for p in placement.values())) + 1
        shell = RouteResult(
            "UNKNOWN", [None] * width, [None] * width,
            [0] * width, [0] * width, [BAR_LEVELS - 1] * width,
            [BAR_LEVELS - 1] * width, {}, {}, {}, {},
            [False] * width, [False] * width, width, 0, 0, 0, 0, 0)
        shell.fail_note = None
        return shell

    def rung2_router(*args, **kwargs):
        captured["rung2_args"] = args
        captured["rung2_kwargs"] = kwargs
        width = max(args[2],
                    max(p.end_col for p in args[1].values())) + 1
        shell = RouteResult(
            "UNKNOWN", [None] * width, [None] * width,
            [0] * width, [0] * width, [BAR_LEVELS - 1] * width,
            [BAR_LEVELS - 1] * width, {}, {}, {}, {},
            [False] * width, [False] * width, width, 0, 0, 0, 0, 0)
        shell.fail_note = "terminal clash at ('M1', 0, 0): X and Y"
        return shell

    monkeypatch.setattr(eng, "solve_routing",
                        lambda *a, **k: eng._failed_route("INFEASIBLE"))
    monkeypatch.setattr(eng, "_default_grid_router",
                        lambda: rung3_router)
    with pytest.raises(eng.UnsupportedCell) as excinfo:
        synth_cell(_netlist(NAND2), exact_budget_s=20.0,
                   grid_router=rung2_router)
    meta = excinfo.value.meta
    # rung 3: the orientation-aware view travels with the call, and it
    # is THE meta["blocks"] object (router and verifier see one view)
    assert "blocks" in captured
    assert captured["blocks"] is not None
    assert captured["blocks"] is meta["blocks"]
    # rung 2: the injected contract stays 4 positional parameters, no
    # blocks kwarg (exact-engine placement -- the pristine view is right)
    assert len(captured["rung2_args"]) == 4
    assert captured["rung2_kwargs"] == {}


def test_plateau_partial_threads_blocks(monkeypatch):
    """_plateau_partial re-runs _RouteGrid on the SAME view the failed
    router run consumed (route3 is blocks-wired), else it would reproduce
    a different run's plateau."""
    import bigcell_engine.route_grid as rg
    sentinel_route = object()
    recorded = {}

    class _FakeGrid(object):
        def __init__(self, netlist, placement, width_cols, **kwargs):
            recorded.setdefault("blocks", []).append(kwargs.get("blocks"))
            self._fail_note = None

        def structural_diagnosis(self):
            return [], []              # clean: phase 1 runs

        def route(self, max_attempts=1):
            return False               # plateaued: the snapshot is taken

        def build_result(self):
            return sentinel_route

    monkeypatch.setattr(rg, "_RouteGrid", _FakeGrid)
    assert eng._plateau_partial(None, None, 4, blocks="VIEW") \
        is sentinel_route
    # both phase grids consume the caller's block view (the two-phase
    # sequence: phase 1 + the metal2-freedom phase 2)
    assert recorded["blocks"] == ["VIEW", "VIEW"]
    eng._plateau_partial(None, None, 4)
    assert recorded["blocks"][-1] is None


# ------------- full-chain pins (long-running; -m slow) ------------------

def _complex4_netlist(flow_dir):
    sp = open(os.path.join(str(flow_dir), "outputs", "multiplier",
                           "COMPLEX4.sp")).read()
    return _netlist(sp)


def _strip_wall(text):
    """Normalize embedded wall seconds ("CP-SAT proof, 0.5s") out of
    provenance notes -- report-only fields that never feed back into
    results (engine docstring), so the determinism pins compare the
    result-bearing content."""
    import re
    return re.sub(r"\b\d+\.\d+s\b", "<t>", text)


@pytest.mark.slow
def test_complex4_full_chain_honest_and_pool_closer_on_true_view(
        flow_dir):
    """The acceptance state on multiplier/COMPLEX4 (14T, tree-arranged):

    - the FULL chain ends in an honest UnsupportedCell whose rung-3
      attempt routed the TRUE view (the router and the verifier now
      share ``meta["blocks"]``): the selection's blocks-less trial
      ranking (place_sa, outside this task's partition) picks a
      candidate whose true-view window is exactly-unroutable;
    - the pool nevertheless CONTAINS a candidate that routes AND
      verifies clean on the true view -- closure is one selection lever
      away (threading blocks into place_sa's trial router), not a
      routing or verifier gap."""
    nl = _complex4_netlist(flow_dir)
    with pytest.raises(eng.UnsupportedCell) as excinfo:
        synth_cell(nl, exact_budget_s=60.0)
    meta = excinfo.value.meta
    assert meta["blocks"] is not None      # the view travels with rung 3
    rung3_route = [a for a in meta["attempts"]
                   if a["rung"] == 3 and a.get("stage") == "routing"]
    assert rung3_route and rung3_route[-1]["ok"] is False
    assert rung3_route[-1]["status"] == "UNKNOWN"

    # the pool closer: the parallel_phase-flip-both variant routes and
    # verifies clean on its own orientation-aware view
    from bigcell_engine.geometry import layout_cell
    from bigcell_engine.netlist_ext import (build_bigcell_blocks,
                                            fold_devices, row_seeds)
    from bigcell_engine.place_euler import euler_orderings
    from bigcell_engine.place_sa import (decomposition_variant_classes,
                                         generate_candidates, sa_refine)
    from bigcell_engine.route_grid import route_cell
    nl3, lw = fold_devices(nl)
    seeds = row_seeds(build_bigcell_blocks(nl3), lw)
    eop, eon = euler_orderings(seeds, lw)
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw, cage=True)
    pool = list(generate_candidates(bp, bn, eop, eon, lw, netlist=nl3))
    pool += [(k, o1, o2) for k, o1, o2 in
             decomposition_variant_classes(nl3, lw, cage=True)]
    closer = None
    for kind, op, on in pool:
        if kind == "var:parallel_phase-flip-both":
            closer = (op, on)
            break
    assert closer is not None, "pool closer candidate vanished"
    placements, width = layout_cell(closer[0], closer[1], lw)
    blocks_view = list(closer[0]) + list(closer[1])
    route = route_cell(nl3, placements, width, lw, blocks=blocks_view)
    assert route.ok, getattr(route, "fail_note", None)
    report = verify_cell(nl3, placements, route, blocks=blocks_view)
    assert report.ok(), report.violations[:4]


@pytest.mark.slow
def test_complex4_chain_deterministic_in_process(flow_dir):
    """AGENTS.md invariant 9 on the acceptance cell: two full synth_cell
    runs in one process give the identical placement and the identical
    (wall-clock-normalized) outcome records."""
    nl = _complex4_netlist(flow_dir)
    outcomes = []
    for _i in range(2):
        with pytest.raises(eng.UnsupportedCell) as excinfo:
            synth_cell(nl, exact_budget_s=60.0)
        outcomes.append(excinfo.value)

    from bigcell_engine.engine import _heuristic_placement
    places = [sorted((d.name, p.row, p.start_col, p.legs,
                      p.leg_width_cols)
                     for d, p in _heuristic_placement(nl)[1].items())
              for _i in range(2)]
    assert places[0] == places[1]

    def canon(exc):
        attempts = [{k: (_strip_wall(v) if isinstance(v, str) else v)
                     for k, v in a.items() if k != "seconds"}
                    for a in exc.meta["attempts"]]
        return _strip_wall(str(exc)), attempts
    assert canon(outcomes[0]) == canon(outcomes[1])


@pytest.mark.slow
def test_complex4_chain_deterministic_across_hash_seeds(repo_dir):
    """Cross-process PYTHONHASHSEED 0/1: the full ladder outcome
    (diagnosis + wall-clock-normalized attempts) is identical
    (invariant 9)."""
    child = (
        "import sys, os, re\n"
        "repo = {repo!r}\n"
        "sys.path.insert(0, os.path.join(repo, 'flow'))\n"
        "sys.path.insert(0, repo)\n"
        "from smt_cell_placer import parse_spice_subckt\n"
        "from smt_engine.netlist import CellNetlist\n"
        "from bigcell_engine.engine import synth_cell\n"
        "sp = open(os.path.join(repo, 'flow', 'outputs', 'multiplier',\n"
        "                       'COMPLEX4.sp')).read()\n"
        "try:\n"
        "    synth_cell(CellNetlist(parse_spice_subckt(sp)),\n"
        "               exact_budget_s=60.0)\n"
        "    print('CLOSED')\n"
        "except Exception as exc:\n"
        "    atts = [{{k: (re.sub(r'\\b\\d+\\.\\d+s\\b', '<t>', v)\n"
        "               if isinstance(v, str) else v)\n"
        "              for k, v in a.items() if k != 'seconds'}}\n"
        "            for a in getattr(exc, 'meta', {{}}).get('attempts',\n"
        "                                                   [])]\n"
        "    print(repr((re.sub(r'\\b\\d+\\.\\d+s\\b', '<t>', str(exc)),\n"
        "               atts)))\n"
    ).format(repo=str(repo_dir))
    outs = []
    for seed in ("0", "1"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        proc = subprocess.run([sys.executable, "-c", child], env=env,
                              capture_output=True, text=True, timeout=900)
        assert proc.returncode == 0, proc.stderr[-2000:]
        outs.append(proc.stdout.strip())
    assert outs[0] and outs[0] == outs[1], outs
