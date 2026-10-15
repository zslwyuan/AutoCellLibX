"""Width/checker benchmark: bigcell engine vs the ASTRAN baseline
(stage 3, doc section 4).

Fixed benchmark set (flow/original_astran_cells gates + flow/outputs/*/
COMPLEX* cells); ASTRAN baseline widths from a cached run (re-running the
queue into a scratch dir when the cache is cold); per-cell record: device
count, ASTRAN width, bigcell width, verify/layout-sanity/pin-access
verdicts.  Report as JSON + markdown.  This is the continuous-verification
backbone for the replacement -- every engine change re-runs it.
"""

BENCHMARK_GLOBS = ("original_astran_cells/*.sp", "outputs/*/*.sp")


def load_benchmark_cells():
    """Return the sorted, de-duplicated benchmark cell list.

    Not implemented yet -- stage 3 step 5 (agent: bigcell-harness).
    """
    raise NotImplementedError("benchmark.load_benchmark_cells")


def run_benchmark(cells, out_dir):
    """Run the engines over the cells and write the report.

    Not implemented yet -- stage 3 step 5 (agent: bigcell-harness).
    """
    raise NotImplementedError("benchmark.run_benchmark")
