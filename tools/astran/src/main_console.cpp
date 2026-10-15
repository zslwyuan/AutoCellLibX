//---------------------------------------------------------------------------
//
// Name:        main_console.cpp
// Purpose:     Console-only entry point for ASTRAN (wxWidgets GUI removed).
//              Replicates the shell-mode path of the original icpdApp.cpp:
//              same --shell flag spelling, same command sequence, same stdout
//              content, so logs and exported layouts are byte-identical.
//
//---------------------------------------------------------------------------

#include <clocale>
#include <cstdlib>
#include <iostream>
#include <fstream>
#include <string>

#include "designmng.h"

using namespace std;

static void printUsage(ostream& out) {
    out << "Usage: Astran --shell <script-file>" << endl;
    out << "       Astran --shell                (interactive shell on stdin)" << endl;
    out << "Runs the ASTRAN shell-mode script and exits on the EXIT command." << endl;
}

int main(int argc, char** argv) {
    setlocale(LC_ALL, "C");

    // Same command line contract as the original wxCmdLineParser usage:
    // "--shell" (or "-s") is a switch, followed by one optional positional
    // FILENAME parameter (the script to execute).
    bool shellMode = false;
    string cmdFilename;
    for (int i = 1; i < argc; ++i) {
        string arg = argv[i];
        if (arg == "--shell" || arg == "-s") {
            shellMode = true;
        } else if (cmdFilename.empty()) {
            cmdFilename = arg;
        } else {
            cerr << "ERROR: Unexpected parameter '" << arg << "'" << endl;
            printUsage(cerr);
            return 1;
        }
    }

    if (!shellMode) {
        cerr << "ERROR: Missing --shell flag (no GUI in this build)." << endl;
        printUsage(cerr);
        return 1;
    }

    // Original: ifstream checked before anything else; a named script that
    // does not exist is an error (reported on stdout, as before).
    ifstream ifile(cmdFilename.c_str());
    if ((!ifile) && (!cmdFilename.empty())) {
        cout << "ERROR: File '" << cmdFilename << "' doesn't exist" << endl;
        return 1;
    }

    DesignMng designmng;
    string cmd;

    // By default load astran.cfg from $ASTRAN_PATH/bin, exactly like the
    // original (no-op when ASTRAN_PATH is unset or the file is absent).
    string astran_path;
    const char* env_path = getenv("ASTRAN_PATH");
    if (env_path)
        astran_path = env_path;
    string astran_cfg = astran_path + "/bin/astran.cfg";

    ifstream afile(astran_cfg.c_str());
    if (afile) {
        cmd = string("read ") + astran_cfg;
        cout << "astran> " << cmd << endl;
        designmng.readCommand(cmd);
    }

    // Read astran_script
    if (ifile) {
        cmd = string("read ") + cmdFilename;
        cout << "astran> " << cmd << endl;
        designmng.readCommand(cmd);
    }

    // Interactive shell.  The script's EXIT command terminates the process;
    // EOF on stdin also ends the loop (the original spun forever here).
    while (true) {
        cout << "astran> ";
        if (!getline(cin, cmd))
            break;
        designmng.readCommand(cmd);
    }

    return EXIT_SUCCESS;
}
