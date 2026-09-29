"""Filesystem layout and environment probe for the GUI.

All paths are absolute and derived from this file's location, so the GUI works
regardless of the current working directory.  (The flow modules themselves are
cwd-sensitive -- they use ``../stdCelllib`` and ``./outputs`` -- so whoever
calls them must chdir to ``pySrc``; that is done in flow_worker, never here.)
"""
import os
import sys

REPO_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PYSRC_DIR = os.path.join(REPO_DIR, "pySrc")
OUTPUTS_DIR = os.path.join(PYSRC_DIR, "outputs")
ORIGINAL_CELLS_DIR = os.path.join(PYSRC_DIR, "originalAstranStdCells")
BENCHMARK_DIR = os.path.join(REPO_DIR, "benchmark", "blif")
STDCELLLIB_DIR = os.path.join(REPO_DIR, "stdCelllib")

LIBERTY_FILE = os.path.join(STDCELLLIB_DIR, "gscl45nm.lib")
LEF_FILE = os.path.join(STDCELLLIB_DIR, "gscl45nm.lef")
SPICE_LIB_FILE = os.path.join(STDCELLLIB_DIR, "cellsAstranFriendly.sp")
LAYER_MAP_FILE = os.path.join(STDCELLLIB_DIR, "gds2_encounter.map")

ASTRAN_BUILD_DIR = os.path.join(REPO_DIR, "tools", "astran", "build")
ASTRAN_BINARY = os.path.join(ASTRAN_BUILD_DIR, "bin", "Astran.exe")
ASTRAN_TECHNOLOGY = os.path.join(ASTRAN_BUILD_DIR, "Work", "tech_freePDK45.rul")
GUROBI_CL = os.path.join(REPO_DIR, "tools", "gurobi_cl", "gurobi_cl.cmd")

# Benchmarks that are too large to parse in a desktop interaction (~90 MB BLIF).
LARGE_BLIF_BYTES = 8 * 1024 * 1024


def benchmark_path(name):
    return os.path.join(BENCHMARK_DIR, name + ".blif")


def output_dir(name):
    return os.path.join(OUTPUTS_DIR, name)


def list_benchmarks():
    """Every benchmark as (name, size_bytes, path), sorted by name."""
    if not os.path.isdir(BENCHMARK_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(BENCHMARK_DIR)):
        if fn.endswith(".blif"):
            p = os.path.join(BENCHMARK_DIR, fn)
            out.append((fn[:-5], os.path.getsize(p), p))
    return out


def ensure_pysrc_on_path():
    """Make the flow modules importable as top-level modules."""
    if PYSRC_DIR not in sys.path:
        sys.path.insert(0, PYSRC_DIR)


class EnvCheck(object):
    """One row of the environment report."""

    def __init__(self, key, label, ok, detail, hint="", required=True):
        self.key = key
        self.label = label
        self.ok = ok
        self.detail = detail
        self.hint = hint
        self.required = required

    @property
    def level(self):
        if self.ok:
            return "ok"
        return "error" if self.required else "warn"


def _module_version(name, attr="__version__"):
    try:
        mod = __import__(name)
    except Exception as exc:            # noqa: BLE001 - reported, not raised
        return None, str(exc)
    return getattr(mod, attr, "?"), ""


def probe_environment():
    """Report the toolchain state the flow needs to run end to end."""
    checks = []

    checks.append(EnvCheck(
        "python", "Python interpreter", True,
        "%s (%s)" % (sys.version.split()[0], sys.executable),
        "The flow and the LP-solver wrapper must share this interpreter "
        "(python-mip lives here)."))

    for mod in ("numpy", "networkx", "matplotlib", "blifparser",
                "liberty", "lark", "gdstk"):
        ver, err = _module_version(mod)
        checks.append(EnvCheck(
            "py:" + mod, "python:%s" % mod, ver is not None,
            ver if ver is not None else err,
            "pip install -r requirements.txt", required=False))

    ver, err = _module_version("mip")
    checks.append(EnvCheck(
        "mip", "python-mip (LP solver backbone)", ver is not None,
        ver if ver is not None else err,
        "ASTRAN compaction calls tools/gurobi_cl/gurobi_cl.cmd, which runs "
        "python-mip + CBC. Without it every compaction fails and cells come "
        "out 0 x 0."))

    checks.append(EnvCheck(
        "astran", "ASTRAN binary", os.path.exists(ASTRAN_BINARY),
        ASTRAN_BINARY,
        "build it with: bash tools/astran/build_astran.sh"))
    checks.append(EnvCheck(
        "tech", "ASTRAN technology rules", os.path.exists(ASTRAN_TECHNOLOGY),
        ASTRAN_TECHNOLOGY, "regenerate with build_astran.sh", required=False))
    checks.append(EnvCheck(
        "solver", "gurobi_cl wrapper", os.path.exists(GUROBI_CL),
        GUROBI_CL, "vendored under tools/gurobi_cl/"))
    checks.append(EnvCheck(
        "liberty", "GSCL45 liberty", os.path.exists(LIBERTY_FILE), LIBERTY_FILE,
        "", required=False))
    checks.append(EnvCheck(
        "lef", "GSCL45 LEF", os.path.exists(LEF_FILE), LEF_FILE,
        "the LEF supplies the nominal cell widths used for area comparison",
        required=False))
    checks.append(EnvCheck(
        "spicelib", "Astran-friendly SPICE library",
        os.path.exists(SPICE_LIB_FILE), SPICE_LIB_FILE))

    n_base = 0
    if os.path.isdir(ORIGINAL_CELLS_DIR):
        n_base = len([f for f in os.listdir(ORIGINAL_CELLS_DIR)
                      if f.endswith(".Astranlog")])
    checks.append(EnvCheck(
        "baseline", "ASTRAN baseline cells generated", n_base > 0,
        "%d cell layouts in originalAstranStdCells/" % n_base,
        "The area comparison needs an ASTRAN baseline at the same row height "
        "as the generated cells; the first run generates the missing ones.",
        required=False))

    return checks


def environment_ready(checks):
    return all(c.ok for c in checks if c.required)
