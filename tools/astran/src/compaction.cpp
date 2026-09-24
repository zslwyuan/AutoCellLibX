/**
 \file compaction.cpp
 Compact layout. 
 \date 25-sep-2006 \author Cristiano Lazzari <clazz@inf.ufrgs.br> 
 */

#include "compaction.h"

#include <cctype>
#include <algorithm>

/** Constructor. */
Compaction::Compaction( cp_algo a ,string name) {
	algo = a;
	lp_filename = name;
	variables.clear();
	constraints.clear();
}

/** Insert new variable. */
void Compaction::insertVal( string name ) {
	variables[name] = 0;  
	//  cout << "INS VAR " << name << endl;
}

/** Insert new constraint. */
void Compaction::insertConstraintBTZ( string v1 ) {
	
	cp_constraint cpc;
	
	cpc.v1 = variables.find( v1 );
	cpc.v2 = variables.end();
	cpc.t  = variables.end();
	
	if ( cpc.v1 == variables.end() ) {
		insertVal( v1 );
		cpc.v1 = variables.find( v1 );
	}
	
	cpc.type = CP_BIG_ZERO;
	
	constraints.push_back( cpc );
}

void Compaction::insertConstraint( string v1 ) {
    ctrts.push_back(v1);
}

/** Insert new constraint. */
void Compaction::insertConstraintEBTZ( string v1 ) {
	
	cp_constraint cpc;
	
	cpc.v1 = variables.find( v1 );
	cpc.v2 = variables.end();
	cpc.t  = variables.end();
	
	if ( cpc.v1 == variables.end() ) {
		insertVal( v1 );
		cpc.v1 = variables.find( v1 );
	}
	
	cpc.type = CP_BIG_EQ_ZERO;
	
	constraints.push_back( cpc );
}

/** Insert new constraint. */
void Compaction::insertConstraintEZ( string v1 ) {
	
	cp_constraint cpc;
	
	cpc.v1 = variables.find( v1 );
	cpc.v2 = variables.end();
	cpc.t  = variables.end();
	
	if ( cpc.v1 == variables.end() ) {
		insertVal( v1 );
		cpc.v1 = variables.find( v1 );
	}
	
	cpc.type = CP_EQ_ZERO;
	
	constraints.push_back( cpc );
}


/** Insert new constraint. */
void Compaction::insertConstraint( string v1, string v2, cp_cons_tp type, int val ) {
	
	cp_constraint cpc;
	
	cpc.v1 = variables.find( v1 );
	cpc.v2 = variables.find( v2 );
	cpc.t  = variables.end();
	
	if ( cpc.v1 == variables.end() ) {
		insertVal( v1 );
		//    variables[v1] = 0;  
		cpc.v1 = variables.find( v1 );
	}
	
	if ( cpc.v2 == variables.end() ) {
		insertVal( v2 );
		//    variables[v2] = 0;  
		cpc.v2 = variables.find( v2 );
	}
	
	cpc.type = type;
	cpc.val = val;    
	
	constraints.push_back( cpc );
	
}

/** Insert new constraint. */
void Compaction::insertConstraint( string v1, string v2, cp_cons_tp type, string t ) {
	
	cp_constraint cpc;
	
	cpc.v1 = variables.find( v1 );
	cpc.v2 = variables.find( v2 );
	cpc.t  = variables.find( t );
	
	if ( cpc.v1 == variables.end() ) {
		insertVal( v1 );
		cpc.v1 = variables.find( v1 );
	}
	
	if ( cpc.v2 == variables.end() ) {
		insertVal( v2 );
		cpc.v2 = variables.find( v2 );
	}
	if ( cpc.t == variables.end() ) {
		insertVal( t );
		cpc.t = variables.find( t );
	}
	
	if ( type == CP_EQ )
		cpc.type = CP_EQ_VAR;
	else if ( type == CP_MIN )
		cpc.type = CP_MIN_VAR;
	else if ( type == CP_MAX )
		cpc.type = CP_MAX_VAR;
	else
		cpc.type = type;
	
	constraints.push_back( cpc );  
}

/** Insert new constraint. */
void Compaction::insertConstraint( string v1, string v2, cp_cons_tp type, string t, int val ) {
	
	cp_constraint cpc;
	
	cpc.v1 = variables.find( v1 );
	cpc.v2 = variables.find( v2 );
	cpc.t  = variables.find( t );
	
	if ( cpc.v1 == variables.end() ) {
		insertVal( v1 );
		cpc.v1 = variables.find( v1 );
	}
	
	if ( cpc.v2 == variables.end() ) {
		insertVal( v2 );
		cpc.v2 = variables.find( v2 );
	}
	if ( cpc.t == variables.end() ) {
		insertVal( t );
		cpc.t = variables.find( t );
	}  
	
	if ( type == CP_EQ )
		cpc.type = CP_EQ_VAR_VAL;
	else if ( type == CP_MIN )
		cpc.type = CP_MIN_VAR_VAL;
	else if ( type == CP_MAX )
		cpc.type = CP_MAX_VAR_VAL;
	else
		cpc.type = type;
	
	cpc.val = val;
	
	constraints.push_back( cpc );  
}

/** Insert Upper Bound. */
void Compaction::insertUpperBound( string v1, int val ) {
	
	cp_constraint cpc;
    
	cpc.v1 = variables.find( v1 );
	cpc.v2 = variables.end();
	cpc.t  = variables.end();
	
	if ( cpc.v1 == variables.end() ) {
		insertVal( v1 );
		cpc.v1 = variables.find( v1 );
	}
	
	cpc.type = CP_UPPER_BOUND;
	cpc.val = val;
	
	constraints.push_back( cpc );
}

/** Insert Upper Bound. */
void Compaction::insertLowerBound( string v1, int val ) {
	
	cp_constraint cpc;
    
	cpc.v1 = variables.find( v1 );
	cpc.v2 = variables.end();
	cpc.t  = variables.end();
	
	if ( cpc.v1 == variables.end() ) {
		insertVal( v1 );
		cpc.v1 = variables.find( v1 );
	}
	
	cpc.type = CP_LOWER_BOUND;
	cpc.val = val;
	
	constraints.push_back( cpc );
}

/** Force these variavles to be integer. */
void Compaction::forceIntegerVar( string v ) {
	int_vars.push_back( v );
}

/** Force these variavles to be binary. */
void Compaction::forceBinaryVar( string v ) {
	bin_vars.push_back( v );
}

/** Force these variavles to be semi-continuous (0 or interval). */
void Compaction::forceSecVar( string v ) {
	sec_vars.push_back( v );
}

/** Force these variavles to be special ordered set. */
void Compaction::forceSOS( string v ) {
	sos_vars.push_back( v );
}


/** Insert LP variable. These variables are include in the minimization objective function. */
void Compaction::insertLPMinVar( string v ) {
	lp_min_var.push_back( v );
	lp_min_val.push_back( 1 );
}

/** Insert LP variable. These variables are include in the minimization objective function. */
void Compaction::insertLPMinVar( string v, int i ) {
	lp_min_var.push_back( v );
	lp_min_val.push_back( i );
}

/*
 int Compaction::solve(string lpSolverFile) {
 cout << "-> Calling LP Solver (" 
 << variables.size() << " variables, " 
 << constraints.size() << " constraints)" << endl;
 
 string fn = lp_filename + ".lp";
 ofstream f(fn.c_str());
 
 
 if ( !f ) {
 cerr << "ERROR:Cannot create file " << fn << ". Please verify your temporary directory." << endl;
 exit(-1);
 }
 
 f << "min: "; 
 for ( unsigned int i = 0; i < lp_min_var.size(); i++ ) {    
 if ( i != 0 )
 f << " + ";
 if ( lp_min_val[i] != 1 )
 f << lp_min_val[i] << " ";
 
 f << lp_min_var[i];
 }
 f << ";" << endl;
 
 // Constant zero
 variables[ "ZERO" ] = 0;
 f << "Czero: ZERO = 0;" << endl;
 
 for ( unsigned int i = 0; i < constraints.size(); i++ ) {
 
 string v1 = constraints[i].v1->first;
 
 string v2  = "0";
 if ( constraints[i].v2 != variables.end() )
 v2 = constraints[i].v2->first;
 
 string t  = "0";
 if ( constraints[i].t != variables.end() )
 t = constraints[i].t->first;
 
 cp_cons_tp type = constraints[i].type;
 
 int val = constraints[i].val;
 
 if ( type == CP_MIN )
 f << "C" << i << ": " << v2 << " - " << v1 << " >= " << val << ";" << endl;
 if ( type == CP_MAX )
 f << "C" << i << ": " << v2 << " - " << v1 << " <= " << val << ";" << endl;
 else if ( type == CP_EQ )
 f << "C" << i << ": " << v2 << " - " << v1 << " = " << val << ";" << endl;
 else if ( type == CP_MIN_VAR_VAL )
 f << "C" << i << ": " << v2 << " - " << v1 << " >= " << val << " " << t << ";" << endl;
 else if ( type == CP_MAX_VAR_VAL )
 f << "C" << i << ": " << v2 << " - " << v1 << " <= " << val << " " << t << ";" << endl;
 else if ( type == CP_EQ_VAR_VAL )
 f << "C" << i << ": " << v2 << " - " << v1 << " = " << val << " " << t << ";" << endl;
 else if ( type == CP_MIN_VAR )
 f << "C" << i << ": " << v2 << " - " << v1 << " >= " << t << ";" << endl;
 else if ( type == CP_MAX_VAR )
 f << "C" << i << ": " << v2 << " - " << v1 << " <= " << t << ";" << endl;
 else if ( type == CP_EQ_VAR )
 f << "C" << i << ": " << v2 << " - " << v1 << " = " << t << ";" << endl;
 else if ( type == CP_BIG_ZERO )
 f << "C" << i << ": " << v1 << " > 0;" << endl;
 else if ( type == CP_BIG_EQ_ZERO )
 f << "C" << i << ": " << v1 << " >= 0;" << endl;
 else if ( type == CP_EQ_ZERO )
 f << "C" << i << ": " << v1 << " = 0;" << endl;
 else if ( type == CP_UPPER_BOUND )
 f << "C" << i << ": " << v1 << " <= " << val << ";" << endl;
 else if ( type == CP_LOWER_BOUND )
 f << "C" << i << ": " << v1 << " >= " << val << ";" << endl;
 
 }
 
 if ( int_vars.size() > 0 ) {  
 f << "int "; 
 for ( unsigned int i = 0; i < int_vars.size(); i++ ) {
 if ( i != 0 )
 f << ", ";
 f << int_vars[i];
 }
 f << ";" << endl;
 }
 
 if ( bin_vars.size() > 0 ) {  
 f << "bin "; 
 for ( unsigned int i = 0; i < bin_vars.size(); i++ ) {
 if ( i != 0 )
 f << ", ";
 f << bin_vars[i];
 }
 f << ";" << endl;
 }
 
 if ( sec_vars.size() > 0 ) {  
 f << "sec "; 
 for ( unsigned int i = 0; i < sec_vars.size(); i++ ) {
 if ( i != 0 )
 f << ", ";
 f << sec_vars[i];
 }
 f << ";" << endl;
 }
 
 if ( sos_vars.size() > 0 ) {  
 f << "sos" << endl; 
 for ( unsigned int i = 0; i < sos_vars.size(); i++ )
 f << "SOS" << i << ": " << sos_vars[i] << " <= 1;" << endl;
 }
 
 
 f.close();
 string cmd = "\"" + lpSolverFile + "\" " + 	lp_filename + ".lp 2> temp.log";
 cout << "-> Running command: " << cmd << endl;
 
 FILE *x = _popen(cmd.c_str(), "r");
 
 if(x==NULL){
 cout << "-> ERROR: Problem to execute lp_solve!" << endl;
 return 0;
 }
 
 char str[150];
 while (fgets(str, 150, x)) {
 
 istringstream s(str);
 
 string n;
 int v;
 
 s >> n;
 if(n=="This"){
 cout << "-> Error executing LP Solver: " << str << endl;
 return 0;
 }
 s >> v;
 
 
 map<string,int>::iterator i = variables.find( n );
 if ( i != variables.end() ) {
 i->second = v;
 }
 }
 
 _pclose(x);
 return 1;
 }
 */

/** Solve Compaction constraints with linear programming. */
int Compaction::solve(string lpSolverFile, int timeLimit) {
	cout << "-> Calling LP Solver (" 
	<< variables.size() << " variables, " 
	<< constraints.size() << " constraints)" << endl;
	
	string fn = lp_filename + ".lp";
	
	// Some variables are stored under names that are not plain identifiers,
	// e.g. "x0b + RELAXATION" or "b0_17_1 + b0_17_2 + b0_17_3".  Gurobi's LP
	// parser accepts such names as single variables, but open-source parsers
	// (COIN-CBC/CoinLpIO, GLPK, ...) treat the embedded '+'/'-' as operators
	// and produce a different (wrong) model.  Rename them to plain names when
	// writing the LP file and translate the solution back on read.
	map<string,string> renameMap;
	{
	    int renameIdx = 0;
	    auto needRename = [](const string& s){
	        for (size_t k = 0; k < s.size(); ++k)
	            if (!(isalnum((unsigned char)s[k]) || s[k] == '_'))
	                return true;
	        return false;
	    };
	    vector<string> allNames = lp_min_var;
	    for (map<string,int>::iterator it = variables.begin(); it != variables.end(); ++it)
	        allNames.push_back(it->first);
	    for (size_t k = 0; k < int_vars.size(); ++k)  allNames.push_back(int_vars[k]);
	    for (size_t k = 0; k < bin_vars.size(); ++k)  allNames.push_back(bin_vars[k]);
	    for (size_t k = 0; k < sec_vars.size(); ++k)  allNames.push_back(sec_vars[k]);
	    for (size_t k = 0; k < sos_vars.size(); ++k)  allNames.push_back(sos_vars[k]);
	    for (size_t k = 0; k < allNames.size(); ++k)
	        if (needRename(allNames[k]) && renameMap.count(allNames[k]) == 0)
	            renameMap[allNames[k]] = "astranVar" + to_string(renameIdx++);
	}
	vector<pair<string,string> > renameOrdered(renameMap.begin(), renameMap.end());
	sort(renameOrdered.begin(), renameOrdered.end(),
	     [](const pair<string,string>& a, const pair<string,string>& b){
	         return a.first.size() > b.first.size();
	     });
	auto S = [&renameOrdered](string s) -> string {
	    for (size_t k = 0; k < renameOrdered.size(); ++k) {
	        const string& from = renameOrdered[k].first;
	        const string& to   = renameOrdered[k].second;
	        size_t p = 0;
	        while ((p = s.find(from, p)) != string::npos) {
	            s.replace(p, from.size(), to);
	            p += to.size();
	        }
	    }
	    return s;
	};
    {
        ofstream f(fn.c_str());
        
        if ( !f )
            throw AstranError("Cannot create file " + fn);
        
        f << "Minimize" << endl; 
        // Gurobi tolerates duplicated variables in the objective, CoinLpIO
        // (COIN-CBC) does not; merge duplicates by summing their coefficients.
        vector<string> mergedMinVar;
        vector<int> mergedMinVal;
        {
            map<string,int> merged;
            for (size_t i = 0; i < lp_min_var.size(); ++i)
                merged[lp_min_var[i]] += lp_min_val[i];
            for (map<string,int>::iterator it = merged.begin(); it != merged.end(); ++it) {
                mergedMinVar.push_back(it->first);
                mergedMinVal.push_back(it->second);
            }
        }
        for ( unsigned int i = 0; i < mergedMinVar.size(); i++ ) {    
            if ( i != 0 ){
                if(mergedMinVal[i]>=0)
                    f << " + ";
                else
                    f << " - ";                
            }
            if ( mergedMinVal[i] != 1 )
                f << abs(mergedMinVal[i]) << " ";
            
            f << S(mergedMinVar[i]);
        }
        f << endl;
        
        f << "Subject To" << endl; 
        
        // Constant zero
        variables[ "ZERO" ] = 0;
        f << "Czero: ZERO = 0;" << endl;
        unsigned int i;
        for (i = 0; i < constraints.size(); i++ ) {
            
            string v1 = constraints[i].v1->first;
            
            string v2  = "0";
            if ( constraints[i].v2 != variables.end() )
                v2 = constraints[i].v2->first;
            
            string t  = "0";
            if ( constraints[i].t != variables.end() )
                t = constraints[i].t->first;
            
            cp_cons_tp type = constraints[i].type;
            
            int val = constraints[i].val;
            
            if ( type == CP_MIN )
                f << "C" << i << ": " << S(v2) << " - " << S(v1) << " >= " << val << endl;
            if ( type == CP_MAX )
                f << "C" << i << ": " << S(v2) << " - " << S(v1) << " <= " << val << endl;
            else if ( type == CP_EQ)
                f << "C" << i << ": " << S(v2) << " - " << S(v1) << " = " << val << endl;
            else if ( type == CP_MIN_VAR_VAL )
                f << "C" << i << ": " << S(v2) << " - " << val << " " << S(t) << " - " << S(v1) << " >= 0" << endl;
            else if ( type == CP_MAX_VAR_VAL )
                f << "C" << i << ": " << S(v2) << " - " << val << " " << S(t) << " - " << S(v1) << " <= 0" << endl;
            else if ( type == CP_EQ_VAR_VAL )
                f << "C" << i << ": " << S(v2) << " - " << val << " " << S(t) << " - " << S(v1) << " = 0" << endl;
            else if ( type == CP_MIN_VAR )
                f << "C" << i << ": " << S(v2) << " - " << S(v1) << " - " << S(t) << " >= 0" << endl;
            else if ( type == CP_MAX_VAR )
                f << "C" << i << ": " << S(v2) << " - " << S(v1) << " - " << S(t) << " <= 0" << endl;
            else if ( type == CP_EQ_VAR )
                f << "C" << i << ": " << S(v2) << " - " << S(v1) << " - " << S(t) << " = 0" << endl;
            else if ( type == CP_BIG_ZERO )
                f << "C" << i << ": " << S(v1) << " > 0" << endl;
            else if ( type == CP_BIG_EQ_ZERO )
                f << "C" << i << ": " << S(v1) << " >= 0" << endl;
            else if ( type == CP_EQ_ZERO )
                f << "C" << i << ": " << S(v1) << " = 0" << endl;
            else if ( type == CP_UPPER_BOUND )
                f << "C" << i << ": " << S(v1) << " <= " << val << endl;
            else if ( type == CP_LOWER_BOUND )
                f << "C" << i << ": " << S(v1) << " >= " << val << endl;
            
        }
        for ( unsigned int j = 0; j < ctrts.size(); j++ ) {
            f << "C" << i+j << ": " << S(ctrts[j]) << endl;
        }
        
        if ( int_vars.size() > 0 ) {  
            f << "Generals" << endl; 
            for (map<string,int>::iterator it = variables.begin();it != variables.end(); ++it){
                if ( it != variables.begin() )
                    f << " ";
                f << S(it->first);
            }
            f << endl;
        }
        
        if ( bin_vars.size() > 0 ) {  
            f << "Binary" << endl; 
            for ( unsigned int i = 0; i < bin_vars.size(); i++ ) {
                if ( i != 0 )
                    f << " ";
                f << S(bin_vars[i]);
            }
            f << endl;
        }
        
        if ( sec_vars.size() > 0 ) {  
            f << "Semi" << endl;
            for ( unsigned int i = 0; i < sec_vars.size(); i++ ) {
                if ( i != 0 )
                    f << " ";
                f << S(sec_vars[i]);
            }
            f << endl;
        }
        
        if ( sos_vars.size() > 0 ) {  
            f << "sos" << endl; 
            for ( unsigned int i = 0; i < sos_vars.size(); i++ )
                f << "SOS" << i << ": " << S(sos_vars[i]) << " <= 1" << endl;
        }
        
        f.flush();
        f.close();
    }
    
    string solFileName = lp_filename + ".sol";
    
    remove(solFileName.c_str());
    
    string cmd = "\"" + lpSolverFile + "\" TimeLimit=" + to_string(timeLimit) + " ResultFile=" + solFileName + " " + lp_filename + ".lp";

	cout << "-> Running command: " << cmd << endl;
	
	FILE *x = _popen(cmd.c_str(), "r");
	
	if(x==NULL)
		throw AstranError("Problem executing: " + cmd);
    
    cout << "-> To interrupt earlier and get the current best solution, type in a terminal: kill -2 [gurobi process]" << endl;
    cout << "-> * and H means new feasible solution found:";
    cerr << " ";
    
	char line[150];
	while (fgets(line, 150, x)) {
		istringstream s(line);
		string n;		
		s >> n;
        if(n!="Warning:")
            printf("%s",line);

        if(n=="H" || n=="*")
			cerr << n;
        
		if(n=="ERROR" || n=="Time" || n=="Unable" || n=="Wrote" || n=="Optimal" || n=="Model")
			cout << endl << line;
        if(n=="Unable" || n=="Model")
            return 0;
    }
    
    _pclose(x);
    
    FILE* stream = fopen(solFileName.c_str(), "r");
    
	if(stream==NULL)
		throw AstranError("Problem opening: " + solFileName);
    
	while (fgets(line, 150, stream)) {
		
		istringstream s(line);
		
		string n;
        double tmp;
		int v;
		
		s >> n;
        if(n=="#") continue;
        
		s >> tmp;
		v = round(tmp);
		
		// translate renamed (sanitized) variable names back to the original names
		if (n.rfind("astranVar", 0) == 0) {
			for (size_t k = 0; k < renameOrdered.size(); ++k) {
				if (renameOrdered[k].second == n) {
					n = renameOrdered[k].first;
					break;
				}
			}
		}
		
		map<string,int>::iterator i = variables.find( n );
		if ( i != variables.end() ) {
			i->second = v;
		}
	}
    fclose(stream);
    
    return 1;
}


/** Get variables values. */
int Compaction::getVariableVal( string name ) {
	map<string,int>::iterator i = variables.find( name );
	if ( i != variables.end() ) 
		return i->second;
	return -1;  
}