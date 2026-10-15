/**
 \file modeldump.cpp

 CPLEX-LP -> JSON model transcoder for the AutoCellLibX stage-1 compaction
 port.  See modeldump.h for the contract.

 Design note: the JSON is derived by re-reading the LP file that
 Compaction::solve has just written rather than by walking Compaction's
 private in-memory containers.  Reasons:

 1. The private members (variables/constraints/ctrts) are not reachable
    from a free function without editing compaction.h.
 2. More importantly, the LP writer itself applies its S() expression
    renames *inconsistently* (raw unrenamed names in the CP_*_VAR_VAL and
    bound forms), which e.g. flips the sign of RELAXATION inside an
    expression key like "x0b + RELAXATION".  The LP text is the only
    complete, faithful projection of the model the solver actually sees,
    and it is exactly what the legacy shim parses -- so transcoding that
    text (with the shim's exact tokenizing rules, ported below) keeps the
    JSON semantically identical to the legacy model by construction.

 Self-contained: C++11, standard library only (matches -std=c++11 of
 nbproject/Makefile-Release.mk).  Every failure is non-fatal by design:
 a broken dump must never take down the layout run that is being compacted.
 */

#include "modeldump.h"

#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace {

/** A parsed linear term; var.empty() marks a bare constant. */
struct Term {
	double coef;
	std::string var;
	Term( double c, const std::string & v ) : coef(c), var(v) {}
};

struct RawConstraint {
	std::string name;   ///< verbatim LP constraint name ("C0", "Cexpr3", "Czero")
	std::string body;   ///< constraint text without name and without ';'
};

struct LpModel {
	std::string objText;                    ///< objective lines joined by ' '
	std::vector<RawConstraint> cons;        ///< Subject-To bodies, file order
	std::vector<std::string> intVars;       ///< Generals section, order kept
	std::vector<std::string> binVars;       ///< Binary section, order kept
	std::vector<std::string> semiVars;      ///< Semi section, order kept
	bool maximise;                          ///< LP said "Maximize"
	LpModel() : maximise(false) {}
};

/** Strip leading/trailing whitespace (isspace), like Python str.strip(). */
static std::string strip( const std::string & s ) {
	size_t b = 0, e = s.size();
	while ( b < e && isspace((unsigned char)s[b]) ) ++b;
	while ( e > b && isspace((unsigned char)s[e-1]) ) --e;
	return s.substr( b, e - b );
}

static std::string lower( const std::string & s ) {
	std::string r = s;
	for ( size_t k = 0; k < r.size(); ++k )
		r[k] = (char)tolower((unsigned char)r[k]);
	return r;
}

/** strtod constrained to the whole token: mirrors Python float(tok), which
 raises ValueError on anything with trailing garbage. */
static bool parseDouble( const std::string & tok, double & out ) {
	if ( tok.empty() )
		return false;
	const char * s = tok.c_str();
	char * end = NULL;
	double v = std::strtod( s, &end );
	if ( end == s )
		return false;
	for ( ; *end; ++end )
		if ( !isspace((unsigned char)*end) )
			return false;
	out = v;
	return true;
}

/**
 Port of tools/gurobi_cl/gurobi_cl.py:_parse_terms -- the exact term
 semantics the legacy shim applies to LP expression text:

 - split on '+'/'-' (variable names never contain them);
 - a token that parses as a finite number followed by another token is a
   coefficient * variable; otherwise it is a bare constant;
 - a non-finite (inf) coefficient means "no bound": the term is dropped,
   together with the variable token that follows it -- never clamped to a
   big-M (AGENTS.md invariant 3).
 \p droppedNonfinite counts the dropped inf tokens (meta information).
 */
static std::vector<Term> parseTerms( const std::string & text, long & droppedNonfinite ) {
	std::vector<std::string> toks;
	std::string cur;
	for ( size_t k = 0; k < text.size(); ++k ) {
		char c = text[k];
		if ( c == '+' || c == '-' ) {
			if ( !cur.empty() ) { toks.push_back(cur); cur.clear(); }
			toks.push_back( std::string( 1, c ) );
		} else if ( isspace((unsigned char)c) ) {
			if ( !cur.empty() ) { toks.push_back(cur); cur.clear(); }
		} else {
			cur += c;
		}
	}
	if ( !cur.empty() )
		toks.push_back( cur );

	std::vector<Term> terms;
	double sign = 1.0;
	size_t i = 0;
	while ( i < toks.size() ) {
		const std::string & t = toks[i];
		if ( t == "+" ) { sign = 1.0; ++i; continue; }
		if ( t == "-" ) { sign = -1.0; ++i; continue; }
		double coef;
		if ( !parseDouble( t, coef ) ) {
			terms.push_back( Term( sign, t ) );       // variable, implicit +1
			++i;
		} else if ( !std::isfinite(coef) ) {
			// drop the inf coefficient and the variable that follows it
			if ( i + 1 < toks.size() && toks[i+1] != "+" && toks[i+1] != "-" )
				i += 2;
			else
				i += 1;
			sign = 1.0;
			++droppedNonfinite;
			continue;
		} else if ( i + 1 < toks.size() && toks[i+1] != "+" && toks[i+1] != "-" ) {
			terms.push_back( Term( sign * coef, toks[i+1] ) );  // coef * var
			i += 2;
		} else {
			terms.push_back( Term( sign * coef, std::string() ) );  // constant
			i += 1;
		}
		sign = 1.0;
	}
	return terms;
}

/**
 Port of the shim's constraint split re.match(r"^(.*?)(<=|>=|=)(.*)$", body).
 \return 0 when no operator is present (the shim's regex only knows <=, >=
 and =, so such a body is dropped), 1 for "<=", 2 for ">=", 3 for "=";
 \p pos receives the operator start index.  A bare '<' or '>' is NOT an
 operator (never emitted by compaction.cpp anyway), but a later '=' in the
 same body still matches the regex, so scanning continues past it.
 */
static int findOperator( const std::string & body, size_t & pos ) {
	for ( size_t k = 0; k < body.size(); ++k ) {
		char c = body[k];
		if ( c == '=' ) { pos = k; return 3; }
		if ( c == '<' && k + 1 < body.size() && body[k+1] == '=' ) { pos = k; return 1; }
		if ( c == '>' && k + 1 < body.size() && body[k+1] == '=' ) { pos = k; return 2; }
	}
	return 0;
}

/**
 Port of tools/gurobi_cl/gurobi_cl.py:_read_cplex_lp, extended to keep the
 constraint names (the legacy reader discards them).  The line
 classification must stay byte-compatible with the Python reader so both
 see the same constraint list in the same order.
 */
static bool readLp( const std::string & path, LpModel & out, std::string & err ) {
	std::ifstream f( path.c_str() );
	if ( !f ) {
		err = "cannot open " + path;
		return false;
	}
	std::string line;
	std::string mode;
	while ( std::getline( f, line ) ) {
		std::string t = strip( line );
		if ( t.empty() )
			continue;
		std::string low = lower( t );
		if ( low == "minimize" || low == "maximize" ) {
			mode = "obj";
			out.maximise = ( low == "maximize" );
			continue;
		}
		if ( low == "subject to" || low == "st" || low == "s.t." || low == "such that" ) {
			mode = "cons"; continue;
		}
		if ( low == "generals" || low == "general" || low == "gen" || low == "integers" ) {
			mode = "int"; continue;
		}
		if ( low == "binary" || low == "binaries" || low == "bin" ) {
			mode = "bin"; continue;
		}
		if ( low == "semi-continuous" || low == "semi" || low == "semis" ) {
			mode = "semi"; continue;
		}
		if ( low == "end" )
			break;
		if ( low.compare( 0, 3, "sos" ) == 0 ) {
			mode = "sos"; continue;   // ignored, like the shim
		}
		if ( mode == "obj" ) {
			out.objText += " " + t;
		} else if ( mode == "cons" ) {
			RawConstraint rc;
			size_t colon = t.find( ':' );
			if ( colon != std::string::npos ) {
				rc.name = strip( t.substr( 0, colon ) );
				rc.body = strip( t.substr( colon + 1 ) );
			} else {
				rc.body = t;
			}
			// Python: body.strip().rstrip(";")
			while ( !rc.body.empty() && rc.body[rc.body.size()-1] == ';' )
				rc.body.erase( rc.body.size() - 1 );
			rc.body = strip( rc.body );
			out.cons.push_back( rc );
		} else if ( mode == "int" ) {
			std::istringstream s( t );
			std::string n;
			while ( s >> n ) out.intVars.push_back( n );
		} else if ( mode == "bin" ) {
			std::istringstream s( t );
			std::string n;
			while ( s >> n ) out.binVars.push_back( n );
		} else if ( mode == "semi" ) {
			std::istringstream s( t );
			std::string n;
			while ( s >> n ) out.semiVars.push_back( n );
		}
	}
	return true;
}

