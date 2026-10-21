"""Unit tests for the fold-variant dimension: fold_devices'
``fold_overrides`` (flow/bigcell_engine/netlist_ext.py) and the
fold-variant candidate classes / lazy phase 6
(flow/bigcell_engine/place_sa.py).

The censused arrangement spaces (contiguous, single/pair-split,
core-guided fitness) all keep the up-front FOLD decision fixed --
``fold_devices`` runs once with the 1.2 um budget default and every
arrangement inherits its block structure.  But the fold decision IS a
placement variable: a device folded into more legs occupies more slot
columns (one gate column per leg, at different x positions), and even
an UNDER-budget device split into 2 legs gives its gate net a second
gate column -- exactly the freedom the assumption cores (AUDIT 5.51)
name as bound (their gate columns land inside the power-coverage bands
no censused arrangement could dodge).

These tests pin the MECHANISM: the override parameter (bounds-checked,
default byte-identical, pure), the core-gated nomination, the class
build (census-guided cap, fold+ordering dedupe, the per-variant trial
context), the lazy phase 6 integration (additive under the
no-cage-free-FEASIBLE gate, after the pair-splits, a fold winner's
report provenance, the honest breakdown against the variant's own leg
map) and cross-process determinism (invariant 9).  The decisive census
evidence (baseline vs fold-variant space on DFFNEGX1/DFFPOSX1/XOR2X1/
MUX2X1/LATCH) lives in flow/_stage3_check/_fold_probe.py + its JSON/log
outputs.
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
from bigcell_engine.geometry import layout_cell
from bigcell_engine.netlist_ext import (build_bigcell_blocks,
                                        fold_devices, row_seeds)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import (fold_signature, fold_variant_classes,
                                     ordering_signature)


NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.ends NAND2
"""

#: a series pair wide enough that BOTH members exceed the 1.2 um budget
#: (the series-fold trigger) -- the Mp1/Mp2 chain folds into
#: ceil(2.5/1.2) = 3 legs by default (n1 is the pure internal junction)
FAT_PAIR = """\
.subckt FATPAIR VCC Y A GND
Mp1 Y A n1 GND PMOS W=2.5u L=0.05u
Mp2 n1 A Y VCC PMOS W=2.5u L=0.05u
Mn1 Y A GND GND NMOS W=0.5u L=0.05u
.ends FATPAIR
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
    return nl, nl3, lw, eop, eon


@pytest.fixture(scope="module")
def xor2(flow_dir):
    return _pipeline(_lib_subckt("XOR2X1", flow_dir))


# --------------------------------------------------------------------------
# fold_devices(fold_overrides): bounds-checked, default byte-identical, pure
# --------------------------------------------------------------------------

def test_default_is_byte_identical(xor2):
    """fold_overrides=None is exactly the unparameterized fold."""
    _nl, nl3, lw, _eop, _eon = xor2
    a_name, a_lw = fold_devices(nl3)
    b_name, b_lw = fold_devices(nl3, fold_overrides=None)
    assert [(d.name, d.gate, d.source, d.drain, d.width_um)
            for d in a_name.devices] \
        == [(d.name, d.gate, d.source, d.drain, d.width_um)
            for d in b_name.devices]
    assert a_lw == b_lw
    assert a_name is b_name          # the no-fold early return


def test_override_rejects_out_of_bounds_legs(xor2):
    _nl, nl3, _lw, _eop, _eon = xor2
    for bad in (0, -1, 1.5, "2", True):
        with pytest.raises(ValueError):
            fold_devices(nl3, fold_overrides={"M9": bad})


def test_override_is_inert_on_unknown_names(xor2):
    """A table may key devices of several cells; unknown names do
    nothing."""
    _nl, nl3, lw, _eop, _eon = xor2
    _n2, lw2 = fold_devices(nl3, fold_overrides={"NOPE": 3, "M0": 1})
    assert lw2 == lw


def test_override_is_pure(xor2):
    _nl, nl3, _lw, _eop, _eon = xor2
    before = [(d.name, d.width_um) for d in nl3.devices]
    fold_devices(nl3, fold_overrides={"M9": 4})
    assert before == [(d.name, d.width_um) for d in nl3.devices]


def test_width_fold_override_splits_an_under_budget_device(xor2):
    """The fold-variant lever's core move: an under-budget device split
    into 2 legs -- (2, 1) in the leg map, netlist unchanged, two gate
    columns for the same net."""
    _nl, nl3, lw, _eop, _eon = xor2
    assert lw["M9"] == (1, 1)              # under budget: default 1 leg
    nl2, lw2 = fold_devices(nl3, fold_overrides={"M9": 2})
    assert nl2 is nl3                      # width folding: no new devices
    assert lw2["M9"] == (2, 1)
    assert lw2["M1"] == (1, 1)             # untouched devices unchanged
    # the split device's gate occupies TWO columns in a placed row
    blocks = build_bigcell_blocks(nl3)
    seeds = row_seeds(blocks, lw2)
    eop, eon = euler_orderings(seeds, lw2)
    placements, _w = layout_cell(eop, eon, lw2)
    m9 = next(d for d in nl3.devices if d.name == "M9")
    assert placements[m9].legs == 2 and placements[m9].leg_width_cols == 1


def test_series_fold_override_sets_the_leg_count():
    """A series chain whose members exceed the budget folds into the
    override's leg count (trigger unchanged); legs = 1 suppresses the
    fold entirely (no #legK copies, no width division).

    The override names the chain's TOTAL leg count: the chain is the
    fold unit (foldingSeries folds the whole stack), so any member's
    override re-decides the whole chain and its members -- originals
    and copies alike -- are exempt from the width-fold pass (a residual
    strip wider than the budget is the caller's DRC choice)."""
    nl = CellNetlist(parse_spice_subckt(FAT_PAIR))
    _n1, lw1 = fold_devices(nl)
    d1, _ = fold_devices(nl)
    d2, lw2 = fold_devices(nl, fold_overrides={"Mp1": 2})
    assert len(d2.devices) < len(d1.devices)   # 2 legs instead of 3
    assert lw2["Mp1"] == (1, 1) and lw2["Mp2"] == (1, 1)
    assert lw2["Mp1#leg2"] == (1, 1)           # copy: exempt, one column
    assert not any(d.name == "Mp1#leg3" for d in d2.devices)
    d4, lw4 = fold_devices(nl, fold_overrides={"Mp1": 4})
    # the chain (2 members) gains copies K=4..2 -> 3 + 6 devices
    assert len(d4.devices) == len(nl.devices) + 3 * 2
    assert lw4["Mp1"] == (1, 1) and lw4["Mp1#leg2"] == (1, 1) \
        and lw4["Mp1#leg3"] == (1, 1) and lw4["Mp1#leg4"] == (1, 1)
    d3, lw3 = fold_devices(nl, fold_overrides={"Mp1": 1})
    assert len(d3.devices) == len(nl.devices)  # no copies at all
    assert lw3["Mp1"] == (1, 1) and lw3["Mp2"] == (1, 1)
    assert _n1 is not None and lw1["Mn1"] == (1, 1)


def test_fold_signature_distinct_and_deterministic(xor2):
    _nl, nl3, lw, _eop, _eon = xor2
    _n2, lw2 = fold_devices(nl3, fold_overrides={"M9": 2})
    s0 = fold_signature(lw)
    s1 = fold_signature(lw)
    s2 = fold_signature(lw2)
    assert s0 == s1
    assert s2 != s0
    assert s0 == tuple(sorted(s0))         # canonical order


# --------------------------------------------------------------------------
# the core-gated nomination
# --------------------------------------------------------------------------

def test_nomination_is_core_gated_and_bounded(xor2):
    """Only devices whose GATE net is core-critical nominate; default+-1
    bounded >= 1 and <= FOLD_VARIANT_MAX_LEGS; sorted, deduped; an empty
    core set nominates nothing."""
    _nl, nl3, lw, _eop, _eon = xor2
    core = ps.core_critical_nets("XOR2X1")     # ("B", "a_13_43#")
    ovs = ps._fold_override_candidates(nl3, lw, core)
    gated = {d.name for d in nl3.devices if d.gate in set(core)}
    assert ovs and all(set(ov) <= gated for ov in ovs)
    assert all(v == 2 for ov in ovs for v in ov.values())   # default 1
    assert [(next(iter(ov)), next(iter(ov.values()))) for ov in ovs] \
        == sorted((next(iter(ov)), next(iter(ov.values()))) for ov in ovs)
    assert ps._fold_override_candidates(nl3, lw, ()) == []
    assert ps._fold_override_candidates(nl3, lw, None) == []


def test_nomination_max_fold_for_over_budget_devices():
    """A device whose width exceeds its fold budget gains the max-fold
    variant (legs = FOLD_VARIANT_MAX_LEGS), skipped when the default
    already reaches the cap."""
    nl = CellNetlist(parse_spice_subckt(FAT_PAIR))
    _n, lw = fold_devices(nl, fold_overrides={"Mp1": 1})   # keep Mp1 whole
    ovs = ps._fold_override_candidates(nl, lw, ("A", "Y"))
    by_name = {}
    for ov in ovs:
        (name, legs), = ov.items()
        by_name.setdefault(name, []).append(legs)
    # Mp1: under-budget legs=1 -> +1 and (over budget) max-fold
    assert by_name["Mp1"] == [2, ps.FOLD_VARIANT_MAX_LEGS]
    # Mp2: budget default legs=3 -> +/-1; the max-fold duplicate of
    # legs+1 == cap dedupes away
    assert by_name["Mp2"] == [2, ps.FOLD_VARIANT_MAX_LEGS]
    assert by_name["Mn1"] == [2]               # under budget: only +1
    # at the cap: no max-fold duplicate
    lw2 = dict(lw, **{"Mp1": (ps.FOLD_VARIANT_MAX_LEGS, 1)})
    ovs2 = ps._fold_override_candidates(nl, lw2, ("A",))
    m1 = [next(iter(ov.values())) for ov in ovs2
          if next(iter(ov)) == "Mp1"]
    assert ps.FOLD_VARIANT_MAX_LEGS not in m1


# --------------------------------------------------------------------------
# the fold-variant classes
# --------------------------------------------------------------------------

def test_fold_variant_classes_deterministic_with_context(xor2):
    _nl, nl3, lw, _eop, _eon = xor2
    core = list(ps.core_critical_nets("XOR2X1"))
    a, ctx_a = fold_variant_classes(nl3, lw, critical_nets=core)
    b, ctx_b = fold_variant_classes(nl3, lw, critical_nets=core)
    assert [(k, ordering_signature(o1, o2)) for k, o1, o2 in a] \
        == [(k, ordering_signature(o1, o2)) for k, o1, o2 in b]
    assert ctx_a == ctx_b
    assert a, "XOR2X1's core-gated devices must nominate fold classes"
    ref = sorted(d.name for d in nl3.devices)
    for kind, op, on in a:
        assert kind.startswith("fold:")
        nl_f, lw_f = ctx_a[kind]
        # the class decomposes its OWN fold decision: total over the
        # override netlist's devices, under the override leg map
        seen = sorted(m.device.name for row in (op, on)
                      for blk in row for m in blk.members)
        assert seen == ref
        assert fold_signature(lw_f) != fold_signature(lw)
        # the override is recoverable from the leg map
        changed = {n: legs for n, (legs, _c) in lw_f.items()
                   if lw.get(n, (1, 1))[0] != legs}
        assert len(changed) == 1
        # the class places under its own leg map without error
        layout_cell(op, on, lw_f)


def test_fold_variant_classes_cap_and_census_guidance(xor2):
    """At most FOLD_VARIANT_MAX_CLASSES variants build classes, and the
    nominated ones are the census-ranked head of the override list."""
    _nl, nl3, lw, _eop, _eon = xor2
    core = list(ps.core_critical_nets("XOR2X1"))
    classes, _ctx = fold_variant_classes(nl3, lw, critical_nets=core)
    heads = sorted({k.split("-")[0] for k, _o1, _o2 in classes})
    assert 1 <= len(heads) <= ps.FOLD_VARIANT_MAX_CLASSES
    # census guidance: the euler-seed rank of every nominated variant is
    # <= the rank of every non-nominated one
    ovs = ps._fold_override_candidates(nl3, lw, core)
    nominated = {h.split(":")[1].split("=")[0] for h in heads}
    assert nominated
    assert len(ovs) >= len(heads)      # XOR2X1 has 6 core-gated devices


def test_fold_variant_classes_empty_without_core(xor2):
    _nl, nl3, lw, _eop, _eon = xor2
    classes, ctx = fold_variant_classes(nl3, lw, critical_nets=None)
    assert classes == [] and ctx == {}


def test_fold_variant_classes_mirror_kinds(flow_dir):
    _nl, nl3, lw, _eop, _eon = _pipeline(_lib_subckt("MUX2X1", flow_dir))
    core = list(ps.core_critical_nets("MUX2X1"))
    classes, _ctx = fold_variant_classes(nl3, lw, critical_nets=core)
    kinds = [k for k, _o1, _o2 in classes]
    assert any(k.endswith("-flip-both") for k in kinds)
    assert any(k.endswith("-die-both") for k in kinds)
    assert any("-align" in k for k in kinds)   # MUX2X1's rows are small


# --------------------------------------------------------------------------
# the lazy phase 6: additive under the no-cage-free-FEASIBLE gate
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


def test_fold_phase_is_lazy_after_the_pair_splits(flow_dir):
    """On a plateau chain the fold classes join LAST (after the pair
    splits); the fallback floor cannot worsen."""
    _nl, nl3, lw, eop, eon = _pipeline(_lib_subckt("XOR2X1", flow_dir))

    def router(_nl, _pl, _w, _lw, max_attempts=0, blocks=None):
        del max_attempts, blocks
        return _fail(6)

    _op, _on, bd = ps.sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router, variant_classes=True,
        core_guided=True)
    kinds = [e["kind"] for e in bd["selection"]["candidates"]]
    fold_kinds = [k for k in kinds if k.startswith("fold:")]
    assert fold_kinds, "phase 6 must join the fold classes on a plateau"
    first_fold = min(kinds.index(k) for k in fold_kinds)
    for prefix in ("var:", "split:", "pairsplit:"):
        this = [k for k in kinds if k.startswith(prefix)]
        if this:
            assert first_fold > max(kinds.index(k) for k in this)
    assert bd["selection"]["conflicts"] == 6
    assert bd["selection"]["candidate_count"] == len(kinds)


def test_fold_phase_skipped_for_earlier_closers(flow_dir):
    """A cell closing cage-free in the fixed classes never builds the
    fold phase (the additive contract)."""
    _nl, nl3, lw, eop, eon = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    seen = []

    def router(_nl, _pl, _w, _lw, max_attempts=0, blocks=None):
        del max_attempts, blocks
        seen.append(1)
        return _ok()

    _op, _on, bd = ps.sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router, variant_classes=True,
        core_guided=True)
    assert bd["selection"]["kind"] == "best"
    assert len(seen) == 1                    # short-circuit: phase 6 cold


