"""Unit tests for the decomposition-variant lever (stage 3, upstream of
the speculate pool).

The conflict evidence (flow/_stage3_check/bench_int3, ctrl/COMPLEX0)
showed the routing plateau surviving EVERY ordering/mirror of one
decomposition, so the lever moved upstream:

- netlist_ext.build_bigcell_blocks' ``variant`` knob builds alternative
  TOTAL decompositions (base / re-phased parallel groups / split
  chains+groups / all-singles / unbounded tree coupling);
- place_sa.decomposition_variant_classes turns them into extra
  speculate candidate classes (per-variant euler+SA best and its
  proven mirror classes, plus alignment nominees -- the aligned P/N
  terminal signal SA's cost cannot see);
- select_orderings(variant_classes=True) joins them as a LAZY second
  phase: a cell that closes in the fixed classes never pays for them,
  a plateau cell gets them ranked exactly like the mirrors.

Acceptance evidence pinned here (the real router, ctrl/COMPLEX0 8T):
the fixed-class pool's best trial score is 4 conflicts (kind
seed-flip-both, full budget 3); the variant pool nominates a
var:singles-align candidate scoring 2 -- strictly better, with the
residual shrinking {cl0#B, cl0#Y, cl1#Y} -> {cl0#a_2_6#}.

All randomness stays inside sa_refine's content-hash discipline; the
variant classes and the selection are pure (invariants 8/9).
"""
import os
import subprocess
import sys

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist, build_diffusion_blocks
from bigcell_engine.netlist_ext import (BLOCK_VARIANTS, _block_shape,
                                        build_bigcell_blocks, fold_devices,
                                        row_seeds)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import (ALIGN_CANDIDATES,
                                     DEFAULT_TRIAL_ATTEMPTS,
                                     alignment_candidates,
                                     decomposition_variant_classes,
                                     generate_candidates,
                                     ordering_signature, sa_refine,
                                     select_orderings)
from bigcell_engine.geometry import N_ROW, P_ROW, layout_cell
from bigcell_engine.route_grid import route_cell

