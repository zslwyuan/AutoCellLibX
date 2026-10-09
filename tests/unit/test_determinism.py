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
from blif_preproc import load_data_and_preprocess
from blif_graph_util import sort_pattern_cluster_seqs
from spice import load_spice_subcircuits, export_spice_netlist

out = tempfile.mkdtemp()
G, cells, netlist, types, ds, ml, seqs, cn = load_data_and_preprocess(
    lib_file_name="../std_celllib/gscl45nm.lib",
    blif_file_name="../benchmark/blif/adder.blif", start_time=0)
seqs = sort_pattern_cluster_seqs(seqs)
subs = load_spice_subcircuits("../std_celllib/cellsAstranFriendly.sp")
export_spice_netlist(seqs[0], subs, 0, out)
print(hashlib.md5(
    open(os.path.join(out, "COMPLEX0.sp"), "rb").read()).hexdigest())
'''


def _export_hash(flow_dir, seed, tmp_path):
    helper = tmp_path / "hash_helper.py"
    helper.write_text(HELPER)
    env = dict(os.environ, PYTHONHASHSEED=str(seed))
    proc = subprocess.run([sys.executable, str(helper)], cwd=flow_dir,
                          env=env, capture_output=True, text=True, check=True)
    return proc.stdout.strip().splitlines()[-1]


def test_netlist_export_is_hash_seed_independent(flow_dir, tmp_path):
    digests = {_export_hash(flow_dir, seed, tmp_path) for seed in (0, 1, 7)}
    assert len(digests) == 1, digests
