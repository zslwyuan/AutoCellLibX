# Third-Party Notices

AutoCellLibX (Apache License 2.0, see `LICENSE`) vendors, bundles or depends
on the following third-party components.  This file lists every component
that is **shipped inside the repository or the customer installer**, its
origin, and its license terms.  Python packages imported at run time are
listed as a group with pointers to their bundled license texts.

The project's own terms (from `LICENSE`): non-commercial use is covered by
the Apache License 2.0; **commercial use requires contacting the project
authors** (Wei ZHANG, eeweiz@ust.hk; Tingyuan LIANG, tliang@connect.ust.hk).
Third-party components keep their own license terms; where a component has
no explicit license text, the situation is stated exactly as it is instead
of being assumed.

---

## 1. ASTRAN (vendored source + shipped binary)

| | |
|---|---|
| What | Transistor-level standard-cell layout synthesizer (placement, routing, ILP compaction). Vendored under `tools/astran/`; the built binary `tools/astran/build/bin/Astran.exe` is shipped in the installer. |
| Origin | Universidade Federal do Rio Grande do Sul (UFRGS), Brazil. Upstream: `github.com/aziesemer/astran`. |
| Copyright (from source headers) | © 2005 Adriel Mota Ziesemer Jr., Cristiano Lazzari; © 2005/2013 Adriel Mota Ziesemer Jr., Renato Hentschke. Contact: `amziesemerj@inf.ufrgs.br`. |
| License | **No license text is present in the vendored tree** (no LICENSE/COPYING/GPL file). The upstream project is distributed for research/academic use. We therefore document the provenance and headers verbatim (see `tools/astran/LICENSE.md`) and do not claim any license on ASTRAN's behalf. |
| Modifications | `compaction.cpp` LP writer adapted for open-source solvers, plus solver-facing fixes — full repair record in `doc/AUDIT_REPORT.md`. |
| Runtime dependency | The binary dynamically links wxWidgets 3.2 runtime DLLs (LGPL-2.1+ with the wxWindows exception; DLLs shipped next to the exe, dynamically loaded). |
| Obligation for users | Redistribution carries the copyright headers (retained in the sources). **Commercial use should be confirmed with the ASTRAN authors**, mirroring the project's own commercial-authorization clause. |

## 2. LP-solver backbone (shipped wrapper + bundled solver)

| | |
|---|---|
| `tools/gurobi_cl/` | `gurobi_cl.py` is this project's own wrapper (Apache 2.0) that emulates Gurobi's CLI on top of python-mip. |
| python-mip | Eclipse Public License 2.0 (text bundled in the installer runtime at `runtime/Lib/site-packages/mip-2.0.0.dist-info/licenses/LICENSE`). |
| COIN-OR CBC (via `cbcbox`) | Eclipse Public License 1.0 (the COIN-OR Cbc solver binary `cbc.exe` and its DLLs are shipped under `runtime/.../cbcbox/`). |

## 3. Standard-cell / PDK data (`stdCelllib/`)

| Component | Origin | License |
|---|---|---|
| `gscl45nm.lib/.lef/.sp/.tlf` (GSCL45) | FreePDK45 / OSU GSCLib ecosystem (NC State / Oklahoma State University) | Apache License 2.0 |
| `sky130_fd_sc_hd__tt_025C_1v80.lib` | SkyWater Open PDK (SkyWater Technology) | Apache License 2.0 |
| `gpdk45nm.m` | Cadence GPDK45 model file | Cadence proprietary (academic redistribution; check with Cadence for commercial use) |

## 4. Benchmark netlists (`benchmark/`)

| Source | License |
|---|---|
| EPFL combinational benchmark suite (`benchmark/EPFL/`) | Research-use suite by EPFL; redistribution for research per its published terms |
| BOOM / Rocket / Gemmini modules (`boomModule/`, `rocketModule/`, `gemmini/`; `.blif` netlists synthesized with Yosys) | UC Berkeley projects, BSD-3-Clause family |

## 5. Python dependencies (bundled in the installer runtime)

The installer carries a trimmed Python 3.11 runtime whose `site-packages`
contains the packages below.  Each package's exact license text ships in its
`*.dist-info/licenses/` (or `*.dist-info/`) folder inside the runtime; the
table gives the short identifier.

| Package | License | | Package | License |
|---|---|---|---|---|
| PySide6 / shiboken6 | LGPL-3.0 / GPL-3.0 / Qt commercial | | networkx | BSD-3-Clause |
| numpy | BSD-3-Clause | | scipy | BSD-3-Clause |
| scikit-learn | BSD-3-Clause | | joblib | BSD-3-Clause |
| threadpoolctl | BSD-3-Clause | | matplotlib | PSF-based |
| contourpy / cycler / kiwisolver | BSD-3-Clause | | pillow | HPND (MIT-like) |
| fonttools / pyparsing | MIT | | python-dateutil | Apache-2.0 / BSD dual |
| packaging | Apache-2.0 / BSD dual | | six | MIT |
| gdstk | Boost Software License 1.0 | | blifparser | MIT |
| **liberty-parser** | **GPL-3.0-or-later** (see note) | | lark | MIT |
| easydict | MIT | | sympy / mpmath | BSD-3-Clause |
| mip | EPL-2.0 | | cbcbox | EPL-1.0 (CBC) |
| cffi | MIT | | pycparser | BSD-3-Clause |
| narwhals / tqdm | MIT / MPL-2.0 | | colorama | BSD-3-Clause |
| typing_extensions | PSF | | pip / setuptools | MIT / PSF |

> **Note on liberty-parser (GPL-3.0-or-later):** this is the only strong
> copyleft dependency.  It is imported by the flow's liberty parser
> (`BLIFPreProc.py`) as an ordinary Python import; GPL obligations apply to
> its distribution inside the runtime.  Its source is available from the
> PyPI project `liberty-parser`; the installer ships the package as
> installed, including its license metadata.  If GPL is unacceptable for a
> deployment, the flow can be switched to a permissively licensed liberty
> parser without touching the algorithm.

## 6. Documentation and figures (`doc/`, `gui/`)

Repository documentation is part of the AutoCellLibX project (Apache 2.0).
Figure assets that reproduce third-party diagrams keep their original
attribution where known; if any figure lacks attribution, please open an
issue so it can be corrected.

---

*This notice is maintained in `THIRD_PARTY_NOTICES.md` at the repository
root; the customer installer ships a copy at its install root.  If a
component's license is mis-stated here, it is an error on our part — please
report it.*
