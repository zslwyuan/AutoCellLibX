"""Unit tests for the research round's two dimensions:

WP1 -- census-guided PAIR-SPLITS (netlist_ext.pair_split_decompositions,
place_sa.pair_split_classes, the lazy phase 5 of select_orderings): the
single-split space's census-(0,0) witnesses are globally walled (AUDIT
5.52), so the split lever composes TWO chains' splits; the pair space is
agent-N-bounded (XOR2X1: 6 compositions x 14.7-17.7M orderings) and the
production pool sees the census-guided top decompositions only.

WP2 -- assumption-core-guided placement fitness (place_sa.
CORE_CRITICAL_NETS / core_critical_nets, the critical_nets parameter of
the two censuses and sa_refine, the core_guided flag of
sa_refine_routable/select_orderings): the AUDIT 5.51 cores' nets gain
the CONNECTIVITY-CRITICAL weighting in the SA cost and the selection
ranks.  Opt-in by construction: flag-off chains and unlisted cells are
byte-identical to the pre-research behaviour (the pinned contracts of
test_bigcell_chainsplit/cage/crossing stay authoritative).

The decisive census evidence (contiguous -> single-split -> pair-split
minima; the funnel verdicts on the witnesses) lives in
flow/_stage3_check/_pairsplit_sweep.py / _pairsplit_funnel.py + their
JSON outputs; these tests pin the MECHANISM (bounded, deterministic,
additive, lazy phase 5 under the no-cage-free-FEASIBLE gate, the
core-score tie-breaks, cross-process determinism -- invariant 9).
"""
import hashlib
import os
import re
import subprocess
import sys

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist, exposed_net_set
from bigcell_engine import place_sa as ps
from bigcell_engine.geometry import layout_cell
from bigcell_engine.netlist_ext import (build_bigcell_blocks,
                                        fold_devices,
                                        pair_split_decompositions,
                                        PAIR_SPLIT_MAX_DECOMPOSITIONS,
                                        row_seeds, split_chain_in_blocks)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import (core_critical_nets,
                                     pair_split_classes,
                                     ordering_signature, select_orderings)


def _lib_subckt(cell, flow_dir):
    path = os.path.join(flow_dir, "..", "std_celllib",
                        "cellsAstranFriendly.sp")
    text = open(path, errors="ignore").read()
    return next(m.group(0) for m in re.finditer(
        r"\.subckt\s+%s\b.*?\.ends" % cell, text, re.S | re.I))


def _pipeline(text):
    nl = CellNetlist(parse_spice_subckt(text))
    nl3, lw = fold_devices(nl)
    seeds = row_seeds(build_bigcell_blocks(nl3), lw)
    eop, eon = euler_orderings(seeds, lw)
    return nl3, lw, eop, eon


@pytest.fixture(scope="module")
def xor2(flow_dir):
    return _pipeline(_lib_subckt("XOR2X1", flow_dir))


# --------------------------------------------------------------------------
# WP1: pair-split decompositions -- bounded, deterministic, total,
# additive (adjacent == contiguous, twice over)
# --------------------------------------------------------------------------

def test_pair_split_decompositions_deterministic_and_capped(xor2):
    nl3, lw, _eop, _eon = xor2
    a = pair_split_decompositions(nl3)
    b = pair_split_decompositions(nl3)
    assert [(x, y) for x, y, _ in a] == [(x, y) for x, y, _ in b]
    # XOR2X1: four 2-member series chains -> 6 two-chain compositions
    assert [(x, y) for x, y, _ in a] == [
        (("M1", 1), ("M10", 1)), (("M1", 1), ("M3", 1)),
        (("M1", 1), ("M7", 1)), (("M10", 1), ("M3", 1)),
        (("M10", 1), ("M7", 1)), (("M3", 1), ("M7", 1))]
    assert len(a) <= PAIR_SPLIT_MAX_DECOMPOSITIONS
    ref = sorted(d.name for d in nl3.devices)
    for _x, _y, blocks in a:
        seen = sorted(m.device.name for blk in blocks
                      for m in blk.members)
        assert seen == ref                     # totality
    # the cap is the sorted prefix (a chain-heavy cell's bound)
    capped = pair_split_decompositions(nl3, max_decompositions=2)
    assert [(x, y) for x, y, _ in capped] == [(("M1", 1), ("M10", 1)),
                                              (("M1", 1), ("M3", 1))]


