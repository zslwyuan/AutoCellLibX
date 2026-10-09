#!/usr/bin/env python3
"""Build the portable AutoCellLibX stage directory (dist/stage/).

The deliverable is a self-contained app folder: a pruned Python 3.11 runtime
(site-packages trimmed to what the flow + GUI actually import), the flow
modules (flow), the GSCL45 PDK data (std_celllib), the benchmark netlists
(without the two >90 MB giants), the vendored ASTRAN build and the
gurobi_cl-compatible LP solver wrapper, plus launchers and install scripts.

Run from the repository root:

    python tools/package/make_stage.py

The stage is rebuilt from scratch every run, so the result is reproducible.
"""
import os
import shutil
import subprocess
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", ".."))
PY = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python311"
DIST = os.path.join(REPO, "dist")
STAGE = os.path.join(DIST, "stage")
PKG = os.path.join(REPO, "tools", "package")

# Benchmarks too large for a desktop interaction (~90 MB BLIF each); a customer
# can copy them back in manually if needed (see README_DELIVERY.md).
BIG_BLIFS = ("BoomBranchPredictor.blif", "DCache.blif")

# site-packages entries the flow + GUI actually import (exact top-level names).
# Everything else in the developer installation is deliberately not shipped.
SITE_KEEP = {
    # --- Qt (only QtCore/QtGui/QtWidgets are imported anywhere in gui/) ---
    "PySide6", "shiboken6",
    "pyside6-6.11.1.dist-info", "pyside6_addons-6.11.1.dist-info",
    "pyside6_essentials-6.11.1.dist-info", "shiboken6-6.11.1.dist-info",
    # --- numeric / ML pieces of the flow ---
    "numpy", "numpy.libs", "numpy-2.4.6.dist-info",
    "scipy", "scipy.libs", "scipy-1.17.1.dist-info",
    "sklearn", "scikit_learn-1.9.0.dist-info",
    "joblib", "joblib-1.5.3.dist-info",
    "threadpoolctl.py", "threadpoolctl-3.6.0.dist-info",
    "narwhals", "narwhals-2.22.1.dist-info",
    # --- matplotlib + its hard deps ---
    "matplotlib", "mpl_toolkits", "matplotlib-3.11.1.dist-info",
    "contourpy", "contourpy-1.3.3.dist-info",
    "cycler", "cycler-0.12.1.dist-info",
    "fontTools", "fonttools-4.63.0.dist-info",
    "kiwisolver", "kiwisolver-1.5.0.dist-info",
    "packaging", "packaging-26.2.dist-info",
    "PIL", "pillow-12.3.0.dist-info",
    "pyparsing", "pyparsing-3.3.2.dist-info",
    "dateutil", "python_dateutil-2.9.0.post0.dist-info",
    "six.py", "six-1.17.0.dist-info",
    # --- graph / parser / GDS pieces ---
    "networkx", "networkx-3.6.1.dist-info",
    "easydict", "easydict-1.13.dist-info",
    "blifparser", "blifparser-2.0.1.dist-info",
    "liberty", "liberty_parser-0.0.29.dist-info",
    "sympy", "sympy-1.14.0.dist-info",
    "mpmath", "mpmath-1.3.0.dist-info",
    "lark", "lark-1.3.1.dist-info",
    "gdstk", "gdstk-1.0.1.dist-info",
    "tqdm", "tqdm-4.70.1.dist-info",
    "colorama", "colorama-0.4.6.dist-info",
    # --- LP solver backbone (python-mip + COIN-OR CBC via cbcbox) ---
    "mip", "mip-2.0.0.dist-info",
    "cffi", "cffi-2.0.0.dist-info",
    "_cffi_backend.cp311-win_amd64.pyd",   # cffi's compiled backend
    "pycparser", "pycparser-3.0.dist-info",
    "cbcbox", "cbcbox-2.935.dist-info",
    "typing_extensions.py", "typing_extensions-4.15.0.dist-info",
    # --- pip/setuptools so a customer can add packages later ---
    "pip", "pip-26.1.2.dist-info",
    "setuptools", "setuptools-83.0.0.dist-info",
    "_distutils_hack", "distutils-precedence.pth",
}

# PySide6 submodules that are NOT imported by the GUI.  Qt6WebEngineCore.dll
# alone is ~200 MB; removing the WebEngine/QML/Quick/Multimedia/... stack
# roughly halves the Qt payload.
PYTHON_REMOVE = {
    "PySide6",  # handled specially below (selective pruning)
    "test", "idlelib", "tkinter", "turtledemo", "lib2to3", "venv",
}

PYSIDE6_REMOVE_PREFIXES = (
    "Qt63D", "Qt6Bluetooth", "Qt6Charts", "Qt6DataVisualization", "Qt6Designer",
    "Qt6Graphs", "Qt6Help", "Qt6HttpServer", "Qt6Labs", "Qt6Location",
    "Qt6Lottie", "Qt6Multimedia", "Qt6NetworkAuth", "Qt6Nfc", "Qt6Pdf",
    "Qt6Positioning", "Qt6PrintSupport", "Qt6Qml", "Qt6Quick", "Qt6RemoteObjects",
    "Qt6Scxml", "Qt6Sensors", "Qt6SerialBus", "Qt6SerialPort", "Qt6ShaderTools",
    "Qt6SpatialAudio", "Qt6Sql", "Qt6StateMachine", "Qt6SvgWidgets", "Qt6Test",
    "Qt6TextToSpeech", "Qt6UiTools", "Qt6VirtualKeyboard", "Qt6WebChannel",
    "Qt6WebEngine", "Qt6WebSockets", "Qt6WebView", "Qt6Xml", "Qt6Concurrent",
    "Qt6DBus", "avcodec", "avformat", "avutil",
)
PYSIDE6_REMOVE_EXACT = {"Qt6OpenGLWidgets.dll", "Qt6OpenGL.dll",
                        "QtOpenGLWidgets.pyd", "QtSvgWidgets.pyd", "QtXml.pyd",
                        "QtNetwork.pyd"}
PYSIDE6_REMOVE_DIRS = ("resources", "translations", "qml", "metatypes",
                       "phrasebooks", "examples", "typesystem")
PYSIDE6_REMOVE_PLUGINS = (
    "sqldrivers", "sceneparsers", "assetimporters", "renderers", "qmltooling",
    "multimedia", "designer", "canbus", "geoservices", "position",
    "texttospeech", "geometryloaders", "webview", "sensors", "scxmldatamodel",
    "vectorimageformats", "renderplugins", "qmllint", "virtualkeyboard",
)

# PySide6 keeps (QtCore/QtGui/QtWidgets).  Everything else is dropped by
# prefix (the WebEngine/QML/Quick/Multimedia/... stack, ~400 MB) or by exact
# name.  ICU, pyside6.abi3.dll, shiboken6.abi3.dll etc. stay automatically.
PYSIDE6_REMOVE_PREFIXES = (
    "Qt63D", "Qt6Bluetooth", "Qt6Charts", "Qt6DataVisualization", "Qt6Designer",
    "Qt6Graphs", "Qt6Help", "Qt6HttpServer", "Qt6Labs", "Qt6Location",
    "Qt6Lottie", "Qt6Multimedia", "Qt6NetworkAuth", "Qt6Nfc", "Qt6Pdf",
    "Qt6Positioning", "Qt6PrintSupport", "Qt6Qml", "Qt6Quick", "Qt6RemoteObjects",
    "Qt6Scxml", "Qt6Sensors", "Qt6SerialBus", "Qt6SerialPort", "Qt6ShaderTools",
    "Qt6SpatialAudio", "Qt6Sql", "Qt6StateMachine", "Qt6SvgWidgets", "Qt6Test",
    "Qt6TextToSpeech", "Qt6UiTools", "Qt6VirtualKeyboard", "Qt6WebChannel",
    "Qt6WebEngine", "Qt6WebSockets", "Qt6WebView", "Qt6Xml", "Qt6Concurrent",
    "Qt6DBus", "avcodec", "avformat", "avutil",
)
PYSIDE6_REMOVE_EXACT = {
    # small modules outside the prefix list that the GUI never imports
    "Qt6OpenGLWidgets.dll", "Qt6OpenGL.dll", "Qt6Network.dll", "Qt6SvgWidgets.dll",
    "Qt6Xml.dll", "Qt6Test.dll",
    "QtOpenGLWidgets.pyd", "QtOpenGL.pyd", "QtNetwork.pyd", "QtSvgWidgets.pyd",
    "QtXml.pyd", "QtTest.pyd", "QtConcurrent.pyd",
}
# The only Qt modules the GUI imports are QtCore/QtGui/QtWidgets; QtSvg is
# kept for icon loading.  All other Qt*.dll / Qt*.pyd are dropped.
PYSIDE6_KEEP_CORE = {"Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll",
                     "QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd",
                     "Qt6Svg.dll", "QtSvg.pyd"}

CBCBOX_REMOVE_SUBDIRS = ("include", "share", "lib64", "cmake")

FLOW_EXTRA_EXCLUDE = {
    "gnn_model.py", "blif_gnn_training.py",  # tensorflow-based training, not the flow
}


def rm(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def copytree_skip(src, dst, skip_dirs=(), skip_suffixes=(".pyc", ".pyo"),
                  skip_names=(), skip_extensions=()):
    """Copy src -> dst pruning __pycache__ and other junk."""
    if not os.path.isdir(src):
        raise FileNotFoundError(src)
    os.makedirs(dst, exist_ok=True)
    for name in sorted(os.listdir(src)):
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if name in skip_names or name in skip_dirs:
            continue
        if name == "__pycache__":
            continue
        if name.endswith(skip_suffixes):
            continue
        if os.path.splitext(name)[1] in skip_extensions:
            continue
        if os.path.isdir(s):
            copytree_skip(s, d, skip_dirs, skip_suffixes, skip_names,
                          skip_extensions)
        else:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)


def main():
    if not os.path.isdir(PY):
        sys.exit("Python install not found: %s" % PY)
    rm(STAGE)
    os.makedirs(STAGE)

    # ------------------------------------------------------------ repo parts
    def copy_repo_dir(rel, **kw):
        copytree_skip(os.path.join(REPO, rel), os.path.join(STAGE, rel), **kw)

    # gui: whole package, no pycache.
    copy_repo_dir("gui")

    # flow: flow modules + cached baselines + the shipped benchmark results.
    flow_src = os.path.join(STAGE, "flow")
    os.makedirs(flow_src)
    for name in sorted(os.listdir(os.path.join(REPO, "flow"))):
        s = os.path.join(REPO, "flow", name)
        d = os.path.join(flow_src, name)
        if name in ("__pycache__", "ILPmodel.lp", "ILPmodel.sol",
                    "someResults.zip") or name in FLOW_EXTRA_EXCLUDE:
            continue
        if os.path.isdir(s):
            copytree_skip(s, d)
        else:
            shutil.copy2(s, d)

    # std_celllib: the GSCL45 PDK data (liberty, LEF, SPICE bodies, layer map).
    copy_repo_dir("std_celllib")

    # benchmarks: the interactive-size suite (drop the two ~90 MB giants).
    blif_dst = os.path.join(STAGE, "benchmark", "blif")
    os.makedirs(blif_dst)
    for name in sorted(os.listdir(os.path.join(REPO, "benchmark", "blif"))):
        if name in BIG_BLIFS:
            continue
        shutil.copy2(os.path.join(REPO, "benchmark", "blif", name),
                     os.path.join(blif_dst, name))

    # tools: the ASTRAN build (binary + wx DLLs + technology rules) and the
    # gurobi_cl-compatible solver wrapper.  The ASTRAN sources are dev-only,
    # but its licensing statement ships with the package.
    copy_repo_dir("tools/astran/build")
    copy_repo_dir("tools/gurobi_cl")
    astran_lic = os.path.join(REPO, "tools", "astran", "LICENSE.md")
    if os.path.exists(astran_lic):
        os.makedirs(os.path.join(STAGE, "tools", "astran"), exist_ok=True)
        shutil.copy2(astran_lic,
                     os.path.join(STAGE, "tools", "astran", "LICENSE.md"))

    # docs: the engineering record travels with the product.
    copy_repo_dir("doc")
    for f in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "README.MD"):
        shutil.copy2(os.path.join(REPO, f), os.path.join(STAGE, f))

    # ------------------------------------------------------- Python runtime
    rt = os.path.join(STAGE, "runtime")
    os.makedirs(rt)
    for f in ("python.exe", "pythonw.exe", "python3.dll", "python311.dll",
              "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        shutil.copy2(os.path.join(PY, f), os.path.join(rt, f))
    shutil.copytree(os.path.join(PY, "DLLs"), os.path.join(rt, "DLLs"))

    # pruned stdlib
    lib_src = os.path.join(PY, "Lib")
    lib_dst = os.path.join(rt, "Lib")
    for name in sorted(os.listdir(lib_src)):
        if name in PYTHON_REMOVE or name == "site-packages":
            continue
        s = os.path.join(lib_src, name)
        d = os.path.join(lib_dst, name)
        if os.path.isdir(s):
            copytree_skip(s, d)
        else:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)

    # site-packages keep-list
    sp_src = os.path.join(lib_src, "site-packages")
    sp_dst = os.path.join(lib_dst, "site-packages")
    os.makedirs(sp_dst)
    for name in sorted(os.listdir(sp_src)):
        if name not in SITE_KEEP:
            continue
        s = os.path.join(sp_src, name)
        d = os.path.join(sp_dst, name)
        if name == "PySide6":
            _copy_pyside6(s, d)
        elif name == "cbcbox":
            _copy_cbcbox(s, d)
        elif os.path.isdir(s):
            copytree_skip(s, d)
        else:
            shutil.copy2(s, d)

    # ------------------------------------------------------ launcher + tools
    _build_launcher()
    for f in ("AutoCellLibX.exe", "AutoCellLibX-Console.cmd", "AutoCellLibX.ico",
              "setup.cmd", "uninstall.cmd", "make_shortcuts.ps1",
              "README_DELIVERY.md"):
        s = os.path.join(PKG, f)
        if not os.path.exists(s):
            sys.exit("missing package file: %s" % s)
        shutil.copy2(s, os.path.join(STAGE, f))

    total = _dir_size(STAGE)
    print("stage built: %s  (%.1f MB)" % (STAGE, total / 1e6))


def _copy_pyside6(src, dst):
    os.makedirs(dst)
    for name in sorted(os.listdir(src)):
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if name in PYSIDE6_REMOVE_DIRS:
            continue
        if name.endswith(".exe"):
            continue
        if name.startswith(PYSIDE6_REMOVE_PREFIXES):
            continue
        if name in PYSIDE6_REMOVE_EXACT:
            continue
        if name.endswith((".pyd", ".dll")) and name.startswith("Qt"):
            # Only QtCore/QtGui/QtWidgets (plus QtSvg) are imported; drop the
            # other Qt binary modules.  Non-Qt support DLLs (pyside6.abi3.dll,
            # shiboken6.abi3.dll, icu*, opengl32sw.dll) are always kept.
            if name not in PYSIDE6_KEEP_CORE:
                continue
        if name == "plugins":
            _copy_pyside6_plugins(s, d)
        elif os.path.isdir(s):
            copytree_skip(s, d)
        else:
            shutil.copy2(s, d)


def _copy_pyside6_plugins(src, dst):
    os.makedirs(dst)
    for name in sorted(os.listdir(src)):
        if name in PYSIDE6_REMOVE_PLUGINS:
            continue
        copytree_skip(os.path.join(src, name), os.path.join(dst, name))


def _copy_cbcbox(src, dst):
    os.makedirs(dst)
    for name in sorted(os.listdir(src)):
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if name == "__pycache__":
            continue
        if name.endswith(".dist-info"):
            copytree_skip(s, d)
            continue
        if name.startswith("cbc_dist") and os.path.isdir(s):
            # Only the runtime pieces: bin (cbc.exe + DLLs) and lib (libCbc...).
            os.makedirs(d, exist_ok=True)
            for sub in ("bin", "lib"):
                if os.path.isdir(os.path.join(s, sub)):
                    copytree_skip(os.path.join(s, sub), os.path.join(d, sub))
        elif os.path.isfile(s):
            shutil.copy2(s, d)


def _build_launcher():
    # MinGW gcc must be driven through the MSYS2 bash: invoked straight from
    # Git Bash it cannot spawn cc1.exe (CreateProcess error).
    msys_bash = r"C:\msys64\usr\bin\bash.exe"
    out = os.path.join(PKG, "AutoCellLibX.exe")
    if not os.path.exists(msys_bash):
        print("MSYS2 bash not found; launcher exe will not be rebuilt")
        return
    res = os.path.join(PKG, "launcher_res.o")
    cmd = ("cd '%s' && windres launcher.rc -O coff -o launcher_res.o && "
           "gcc -O2 -mwindows -static launcher.c launcher_res.o "
           "-o AutoCellLibX.exe -luser32 -lshell32" % PKG)
    subprocess.run([msys_bash, "-lc", cmd], check=True)
    print("launcher rebuilt: %s" % out)


def _dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    return total


if __name__ == "__main__":
    main()
