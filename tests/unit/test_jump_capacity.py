"""The exact model's metal-jump capacity
(smt_engine.route_model build_routing_model jump_m2=True).

The fold-combo campaign's 48 census-(0,0) witnesses bound on METAL-JUMP
CAPACITY (doc/AUDIT_REPORT.md 5.57: the witness cores name
bridge/tjoin/e5same/gjoin) -- and the fd4fee3 vocabulary audit found WHY
the capacity was absent: the span track-change disjuncts (``j2`` for
tjoin, ``j2g`` for gjoin) were emitted alongside the tighter
unconditional ``<= 1 + join`` duplicate, which wins, so the disjuncts
never fired (the dual rule, correctly gated under ``if (not
m2_spans)``, is the working precedent).  ``jump_m2=True`` (requires
``m2_spans``) is the jump build:

- the span track-change disjuncts actually fire (the relaxed inequality
  replaces the tight one);
- a track change may land on or leave an M2 segment (the span joins the
  same-net M2 segment endpoint at its column -- the verify BFS's M2-M2
  merge edge);
- an M2 run's ends may anchor through a LIVE span of the net (at least
  one node via) instead of an adjacent M1 segment (the m2run
  relaxation);
- a diffusion access bar may reach an M2 hop through a node via + span
  (the acccon anchor).

Pins:

- byte-identity: the default and m2_spans builds serialize to their
  pinned COMPLEX0 proto hashes (201ea3e1... / 0526cb39...), the jump
  build to its own (588f6507...); jump_m2=True without m2_spans is the
  default build (a jump rides the span vocabulary);
- THE closure: MUX2X1's census-(0,0) fold-combo witness
  (override M1=2+M4=2+M6=2+M9=2, witness orderings (0, 2) of the
  deterministic row-ordering enumeration) -- INFEASIBLE on the legacy
  build (the recorded ef7a0f8 verdict, machine-reproduced), OPTIMAL on
  the jump build, decoded route verifying cleanly: 8 spans / 4 M2
  segments / 13 node vias, identical across rebuilds.  The witness's
  full chain (verify -> GDS -> layout_sanity) is clean at 1.71 um
  (ASTRAN 1.33, ratio 1.286) -- the campaign's 49th closure;
- determinism (AGENTS.md invariants 8/9): single-worker CP-SAT, sorted
  iteration -- identical routes in-process and across PYTHONHASHSEED.
"""
import hashlib
import itertools
import os
import re

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist, exposed_net_set
from smt_engine.route_model import (build_routing_model,
                                    solve_routing,
                                    verify_style_access_points)
from smt_engine.verify import verify_cell

#: the closure witness (flow/_stage3_check/_foldcombo_census_MUX2X1.json,
#: the campaign's recorded data): combo override and the (p_row, n_row)
#: indices of the census-(0, 0) ordering pair
CLOSURE_OVERRIDE = {"M1": 2, "M4": 2, "M6": 2, "M9": 2}
CLOSURE_WITNESS = (0, 2)

#: the pinned COMPLEX0 proto hashes (flow/_stage3_check/_m2_byteid*.txt,
#: flow/_stage3_check/_jumpcap_byteid.txt)
HASH_DEFAULT = ("201ea3e1d0ea78bfd847e5767ebec4c0fe13d6b9471104077"
                "eb8e1127987dd40")
HASH_SPANS = ("0526cb3924915f6e24b04dd0a047154f788506a6ac7816d0c27"
              "e641e8c88eb23")
HASH_JUMP = ("588f65078c85bf9983c37ac815c9d8e80e8b71085b6dbcca49bed"
             "6991681c653")


_REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def _lib_subckt(name):
    lib_path = os.path.join(_REPO_DIR, "std_celllib",
                            "cellsAstranFriendly.sp")
    lib = open(lib_path).read()
    m = re.search(r"\.subckt\s+%s\b.*?\.ends" % name, lib, re.S | re.I)
    assert m, "%s not in the library" % name
    return m.group(0)


def _mux_cell():
    from bigcell_engine.netlist_ext import fold_devices
    nl = CellNetlist(parse_spice_subckt(_lib_subckt("MUX2X1")))
    return fold_devices(nl)