def test_double_adjacent_pair_split_places_like_the_contiguous_cell(xor2):
    """Both sub-chain pairs adjacent -> the pair-split arrangement IS the
    original contiguous one (identical placements and width): the two-
    split composition only ever ADDS arrangements."""
    nl3, lw, _eop, _eon = xor2
    base = build_bigcell_blocks(nl3)
    chain = next(b for b in base if b.kind == "series"
                 and b.first.name == "M1")
    chain2 = next(b for b in base if b.kind == "series"
                  and b.first.name == "M10")
    others = [b for b in base if b is not chain and b is not chain2]
    (_ca, _pa), (_cb, _pb), blocks = pair_split_decompositions(nl3)[0]
    left = next(b for b in blocks if b.first.name == "M1")
    right = next(b for b in blocks if b.first.name == "M2")
    left2 = next(b for b in blocks if b.first.name == "M10")
    right2 = next(b for b in blocks if b.first.name == "M9")
    on = [b for b in base if not b.first.is_p]
    op0 = [chain, chain2] + [b for b in others if b.first.is_p]
    pl1, w1 = layout_cell(op0, on, lw)
    op1 = [left, right, left2, right2] + [b for b in others
                                          if b.first.is_p]
    pl2, w2 = layout_cell(op1, on, lw)
    assert w1 == w2
    assert all(pl1[d].start_col == pl2[d].start_col
               and pl1[d].row == pl2[d].row for d in pl1)


# --------------------------------------------------------------------------
# WP1: the pair-split classes -- census-guided, bounded, deterministic
# --------------------------------------------------------------------------

XOR_PAIR_COMBOS = ((("M1", 1), ("M10", 1)), (("M1", 1), ("M3", 1)),
                   (("M1", 1), ("M7", 1)), (("M10", 1), ("M3", 1)),
                   (("M10", 1), ("M7", 1)), (("M3", 1), ("M7", 1)))


def _seed_of(nl3, lw, combo):
    (a, pa), (b, pb) = combo
    blocks = split_chain_in_blocks(build_bigcell_blocks(nl3), a, pa)
    blocks = split_chain_in_blocks(blocks, b, pb)
    seeds = row_seeds(blocks, lw)
    return euler_orderings(seeds, lw)


def test_pair_split_classes_deterministic_and_census_guided(xor2):
    nl3, lw, _eop, _eon = xor2
    a = pair_split_classes(nl3, lw)
    b = pair_split_classes(nl3, lw)
    assert [(k, ordering_signature(o1, o2)) for k, o1, o2 in a] \
        == [(k, ordering_signature(o1, o2)) for k, o1, o2 in b]
    assert a, "XOR2X1's chain pairs must nominate pair-split classes"
    ref = sorted(d.name for d in nl3.devices)
    tags = []
    for kind, op, on in a:
        assert kind.startswith("pairsplit:")
        seen = sorted(m.device.name for row in (op, on)
                      for blk in row for m in blk.members)
        assert seen == ref
        tag = kind.split("-")[0]
        if tag not in tags:
            tags.append(tag)
    # the census-guided nomination: at most PAIR_SPLIT_MAX_CLASSES
    # decompositions, ranked by the euler seed's (crossing, cage) with
    # the implementation's sorted-(chain, point) tie-break
    assert len(tags) <= ps.PAIR_SPLIT_MAX_CLASSES
    censused = sorted(
        (ps.crossing_cage_penalty(*_seed_of(nl3, lw, c), nl3, lw)[0],
         ps.gate_cage_penalty(*_seed_of(nl3, lw, c), nl3, lw)[0], c)
        for c in XOR_PAIR_COMBOS)
    first = censused[0][2]
    assert tags[0] == "pairsplit:%s@%d+%s@%d" % (first[0][0], first[0][1],
                                                 first[1][0], first[1][1])


