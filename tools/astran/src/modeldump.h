/**
 \file modeldump.h

 STAGE 1 of the AutoCellLibX ASTRAN -> Python compaction port: export the
 compaction ILP model as JSON so the Python side (tools/gurobi_cl) can stop
 hand-parsing the CPLEX-LP text (AGENTS.md invariant 3).

 The dump is driven entirely by the environment variable ASTRAN_MODEL_DUMP;
 when it is unset a stock ASTRAN run behaves exactly as before.
 */

#pragma once

#include <string>

/**
 If the environment variable ASTRAN_MODEL_DUMP is set to a path, parse the
 CPLEX-LP file \p lpPath that Compaction::solve has just written (its own,
 deterministic, machine-format output) and emit the equivalent JSON model to
 that path.  The JSON mirrors exactly what the LP solver shim
 (tools/gurobi_cl/gurobi_cl.py) parses out of the LP text:

 - expression columns already appear as the plain "astranExprN" variables
   the LP writer renamed them to; their definition constraints (CexprN)
   are kept as ordinary constraints -- never collapsed into free variables;
 - terms with a non-finite (inf) coefficient mean "no bound" and are
   dropped, exactly like the shim's parser drops them;
 - constraint names (C<i>, Cexpr<j>, Czero) are preserved verbatim;
 - variables are listed in the order the shim's model builder creates them
   (Generals, Binary, Semi, objective scan, constraint scan), so a model
   built from the JSON has the same column order as the legacy model.

 Unset/empty ASTRAN_MODEL_DUMP -> the function returns immediately (zero
 behaviour change).  Never throws: any I/O or parse problem is reported on
 stdout and the regular LP solve continues.
 */
void astranDumpModelJson( const std::string & lpPath );
