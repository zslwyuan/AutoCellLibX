# BIGCELL slot geometry: ASTRAN's terminal-slot model, reverse-engineered

Status: design note for the `bigcell_engine` width-parity fix (stage 3).
Everything below labeled *measured* was read off the GDS files in
`flow/original_astran_cells/` (gdstk, calibrated 16.5 raw units/um -- the
same calibration `gui/gds_model.py` and `flow/layout_sanity.py` use) and
cross-checked against `tools/astran/src/autocell2.cpp` and
`tools/astran/src/cellnetlst.cpp`.  This document is the contract for
`bigcell_engine/geometry.py`, `place_sa.py`, `netlist_ext.py`,
`gds_cells.py` and the additive `smt_engine/verify.py` adaptation.

## 1. The defect being fixed

`bigcell_engine` inherited the exact engine's device-width model: a
transistor of electrical width W is drawn as a *horizontal* diffusion run
of `ceil(W / 0.19 um)` columns, so a NAND2's four W=0.5u devices occupy
12 columns (2.28 um) where ASTRAN produces 0.76 um.  ASTRAN does not do
this.  The measurements below show what ASTRAN actually does.

## 2. Measured facts

Calibration: every cell's prBoundary (layer 235) reads exactly the log's
"Cell Size" under 16.5 raw units/um (NAND2X1: 0.76 x 2.47).  All numbers
below are um in that frame.

### 2.1 W is drawn VERTICALLY

| cell / device       | W (.sp) | active strip y-extent |
|---------------------|---------|-----------------------|
| INVX1 PMOS          | 0.5u    | 0.50                  |
| INVX1 NMOS          | 0.25u   | 0.25                  |
| NAND2X1 both rows   | 0.5u    | 0.50                  |
| NOR2X1 P row        | 1u      | 1.00                  |
| NOR2X1 N row        | 0.25u   | 0.25                  |

`insertGate` (autocell2.cpp:1103) pins it in the source:
`y(currentDiff)a .. y(currentDiff)b == transWidth`.  The horizontal
footprint of a device is *not* a function of W.

### 2.2 The horizontal footprint is a slot sequence

Per diffusion run, x-positions (NAND2X1, local frame, outline 0..0.76):

```
contact columns : 0.275        0.46         0.65
gate columns    :     0.3675        0.5575
diffusion strip : 0.2375 .. 0.6875  (one strip, both rows)
```

- terminal contact slots sit on a 0.19 pitch (0.275 -> 0.46 -> 0.65);
- each poly gate sits midway between its flanking contact slots
  (0.0925/0.0975 half-pitches);
- the diffusion strip extends 0.0375 beyond the outermost contacts
  (strip = contact span + 0.075).

So **one 0.19 um column = one (terminal | gate | terminal) triple**: a
diffusion run of M transistors spans M columns, carries M+1 terminal
slots on the column *edges* (x = c * 0.19) and M gate slots at the
column *centres* (x = (c + 0.5) * 0.19).  Internal series/parallel
junctions occupy one shared edge slot; uncontacted internal junctions
(NOR2X1's Z) simply carry no contact -- they still occupy their edge
slot in the pitch.

These are exactly the column conventions `smt_engine` already uses:
`_track_x(c) = c*g` for vertical stripes (diffusion access) and
`_col_x(c) = (c+0.5)*g` for gate stripes.

### 2.3 Sharing: facing-equal nets reuse one contact slot

ASTRAN's route() walks the P and N orderings in lockstep
(autocell2.cpp:314-460): per step it creates a DIFF element (terminal
slot), a GATE element, and a second DIFF element; the next step creates
a NEW diff element only when `testGap` says the facing nets differ
(autocell2.cpp:226-241, 331).  Equal facing nets share the element --
one contact slot.  The placement cost's width proxy `posPN`
(cellnetlst.cpp:406-443) counts exactly this:
`posPN = 2L + 1 + gaps` (L = lockstep length, gaps = diffusion breaks),
which reproduces every log's "Final cost: Width=" (INVX1 3, NAND2X1 5,
NAND3X1 7, MUX2X1 11, XOR2X1 13).

The final compacted width is *smaller* than posPN because the LP packs
slots at the half pitch (2.2); the compaction result is pinned by
measurements, not by posPN.

### 2.4 Cells are ONE diffusion strip per row

Both rows of every measured cell draw a single continuous active strip
(per-device rects abut: NOR2X1's P row = two rects touching at the
shared Z edge, x 0.04..0.265 + 0.265..0.595).  Blocks that share a
terminal continue the strip; blocks separated by a diffusion break are
two strips.

### 2.5 Width table (the acceptance gate)

ASTRAN width vs `cols * 0.19 + 0.385` where cols = the widest row's
member columns (+1 per diffusion break) and 0.385 = 0.075 diffusion
enclosure + 0.2375 left pin-escape margin + 0.0725 right margin
(measured: INVX1/NAND2X1 left margin 0.2375, right 0.0725 exactly;
larger cells squeeze the escape margin -- the constant keeps every
reference cell inside the 0.8-1.3x band):

| cell     | ASTRAN um | cols | model um | ratio |
|----------|-----------|------|----------|-------|
| INVX1    | 0.57      | 1    | 0.575    | 1.01  |
| NAND2X1  | 0.76      | 2    | 0.765    | 1.01  |
| NOR2X1   | 0.76      | 2    | 0.765    | 1.01  |
| NAND3X1  | 0.76      | 3    | 0.955    | 1.26  |
| AOI21X1  | 0.95      | 3    | 0.955    | 1.01  |
| AND2X1   | 0.95      | 3    | 0.955    | 1.01  |
| OR2X1    | 0.95      | 3    | 0.955    | 1.01  |
| OAI21X1  | 0.95      | 3    | 0.955    | 1.01  |
| AOI22X1  | 1.14      | 4    | 1.145    | 1.00  |
| NOR3X1   | 1.33      | 6    | 1.525    | 1.15  |
| MUX2X1   | 1.33      | 5    | 1.335    | 1.00  |
| XNOR2X1  | 1.52      | 6    | 1.525    | 1.00  |
| CLKBUF1  | 1.90      | 8    | 1.905    | 1.00  |
| XOR2X1   | 1.90      | 6    | 1.525    | 0.80  |

(All 14 rows measured from the implemented chain -- zero diffusion gaps
on every cell, matching the logs' "Nr. Gaps=0" -- and regenerated by
`flow/_stage3_check/_width_table.py --gds`; every GDS passes
`layout_sanity.check_layout(units_per_um=1.0)`.)

### 2.6 Folding

`foldTrans` (cellnetlst.cpp:254-286) folds a device with W above the
per-row diffusion budget (empirically 1.2 um, already pinned in
`netlist_ext.py`) into `ceil(W / 1.2)` parallel *legs* -- new
transistors appended to the ordering.  Each leg is a first-class
transistor: it gets its own gate slot and its own terminal slots
(sharing where the eulerian path reuses a net).  Horizontally a leg is
ONE column; the leg's diffusion strip is W/legs tall.  BUFX4: 6 -> 7
transistors (one NMOS W=2u -> 2 legs... the log pins the count), FAX1:
28 -> 43.  Nothing about folding changes width per leg -- folding only
adds columns the way any other transistor does.

## 3. The slot-model IR (what changes in `geometry.py`)

The IR keeps its shape: `{Device: PlacedTransistor(row, start_col,
legs, leg_width_cols)}`, reinterpreted:

- **legs** = the fold-leg count (unchanged semantics);
- **leg_width_cols = 1**: one leg occupies ONE column -- its gate at
  the column centre, its terminals at the column edges.  (The old
  `ceil(W/0.19)` value is gone; W lives in the strip height.)
- `start_col` = the member's own column; its left terminal edge is
  `start_col`, right terminal edge `start_col + legs*leg_width_cols`
  (edge indices and column indices share one number line: edge e is
  the left boundary of column e);
- a block of k members occupies k columns and k+1 edge slots;
- **facing-equal-net blocks share the edge slot** (next block starts
  at the previous block's end edge -- no gap); different nets insert
  `BREAK_GAP_COLS = 1` empty break column between the facing edge
  slots (place_row's existing rule, unchanged code, new meaning);
- row width in columns = `sum(member columns) + breaks`; the cell
  width (um) = `width_cols * 0.19 + 0.385` (`geometry.width_um`).

`place_row` / `layout_cell` keep their signatures and determinism
(pure functions of the ordering).

## 4. SA cost over the slot model (`place_sa.py`)

The row picture moves to **half-slot coordinates** (ASTRAN's posPN
space): edge e -> 2e, gate of column c -> 2c+1.  A member registers its
left net at edge 2c, right net at edge 2(c+w), its gate(s) at
2(c+j)+1.  Net bounding boxes, congestion and `w_routing` (span) run
over the half-slot line; `gaps` and `width` stay in columns (width ==
`layout_cell`'s width, pinned by test); gate mismatches compare the
two rows' gate keys (2c+1) -- aligned gate columns share one poly
stripe.  The incremental==full machinery is unchanged (the pictures are
just sparser), and `sa_refine` keeps asserting it every iteration.

## 5. Blocks: expressing ASTRAN's eulerian runs

ASTRAN's ordering is a flat transistor path; every pair of consecutive
transistors with equal facing nets shares a slot.  The block
decomposition must reproduce that sharing or cells like NOR3X1 pay
phantom breaks:

- NOR3X1's P row is a "doubled" network: three 2-PMOS pairs
  (VCC-a2, a2-a25, a25-Y) whose coupler nodes a2/a25 each have FOUR
  device terminals.  ASTRAN's eulerian path runs all six in ONE strip:
  VCC M0 a2 M2 a25 M4 Y M5 a25 M3 a2 M1 VCC (6 columns, 7 terminal
  slots, 0 breaks; measured: 7 contact columns at 0.19 pitch).
  Keeping the pairs as blocks costs 2 break columns -> 8 columns
  (1.90 um, ratio 1.43 -- out of band).
- `build_bigcell_blocks` therefore gains `max_coupler_degree`
  (default 3 = today's behaviour exactly, so the exact-engine-parity
  tests stay verbatim); the slot chain passes an unbounded coupler
  degree so pure internal nodes of ANY degree >= 3 couple their units,
  the consuming parallel groups dissolve into singles, and the
  linearizer's trail grows by deterministic Euler splicing (when the
  greedy walk stalls, a remaining unit incident to any net of the run
  is spliced in at its leftmost position) -- reproducing the 6-member
  single strip above.

A consequence: one net can occupy SEVERAL edge slots of a row (a2
above appears twice).  Such slots all need contacts (the regions are
tied by metal after routing) -- `exposed_net_set`'s "internal junction
needs no contact" rule only holds for nets occupying ONE region.

## 6. GDS emission (`gds_cells.py`, new)

ASTRAN-style boxes (layer map from `smt_engine/gds.py`, imported not
forked): prBoundary outline `cols*0.19 + 0.385` wide x 2.47 tall;
nwell/pwell with ASTRAN's 0.235 overhang; 0.13 M1 supply rails drawn
inside the cell (invariant 2) with VCC/GND labels; per-member diffusion
strips x[stop..stop+legs*0.19] with y-extent = W (N strip anchored top
at nwell boundary - 0.0725 growing down, P strip anchored bottom at
nwell boundary + 0.0725 growing up); poly stripes at gate columns
(merged where P/N gates align, ASTRAN's shared-stripe style); contacts
(0.065 squares, stacked vertically to fill W like ASTRAN's 2-contact
columns) on every terminal slot whose net is exposed or multi-region;
M1 stubs from power slots to the rails.  With a RouteResult, the
route's stripes/segments/vias/poly-jumps are drawn shifted by the
escape margin (the route grid's column c lives at die x
0.2375 + c*0.19).  Honest GDS header (1 um / 1 nm) -- benchmark's
sanity call reads it with units_per_um=1.0.

## 7. `smt_engine/verify.py`: additive slot-model access

`verify_cell(..., slot_model=False)` -- default untouched.  With the
flag, diffusion access points come from the slot model (member edges at
their true edge columns, multi-region slots included) instead of
`diffusion_access_points` (which insets a single-column device's right
access into its own column).  Every other invariant is
representation-free and works unchanged: block abutment, break gaps,
stripe coverage, gate crossings, the BFS.

## 8. What route_grid must adapt later (NOT changed today)

`route_grid.py` consumes placements parametrically and already matches
the slot conventions for gates (`gate_access_points` at column centres)
and stripes (column edges).  To route slot-model cells it needs:

1. **Diffusion access edges**: `_oriented_diffusion_access_points`
   reads `(rnet, p.start_col + width - 1)` -- the exact engine's
   inset.  Slot model: right access at edge `start_col + width`
   (= column start+width's left edge).  For width==1 legs the inset
   collapses both terminals onto one column; the edge form is required.
2. **Multi-region nets**: a net occupying several edge slots of a row
   (section 5) needs its slots wired together (M1 tie) -- the point
   model must expose every occurrence, not only block ends.
3. **Die-frame shift**: with the GDS escape margin, route column c
   draws at x 0.2375 + c*0.19 (gds_cells does the shift; the router
   itself is frame-free).
4. **Track alignment**: the 7-track y-model's row bands (row_geometry)
   split each polarity into two 0.55 um sub-bands; the slot model draws
   one W-tall strip per polarity (up to 1.2 um).  Routing stripes
   reaching the strip centre tracks still work for W <= ~1.0; aligning
   the track model to the slot strips (or capping strip W) is pending
   alongside the router work.

Until then, unrouted slot-model GDS (geometry + rails + contacts, no
signal wiring) is the width/geometry evidence; `route_cell` on a slot
placement is attempted but not gated on.
