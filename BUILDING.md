# Building, Running and Testing AutoCellLibX

This repository is **self-contained**: ASTRAN (the transistor-level cell layout
synthesizer) and the LP-solver wrapper are vendored under `tools/`. Python code,
ASTRAN sources and the test suite are managed as a single project.

```
AutoCellLibX/
├── pySrc/                 # AutoCellLibX Python flow (pattern mining, growth, flow)
├── tests/                 # test suite (unit + integration)
├── tools/
│   ├── astran/            # vendored ASTRAN sources + build rules + tech files
│   │   ├── src/           #   C++ sources
│   │   ├── nbproject/     #   CodeBlocks makefiles
│   │   ├── build/Work/    #   technology rules (tech_freePDK45.rul) + samples
│   │   ├── build/bin/     #   output dir (Astran binary; not in git)
│   │   ├── bin/wx-config  #   shim pointing at MSYS2's wxWidgets 3.2
│   │   └── build_astran.sh#   build script -> build/bin/Astran
│   └── gurobi_cl/         # vendored gurobi_cl-compatible wrapper (python-mip + CBC)
├── benchmark/             # BLIF netlists + synthesis scripts
├── stdCelllib/            # FreePDK45 (GSCL45) library, LEF/LIB/SPICE
├── doc/                   # analysis + audit reports
└── requirements.txt
```

## 1. Python environment

```bash
pip install -r requirements.txt
```

## 2. Build ASTRAN

Prerequisites: **MSYS2** at `C:\msys64` with
`mingw-w64-x86_64-gcc` and `mingw-w64-x86_64-wxwidgets3.2-msw`.

```bash
bash tools/astran/build_astran.sh
# -> tools/astran/build/bin/Astran(.exe)
```

The script uses `tools/astran/bin/wx-config` (a shim that reports the MSYS2
wxWidgets 3.2 flags) so the build does not depend on which shell's `/mingw64`
is on `PATH`.

## 3. Run the flow

The Python flow resolves all tool paths relative to `pySrc/`, so it works from
any directory:

```bash
cd pySrc
python main.py
```

- `pySrc/Astran.py` defines the project-internal paths
  (`ASTRAN_BUILD_PATH`, `ASTRAN_TECHNOLOGY`, `GUROBI_CL`) from the repo root.
- `pySrc/main.py` selects the benchmark(s) to run (`benchmarks = ["adder"]` by
  default).
- The LP solver used by ASTRAN is `tools/gurobi_cl/gurobi_cl.cmd`
  (python-mip + COIN-OR CBC), injected via ASTRAN's `set lpsolve` command.

### GUI

There is also a PySide6 desktop front end for the same flow (configure, run
with live per-cell progress, then inspect patterns, GDS layouts and area
charts):

```bash
pip install PySide6
python -m gui          # or: python gui/app.py
```

See `gui/README.md`.  The GUI drives the same vendored ASTRAN through
`tools/gurobi_cl`, so the same caveats apply (one cell at a time; the 360 Total
Security false positive on `build/bin/Astran.exe`).

## 4. Test

```bash
cd <repo root>
python -m pytest                 # fast unit tests (slow ones deselected)
python -m pytest -m slow         # integration tests (need vendored ASTRAN)
python -m pytest -m "" tests     # everything
```

Test layout:

| Path | Scope | Needs ASTRAN |
|---|---|---|
| `tests/unit/test_graph_util.py` | data structures, sorting, pruning | no |
| `tests/unit/test_blif_parse.py` | liberty/BLIF parsing, graph construction | no |
| `tests/unit/test_encoding.py` | subgraph encode/tree alignment | no |
| `tests/unit/test_clustering.py` | initial clustering, dense pattern ids | no |
| `tests/unit/test_pattern_growth.py` | growth invariants, same-pattern skip | no |
| `tests/unit/test_spice.py` | SPICE subckt parse/rename/export | no |
| `tests/unit/test_area.py` | GDS area readers | no |
| `tests/integration/test_astran_binary.py` | ASTRAN binary exists + INVX1 smoke | **yes** |
| `tests/integration/test_pipeline.py` | mining+growth+SPICE export (no ASTRAN) | no |

## 5. Toolchain notes (Windows)

- Runtime wxWidgets DLLs are staged into `tools/astran/build/bin/` by the build
  script; `pySrc/Astran.py` additionally prepends `C:\msys64\mingw64\bin`.
- If 360 Total Security flags the freshly built `Astran.exe`
  (`HEUR/QVM...Malware.Gen`, caused by its `_popen` usage), add
  `tools/astran/build/bin` to its trust list — this is a known false positive.

## 6. Customer installer (`tools/package/`)

The customer deliverable is a single self-extracting installer built **without
network access**: no PyInstaller/Inno Setup required.

```bash
python tools/package/make_installer.py
# -> dist/AutoCellLibX-Setup.exe   (stub + appended ZIP of the stage)
```

The pipeline is:

1. `make_stage.py` assembles `dist/stage/` — a portable app folder: the flow
   (`pySrc`, `stdCelllib`, `benchmark/blif` without the two >90 MB giants),
   the vendored ASTRAN build and `tools/gurobi_cl`, plus a **pruned Python
   3.11 runtime** copied from the dev install (site-packages reduced to the
   packages the flow actually imports; PySide6 trimmed to QtCore/QtGui/
   QtWidgets). The keep-list is `SITE_KEEP` in the script — new Python deps
   must be added there or the stage import test fails.
2. `make_icon.py` renders the app icon; `launcher.c` is the portable
   `AutoCellLibX.exe` (finds its own dir, prepends `runtime\` on PATH, starts
   `pythonw -m gui`); both compile with MSYS2 MinGW (drive gcc/windres through
   `C:\msys64\usr\bin\bash.exe` — invoked straight from Git Bash gcc cannot
   spawn cc1.exe).
3. `installer_stub.c` is a self-extracting stub (static CRT + static zlib):
   it finds the ZIP appended to itself, extracts to `%TEMP%` behind a progress
   dialog, runs `setup.cmd` (copies to `%LOCALAPPDATA%\AutoCellLibX`, creates
   Desktop/Start-Menu shortcuts) and cleans up.  `setup.cmd` / `uninstall.cmd`
   / `make_shortcuts.ps1` / `README_DELIVERY.md` ship inside the stage.
4. `make_installer.py` zips the stage and appends it to the stub.

Verification before handing out a build (all must pass):

```bash
cd dist/stage
./runtime/python.exe -c "import sys; sys.path[:0] = ['.', 'pySrc']; \
    import matplotlib; matplotlib.use('Agg'); \
    import Astran, BLIFPreProc, BLIFPatternGrowth, spice, GDSIIAnalysis; \
    from gui import paths; \
    print([c.label for c in paths.probe_environment() if not c.ok and c.required])"
```

plus a `from mip import Model` LP solve (cbcbox pruning) and a real GUI launch
from the installed copy.  The launcher/console entry points are
`AutoCellLibX.exe` and `AutoCellLibX-Console.cmd` (console shows Python
stderr, for customer-side diagnosis).