def test_fold_phase_gated_on_steering_and_variants(flow_dir):
    """cage=False and variant_classes=False chains keep today's exact
    pools (phase 6 rides the steered production gate)."""
    _nl, nl3, lw, eop, eon = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    for kwargs in ({"variant_classes": True, "cage": False},
                   {"variant_classes": False, "cage": True}):
        _op, _on, bd = ps.sa_refine_routable(
            eop, eon, nl3, lw, trial_router=lambda *a, **k: _fail(3),
            core_guided=True, **kwargs)
        kinds = [e["kind"] for e in bd["selection"]["candidates"]]
        assert not any(k.startswith("fold:") for k in kinds)


def test_fold_winner_report_and_breakdown(flow_dir):
    """A fold candidate that routes wins under the established policy;
    its report carries the override provenance and the breakdown is the
    honest one (computed against the variant's own leg map)."""
    _nl, nl3, lw, eop, eon = _pipeline(_lib_subckt("XOR2X1", flow_dir))

    def router(_nl, _pl, _w, _lw, max_attempts=0, blocks=None):
        del max_attempts, blocks
        if any(v[0] > 1 for v in _lw.values()):
            return _ok()                   # only fold variants route
        return _fail(6)

    op, on, bd = ps.sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router, variant_classes=True,
        core_guided=True)
    sel = bd["selection"]
    assert sel["feasible"] and sel["cage"] == 0
    assert sel["kind"].startswith("fold:")
    ov = sel["fold_overrides"]
    assert ov and len(ov) == 1
    name, legs = next(iter(ov.items()))
    assert legs == 2
    assert (name, legs) in sel["fold_signature"]
    # the winner's orderings place the 2-leg device
    dev_names = {m.device.name for row in (op, on)
                 for b in row for m in b.members}
    assert name in dev_names
    # the breakdown's width is the variant's own (2-leg) placement
    _nl_f, lw_f = fold_devices(nl3, fold_overrides=ov)
    placements, w = layout_cell(op, on, lw_f)
    assert bd["width"] == w


