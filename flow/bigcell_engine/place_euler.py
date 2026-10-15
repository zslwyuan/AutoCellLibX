"""Deterministic Euler-chain constructive placement (stage 3, doc section
2.2 C).

Block-granularity recast of ASTRAN's eulerpath()/visit() (cellnetlst.cpp:
36-193 -- dead code there, recast here for real): nodes = block end-nets,
edges = blocks; one trail per polarity, built by a JOINT walk so P and N
advance in lockstep and same-gate P/N blocks land in the same step
(columns) -- ASTRAN's visit(nDifs) preference order, ported:

1. advance both rows, next blocks share a gate;
2. gap: N continues, P restarts on a net whose block matches N's gate;
3. gap: P continues, N restarts likewise;
4. gap: both restart on same-gate blocks;
5. advance both rows, gates differ;
6./7. advance one row only (the other has nothing at its head);
8. gap: both restart on any blocks;
9./10. gap: restart one row while the other is exhausted.

A restart is a diffusion break in that row (the trail begins again on a
different net).  One attempt runs with the full gap budget
``(np+nn)//2`` -- mirroring eulerpath's ``cntDifs <= trans.size()/2``
ceiling -- because the preference order already spends restarts only
when stuck (greedy gap minimality); retrying ascending budgets like
eulerpath does re-explores the same failures per level and is the main
reason that code was too slow to ship.  Backtracking is deterministic
(every candidate list sorted, lexicographic tie-breaks) and bounded by a
hard node-expansion budget (EXPANSION_BUDGET) plus a failure memo; on
exhaustion the greedy row seeds (netlist_ext.row_seeds) are returned
unchanged.  Constructs in milliseconds what SA needs thousands of moves
to find; it is place_sa's initializer.
"""

from bigcell_engine.geometry import N_ROW, P_ROW, block_width_cols
from bigcell_engine.netlist_ext import mirror_block

EXPANSION_BUDGET = 200000
_MAX_MEMO = 100000


class _RowModel(object):
    """Static per-row trail data: blocks, gate sets, incident nets."""

    def __init__(self, blocks, leg_widths):
        self.blocks = list(blocks)
        self.gates = [frozenset(m.device.gate for m in b.members)
                      for b in self.blocks]
        if leg_widths:
            self.widths = [block_width_cols(b, leg_widths)
                           for b in self.blocks]
        else:
            self.widths = [len(b.members) for b in self.blocks]
        # candidate key: wider blocks first, then first-device name
        self.key = [(-w, b.first.name) for w, b in
                    zip(self.widths, self.blocks)]
        self.order = sorted(range(len(self.blocks)), key=lambda i: self.key[i])
        self.incident = {}
        for i in self.order:
            b = self.blocks[i]
            for net in set((b.left_net, b.right_net)):
                self.incident.setdefault(net, []).append(i)

    def candidates(self, head, used):
        """Unused blocks reachable at ``head`` as (idx, flip), sorted.

        ``head`` None = trail start: every unused block, forward first.
        """
        out = []
        if head is None:
            for i in self.order:
                if not used[i]:
                    out.append((i, False))
                    if (self.blocks[i].left_net
                            != self.blocks[i].right_net):
                        out.append((i, True))
            return out
        for i in self.incident.get(head, ()):    # insertion = key order
            if used[i]:
                continue
            b = self.blocks[i]
            if b.left_net == head:
                out.append((i, False))
            elif b.right_net == head:
                out.append((i, True))
        return out

    def restarts(self, used):
        """(net, idx, flip) for every unused block, grouped by net name."""
        out = []
        for net in sorted(self.incident):
            for i in self.incident[net]:
                if used[i]:
                    continue
                b = self.blocks[i]
                if b.left_net == net:
                    out.append((net, i, False))
                elif b.right_net == net:
                    out.append((net, i, True))
        return out


