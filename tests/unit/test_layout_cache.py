"""Unit tests for the ASTRAN layout cache decision (pySrc/astran.py)."""
import os
import time

from astran import astranLayoutIsStale


def _make(path, mtime):
    with open(path, "w") as f:
        f.write("x")
    os.utime(path, (mtime, mtime))


def test_missing_layout_is_stale(tmp_path):
    sp = str(tmp_path / "a.sp")
    _make(sp, time.time())
    assert astranLayoutIsStale(str(tmp_path / "a.gds"), sp) is True


def test_layout_without_netlist_is_fresh(tmp_path):
    gds = str(tmp_path / "a.gds")
    _make(gds, time.time())
    assert astranLayoutIsStale(gds, str(tmp_path / "missing.sp")) is False


def test_layout_newer_than_netlist_is_fresh(tmp_path):
    gds = str(tmp_path / "a.gds")
    sp = str(tmp_path / "a.sp")
    now = time.time()
    _make(sp, now - 100)
    _make(gds, now)
    assert astranLayoutIsStale(gds, sp) is False


def test_netlist_newer_than_layout_is_stale(tmp_path):
    gds = str(tmp_path / "a.gds")
    sp = str(tmp_path / "a.sp")
    now = time.time()
    _make(gds, now - 100)
    _make(sp, now)
    assert astranLayoutIsStale(gds, sp) is True