def test_pair_split_classes_carry_mirror_kinds(flow_dir):
    """MUX2X1's pair decompositions are small enough for the alignment
    nominees; every nominated head carries its proven both-rows
    mirrors."""
    nl3, lw, _eop, _eon = _pipeline(_lib_subckt("MUX2X1", flow_dir))
    kinds = [k for k, _o1, _o2 in pair_split_classes(nl3, lw)]
    assert any(k.endswith("-flip-both") for k in kinds)
    assert any(k.endswith("-die-both") for k in kinds)
    assert any("-align" in k for k in kinds)


# --------------------------------------------------------------------------
# WP1: the lazy phase 5 -- additive under the no-cage-free-FEASIBLE gate
# --------------------------------------------------------------------------

def _fail(conflicts):
    from types import SimpleNamespace
    note = ("no conflict-free routing after %d attempts (best %d "
            "conflicts at attempt 2; unresolved: N)"
            % (300, conflicts))
    return SimpleNamespace(ok=False, fail_note=note, status_name="UNKNOWN",
                           attempts_used=300)


def _ok():
    from types import SimpleNamespace
    return SimpleNamespace(ok=True, fail_note=None, status_name="FEASIBLE",
                           attempts_used=1)


def test_pairsplit_phase_is_lazy_behind_all_other_phases(flow_dir):
    """A chain whose fixed + variant + legacy-twin + single-split classes
    all plateau gets the pair-split classes LAST; the fallback floor
    cannot worsen (the rank takes the minimum)."""
    nl3, lw, eop, eon = _pipeline(_lib_subckt("XOR2X1", flow_dir))

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        return _fail(6)

    _op, _on, bd = ps.sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router, variant_classes=True)
    kinds = [e["kind"] for e in bd["selection"]["candidates"]]
    pair_kinds = [k for k in kinds if k.startswith("pairsplit:")]
    assert pair_kinds, "phase 5 must join the pair-split classes"
    first_pair = min(kinds.index(k) for k in pair_kinds)
    steered = [k for k in kinds if k.startswith("var:")
               and "-legacy" not in k]
    legacy = [k for k in kinds if k.startswith("var:")
              and "-legacy" in k]
    split_kinds = [k for k in kinds if k.startswith("split:")]
    assert first_pair > max(kinds.index(k) for k in steered)
    assert first_pair > max(kinds.index(k) for k in split_kinds)
    if legacy:
        assert first_pair > max(kinds.index(k) for k in legacy)
    assert bd["selection"]["conflicts"] == 6
    assert bd["selection"]["candidate_count"] == len(kinds)


def test_pairsplit_phase_skipped_for_earlier_closers(flow_dir):
    """A cell closing cage-free in the fixed classes never builds the
    pair-split phase (the additive contract)."""
    nl3, lw, eop, eon = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    seen = []

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        seen.append(1)
        return _ok()

    _op, _on, bd = ps.sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router, variant_classes=True)
    assert bd["selection"]["kind"] == "best"
    assert len(seen) == 1                    # short-circuit: phase 5 cold


def test_no_pairsplit_phase_without_steering_or_variants(flow_dir):
    """cage=False and variant_classes=False chains keep today's exact
    pools (phase 5 is gated on the steered production chain)."""
    nl3, lw, eop, eon = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    for kwargs in ({"variant_classes": True, "cage": False},
                   {"variant_classes": False, "cage": True}):
        _op, _on, bd = ps.sa_refine_routable(
            eop, eon, nl3, lw, trial_router=lambda *a, **k: _fail(3),
            **kwargs)
        kinds = [e["kind"] for e in bd["selection"]["candidates"]]
        assert not any(k.startswith("pairsplit:") for k in kinds)


# --------------------------------------------------------------------------
# WP2: the core table, the weighted census, the core-guided chain
# --------------------------------------------------------------------------

def test_core_critical_nets_table_and_provenance():
    """The committed table matches the AUDIT 5.51 cores' net sets
    (net-suffixed core members; TBUFX2 deliberately absent -- it closes
    on the production ladder) and unlisted cells get no weighting."""
    assert core_critical_nets("XOR2X1") == ("B", "a_13_43#")
    assert core_critical_nets("XNOR2X1") == ("B", "a_12_41#")
    assert core_critical_nets("MUX2X1") == ("A", "B")
    assert core_critical_nets("LATCH") == ("D", "a_2_6#")
    assert core_critical_nets("DFFNEGX1") == ("Q", "a_66_6#")
    assert core_critical_nets("DFFPOSX1") == ("a_22_6#", "a_34_4#")
    assert core_critical_nets("COMPLEX10") == (
        "cl0#a_2_6#", "cl1#A", "cl1#Y", "cl1#a_13_43#", "cl1#a_2_6#",
        "cl2#B", "cl2#Y", "cl2#a_2_6#", "cl3#A", "cl3#Y")
    assert "cl1#Y" in core_critical_nets("COMPLEX20")
    assert core_critical_nets("TBUFX2") == ()
    assert core_critical_nets("NAND2X1") == ()
    assert core_critical_nets("INVX1") == ()


def test_weighted_census_counts_crit_entities_only_at_the_weight(xor2):
    """weighted = raw + CORE_CENSUS_WEIGHT * critical for both censuses;
    the default (critical_nets=None) keeps the raw count byte-identical.
    The arrangement is XOR2X1's euler seed (raw counts > 0 and a
    non-empty critical subset -- the core nets B/a_13_43# gate there);
    the attribution is cross-checked against the census internals."""
    nl3, lw, eop, eon = xor2
    crit = core_critical_nets("XOR2X1")
    cage_raw, cage_cols = ps.gate_cage_penalty(eop, eon, nl3, lw)
    cage_w, cage_cols_w = ps.gate_cage_penalty(eop, eon, nl3, lw,
                                               critical_nets=crit)
    assert cage_cols == cage_cols_w
    cross_raw, cross_cols = ps.crossing_cage_penalty(eop, eon, nl3, lw)
    cross_w, cross_cols_w = ps.crossing_cage_penalty(eop, eon, nl3, lw,
                                                     critical_nets=crit)
    assert cross_cols == cross_cols_w
    # the attribution, computed directly from the internals
    exposed = frozenset(exposed_net_set(nl3))
    vp = ps._cage_row_view([ps._entry(b, False, lw) for b in eop],
                           True, exposed)
    vn = ps._cage_row_view([ps._entry(b, False, lw) for b in eon],
                           False, exposed)
    _c, _cols, caged_crit = ps._cage_from_views(vp, vn, exposed,
                                                frozenset(crit))
    _x, _xcols, cross_crit = ps._crossing_from_views(vp, vn, exposed,
                                                     frozenset(crit))
    _c0, _cols0, caged_crit0 = ps._cage_from_views(vp, vn, exposed)
    _x0, _xcols0, cross_crit0 = ps._crossing_from_views(vp, vn, exposed)
    assert caged_crit0 == 0 and cross_crit0 == 0
    assert caged_crit > 0 and cross_crit > 0
    assert cage_w == cage_raw + ps.CORE_CENSUS_WEIGHT * caged_crit
    assert cross_w == cross_raw + ps.CORE_CENSUS_WEIGHT * cross_crit


def test_sa_refine_with_critical_nets_keeps_incremental_consistency(xor2):
    """The core-guided SA term (CAGE + CORE weights) survives sa_refine's
    incremental==full assertion at every iteration boundary."""
    nl3, lw, eop, eon = xor2
    crit = core_critical_nets("XOR2X1")
    op, on, bd = ps.sa_refine(eop, eon, nl3, lw, iterations=2,
                              cage=True, critical_nets=crit)
    assert bd["caged_gates_crit"] >= 0
    assert bd["contested_crossings"] >= 0
    assert op and on
    # the unweighted path keeps its exact breakdown shape (no new keys)
    _op2, _on2, bd2 = ps.sa_refine(eop, eon, nl3, lw, iterations=1,
                                   cage=True)
    assert "caged_gates_crit" not in bd2
    assert "contested_crossings" not in bd2


def test_core_guided_fallback_ranks_core_score_before_cost(xor2):
    """On an all-equal measured floor, the core-guided fallback ranks
    core_score BEFORE the legacy cost/pool index -- the core nets' access
    quality dominates the plateau ranking; flag-off keeps today's
    (cost, index) rank, and only the core-guided report carries the
    crit fields."""
    nl3, lw, eop, eon = xor2

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        return _fail(6)

    _op, _on, rep = select_orderings(eop, eon, eop, eon, nl3, lw,
                                     candidate_count=4,
                                     trial_router=router,
                                     core_guided=True)
    entries = rep["candidates"]
    assert all("cage_crit" in e and "crossing_crit" in e
               and "core_score" in e for e in entries)
    for e in entries:
        assert e["core_score"] == ps.CORE_CENSUS_WEIGHT * e["cage_crit"] \
            + e["crossing_crit"]
    best = min(entries, key=lambda e: (e["core_score"], e["cost"],
                                       e["index"]))
    assert rep["selected"] == best["index"]
    # flag-off: today's rank, no crit fields
    seen = []

    def router2(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        seen.append(1)
        return _fail(6)

    _op2, _on2, rep2 = select_orderings(eop, eon, eop, eon, nl3, lw,
                                        candidate_count=4,
                                        trial_router=router2)
    entries2 = rep2["candidates"]
    assert all("core_score" not in e for e in entries2)
    best2 = min(entries2, key=lambda e: (e["cost"], e["index"]))
    assert rep2["selected"] == best2["index"]


def test_core_guided_chain_is_inert_for_unlisted_cells(flow_dir):
    """A cell outside the core table: core_guided=True is a no-op -- the
    selected arrangement matches the flag-off chain byte-for-byte (the
    additive contract for every closing cell)."""
    nl3, lw, eop, eon = _pipeline(_lib_subckt("NAND2X1", flow_dir))
    seen_a, seen_b = [], []

    def router_factory(log):
        def router(_nl, _pl, _w, _lw, max_attempts=0):
            del max_attempts
            log.append(1)
            return _ok()
        return router

    _op1, _on1, rep1 = ps.sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router_factory(seen_a),
        variant_classes=True, core_guided=False)
    _op2, _on2, rep2 = ps.sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router_factory(seen_b),
        variant_classes=True, core_guided=True)
    sel1, sel2 = rep1["selection"], rep2["selection"]
    assert sel1["kind"] == sel2["kind"] == "best"
    assert len(seen_a) == len(seen_b) == 1
    assert ordering_signature(_op1, _on1) == ordering_signature(_op2, _on2)
    assert "core_score" not in sel2


# --------------------------------------------------------------------------
# determinism across processes (invariant 9): both new levers
# --------------------------------------------------------------------------

_RESEARCH_HASH_HELPER = """\
import hashlib, os, re, sys
sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.netlist_ext import (build_bigcell_blocks, fold_devices,
                                        pair_split_decompositions, row_seeds)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import (core_critical_nets,
                                     ordering_signature, pair_split_classes,
                                     sa_refine)

text = open(%r).read()
m = re.search(r"\\.subckt\\s+XOR2X1\\b.*?\\.ends", text, re.S | re.I)
nl = CellNetlist(parse_spice_subckt(m.group(0)))
nl3, lw = fold_devices(nl)
pairs = [(x, y) for x, y, _b in pair_split_decompositions(nl3)]
classes = [(k, ordering_signature(o1, o2))
           for k, o1, o2 in pair_split_classes(nl3, lw)]
seeds = row_seeds(build_bigcell_blocks(nl3), lw)
eop, eon = euler_orderings(seeds, lw)
op, on, bd = sa_refine(eop, eon, nl3, lw, cage=True,
                       critical_nets=core_critical_nets("XOR2X1"))
print(hashlib.sha256(repr((pairs, classes, core_critical_nets("XOR2X1"),
                           bd["caged_gates_crit"],
                           bd["contested_crossings_crit"],
                           ordering_signature(op, on))).encode())
      .hexdigest())
"""


def test_research_levers_byte_stable_across_processes(flow_dir, tmp_path):
    """Cross-process determinism (invariant 9) for BOTH new dimensions:
    the pair-split decompositions/classes and the core-guided refine
    hash identically under different PYTHONHASHSEED values."""
    src = tmp_path / "XOR2X1.sp"
    src.write_text(_lib_subckt("XOR2X1", flow_dir))
    helper = tmp_path / "research_hash_helper.py"
    helper.write_text(_RESEARCH_HASH_HELPER % str(src))
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, str(helper)], cwd=os.path.join(flow_dir),
            env=env, capture_output=True, text=True, check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests
