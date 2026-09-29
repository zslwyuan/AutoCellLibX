"""AutoCellLibX desktop GUI (PySide6).

A stage-aware front end for the AutoCellLibX flow: configure a run, watch it
execute with live progress, then inspect the patterns, GDS layouts and area
results it produced.

The package is deliberately split so that everything except the widgets is
Qt-free and therefore unit-testable:

    paths       - where things live on disk, environment probe
    theme       - palette + GDS layer colours
    artifacts   - parsing of bestRecord-* / .Astranlog / .sp (pure Python)
    gds_model   - GDSII -> display geometry (gdstk, no Qt)
    flow_core   - the pipeline orchestration with callback hooks (no Qt)
    flow_worker - thin QThread/QSIGNAL bridge around flow_core
    widgets/    - reusable canvases (graph, layout, log)
    tabs/       - one module per top-level page
"""

__version__ = "1.0.0"
