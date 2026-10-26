"""GDS-seed candidates: ASTRAN's own layouts as speculate-pool seeds.

The migration story (agent gds-seeds, AUDIT 5.60): the 21 ASTRAN-fallback
cells' layouts exist as .gds in the repo (the library gates' ASTRAN
baselines + the mined COMPLEX cells).  ASTRAN closing them proves feasible
arrangements EXIST; this module extracts those arrangements so Python can
route/verify/own the cells without ever running ASTRAN again.

What the extraction reads (the inverse of doc/BIGCELL_SLOT_GEOMETRY.md's
forward rules; calibrated 16.5 raw units/um, layer map metal1=49,
poly=9, contact=10, active=1):

- diffusion strips: connected active components per polarity row;
- gate columns: narrow poly rects crossing a strip (their x-centre is the
  column, their gate net comes from the poly component's metal1 pin);
- terminal regions: the strip segments between consecutive gates; a
  region's net comes from its contact's metal1 component;
- nets: connected components of metal1 + poly + regions bridged by
  contacts; labels pin external nets case-blind (ASTRAN upper-cases pin
  labels, the decks keep mixed case);
- devices: a deterministic DFS walks the gates left to right, matching
  each to the netlist device with the gate net and the terminal pair the
  regions demand, pinning ambiguous components (pure internal junctions
  with identical signatures) through the choice.

The projection to the slot model: each transistor becomes ONE
single-member DiffusionBlock carrying its die orientation, so
geometry.place_row reproduces ASTRAN's per-row order, orientations and
diffusion breaks exactly (breaks land where ASTRAN's strips separate --
measured: every strip boundary faces differing nets, place_row's
BREAK_GAP_COLS rule fires there and only there).

THE HONEST VERDICT (2026-10-27, full evidence in AUDIT 5.60): every one
of the 15 extractable arrangements, projected into the slot model, is
CP-SAT-proven INFEASIBLE in the engine's FULL exact vocabulary
(solve_routing(metal2=True, m2_spans=True, jump_m2=True), 2-12 s per
proof, zero timeouts).  Six of the 21 have no ASTRAN layout to extract at
all (ASTRAN's own run never finished: CLKBUF2, CLKBUF3, DFFSR, FAX1,
HAX1, LATCH -- no Cell Size line, no .gds).  The wall is NOT the search:
it is the two geometry features ASTRAN's layouts use that the slot model
cannot express, both measured per cell in AUDIT 5.60:

- **multi-column terminal regions**: ASTRAN's LP compaction pushes gates
  apart to make routing corridor space inside continuous diffusion
  (measured gate gaps up to 4.3 pitches where the model has one); the
  slot model gives every member exactly one column;
- **independent row x-offsets**: ASTRAN's rows start at different x
  (NOR3X1's N chain sits centred under the P row, 2.2 columns right);
  place_row pins every row at column 0.

So the runtime closure table (:data:`SEED_TABLE`) is EMPTY today: per the
ownership rule, an arrangement is committed there only when it CLOSES
(route or exact solve verified clean), and then the closure reproduces
from the table alone -- the .gds was the migration source, the table is
the runtime input, deterministically (hashlib digest keys, no hash() use,
AGENTS.md invariant 9).  :data:`EXTRACTED_TABLE` keeps all 15 extracted
arrangements as the migration record and the ready-made target set for
the vocabulary extensions AUDIT 5.57-5.60 point at; the provenance tests
re-derive it from the .gds files byte-exactly.

Public API:

- :func:`netlist_digest` -- the stable identity key (invariant 6:
  COMPLEX ids are per-run; the name alone never disambiguates);
- :func:`seed_candidates` -- the lazy first-priority candidate class
  consumed by place_sa.select_orderings (empty while the closure table
  is empty);
- :func:`extract_arrangement` / :func:`candidate_from_gds` -- the
  migration-time extractor (the research path for the next session).
"""

import hashlib

from smt_engine.netlist import BlockMember, DiffusionBlock

#: ASTRAN GDS calibration (gui/gds_model.py, flow/layout_sanity.py).
UNITS_PER_UM = 16.5
#: the poly-stripe width above which a poly rect is routing, not a gate
_GATE_MAX_WIDTH = 2.5
_EPS = 1e-9

SEED_KIND = "gds-seed"


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

def netlist_digest(netlist):
    """A stable content digest of a CellNetlist (12 hex chars).

    Sorted device tuples (name, terminals, polarity, W) over sha1 -- the
    same netlist always digests identically across processes (invariant
    9); two different cells sharing a subckt name (max/COMPLEX0 vs
    adder/COMPLEX0) never collide.
    """
    h = hashlib.sha1()
    for d in sorted(netlist.devices, key=lambda d: d.name):
        h.update(("%s|%s|%s|%s|%s|%.6g\n" % (
            d.name, d.drain, d.gate, d.source, "P" if d.is_p else "N",
            d.width_um)).encode())
    return h.hexdigest()[:12]


# --------------------------------------------------------------------------
# the extracted arrangements (migration record; provenance-tested)
# --------------------------------------------------------------------------

#: Per-cell extracted ASTRAN arrangements, keyed by (subckt name, digest).
#: Plain data: p/n rows as ((device, left_net, right_net), ...) in
#: left-to-right die order.  ``verdict`` records the measured outcome
#: (exact-infeasible: the full-vocabulary CP-SAT proof of AUDIT 5.60).
EXTRACTED_TABLE = {
    ('CLKBUF1', '8cf4a81927d7'): {
        "source": 'original_astran_cells/CLKBUF1.gds',
        "astran_um": 1.9,
        "p_strips": 1, "n_strips": 1,
        "verdict": "exact-infeasible",
        "p": (
        ('M0', 'VCC', 'a_9_6#'), ('M1', 'a_9_6#', 'VCC'), ('M2', 'VCC', 'a_25_6#'), ('M3', 'a_25_6#', 'VCC'),
        ('M4', 'VCC', 'a_41_6#'), ('M5', 'a_41_6#', 'VCC'), ('M6', 'VCC', 'Y'), ('M7', 'Y', 'VCC'),
    ),
        "n": (
        ('M8', 'GND', 'a_9_6#'), ('M9', 'a_9_6#', 'GND'), ('M10', 'GND', 'a_25_6#'), ('M11', 'a_25_6#', 'GND'),
        ('M12', 'GND', 'a_41_6#'), ('M13', 'a_41_6#', 'GND'), ('M14', 'GND', 'Y'), ('M15', 'Y', 'GND'),
    ),
    },
    ('DFFNEGX1', '2dbd20aa37c7'): {
        "source": 'original_astran_cells/DFFNEGX1.gds',
        "astran_um": 3.23,
        "p_strips": 2, "n_strips": 2,
        "verdict": "exact-infeasible",
        "p": (
        ('M1', 'VCC', 'a_17_74#'), ('M2', 'a_17_74#', 'a_23_6#'), ('M3', 'a_23_6#', 'a_31_74#'), ('M4', 'a_31_74#', 'VCC'),
        ('M5', 'VCC', 'a_34_4#'), ('M0', 'a_2_6#', 'VCC'), ('M6', 'VCC', 'a_61_74#'), ('M7', 'a_61_74#', 'a_66_6#'),
        ('M8', 'a_66_6#', 'a_76_84#'), ('M9', 'a_76_84#', 'VCC'), ('M11', 'VCC', 'Q'),
    ),
        "n": (
        ('M12', 'GND', 'a_17_6#'), ('M13', 'a_17_6#', 'a_23_6#'), ('M14', 'a_23_6#', 'a_31_6#'), ('M15', 'a_31_6#', 'GND'),
        ('M16', 'GND', 'a_34_4#'), ('M10', 'a_2_6#', 'GND'), ('M17', 'GND', 'a_61_6#'), ('M18', 'a_61_6#', 'a_66_6#'),
        ('M19', 'a_66_6#', 'a_76_6#'), ('M20', 'a_76_6#', 'GND'), ('M21', 'GND', 'Q'),
    ),
    },
    ('DFFPOSX1', 'd7bbc86b33f8'): {
        "source": 'original_astran_cells/DFFPOSX1.gds',
        "astran_um": 3.42,
        "p_strips": 2, "n_strips": 2,
        "verdict": "exact-infeasible",
        "p": (
        ('M1', 'VCC', 'a_17_74#'), ('M2', 'a_17_74#', 'a_22_6#'), ('M3', 'a_22_6#', 'a_31_74#'), ('M4', 'a_31_74#', 'VCC'),
        ('M5', 'VCC', 'a_34_4#'), ('M0', 'a_2_6#', 'VCC'), ('M6', 'VCC', 'a_61_74#'), ('M7', 'a_61_74#', 'a_66_6#'),
        ('M8', 'a_66_6#', 'a_76_84#'), ('M9', 'a_76_84#', 'VCC'), ('M11', 'VCC', 'Q'),
    ),
        "n": (
        ('M12', 'GND', 'a_17_6#'), ('M13', 'a_17_6#', 'a_22_6#'), ('M14', 'a_22_6#', 'a_31_6#'), ('M15', 'a_31_6#', 'GND'),
        ('M16', 'GND', 'a_34_4#'), ('M10', 'a_2_6#', 'GND'), ('M17', 'GND', 'a_61_6#'), ('M18', 'a_61_6#', 'a_66_6#'),
        ('M19', 'a_66_6#', 'a_76_6#'), ('M20', 'a_76_6#', 'GND'), ('M21', 'GND', 'Q'),
    ),
    },
    ('MUX2X1', '6028a7b039e2'): {
        "source": 'original_astran_cells/MUX2X1.gds',
        "astran_um": 1.33,
        "p_strips": 1, "n_strips": 1,
        "verdict": "exact-infeasible",
        "p": (
        ('M1', 'VCC', 'a_17_50#'), ('M2', 'a_17_50#', 'Y'), ('M3', 'Y', 'a_30_54#'), ('M4', 'a_30_54#', 'VCC'),
        ('M0', 'VCC', 'a_2_10#'),
    ),
        "n": (
        ('M6', 'GND', 'a_17_10#'), ('M7', 'a_17_10#', 'Y'), ('M8', 'Y', 'a_30_10#'), ('M9', 'a_30_10#', 'GND'),
        ('M5', 'GND', 'a_2_10#'),
    ),
    },
    ('NOR3X1', 'b9558e1535cd'): {
        "source": 'original_astran_cells/NOR3X1.gds',
        "astran_um": 1.33,
        "p_strips": 1, "n_strips": 1,
        "verdict": "exact-infeasible",
        "p": (
        ('M2', 'a_25_64#', 'a_2_64#'), ('M0', 'a_2_64#', 'VCC'), ('M1', 'VCC', 'a_2_64#'), ('M3', 'a_2_64#', 'a_25_64#'),
        ('M4', 'a_25_64#', 'Y'), ('M5', 'Y', 'a_25_64#'),
    ),
        "n": (
        ('M6', 'GND', 'Y'), ('M7', 'Y', 'GND'), ('M8', 'GND', 'Y'),
    ),
    },
    ('XNOR2X1', '5045c6d64101'): {
        "source": 'original_astran_cells/XNOR2X1.gds',
        "astran_um": 1.52,
        "p_strips": 1, "n_strips": 1,
        "verdict": "exact-infeasible",
        "p": (
        ('M5', 'a_12_41#', 'VCC'), ('M4', 'VCC', 'a_35_54#'), ('M3', 'a_35_54#', 'Y'), ('M2', 'Y', 'a_18_54#'),
        ('M1', 'a_18_54#', 'VCC'), ('M0', 'VCC', 'a_2_6#'),
    ),
        "n": (
        ('M11', 'a_12_41#', 'GND'), ('M10', 'GND', 'a_35_6#'), ('M9', 'a_35_6#', 'Y'), ('M8', 'Y', 'a_18_6#'),
        ('M7', 'a_18_6#', 'GND'), ('M6', 'GND', 'a_2_6#'),
    ),
    },
    ('XOR2X1', '638f68c918e4'): {
        "source": 'original_astran_cells/XOR2X1.gds',
        "astran_um": 1.9,
        "p_strips": 1, "n_strips": 1,
        "verdict": "exact-infeasible",
        "p": (
        ('M0', 'a_2_6#', 'VCC'), ('M4', 'VCC', 'a_35_54#'), ('M3', 'a_35_54#', 'Y'), ('M2', 'Y', 'a_18_54#'),
        ('M1', 'a_18_54#', 'VCC'), ('M5', 'VCC', 'a_13_43#'),
    ),
        "n": (
        ('M6', 'a_2_6#', 'GND'), ('M10', 'GND', 'a_35_6#'), ('M9', 'a_35_6#', 'Y'), ('M8', 'Y', 'a_18_6#'),
        ('M7', 'a_18_6#', 'GND'), ('M11', 'GND', 'a_13_43#'),
    ),
    },
    ('COMPLEX0', 'e6b547710f5e'): {
        "source": 'outputs/max/COMPLEX0.gds',
        "astran_um": 1.71,
        "p_strips": 1, "n_strips": 1,
        "verdict": "exact-infeasible",
        "p": (
        ('Mcl1#0', 'cl1#a_2_10#', 'VCC'), ('Mcl1#1', 'VCC', 'cl1#a_17_50#'), ('Mcl1#2', 'cl1#a_17_50#', 'cl1#Y'), ('Mcl1#3', 'cl1#Y', 'cl1#a_30_54#'),
        ('Mcl1#4', 'cl1#a_30_54#', 'VCC'), ('Mcl0#0', 'VCC', 'cl0#Y'),
    ),
        "n": (
        ('Mcl1#5', 'cl1#a_2_10#', 'GND'), ('Mcl1#6', 'GND', 'cl1#a_17_10#'), ('Mcl1#7', 'cl1#a_17_10#', 'cl1#Y'), ('Mcl1#8', 'cl1#Y', 'cl1#a_30_10#'),
        ('Mcl1#9', 'cl1#a_30_10#', 'GND'), ('Mcl0#1', 'GND', 'cl0#Y'),
    ),
    },
    ('COMPLEX0', '13d6093208c8'): {
        "source": 'outputs/multiplier/COMPLEX0.gds',
        "astran_um": 5.51,
        "p_strips": 2, "n_strips": 3,
        "verdict": "exact-infeasible",
        "p": (
        ('Mcl1#0', 'VCC', 'cl1#Y'), ('Mcl1#1', 'cl1#Y', 'VCC'), ('Mcl2#1', 'VCC', 'cl2#Y'), ('Mcl2#0', 'cl2#Y', 'VCC'),
        ('Mcl0#0', 'VCC', 'cl0#Y'), ('Mcl0#1', 'cl0#Y', 'VCC'), ('Mcl0#2', 'VCC', 'cl0#Y'), ('Mcl3#3', 'cl3#a_2_54#', 'cl3#Y'),
        ('Mcl3#2', 'cl3#Y', 'cl3#a_2_54#'), ('Mcl3#1', 'cl3#a_2_54#', 'VCC'), ('Mcl3#0', 'VCC', 'cl3#a_2_54#'),
    ),
        "n": (
        ('Mcl1#2', 'GND', 'cl1#a_9_6#'), ('Mcl1#3', 'cl1#a_9_6#', 'cl1#Y'), ('Mcl2#3', 'cl2#Y', 'cl2#a_9_6#'), ('Mcl2#2', 'cl2#a_9_6#', 'GND'),
        ('Mcl0#3', 'GND', 'cl0#a_9_6#'), ('Mcl0#4', 'cl0#a_9_6#', 'cl0#a_14_6#'), ('Mcl0#5', 'cl0#a_14_6#', 'cl0#Y'), ('Mcl3#7', 'GND', 'cl3#a_28_6#'),
        ('Mcl3#6', 'cl3#a_28_6#', 'cl3#Y'), ('Mcl3#5', 'cl3#Y', 'cl3#a_11_6#'), ('Mcl3#4', 'cl3#a_11_6#', 'GND'),
    ),
    },
    ('COMPLEX1', 'aa4c72582c5b'): {
        "source": 'outputs/adder/COMPLEX1.gds',
        "astran_um": 3.61,
        "p_strips": 3, "n_strips": 3,
        "verdict": "exact-infeasible",
        "p": (
        ('Mcl1#0', 'cl1#a_2_6#', 'VCC'), ('Mcl1#4', 'VCC', 'cl1#a_35_54#'), ('Mcl1#3', 'cl1#a_35_54#', 'cl1#Y'), ('Mcl1#2', 'cl1#Y', 'cl1#a_18_54#'),
        ('Mcl1#1', 'cl1#a_18_54#', 'VCC'), ('Mcl1#5', 'VCC', 'cl1#a_13_43#'), ('Mcl0#0', 'cl0#a_2_6#', 'VCC'), ('Mcl0#4', 'VCC', 'cl0#a_35_54#'),
        ('Mcl0#3', 'cl0#a_35_54#', 'cl0#Y'), ('Mcl0#2', 'cl0#Y', 'cl0#a_18_54#'), ('Mcl0#1', 'cl0#a_18_54#', 'VCC'), ('Mcl0#5', 'VCC', 'cl0#a_12_41#'),
        ('Mcl2#2', 'VCC', 'cl2#Y'), ('Mcl2#1', 'cl2#Y', 'cl2#a_9_54#'), ('Mcl2#0', 'cl2#a_9_54#', 'VCC'),
    ),
        "n": (
        ('Mcl1#6', 'cl1#a_2_6#', 'GND'), ('Mcl1#10', 'GND', 'cl1#a_35_6#'), ('Mcl1#9', 'cl1#a_35_6#', 'cl1#Y'), ('Mcl1#8', 'cl1#Y', 'cl1#a_18_6#'),
        ('Mcl1#7', 'cl1#a_18_6#', 'GND'), ('Mcl1#11', 'GND', 'cl1#a_13_43#'), ('Mcl0#6', 'cl0#a_2_6#', 'GND'), ('Mcl0#10', 'GND', 'cl0#a_35_6#'),
        ('Mcl0#9', 'cl0#a_35_6#', 'cl0#Y'), ('Mcl0#8', 'cl0#Y', 'cl0#a_18_6#'), ('Mcl0#7', 'cl0#a_18_6#', 'GND'), ('Mcl0#11', 'GND', 'cl0#a_12_41#'),
        ('Mcl2#5', 'cl2#Y', 'cl2#a_2_6#'), ('Mcl2#4', 'cl2#a_2_6#', 'GND'), ('Mcl2#3', 'GND', 'cl2#a_2_6#'),
    ),
    },
    ('COMPLEX10', '0c7877ba445b'): {
        "source": 'outputs/adder/COMPLEX10.gds',
        "astran_um": 4.37,
        "p_strips": 4, "n_strips": 4,
        "verdict": "exact-infeasible",
        "p": (
        ('Mcl3#2', 'cl3#Y', 'cl3#a_2_54#'), ('Mcl3#1', 'cl3#a_2_54#', 'VCC'), ('Mcl3#0', 'VCC', 'cl3#a_2_54#'), ('Mcl2#2', 'cl2#Y', 'VCC'),
        ('Mcl2#0', 'VCC', 'cl2#a_9_54#'), ('Mcl2#1', 'cl2#a_9_54#', 'cl2#Y'), ('Mcl0#5', 'cl0#a_12_41#', 'VCC'), ('Mcl0#1', 'VCC', 'cl0#a_18_54#'),
        ('Mcl0#2', 'cl0#a_18_54#', 'cl0#Y'), ('Mcl0#3', 'cl0#Y', 'cl0#a_35_54#'), ('Mcl0#4', 'cl0#a_35_54#', 'VCC'), ('Mcl0#0', 'VCC', 'cl0#a_2_6#'),
        ('Mcl1#5', 'cl1#a_13_43#', 'VCC'), ('Mcl1#1', 'VCC', 'cl1#a_18_54#'), ('Mcl1#2', 'cl1#a_18_54#', 'cl1#Y'), ('Mcl1#3', 'cl1#Y', 'cl1#a_35_54#'),
        ('Mcl1#4', 'cl1#a_35_54#', 'VCC'), ('Mcl1#0', 'VCC', 'cl1#a_2_6#'),
    ),
        "n": (
        ('Mcl3#5', 'GND', 'cl3#Y'), ('Mcl3#4', 'cl3#Y', 'cl3#a_12_6#'), ('Mcl3#3', 'cl3#a_12_6#', 'GND'), ('Mcl2#5', 'cl2#Y', 'cl2#a_2_6#'),
        ('Mcl2#3', 'cl2#a_2_6#', 'GND'), ('Mcl2#4', 'GND', 'cl2#a_2_6#'), ('Mcl0#11', 'cl0#a_12_41#', 'GND'), ('Mcl0#7', 'GND', 'cl0#a_18_6#'),
        ('Mcl0#8', 'cl0#a_18_6#', 'cl0#Y'), ('Mcl0#9', 'cl0#Y', 'cl0#a_35_6#'), ('Mcl0#10', 'cl0#a_35_6#', 'GND'), ('Mcl0#6', 'GND', 'cl0#a_2_6#'),
        ('Mcl1#11', 'cl1#a_13_43#', 'GND'), ('Mcl1#7', 'GND', 'cl1#a_18_6#'), ('Mcl1#8', 'cl1#a_18_6#', 'cl1#Y'), ('Mcl1#9', 'cl1#Y', 'cl1#a_35_6#'),
        ('Mcl1#10', 'cl1#a_35_6#', 'GND'), ('Mcl1#6', 'GND', 'cl1#a_2_6#'),
    ),
    },
    ('COMPLEX11', '419776c896b9'): {
        "source": 'outputs/adder/COMPLEX11.gds',
        "astran_um": 3.8,
        "p_strips": 3, "n_strips": 4,
        "verdict": "exact-infeasible",
        "p": (
        ('Mcl2#0', 'cl2#a_2_54#', 'cl2#a_9_54#'), ('Mcl2#1', 'cl2#a_9_54#', 'VCC'), ('Mcl2#2', 'VCC', 'cl2#Y'), ('Mcl4#2', 'VCC', 'cl4#Y'),
        ('Mcl4#1', 'cl4#Y', 'cl4#a_9_54#'), ('Mcl4#0', 'cl4#a_9_54#', 'VCC'), ('Mcl0#1', 'VCC', 'cl0#Y'), ('Mcl0#0', 'cl0#Y', 'VCC'),
        ('Mcl1#0', 'VCC', 'cl1#Y'), ('Mcl1#1', 'cl1#Y', 'VCC'), ('Mcl3#0', 'cl3#a_2_6#', 'VCC'), ('Mcl3#1', 'VCC', 'cl3#a_18_54#'),
        ('Mcl3#2', 'cl3#a_18_54#', 'cl3#Y'), ('Mcl3#3', 'cl3#Y', 'cl3#a_35_54#'), ('Mcl3#4', 'cl3#a_35_54#', 'VCC'), ('Mcl3#5', 'VCC', 'cl3#a_12_41#'),
    ),
        "n": (
        ('Mcl2#3', 'GND', 'cl2#a_2_54#'), ('Mcl2#4', 'cl2#a_2_54#', 'GND'), ('Mcl2#5', 'GND', 'cl2#Y'), ('Mcl4#5', 'cl4#Y', 'cl4#a_2_6#'),
        ('Mcl4#4', 'cl4#a_2_6#', 'GND'), ('Mcl4#3', 'GND', 'cl4#a_2_6#'), ('Mcl0#3', 'cl0#Y', 'cl0#a_9_6#'), ('Mcl0#2', 'cl0#a_9_6#', 'GND'),
        ('Mcl1#2', 'GND', 'cl1#a_9_6#'), ('Mcl1#3', 'cl1#a_9_6#', 'cl1#Y'), ('Mcl3#6', 'cl3#a_2_6#', 'GND'), ('Mcl3#7', 'GND', 'cl3#a_18_6#'),
        ('Mcl3#8', 'cl3#a_18_6#', 'cl3#Y'), ('Mcl3#9', 'cl3#Y', 'cl3#a_35_6#'), ('Mcl3#10', 'cl3#a_35_6#', 'GND'), ('Mcl3#11', 'GND', 'cl3#a_12_41#'),
    ),
    },
    ('COMPLEX20', '3b6bc5270d1d'): {
        "source": 'outputs/max/COMPLEX20.gds',
        "astran_um": 2.85,
        "p_strips": 3, "n_strips": 3,
        "verdict": "exact-infeasible",
        "p": (
        ('Mcl3#0', 'VCC', 'cl3#a_9_54#'), ('Mcl3#1', 'cl3#a_9_54#', 'cl3#Y'), ('Mcl3#2', 'cl3#Y', 'VCC'), ('Mcl0#3', 'cl0#a_2_54#', 'cl0#Y'),
        ('Mcl0#2', 'cl0#Y', 'cl0#a_2_54#'), ('Mcl0#1', 'cl0#a_2_54#', 'VCC'), ('Mcl0#0', 'VCC', 'cl0#a_2_54#'), ('Mcl2#0', 'cl2#Y', 'VCC'),
        ('Mcl1#0', 'VCC', 'cl1#Y'),
    ),
        "n": (
        ('Mcl3#3', 'cl3#a_2_6#', 'GND'), ('Mcl3#4', 'GND', 'cl3#a_2_6#'), ('Mcl3#5', 'cl3#a_2_6#', 'cl3#Y'), ('Mcl0#7', 'GND', 'cl0#a_28_6#'),
        ('Mcl0#6', 'cl0#a_28_6#', 'cl0#Y'), ('Mcl0#5', 'cl0#Y', 'cl0#a_11_6#'), ('Mcl0#4', 'cl0#a_11_6#', 'GND'), ('Mcl2#1', 'cl2#Y', 'GND'),
        ('Mcl1#1', 'GND', 'cl1#Y'),
    ),
    },
    ('COMPLEX7', 'd674408ae52e'): {
        "source": 'outputs/multiplier/COMPLEX7.gds',
        "astran_um": 4.18,
        "p_strips": 3, "n_strips": 3,
        "verdict": "exact-infeasible",
        "p": (
        ('Mcl2#0', 'cl2#a_2_6#', 'VCC'), ('Mcl2#1', 'VCC', 'cl2#a_18_54#'), ('Mcl2#2', 'cl2#a_18_54#', 'cl2#Y'), ('Mcl2#3', 'cl2#Y', 'cl2#a_35_54#'),
        ('Mcl2#4', 'cl2#a_35_54#', 'VCC'), ('Mcl2#5', 'VCC', 'cl2#a_12_41#'), ('Mcl0#1', 'VCC', 'cl0#Y'), ('Mcl0#0', 'cl0#Y', 'VCC'),
        ('Mcl1#5', 'cl1#a_12_41#', 'VCC'), ('Mcl1#4', 'VCC', 'cl1#a_35_54#'), ('Mcl1#3', 'cl1#a_35_54#', 'cl1#Y'), ('Mcl1#2', 'cl1#Y', 'cl1#a_18_54#'),
        ('Mcl1#1', 'cl1#a_18_54#', 'VCC'), ('Mcl1#0', 'VCC', 'cl1#a_2_6#'),
    ),
        "n": (
        ('Mcl2#6', 'cl2#a_2_6#', 'GND'), ('Mcl2#7', 'GND', 'cl2#a_18_6#'), ('Mcl2#8', 'cl2#a_18_6#', 'cl2#Y'), ('Mcl2#9', 'cl2#Y', 'cl2#a_35_6#'),
        ('Mcl2#10', 'cl2#a_35_6#', 'GND'), ('Mcl2#11', 'GND', 'cl2#a_12_41#'), ('Mcl0#3', 'cl0#Y', 'cl0#a_9_6#'), ('Mcl0#2', 'cl0#a_9_6#', 'GND'),
        ('Mcl1#11', 'cl1#a_12_41#', 'GND'), ('Mcl1#10', 'GND', 'cl1#a_35_6#'), ('Mcl1#9', 'cl1#a_35_6#', 'cl1#Y'), ('Mcl1#8', 'cl1#Y', 'cl1#a_18_6#'),
        ('Mcl1#7', 'cl1#a_18_6#', 'GND'), ('Mcl1#6', 'GND', 'cl1#a_2_6#'),
    ),
    },
    ('COMPLEX9', 'f7639553a301'): {
        "source": 'outputs/adder/COMPLEX9.gds',
        "astran_um": 3.42,
        "p_strips": 3, "n_strips": 3,
        "verdict": "exact-infeasible",
        "p": (
        ('Mcl2#0', 'cl2#a_2_54#', 'cl2#a_9_54#'), ('Mcl2#1', 'cl2#a_9_54#', 'VCC'), ('Mcl2#2', 'VCC', 'cl2#Y'), ('Mcl0#1', 'VCC', 'cl0#Y'),
        ('Mcl0#0', 'cl0#Y', 'VCC'), ('Mcl1#0', 'VCC', 'cl1#Y'), ('Mcl1#1', 'cl1#Y', 'VCC'), ('Mcl3#0', 'cl3#a_2_6#', 'VCC'),
        ('Mcl3#4', 'VCC', 'cl3#a_35_54#'), ('Mcl3#3', 'cl3#a_35_54#', 'cl3#Y'), ('Mcl3#2', 'cl3#Y', 'cl3#a_18_54#'), ('Mcl3#1', 'cl3#a_18_54#', 'VCC'),
        ('Mcl3#5', 'VCC', 'cl3#a_12_41#'),
    ),
        "n": (
        ('Mcl2#3', 'GND', 'cl2#a_2_54#'), ('Mcl2#4', 'cl2#a_2_54#', 'GND'), ('Mcl2#5', 'GND', 'cl2#Y'), ('Mcl0#3', 'cl0#Y', 'cl0#a_9_6#'),
        ('Mcl0#2', 'cl0#a_9_6#', 'GND'), ('Mcl1#2', 'GND', 'cl1#a_9_6#'), ('Mcl1#3', 'cl1#a_9_6#', 'cl1#Y'), ('Mcl3#6', 'cl3#a_2_6#', 'GND'),
        ('Mcl3#10', 'GND', 'cl3#a_35_6#'), ('Mcl3#9', 'cl3#a_35_6#', 'cl3#Y'), ('Mcl3#8', 'cl3#Y', 'cl3#a_18_6#'), ('Mcl3#7', 'cl3#a_18_6#', 'GND'),
        ('Mcl3#11', 'GND', 'cl3#a_12_41#'),
    ),
    },
}

#: The runtime closure table: arrangements that CLOSE (route or exact
#: solve verified clean) and therefore became Python-owned.  An entry
#: here makes :func:`seed_candidates` hand the arrangement to the
#: speculate pool as its FIRST candidate -- the closure then reproduces
#: from this table alone, no .gds consulted.  Empty today: the 15
#: extracted arrangements are all exact-infeasible in the current
#: vocabulary (AUDIT 5.60), so committing them as production candidates
#: would only burn trials; the honest capture list is empty.
SEED_TABLE = {
}


# --------------------------------------------------------------------------
# candidate construction
# --------------------------------------------------------------------------

def _table_entry(table, netlist):
    name = getattr(getattr(netlist, "subckt", None), "subckt_name", None)
    if name is None:
        return None
    return table.get((name, netlist_digest(netlist)))


def seed_orderings(netlist, entry):
    """(ordering_p, ordering_n) as single-member DiffusionBlocks.

    One block per transistor carrying its die orientation, so
    geometry.place_row reproduces the extracted arrangement: contiguous
    where ASTRAN's strip continues (facing nets equal), one break column
    where ASTRAN's strips separate (facing nets differ -- measured on
    every extracted cell).  Pure function of (netlist, entry).
    """
    dev = {d.name: d for d in netlist.devices}
    out = []
    for row in ("p", "n"):
        blocks = []
        for name, lnet, rnet in entry[row]:
            blocks.append(DiffusionBlock(
                "single", [BlockMember(dev[name], lnet, rnet)]))
        out.append(blocks)
    return out[0], out[1]


def _entry_covers(entry, netlist):
    """Whether the entry's device names cover the netlist exactly once."""
    names = [t[0] for t in entry["p"]] + [t[0] for t in entry["n"]]
    want = {d.name for d in netlist.devices}
    return len(names) == len(set(names)) and set(names) == want


def seed_candidates(netlist, table=None):
    """The seed candidate class: [(kind, ordering_p, ordering_n)].

    Lazy and cheap: one digest lookup; empty for every netlist not in
    the closure table (all of them today), so the engine's speculate
    pool is untouched for every closing cell.  A table cell whose fold
    decision changed the netlist (device names no longer covered) is
    honestly skipped -- the seed speaks the arrangement of the exact
    netlist it was extracted from.
    """
    table = SEED_TABLE if table is None else table
    entry = _table_entry(table, netlist)
    if entry is None or not _entry_covers(entry, netlist):
        return []
    ordering_p, ordering_n = seed_orderings(netlist, entry)
    return [(SEED_KIND, ordering_p, ordering_n)]


# --------------------------------------------------------------------------
# the extractor (migration time; provenance-tested against the .gds)
# --------------------------------------------------------------------------

class ExtractError(Exception):
    """The arrangement did not extract: ``args[0]`` says what and where."""


def _ov(a0, a1, b0, b1):
    return a0 <= b1 + _EPS and b0 <= a1 + _EPS


def _rects_ov(a, b):
    return _ov(a[0][0], a[1][0], b[0][0], b[1][0]) \
        and _ov(a[0][1], a[1][1], b[0][1], b[1][1])


class _UF(object):
    """Union-find over rect indices (deterministic: min-root union)."""

    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def _rect_clusters(rects):
    """(clusters, cluster index per rect) under rect overlap/touch."""
    n = len(rects)
    uf = _UF(n)
    for i in range(n):
        for j in range(i + 1, n):
            if _rects_ov(rects[i], rects[j]):
                uf.union(i, j)
    groups = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)
    order = sorted(groups)
    cl_of = [0] * n
    clusters = []
    for k, root in enumerate(order):
        clusters.append(groups[root])
        for i in groups[root]:
            cl_of[i] = k
    return clusters, cl_of


def extract_arrangement(netlist, gds_path):
    """Extract ASTRAN's arrangement from one .gds as per-row oriented
    device sequences.

    Returns ``{"p": [(dev, lnet, rnet)], "n": [...],
    "metrics": {p_trans, n_trans, p_strips, n_strips, tap_strips}}`` --
    exactly what :func:`seed_orderings` and the EXTRACTED_TABLE entries
    consume.  Raises :class:`ExtractError` with an honest reason on any
    coverage failure.  Deterministic (sorted structures everywhere,
    invariant 9); pure function of (netlist, gds_path).
    """
    import gdstk

    lib = gdstk.read_gds(gds_path)
    cell = lib.top_level()[0]
    active, polyg, cont, m1 = [], [], [], []
    bb = None
    for p in cell.polygons:
        r = p.bounding_box()
        if p.layer == 1:
            active.append(r)
        elif p.layer == 9:
            polyg.append(r)
        elif p.layer == 10:
            cont.append(r)
        elif p.layer == 49:
            m1.append(r)
        elif p.layer == 235:
            bb = r
    if bb is None:
        raise ExtractError("no prBoundary outline")
    mid = (bb[0][1] + bb[1][1]) / 2.0

    m1_cl, m1_cl_of = _rect_clusters(m1)
    poly_cl, poly_cl_of = _rect_clusters(polyg)

    # ---- strips: connected active components per polarity row ----------
    strips = []
    for row in (0, 1):                     # 0 = P (upper), 1 = N
        rects = [r for r in active
                 if ((r[0][1] + r[1][1]) / 2.0 > mid) == (row == 0)]
        for members in _rect_clusters(rects)[0]:
            grp = [rects[i] for i in members]
            strips.append({
                "row": row, "rects": grp,
                "x0": min(r[0][0] for r in grp),
                "x1": max(r[1][0] for r in grp),
                "ylo": min(r[0][1] for r in grp),
                "yhi": max(r[1][1] for r in grp)})
    strips.sort(key=lambda s: (s["row"], s["x0"]))

    # ---- gates: narrow poly rects crossing a strip ----------------------
    for s in strips:
        crossing = []
        for pi, pr in enumerate(polyg):
            if pr[1][0] - pr[0][0] > _GATE_MAX_WIDTH:
                continue                    # poly routing, not a gate
            for ar in s["rects"]:
                if _rects_ov(pr, ar):
                    crossing.append((pi, pr))
                    break
        crossing.sort(key=lambda t: (t[1][0][0], t[1][1][0]))
        cols = []
        for pi, pr in crossing:
            if cols and _ov(cols[-1]["x0"], cols[-1]["x1"],
                            pr[0][0], pr[1][0]):
                cols[-1]["polys"].append(pi)
                cols[-1]["x0"] = min(cols[-1]["x0"], pr[0][0])
                cols[-1]["x1"] = max(cols[-1]["x1"], pr[1][0])
            else:
                cols.append({"polys": [pi], "x0": pr[0][0],
                             "x1": pr[1][0]})
        for g in cols:
            g["x"] = (g["x0"] + g["x1"]) / 2.0
            ylo, yhi = None, None
            for ar in s["rects"]:
                if ar[0][0] - _EPS <= g["x"] <= ar[1][0] + _EPS:
                    ylo = ar[0][1] if ylo is None else min(ylo, ar[0][1])
                    yhi = ar[1][1] if yhi is None else max(yhi, ar[1][1])
            # W is a hint only: the union at the gate x reads the tallest
            # adjacent region (a W=0.5 device flanked by W=1.0 neighbours
            # measures 1.0), so it sorts the device candidates but never
            # rejects -- the gate-net + terminal-pair chain validates.
            g["w"] = ((yhi or 0) - (ylo or 0)) / UNITS_PER_UM
        s["gates"] = cols
        regions = []
        bounds = [s["x0"]] + [g["x"] for g in cols] + [s["x1"]]
        for i in range(len(cols) + 1):
            regions.append({"row": s["row"], "lo": bounds[i],
                            "hi": bounds[i + 1], "strip": s, "idx": i})
        s["regions"] = regions

    tap_strips = [s for s in strips if not s["gates"]]
    strips = [s for s in strips if s["gates"]]

    # ---- components: metal1 + poly + regions bridged by contacts --------
    regions_all = [r for s in strips for r in s["regions"]]
    n_m1, n_poly = len(m1_cl), len(poly_cl)
    base_poly, base_reg = n_m1, n_m1 + n_poly
    uf = _UF(n_m1 + n_poly + len(regions_all))
    for ri, r in enumerate(regions_all):
        r["node"] = base_reg + ri
        r["adj"] = 1 if (r["idx"] == 0
                         or r["idx"] == len(r["strip"]["gates"])) else 2

    for c in cont:
        ms = {m1_cl_of[i] for i, r in enumerate(m1) if _rects_ov(c, r)}
        if not ms:
            continue
        ps = {poly_cl_of[i] for i, r in enumerate(polyg)
              if _rects_ov(c, r)}
        if ps:
            for mi in ms:
                for pi in ps:
                    uf.union(mi, base_poly + pi)
            continue
        cx, cy = (c[0][0] + c[1][0]) / 2.0, (c[0][1] + c[1][1]) / 2.0
        for r in regions_all:
            s = r["strip"]
            if r["lo"] - _EPS <= cx <= r["hi"] + _EPS \
                    and s["ylo"] - _EPS <= cy <= s["yhi"] + _EPS:
                for mi in ms:
                    uf.union(mi, r["node"])
                break

    # labels pin external nets case-blind (ASTRAN upper-cases labels)
    label_comps = {}
    for lab in cell.labels:
        if lab.layer != 49:
            continue
        lx, ly = lab.origin
        for i, r in enumerate(m1):
            if r[0][0] - _EPS <= lx <= r[1][0] + _EPS \
                    and r[0][1] - _EPS <= ly <= r[1][1] + _EPS:
                label_comps[uf.find(m1_cl_of[i])] = lab.text
                break

    comp_gates = {}
    for s in strips:
        for g in s["gates"]:
            g["comp"] = uf.find(base_poly + poly_cl_of[g["polys"][0]])
            for pi in g["polys"][1:]:
                other = uf.find(base_poly + poly_cl_of[pi])
                if other != g["comp"]:
                    raise ExtractError(
                        "gate column spans two poly components")
            comp_gates.setdefault(g["comp"], []).append((s["row"], s, g))
    comp_regions = {}
    for r in regions_all:
        r["comp"] = uf.find(r["node"])
        comp_regions.setdefault(r["comp"], []).append(r)

    def comp_sig(comp):
        return (sum(1 for row, _s, _g in comp_gates.get(comp, ())
                    if row == 0),
                sum(1 for row, _s, _g in comp_gates.get(comp, ())
                    if row == 1),
                sum(r["adj"] for r in comp_regions.get(comp, ())
                    if r["row"] == 0),
                sum(r["adj"] for r in comp_regions.get(comp, ())
                    if r["row"] == 1))

    net_sig = {}
    for net in netlist.nets:
        net_sig[net] = (
            sum(1 for d in netlist.devices if d.is_p and d.gate == net),
            sum(1 for d in netlist.devices if not d.is_p and d.gate == net),
            sum(1 for d in netlist.devices
                if d.is_p and net in (d.source, d.drain)),
            sum(1 for d in netlist.devices
                if not d.is_p and net in (d.source, d.drain)))

    net_comps = set(comp_gates) | set(comp_regions)
    upper_net = {}
    for net in sorted(netlist.nets):
        upper_net.setdefault(net.upper(), net)
    # candidate net sets: label-pinned, exact signature match, or
    # unconstrained (None -- pinned by the device walk below)
    cand = {}
    for comp in sorted(net_comps):
        lab = label_comps.get(comp)
        if lab is not None and lab.upper() in upper_net:
            cand[comp] = frozenset((upper_net[lab.upper()],))
            continue
        options = frozenset(n for n in sorted(net_sig)
                            if net_sig[n] == comp_sig(comp))
        cand[comp] = options or None

    # ---- the deterministic device walk ----------------------------------
    dev_by_row = {0: [d for d in netlist.devices if d.is_p],
                  1: [d for d in netlist.devices if not d.is_p]}
    gates_seq = []
    for s in strips:
        for gi, g in enumerate(s["gates"]):
            gates_seq.append((s, gi, g))

    comp_cand = dict(cand)

    def options_for(comp):
        return comp_cand.get(comp, cand.get(comp))

    def restrict(comp, nets):
        cur = comp_cand.get(comp, cand.get(comp))
        if cur is None:
            comp_cand[comp] = frozenset(nets)
            return True
        new = cur & frozenset(nets)
        if not new:
            return False
        comp_cand[comp] = new
        return True

    def solve(k, used, acc):
        if k == len(gates_seq):
            return {0: list(acc[0]), 1: list(acc[1])}
        s, gi, g = gates_seq[k]
        row = s["row"]
        r_left, r_right = s["regions"][gi], s["regions"][gi + 1]
        g_opts = options_for(g["comp"])
        ordered = sorted(dev_by_row[row],
                         key=lambda d: (abs(d.width_um - g["w"]), d.name))
        for d in ordered:
            if d.name in used:
                continue
            if g_opts is not None and d.gate not in g_opts:
                continue
            terms = [d.source, d.drain]
            lopts = options_for(r_left["comp"])
            ropts = options_for(r_right["comp"])
            lset = [t for t in terms if lopts is None or t in lopts]
            rset = [t for t in terms if ropts is None or t in ropts]
            if not lset or not rset:
                continue
            saved = dict(comp_cand)
            choices = []
            if d.source == d.drain:
                choices.append((d.source, d.source))
            else:
                if d.source in lset and d.drain in rset:
                    choices.append((d.source, d.drain))
                if d.drain in lset and d.source in rset:
                    choices.append((d.drain, d.source))
            for lnet, rnet in choices:
                ok = restrict(g["comp"], (d.gate,)) \
                    and restrict(r_left["comp"], (lnet,)) \
                    and restrict(r_right["comp"], (rnet,))
                if not ok:
                    comp_cand.clear()
                    comp_cand.update(saved)
                    continue
                used.add(d.name)
                acc[row].append((d.name, lnet, rnet))
                out = solve(k + 1, used, acc)
                if out is not None:
                    return out
                acc[row].pop()
                used.discard(d.name)
                comp_cand.clear()
                comp_cand.update(saved)
            comp_cand.clear()
            comp_cand.update(saved)
        return None

    result = solve(0, set(), {0: [], 1: []})
    if result is None:
        raise ExtractError("device walk found no consistent assignment")
    for opts in comp_cand.values():
        if opts is not None and len(opts) > 1:
            raise ExtractError(
                "net identity unresolved for an ambiguous component")
    return {
        "p": result[0], "n": result[1],
        "metrics": {
            "p_trans": sum(len(s["gates"]) for s in strips
                           if s["row"] == 0),
            "n_trans": sum(len(s["gates"]) for s in strips
                           if s["row"] == 1),
            "p_strips": sum(1 for s in strips if s["row"] == 0),
            "n_strips": sum(1 for s in strips if s["row"] == 1),
            "tap_strips": len(tap_strips),
        },
    }


def candidate_from_gds(netlist, gds_path):
    """The one-call research path: extract + build the seed orderings.

    Returns (entry, ordering_p, ordering_n) where ``entry`` is the plain
    data shape of EXTRACTED_TABLE (``p``/``n``/``metrics``); raises
    :class:`ExtractError` on coverage failure.  What the next session's
    funnel runs after a vocabulary extension.
    """
    ext = extract_arrangement(netlist, gds_path)
    entry = {"p": [tuple(t) for t in ext["p"]],
             "n": [tuple(t) for t in ext["n"]],
             "metrics": ext["metrics"]}
    ordering_p, ordering_n = seed_orderings(netlist, entry)
    return entry, ordering_p, ordering_n