# --------------------------------------------------------------------------
# determinism across processes (invariant 9)
# --------------------------------------------------------------------------

_FOLD_HASH_HELPER = """\
import hashlib, os, sys
sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.netlist_ext import fold_devices
from bigcell_engine.place_sa import (fold_signature, fold_variant_classes,
                                     ordering_signature)

nl = CellNetlist(parse_spice_subckt(open(%r).read()))
nl3, lw = fold_devices(nl)
core = list(__import__("bigcell_engine.place_sa", fromlist=[
    "core_critical_nets"]).core_critical_nets("XOR2X1"))
classes, ctx = fold_variant_classes(nl3, lw, critical_nets=core)
payload = [(k, ordering_signature(o1, o2),
            fold_signature(ctx[k][1])) for k, o1, o2 in classes]
print(hashlib.sha256(repr(payload).encode()).hexdigest())
"""


def test_fold_classes_byte_stable_across_processes(flow_dir, tmp_path):
    src = tmp_path / "XOR2X1.sp"
    src.write_text(_lib_subckt("XOR2X1", flow_dir))
    helper = tmp_path / "fold_hash_helper.py"
    helper.write_text(_FOLD_HASH_HELPER % str(src))
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, str(helper)], cwd=os.path.join(flow_dir),
            env=env, capture_output=True, text=True, check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests
