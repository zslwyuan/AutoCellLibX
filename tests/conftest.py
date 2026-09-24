"""Shared pytest fixtures for the AutoCellLibX test suite.

The pySrc modules use paths relative to the pySrc directory (e.g.
``../stdCelllib/...``), so tests that call them must run with ``cwd=pySrc``.
Use the ``in_pysrc`` fixture for that.
"""
import os
import sys

import pytest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYSRC_DIR = os.path.join(REPO_DIR, "pySrc")

# Make the flow importable as top-level modules (BLIFPreProc, spice, ...).
if PYSRC_DIR not in sys.path:
    sys.path.insert(0, PYSRC_DIR)

BENCHMARK_BLIF_DIR = os.path.join(REPO_DIR, "benchmark", "blif")
LIBERTY_FILE = os.path.join(REPO_DIR, "stdCelllib", "gscl45nm.lib")
SPICE_LIB_FILE = os.path.join(REPO_DIR, "stdCelllib", "cellsAstranFriendly.sp")


@pytest.fixture(scope="session")
def repo_dir():
    return REPO_DIR


@pytest.fixture(scope="session")
def pysrc_dir():
    return PYSRC_DIR


@pytest.fixture()
def in_pysrc(monkeypatch):
    """Run the test body with cwd = pySrc (required by path-relative modules)."""
    monkeypatch.chdir(PYSRC_DIR)
    return PYSRC_DIR
