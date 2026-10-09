# AGENTS.md

Orientation for anyone (human or AI agent) changing this repository. Read this
before editing. It records the invariants and the non-obvious pitfalls that
have already cost time once.

## What this project is

AutoCellLibX extends a standard-cell library by mining **frequently occurring
sub-circuits** from a design's netlist, merging each such pattern into a new
"complex" cell, and laying that cell out transistor-level. It is built around
three pieces:

- `pySrc/` — the Python flow: BLIF/liberty parsing, subgraph encoding,
  clustering, pattern growth, SPICE export, area evaluation.
- `tools/astran/` — **ASTRAN**, the transistor-level standard-cell layout
  synthesizer (vendored C++ source, UFRGS). Also vendored, not a submodule.
- `tools/gurobi_cl/` — the LP-solver shim ASTRAN calls for ILP compaction,
  implemented on python-mip + COIN-OR CBC (an open replacement for `gurobi_cl`).

Everything is one repository, one test suite, one commit history. There is no
separate ASTRAN checkout to keep in sync.

## Desktop GUI (`gui/`)

A PySide6 front end (`python -m gui` or `python gui/app.py`) that wraps the
same pipeline in a stage-aware, cancellable run and adds the visualisations
the CLI never had (interactive GDS viewer, pattern/design graphs, area
charts).  When changing the flow, keep these GUI-side invariants:

- **The core is Qt-free and unit-tested.** `gui/paths.py`, `gui/artifacts.py`
  (record/log/SPICE readers), `gui/gds_model.py`, `gui/flow_core.py` are plain
  Python; only `gui/widgets/` and `gui/tabs/` touch Qt.  The parsing/calibration
  behaviour is pinned by `tests/unit/test_gui_artifacts.py`.
- **`flow_core.py` is a faithful port of `main.py`'s control flow** with
  progress callbacks and cancellation.  It must keep the same guards (trace-keyed
  de-dup, 0×0-layout exclusion, incremental `bestRecord-*` writes) and run one
  ASTRAN cell at a time.  A GUI run and a CLI run must produce the same cells.
- **The GDS viewer calibrates against the log, never the file's UNITS record.**
  ASTRAN writes a bogus UNITS record; empirically every generated cell is 16.5
  GDS units/µm, so the viewer scales by (outline-height / log-height).  See
  `gui/gds_model.py`.
- **matplotlib is pinned to Agg** in `gui/app.py` before the flow's pyplot
  imports, so the worker-thread pattern figures never touch the Qt backend.
- **ASTRAN launch failures are surfaced as actionable guidance** (the 360
  Total Security false positive), not raw tracebacks — see
  `flow_core._popen_astran`.  If the binary is quarantined, the layout run
  fails with that message; whitelist `tools/astran/build/bin/` and rebuild.

See `gui/README.md` for the page-by-page tour.

## Canonical documents

| Document | Contents |
|---|---|
| `BUILDING.md` | environment, ASTRAN build, run and test commands |
| `doc/IMPLEMENTATION_GUIDE.md` | bottom-up implementation guide for first-time readers (data formats → … → GUI) |
| `doc/PROJECT_ANALYSIS.md` | directory/module/flow analysis |
| `doc/AUDIT_REPORT.md` | algorithm + config audit and the repair record |
| `doc/LESSONS_LEARNED.md` | why these defects were hard to see, and the debugging moves that found them |
| `PROGRESS_Windows_Setup.md` | Windows/MSYS2 bring-up notes |

Record non-trivial findings and every behavioural fix in
`doc/AUDIT_REPORT.md`. That file is the project's engineering log; a fix that
is only in the code is effectively undocumented.

## Invariants — do not break these

1. **Area is measured as nominal cell *width*, never GDS bounding-box area.**
   `Astran.loadAstranArea`, `gds_analysis.loadOrignalGSCL45nmGDS` and
   `gds_analysis.loadAstranGDS` all return width. Row height is fixed per
   library, so area ∝ width; the three sources used to be measured
   inconsistently (ASTRAN baseline at H=3.2µm, generated cells at H=2.6µm),
   which alone inflated the reported savings. If you add a new area source,
   return width.

2. **Cell geometry is set explicitly in the ASTRAN run script**, not left to
   ASTRAN's compiled-in defaults. `Astran.runAstranForNetlist` emits
   `set rowheight 13` / `set grid 0.19 0.19` / `set supplysize 0.26` /
   `set nwellpos 1.235` / `set celltemplate "Tapless"`, i.e. H = 13 × 0.19 =
   2.47 µm — exactly the GSCL45 CoreSite height, with widths on the library's
   0.19 µm (M1-pitch) granularity and 0.13 µm supply rails like the library's
   abutment rails (drawn inside the cell). `nwellpos` = H/2, so nwell and
   pwell come out equal height, matching the handcrafted library. Change the
   target row height here (and re-validate DRC), not by editing ASTRAN.

3. **ASTRAN puts *expressions* where LP readers expect variable names** (e.g.
   a column named `b0_17_1 + b0_17_2 + b0_17_3`). `compaction.cpp` renames
   those to plain names **and emits explicit definition constraints**
   (`astranExprN - b0_17_1 - b0_17_2 = 0`) so the model is equivalent. Do not
   "simplify" this by collapsing the expressions into free variables — that
   silently drops every constraint. CoinLpIO also rejects such column names and
   falls back to `x0, x1, …`, disconnecting the whole model, which is why the
   adapter parses the LP itself instead of calling `Model.read()`.

4. **The solver adapter must treat FEASIBLE as success.** With a relative gap
   tolerance CBC returns `FEASIBLE`, not `OPTIMAL`; requiring `OPTIMAL` makes
   it write an empty `.sol`, and ASTRAN then reads all zeros and produces a
   0 × 0 cell.

5. **A pattern's identity is its `patternExtensionTrace` string.**
   `dumpedPaterns` in `main.py` is keyed by the trace. Any "have I seen this
   pattern" test must compare traces — comparing a `clusterTypeId` (int)
   against those keys is always true and disables de-duplication entirely.
   Since 2026-10 the base `[...]` segment is **canonical** (children sorted
   after the root, `canonical_pattern_code`): the same pattern can appear under
   a legacy, order-sensitive name in older `outputs/` snapshots — treat the
   two spellings as the same pattern when comparing across regenerations.

6. **`COMPLEX<n>` ids are assigned per run and are not stable.** The same id
   can name a different pattern in a different run. Never hand-edit
   `outputs/*/COMPLEX*.sp|gds`, and never assume an id↔pattern mapping
   recorded in `bestRecord-*` matches files on disk. Regenerate instead.

7. **A cached layout is only valid for the netlist it was built from.**
   `main.py` regenerates when the `.gds` is missing or older than its `.sp`,
   and `exportSpiceNetlist` writes only when the content changes so the mtime
   is a usable signal. Keep both halves of that contract.

8. **ASTRAN is deterministic** (no `srand()` anywhere). Two runs of the same
   binary on the same netlist give the same layout, so any width change is
   caused by a code/netlist change — not by run-to-run noise. Use that when
   bisecting a surprising area change.

9. **The Python flow must be deterministic too.** Never let set/dict iteration
   order reach an output. `exportSpiceNetlist` builds the port list from an
   insertion-ordered mapping for exactly this reason: with a plain `set` the
   exported netlist changed on every process (`PYTHONHASHSEED`), which defeated
   the layout cache and made results irreproducible.
   `tests/unit/test_determinism.py` enforces it.

10. **An area comparison requires a matched row height.** Width is an area proxy
    only at a fixed height, so the ASTRAN baseline (`pySrc/originalAstranStdCells`)
    and the generated complexes must both go through `runAstranForNetlist` with
    the same geometry constants. Comparing 3.2 µm baselines against 2.6 µm
    complexes once flipped a candidate from +6.5 % to −19.5 %.

## Pitfalls that have already bitten

- **Don't run two ASTRAN cells concurrently.** The LP is written as
  `ILPmodel.lp` / `ILPmodel.sol` in the process working directory; parallel
  runs clobber each other.
- **ASTRAN's `autoFlow` is the slow part**: placement (simulated annealing)
  plus one or more compaction solves, ~5–10 min per cell. The adapter caps a
  solve at 300 s and uses a 2 % relative gap; this only trades shrink quality
  for time, since compaction acts on an already-legal layout.
- **Non-finite coefficients.** ASTRAN emits pairs of expression-definition
  constraints, one with coefficient `0.000000` and its twin with `inf`. The
  adapter **drops** the term (`inf` means "no bound"). Never clamp it to a
  big-M: `astranExpr = y + 1e9·x` is a different constraint, and CBC then
  reports `NO_SOLUTION_FOUND`.
- **A failed solve is silent.** On `NO_SOLUTION_FOUND` the adapter writes an
  all-zero solution and ASTRAN emits a **0 × 0 cell**; `main.py` detects that
  and excludes the pattern from the reported savings (never count zero width).
  Grep the logs for "no usable LP solution" when a cell is missing or 0 × 0.
  Set `ASTRAN_DUMP_FAILED_LP=1` to keep the model that failed as
  `ILPmodel.fail.lp` (the LP is otherwise overwritten by the next solve).
- **An infeasible compaction model on a tight row is real, and the third
  disjunct is the usual culprit.** The "intelligent" spacing rule gives the
  solver three ways to separate a pair (right of / above / diagonally up-right,
  selected by a `b<A>_<B>_<option>_<uid>` binary). Once `createNode` pins the
  end-line variables `a2`/`b2` to the real edges (§5.11), option 3 couples both
  coordinates and can be unsatisfiable for a relative placement the placer
  already fixed — CBC then *proves* `INFEASIBLE` even though a legal layout
  exists. `autoFlow`'s `conservative` retry shrinks the diffusion (making it
  worse) and never widens the cell, so it cannot recover; neither does adding
  internal tracks. The adapter recovers by rebuilding the model with the option
  3 disjuncts dropped and re-solving; ASTRAN's repair pass then enforces the
  real spacing on the solved coordinates. This fires only on a *proved*
  `INFEASIBLE`, never on a timeout — a model that is merely too hard for the
  budget must keep its exact constraints so the normal escalation still
  reproduces the same cell. The recovery is a safety net, not the norm: with the
  current H = 2.47 µm equal-well geometry (`nwellpos 1.235`) all four adder
  complexes solve feasible on the first attempt — the retry was needed under the
  old 1.0825 geometry (see `doc/AUDIT_REPORT.md`). Grep the logs for
  "retrying without the option-3 spacing disjuncts" to check whether it fired.
- **Every disjunctive keep-away constraint needs its own big-M term.** The
  repair pass in `compact()` inserts four binaries per violating pair; each of
  the four constraints must carry `+ RELAXATION` with coefficient
  `rule + relaxation`, exactly as `insertDistanceRuleInteligent` writes them.
  Without it the "off" branch `t_i = 0` still forces e.g. `x_B_a >= x_A_b`, so
  options 1 and 2 contradict each other and the re-solve is *always*
  infeasible: the loop spins to its 8-pass budget, leaves the variables
  untouched, and the cell is exported with the original violations. The log
  prints "Spacing repair pass N: M violating pair(s)" — the final M must be 0,
  which `tests/unit/test_gds_quality.py` now enforces.
- **CBC solves fast but proves slowly.** On ASTRAN's big-M models (M = 20000 µm)
  CBC finds a good feasible solution quickly yet cannot close the 2 % gap, so
  the adapter accepts the first-phase solution after
  `GUROBI_CL_TIME_LIMIT` seconds (default 300) and only spends more time when
  nothing was found at all. Do not raise the limit expecting tighter layouts;
  for provable optimality use real Gurobi.
- **`.subckt` port order changes the layout**, not just its formatting —
  reordering the pins moves ASTRAN's placement, and the effect is
  cell-dependent: a "canonical" order (VCC GND first, signals sorted) improved
  COMPLEX0 (2.4 → 2.0 µm) but made COMPLEX9 (3.6 → 4.2) and COMPLEX10
  (3.8 → 8.4) worse, so the insertion order is kept. Treat any change of
  ordering as a change of result.