/** Format a finite double as a JSON number ('%.17g' round-trips exactly). */
static std::string num( double v ) {
	if ( v == 0.0 )
		v = v + 0.0;   // normalise -0
	char buf[48];
	std::snprintf( buf, sizeof(buf), "%.17g", v );
	return std::string( buf );
}

/** Minimal JSON string escaping for variable/constraint names. */
static std::string jstr( const std::string & s ) {
	std::string r = "\"";
	for ( size_t k = 0; k < s.size(); ++k ) {
		unsigned char c = (unsigned char)s[k];
		if ( c == '"' || c == '\\' ) {
			r += '\\'; r += (char)c;
		} else if ( c < 0x20 ) {
			char buf[8];
			std::snprintf( buf, sizeof(buf), "\\u%04x", c );
			r += buf;
		} else {
			r += (char)c;
		}
	}
	r += "\"";
	return r;
}

}  // namespace

void astranDumpModelJson( const std::string & lpPath ) {
	const char * dest = std::getenv( "ASTRAN_MODEL_DUMP" );
	if ( dest == NULL || *dest == '\0' )
		return;   // not requested: stock behaviour, do nothing

	try {
		LpModel m;
		std::string err;
		if ( !readLp( lpPath, m, err ) ) {
			std::cout << "-> modeldump: WARNING cannot dump model (" << err << ")" << std::endl;
			return;
		}

		long droppedNonfinite = 0;

		// Objective terms (constants dropped, like the shim's builder).
		std::vector<Term> objTerms = parseTerms( m.objText, droppedNonfinite );
		std::ostringstream objJson;
		bool firstTerm = true;
		for ( size_t k = 0; k < objTerms.size(); ++k ) {
			if ( objTerms[k].var.empty() )
				continue;
			if ( !firstTerm )
				objJson << ", ";
			objJson << "{\"var\": " << jstr(objTerms[k].var)
			        << ", \"coef\": " << num(objTerms[k].coef) << "}";
			firstTerm = false;
		}

		// Parse every constraint body once (split, terms, folded rhs).
		struct ParsedCon {
			RawConstraint raw;
			int op;                       // 0 = dropped (no operator)
			std::vector<Term> terms;      // lhs terms then negated rhs terms
			double rhs;
		};
		std::vector<ParsedCon> parsed;
		long droppedNoOperator = 0;
		for ( size_t k = 0; k < m.cons.size(); ++k ) {
			ParsedCon pc;
			pc.raw = m.cons[k];
			size_t pos = 0;
			pc.op = findOperator( pc.raw.body, pos );
			if ( pc.op == 0 ) {
				// no <=, >= or = in the body: the legacy builder drops it
				++droppedNoOperator;
				parsed.push_back( pc );
				continue;
			}
			std::string lhs = pc.raw.body.substr( 0, pos );
			std::string rhs = pc.raw.body.substr( pos + ( pc.op == 3 ? 1 : 2 ) );
			std::vector<Term> lt = parseTerms( lhs, droppedNonfinite );
			std::vector<Term> rt = parseTerms( rhs, droppedNonfinite );
			double lhsConst = 0.0, rhsConst = 0.0;
			for ( size_t j = 0; j < lt.size(); ++j ) {
				if ( lt[j].var.empty() ) { lhsConst += lt[j].coef; continue; }
				pc.terms.push_back( Term( lt[j].coef, lt[j].var ) );
			}
			for ( size_t j = 0; j < rt.size(); ++j ) {
				if ( rt[j].var.empty() ) { rhsConst += rt[j].coef; continue; }
				pc.terms.push_back( Term( -rt[j].coef, rt[j].var ) );
			}
			pc.rhs = rhsConst - lhsConst;   // shim: (rhs_const - lhs_const)
			parsed.push_back( pc );
		}

		// Variable list in the shim's creation order: Generals, Binary, Semi,
		// objective scan, then constraint scan (first occurrence wins).
		std::map<std::string, size_t> seen;   // name -> index in ordered list
		std::vector<std::string> ordered;
		std::map<std::string, int> kindOf;    // 0 continuous, 1 integer, 2 binary
		for ( size_t k = 0; k < m.intVars.size(); ++k )
			if ( seen.count(m.intVars[k]) == 0 ) {
				seen[m.intVars[k]] = ordered.size();
				ordered.push_back( m.intVars[k] );
				kindOf[m.intVars[k]] = 1;
			}
		for ( size_t k = 0; k < m.binVars.size(); ++k )
			if ( seen.count(m.binVars[k]) == 0 ) {
				seen[m.binVars[k]] = ordered.size();
				ordered.push_back( m.binVars[k] );
				kindOf[m.binVars[k]] = 2;
			}
		for ( size_t k = 0; k < m.semiVars.size(); ++k )
			if ( seen.count(m.semiVars[k]) == 0 ) {
				seen[m.semiVars[k]] = ordered.size();
				ordered.push_back( m.semiVars[k] );
				kindOf[m.semiVars[k]] = 0;   // shim declares semi vars continuous
			}
		for ( size_t k = 0; k < objTerms.size(); ++k )
			if ( !objTerms[k].var.empty() && seen.count(objTerms[k].var) == 0 ) {
				seen[objTerms[k].var] = ordered.size();
				ordered.push_back( objTerms[k].var );
				kindOf[objTerms[k].var] = 0;
			}
		for ( size_t k = 0; k < parsed.size(); ++k ) {
			if ( parsed[k].op == 0 )
				continue;   // dropped constraints create no variables
			for ( size_t j = 0; j < parsed[k].terms.size(); ++j ) {
				const std::string & n = parsed[k].terms[j].var;
				if ( seen.count(n) == 0 ) {
					seen[n] = ordered.size();
					ordered.push_back( n );
					kindOf[n] = 0;
				}
			}
		}

		// --- emit JSON ---
		std::ofstream o( dest );
		if ( !o ) {
			std::cout << "-> modeldump: WARNING cannot write " << dest << std::endl;
			return;
		}

		o << "{\n \"meta\": {\n";
		o << "  \"format_version\": 1,\n";
		o << "  \"generator\": \"astran-modeldump 1.0 (AutoCellLibX stage 1)\",\n";
		{
			// basename only: keep the dump independent of the run directory
			std::string base = lpPath;
			size_t slash = base.find_last_of( "/\\" );
			if ( slash != std::string::npos )
				base = base.substr( slash + 1 );
			o << "  \"source_lp\": " << jstr(base) << ",\n";
		}
		o << "  \"objective\": {\"sense\": " << jstr(m.maximise ? "max" : "min")
		  << ", \"terms\": [" << objJson.str() << "]},\n";
		o << "  \"dropped_no_operator\": " << droppedNoOperator << ",\n";
		o << "  \"dropped_nonfinite_terms\": " << droppedNonfinite << "\n";
		o << " },\n";

		o << " \"variables\": [\n";
		for ( size_t k = 0; k < ordered.size(); ++k ) {
			int kind = kindOf[ordered[k]];
			// bounds: CPLEX-LP defaults, as the shim's builder relies on them
			// (lb 0, ub +inf); Binary section vars are [0, 1].  "ub": null
			// means +inf -- only real bounds are emitted.
			const char * ubJson = ( kind == 2 ) ? "1" : "null";
			const char * intJson = ( kind >= 1 ) ? "true" : "false";
			o << "  {\"name\": " << jstr(ordered[k])
			  << ", \"lb\": 0, \"ub\": " << ubJson
			  << ", \"integer\": " << intJson << "}";
			if ( k + 1 < ordered.size() )
				o << ",";
			o << "\n";
		}
		o << " ],\n";

		o << " \"constraints\": [\n";
		bool firstCon = true;
		for ( size_t k = 0; k < parsed.size(); ++k ) {
			if ( parsed[k].op == 0 )
				continue;
			if ( !firstCon )
				o << ",\n";
			firstCon = false;
			const char * sense = ( parsed[k].op == 1 ) ? "<=" : ( parsed[k].op == 2 ) ? ">=" : "=";
			o << "  {\"name\": " << jstr(parsed[k].raw.name) << ", \"terms\": [";
			for ( size_t j = 0; j < parsed[k].terms.size(); ++j ) {
				if ( j )
					o << ", ";
				o << "{\"var\": " << jstr(parsed[k].terms[j].var)
				  << ", \"coef\": " << num(parsed[k].terms[j].coef) << "}";
			}
			o << "], \"sense\": " << jstr(sense)
			  << ", \"rhs\": " << num(parsed[k].rhs) << "}";
		}
		o << "\n ]\n}\n";
		o.flush();
		if ( !o ) {
			std::cout << "-> modeldump: WARNING failed writing " << dest << std::endl;
			return;
		}
		std::cout << "-> modeldump: wrote JSON model to " << dest << std::endl;
	} catch ( ... ) {
		// never let a dump problem break the compaction run
		std::cout << "-> modeldump: WARNING unexpected error while dumping model" << std::endl;
	}
}
