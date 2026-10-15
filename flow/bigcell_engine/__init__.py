"""Big-cell synthesis engine: heuristic placement + negotiated-congestion
routing for cells beyond the exact engine's envelope (stage 3).

Contract (mirrors flow/smt_engine/__init__.py):

- deterministic: sorted iteration everywhere, content-hashed per-cell RNG
  seeds, iteration budgets instead of wall-clock cutoffs (invariant 9);
- Qt-free core, unit-tested, tests run from the repo root with cwd=flow;
- the placement IR is smt_engine's own -- {Device: PlacedTransistor(row,
  start_col, legs, leg_width_cols)} + width in 0.19 um columns -- so the
  exact engine (route_model), the GDS writer (smt_engine/gds.py) and the
  structural self-check (smt_engine/verify.py) consume bigcell output
  unchanged;
- rows: 0 = P (upper row), 1 = N (lower row), height 2.47 um fixed
  (invariants 1/2/10).

Module map (doc/STAGE3_BIGCELL_ENGINE.md section 2):

- geometry.py      ordering -> column layout (shared math, implemented)
- netlist_ext.py   folding + row seeds + tree/branch blocks over
                   smt_engine.netlist's diffusion blocks
- place_euler.py   deterministic Euler-chain constructive placement
- place_sa.py      Threshold-Accept refinement, ASTRAN move set + cost,
                   incremental cost evaluation
- route_grid.py    negotiated-congestion router (GraphRouter port)
- engine.py        orchestration: exact rung -> grid rung -> fallback
- benchmark.py     width/checker benchmark vs the ASTRAN baseline
"""

from .geometry import (DEFAULT_LEG_WIDTHS_MIN_COLS, GRID_UM, HEIGHT_UM,
                       P_ROW, N_ROW, default_leg_widths, block_width_cols,
                       place_row, layout_cell)