def euler_orderings(blocks_by_row, leg_widths=None,
                    expansion_budget=EXPANSION_BUDGET):
    """Return (ordering_p, ordering_n) block sequences.

    ``blocks_by_row`` is row_seeds' {P_ROW: [...], N_ROW: [...]} mapping.
    Deterministic; pure function of the inputs.  On budget exhaustion the
    seed orderings are returned as-is (the doc's fallback).
    """
    seed_p = list(blocks_by_row[P_ROW])
    seed_n = list(blocks_by_row[N_ROW])
    if not seed_p or not seed_n:
        return seed_p, seed_n
    p = _RowModel(seed_p, leg_widths)
    n = _RowModel(seed_n, leg_widths)
    budget = [expansion_budget]
    result = _joint_walk(p, n, (len(p.blocks) + len(n.blocks)) // 2, budget)
    if result is not None:
        seq_p, seq_n = result
        return (_materialize(p, seq_p), _materialize(n, seq_n))
    return seed_p, seed_n


def _materialize(model, seq):
    """(idx, flip) steps -> oriented DiffusionBlock list."""
    out = []
    for idx, flip in seq:
        block = model.blocks[idx]
        out.append(block if not flip else mirror_block(block))
    return out


def _joint_walk(p, n, max_gaps, budget):
    """One bounded DFS; returns ((idx, flip) lists) or None."""
    used_p = [False] * len(p.blocks)
    used_n = [False] * len(n.blocks)
    seq_p = []
    seq_n = []
    memo = {}

    def head_of(model, idx, flip):
        block = model.blocks[idx]
        return block.right_net if not flip else block.left_net

    def rec(p_head, n_head, gaps):
        if budget[0] <= 0:
            return False
        budget[0] -= 1
        if all(used_p) and all(used_n):
            return True
        key = (p_head, n_head, frozenset(
            i for i in range(len(used_p)) if used_p[i]), frozenset(
            i for i in range(len(used_n)) if used_n[i]))
        prev = memo.get(key)
        if prev is not None and prev >= max_gaps - gaps:
            return False

        def advance(pi, pf, ni, nf, gap_step):
            """Consume one P block and one N block (gap_step on restart)."""
            if gap_step and gaps >= max_gaps:
                return False
            used_p[pi] = True
            seq_p.append((pi, pf))
            used_n[ni] = True
            seq_n.append((ni, nf))
            ok = rec(head_of(p, pi, pf), head_of(n, ni, nf),
                     gaps + (1 if gap_step else 0))
            if not ok:
                seq_p.pop()
                seq_n.pop()
                used_p[pi] = False
                used_n[ni] = False
            return ok

        def advance_p(pi, pf, gap_step):
            if gap_step and gaps >= max_gaps:
                return False
            used_p[pi] = True
            seq_p.append((pi, pf))
            ok = rec(head_of(p, pi, pf), n_head,
                     gaps + (1 if gap_step else 0))
            if not ok:
                seq_p.pop()
                used_p[pi] = False
            return ok

        def advance_n(ni, nf, gap_step):
            if gap_step and gaps >= max_gaps:
                return False
            used_n[ni] = True
            seq_n.append((ni, nf))
            ok = rec(p_head, head_of(n, ni, nf),
                     gaps + (1 if gap_step else 0))
            if not ok:
                seq_n.pop()
                used_n[ni] = False
            return ok

        p_cands = p.candidates(p_head, used_p)
        n_cands = n.candidates(n_head, used_n)
        p_rest = p.restarts(used_p)
        n_rest = n.restarts(used_n)

        # 1. both advance, same gate
        for pi, pf in p_cands:
            for ni, nf in n_cands:
                if p.gates[pi] & n.gates[ni]:
                    if advance(pi, pf, ni, nf, False):
                        return True
        # 2. gap: N continues, P restarts on a gate-matched block
        for ni, nf in n_cands:
            for _net, pi, pf in p_rest:
                if p.gates[pi] & n.gates[ni]:
                    if advance(pi, pf, ni, nf, True):
                        return True
        # 3. gap: P continues, N restarts on a gate-matched block
        for pi, pf in p_cands:
            for _net, ni, nf in n_rest:
                if p.gates[pi] & n.gates[ni]:
                    if advance(pi, pf, ni, nf, True):
                        return True
        # 4. gap: both restart, same gate
        for _np, pi, pf in p_rest:
            for _nn, ni, nf in n_rest:
                if p.gates[pi] & n.gates[ni]:
                    if advance(pi, pf, ni, nf, True):
                        return True
        # 5. both advance, gates differ
        for pi, pf in p_cands:
            for ni, nf in n_cands:
                if advance(pi, pf, ni, nf, False):
                    return True
        # 6./7. one row advances (the other's head has nothing)
        for pi, pf in p_cands:
            if advance_p(pi, pf, False):
                return True
        for ni, nf in n_cands:
            if advance_n(ni, nf, False):
                return True
        # 8. gap: both restart on any blocks
        for _np, pi, pf in p_rest:
            for _nn, ni, nf in n_rest:
                if advance(pi, pf, ni, nf, True):
                    return True
        # 9./10. gap: restart one row while the other is exhausted
        for _net, pi, pf in p_rest:
            if advance_p(pi, pf, True):
                return True
        for _net, ni, nf in n_rest:
            if advance_n(ni, nf, True):
                return True
        memo[key] = max_gaps - gaps
        return False

    if rec(None, None, 0):
        return list(seq_p), list(seq_n)
    return None
