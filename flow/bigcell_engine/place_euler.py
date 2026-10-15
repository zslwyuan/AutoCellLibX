"""Deterministic Euler-chain constructive placement (stage 3, doc section
2.2 C).

Block-granularity recast of ASTRAN's eulerpath()/visit() (cellnetlst.cpp:36-
193 -- dead code there, recast here for real): nodes = block end-nets,
edges = blocks; find one trail per polarity maximizing same-gate column
pairing across rows with a bounded gap budget.  Deterministic backtracking
with a hard node-expansion budget and lexicographic tie-breaks; on budget
exhaustion fall back to netlist_ext.row_seeds.  Constructs in milliseconds
what SA needs thousands of moves to find; it is place_sa's initializer.
"""

EXPANSION_BUDGET = 200000


def euler_orderings(blocks_by_row, leg_widths):
    """Return (ordering_p, ordering_n) block sequences.

    Not implemented yet -- stage 3 step 2 (agent: bigcell-placement).
    """
    raise NotImplementedError("place_euler.euler_orderings")