- **A pipeline run does not delete obsolete outputs.** Rerunning with a
  different pattern set leaves orphan `COMPLEX*` files behind, so clear the
  benchmark output directory before a regeneration you intend to commit.
- **The growth-export must use the grown pattern's own `clusterTypeId`.**
  Exporting with `len(clusterSeqs)` as the id collides with ids already dumped
  and silently overwrote `COMPLEX9.sp` while its `.gds` kept the old layout —
  the dataset tests catch exactly this class of mismatch.
- **Unequal P/N counts are an ASTRAN landmine.** When a cell has different
  PMOS/NMOS counts, `transPlacement` pads the shorter ordering with `link=-1`
  GAP entries; any code reading `getTrans(ordering[i].link)` must skip them
  (`route()` had four such unguarded reads → `trans[-1]`), and single-element
  series in `seriesFolding` must fold between the real nets. NOR3X1 (P6/N3)
  crashed on both until fixed.
- **MSYS2's own python shadows the solver wrapper.** Installing any mingw
  package that pulls `mingw-w64-x86_64-python` puts a python.exe (no python-mip)
  into `C:\msys64\mingw64\bin`, and `gurobi_cl.cmd` calls bare `python`.
  `astran.py` now puts the flow interpreter first on PATH; keep that ordering
  if you touch it.
- **Do not call `Model.read()` on the generated LP** (see invariant 3).
- **`build/bin/Astran.exe` looks like malware to 360 Total Security**
  (`HEUR/QVM…Malware.Gen`, from its `_popen` use). It is a false positive;
  `build_astran.sh` strips the binary after linking, which *reduces* the
  heuristic hits but does not prevent a quarantine when 360 updates its
  definitions (observed twice). The durable fix is adding the directory to
  360's trust list (done manually on the development machine); `Astran.keep`
  and `AstranBackup.zip` next to the binary are restore backups for a
  mid-run quarantine.
- **`wx-config` from MSYS2 mis-resolves under Git Bash.** The build uses
  `tools/astran/bin/wx-config`, a shim that reports the MSYS2 wxWidgets 3.2
  flags directly.
- **Layer/stream numbers now follow the GSCL45 stream map** (metal1=49,
  via=50, …) — see `stdCelllib/gds2_encounter.map` and the calibrated layer
  map in `tools/astran/build/Work/tech_freePDK45.rul`. Generated GDS can be
  merged with the library without remapping; base layers (active 1, poly 9,
  contact 10, wells) keep the Cadence-style numbering used across the repo.

## Workflows

```bash
# unit tests (fast; slow integration tests are deselected by default)
python -m pytest

# integration tests (need the vendored ASTRAN build)
python -m pytest -m slow

# rebuild ASTRAN
bash tools/astran/build_astran.sh

# run the whole flow
cd pySrc && python main.py

# run the desktop GUI (PySide6)
python -m gui

# regenerate one cell's layout without re-running mining
cd pySrc && python regenerate_cells.py --dir outputs/adder COMPLEX1
```

## Conventions

- **Tests run with cwd = `pySrc`.** The flow modules use paths like
  `../stdCelllib/...`, so tests that exercise them must use the `in_pysrc`
  fixture. Put fast tests in `tests/unit/`, anything needing ASTRAN or long
  runtimes in `tests/integration/` under `@pytest.mark.slow`.
- Prefer a regression test over no test when a fix is cheap to pin down; the
  cache and netlist-export contracts above exist because tests caught them.
- Keep tool paths centralised in `pySrc/astran.py`; do not hard-code absolute
  paths in new code.
- Commit messages: state the defect and the evidence, not just the edit. If a
  change alters generated cells, say how the width moved.
- The `outputs/<benchmark>/COMPLEX*` result set **is tracked**: commit it as
  one coherent snapshot rather than a few files at a time, since the files
  only make sense together. Build artifacts, `ILPmodel.*`, `__pycache__/` and
  `.pytest_cache/` are ignored.
