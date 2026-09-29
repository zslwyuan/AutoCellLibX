@echo off
rem AutoCellLibX installer step (ASCII only: cmd.exe parses batch files in the
rem ANSI codepage, so any non-ASCII text here would corrupt the parse).
rem Copies the payload to %LOCALAPPDATA%\AutoCellLibX, creates Start Menu +
rem Desktop shortcuts, offers to launch.  Run by the self-extracting stub from
rem the extraction directory (%%~dp0).
setlocal EnableExtensions
title AutoCellLibX Setup
set "SRC=%~dp0"
rem %~dp0 ends with a backslash; a trailing \" inside quotes breaks cmd's
rem argument parsing and glues the whole command line together.
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
set "DEST=%LOCALAPPDATA%\AutoCellLibX"
echo.
echo   AutoCellLibX ^| Standard-Cell Extension Workbench
echo   ================================================
echo   Install dir: %DEST%
echo.
if not exist "%DEST%" mkdir "%DEST%"
robocopy "%SRC%" "%DEST%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo   FAILED: could not copy files ^(robocopy error %errorlevel%^).
    echo   Check disk space and write permission for %LOCALAPPDATA%.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%DEST%\make_shortcuts.ps1"
echo   Desktop and Start Menu shortcuts created.
echo.
echo   Installed. Before first use, please read:
echo     %DEST%\README_DELIVERY.md
echo   (includes whitelist steps for security software that flags ASTRAN).
echo.
if /i "%ACLX_SILENT%"=="1" goto :done
choice /C YN /T 15 /D N /M "Launch AutoCellLibX now"
if errorlevel 2 goto :done
start "" "%DEST%\AutoCellLibX.exe"
:done
exit /b 0
