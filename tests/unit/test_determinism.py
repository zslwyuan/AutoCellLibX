"""The exported netlist must not depend on dict/set hash order.

A complex's ports must come out in a deterministic order.  A plain set iterates
in hash order, which varies per process (PYTHONHASHSEED); that made the netlist
-- and with it the layout cache key -- different on every run, so cached
layouts were regenerated needlessly and results were not reproducible.
"""
import hashlib
import os
import subprocess
import sys

HELPER = r'''
import hashlib, os, sys, tempfile
sys.path.insert(0, os.getcwd())
from BLIFPreProc import loadDataAndPreprocess
from BLIFGraphUtil import sortPatternClusterSeqs
from spice import loadSpiceSubcircuits, exportSpiceNetlist

out = tempfile.mkdtemp()
G, cells, netlist, types, ds, ml, seqs, cn = loadDataAndPreprocess(
    libFileName="../stdCelllib/gscl45nm.lib",
    blifFileName="../benchmark/blif/adder.blif", startTime=0)
seqs = sortPatternClusterSeqs(seqs)
subs = loadSpiceSubcircuits("../stdCelllib/cellsAstranFriendly.sp")
exportSpiceNetlist(seqs[0], subs, 0, out)
print(hashlib.md5(
    open(os.path.join(out, "COMPLEX0.sp"), "rb").read()).hexdigest())
'''


def _export_hash(pysrc_dir, seed, tmp_path):
    helper = tmp_path / "hash_helper.py"
    helper.write_text(HELPER)
    env = dict(os.environ, PYTHONHASHSEED=str(seed))
    proc = subprocess.run([sys.executable, str(helper)], cwd=pysrc_dir,
                          env=env, capture_output=True, text=True, check=True)
    return proc.stdout.strip().splitlines()[-1]


def test_netlist_export_is_hash_seed_independent(pysrc_dir, tmp_path):
    digests = {_export_hash(pysrc_dir, seed, tmp_path) for seed in (0, 1, 7)}
    assert len(digests) == 1, digests