INV = """\
.subckt INV VCC Y A GND
Mp Y A VCC VCC PMOS W=0.5u L=0.05u
Mn Y A GND GND NMOS W=0.5u L=0.05u
.ends INV
"""

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.ends NAND2
"""

AOI21 = """\
.subckt AOI21 VCC Y A B C GND
MpA n1 A VCC VCC PMOS W=0.5u L=0.05u
MpB n1 B VCC VCC PMOS W=0.5u L=0.05u
MpC Y C n1 VCC PMOS W=0.5u L=0.05u
MnA Y A n2 GND NMOS W=0.5u L=0.05u
MnB n2 B GND GND NMOS W=0.5u L=0.05u
MnC Y C GND GND NMOS W=0.25u L=0.05u
.ends AOI21
"""

# two parallel pairs over a shared pure internal net of degree 4: the
# default (degree-3) decomposition keeps two parallel blocks, the
# unbounded max_merge coupling fuses them into one tree trail
DOUBLED = """\
.subckt DOUBLED VCC Y A B GND
MpA n1 A VCC VCC PMOS W=0.5u L=0.05u
MpB n1 B VCC VCC PMOS W=0.5u L=0.05u
MnA n1 A Y GND NMOS W=0.5u L=0.05u
MnB n1 B Y GND NMOS W=0.5u L=0.05u
.ends DOUBLED
"""


def _pipeline(text, **kw):
    nl = CellNetlist(parse_spice_subckt(text))
    nl3, lw = fold_devices(nl)
    blocks = build_bigcell_blocks(nl3, **kw)
    return nl3, lw, blocks


def _check_total(netlist, blocks):
    seen = {}
    for block in blocks:
        for a, b in zip(block.members, block.members[1:]):
            assert a.right_net == b.left_net, (block.kind, block.first.name)
        for member in block.members:
            seen[member.device.name] = seen.get(member.device.name, 0) + 1
        assert len({m.device.is_p for m in block.members}) == 1
    names = [d.name for d in netlist.devices]
    assert sorted(seen) == sorted(names)
    assert all(count == 1 for count in seen.values())


# --------------------------------------------------------------------------
# build_bigcell_blocks variants: totality + the structural differences
# --------------------------------------------------------------------------

def test_every_variant_is_total_and_deterministic():
    for text in (INV, NAND2, AOI21, DOUBLED):
        nl3, _lw, _blocks = _pipeline(text)
        for variant in BLOCK_VARIANTS:
            a = build_bigcell_blocks(nl3, variant=variant)
            b = build_bigcell_blocks(nl3, variant=variant)
            assert _block_shape(a) == _block_shape(b), (text, variant)
            _check_total(nl3, a)


def test_unknown_variant_raises():
    nl3, _lw, _b = _pipeline(NAND2)
    with pytest.raises(ValueError):
        build_bigcell_blocks(nl3, variant="nope")


def test_base_variant_is_the_smt_engine_decomposition():
    for text in (NAND2, AOI21):
        nl3, _lw, _b = _pipeline(text)
        base = build_bigcell_blocks(nl3, variant="base")
        assert _block_shape(base) == \
            _block_shape(build_diffusion_blocks(nl3))


def test_default_equals_base_without_couplers_and_differs_with():
    for text in (INV, NAND2):
        nl3, _lw, _b = _pipeline(text)
        assert _block_shape(build_bigcell_blocks(nl3)) == \
            _block_shape(build_bigcell_blocks(nl3, variant="base"))
    nl3, _lw, _b = _pipeline(AOI21)
    assert any(b.kind == "tree"
               for b in build_bigcell_blocks(nl3))
    assert not any(b.kind == "tree"
                   for b in build_bigcell_blocks(nl3, variant="base"))


def test_max_merge_couples_degree4_units_the_default_leaves_split():
    """DOUBLED's shared net n1 has 4 diffusion terminals and no gate:
    default (degree-3 cap) keeps the two parallel blocks apart;
    max_merge couples its units into a tree trail.  The trail forms for
    the FIRST unit polarity only (the pre-existing coupling rule: same
    polarity per net -- P and N diffusions never share a strip -- with
    the first-sorted unit's polarity as the reference); the other
    polarity's pair keeps its blocks."""
    nl3, _lw, _b = _pipeline(DOUBLED)
    default = build_bigcell_blocks(nl3)
    assert sorted(b.kind for b in default) == ["parallel", "parallel"]
    merged = build_bigcell_blocks(nl3, variant="max_merge")
    trees = [b for b in merged if b.kind == "tree"]
    assert len(trees) == 1 and len(trees[0].members) == 2
    tree = trees[0]
    assert tree.members[0].right_net == \
        tree.members[1].left_net == "n1"
    _check_total(nl3, merged)


def test_parallel_phase_buries_the_smaller_pair_net():
    """build_diffusion_blocks orients a parallel pair so the
    lexicographically LARGER net is the internal shared edge; the phase
    variant swaps that: NAND2's pull-up pair buries VCC and re-exposes
    Y at BOTH block ends -- a structure no flip of the original block
    can express (a flip keeps the internal net)."""
    nl3, _lw, _b = _pipeline(NAND2)
    phase = build_bigcell_blocks(nl3, variant="parallel_phase")
    par = next(b for b in phase if b.kind == "parallel")
    ends = (par.left_net, par.right_net)
    internal = par.members[0].right_net
    assert internal == par.members[1].left_net
    assert internal == "VCC" and set(ends) == {"Y"}
    # the default phase is the complement
    default = build_bigcell_blocks(nl3)
    par0 = next(b for b in default if b.kind == "parallel")
    assert par0.members[0].right_net == "Y"
    _check_total(nl3, phase)


def test_split_variants_dissolve_only_their_kind():
    nl3, _lw, _b = _pipeline(NAND2)
    sp = build_bigcell_blocks(nl3, variant="split_parallel")
    kinds = sorted(b.kind for b in sp)
    assert kinds == ["series", "single", "single"]
    ss = build_bigcell_blocks(nl3, variant="split_series")
    kinds = sorted(b.kind for b in ss)
    assert kinds == ["parallel", "single", "single"]
    singles = build_bigcell_blocks(nl3, variant="singles")
    assert all(b.kind == "single" for b in singles)
    assert len(singles) == len(nl3.devices)
    _check_total(nl3, singles)


# --------------------------------------------------------------------------
# alignment nomination
# --------------------------------------------------------------------------

def _singles_split(blocks):
    return ([b for b in blocks if b.first.is_p],
            [b for b in blocks if not b.first.is_p])


def test_alignment_candidates_are_deterministic_and_total(flow_dir):
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl3, lw, blocks = _pipeline(open(path).read(), variant="singles")
    p_blocks, n_blocks = _singles_split(blocks)
    a = alignment_candidates(p_blocks, n_blocks, lw)
    b = alignment_candidates(p_blocks, n_blocks, lw)
    assert [ordering_signature(op, on) for op, on in a] == \
        [ordering_signature(op, on) for op, on in b]
    assert 1 <= len(a) <= ALIGN_CANDIDATES
    for op, on in a:
        _check_total(nl3, op + on)
    # the nominees sit in the top alignment group: every aligned gate
    # pair the cell can express (4 signal nets have P/N gates) is aligned
    from bigcell_engine.place_sa import _row_terminals
    for op, on in a:
        gates_p, _ep, _bp, _wp = _row_terminals(op, lw)
        gates_n, _en, _bn, _wn = _row_terminals(on, lw)
        cols = set(gates_p) | set(gates_n)
        ga = sum(1 for c in cols
                 if gates_p.get(c, set()) & gates_n.get(c, set()))
        assert ga == 4


def test_alignment_candidates_skip_oversized_rows(flow_dir):
    text = open(os.path.join(flow_dir, "outputs", "ctrl",
                             "COMPLEX11.sp")).read()
    nl3, lw, blocks = _pipeline(text, variant="singles")
    p_blocks, n_blocks = _singles_split(blocks)
    from bigcell_engine.place_sa import _ALIGN_ROW_CAP
    import math
    if (math.factorial(len(p_blocks)) * 2 ** len(p_blocks)
            > _ALIGN_ROW_CAP):
        assert alignment_candidates(p_blocks, n_blocks, lw) == []


# --------------------------------------------------------------------------
# variant candidate classes + the lazy speculate phase
# --------------------------------------------------------------------------

class _FailRouter(object):
    """Counts trial calls; every route fails with the given conflicts."""

    def __init__(self, conflicts):
        self.conflicts = conflicts
        self.calls = 0

    def __call__(self, _nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        self.calls += 1
        from types import SimpleNamespace
        note = ("no conflict-free routing after %d attempts (best %d "
                "conflicts at attempt 2; unresolved: N)"
                % (DEFAULT_TRIAL_ATTEMPTS, self.conflicts))
        return SimpleNamespace(ok=False, fail_note=note,
                               status_name="UNKNOWN",
                               attempts_used=DEFAULT_TRIAL_ATTEMPTS)


class _WidthFeasibleRouter(object):
    """FEASIBLE when the placement is at least ``min_width`` columns."""

    def __init__(self, min_width):
        self.min_width = min_width
        self.calls = 0

    def __call__(self, _nl, _pl, width, _lw, max_attempts=0):
        del max_attempts
        self.calls += 1
        from types import SimpleNamespace
        if width >= self.min_width:
            return SimpleNamespace(ok=True, fail_note=None,
                                   status_name="FEASIBLE", attempts_used=1)
        note = ("no conflict-free routing after %d attempts (best 5 "
                "conflicts at attempt 2; unresolved: N)"
                % DEFAULT_TRIAL_ATTEMPTS)
        return SimpleNamespace(ok=False, fail_note=note,
                               status_name="UNKNOWN",
                               attempts_used=DEFAULT_TRIAL_ATTEMPTS)


def test_variant_classes_skip_default_shaped_variants(flow_dir):
    """base/max_merge cannot produce a new ordering on a coupler-free
    cell (their block shape IS the default's) -- they cost nothing."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl3, lw, _b = _pipeline(open(path).read())
    classes = decomposition_variant_classes(nl3, lw)
    kinds = [k for k, _op, _on in classes]
    assert "var:base" not in kinds and "var:max_merge" not in kinds
    assert "var:singles" in kinds
    assert any(k.startswith("var:singles-align") for k in kinds)
    sigs = [ordering_signature(op, on) for _k, op, on in classes]
    assert len(sigs) == len(set(sigs))
    again = decomposition_variant_classes(nl3, lw)
    assert kinds == [k for k, _op, _on in again]


def test_variant_classes_carry_every_device_once(flow_dir):
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl3, lw, _b = _pipeline(open(path).read())
    for _kind, op, on in decomposition_variant_classes(nl3, lw):
        _check_total(nl3, op + on)


def test_select_short_circuits_before_the_variant_phase():
    """A cell closing in the fixed classes never builds the variant
    classes (the first FEASIBLE candidate wins in pool order)."""
    nl3, lw, blocks = _pipeline(NAND2)
    seeds = row_seeds(blocks, lw)
    eop, eon = euler_orderings(seeds, lw)
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw, iterations=2, quality=2.0,
                            init_moves=100)
    router = _WidthFeasibleRouter(0)          # every candidate routes
    _op, _on, report = select_orderings(bp, bn, eop, eon, nl3, lw,
                                        trial_router=router,
                                        variant_classes=True)
    assert report["feasible"] and report["selected"] == 0
    assert report["kind"] == "best"
    assert router.calls == 1
    assert all(not e["kind"].startswith("var:")
               for e in report["candidates"])


def test_select_phase2_extends_the_pool_when_nothing_routes(flow_dir):
    """When every fixed class fails its trial, the variant classes join
    the pool and are trialed like the mirrors (fallback = lowest
    conflicts, cost, index)."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl3, lw, blocks = _pipeline(open(path).read())
    seeds = row_seeds(blocks, lw)
    eop, eon = euler_orderings(seeds, lw)
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
    router = _FailRouter(9)
    _op, _on, report = select_orderings(bp, bn, eop, eon, nl3, lw,
                                        trial_router=router,
                                        variant_classes=True)
    kinds = [e["kind"] for e in report["candidates"]]
    assert len(kinds) > 10                    # the pool grew
    assert any(k.startswith("var:") for k in kinds)
    assert report["selected"] == 0            # ties -> pool head wins
    assert report["candidate_count"] == len(kinds)


def test_select_phase2_feasible_variant_wins():
    """A variant candidate that routes beats every failing fixed
    candidate (first FEASIBLE in pool priority order)."""
    nl3, lw, blocks = _pipeline(DOUBLED)
    seeds = row_seeds(blocks, lw)
    eop, eon = euler_orderings(seeds, lw)
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw, iterations=2, quality=2.0,
                            init_moves=100)
    fixed_width = layout_cell(bp, bn, lw)[1]
    router = _WidthFeasibleRouter(fixed_width + 1)
    op, on, report = select_orderings(bp, bn, eop, eon, nl3, lw,
                                      trial_router=router,
                                      variant_classes=True)
    assert report["feasible"] and report["conflicts"] == 0
    assert report["kind"].startswith("var:")
    assert report["selected"] >= 10
    assert layout_cell(op, on, lw)[1] >= fixed_width + 1


def test_select_phase2_is_deterministic_in_process(flow_dir):
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl3, lw, blocks = _pipeline(open(path).read())
    seeds = row_seeds(blocks, lw)
    eop, eon = euler_orderings(seeds, lw)
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)

    def run():
        router = _FailRouter(4)
        _op, _on, report = select_orderings(bp, bn, eop, eon, nl3, lw,
                                            trial_router=router,
                                            variant_classes=True)
        return report

    a, b = run(), run()
    assert a["candidates"] == b["candidates"]
    assert (a["selected"], a["kind"], a["conflicts"]) == \
        (b["selected"], b["kind"], b["conflicts"])


