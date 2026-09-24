@echo off
rem Gurobi-compatible CLI wrapper (python-mip + COIN-OR CBC), used by ASTRAN
rem via its "set lpsolve" command. %~dp0 resolves to this script's directory.
python "%~dp0gurobi_cl.py" %*
