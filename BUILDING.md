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