def test_generate_candidates_appends_and_dedupes_extra_classes():
    nl3, lw, _blocks = _pipeline(NAND2)
    seeds = row_seeds(nl3 and build_bigcell_blocks(nl3), lw)
    eop, eon = euler_orderings(seeds, lw)
    base = generate_candidates(eop, eon, eop, eon, lw)
    # genuinely NEW content: the singles decomposition's rows cannot
    # collide with any base class (no parallel/series block there)
    s_blocks = build_bigcell_blocks(nl3, variant="singles")
    s_seeds = row_seeds(s_blocks, lw)
    s_p, s_n = s_seeds[P_ROW], s_seeds[N_ROW]
    extra = [("var:x", s_p, s_n), ("var:x-dup", list(s_p), list(s_n))]
    got = generate_candidates(eop, eon, eop, eon, lw, 100,
                              extra_classes=extra)
    kinds = [k for k, _op, _on in got]
    assert kinds[:len(base)] == [k for k, _op, _on in base]
    assert kinds.count("var:x") == 1          # deduped within the extras
    assert "var:x-dup" not in kinds           # deduped against var:x
    sigs = [ordering_signature(op, on) for _k, op, on in got]
    assert len(sigs) == len(set(sigs))


# --------------------------------------------------------------------------
# the acceptance evidence: ctrl/COMPLEX0 (real router)
# --------------------------------------------------------------------------

