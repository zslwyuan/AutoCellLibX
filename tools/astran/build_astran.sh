#!/bin/sh
# Build the vendored ASTRAN on Windows with MSYS2 MinGW64 + wxWidgets 3.2.
#
#   tools/astran/build_astran.sh
#
# Produces: tools/astran/build/bin/Astran(.exe)
#
# Requirements:
#   - MSYS2 installed at C:\msys64 with mingw-w64-x86_64-gcc and
#     mingw-w64-x86_64-wxwidgets3.2-msw
#   - bin/wx-config (this repo) is used to keep the wx flags consistent
#
# Run from Git Bash (or any POSIX shell).
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

if [ ! -d /c/msys64/mingw64 ]; then
    echo "ERROR: C:/msys64/mingw64 not found. Install MSYS2 + MinGW64 toolchain." >&2
    exit 1
fi

# Our wx-config shim first, then the MSYS2 toolchain (g++, mingw32-make, wx).
export PATH="$HERE/bin:/c/msys64/mingw64/bin:$PATH"

echo ">> Compiling ASTRAN (mingw32-make, Release)"
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

# Stage the wxWidgets runtime DLLs next to the binary so it can run without
# MSYS2 on PATH (best effort; Astran.py also prepends C:\msys64\mingw64\bin).
for dll in wxbase32u_gcc_custom.dll wxmsw32u_core_gcc_custom.dll; do
    if [ -f "/c/msys64/mingw64/bin/$dll" ]; then
        cp -f "/c/msys64/mingw64/bin/$dll" build/bin/
    fi
done

BIN=build/bin/Astran
[ -f build/bin/Astran.exe ] && BIN=build/bin/Astran.exe
echo ">> Built: $HERE/$BIN"
