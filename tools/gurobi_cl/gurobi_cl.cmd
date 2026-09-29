@echo off
rem Gurobi-compatible CLI wrapper (python-mip + COIN-OR CBC), used by ASTRAN
rem via its "set lpsolve" command. %~dp0 resolves to this script's directory.
rem
rem pythonw.exe (not python.exe): the solver is spawned by Astran.exe, which
rem runs with CREATE_NO_WINDOW from the GUI -- a console python.exe would
rem still open a black window for every LP solve.  pythonw gives the wrapper
rem no stdout/stderr, so gurobi_cl.py redirects its print() calls to the log
rem files itself; ASTRAN only reads the ResultFile=.sol, never this stdout.
rem The interpreter dir is on PATH first (Astran.py prepends it; so does the
rem packaged launcher), so bare pythonw resolves to the right runtime.
pythonw "%~dp0gurobi_cl.py" %*