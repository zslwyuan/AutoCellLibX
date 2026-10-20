"""Unit tests for the crossing-level lever (AUDIT 5.49 -- the
XOR/MUX/TBUF/LATCH 12T class) in flow/bigcell_engine/place_sa.py.

M2B's CP-SAT dissection proved that class binds on CROSSING-SAFETY (M1
landing-point supply): the demanded wire crossings sit inside the power
bars' mandatory coverage bands and no track count lifts them; the
freedom is the PLACEMENT.  The census extends agent H's gate-contact
census one level deeper (:func:`crossing_cage_penalty`, contact
escapable -> crossing escapable): per net, the boundaries its wire MUST
span are checked for a fully-walled escape (level 1: no M1 track free
of foreign forced coverage at either endpoint, no ANCHORED poly escape
-- route_model's E4 run-anchoring needs a same-net gate merge inside
the run, which a plain boundary does not have) and for SOLE-SURVIVOR
lane forcing whose claimed corridor nodes two nets contest (level 2 --
the downstream mechanism that makes the class INFEASIBLE).

This file pins

- the static predicate: closing library arrangements stay clean
  (INVX1/NAND2X1), the class's cost-best arrangements are contested at
  the measured columns, the XOR2X1 production-chain selection carries
  the (3, (3, 4, 5)) corridor-contest map the drop-CS probes named;
- determinism (invariant 9), the selection report plumbing, and the
  FEASIBLE-but-caged tier's crossing tie-break (the fallback ranks stay
  (floor, cost, index)-verbatim -- pinned by test_bigcell_cage);
- the per-cell honesty evidence: the exhaustive census sweeps over the
  four enumerable decomposition variants found NO (crossing=0, cage=0)
  arrangement for any class cell, and every census-floor winner is
  exactly INFEASIBLE -- the placement axis alone does not close the
  class; the next lever is the CP-SAT sufficient-assumptions
  dissection.  The chain-level pin below carries that evidence in the
  report data.

Fast tests use ctrl/COMPLEX0-scale inputs and injected/patched routers;
the XOR2X1 chain evidence runs the real machinery once (module
fixture).  All randomness stays inside sa_refine's content-hash
discipline (invariants 8/9).
"""
import hashlib
import os
import re
import subprocess
import sys

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine import place_sa as ps
from bigcell_engine.netlist_ext import (build_bigcell_blocks, fold_devices,
                                        row_seeds)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import (crossing_cage_penalty,
                                     gate_cage_penalty, sa_refine,
                                     sa_refine_routable, select_orderings,
                                     ordering_signature)

INVX1 = """\
.subckt INVX1 VCC Y A GND
M0 Y A VCC VCC PMOS W=0.5u L=0.05u
M1 Y A GND GND NMOS W=0.25u L=0.05u
.ends INVX1
"""


def _pipeline(text):
    """fold -> blocks -> seeds -> euler: the pre-SA state."""
    nl0 = CellNetlist(parse_spice_subckt(text))
    nl, leg_widths = fold_devices(nl0)
    seeds = row_seeds(build_bigcell_blocks(nl), leg_widths)
    eop, eon = euler_orderings(seeds, leg_widths)
    return nl, leg_widths, eop, eon


def _lib_subckt(cell, flow_dir):
    path = os.path.join(flow_dir, "..", "std_celllib",
                        "cellsAstranFriendly.sp")
    text = open(path, errors="ignore").read()
    return next(m.group(0) for m in re.finditer(
        r"\.subckt\s+%s\b.*?\.ends" % cell, text, re.S | re.I))


# --------------------------------------------------------------------------
# the predicate: clean where the closers are clean, contested where the
# drop-CS probes' violations land, deterministic
# --------------------------------------------------------------------------

def test_closing_arrangements_are_crossing_clean():
    """INVX1's arrangements (euler seed and cost best) offer every
    demanded crossing a lane: the census never contests a closing
    library cell."""
    nl3, lw, eop, eon = _pipeline(INVX1)
    assert crossing_cage_penalty(eop, eon, nl3, lw) == (0, ())
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
    assert crossing_cage_penalty(bp, bn, nl3, lw) == (0, ())


@pytest.mark.parametrize("cell, expected", [
    ("XOR2X1", (5, (0, 1, 2, 4, 5))),
    ("XNOR2X1", (5, (0, 1, 2, 4, 5))),
    ("MUX2X1", (2, (3, 4))),
    ("TBUFX2", (4, (1, 2))),
    ("LATCH", (5, (0, 1, 2, 4, 5))),
])
def test_class_cost_best_arrangements_are_contested(flow_dir, cell,
                                                    expected):
    """The 12T class's cost-best arrangements carry contested
    crossings at exactly the measured columns (the drop-CS probes'
    violation columns cover these; the exact models are INFEASIBLE on
    every one of them)."""
    nl3, lw, eop, eon = _pipeline(_lib_subckt(cell, flow_dir))
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
    assert crossing_cage_penalty(bp, bn, nl3, lw) == expected


def test_predicate_is_deterministic(flow_dir):
    """Pure function of the ordering pair (invariant 9): repeated calls
    agree, the shape is (int, tuple-of-int)."""
    nl3, lw, eop, eon = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    a = crossing_cage_penalty(eop, eon, nl3, lw)
    b = crossing_cage_penalty(eop, eon, nl3, lw)
    assert a == b
    assert isinstance(a[0], int) and isinstance(a[1], tuple)
    assert all(isinstance(c, int) for c in a[1])


# --------------------------------------------------------------------------
# the chain evidence: the production selection carries the corridor
# contest map (the level-2 anatomy the cage census cannot see)
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def xor2x1_chain(flow_dir):
    nl3, lw, eop, eon = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    op, on, bd = sa_refine_routable(eop, eon, nl3, lw,
                                    variant_classes=True)
    return nl3, lw, op, on, bd


def test_xor2x1_chain_selection_contests_the_corridor(xor2x1_chain):
    """THE lever's evidence on the class's smallest cell: the chain's
    selection is gate-cage-clean (cage 0 -- agent H's census sees no
    wall) yet crossing-contested at columns 3/4/5 -- the T3 corridor
    node contests the drop-CS probes named (dropping crossing-safety
    alone flips the exact model OPTIMAL and verify then violates
    exactly there).  The selection report carries the count."""
    nl3, lw, op, on, bd = xor2x1_chain
    assert gate_cage_penalty(op, on, nl3, lw) == (0, ())
    assert crossing_cage_penalty(op, on, nl3, lw) == (3, (3, 4, 5))
    sel = bd["selection"]
    assert sel["cage"] == 0
    assert sel["crossing"] == 3
    assert all("crossing" in e for e in sel["candidates"])


# --------------------------------------------------------------------------
# the selection plumbing: report field + the FEASIBLE-but-caged tier
# tie-break (the fallback ranks stay pinned verbatim -- the pin lives
# in test_bigcell_cage)
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ctrl_pool(flow_dir):
    """(nl3, lw, best_p, best_n, eop, eon) for ctrl/COMPLEX0."""
    nl3, lw, eop, eon = _pipeline(
        open(os.path.join(flow_dir, "outputs", "ctrl",
                          "COMPLEX0.sp")).read())
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
    return nl3, lw, bp, bn, eop, eon


def _ok():
    from types import SimpleNamespace
    return SimpleNamespace(ok=True, fail_note=None,
                           status_name="FEASIBLE", attempts_used=1)


def _fail(conflicts):
    from types import SimpleNamespace
    return SimpleNamespace(
        ok=False,
        fail_note=("no conflict-free routing after 300 attempts (best %d "
                   "conflicts at attempt 2; unresolved: N)" % conflicts),
        status_name="UNKNOWN", attempts_used=300)


def _fail_nofloor():
    """A build-failure RouteResult stub: no conflict count in the note
    -- the _UNROUTABLE class."""
    from types import SimpleNamespace
    return SimpleNamespace(
        ok=False, fail_note="impossible to find a path for net X",
        status_name="UNKNOWN", attempts_used=300)


def test_selection_report_carries_crossing(ctrl_pool):
    """Every trialed candidate and the winner report carry the census
    count next to the cage count."""
    nl3, lw, bp, bn, eop, eon = ctrl_pool
    _op, _on, report = select_orderings(bp, bn, eop, eon, nl3, lw,
                                        trial_router=lambda *a, **k: _ok())
    assert "crossing" in report
    assert all("crossing" in e for e in report["candidates"])


def test_feasible_caged_tie_breaks_crossing_free_first(ctrl_pool,
                                                       monkeypatch):
    """The FEASIBLE-but-caged tier key gains the crossing tie-break:
    equal-cage FEASIBLE candidates rank crossing-free-first (the
    censuses are patched to force the exact tie -- their own values
    are pinned by the tests above; the fallback ranks stay
    (floor, cost, index)-verbatim)."""
    nl3, lw, bp, bn, eop, eon = ctrl_pool
    monkeypatch.setattr(ps, "gate_cage_penalty",
                        lambda *a, **k: (1, (0,)))

    def _crossing(op, on, *a, **k):
        # index 0 = the SA best (pool head), everything else clean
        return (1, (0,)) if op == bp and on == bn else (0, ())

    monkeypatch.setattr(ps, "crossing_cage_penalty", _crossing)
    _op, _on, report = select_orderings(bp, bn, eop, eon, nl3, lw,
                                        trial_router=lambda *a, **k: _ok())
    assert report["feasible"] and report["cage"] == 1
    assert report["crossing"] == 0
    assert report["kind"] == "flip-both"    # first crossing-free caged


def test_fallback_ranks_stay_byte_compatible(ctrl_pool):
    """The no-route fallback keeps the pinned (conflicts, cost, index)
    rank verbatim -- equal (floor, cost) ties resolve by pool index
    exactly as before the crossing lever (test_bigcell_cage's
    contract, re-pinned here against the report's new field)."""
    nl3, lw, bp, bn, eop, eon = ctrl_pool
    _op, _on, report = select_orderings(
        bp, bn, eop, eon, nl3, lw,
        trial_router=lambda *a, **k: _fail(9))
    assert report["selected"] == 0
    assert report["conflicts"] == 9
    assert report["kind"] == "best"


def test_floorless_unroutable_report_crossing(ctrl_pool):
    """Build-failure candidates keep the pinned (cage, cost, index)
    rank and their report entries still carry the crossing census."""
    nl3, lw, bp, bn, eop, eon = ctrl_pool
    _op, _on, report = select_orderings(
        bp, bn, eop, eon, nl3, lw,
        trial_router=lambda *a, **k: _fail_nofloor())
    assert report["kind"] == "die-both"     # the pinned floorless order
    assert all("crossing" in e for e in report["candidates"])


# --------------------------------------------------------------------------
# the alignment nominees: the crossing-aware finalist rank stays
# deterministic and preserves the pinned tail behaviour (the ctrl
# M2-fingerprint pins in test_bigcell_variants guard the order)
# --------------------------------------------------------------------------

def test_alignment_nominees_with_netlist_are_deterministic(flow_dir):
    from bigcell_engine.netlist_ext import build_bigcell_blocks
    nl0 = CellNetlist(parse_spice_subckt(
        open(os.path.join(flow_dir, "outputs", "ctrl",
                          "COMPLEX0.sp")).read()))
    nl3, lw = fold_devices(nl0)
    blocks = build_bigcell_blocks(nl3)
    p_blocks = [b for b in blocks if b.first.is_p]
    n_blocks = [b for b in blocks if not b.first.is_p]
    a = ps.alignment_candidates(p_blocks, n_blocks, lw, limit=4,
                                netlist=nl3)
    b = ps.alignment_candidates(p_blocks, n_blocks, lw, limit=4,
                                netlist=nl3)
    assert [ordering_signature(op, on) for op, on in a] == \
        [ordering_signature(op, on) for op, on in b]
    assert 1 <= len(a) <= 4


# --------------------------------------------------------------------------
# cross-process determinism (invariant 9) on the chain with the new
# report field
# --------------------------------------------------------------------------

_CHAIN_HASH_HELPER = """\
import hashlib, os, re, sys
sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.netlist_ext import build_bigcell_blocks, fold_devices, \\
    row_seeds
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import ordering_signature, sa_refine_routable

text = open("../std_celllib/cellsAstranFriendly.sp",
            errors="ignore").read()
sub = next(m.group(0) for m in re.finditer(
    r"\\.subckt\\s+XOR2X1\\b.*?\\.ends", text, re.S | re.I))
nl = CellNetlist(parse_spice_subckt(sub))
nl3, lw = fold_devices(nl)
seeds = row_seeds(build_bigcell_blocks(nl3), lw)
eop, eon = euler_orderings(seeds, lw)
op, on, bd = sa_refine_routable(eop, eon, nl3, lw, variant_classes=True)
sel = bd["selection"]
print(sel["kind"], sel["conflicts"], sel["cage"], sel["crossing"],
      hashlib.sha256(repr(ordering_signature(op, on)).encode())
      .hexdigest())
"""


def test_class_chain_is_byte_stable_across_processes(flow_dir, tmp_path):
    """Identical selection (kind, conflicts, cage, crossing, signature
    hash) under different PYTHONHASHSEED values (invariant 9)."""
    helper = tmp_path / "crossing_hash_helper.py"
    helper.write_text(_CHAIN_HASH_HELPER)
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, str(helper)], cwd=flow_dir,
                              env=env, capture_output=True, text=True,
                              check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests
