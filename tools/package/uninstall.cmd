@echo off
rem Remove the AutoCellLibX install (folder + shortcuts).  ASCII only, see
rem setup.cmd.  Run from anywhere; it leaves the current directory first so
rem rd can delete the install folder even when started from inside it.
setlocal EnableExtensions
title AutoCellLibX Uninstall
echo Closing running AutoCellLibX ...
taskkill /IM pythonw.exe /F >nul 2>nul
del /q "%USERPROFILE%\Desktop\AutoCellLibX.lnk" >nul 2>nul
del /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\AutoCellLibX.lnk" >nul 2>nul
cd /d "%TEMP%"
rd /s /q "%LOCALAPPDATA%\AutoCellLibX" >nul 2>nul
echo AutoCellLibX has been removed (%LOCALAPPDATA%\AutoCellLibX deleted).
pause
