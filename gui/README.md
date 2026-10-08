# AutoCellLibX GUI · 标准单元扩展工作台

A PySide6 desktop front end for the AutoCellLibX flow.  It wraps the same
pipeline as `pySrc/main.py` in a stage-aware, observable, cancellable run and
adds the visualisations the command line never had: an interactive GDS layout
viewer, pattern/design graphs, and area-savings charts.

> 第一次接触本项目？先读 [`doc/IMPLEMENTATION_GUIDE.md`](../doc/IMPLEMENTATION_GUIDE.md)
> （自底向上实现指南），再回来看本页的界面操作；算法与接口的深度分析在
> [`doc/ALGORITHM_DESIGN.md`](../doc/ALGORITHM_DESIGN.md)。

## Run it

```bash
# from the repository root
python -m gui
# or
python gui/app.py
```

No extra dependencies beyond the flow's `requirements.txt` plus **PySide6**
(`pip install PySide6`).

## The seven pages

| Page | What you do there |
|---|---|
| **总览 Overview** | Read the quick-start, see the pipeline stages, check the environment (ASTRAN binary, solver, library). Key numbers up top. |
| **配置 Configure** | Pick built-in benchmarks (with size + "large design" warnings); **「📄 添加 BLIF 文件…」 imports any external netlist** as an extra input (a custom name shadows a same-named built-in, outputs land in `outputs/<name>/`). **Input files (PDK)** lets you point the flow at a custom Liberty `.lib`, SPICE `.sp`, ASTRAN technology `.rul`, LEF (nominal widths for area) and a layer map for the GDS viewer — empty rows mean the repository defaults. **Layout constraints** makes the ASTRAN geometry editable (row height, h/v grid, supply rail, nwell position, template); defaults read from `pySrc/Astran.py`, and a custom geometry/technology regenerates the whole ASTRAN baseline so the area comparison stays matched-height. |
| **运行 Run** | Start/stop. Watch the stage list tick over, the **live ASTRAN cell panel** (folding → placing → routing → compacting, LP size, solver status, width), and the levelled coloured log. |
| **模式 Patterns** | A table of every COMPLEX cell: pattern code, occurrences, size, coverage, layout width, savings. Click one to see its subgraph figure and transistor-level `.sp`. |
| **版图 Layouts** | **Interactive GDS viewer**: pan/zoom, layer toggles + presets (metals / active / M1), ruler + scale bar, two-click measurement, cursor read-out in µm, per-cell info (LP size, solver, repair passes), export PNG, regenerate one cell. |
| **结果 Results** | The area story: design-level savings tiles, "side-by-side vs merged width" grouped bars, per-pattern savings bars, design breakdown, and the raw `bestRecord-*` files. |
| **设计 Design** | Parse a benchmark's netlist on demand: node/edge/type counts, cell-type histogram, and an interactive neighbourhood explorer around any cell type. |
| **PDK 编辑 PDK Editor** | View / edit / save the ASTRAN technology rules (`.rul`) and the Cadence layer map (`.map`), with a Chinese+English explanation for every field. Rule names are decoded from ASTRAN's S/E/W/R/A notation; edits are validated (values numeric, streams integer) and the raw-text preview re-renders live; `另存为…` points the run configuration at the new file. |

## Design notes (for maintainers)

- **Qt-free core.** Everything except the widgets is plain Python and unit
  tested: `paths`, `artifacts` (record/log/SPICE readers), `gds_model`
  (GDS → microns), `flow_core` (the pipeline). See
  `tests/unit/test_gui_artifacts.py`.
- **The pipeline is a faithful port of `main.py`** with progress callbacks and
  cooperative cancellation; it keeps the trace-keyed de-duplication, the
  "exclude a 0×0 layout" guards, and the incremental `bestRecord-*` writes, so
  a GUI run and a CLI run produce the same cells.  ASTRAN is launched one cell
  at a time (the shared `ILPmodel.lp` in the working directory forbids
  concurrency).
- **Width is the area proxy** and the log's `Cell Size (W x H)` stays the
  authoritative dimension (AGENTS.md invariant 1).  ASTRAN writes a **bogus
  GDS UNITS record**, so the viewer calibrates its µm scale against the log
  height (empirically 16.5 GDS units/µm) — see `gds_model.py`.
- **matplotlib is pinned to Agg** before the flow's pyplot ever imports, so the
  pattern figures the flow draws in the worker thread never touch the GUI's Qt
  backend.

## ASTRAN and 360 Total Security

`tools/astran/build/bin/Astran.exe` is a **false positive** for 360 Total
Security (`HEUR/QVM…Malware.Gen`) and gets **quarantined the first time it is
executed**.  Symptoms in the GUI: a layout run fails with "无法启动 ASTRAN 二进制"
and the environment check that was green a moment ago turns red.

Fix (from AGENTS.md): add `tools/astran/build/bin/` (or the exe) to 360's
trust list, then rebuild with `bash tools/astran/build_astran.sh`.  The GUI's
error message says the same thing.
