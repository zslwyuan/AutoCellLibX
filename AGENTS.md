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

## Canonical documents

| Document | Contents |
|---|---|
| `BUILDING.md` | environment, ASTRAN build, run and test commands |
| `doc/PROJECT_ANALYSIS.md` | directory/module/flow analysis |
| `doc/AUDIT_REPORT.md` | algorithm + config audit and the repair record |
| `doc/LESSONS_LEARNED.md` | why these defects were hard to see, and the debugging moves that found them |
| `PROGRESS_Windows_Setup.md` | Windows/MSYS2 bring-up notes |

Record non-trivial findings and every behavioural fix in
`doc/AUDIT_REPORT.md`. That file is the project's engineering log; a fix that
is only in the code is effectively undocumented.

## Invariants — do not break these

1. **Area is measured as nominal cell *width*, never GDS bounding-box area.**
   `Astran.loadAstranArea`, `GDSIIAnalysis.loadOrignalGSCL45nmGDS` and
   `GDSIIAnalysis.loadAstranGDS` all return width. Row height is fixed per
   library, so area ∝ width; the three sources used to be measured
   inconsistently (ASTRAN baseline at H=3.2µm, generated cells at H=2.6µm),
   which alone inflated the reported savings. If you add a new area source,
   return width.

2. **Cell geometry is set explicitly in the ASTRAN run script**, not left to
   ASTRAN's compiled-in defaults. `Astran.runAstranForNetlist` emits
   `set rowheight 13` / `set grid 0.20 0.20` / `set supplysize 0.72` /
   `set nwellpos 1.14` / `set celltemplate "Tapless"`, i.e. H = 13 × 0.20 =
   2.6 µm. Change the target row height here (and re-validate DRC), not by
   editing ASTRAN.

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
- **CBC solves fast but proves slowly.** On ASTRAN's big-M models (M = 20000 µm)
  CBC finds a good feasible solution quickly yet cannot close the 2 % gap, so
  the adapter accepts the first-phase solution after
  `GUROBI_CL_TIME_LIMIT` seconds (default 300) and only spends more time when
  nothing was found at all. Do not raise the limit expecting tighter layouts;
  for provable optimality use real Gurobi.
- **`.subckt` port order changes the layout**, not just its formatting —
  reordering the pins moves ASTRAN's placement (COMPLEX0: 2.4 µm in insertion
  order versus 2.0 µm in the old hash order). Keep it deterministic, and treat
  a change of ordering as a change of result.
- **A pipeline run does not delete obsolete outputs.** Rerunning with a
  different pattern set leaves orphan `COMPLEX*` files behind, so clear the
  benchmark output directory before a regeneration you intend to commit.
- **Do not call `Model.read()` on the generated LP** (see invariant 3).
- **`build/bin/Astran.exe` looks like malware to 360 Total Security**
  (`HEUR/QVM…Malware.Gen`, from its `_popen` use). It is a false positive; add
  the directory to the trust list. It is not committed.
- **`wx-config` from MSYS2 mis-resolves under Git Bash.** The build uses
  `tools/astran/bin/wx-config`, a shim that reports the MSYS2 wxWidgets 3.2
  flags directly.
- **Also reported in a prior audit** and still open: generated row height
  (2.6 µm) does not exactly match the GSCL45 site height (2.47 µm), and
  ASTRAN's stream layer numbers differ from the GSCL45 library's — remap before
  mixing layouts in one GDS. See `doc/AUDIT_REPORT.md` §5.5.

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
- Keep tool paths centralised in `pySrc/Astran.py`; do not hard-code absolute
  paths in new code.
- Commit messages: state the defect and the evidence, not just the edit. If a
  change alters generated cells, say how the width moved.
- The `outputs/<benchmark>/COMPLEX*` result set **is tracked**: commit it as
  one coherent snapshot rather than a few files at a time, since the files
  only make sense together. Build artifacts, `ILPmodel.*`, `__pycache__/` and
  `.pytest_cache/` are ignored.
