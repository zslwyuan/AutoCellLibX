"""GDS-seed tests: the migration record, the candidate class, the wall.

The GDS-seed attack (AUDIT 5.60): ASTRAN's own layouts, extracted from
the repo's .gds files as speculate-pool seeds.  These tests pin the three
contracts the attack committed:

- **provenance**: every EXTRACTED_TABLE entry re-derives from its .gds
  byte-exactly (the table is data, the .gds files stay the migration
  source -- a future regeneration must reproduce the same arrangements);
- **the projection**: seed_orderings' blocks place through
  geometry.layout_cell and reproduce ASTRAN's per-row order,
  orientations and diffusion breaks (breaks land exactly where the
  extracted strips separate);
- **the wiring**: a closure-table entry makes seed_candidates hand the
  arrangement to select_orderings as pool priority 0, and the selection
  picks it; netlists outside the table see no seed at all (the 28
  existing closures keep their exact pools byte-for-byte);
- **the wall** (the honest negative result): the extracted arrangements
  are CP-SAT-proven INFEASIBLE in the engine's full exact vocabulary --
  pinned for the cheapest cell in the fast suite and for all fifteen in
  the slow sweep, so a future vocabulary extension that unlocks a
  capture flips a test and gets noticed.
"""

import os
import re
import subprocess
import sys

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist

from bigcell_engine import gds_seeds
from bigcell_engine.geometry import layout_cell
from bigcell_engine.gds_seeds import (EXTRACTED_TABLE, SEED_TABLE,
                                      candidate_from_gds,
                                      extract_arrangement,
                                      netlist_digest, seed_candidates,
                                      seed_orderings)
from bigcell_engine.netlist_ext import fold_devices

LIB_DECK = os.path.join("..", "std_celllib", "cellsAstranFriendly.sp")


def _load_cell(entry_source, flow_dir):
    """The CellNetlist an EXTRACTED_TABLE entry speaks.

    ``entry_source`` is the entry's flow-relative .gds path: mined
    cells sit next to their own .sp, library baselines sit in the
    shared cellsAstranFriendly deck.
    """
    gds = os.path.join(flow_dir, entry_source)
    if entry_source.startswith("outputs/"):
        text = open(gds[:-4] + ".sp", errors="ignore").read()
        return CellNetlist(parse_spice_subckt(text))
    name = os.path.basename(entry_source)[:-4]
    text = open(os.path.join(flow_dir, LIB_DECK), errors="ignore").read()
    blk = re.split(r"\.subckt\s+%s\b" % name, text)[1].split(".ends")[0]
    return CellNetlist(parse_spice_subckt(
        ".subckt %s x\n%s.ends" % (name, blk)))


def _entry_for(name):
    return [k for k in EXTRACTED_TABLE if k[0] == name][0]


# --------------------------------------------------------------------------
# provenance: the table re-derives from the .gds
# --------------------------------------------------------------------------

def test_extracted_table_covers_every_extractable_fallback_cell():
    # 21 unsupported cells - 6 with no ASTRAN layout at all (ASTRAN's own
    # run never finished: no Cell Size line, no .gds) = 15 extractable
    assert len(EXTRACTED_TABLE) == 15
    assert sorted(key[0] for key in EXTRACTED_TABLE) == sorted([
        "CLKBUF1", "DFFNEGX1", "DFFPOSX1", "MUX2X1", "NOR3X1", "XNOR2X1",
        "XOR2X1", "COMPLEX0", "COMPLEX0", "COMPLEX1", "COMPLEX7",
        "COMPLEX9", "COMPLEX10", "COMPLEX11", "COMPLEX20"])
    for key, entry in sorted(EXTRACTED_TABLE.items()):
        assert entry["source"].endswith(".gds")
        assert entry["verdict"] == "exact-infeasible"
        assert entry["astran_um"] > 0
        assert entry["p_strips"] >= 1 and entry["n_strips"] >= 1


@pytest.mark.parametrize("key", sorted(EXTRACTED_TABLE))
def test_extraction_reproduces_the_committed_table(flow_dir, key):
    """The migration record re-derives from the .gds byte-exactly."""
    entry = EXTRACTED_TABLE[key]
    nl = _load_cell(entry["source"], flow_dir)
    assert netlist_digest(nl) == key[1]
    ext = extract_arrangement(nl, os.path.join(flow_dir, entry["source"]))
    assert [tuple(t) for t in ext["p"]] == list(entry["p"])
    assert [tuple(t) for t in ext["n"]] == list(entry["n"])
    m = ext["metrics"]
    assert m["p_strips"] == entry["p_strips"]
    assert m["n_strips"] == entry["n_strips"]
    assert m["p_trans"] == len(entry["p"])
    assert m["n_trans"] == len(entry["n"])


def test_extractions_are_device_total(flow_dir):
    """Every extracted row covers its netlist's row devices exactly once,
    with the devices' own terminal nets on the die edges; none of the 15
    cells folds (their ASTRAN logs say "after folding" == "before"), so
    the arrangement speaks the unfolded netlist."""
    for key, entry in sorted(EXTRACTED_TABLE.items()):
        nl = _load_cell(entry["source"], flow_dir)
        dev = {d.name: d for d in nl.devices}
        for row, polarity in (("p", True), ("n", False)):
            seq = entry[row]
            assert {t[0] for t in seq} == \
                {d.name for d in nl.devices if d.is_p == polarity}
            assert len(seq) == len({t[0] for t in seq})
            for name, lnet, rnet in seq:
                d = dev[name]
                assert {lnet, rnet} == {d.source, d.drain}
        nl3, _lws = fold_devices(nl)
        assert nl3 is nl


# --------------------------------------------------------------------------
# the projection: orderings -> placement -> breaks
# --------------------------------------------------------------------------

@pytest.mark.parametrize("key", sorted(EXTRACTED_TABLE))
def test_seed_projects_to_astrians_breaks(flow_dir, key):
    """place_row reproduces ASTRAN's diffusion strips: the seed's rows
    break exactly where the extracted strips separate (strips - 1 breaks
    per row, and only there -- no phantom breaks pad the width)."""
    entry = EXTRACTED_TABLE[key]
    nl = _load_cell(entry["source"], flow_dir)
    nl3, lws = fold_devices(nl)
    ordering_p, ordering_n = seed_orderings(nl3, entry)
    placements, width = layout_cell(ordering_p, ordering_n, lws)
    for ordering, seq, strips, row in ((ordering_p, entry["p"],
                                        entry["p_strips"], 0),
                                       (ordering_n, entry["n"],
                                        entry["n_strips"], 1)):
        breaks = sum(1 for a, b in zip(seq, seq[1:]) if a[2] != b[1])
        assert breaks == strips - 1, \
            "%s row %d: %d breaks vs %d strips" % (key, row, breaks,
                                                   strips)
        placed = [p for p in placements.values() if p.row == row]
        assert len(placed) == len(seq)
    width_expected = max(len(entry["p"]) + entry["p_strips"] - 1,
                        len(entry["n"]) + entry["n_strips"] - 1)
    assert width == width_expected


def test_nor3x1_extraction_is_the_doubled_ladder_run(flow_dir):
    """The known-good witness (doc/BIGCELL_SLOT_GEOMETRY.md section 5):
    NOR3X1's P row is ONE strip of six members -- a doubled ladder run
    over the three coupler nets -- and the N row is the three parallel
    pulldowns in one strip.  The GDS's actual gate sequence (verified
    independently: each gate's poly reaches a labelled M1 pin) is
    B-A-A-B-C-C with a_25_64# occupying THREE slots (both strip ends
    and the M3/M4 junction) -- the note's section-5 trail is the same
    eulerian circuit written from a different start; the structural
    claims (6 columns, 7 slots, 0 breaks) hold exactly."""
    entry = EXTRACTED_TABLE[_entry_for("NOR3X1")]
    assert entry["p_strips"] == 1 and entry["n_strips"] == 1
    nl = _load_cell(entry["source"], flow_dir)
    gate = {d.name: d.gate for d in nl.devices}
    assert [gate[t[0]] for t in entry["p"]] == list("BAABCC")
    p_slots = [entry["p"][0][1]] + [t[2] for t in entry["p"]]
    assert len(p_slots) == 7                    # 6 columns, 7 slots
    assert sorted(p_slots) == sorted(
        ["a_25_64#", "a_25_64#", "a_25_64#", "a_2_64#", "a_2_64#",
         "VCC", "Y"])
    n_slots = [entry["n"][0][1]] + [t[2] for t in entry["n"]]
    assert sorted(n_slots) == ["GND", "GND", "Y", "Y"]


# --------------------------------------------------------------------------
# identity + inertness (the 28 closures keep their exact pools)
# --------------------------------------------------------------------------

def test_complexc_ids_stay_disambiguated(flow_dir):
    """Same subckt name, different cells: the two COMPLEX0 extractions
    (max, multiplier) have distinct digests, and the CLOSING
    adder/COMPLEX0 (one of the 28) is not in the table at all."""
    keys = [k for k in EXTRACTED_TABLE if k[0] == "COMPLEX0"]
    assert len(keys) == 2
    assert len({k[1] for k in keys}) == 2
    adder = os.path.join(flow_dir, "outputs", "adder", "COMPLEX0.sp")
    nl = CellNetlist(parse_spice_subckt(
        open(adder, errors="ignore").read()))
    assert ("COMPLEX0", netlist_digest(nl)) not in EXTRACTED_TABLE
    assert seed_candidates(nl) == []


def test_seed_candidates_empty_while_no_closure_exists(flow_dir):
    """The closure table is the honest empty capture list: every netlist
    -- table cells included -- gets no production candidate until an
    arrangement actually closes (AUDIT 5.60)."""
    assert SEED_TABLE == {}
    for key, entry in sorted(EXTRACTED_TABLE.items()):
        nl = _load_cell(entry["source"], flow_dir)
        assert seed_candidates(nl) == []
    text = open(os.path.join(flow_dir, LIB_DECK), errors="ignore").read()
    blk = re.split(r"\.subckt\s+NAND2X1\b", text)[1].split(".ends")[0]
    nl = CellNetlist(parse_spice_subckt(
        ".subckt NAND2X1 VCC Y A B GND\n%s.ends" % blk))
    assert seed_candidates(nl) == []


def test_candidate_from_gds_is_the_research_entry_point(flow_dir):
    entry = EXTRACTED_TABLE[_entry_for("XNOR2X1")]
    nl = _load_cell(entry["source"], flow_dir)
    got, op, on = candidate_from_gds(
        nl, os.path.join(flow_dir, entry["source"]))
    assert [tuple(t) for t in got["p"]] == list(entry["p"])
    assert [tuple(t) for t in got["n"]] == list(entry["n"])
    nl3, lws = fold_devices(nl)
    _placements, width = layout_cell(op, on, lws)
    assert width == len(entry["p"])      # one strip per row, no breaks


# --------------------------------------------------------------------------
# the wiring: a closure-table entry is the first-priority candidate
# --------------------------------------------------------------------------

class _Ok(object):
    ok = True
    status_name = "FEASIBLE"
    fail_note = None
    attempts_used = 1


def _chain_heads(nl):
    from bigcell_engine.netlist_ext import build_bigcell_blocks, row_seeds
    from bigcell_engine.place_euler import euler_orderings
    nl3, lws = fold_devices(nl)
    seeds = row_seeds(build_bigcell_blocks(nl3), lws)
    op, on = euler_orderings(seeds, lws)
    return nl3, lws, op, on


def test_closure_table_entry_wins_the_selection(flow_dir, monkeypatch):
    """The ownership mechanism, exercised end to end with real data: the
    MUX2X1 arrangement, injected into the closure table, joins the pool
    as candidate 0 and -- routing FEASIBLE cage-free -- is selected."""
    entry_key = _entry_for("MUX2X1")
    entry = dict(EXTRACTED_TABLE[entry_key])
    nl = _load_cell(entry["source"], flow_dir)
    nl3, lws, op, on = _chain_heads(nl)
    monkeypatch.setitem(gds_seeds.SEED_TABLE, entry_key, entry)
    assert len(seed_candidates(nl3)) == 1

    from bigcell_engine.place_sa import select_orderings
    calls = []

    def router(nl_r, placements, width, leg_widths, max_attempts=0,
               blocks=None):
        calls.append(placements)
        return _Ok()

    sel_p, sel_n, report = select_orderings(
        op, on, op, on, nl3, lws, trial_router=router,
        variant_classes=True)
    assert report["kind"] == "gds-seed"
    assert report["selected"] == 0
    assert report["feasible"] and report["cage"] == 0
    # the seed was tried first (pool priority 0) and the selection
    # returned exactly the extracted arrangement
    ordering_p, ordering_n = seed_orderings(nl3, entry)
    first, _w = layout_cell(ordering_p, ordering_n, lws)
    assert {d.name: (p.row, p.start_col) for d, p in first.items()} == \
        {d.name: (p.row, p.start_col) for d, p in calls[0].items()}
    assert [(m.device.name, m.left_net, m.right_net) for b in sel_p
            for m in b.members] == list(entry["p"])
    assert [(m.device.name, m.left_net, m.right_net) for b in sel_n
            for m in b.members] == list(entry["n"])


def test_selection_pool_is_unchanged_without_a_seed(flow_dir):
    """No table entry, no change: a non-table cell's trials and selection
    are exactly the pre-seed behaviour (the 28-closure no-regression
    contract, structurally)."""
    text = open(os.path.join(flow_dir, LIB_DECK), errors="ignore").read()
    blk = re.split(r"\.subckt\s+NAND2X1\b", text)[1].split(".ends")[0]
    nl = CellNetlist(parse_spice_subckt(
        ".subckt NAND2X1 VCC Y A B GND\n%s.ends" % blk))
    nl3, lws, op, on = _chain_heads(nl)
    from bigcell_engine.place_sa import select_orderings
    calls = []

    def router(nl_r, placements, width, leg_widths, max_attempts=0,
               blocks=None):
        calls.append(placements)
        return _Ok()

    _sel_p, _sel_n, report = select_orderings(
        op, on, op, on, nl3, lws, trial_router=router)
    assert report["kind"] == "best"           # the SA-best candidate, as
    assert report["selected"] == 0             # before the seed class
    # the FEASIBLE short-circuit stops the scan at pool entry 0 -- the
    # exact pre-seed contract (no extra trial, no reordering)
    assert len(calls) == 1
    assert len(report["candidates"]) == 1


# --------------------------------------------------------------------------
# the wall: the honest negative result, pinned
# --------------------------------------------------------------------------

def _seed_placement(flow_dir, name):
    entry = EXTRACTED_TABLE[_entry_for(name)]
    nl = _load_cell(entry["source"], flow_dir)
    nl3, lws = fold_devices(nl)
    ordering_p, ordering_n = seed_orderings(nl3, entry)
    placements, width = layout_cell(ordering_p, ordering_n, lws)
    return nl3, placements, width, list(ordering_p) + list(ordering_n)


def _assert_exact_infeasible(flow_dir, name, time_limit_s):
    from smt_engine.route_model import (solve_routing,
                                        verify_style_access_points)
    nl3, placements, width, blocks = _seed_placement(flow_dir, name)
    acc = verify_style_access_points(nl3, placements, blocks)
    route = solve_routing(nl3, placements, width + 1, metal2=True,
                          m2_spans=True, jump_m2=True,
                          time_limit_s=time_limit_s, accesses=acc)
    assert not route.ok, \
        "%s closed: move the entry into SEED_TABLE and pin it!" % name
    assert route.status_name == "INFEASIBLE", \
        (name, route.status_name)


def test_nor3x1_seed_is_exact_infeasible(flow_dir):
    """ASTRAN's own NOR3X1 arrangement, projected into the slot model,
    is unroutable in the FULL exact vocabulary (CP-SAT proof, ~1 s).
    A future vocabulary extension that makes this FEASIBLE/OPTIMAL has
    opened a capture: flip this test, move the entry into SEED_TABLE
    and pin the closure (AUDIT 5.60)."""
    _assert_exact_infeasible(flow_dir, "NOR3X1", 60.0)


@pytest.mark.slow
def test_every_extracted_seed_is_exact_infeasible(flow_dir):
    """The full 15-cell proof sweep (AUDIT 5.60): every extracted
    arrangement, projected into the slot model, is CP-SAT INFEASIBLE
    with metal2 + m2_spans + jump_m2 (2-12 s per proof, zero timeouts).
    The capture list is empty; this is its evidence."""
    for key in sorted(EXTRACTED_TABLE):
        _assert_exact_infeasible(flow_dir, key[0], 120.0)


# --------------------------------------------------------------------------
# determinism (invariant 9): the migration source is process-stable
# --------------------------------------------------------------------------

def test_extraction_is_hashseed_independent(flow_dir, tmp_path):
    """Cross-process PYTHONHASHSEED 0/1: the extraction, the digest and
    the candidate construction are byte-identical -- the runtime
    consumers (a future closure's regression test) inherit this."""
    entry = EXTRACTED_TABLE[_entry_for("XNOR2X1")]
    nl = _load_cell(entry["source"], flow_dir)
    deck = tmp_path / "xnor2x1.sp"
    with open(deck, "w") as fh:
        fh.write(".subckt XNOR2X1 x\n")
        for d in nl.devices:
            fh.write("M%s %s %s %s %s %s W=%.6gu L=0.05u\n" % (
                d.name, d.drain, d.gate, d.source, d.bulk,
                "PMOS" if d.is_p else "NMOS", d.width_um))
        fh.write(".ends\n")
    script = """
import os, sys
sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.gds_seeds import (candidate_from_gds,
                                      netlist_digest)
nl = CellNetlist(parse_spice_subckt(
    open(%r, errors='ignore').read()))
entry, op, on = candidate_from_gds(nl, %r)
print(netlist_digest(nl))
print(entry['p'])
print(entry['n'])
print([(b.kind, [(m.device.name, m.left_net, m.right_net)
                 for m in b.members]) for b in op])
print([(b.kind, [(m.device.name, m.left_net, m.right_net)
                 for m in b.members]) for b in on])
""" % (str(deck), os.path.join(flow_dir, entry["source"]))
    outs = []
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        res = subprocess.run(
            [sys.executable, "-c", script], cwd=flow_dir, env=env,
            capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        outs.append(res.stdout)
    assert outs[0] == outs[1]
