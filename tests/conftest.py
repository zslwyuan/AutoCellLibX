"""Shared pytest fixtures for the AutoCellLibX test suite.

The flow modules use paths relative to the flow directory (e.g.
``../std_celllib/...``), so tests that call them must run with ``cwd=flow``.
Use the ``in_flow`` fixture for that.
"""
import os
import sys

import pytest

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOW_DIR = os.path.join(REPO_DIR, "flow")

# Make the flow importable as top-level modules (blif_preproc, spice, ...).
if FLOW_DIR not in sys.path:
    sys.path.insert(0, FLOW_DIR)

BENCHMARK_BLIF_DIR = os.path.join(REPO_DIR, "benchmark", "blif")
LIBERTY_FILE = os.path.join(REPO_DIR, "std_celllib", "gscl45nm.lib")
SPICE_LIB_FILE = os.path.join(REPO_DIR, "std_celllib", "cellsAstranFriendly.sp")


@pytest.fixture(scope="session")
def repo_dir():
    return REPO_DIR


@pytest.fixture(scope="session")
def flow_dir():
    return FLOW_DIR


@pytest.fixture()
def in_flow(monkeypatch):
    """Run the test body with cwd = flow (required by path-relative modules)."""
    monkeypatch.chdir(FLOW_DIR)
    return FLOW_DIR
