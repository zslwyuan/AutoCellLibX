"""Preflight linter for ASTRAN-bound SPICE netlists.

ASTRAN's SPICE reader (tools/astran/src/spice.h) is far stricter and
quirker than a typical simulator parser, and every violation costs a full
layout run to discover (the load aborts, ``cellgen select`` then reports
"Cell not found").  This linter re-implements the parser's acceptance
rules so a malformed deck fails in milliseconds instead:

* transistor lines are recognised ONLY by a leading 'M' (anything else --
  e.g. an instance prefix "g0#M0" -- is either skipped or aborts the load);
* names starting with 'C' or 'D' are silently *skipped* as capacitor/diode
  cards, and 'X' lines become subcircuit instances -- so a transistor named
  that way vanishes from the netlist;
* the model token must be literally PMOS/CMOSP/MODP/PMOS_VTL or
  NMOS/CMOSN/MODN/NMOS_VTL;
* W/L values go through atof(): "L={LCH}" parses to 0 (folding then
  divides by it); only AD/PD/AS/PS/NRD/NRS/M extra parameters survive;
* '+' continuation lines are skipped wholesale, so W/L must live on the
  M line itself;
* '.END'/'.MODEL' stop the whole file read; nested .SUBCKT is rejected;
* ASTRAN defaults to vddNet=VCC / gndNet=GND -- decks using VDD/VSS need a
  rename or "set vddnet/gndnet" in the run script.

Usage as a library:  ``issues = lint_netlist(path)``
Usage as a CLI:      ``python astran_lint.py file.sp [more.sp]``  (exit 1
on any error-severity issue).
"""

import os
import re
import sys
from dataclasses import dataclass

MODELS_P = {"PMOS", "CMOSP", "MODP", "PMOS_VTL"}
MODELS_N = {"NMOS", "CMOSN", "MODN", "NMOS_VTL"}
MODELS = MODELS_P | MODELS_N
ALLOWED_PARAMS = {"L", "W", "AD", "PD", "AS", "PS", "NRD", "NRS", "M"}

# Above this many transistors a single cell is beyond the project's proven
# ASTRAN range (largest shipped cell: 36T) -- runs get slow and risky.
DEFAULT_WARN_TRANSISTORS = 40

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    severity: str
    line: int          # 1-based; 0 = file-level
    message: str

    def __str__(self):
        loc = "line %d" % self.line if self.line else "file"
        return "%s: %s: %s" % (self.severity, loc, self.message)


def _parse_float_prefix(token):
    """atof semantics: leading numeric prefix, None when there isn't one."""
    match = re.match(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", token)
    return float(match.group(0)) if match else None


def lint_text(text, source="netlist", warn_transistors=DEFAULT_WARN_TRANSISTORS):
    """Lint one SPICE deck; returns a list of Issue (errors and warnings)."""
    issues = []
    lines = text.splitlines()

    in_subckt = False
    saw_stop = False
    names_in_subckt = set()
    transistors = 0
    cell_sizes = {}            # subckt name -> transistor count
    cur_cell = None
    supply_vcc = False
    supply_gnd = False
    subckt_count = 0

    for idx, raw in enumerate(lines, start=1):
        words = raw.split()
        if not words:
            continue
        first = words[0]
        head = first[0].upper()
        upper0 = first.upper()

        if saw_stop:
            issues.append(Issue(WARNING, idx,
                                "content after .END/.MODEL is never read "
                                "by ASTRAN (the file stops there)"))
            break

        if upper0 == ".GLOBAL":
            continue
        if head == "*":
            continue
        if head == "+":
            joined = raw.upper()
            if ("W=" in joined) or ("L=" in joined):
                issues.append(Issue(
                    ERROR, idx,
                    "'+' continuation lines are skipped entirely by "
                    "ASTRAN -- W/L must be on the M line itself"))
            continue
        if head in ("C", "D"):
            # capacitor/diode card: silently skipped by ASTRAN.  Flag only
            # the plausible-mistake shape (>= 6 tokens and a model token).
            if len(words) >= 6 and words[5].upper() in MODELS:
                issues.append(Issue(
                    ERROR, idx,
                    "device %r starts with '%s' and is silently SKIPPED "
                    "by ASTRAN's parser -- rename it to start with 'M'"
                    % (first, head)))
            continue
        if upper0 in (".MODEL", ".END"):
            saw_stop = True
            continue
        if upper0 == ".SUBCKT":
            if in_subckt:
                issues.append(Issue(ERROR, idx,
                                    "nested .SUBCKT is rejected by ASTRAN"))
            elif len(words) < 2:
                issues.append(Issue(ERROR, idx, ".SUBCKT without a name"))
            else:
                in_subckt = True
                subckt_count += 1
                names_in_subckt = set()
                cur_cell = words[1].upper()
                cell_sizes[cur_cell] = 0
            continue
        if upper0 == ".INCLUDE":
            issues.append(Issue(WARNING, idx,
                                ".INCLUDE is resolved relative to the ASTRAN "
                                "process working directory -- prefer a "
                                "single self-contained file"))
            continue
        if upper0 == ".ENDS":
            in_subckt = False
            continue
        if head == "X":
            issues.append(Issue(
                WARNING, idx,
                "instance line %r -- ASTRAN will look up the referenced "
                "subckt; a transistor accidentally named X... becomes an "
                "instance" % first))
            continue

        if head == "M":
            if len(words) < 6:
                issues.append(Issue(
                    ERROR, idx,
                    "transistor line has %d tokens; ASTRAN needs at least "
                    "M<name> D G S B MODEL (6)" % len(words)))
                continue
            if first in names_in_subckt:
                issues.append(Issue(ERROR, idx,
                                    "duplicate transistor name %r in this "
                                    "subckt" % first))
            names_in_subckt.add(first)
            transistors += 1
            if cur_cell is not None:
                cell_sizes[cur_cell] = cell_sizes.get(cur_cell, 0) + 1

            model = words[5].upper()
            if model not in MODELS:
                issues.append(Issue(
                    ERROR, idx,
                    "model %r is not accepted by ASTRAN (use PMOS or NMOS)"
                    % words[5]))

            params = {}
            for token in words[6:]:
                if "=" not in token:
                    issues.append(Issue(
                        ERROR, idx,
                        "parameter %r is not NAME=VALUE; ASTRAN rejects the "
                        "line" % token))
                    continue
                pname, _, pvalue = token.partition("=")
                pname = pname.upper()
                if pname not in ALLOWED_PARAMS:
                    issues.append(Issue(
                        ERROR, idx,
                        "parameter %r is not supported by ASTRAN (allowed: "
                        "%s)" % (pname, "/".join(sorted(ALLOWED_PARAMS)))))
                elif pname in ("L", "W"):
                    value = _parse_float_prefix(pvalue)
                    if value is None:
                        issues.append(Issue(
                            ERROR, idx,
                            "%s=%r parses to no number (atof gives 0) -- "
                            "substitute real values, e.g. %s=0.05u"
                            % (pname, pvalue, pname)))
                    elif value <= 0:
                        issues.append(Issue(
                            ERROR, idx,
                            "%s=%r is not positive" % (pname, pvalue)))
                    else:
                        params[pname] = value
            if "L" not in params or "W" not in params:
                issues.append(Issue(
                    ERROR, idx,
                    "transistor %s lacks a valid L= or W= on the M line"
                    % first))

            for net in words[1:5]:
                supply_vcc = supply_vcc or net.upper() == "VCC"
                supply_gnd = supply_gnd or net.upper() == "GND"
            continue

        # Anything else makes the parser throw "Errot in line N" and abort
        # the whole netlist load.
        issues.append(Issue(
            ERROR, idx,
            "unrecognised line -- ASTRAN aborts the netlist load here "
            "(only M/*/+/.SUBCKT/.ENDS/.INCLUDE/.GLOBAL are understood)"))

    if in_subckt:
        issues.append(Issue(ERROR, 0, "last .SUBCKT is never closed (.ENDS)"))
    if subckt_count == 0:
        issues.append(Issue(ERROR, 0, "no .SUBCKT found -- nothing for "
                                      "'cellgen select' to pick"))
    if transistors == 0 and subckt_count > 0:
        issues.append(Issue(ERROR, 0, "no transistors parsed"))
    for cell_name, size in cell_sizes.items():
        if size > warn_transistors:
            issues.append(Issue(
                WARNING, 0,
                "cell %s has %d transistors -- beyond the proven range "
                "(largest shipped: 36T); expect long placement/compaction"
                % (cell_name, size)))
    if transistors and not supply_vcc:
        issues.append(Issue(
            WARNING, 0,
            "no VCC net found -- ASTRAN defaults vddNet=VCC; rename or add "
            "'set vddnet <name>' to the run script"))
    if transistors and not supply_gnd:
        issues.append(Issue(
            WARNING, 0,
            "no GND net found -- ASTRAN defaults gndNet=GND; rename or add "
            "'set gndnet <name>' to the run script"))
    return issues


def lint_netlist(path, warn_transistors=DEFAULT_WARN_TRANSISTORS):
    with open(path, "r", errors="replace") as fh:
        return lint_text(fh.read(), source=os.path.basename(path),
                         warn_transistors=warn_transistors)


def errors(issues):
    return [i for i in issues if i.severity == ERROR]


def format_issues(issues, source="netlist"):
    if not issues:
        return "%s: OK (no issues)" % source
    return "\n".join("%s: %s" % (source, i) for i in issues)


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("netlists", nargs="+", help=".sp files to check")
    parser.add_argument("--max-transistors", type=int,
                        default=DEFAULT_WARN_TRANSISTORS,
                        help="warn above this many transistors per file")
    args = parser.parse_args(argv)

    rc = 0
    for path in args.netlists:
        issues = lint_netlist(path, warn_transistors=args.max_transistors)
        print(format_issues(issues, source=path))
        if errors(issues):
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
