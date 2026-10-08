#!/usr/bin/env python3
"""Build the customer installer in dist/.

Primary deliverable (two files, avoids 360 Total Security's real-time
quarantine of exe-with-appended-archive):

    AutoCellLibX-Setup.exe   - the C stub (tools/package/installer_stub.c)
    AutoCellLibX-Setup.dat   - the stage directory as a ZIP

Running the exe extracts the .dat to %TEMP% (progress dialog), runs
setup.cmd (copies to %LOCALAPPDATA%\\AutoCellLibX, creates shortcuts) and
cleans up.  With --single the archive is also appended to the exe for
single-file delivery on machines without that heuristic.

    python tools/package/make_installer.py   [--no-stage] [--single]
"""
import argparse
import os
import shutil
import subprocess
import sys
import zipfile

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", ".."))
PKG = os.path.join(REPO, "tools", "package")
DIST = os.path.join(REPO, "dist")
STAGE = os.path.join(DIST, "stage")
DAT_PATH = os.path.join(DIST, "AutoCellLibX-Setup.dat")
STUB_EXE = os.path.join(DIST, "installer_stub.exe")
OUT = os.path.join(DIST, "AutoCellLibX-Setup.exe")
MSYS_BASH = r"C:\msys64\usr\bin\bash.exe"


def build_stub():
    if not os.path.exists(MSYS_BASH):
        sys.exit("MSYS2 bash not found: %s" % MSYS_BASH)
    if os.path.exists(STUB_EXE):
        os.remove(STUB_EXE)
    cmd = ("cd '%s' && gcc -O2 -mwindows -static -fno-use-linker-plugin "
           "installer_stub.c "
           "-o '%s' -lz -lshell32 -lcomctl32 -luser32 -lgdi32 -lole32"
           % (PKG, STUB_EXE))
    subprocess.run([MSYS_BASH, "-lc", cmd], check=True)
    print("stub built: %s" % STUB_EXE)


def make_dat():
    if os.path.exists(DAT_PATH):
        os.remove(DAT_PATH)
    n = 0
    with zipfile.ZipFile(DAT_PATH, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        for root, _dirs, files in os.walk(STAGE):
            for f in sorted(files):
                src = os.path.join(root, f)
                rel = os.path.relpath(src, STAGE).replace("\\", "/")
                zf.write(src, rel)
                n += 1
    print("dat built: %s  (%d files, %.1f MB)"
          % (DAT_PATH, n, os.path.getsize(DAT_PATH) / 1e6))


def emit_installer():
    shutil.copy2(STUB_EXE, OUT)
    print("installer built: %s  (%.2f MB, stub only; reads %s from its dir)"
          % (OUT, os.path.getsize(OUT) / 1e6,
             os.path.basename(DAT_PATH)))


def emit_single_file():
    single = os.path.join(DIST, "AutoCellLibX-Setup-SingleFile.exe")
    with open(single, "wb") as out:
        with open(STUB_EXE, "rb") as fh:
            shutil.copyfileobj(fh, out)
        with open(DAT_PATH, "rb") as fh:
            shutil.copyfileobj(fh, out)
    print("single-file variant built: %s  (%.1f MB, may be quarantined by 360)"
          % (single, os.path.getsize(single) / 1e6))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-stage", action="store_true",
                    help="reuse the existing dist/stage")
    ap.add_argument("--single", action="store_true",
                    help="also emit the single-file (appended archive) variant")
    args = ap.parse_args()

    if not args.no_stage:
        subprocess.run([sys.executable, os.path.join(PKG, "make_stage.py")],
                       check=True)
    if not os.path.isdir(STAGE):
        sys.exit("no stage directory; run make_stage.py first")
    build_stub()
    make_dat()
    emit_installer()
    if args.single:
        emit_single_file()


if __name__ == "__main__":
    main()
