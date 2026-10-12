"""Unit tests for flow/astran_lint.py -- the ASTRAN SPICE preflight rules.

Every rule here cost real time once (a full ASTRAN run lost to a parser
abort or a silently dropped transistor), so they are pinned down with
toy netlists covering the good case and each failure mode.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "flow"))

from astran_lint import ERROR, WARNING, lint_text          # noqa: E402

GOOD = """\
.subckt TOY_NAND A B Y VCC GND
M0 Y A VCC VCC PMOS W=0.5u L=0.05u
M1 VCC B Y VCC PMOS W=0.5u L=0.05u
M2 n1 A GND GND NMOS W=0.5u L=0.05u
M3 Y B n1 GND NMOS W=0.5u L=0.05u
.ends TOY_NAND
"""


def severities(issues, severity):
    return [i for i in issues if i.severity == severity]


def messages(issues):
    return [i.message for i in issues]


def test_good_netlist_passes_clean():
    assert lint_text(GOOD) == []


def test_non_m_transistor_line_aborts_load():
    bad = GOOD.replace("M0 Y A VCC VCC PMOS", "g0#M0 Y A VCC VCC PMOS")
    errs = severities(lint_text(bad), ERROR)
    assert any("unrecognised line" in m for m in messages(errs))


def test_c_prefixed_device_is_silently_skipped():
    bad = GOOD.replace("M0 Y A VCC VCC PMOS", "C0 Y A VCC VCC PMOS")
    errs = severities(lint_text(bad), ERROR)
    assert any("silently SKIPPED" in m for m in messages(errs))


def test_x_prefixed_device_becomes_instance():
    bad = GOOD.replace("M0 Y A VCC VCC PMOS", "X0 Y A VCC VCC PMOS")
    warns = severities(lint_text(bad), WARNING)
    assert any("instance" in m for m in messages(warns))


def test_custom_model_names_rejected():
    bad = GOOD.replace("PMOS W=0.5u L=0.05u", "PMOS_CORE W=0.5u L=0.05u", 1)
    errs = severities(lint_text(bad), ERROR)
    assert any("model 'PMOS_CORE' is not accepted" in m
               for m in messages(errs))


def test_braced_parameter_parses_to_zero():
    bad = GOOD.replace("L=0.05u", "L={LCH}")
    errs = severities(lint_text(bad), ERROR)
    assert any("parses to no number" in m for m in messages(errs))


def test_wl_on_continuation_line_is_an_error():
    bad = (".subckt T A Y VCC GND\n"
           "M0 Y A VCC VCC PMOS\n"
           "+ W=0.5u L=0.05u\n"
           "M1 Y A GND GND NMOS W=0.5u L=0.05u\n"
           ".ends T\n")
    errs = severities(lint_text(bad), ERROR)
    assert any("continuation" in m for m in messages(errs))
    assert any("lacks a valid L= or W=" in m for m in messages(errs))


def test_short_transistor_line_rejected():
    bad = GOOD.replace("M0 Y A VCC VCC PMOS W=0.5u L=0.05u", "M0 Y A VCC PMOS")
    errs = severities(lint_text(bad), ERROR)
    assert any("at least" in m for m in messages(errs))


def test_unknown_parameter_rejected():
    bad = GOOD.replace("L=0.05u", "L=0.05u FOO=1")
    errs = severities(lint_text(bad), ERROR)
    assert any("not supported" in m for m in messages(errs))


def test_duplicate_transistor_names_rejected():
    bad = GOOD.replace("M1 VCC B Y", "M0 VCC B Y")
    errs = severities(lint_text(bad), ERROR)
    assert any("duplicate transistor name" in m for m in messages(errs))


def test_vdd_vss_deck_warns_about_supply_defaults():
    bad = GOOD.replace("VCC", "VDD").replace("GND", "VSS")
    issues = lint_text(bad)
    assert severities(issues, ERROR) == []
    warns = messages(severities(issues, WARNING))
    assert any("vddNet" in m for m in warns)
    assert any("gndNet" in m for m in warns)


def test_large_cell_warns_about_runtime():
    body = "".join("M%d Y A VCC VCC PMOS W=0.5u L=0.05u\n" % i
                   for i in range(45))
    deck = ".subckt BIG A Y VCC GND\n" + body + ".ends BIG\n"
    warns = messages(severities(lint_text(deck), WARNING))
    assert any("beyond the proven range" in m for m in warns)


def test_nested_subckt_rejected():
    bad = (".subckt A X VCC GND\nM0 X B VCC VCC PMOS W=0.5u L=0.05u\n"
           ".subckt B Y VCC GND\n.ends B\n.ends A\n")
    errs = severities(lint_text(bad), ERROR)
    assert any("nested .SUBCKT" in m for m in messages(errs))


def test_content_after_end_is_warned():
    bad = GOOD + ".end\nM9 X A VCC VCC PMOS W=0.5u L=0.05u\n"
    warns = messages(severities(lint_text(bad), WARNING))
    assert any("never read" in m for m in warns)


def test_unclosed_subckt_rejected():
    bad = GOOD.replace(".ends TOY_NAND\n", "")
    errs = severities(lint_text(bad), ERROR)
    assert any("never closed" in m for m in messages(errs))


def test_include_warns_about_relative_paths():
    bad = ".include ../lib/models.sp\n" + GOOD
    warns = messages(severities(lint_text(bad), WARNING))
    assert any(".INCLUDE" in m for m in warns)


def test_multiplier_and_area_params_allowed():
    good = GOOD.replace("W=0.5u L=0.05u",
                        "W=0.5u L=0.05u M=2 AD=0p PD=0u AS=0p PS=0u")
    assert lint_text(good) == []


def test_dot_prefixed_width_value_accepted():
    good = GOOD.replace("W=0.5u", "W=.5u")
    assert lint_text(good) == []


def test_missing_subckt_is_file_level_error():
    errs = severities(lint_text("* just a comment\n"), ERROR)
    assert any("no .SUBCKT" in m for m in messages(errs))
