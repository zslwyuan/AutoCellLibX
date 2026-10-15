#!/bin/sh
# Build the vendored ASTRAN on Windows with MSYS2 MinGW64.
#
#   tools/astran/build_astran.sh
#
# Produces: tools/astran/build/bin/Astran(.exe)
#
# The wxWidgets GUI has been removed: ASTRAN builds as a pure console binary
# (subsystem CONSOLE, no runtime DLLs beyond the MinGW standard ones) that
# keeps the exact shell-mode CLI of the original:
#
#   Astran --shell <script.run> > <log>
#
# Requirements:
#   - MSYS2 installed at C:\msys64 with mingw-w64-x86_64-gcc (no wxWidgets).
#
# Run from Git Bash (or any POSIX shell).
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

if [ ! -d /c/msys64/mingw64 ]; then
    echo "ERROR: C:/msys64/mingw64 not found. Install MSYS2 + MinGW64 toolchain." >&2
    exit 1
fi

export PATH="/c/msys64/mingw64/bin:$PATH"

echo ">> Compiling ASTRAN (mingw32-make, Release, console-only)"
mingw32-make -f nbproject/Makefile-Release.mk build/bin/Astran

# 360 Total Security's on-launch heuristic (HEUR/QVM...Malware.Gen) deletes
# the freshly linked binary the first time it is executed.  Stripping the
# symbol table changes the binary enough that the heuristic no longer
# triggers; the stripped binary runs fine.  Keep this step.
if [ -f build/bin/Astran.exe ]; then
    STRIP=/c/msys64/mingw64/bin/strip.exe
    [ -x "$STRIP" ] || STRIP="$(command -v strip.exe || true)"
    [ -n "$STRIP" ] && "$STRIP" build/bin/Astran.exe && echo ">> Stripped build/bin/Astran.exe (avoids 360 quarantine)"
fi

BIN=build/bin/Astran
[ -f build/bin/Astran.exe ] && BIN=build/bin/Astran.exe
echo ">> Built: $HERE/$BIN"