def test_ctrl_complex0_variant_candidate_closes_the_cell(flow_dir):
    """THE acceptance, updated by the metal2 freedom: the fixed pool's
    best trial score for ctrl/COMPLEX0 dropped from 4 conflicts to 1
    (the corridor-locked escapes now lift onto metal2) but the fixed
    pool still cannot close -- the gate-contact contest at col 1 is
    beyond metal2 for those orientations.  The variant pool nominates a
    candidate that routes FEASIBLE outright, and the full-budget route
    from the selected ordering CLOSES the cell and verifies clean."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl3, lw, blocks = _pipeline(open(path).read())
    seeds = row_seeds(blocks, lw)
    eop, eon = euler_orderings(seeds, lw)
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
    fixed_p, fixed_n, fixed_report = select_orderings(bp, bn, eop, eon,
                                                      nl3, lw)
    assert not fixed_report["feasible"]
    assert fixed_report["conflicts"] == 1     # the metal2-era trial floor
    sel_p, sel_n, report = select_orderings(bp, bn, eop, eon, nl3, lw,
                                            variant_classes=True)
    assert report["feasible"]                 # STRICTLY better: closed
    assert report["conflicts"] == 0
    assert report["kind"].startswith("var:")
    # the full-budget route from the selected ordering closes and verifies
    placements, width = layout_cell(sel_p, sel_n, lw)
    r = route_cell(nl3, placements, width, lw)
    assert r.ok and r.status_name == "FEASIBLE"
    from smt_engine.verify import verify_cell
    rep = verify_cell(nl3, placements, r, blocks=list(sel_p) + list(sel_n))
    assert rep.ok(), rep.violations[:4]


_SLOT_HASH_HELPER = """\
import hashlib, os, sys
sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.netlist_ext import fold_devices
from bigcell_engine.place_sa import decomposition_variant_classes

SP = %r

nl = CellNetlist(parse_spice_subckt(SP))
nl3, lw = fold_devices(nl)
classes = decomposition_variant_classes(nl3, lw)
shape = [(k, [(b.kind, tuple((m.device.name, m.left_net, m.right_net)
                             for m in b.members)) for b in op]
          + [(b.kind, tuple((m.device.name, m.left_net, m.right_net)
                            for m in b.members)) for b in on])
         for k, op, on in classes]
print(hashlib.sha256(repr(shape).encode()).hexdigest())
"""


def test_variant_classes_are_byte_stable_across_processes(flow_dir,
                                                          tmp_path):
    """Cross-process determinism (invariant 9): identical variant class
    list (kinds + block content) under different PYTHONHASHSEED values."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    helper = tmp_path / "variants_hash_helper.py"
    helper.write_text(_SLOT_HASH_HELPER % open(path).read())
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, str(helper)], cwd=flow_dir,
                              env=env, capture_output=True, text=True,
                              check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests
