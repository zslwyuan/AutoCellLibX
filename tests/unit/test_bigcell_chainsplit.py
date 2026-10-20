"""Unit tests for the chain-split candidate classes in
flow/bigcell_engine/place_sa.py + flow/bigcell_engine/netlist_ext.py
(the arrangement-space extension for the entangled-wall class, AUDIT
5.50/5.52).

The contiguous arrangement space (decomposition variant x block ordering
x block flips) keeps every series chain's diffusion CONTIGUOUS; the
census proved the XOR/MUX/LATCH class (crossing=0, cage=0)-unreachable
there (XOR2X1's 589,824 arrangements, AUDIT 5.50).  The extension lets a
series chain place as TWO sub-chains with its internal node wired by
metal: each split decomposition replaces ONE series chain of the default
decomposition at ONE internal point with two sub-chain blocks whose
facing ends carry the same internal net -- so every consumer's break
rule (place_row, row_edges, die_view, verify, the router) inserts the
gap exactly when the sub-chains sit non-adjacent, and the internal net
becomes multi-region/contactable like a tree block's re-exposed branch
net.  Placed adjacent the pair IS the original block: the split only
ever ADDS arrangements.

The decisive census evidence (contiguous min (0,2)/(0,2)/(0,3) vs
split-space census-(0,0) witnesses on XOR2X1/XNOR2X1/MUX2X1, and the
router-level funnel verdicts) lives in flow/_stage3_check/
_chainsplit_probe.py / _chainsplit_funnel.py + their JSON/log outputs;
these tests pin the MECHANISM: candidate generation (bounded,
deterministic, totality), the adjacency-equivalence and multi-region
semantics every consumer shares, the pool integration (additive, lazy
phase 4 under the no-cage-free-FEASIBLE gate, byte-identical pools for
earlier closers), and cross-process determinism (invariant 9).
"""
import hashlib
import os
import re
import subprocess
import sys

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.die_view import die_slot_access_points
from bigcell_engine import place_sa as ps
from bigcell_engine.geometry import layout_cell, row_edges
from bigcell_engine.netlist_ext import (CHAIN_SPLIT_MAX_DECOMPOSITIONS,
                                        build_bigcell_blocks,
                                        chain_split_decompositions,
                                        fold_devices, row_seeds,
                                        split_chain_in_blocks,
                                        split_points_for_chain)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import (chain_split_classes,
                                     ordering_signature, select_orderings)

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.ends NAND2
"""


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
# candidate generation: bounded, deterministic, total
# --------------------------------------------------------------------------

def test_split_points_are_bounded_and_deterministic():
    assert split_points_for_chain(2) == (1,)
    assert split_points_for_chain(6) == (1, 2, 3, 4, 5)
    long = split_points_for_chain(12)
    assert len(long) <= 4 and list(long) == sorted(long)
    assert all(1 <= p <= 11 for p in long)
    assert long == split_points_for_chain(12)


def test_chain_split_decompositions_total_and_deterministic(xor2):
    nl3, lw, _eop, _eon = xor2
    ref = sorted(d.name for d in nl3.devices)
    a = chain_split_decompositions(nl3)
    b = chain_split_decompositions(nl3)
    assert [(n, p) for n, p, _b in a] == [(n, p) for n, p, _b in b]
    # XOR2X1: four 2-member series chains, one split point each
    assert [(n, p) for n, p, _b in a] == [("M1", 1), ("M10", 1),
                                          ("M3", 1), ("M7", 1)]
    for _n, _p, blocks in a:
        seen = sorted(m.device.name for blk in blocks
                      for m in blk.members)
        assert seen == ref                     # totality
    # the split chain's two sub-chains face each other on the internal net
    n, p, blocks = a[0]
    split_names = {blk.first.name for blk in blocks
                   if blk.kind in ("single", "series")
                   and blk.first.name in (n, "M2")}
    assert len(split_names) == 2
    subs = [blk for blk in blocks if blk.first.name in split_names]
    ends = {blk.members[-1].right_net for blk in subs} \
        | {blk.members[0].left_net for blk in subs}
    assert len(ends & {"a_18_54#"}) == 1       # the internal net shared


def test_chain_split_decompositions_are_capped(xor2):
    """The decomposition count honours the documented cap (exercised via
    its parameter; the constant bounds the pool cost) and the generation
    is content-deterministic."""
    nl3, lw, _eop, _eon = xor2

    def content(decomps):
        return [(n, p, ordering_signature(
                    [b for b in blocks if b.first.is_p],
                    [b for b in blocks if not b.first.is_p]))
                for n, p, blocks in decomps]

    full = chain_split_decompositions(nl3)
    assert len(full) == 4                    # XOR2X1's four 2-chains
    assert content(full) == content(chain_split_decompositions(nl3))
    capped = chain_split_decompositions(nl3, max_decompositions=2)
    assert [(n, p) for n, p, _b in capped] \
        == [("M1", 1), ("M10", 1)]           # sorted (chain, point) prefix
    assert len(capped) <= CHAIN_SPLIT_MAX_DECOMPOSITIONS


def test_split_chain_in_blocks_rejects_non_chains(xor2):
    nl3, lw, _eop, _eon = xor2
    blocks = build_bigcell_blocks(nl3)
    assert split_chain_in_blocks(blocks, "M0", 1) is None   # single
    assert split_chain_in_blocks(blocks, "M1", 0) is None   # not internal
    assert split_chain_in_blocks(blocks, "M1", 2) is None
    assert split_chain_in_blocks(blocks, "NOPE", 1) is None


# --------------------------------------------------------------------------
# semantics: adjacent == contiguous; separated == multi-region metal tie
# --------------------------------------------------------------------------

def test_adjacent_subchains_place_like_the_contiguous_block(xor2):
    """Placed adjacent, the split pair IS the original block (facing
    nets equal -> no break -> shared diffusion): identical placements
    and width, so the split only ever adds arrangements."""
    nl3, lw, _eop, _eon = xor2
    base = build_bigcell_blocks(nl3)
    chain = next(b for b in base if b.kind == "series"
                 and b.first.name == "M1")
    others = [b for b in base if b is not chain]
    name, _point, blocks = chain_split_decompositions(nl3)[0]
    assert name == "M1"
    left = next(b for b in blocks if b.first.name == "M1")
    right = next(b for b in blocks if b.first.name == "M2")
    on = [b for b in base if not b.first.is_p]
    pl1, w1 = layout_cell([chain] + others, on, lw)
    pl2, w2 = layout_cell([left, right] + others, on, lw)
    assert w1 == w2
    assert all(pl1[d].start_col == pl2[d].start_col
               and pl1[d].row == pl2[d].row for d in pl1)


def test_separated_subchains_make_the_internal_net_multiregion(xor2):
    """Separated, the internal net owns two edge slots in one row -> it
    is contactable through the SHARED die view (router == verifier) and
    absent from the accesses while contiguous."""
    nl3, lw, _eop, _eon = xor2
    base = build_bigcell_blocks(nl3)
    chain = next(b for b in base if b.kind == "series"
                 and b.first.name == "M1")
    others = [b for b in base if b is not chain]
    _n, _p, blocks = chain_split_decompositions(nl3)[0]
    left = next(b for b in blocks if b.first.name == "M1")
    right = next(b for b in blocks if b.first.name == "M2")
    on = [b for b in base if not b.first.is_p]
    mid = others[0]
    op_sep = [left, mid, right] + [b for b in others if b is not mid]
    pl_sep, _w = layout_cell(op_sep, on, lw)
    edges = row_edges(op_sep, lw)
    internal = "a_18_54#"
    slots = [c for c, net, _w2 in edges if net == internal]
    assert len(slots) >= 2                   # two regions, one row
    acc_sep, _pow = die_slot_access_points(
        nl3, pl_sep, blocks=list(op_sep) + list(on))
    assert [c for c, _d in acc_sep[internal]] == sorted(set(slots))
    op_adj = [left, right] + others
    pl_adj, _w2 = layout_cell(op_adj, on, lw)
    acc_adj, _pow2 = die_slot_access_points(
        nl3, pl_adj, blocks=list(op_adj) + list(on))
    assert internal not in acc_adj           # shared diffusion: no wire


# --------------------------------------------------------------------------
# the pool classes: same discipline as the variant classes
# --------------------------------------------------------------------------

def test_chain_split_classes_deterministic_and_total(xor2):
    nl3, lw, _eop, _eon = xor2
    a = chain_split_classes(nl3, lw)
    b = chain_split_classes(nl3, lw)
    assert [(k, ordering_signature(o1, o2)) for k, o1, o2 in a] \
        == [(k, ordering_signature(o1, o2)) for k, o1, o2 in b]
    assert a, "XOR2X1's series chains must nominate split classes"
    ref = sorted(d.name for d in nl3.devices)
    for kind, op, on in a:
        assert kind.startswith("split:")
        seen = sorted(m.device.name for row in (op, on)
                      for blk in row for m in blk.members)
        assert seen == ref


def test_chain_split_classes_carry_mirror_and_align_kinds(flow_dir):
    """MUX2X1's split decompositions are small enough for the alignment
    nominees (P=4/N=3 rows): every decomposition nominates the head plus
    its proven both-rows mirrors, and the align classes where the pair
    cap allows."""
    nl3, lw, _eop, _eon = _pipeline(_lib_subckt("MUX2X1", flow_dir))
    classes = chain_split_classes(nl3, lw)
    kinds = [k for k, _o1, _o2 in classes]
    assert any(k.endswith("-flip-both") for k in kinds)
    assert any(k.endswith("-die-both") for k in kinds)
    assert any("-align" in k for k in kinds)   # 18k pairs < the cap


# --------------------------------------------------------------------------
# the lazy phase 4: additive under the no-cage-free-FEASIBLE gate
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


def test_split_phase_is_lazy_behind_the_variant_phases(flow_dir):
    """A chain whose fixed + variant + legacy-twin classes all plateau
    gets the split classes LAST (after every steered and legacy kind);
    the fallback floor cannot worsen (the rank takes the minimum)."""
    nl3, lw, eop, eon = _pipeline(_lib_subckt("XOR2X1", flow_dir))

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        return _fail(6)

    _op, _on, bd = ps.sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router, variant_classes=True)
    kinds = [e["kind"] for e in bd["selection"]["candidates"]]
    split_kinds = [k for k in kinds if k.startswith("split:")]
    assert split_kinds, "phase 4 must join the split classes on a plateau"
    first_split = min(kinds.index(k) for k in split_kinds)
    steered = [k for k in kinds if k.startswith("var:")
               and "-legacy" not in k]
    legacy = [k for k in kinds if k.startswith("var:")
              and "-legacy" in k]
    assert first_split > max(kinds.index(k) for k in steered)
    if legacy:
        assert first_split > max(kinds.index(k) for k in legacy)
    assert bd["selection"]["conflicts"] == 6
    assert bd["selection"]["candidate_count"] == len(kinds)


def test_split_phase_skipped_for_earlier_closers(flow_dir):
    """A cell closing cage-free in the fixed classes never builds the
    split phase (its exact pool, trials and selection are untouched --
    the additive contract)."""
    nl3, lw, eop, eon = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    seen = []

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        seen.append(1)
        return _ok()

    _op, _on, bd = ps.sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router, variant_classes=True)
    assert bd["selection"]["kind"] == "best"
    assert len(seen) == 1                    # short-circuit: phase 4 cold


def test_no_split_phase_without_steering_or_variants(flow_dir):
    """Explicit cage=False chains and variant_classes=False chains keep
    today's exact pools (the split phase is gated on the steered
    production chain)."""
    nl3, lw, eop, eon = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    for kwargs in ({"variant_classes": True, "cage": False},
                   {"variant_classes": False, "cage": True}):
        _op, _on, bd = ps.sa_refine_routable(
            eop, eon, nl3, lw, trial_router=lambda *a, **k: _fail(3),
            **kwargs)
        kinds = [e["kind"] for e in bd["selection"]["candidates"]]
        assert not any(k.startswith("split:") for k in kinds)


# --------------------------------------------------------------------------
# determinism across processes (invariant 9)
# --------------------------------------------------------------------------

_SPLIT_HASH_HELPER = """\
import hashlib, os, sys
sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.netlist_ext import fold_devices
from bigcell_engine.place_sa import chain_split_classes, ordering_signature

nl = CellNetlist(parse_spice_subckt(open(%r).read()))
nl3, lw = fold_devices(nl)
classes = chain_split_classes(nl3, lw)
print(hashlib.sha256(repr([(k, ordering_signature(o1, o2))
                           for k, o1, o2 in classes]).encode())
      .hexdigest())
"""


def test_split_classes_byte_stable_across_processes(flow_dir, tmp_path):
    src = tmp_path / "XOR2X1.sp"
    src.write_text(_lib_subckt("XOR2X1", flow_dir))
    helper = tmp_path / "split_hash_helper.py"
    helper.write_text(_SPLIT_HASH_HELPER % str(src))
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, str(helper)], cwd=os.path.join(flow_dir),
            env=env, capture_output=True, text=True, check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests
