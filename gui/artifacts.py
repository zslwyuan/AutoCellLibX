"""Readers for everything the flow leaves on disk.  Qt-free (unit-tested).

The documents parsed here are the flow's *contract* with the outside world
(see ``doc/ALGORITHM_DESIGN.md`` §5), so the parsers are deliberately tolerant
of extra whitespace and of files that are still being written: the live run
view re-reads a log while ASTRAN is appending to it.
"""
import ast
import os
import re

_CELL_RE = re.compile(r"^COMPLEX(\d+)$")

# Progress markers in .Astranlog, in execution order, with a rough fraction of
# the per-attempt work each one implies.  Used both for the live progress bar
# and to label "what is ASTRAN doing right now".
PHASES = [
    ("Loading technology", 0.01),
    ("Loading netlist", 0.02),
    ("Selecting cell", 0.03),
    ("Calculating cell area", 0.05),
    ("Applying folding", 0.08),
    ("Placing transistors", 0.45),
    ("Routing cell", 0.70),
    ("Optimizing routing graph", 0.80),
    ("Compacting layout", 0.90),
    ("Calling LP Solver", 0.92),
    ("Writing GDS", 0.99),
]

_PHASE_MARKERS = [
    ("> Loading technology from file:", "Loading technology"),
    ("> Loading cells netlist from file:", "Loading netlist"),
    ("> Selecting cell netlist:", "Selecting cell"),
    ("> Calculating cell area...", "Calculating cell area"),
    ("> Applying folding...", "Applying folding"),
    ("> Placing transistors...", "Placing transistors"),
    ("> Routing cell...", "Routing cell"),
    ("> Optimizing routing graph...", "Optimizing routing graph"),
    ("> Compacting layout...", "Compacting layout"),
    ("> Calling LP Solver", "Calling LP Solver"),
    ("-> Cell Size (W x H):", "Writing GDS"),
]


def cell_sort_key(name):
    """COMPLEX10 sorts after COMPLEX9 (numeric, not lexicographic)."""
    m = _CELL_RE.match(name or "")
    return (0, int(m.group(1))) if m else (1, name or "")


# ---------------------------------------------------------------- ASTRAN log
class AstranLog(object):
    """State parsed out of one ``<cell>.Astranlog``.

    ``complete`` means the log ends with a usable ``Cell Size`` line; a log
    without one is either still running or a failure (width 0 => 0 x 0 cell,
    AGENTS.md pitfall "a failed solve is silent").
    """

    def __init__(self, path=""):
        self.path = path
        self.exists = False
        self.complete = False
        self.width_um = None
        self.height_um = None
        self.n_transistors = None
        self.n_pmos = None
        self.n_nmos = None
        self.n_before_folding = None
        self.pmos_before = None
        self.nmos_before = None
        self.attempts = []            # [(tracks, conservative), ...]
        self.solver_vars = None
        self.solver_cons = None
        self.solver_status = None
        self.solver_objective = None
        self.option3_retry = False
        self.option3_retries = 0
        self.spacing_repairs = []     # final violating-pair count per repair pass
        self.last_phase = ""
        self.last_phase_index = -1
        self.phase_hits = {}
        self.lines = 0
        self.errors = []
        self.elapsed_s = None

    @property
    def phase_fraction(self):
        """0..1 within the current (tracks, conservative) attempt."""
        if self.last_phase_index < 0:
            return 0.0
        return PHASES[self.last_phase_index][1]

    @property
    def attempt_index(self):
        return max(0, len(self.attempts) - 1)

    @property
    def failed(self):
        """A finished log with no usable width (0 x 0 cell)."""
        return self.exists and not self.complete

    @property
    def status(self):
        if not self.exists:
            return "missing"
        if not self.complete:
            return "running" if self.lines else "empty"
        if self.width_um and self.width_um > 0:
            return "ok"
        return "zero-width"


def parse_astran_log(path, tail_bytes=None):
    """Parse an ASTRAN log.  ``tail_bytes`` limits the read (live tailing)."""
    log = AstranLog(path)
    if not os.path.exists(path):
        return log
    log.exists = True
    try:
        if tail_bytes:
            size = os.path.getsize(path)
            with open(path, "r", errors="replace") as fh:
                if size > tail_bytes:
                    fh.seek(size - tail_bytes)
                    fh.readline()          # drop the partial first line
                data = fh.read()
            lines = data.splitlines()
        else:
            with open(path, "r", errors="replace") as fh:
                lines = fh.read().splitlines()
    except OSError:
        return log

    for line in lines:
        log.lines += 1
        stripped = line.strip()

        if "-> Trying with" in line:
            m = re.search(r"Trying with (\d+) tracks and conservative = (\d+)", line)
            if m:
                log.attempts.append((int(m.group(1)), int(m.group(2))))
        elif "Number of transistors before folding:" in line:
            m = re.search(r"folding: (\d+) -> P\((\d+)\) N\((\d+)\)", line)
            if m:
                log.n_before_folding, log.pmos_before, log.nmos_before = (
                    int(m.group(1)), int(m.group(2)), int(m.group(3)))
        elif "Number of transistors after folding:" in line:
            m = re.search(r"folding: (\d+) -> P\((\d+)\) N\((\d+)\)", line)
            if m:
                log.n_transistors, log.n_pmos, log.n_nmos = (
                    int(m.group(1)), int(m.group(2)), int(m.group(3)))
        elif "Cell Size (W x H):" in line:
            try:
                wh = line.split("Cell Size (W x H):")[1].strip().split("x")
                log.width_um = float(wh[0].strip())
                log.height_um = float(wh[1].strip())
                log.complete = True
            except (IndexError, ValueError):
                pass
        elif "Calling LP Solver" in line:
            m = re.search(r"\((\d+) variables, (\d+) constraints\)", line)
            if m:
                log.solver_vars, log.solver_cons = int(m.group(1)), int(m.group(2))
        elif "Solver status" in line:
            m = re.search(r"Solver status (\S+)", line)
            if m:
                log.solver_status = m.group(1).rstrip(",")
            m = re.search(r"objective ([\d.eE+-]+)", line)
            if m:
                try:
                    log.solver_objective = float(m.group(1))
                except ValueError:
                    pass
        elif "retrying without the option-3 spacing disjuncts" in line:
            log.option3_retry = True
            log.option3_retries += 1
        elif "Spacing repair pass" in line:
            m = re.search(r"Spacing repair pass \d+: (\d+) violating", line)
            if m:
                log.spacing_repairs.append(int(m.group(1)))
        elif "Runtime = " in line:
            m = re.search(r"Runtime = ([\d.]+) s", line)
            if m:
                log.elapsed_s = float(m.group(1))

        if not log.complete:
            for idx, (marker, name) in enumerate(_PHASE_MARKERS):
                if marker in line:
                    log.last_phase = name
                    log.last_phase_index = idx
                    log.phase_hits[name] = log.phase_hits.get(name, 0) + 1

        low = stripped.lower()
        if "error" in low or "infeasible" in low or "no solution" in low:
            if stripped not in log.errors:
                log.errors.append(stripped)
    return log


# ------------------------------------------------------------- .sp netlists
class SpiceNetlist(object):
    def __init__(self, path=""):
        self.path = path
        self.name = ""
        self.ports = []
        self.body = []            # device lines (M...)
        self.all_lines = []
        self.pattern_code = ""
        self.occurrences = None
        self.cells = []
        self.n_transistors = 0
        self.n_pmos = 0
        self.n_nmos = 0

    @property
    def exists(self):
        return bool(self.all_lines)

    @property
    def n_nets(self):
        names = set(self.ports)
        for line in self.body:
            parts = line.split()
            if parts and parts[0].startswith("M"):
                names.update(parts[1:6])
        return len(names)


def read_spice_netlist(path):
    nl = SpiceNetlist(path)
    if not os.path.exists(path):
        return nl
    with open(path, "r", errors="replace") as fh:
        lines = [l.rstrip("\n") for l in fh]
    nl.all_lines = lines
    for line in lines:
        s = line.strip()
        if s.startswith(".subckt "):
            parts = s.split()
            nl.name = parts[1] if len(parts) > 1 else ""
            nl.ports = parts[2:]
        elif s.startswith(".ends"):
            continue
        elif s.startswith("M"):
            nl.body.append(s)
            parts = s.split()
            if line.rstrip().endswith("PMOS") or " PMOS" in s:
                nl.n_pmos += 1
            elif "NMOS" in s:
                nl.n_nmos += 1
            nl.n_transistors += 1
        elif s.startswith("* pattern code:"):
            nl.pattern_code = s.split("* pattern code:", 1)[1].strip()
        elif "occurrences in design" in s:
            m = re.search(r"\* (\d+) occurrences", s)
            if m:
                nl.occurrences = int(m.group(1))
        elif s.startswith("* each contains"):
            m = re.search(r"each contains (\d+) cells", s)
            if m:
                nl.cell_count = int(m.group(1))
        elif s.startswith("*   "):
            nl.cells.append(s[4:].strip())
    return nl


# ---------------------------------------------------------------- records
class BestRecord(object):
    """``bestRecord-<bench>``: the greedy combination the runner settled on."""

    def __init__(self, path=""):
        self.path = path
        self.exists = False
        self.save_area_astran = None
        self.save_ratio_astran = None
        self.save_area_gscl = None
        self.save_ratio_gscl = None
        self.selected = []        # [(name, clusterNum, cellNum, trace), ...]
        self.runtime_s = None


def read_best_record(path):
    rec = BestRecord(path)
    if not os.path.exists(path):
        return rec
    rec.exists = True
    for line in open(path, "r", errors="replace"):
        s = line.strip()
        if not s:
            continue
        if "compared to Astran GDS area" in s:
            num = _first_float(s)
            if num is not None:
                if "%" in s:
                    rec.save_ratio_astran = num
                else:
                    rec.save_area_astran = num
        elif "compared to GSCL GDS area" in s:
            num = _first_float(s)
            if num is not None:
                if "%" in s:
                    rec.save_ratio_gscl = num
                else:
                    rec.save_area_gscl = num
        elif s.startswith("runtime:") or "runtime:" in s:
            m = re.search(r"runtime:\s*([\d.eE+-]+)", s)
            if m:
                try:
                    rec.runtime_s = float(m.group(1))
                except ValueError:
                    pass
        elif s.startswith("(") and s.endswith(")"):
            try:
                tup = ast.literal_eval(s)
            except (ValueError, SyntaxError):
                continue
            if isinstance(tup, tuple) and len(tup) == 4:
                rec.selected.append(tup)
    return rec


class PatternRecord(object):
    """One row of ``bestRecord-seperate<bench>`` (phase-2 per-pattern detail)."""

    def __init__(self, design_area, save_area, save_ratio, pattern_cnt,
                 pattern_size, coverage, name, code):
        self.design_area = design_area
        self.save_area = save_area
        self.save_ratio = save_ratio
        self.pattern_cnt = pattern_cnt
        self.pattern_size = pattern_size
        self.coverage = coverage
        self.name = name
        self.code = code

    def as_row(self):
        return [self.name, "%.3f" % self.save_area, "%.2f%%" % self.save_ratio,
                str(self.pattern_cnt), str(self.pattern_size),
                str(self.coverage), self.code]


def read_separate_record(path):
    rows = []
    if not os.path.exists(path):
        return rows
    for line in open(path, "r", errors="replace"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 8 or cells[0] in ("designOverallArea", ""):
            continue
        try:
            rows.append(PatternRecord(
                _to_float(cells[0]), _to_float(cells[1]), _to_float(cells[2]),
                _to_int(cells[3]), _to_int(cells[4]), _to_int(cells[5]),
                cells[6], cells[7]))
        except ValueError:
            continue
    return rows


def _first_float(text):
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text.replace("%", " %"))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _to_float(text):
    return float(text.replace("%", "").strip())


def _to_int(text):
    return int(float(text.strip()))


# ------------------------------------------------------------ output dir scan
class CellArtifact(object):
    """One COMPLEX cell as found in an output directory."""

    def __init__(self, name, directory):
        self.name = name
        self.directory = directory
        self.sp_path = os.path.join(directory, name + ".sp")
        self.gds_path = os.path.join(directory, name + ".gds")
        self.png_path = os.path.join(directory, name + ".png")
        self.log_path = os.path.join(directory, name + ".Astranlog")
        self.run_path = os.path.join(directory, name + ".run")

    @property
    def has_sp(self):
        return os.path.exists(self.sp_path)

    @property
    def has_gds(self):
        return os.path.exists(self.gds_path)

    @property
    def has_png(self):
        return os.path.exists(self.png_path)

    @property
    def has_log(self):
        return os.path.exists(self.log_path)

    def __repr__(self):
        return "<CellArtifact %s>" % self.name


