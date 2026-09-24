"""Consistency checks on the committed adder results.

These guard contracts that live in main.py but only become visible in the
generated files: pattern de-duplication (the same pattern must not be exported
under two ids) and layout/netlist agreement (a cached layout must belong to the
netlist sitting next to it).  They are content-based, so they hold across a
fresh checkout regardless of file mtimes.
"""
import glob
import os
import re

import pytest

PATTERN_CODE_RE = re.compile(r"^\* pattern code: (.*)$", re.M)


def _outdir(repo_dir):
    return os.path.join(repo_dir, "pySrc", "outputs", "adder")


def _complex_netlists(repo_dir):
    return sorted(glob.glob(os.path.join(_outdir(repo_dir), "COMPLEX*.sp")))


def test_no_two_complexes_share_a_pattern(repo_dir):
    files = _complex_netlists(repo_dir)
    if not files:
        pytest.skip("no adder outputs")
    seen = {}
    for path in files:
        text = open(path, encoding="utf-8", errors="replace").read()
        match = PATTERN_CODE_RE.search(text)
        assert match, "no pattern code in %s" % path
        code = match.group(1).strip()
        name = os.path.basename(path)
        assert code not in seen, "%s duplicates %s (%s)" % (
            name, seen[code], code)
        seen[code] = name


def test_logged_transistor_count_matches_the_netlist(repo_dir):
    """Catches a stale layout: the log next to a .sp must describe that .sp."""
    files = _complex_netlists(repo_dir)
    if not files:
        pytest.skip("no adder outputs")
    for sp in files:
        name = os.path.basename(sp)[:-3]
        log = os.path.join(_outdir(repo_dir), name + ".Astranlog")
        if not os.path.exists(log):
            continue
        inNetlist = sum(1 for line in open(sp) if line.startswith("M"))
        logged = None
        for line in open(log, encoding="utf-8", errors="replace"):
            if "transistors before folding" in line:
                logged = int(line.split(":")[1].split("->")[0].strip())
                break
        assert logged == inNetlist, (
            "%s: netlist has %d transistors, log says %s"
            % (name, inNetlist, logged))
