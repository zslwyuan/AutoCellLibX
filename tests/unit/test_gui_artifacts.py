"""Unit tests for the GUI's Qt-free helper modules.

The readers are tested against the real ``outputs/adder`` artifacts, but never
against frozen numbers: the flow itself regenerates those files (a rerun with
a different toolchain or geometry rewrites every COMPLEX cell), so the tests
pin the *mechanism* (a calibrated width equals the log's width, the viewer's
µm scale is consistent) rather than the dataset.
The widgets themselves are not tested (they need a display); everything they
depend on is.
"""
import os

import pytest

from gui import artifacts, gds_model, paths

ADDER_DIR = os.path.join(paths.OUTPUTS_DIR, "adder")


# ------------------------------------------------------------ cell ordering
def test_cell_sort_key_numeric():
    names = ["COMPLEX10", "COMPLEX9", "COMPLEX0", "COMPLEX1", "foo"]
    assert sorted(names, key=artifacts.cell_sort_key) == \
        ["COMPLEX0", "COMPLEX1", "COMPLEX9", "COMPLEX10", "foo"]


# -------------------------------------------------------------- ASTRAN log
def test_parse_astran_log_complete():
    log = artifacts.parse_astran_log(os.path.join(ADDER_DIR, "COMPLEX0.Astranlog"))
    assert log.exists and log.complete
    assert log.width_um and log.width_um > 0
    assert log.height_um and log.height_um > 0
    assert log.status == "ok"


def test_parse_astran_log_details():
    log = artifacts.parse_astran_log(os.path.join(ADDER_DIR, "COMPLEX9.Astranlog"))
    assert log.complete and log.width_um > 0
    assert log.n_transistors and log.n_transistors > 0
    assert log.solver_vars and log.solver_vars > 1000
    assert log.solver_status and log.solver_status != ""
    assert log.spacing_repairs and log.spacing_repairs[-1] == 0


def test_parse_astran_log_missing():
    log = artifacts.parse_astran_log(os.path.join(ADDER_DIR, "NOPE.Astranlog"))
    assert not log.exists and log.status == "missing"


def test_parse_astran_log_tail():
    full = artifacts.parse_astran_log(os.path.join(ADDER_DIR, "COMPLEX9.Astranlog"))
    tail = artifacts.parse_astran_log(os.path.join(ADDER_DIR, "COMPLEX9.Astranlog"),
                                      tail_bytes=4000)
    assert tail.width_um == full.width_um        # the size line survives a tail read


# ----------------------------------------------------------------- records
def test_read_best_record():
    rec = artifacts.read_best_record(os.path.join(ADDER_DIR, "bestRecord-adder"))
    assert rec.exists
    # The numbers move with every regeneration; the *shape* must not.
    assert rec.save_area_astran is not None and rec.save_area_astran >= 0
    assert rec.save_ratio_astran is not None
    assert rec.save_area_gscl is not None and rec.save_ratio_gscl is not None
    if rec.selected:
        assert rec.selected[0][0].startswith("COMPLEX")
        assert len(rec.selected[0]) == 4


def test_read_separate_record():
    rows = artifacts.read_separate_record(
        os.path.join(ADDER_DIR, "bestRecord-seperateadder"))
    assert isinstance(rows, list)
    for row in rows:
        assert row.name.startswith("COMPLEX")
        assert isinstance(row.save_area, float)
        assert len(row.as_row()) == 7


# ------------------------------------------------------------ spice netlist
def test_read_spice_netlist():
    sp = artifacts.read_spice_netlist(os.path.join(ADDER_DIR, "COMPLEX1.sp"))
    assert sp.exists and sp.name == "COMPLEX1"
    assert len(sp.ports) > 0
    assert sp.n_transistors > 0
    assert sp.pattern_code
    assert sp.occurrences is not None and sp.occurrences > 0
    assert sp.n_transistors == sp.n_pmos + sp.n_nmos


# ------------------------------------------------------------ trace helpers
@pytest.mark.parametrize("trace,expected", [
    ("[NAND2X1,NAND2X1,OR2X1]", ["NAND2X1", "NAND2X1", "OR2X1"]),
    ("[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0",
     ["NAND2X1", "NAND2X1", "OR2X1", "XNOR2X1"]),
    ("[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0+OAI21X1_c2o0+AND2X1_c4i0",
     ["NAND2X1", "NAND2X1", "OR2X1", "XNOR2X1", "OAI21X1", "AND2X1"]),
    ("", []),
])
def test_trace_to_types(trace, expected):
    assert artifacts.trace_to_types(trace) == expected


def test_load_baseline_widths_and_original_width():
    widths = artifacts.load_baseline_widths(paths.ORIGINAL_CELLS_DIR)
    assert widths, "expected committed ASTRAN baseline cells"
    assert "NAND2X1" in widths and "OR2X1" in widths
    orig = artifacts.pattern_original_width("[NAND2X1,NAND2X1,OR2X1]", widths)
    assert orig == pytest.approx(2 * widths["NAND2X1"] + widths["OR2X1"])


# ------------------------------------------------------------- scan outputs
def test_scan_output_dir():
    cells = artifacts.scan_output_dir(ADDER_DIR)
    assert cells
    names = [c.name for c in cells]
    # numeric COMPLEX ordering, whatever cells exist today
    assert names == sorted(names, key=artifacts.cell_sort_key)
    for c in cells:
        assert c.has_sp and c.has_gds and c.has_log


# ------------------------------------------------------------ gds calibration
def test_gds_calibration_matches_log():
    """The viewer's µm scale must make the layout agree with the flow's area
    metric (the log's Cell Size), whatever the current toolchain produced."""
    for name in ("COMPLEX0", "COMPLEX1", "COMPLEX9", "COMPLEX10"):
        log_path = os.path.join(ADDER_DIR, name + ".Astranlog")
        log = artifacts.parse_astran_log(log_path)
        if not log.complete:
            continue
        model = gds_model.load_layout(os.path.join(ADDER_DIR, name + ".gds"),
                                      log_path)
        assert model.calibrated
        assert model.width_um == pytest.approx(log.width_um, abs=1e-6)
        assert model.height_um == pytest.approx(log.height_um, abs=1e-6)
        assert model.units_per_um == pytest.approx(16.5, rel=0.1)


def test_gds_layer_stats():
    model = gds_model.load_layout(os.path.join(ADDER_DIR, "COMPLEX9.gds"),
                                  os.path.join(ADDER_DIR, "COMPLEX9.Astranlog"))
    names = {l.name for l in model.ordered_layers()}
    assert {"active", "poly", "metal1", "pr_boundary"} <= names
    pr = next(l for l in model.ordered_layers() if l.name == "pr_boundary")
    # The boundary polygon must match the displayed cell outline.
    assert pr.area_um2 == pytest.approx(model.width_um * model.height_um,
                                        rel=0.05)


# ------------------------------------------------------- environment probe
def test_probe_environment_shape():
    checks = paths.probe_environment()
    assert checks and all(hasattr(c, "ok") and hasattr(c, "label") for c in checks)
    assert any(c.key == "astran" for c in checks)


# ------------------------------------------------- custom BLIF inputs
def test_custom_blif_resolution():
    """A user-added BLIF must shadow the standard benchmark of the same name."""
    from gui import flow_core
    cfg = flow_core.FlowConfig()
    cfg.custom_blifs = {"my_design": r"D:\data\my_design.blif"}
    runner = flow_core.FlowRunner(cfg)
    assert runner._blif_path("my_design") == r"D:\data\my_design.blif"
    assert runner._blif_path("adder") == paths.benchmark_path("adder")
    assert runner._blif_path("my_design") != paths.benchmark_path("my_design")
    assert "custom=1" in cfg.describe()


# ------------------------------------------------------ PDK inputs & geometry
def test_pdk_config_resolution():
    """None-valued PDK fields must resolve to the repository defaults."""
    from gui import flow_core
    cfg = flow_core.FlowConfig()
    assert cfg.liberty() == paths.LIBERTY_FILE
    assert cfg.spice_lib() == paths.SPICE_LIB_FILE
    assert cfg.technology() == paths.ASTRAN_TECHNOLOGY
    assert cfg.lef() == paths.LEF_FILE
    assert cfg.layer_map() == paths.LAYER_MAP_FILE
    cfg.liberty_file = r"D:\pdk\my.lib"
    cfg.geometry = {"cells_height": 20, "nwell_pos": 1.0}
    assert cfg.liberty() == r"D:\pdk\my.lib"
    assert "pdk=自定义" in cfg.describe()


def test_read_lef_widths():
    widths = artifacts.read_lef_widths(paths.LEF_FILE)
    assert widths, "expected gscl45nm.lef macros"
    assert "NAND2X1" in widths and widths["NAND2X1"] > 0


def test_read_layer_map():
    layer_map = artifacts.read_layer_map(paths.LAYER_MAP_FILE)
    assert layer_map, "expected gds2_encounter.map entries"
    assert layer_map[49] == "metal1"
    assert layer_map[51] == "metal2"
    assert 1 not in layer_map          # base layers keep Cadence numbers


def test_baseline_staleness_with_custom_geometry():
    """A custom geometry must invalidate the cached ASTRAN baseline (matched
    row heights are required for the area comparison, AGENTS.md invariant 10)."""
    from gui import flow_core
    cfg = flow_core.FlowConfig()
    runner = flow_core.FlowRunner(cfg)
    assert not runner._baseline_is_stale_geometry()
    cfg.geometry = {"cells_height": 20, "h_grid": 0.19, "v_grid": 0.19,
                    "supply_size": 0.26, "nwell_pos": 1.0, "cell_template": "Tapless"}
    assert runner._baseline_is_stale_geometry()
    cfg.geometry = None
    cfg.technology_file = r"D:\pdk\custom.rul"
    assert runner._baseline_is_stale_geometry()


def test_geometry_override_in_run_script():
    """The GUI's layout-constraint overrides must reach the ASTRAN .run script
    while the defaults stay byte-identical to the CLI flow."""
    import astran
    default = astran.build_astran_commands(
        "gu", "tech", "net.sp", "CELL", "dir")
    assert "set nwellpos %g" % astran.ASTRAN_NWELL_POS in default
    assert "set rowheight %d" % astran.ASTRAN_CELLS_HEIGHT in default
    custom = astran.build_astran_commands(
        "gu", "tech", "net.sp", "CELL", "dir",
        geometry={"nwell_pos": 1.0, "cells_height": 20})
    assert "set nwellpos 1" in custom
    assert "set rowheight 20" in custom
    assert "set grid %g %g" % (astran.ASTRAN_HGRID, astran.ASTRAN_VGRID) in custom


# -------------------------------------------------------- PDK editor parsers
RUL_PATH = os.path.join(paths.ASTRAN_BUILD_DIR, "Work", "tech_freePDK45.rul")
MAP_PATH = paths.LAYER_MAP_FILE


def test_parse_rul_file_lossless():
    from gui import pdk_editor as pdk
    rows = pdk.parse_rul_file(RUL_PATH)
    assert rows, "expected the vendored technology file"
    rules = pdk.rul_rules(rows)
    layers = pdk.rul_layers(rows)
    assert len(rules) > 50
    assert len(layers) >= 15
    # globals and a known rule
    names = {r.cells[0][0] for r in rules}
    assert "TECHNAME" in names and "S1P1P1" in names and "W2DF" in names
    # layers: CONT -> GDSII 10
    cont = next(r for r in layers if r.cells[0][0] == "CONT")
    assert cont.cells[2][0] == "10"
    # lossless round-trip: raw lines are preserved verbatim
    original = open(RUL_PATH, "r", errors="replace").read()
    assert pdk.rul_to_text(rows) == original


def test_decode_rule_name():
    from gui import pdk_editor as pdk
    short, detail = pdk.decode_rule_name("S1P1P1")
    assert "间距" in short and "poly" in detail
    short, detail = pdk.decode_rule_name("W2DF")
    assert "宽度" in detail or "width" in detail
    short, detail = pdk.decode_rule_name("E2M1CT")
    assert "包含" in detail
    short, _d = pdk.decode_rule_name("TECHNAME")
    assert "工艺名" in short


def test_edit_rule_row_render():
    from gui import pdk_editor as pdk
    rows = pdk.parse_rul_file(RUL_PATH)
    row = next(r for r in pdk.rul_rules(rows) if r.cells[0][0] == "S1P1P1")
    pdk.render_rule_row(row, "S1P1P1", "0.080")
    assert row.raw.endswith("0.080")
    assert row.cells[1][0] == "0.080"
    ok, msg = pdk.validate_rows(rows)
    assert ok
    # an invalid edit is caught
    pdk.render_rule_row(row, "S1P1P1", "abc")
    ok, msg = pdk.validate_rows(rows)
    assert not ok and "数值" in msg


def test_parse_map_file_lossless_and_entries():
    from gui import pdk_editor as pdk
    rows = pdk.parse_map_file(MAP_PATH)
    assert rows
    entries = pdk.map_entries(rows)
    assert ("metal1", "NET", 49, 0) in entries
    assert ("metal2", "PIN", 51, 0) in entries
    original = open(MAP_PATH, "r", errors="replace").read()
    assert pdk.map_to_text(rows) == original
    # purpose explanations present
    row = next(r for r in rows if r.kind == "row" and r.cells[1][0] == "NET")
    assert "走线" in row.cells[1][1]


def test_map_edit_validation():
    from gui import pdk_editor as pdk
    rows = pdk.parse_map_file(MAP_PATH)
    row = next(r for r in rows if r.kind == "row")
    pdk.render_map_row(row, row.cells[0][0], row.cells[1][0], "not-int", "0")
    ok, msg = pdk.validate_rows(rows)
    assert not ok and "整数" in msg
def test_astran_launch_error_translated(monkeypatch, tmp_path):
    """A missing/blocked binary must become actionable guidance, not a traceback."""
    from gui import flow_core
    monkeypatch.setattr(flow_core.paths, "ASTRAN_BINARY",
                        str(tmp_path / "no_such_Astran.exe"))
    log_fh = open(tmp_path / "x.log", "w")
    try:
        with pytest.raises(flow_core.AstranLaunchError) as exc:
            flow_core._popen_astran(str(tmp_path / "x.run"), log_fh)
    finally:
        log_fh.close()
    msg = str(exc.value)
    assert "360" in msg and "build_astran" in msg and "信任区" in msg