def scan_output_dir(directory):
    """Every COMPLEX* artifact in ``directory``, in numeric id order."""
    if not os.path.isdir(directory):
        return []
    names = set()
    for fn in os.listdir(directory):
        base, ext = os.path.splitext(fn)
        if ext.lower() in (".sp", ".gds", ".png", ".astranlog", ".run"):
            if base.upper().startswith("COMPLEX"):
                names.add(base)
    return [CellArtifact(n, directory) for n in sorted(names, key=cell_sort_key)]


def list_output_benchmarks(outputs_dir):
    """Benchmark names that already have an ``outputs/<name>`` directory."""
    if not os.path.isdir(outputs_dir):
        return []
    return sorted(d for d in os.listdir(outputs_dir)
                  if os.path.isdir(os.path.join(outputs_dir, d)))


# -------------------------------------------------- analysis helpers
def trace_to_types(trace):
    """Pattern code -> the list of standard-cell types it contains.

    The code is the initial tree ``[A,B,C]`` followed by one growth extension
    per absorbed neighbour ``+TYPE_c<i>o<k>`` / ``+TYPE_c<i>i<j>``, so each
    extension contributes its ``TYPE`` prefix.  Used to estimate the pattern's
    "original" width (the sum of its cells' individual widths).
    """
    if not trace:
        return []
    types = []
    parts = trace.split("+")
    initial = parts[0].strip()
    if initial.startswith("[") and initial.endswith("]"):
        initial = initial[1:-1]
    for t in initial.split(","):
        t = t.strip()
        if t:
            types.append(t)
    for ext in parts[1:]:
        ext = ext.strip()
        if not ext:
            continue
        m = re.match(r"(.+?)_c\d+[io]\d+$", ext)
        types.append(m.group(1) if m else ext)
    return types


def load_baseline_widths(directory):
    """Nominal width of each ASTRAN baseline cell, from its .Astranlog.

    Same metric the flow's GDSIIAnalysis.loadAstranGDS returns, but read from
    an absolute directory so the GUI main thread does not need cwd = pySrc.
    """
    widths = {}
    if not os.path.isdir(directory):
        return widths
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith(".Astranlog"):
            continue
        log = parse_astran_log(os.path.join(directory, fn))
        if log.complete and log.width_um:
            widths[fn[:-len(".Astranlog")]] = log.width_um
    return widths


def pattern_original_width(trace, baseline_widths):
    """Sum of the baseline widths of a pattern's cells; None if unknown."""
    total = 0.0
    found = 0
    for t in trace_to_types(trace):
        if t in baseline_widths:
            total += baseline_widths[t]
            found += 1
    return total if found else None


def read_lef_widths(lef_path):
    """Nominal width of every LEF MACRO, from its SIZE statement.

    Generalisation of GDSIIAnalysis.loadOrignalGSCL45nmGDS: that one is pinned
    to the 32 GSCL45 cells; this reads whatever LEF the user points at (the
    GUI's area comparison for a custom PDK).
    """
    widths = {}
    if not os.path.exists(lef_path):
        return widths
    macro = None
    for line in open(lef_path, "r", errors="replace"):
        t = line.strip()
        if t.startswith("MACRO "):
            macro = t.split()[1]
        elif t.startswith("SIZE ") and macro is not None:
            parts = t.replace(";", "").split()
            if len(parts) >= 4:
                try:
                    widths[macro] = float(parts[1])
                except ValueError:
                    pass
        elif t.startswith("END ") and macro is not None:
            macro = None
    return widths


def read_layer_map(map_path):
    """Parse a Cadence-style layer map (``name purpose stream datatype`` rows)
    into ``{stream: name}``.  Used to label GDS layers of a custom PDK."""
    out = {}
    if not os.path.exists(map_path):
        return out
    for line in open(map_path, "r", errors="replace"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) < 3:
            continue
        try:
            stream = int(parts[2])
        except ValueError:
            continue
        if stream not in out:            # first occurrence wins
            out[stream] = parts[0]
    return out