def _row_orderings(blocks):
    """Every ordering of one row's blocks over all flips (the census
    enumeration, _foldcombo_census.row_orderings)."""
    from bigcell_engine import place_sa as ps
    out = []
    for perm in itertools.permutations(range(len(blocks))):
        for flips in itertools.product((0, 1), repeat=len(blocks)):
            out.append([ps.mirror_block(blocks[i]) if f else blocks[i]
                        for i, f in zip(perm, flips)])
    return out


def _closure_placement():
    """(nl3, lw_f, op, on, placements, w, blocks_view) of the closure
    witness; the census (crossing=0, cage=0) is re-asserted."""
    from bigcell_engine.geometry import layout_cell
    from bigcell_engine.netlist_ext import build_bigcell_blocks, fold_devices
    from bigcell_engine import place_sa as ps
    nl3, lws = _mux_cell()
    _f, lw_f = fold_devices(nl3, fold_overrides=dict(CLOSURE_OVERRIDE))
    blocks = build_bigcell_blocks(nl3)
    p_rows = _row_orderings([b for b in blocks if b.first.is_p])
    n_rows = _row_orderings([b for b in blocks if not b.first.is_p])
    i, j = CLOSURE_WITNESS
    op, on = p_rows[i], n_rows[j]
    exposed = frozenset(exposed_net_set(nl3))
    pv = ps._cage_row_view([ps._entry(b, False, lw_f) for b in op],
                           True, exposed)
    nv_ = ps._cage_row_view([ps._entry(b, False, lw_f) for b in on],
                            False, exposed)
    assert ps._crossing_from_views(pv, nv_, exposed)[0] == 0
    assert ps._cage_from_views(pv, nv_, exposed)[0] == 0
    placements, w = layout_cell(op, on, lw_f)
    return nl3, lw_f, op, on, placements, w, list(op) + list(on)


# --- byte-identity -------------------------------------------------------

def _complex0_hashes():
    from bigcell_engine.engine import _heuristic_placement
    nl = CellNetlist(parse_spice_subckt(
        open(os.path.join(_REPO_DIR, "flow", "outputs", "ctrl",
                          "COMPLEX0.sp")).read()))
    nl3, pl, w, lws, blocks, orderings, _seed_tr = _heuristic_placement(nl)
    acc = verify_style_access_points(nl3, pl, blocks)

    def build(**kw):
        rm = build_routing_model(nl3, pl, width_cols=w + 1, accesses=acc,
                                 **kw)
        return hashlib.sha256(str(rm.model.Proto()).encode()).hexdigest()

    return build


def test_proto_hashes_pinned():
    """The three builds' COMPLEX0 proto hashes: the default and
    m2_spans builds are byte-identical to their pre-extension pins,
    the jump build to its own."""
    build = _complex0_hashes()
    assert build() == HASH_DEFAULT
    assert build(m2_spans=True) == HASH_SPANS
    assert build(m2_spans=True, jump_m2=True) == HASH_JUMP


def test_jump_m2_requires_m2_spans():
    """jump_m2=True without m2_spans is the default build (a jump rides
    the span vocabulary): no span structures, default proto hash."""
    build = _complex0_hashes()
    assert build(m2_spans=False, jump_m2=True) == HASH_DEFAULT
    from bigcell_engine.geometry import layout_cell
    from bigcell_engine.netlist_ext import build_bigcell_blocks
    nl3, lws = _mux_cell()
    blocks = build_bigcell_blocks(nl3)
    op = [b for b in blocks if b.first.is_p]
    on = [b for b in blocks if not b.first.is_p]
    placements, w = layout_cell(op, on, lws)
    rm = build_routing_model(nl3, placements, width_cols=w + 1,
                             m2_spans=False, jump_m2=True)
    assert rm.span_on is None and rm.nv is None


# --- THE closure: jump capacity closes what the legacy build cannot -----

