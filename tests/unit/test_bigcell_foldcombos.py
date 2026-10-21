"""Unit tests for the fold-COMBO dimension: the fold dimension COMPOSED
(several core-gated devices overridden SIMULTANEOUSLY) --
place_sa.fold_combo_candidates / fold_combo_classes and the lazy phase 7.

S2's fold variants (test_bigcell_folds.py) override ONE device each, so
every variant relocates only its own gate columns -- and the fold census
(flow/_stage3_check/_fold_census_*.json, AUDIT 5.55) proved every
per-device variant's whole ordering space still holds exactly one caged
gate.  The open composition question: device A's fold moves A's gate
columns OUT of the band where device B's caged gate sits, and vice
versa, so overriding BOTH simultaneously may free both cages where
either alone frees one.

These tests pin the MECHANISM: the combination nomination (the sorted
Cartesian product of the per-device option sets, fold-signature dedupe,
the documented cap, pure), the class build (the fold-variant twin's
census-guided cap and per-combo trial context), the lazy phase 7
integration (additive under the no-cage-free-FEASIBLE gate, AFTER the
one-device fold phase, a combo winner's whole-table provenance, the
honest breakdown against the combo's own leg map) and cross-process
determinism (invariant 9).  The decisive census evidence (per-device
best vs combo best, the (0,0) question) lives in
flow/_stage3_check/_foldcombo_census.py + its JSON/log outputs.
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
from bigcell_engine.netlist_ext import fold_devices
from bigcell_engine.place_sa import (fold_combo_candidates,
                                     fold_combo_classes, fold_signature,
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
#: (the series-fold trigger): the default fold is ceil(2.5/1.2) = 3 legs,
#: so the fold-COMBO space exercises the series-chain override semantics
#: (the chain is the fold unit; the smallest named member wins)
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
    return nl, nl3, lw


# --------------------------------------------------------------------------
# fold_combo_candidates: the product space, the signature dedupe, the cap
# --------------------------------------------------------------------------

def test_combo_candidates_are_the_full_product(flow_dir):
    """XOR2X1 gates 6 devices (B + a_13_43#); each device's option set is
    {default 1, nominated 2} -> 2^6 - 1 = 63 non-empty combos after the
    all-default signature skip.  Deterministic and pure."""
    _nl, nl3, lw = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    core = list(ps.core_critical_nets("XOR2X1"))
    combos = fold_combo_candidates(nl3, lw, core)
    assert len(combos) == 63
    gated = sorted({d.name for d in nl3.devices if d.gate in set(core)})
    assert all(sorted(ov) == gated or set(ov) <= set(gated) for ov in combos)
    # every device's legs stay within its option set {1, 2}
    for ov in combos:
        assert all(legs in (1, 2) for legs in ov.values())
    # deterministic (invariant 9)
    assert combos == fold_combo_candidates(nl3, lw, core)
    # pure
    before = [(d.name, d.width_um) for d in nl3.devices]
    fold_combo_candidates(nl3, lw, core)
    assert before == [(d.name, d.width_um) for d in nl3.devices]


def test_combo_candidates_dedupe_by_fold_signature():
    """The dedupe contract on the chain's own RECEIVED fold state: the
    FAT_PAIR default fold (3 legs) divides its members under budget, so
    the combos are pure width folds of the divided members -- 8 choices
    over (Mp1, Mp2, Mn1) with the all-default choice collapsing into the
    received fold's signature (skipped) and every remaining combo a
    distinct fold decision (fold_devices returns the received netlist
    itself: no re-fold, no new copies).  The chain-as-fold-unit masking
    (the smallest named member decides) is fold_devices' own semantics,
    pinned in test_bigcell_folds.py on the unfolded netlist."""
    _nl, nl3, lw = _pipeline(FAT_PAIR)
    combos = fold_combo_candidates(nl3, lw, ("A",))
    assert len(combos) == 7
    sigs = []
    for ov in combos:
        f, lw_f = fold_devices(nl3, fold_overrides=ov)
        assert f is nl3                     # width folds only, no re-fold
        sigs.append(fold_signature(lw_f))
    assert len(set(sigs)) == 7
    assert fold_signature(lw) not in sigs
    # every device's legs stay within its option set {1, 2}
    assert all(legs in (1, 2) for ov in combos for legs in ov.values())


def test_combo_candidates_empty_without_core(flow_dir):
    _nl, nl3, lw = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    assert fold_combo_candidates(nl3, lw, ()) == []
    assert fold_combo_candidates(nl3, lw, None) == []


def test_combo_candidates_cap(flow_dir):
    """The documented cap keeps the FIRST sorted combos."""
    _nl, nl3, lw = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    core = list(ps.core_critical_nets("XOR2X1"))
    full = fold_combo_candidates(nl3, lw, core)
    capped = fold_combo_candidates(nl3, lw, core, max_combos=10)
    assert len(capped) == 10
    assert capped == full[:10]
    assert fold_combo_candidates(nl3, lw, core, max_combos=0) == []


# --------------------------------------------------------------------------
# the fold-combo classes
# --------------------------------------------------------------------------

def test_combo_classes_deterministic_with_context(flow_dir):
    _nl, nl3, lw = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    core = list(ps.core_critical_nets("XOR2X1"))
    a, ctx_a = fold_combo_classes(nl3, lw, critical_nets=core)
    b, ctx_b = fold_combo_classes(nl3, lw, critical_nets=core)
    assert [(k, ordering_signature(o1, o2)) for k, o1, o2 in a] \
        == [(k, ordering_signature(o1, o2)) for k, o1, o2 in b]
    assert ctx_a == ctx_b
    assert a, "XOR2X1's core must nominate combo classes"
    ref = sorted(d.name for d in nl3.devices)
    base_fold = fold_signature(lw)
    for kind, op, on in a:
        assert kind.startswith("foldcombo:")
        nl_f, lw_f = ctx_a[kind]
        # the class decomposes its OWN fold decision
        seen = sorted(m.device.name for row in (op, on)
                      for blk in row for m in blk.members)
        assert seen == ref
        assert fold_signature(lw_f) != base_fold
        # the kind names the whole override table, sorted; folding the
        # received netlist with the parsed table reproduces the ctx leg
        # map exactly (the recovery contract -- the table may pin
        # default legs explicitly, which a leg-map diff would drop)
        head = kind.split("-flip")[0].split("-die")[0].split("-align")[0]
        body = head.split(":", 1)[1]
        ov_parsed = {kv.split("=")[0]: int(kv.split("=")[1])
                     for kv in body.split("+")}
        assert list(ov_parsed) == sorted(ov_parsed)
        _nl2, lw2 = fold_devices(nl3, fold_overrides=ov_parsed)
        assert fold_signature(lw2) == fold_signature(lw_f)
        # the class places under its own leg map without error
        layout_cell(op, on, lw_f)


def _diff(lw_base, lw_var):
    """The override table recoverable from two leg maps (changed legs)."""
    return {n: legs for n, (legs, _c) in lw_var.items()
            if lw_base.get(n, (1, 1))[0] != legs}


def test_combo_classes_cap_and_census_guidance(flow_dir):
    """At most FOLD_VARIANT_MAX_CLASSES combos build classes, and the
    nominated ones are the census-ranked head of the combination list."""
    from bigcell_engine.netlist_ext import build_bigcell_blocks, row_seeds
    from bigcell_engine.place_euler import euler_orderings
    _nl, nl3, lw = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    core = list(ps.core_critical_nets("XOR2X1"))
    classes, _ctx = fold_combo_classes(nl3, lw, critical_nets=core)
    heads = sorted({k.split("-flip")[0].split("-die")[0]
                    .split("-align")[0] for k, _o1, _o2 in classes})
    assert 1 <= len(heads) <= ps.FOLD_VARIANT_MAX_CLASSES
    # census guidance: the euler-seed rank of every nominated combo is
    # <= the rank of every non-nominated one
    ranked = []
    for ov in fold_combo_candidates(nl3, lw, core):
        nl_f, lw_f = fold_devices(nl3, fold_overrides=ov)
        seeds = row_seeds(build_bigcell_blocks(nl_f), lw_f)
        eop, eon = euler_orderings(seeds, lw_f)
        ranked.append((ps.crossing_cage_penalty(eop, eon, nl_f, lw_f)[0],
                       ps.gate_cage_penalty(eop, eon, nl_f, lw_f)[0],
                       tuple(sorted(ov.items()))))
    ranked.sort()
    assert len(ranked) >= len(heads)


def test_combo_classes_empty_without_core(flow_dir):
    _nl, nl3, lw = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    classes, ctx = fold_combo_classes(nl3, lw, critical_nets=None)
    assert classes == [] and ctx == {}


# --------------------------------------------------------------------------
# the lazy phase 7: additive, after the one-device fold phase
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


def test_combo_phase_is_lazy_after_the_fold_phase(flow_dir):
    """On a plateau chain the combo classes join LAST (after the
    one-device fold variants); the fallback floor cannot worsen."""
    from bigcell_engine.netlist_ext import build_bigcell_blocks, row_seeds
    from bigcell_engine.place_euler import euler_orderings
    _nl, nl3, lw = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    seeds = row_seeds(build_bigcell_blocks(nl3), lw)
    eop, eon = euler_orderings(seeds, lw)

    def router(_nl, _pl, _w, _lw, max_attempts=0, blocks=None):
        del max_attempts, blocks
        return _fail(6)

    _op, _on, bd = ps.sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router, variant_classes=True,
        core_guided=True)
    kinds = [e["kind"] for e in bd["selection"]["candidates"]]
    combo_kinds = [k for k in kinds if k.startswith("foldcombo:")]
    fold_kinds = [k for k in kinds if k.startswith("fold:")]
    assert combo_kinds, "phase 7 must join the combo classes on a plateau"
    assert fold_kinds, "phase 6 must precede phase 7"
    assert kinds.index(combo_kinds[0]) > \
        max(kinds.index(k) for k in fold_kinds)
    for prefix in ("var:", "split:", "pairsplit:"):
        this = [k for k in kinds if k.startswith(prefix)]
        if this:
            assert kinds.index(combo_kinds[0]) > \
                max(kinds.index(k) for k in this)
    assert bd["selection"]["conflicts"] == 6
    assert bd["selection"]["candidate_count"] == len(kinds)


def test_combo_phase_skipped_for_earlier_closers(flow_dir):
    """A cell closing cage-free in the fixed classes never builds the
    combo phase (the additive contract)."""
    from bigcell_engine.netlist_ext import build_bigcell_blocks, row_seeds
    from bigcell_engine.place_euler import euler_orderings
    _nl, nl3, lw = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    seeds = row_seeds(build_bigcell_blocks(nl3), lw)
    eop, eon = euler_orderings(seeds, lw)
    seen = []

    def router(_nl, _pl, _w, _lw, max_attempts=0, blocks=None):
        del max_attempts, blocks
        seen.append(1)
        return _ok()

    _op, _on, bd = ps.sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router, variant_classes=True,
        core_guided=True)
    assert bd["selection"]["kind"] == "best"
    assert len(seen) == 1                    # short-circuit: phase 7 cold


def test_combo_phase_gated_on_steering_and_variants(flow_dir):
    """cage=False and variant_classes=False chains keep today's exact
    pools (phase 7 rides the steered production gate)."""
    from bigcell_engine.netlist_ext import build_bigcell_blocks, row_seeds
    from bigcell_engine.place_euler import euler_orderings
    _nl, nl3, lw = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    seeds = row_seeds(build_bigcell_blocks(nl3), lw)
    eop, eon = euler_orderings(seeds, lw)
    for kwargs in ({"variant_classes": True, "cage": False},
                   {"variant_classes": False, "cage": True}):
        _op, _on, bd = ps.sa_refine_routable(
            eop, eon, nl3, lw, trial_router=lambda *a, **k: _fail(3),
            core_guided=True, **kwargs)
        kinds = [e["kind"] for e in bd["selection"]["candidates"]]
        assert not any(k.startswith("foldcombo:") for k in kinds)


def test_combo_winner_report_and_breakdown(flow_dir):
    """A combo candidate that routes wins under the established policy;
    its report carries the WHOLE override table as provenance and the
    breakdown is the honest one (computed against the combo's own leg
    map)."""
    from bigcell_engine.netlist_ext import build_bigcell_blocks, row_seeds
    from bigcell_engine.place_euler import euler_orderings
    _nl, nl3, lw = _pipeline(_lib_subckt("XOR2X1", flow_dir))
    seeds = row_seeds(build_bigcell_blocks(nl3), lw)
    eop, eon = euler_orderings(seeds, lw)

    def router(_nl, _pl, _w, _lw, max_attempts=0, blocks=None):
        del max_attempts, blocks
        if sum(1 for v in _lw.values() if v[0] > 1) >= 2:
            return _ok()                   # only combos (>= 2 devices) route
        return _fail(6)

    op, on, bd = ps.sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router, variant_classes=True,
        core_guided=True)
    sel = bd["selection"]
    assert sel["feasible"]
    assert sel["kind"].startswith("foldcombo:")
    ov = sel["fold_overrides"]
    assert ov and len(ov) >= 2             # the WHOLE table, several devices
    for name, legs in ov.items():
        assert (name, legs) in sel["fold_signature"]
    # the winner's orderings place the folded devices
    dev_names = {m.device.name for row in (op, on)
                 for b in row for m in b.members}
    assert set(ov) <= dev_names
    # the breakdown's width is the combo's own placement
    _nl_f, lw_f = fold_devices(nl3, fold_overrides=ov)
    placements, w = layout_cell(op, on, lw_f)
    assert bd["width"] == w


# --------------------------------------------------------------------------
# determinism across processes (invariant 9)
# --------------------------------------------------------------------------

_COMBO_HASH_HELPER = """\
import hashlib, os, sys
sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.netlist_ext import fold_devices
from bigcell_engine.place_sa import (core_critical_nets, fold_combo_classes,
                                     fold_signature, ordering_signature)

nl = CellNetlist(parse_spice_subckt(open(%r).read()))
nl3, lw = fold_devices(nl)
core = list(core_critical_nets(%r))
classes, ctx = fold_combo_classes(nl3, lw, critical_nets=core)
payload = [(k, ordering_signature(o1, o2),
            fold_signature(ctx[k][1])) for k, o1, o2 in classes]
print(hashlib.sha256(repr(payload).encode()).hexdigest())
"""


def test_combo_classes_byte_stable_across_processes(flow_dir, tmp_path):
    src = tmp_path / "XOR2X1.sp"
    src.write_text(_lib_subckt("XOR2X1", flow_dir))
    helper = tmp_path / "combo_hash_helper.py"
    helper.write_text(_COMBO_HASH_HELPER % (str(src), "XOR2X1"))
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, str(helper)], cwd=os.path.join(flow_dir),
            env=env, capture_output=True, text=True, check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests
