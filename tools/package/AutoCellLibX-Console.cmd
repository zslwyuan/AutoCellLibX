@echo off
rem Console launcher: shows the GUI with all Python output on this console,
rem for diagnosing startup problems (double-click AutoCellLibX.exe for normal
rem use).
setlocal
set "APP=%~dp0"
set "PATH=%APP%runtime;%APP%runtime\Scripts;%PATH%"
cd /d "%APP%"
"%APP%runtime\python.exe" -m gui %*
