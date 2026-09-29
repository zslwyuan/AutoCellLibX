# ASTRAN — provenance and license status

This file documents, exactly and without assumption, the licensing situation
of the ASTRAN sources vendored in this directory.  It exists because the
vendored tree itself contains **no license text**, and AutoCellLibX ships and
redistributes ASTRAN (sources and the built binary), so its terms must be
stated somewhere.

## What ASTRAN is

ASTRAN is a transistor-level standard-cell layout synthesizer: it takes a
SPICE subcircuit netlist, performs transistor placement (simulated
annealing), routing and ILP-based compaction, and writes GDSII layout.  In
AutoCellLibX it generates both the reference ("baseline") layouts of the
GSCL45 standard cells and the layouts of the mined complex cells.

## Provenance

| | |
|---|---|
| Upstream repository | `github.com/aziesemer/astran` |
| Developers | Adriel Mota Ziesemer Jr., Cristiano Lazzari, Renato Hentschke — Universidade Federal do Rio Grande do Sul (UFRGS), Brazil |
| Contact | `amziesemerj@inf.ufrgs.br` |
| Copyright headers (verbatim from the sources) | `Copyright (C) 2005 by Adriel Mota Ziesemer Jr.` ; `Copyright (C) 2005 by Adriel Mota Ziesemer Jr., Cristiano Lazzari` ; `Copyright (C) 2005/2013 by Adriel Mota Ziesemer Jr., Renato Hentschke` |
| License text in the vendored tree | **None.**  There is no LICENSE, COPYING or GPL file, and no license statement in any source header. |

## What this means for users and redistributors

- The absence of a license text means the default copyright law applies:
  ASTRAN is **not** public domain, and rights are held by the copyright
  holders named in the headers.
- The upstream project has historically been distributed for research and
  academic use.  AutoCellLibX redistributes it (sources under
  `tools/astran/src/`, built binary under `tools/astran/build/bin/`) as part
  of the AutoCellLibX project, which is licensed under the Apache License
  2.0 (see the root `LICENSE`).
- **For commercial use of ASTRAN, contact its authors first.**  This is the
  same precaution AutoCellLibX takes for its own commercial clause: we do
  not grant — and cannot grant — rights on ASTRAN beyond what its copyright
  holders grant.
- The copyright headers are retained in the vendored sources (Apache 2.0
  §4(c) attribution is satisfied for the parts we ship).

## Modifications

ASTRAN is vendored with modifications, all documented in
`doc/AUDIT_REPORT.md`:

- `compaction.cpp` — LP model writer fixes and debug hooks for open-source
  solvers (expression-variable constraints, option-3 disjunct recovery is
  implemented in the *solver wrapper* instead, `End` keyword, failed-model
  dump via `ASTRAN_DUMP_FAILED_LP`).
- The build (`build_astran.sh`) stages the wxWidgets 3.2 runtime DLLs next
  to the binary; wxWidgets is LGPL-2.1+ with the wxWindows exception and is
  **dynamically linked**.

The modified sources are what this repository ships; they build with the
toolchain described in `BUILDING.md`.