def test_mux2x1_witness_closes_through_jump_capacity():
    """The fold-combo witness is INFEASIBLE on the legacy build (the
    recorded ef7a0f8 verdict: all 48 census-(0,0) witnesses
    INFEASIBLE) and OPTIMAL on the jump build -- the metal-jump
    capacity the witness cores named (bridge/tjoin/e5same/gjoin)."""
    nl3, lw_f, op, on, placements, w, blocks_view = _closure_placement()
    acc = verify_style_access_points(nl3, placements, blocks_view)
    legacy = solve_routing(nl3, placements, width_cols=w + 1,
                           accesses=acc, m2_spans=True, time_limit_s=60.0)
    assert legacy.status_name == "INFEASIBLE"
    jump = solve_routing(nl3, placements, width_cols=w + 1, accesses=acc,
                         m2_spans=True, jump_m2=True, time_limit_s=60.0)
    assert jump.status_name in ("OPTIMAL", "FEASIBLE")
    # the decoded vocabulary shape and the deterministic route makeup
    assert len(jump.m2v) == 8
    assert jump.m2_count == 4
    assert sum(1 for v in jump.m2via.values() if v) == 13
    rep = verify_cell(nl3, placements, jump, blocks=blocks_view)
    assert rep.ok(), rep.violations


def test_mux2x1_jump_closure_deterministic():
    """Two jump solves of the same witness give identical routes
    (invariant 9: single-worker CP-SAT, sorted iteration)."""
    nl3, lw_f, op, on, placements, w, blocks_view = _closure_placement()
    acc = verify_style_access_points(nl3, placements, blocks_view)
    seen = []
    for _ in range(2):
        r = solve_routing(nl3, placements, width_cols=w + 1,
                          accesses=acc, m2_spans=True, jump_m2=True,
                          time_limit_s=60.0)
        seen.append((r.status_name,
                     sorted(r.m2v.items()),
                     sorted(k for k, v in r.m2via.items() if v),
                     sorted(r.hseg.items()),
                     tuple(r.col_owner_n), tuple(r.col_owner_p)))
    assert seen[0] == seen[1]


def _closure_signature():
    """The closure witness's decoded route signature."""
    nl3, lw_f, op, on, placements, w, blocks_view = _closure_placement()
    acc = verify_style_access_points(nl3, placements, blocks_view)
    r = solve_routing(nl3, placements, width_cols=w + 1, accesses=acc,
                      m2_spans=True, jump_m2=True, time_limit_s=60.0)
    return (r.status_name, sorted(r.m2v.items()),
            sorted(k for k, v in r.m2via.items() if v),
            sorted(r.hseg.items()))


def test_jump_closure_deterministic_cross_process_hash_seed(repo_dir):
    """The closure route is identical across processes and hash seeds
    (the test_span_solve_deterministic_cross_process_hash_seed
    discipline, on the jump build)."""
    import subprocess
    import sys
    child = (
        "import sys, os\n"
        "repo = {repo!r}\n"
        "sys.path.insert(0, os.path.join(repo, 'flow'))\n"
        "sys.path.insert(0, repo)\n"
        "from tests.unit.test_jump_capacity import _closure_signature\n"
        "print(_closure_signature())\n"
    ).format(repo=str(repo_dir))
    outs = []
    for seed in ("0", "1"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        proc = subprocess.run([sys.executable, "-c", child], env=env,
                              capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr[-2000:]
        outs.append(proc.stdout.strip())
    assert outs[0] and outs[0] == outs[1], outs


def test_mux2x1_jump_closure_full_chain(tmp_path):
    """The closure chain on the jump build's own route: verify -> GDS
    -> layout_sanity (the M2B evidence chain)."""
    from layout_sanity import check_layout
    from bigcell_engine.gds_cells import write_cell_gds
    nl3, lw_f, op, on, placements, w, blocks_view = _closure_placement()
    acc = verify_style_access_points(nl3, placements, blocks_view)
    r = solve_routing(nl3, placements, width_cols=w + 1, accesses=acc,
                      m2_spans=True, jump_m2=True, time_limit_s=60.0)
    assert r.ok
    rep = verify_cell(nl3, placements, r, blocks=blocks_view)
    assert rep.ok(), rep.violations
    gds = str(tmp_path / "mux2x1_jump_closure.gds")
    write_cell_gds(gds, nl3, placements, w, op, on, lw_f, r)
    sanity = check_layout(gds, units_per_um=1.0)
    assert sanity.ok(), sanity.violations
