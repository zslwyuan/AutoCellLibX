# STAGE 3 — Big-Cell Placement+Routing Engine (pure Python)

> **Status**: design document (no code yet). Drives a real implementation later.
> **Scope**: cells the `smt_engine` cannot close — irregular structures and
> >~12 transistors (the mined `COMPLEX*` cells run 14–36 T).
> **Dependencies on earlier stages of the ASTRAN-retirement plan**:
> - **Stage 1** lands a clean, Python-owned compaction model (JSON geometry +
>   constraint request, solved by python-mip/CBC or the existing CP-SAT
>   backend in `tools/gurobi_cl/cpsat_backend.py`). Stage 3 consumes it; it
>   does **not** re-own compaction.
> - **Stage 2** lands the per-cell engine flag `--engine auto|smt|astran`.
>   Stage 3 adds `bigcell` as the middle rung of that ladder.
> **Binding constraints**: every section below respects the AGENTS.md
> invariants, especially #8/#9 (determinism), #1/#10 (area = width at matched
> row height), #4/#5/#7 (FEASIBLE-is-success, trace identity, cache contract)
> and the ASTRAN landmine list (GAP padding, M-prefix lint, `.subckt` port
> order, per-cell LP cwd).

---

## 1. What ASTRAN does for big cells today

ASTRAN's per-cell pipeline (`AutoCell::autoFlow`, `tools/astran/src/autocell2.cpp:140-169`)
is: select/flatten → calcArea → fold → place (SA) → route (negotiated graph
routing) → compact (ILP) → export, wrapped in two retry loops (track count and
"conservative" diffusion shrinking). A cell netlist enters as transistor-level
`.sp` (flat, `Circuit::getFlattenCell`, `tools/astran/src/circuit.cpp:137-163`).

### 1.1 Geometry template — `calcArea` (autocell2.cpp:68-128)

Fixed by the flow's run script, never ASTRAN defaults (AGENTS.md invariant 2):
`flow/astran.py:80-84` emits `set rowheight 13`, `set grid 0.19 0.19`,
`set supplysize 0.26`, `set nwellpos 1.235`, `set celltemplate "Tapless"` →
H = 13 × 0.19 = **2.47 µm** (GSCL45 CoreSite), wells split at H/2. `calcArea`
derives from the `.rul` rules: diffusion y-extents (`nDif_*Y`/`pDif_*Y`,
autocell2.cpp:81-119), the per-polarity max device height `nSize`/`pSize`
(used by folding), and — critically for routing — the sorted list
`trackPos` of legal horizontal M1 track y-centres between the supply rails
(autocell2.cpp:86-100). At H = 2.47 µm this yields ~**13 M1 tracks** (the
`smt_engine` 7-track model is a deliberate simplification of this; see
`flow/smt_engine/route_model.py:6-13`). A second argument (`reduceMetTracks`,
the "conservative" retry) *shrinks* the diffusion windows to leave more routing
room — note it makes the folding/placement problem harder, which is why the
retry ladder often does not recover (AGENTS.md landmine: "the conservative
retry shrinks the diffusion, making it worse").

### 1.2 Folding — `foldTrans` (autocell2.cpp:171-180; cellnetlst.cpp:254-286)

Two deterministic transforms:
- **series folding**: walks the device graph from the supply rails and splits
  long series stacks into legs (`foldingSeries`/`seriesFolding`,
  cellnetlst.cpp:772-890);
- **width folding**: any device wider than the row's diffusion height is split
  into `ceil(W/size)` parallel legs (cellnetlst.cpp:262-285).
This changes the transistor count before placement (the `.Astranlog` line
"Number of transistors before/after folding" — the freshness check in
`doc/AUDIT_REPORT.md` §5.37 keys on it).

### 1.3 Placement — dual-row ordering + Threshold Accept

Representation (cellnetlst.cpp:533-554): two equal-length sequences
`orderingP`/`orderingN`; slot *i* of each row is `{link, type}` = which
transistor occupies position *i* and which terminal (SOURCE/DRAIN) faces left.
Diffusion sharing is *implicit in adjacency*: slot *i* and *i+1* share
diffusion iff the right net of *i* equals the left net of *i+1*. Rows with
unequal P/N counts are padded with `link = -1` GAP entries (cellnetlst.cpp:547-553)
— the known `trans[-1]` landmine (AGENTS.md; four unguarded reads crashed
NOR3X1).

**Important finding for this design**: ASTRAN contains a joint P/N Euler-trail
constructor (`CellNetlst::eulerpath`, cellnetlst.cpp:182-193, with a bounded-gap
backtracking `visit`, cellnetlst.cpp:36-176) but **it has no caller** — the
shipped placement is pure metaheuristics starting from netlist order. The
"Euler-chain construction" option in §2.3 is therefore new functionality that
can cite this code as prior art, not a port of shipped behaviour.

Algorithm: `ThresholdAccept` (`tools/astran/src/thresholdaccept.h:86-204`), a
deterministic SA variant (accept if `Δcost ≤ threshold`; threshold decays by
`0.98 − accept_ratio²/2`, thresholdaccept.h:13-15; initial threshold found by a
bisection search running **5000 perturbations per step**, thresholdaccept.h:45-77).
Move set (`CellNetlst::perturbation`/`move`, cellnetlst.cpp:462-507): pick the
P row (p=1/4), N row (p=1/4) or both (p=1/2); inside a row pick a random
segment (length 1..n, random origin) and either **shift** it elsewhere or
**mirror** it (reverse order + flip S/D orientation). One move = one full
`getCost()` (cellnetlst.cpp:364-460).

Cost = `localCong² Σ + 100·(4·maxCong + 4·mismatchesGate + 2·wGaps + 1·wRouting + 4·posPN)`
(weights from `autoFlow`'s call `placeTrans(false, 150, 3, 4, 4, 1, 4, 2)`,
autocell2.cpp:152). The terms are exactly where layout quality comes from:

| Term | Meaning | Quality lever |
|---|---|---|
| `posPN` | cell width in gate positions | first-order area (invariant 1: width is the metric) |
| `wGaps` | diffusion breaks (neighbouring same-row slots with different edge nets) | every break widens the cell; diffusion sharing = zero-gap adjacency |
| `mismatchesGate` | columns where P and N gate nets differ | aligned gates share one straight poly stripe |
| `wRouting` | Σ net bounding-box spans | wirelength proxy for routability |
| `maxCong`/`localCong` | max / squared-sum overlap of net bounding boxes | congestion proxy that gates the track-count loop |

Budget mechanics (why big cells cost hours): `getProblemSize()` =
`|orderingP| × |orderingN|` (cellnetlst.cpp:509-511) and
`num_repetitions = problemSize × quality_factor` (thresholdaccept.h:94) with
quality 150. The 14 T adder/COMPLEX0 log shows `problem size = 49` →
7,350 moves per SA iteration (adder/COMPLEX0.Astranlog:13); a 36 T cell has
~18×18 = 324 → **48,600 full-cost moves per iteration**, times dozens of
iterations, times `nrAttempts = 3` (autocell2.cpp:152), wrapped in the
track-count loop (2→4 tracks, congestion gates ≤6/≤8, autocell2.cpp:148-157)
and then the **speculative** round: 3 × (fresh SA + trial route), picking the
ordering with the best real routing cost (autocell2.cpp:158, 187-216) — the
"double SA rounds" of the measured ~1.5 h big-cell placement. Termination is
10 consecutive same-cost iterations (thresholdaccept.h:168-177) or a
**wall-clock escape at 17,500 s** (thresholdaccept.h:194) — that escape hatch
is the one piece of ASTRAN's schedule a Python re-implementation must *not*
copy (invariant 9); it never fires in practice, which is why ASTRAN behaves
deterministically despite it (invariant 8 holds because `rand()` is never
seeded — C default seed — not because time is bounded).

### 1.4 Routing — negotiated congestion on a per-column graph

`AutoCell::route` (autocell2.cpp:243-474) walks the two orderings and emits one
`Element` per grid column with per-track nodes: horizontal M1 arcs (cost 4
between diffusions, 16 inside diffusion regions), vertical poly arcs (cost 6),
diffusion-contact arcs (cost 20), and a 0-cost `inoutCnt` hub per column wired
to every track so cell I/O pins can attach anywhere (autocell2.cpp:11-66,
58-62, 303-309). Gate nodes attach to the poly nodes over each device's diffusion
span (autocell2.cpp:377-392). The solver is `GraphRouter::routeNets`
(graphrouter.cpp:92-184): textbook Pathfinder (negotiated congestion) — route
everything allowing overlap, bump `history` on contested nodes
(graphrouter.cpp:138), next-round cost = `arc.cost + history·(nrNets+1)`
(graphrouter.cpp:429-434), rip up and re-route conflicted nets, up to **8000
attempts** (autocell2.cpp:470) with a `cntConflict > 50000` stall break
(graphrouter.cpp:165). Two Steiner-point optimization sweeps follow
(`rt->optimize() && rt->optimize()`, autocell2.cpp:472; graphrouter.cpp:230-282).
Unroutable → `conservative++` → whole pipeline restarts (max 4).

The second router — `Router`/`GridRouter` (router.cpp, gridrouter.cpp) — is a
3-layer (M1/via/M2) grid A* with the same Pathfinder history scheme
(gridrouter.cpp:83-156, 158-250, 339-351); it serves the *multi-cell*
placement flow (`Placer::incrementalPlacement`, placer.cpp:37-127;
`designmng.cpp:445,460`), not the per-cell flow, but it is the in-tree proof
that ASTRAN-style routing generalizes to an M2 escape layer.

### 1.5 Compaction — ILP coordinate squeezing

`AutoCell::compact` (autocell2.cpp:476-1074) turns the routed geometry into an
LP (`Compaction`, compaction.cpp): four variables per geometry Box
(`x{i}a/b`, `y{i}a/b`) plus end-line extension variables `a2/b2` pinned to the
real edges (§5.11 discipline), spacing as **disjunctive constraints with a
big-M** (`insertDistanceRuleInteligent`, autocell2.cpp:1643-1682; three
options — right-of / above / diagonal — selected by binaries, each constraint
carrying `+ RELAXATION` so the off-branch relaxes; M = 20000 µm). Objective:
`width` at weight **5000** dominates, everything else is tie-breaking
(autocell2.cpp:810-813); width is forced onto the 0.19 µm grid via integer
`width_gpos` (autocell2.cpp:811-812). Solve via the `gurobi_cl` shim
(compaction.cpp:462-746); then up to **8 repair passes** detect solved-coordinate
spacing violations between nodes farther apart than the pairwise model covers
and re-solve with new keep-away disjuncts until 0 violations
(autocell2.cpp:825-905). The Python adapter adds the escalation ladder the
AGENTS.md landmines describe: FEASIBLE = success (invariant 4), 300 s cap +
2 % gap, and rebuild-without-option-3 only on *proved* INFEASIBLE. Measured on
the biggest adder cell: 11,554 constraints / 6,447 variables / 2,740 binaries
(doc/P2_MERGE_PLAN.md stage 2), and CP-SAT matched CBC's width with a slightly
better objective (−0.11 %); COMPLEX1 CBC@180 s collapsed to 9.31 µm while
CP-SAT got 3.61 µm — the solver backend already matters more than the model.

### 1.6 Measured behaviour on this repo's big cells

Benchmark set (all `flow/outputs/*/COMPLEX*`, transistor counts counted from
`.sp`, widths from regenerated 2026-10 logs, AUDIT §5.37):

| Cell | T | ASTRAN width (µm) | | Cell | T | ASTRAN width (µm) |
|---|---|---|---|---|---|---|
| adder/COMPLEX0 | 14 | 2.09 | | multiplier/COMPLEX0 | 22 | 5.51 |
| ctrl/COMPLEX11 | 14 | — | | adder/COMPLEX9 | 26 | 3.42 |
| multiplier/COMPLEX4 | 14 | — | | multiplier/COMPLEX7 | 28 | — |
| multiplier/COMPLEX5 | 16 | — | | adder/COMPLEX1 | 30 | 3.61 |
| max/COMPLEX20 | 18 | — | | adder/COMPLEX11 | 32 | 3.80 |
| | | | | adder/COMPLEX10 | 36 | 4.37 |

(The commonly cited "36 T → 3.61 µm" datum is the big-cell band of this
snapshot — 28–36 T cells land at 3.4–4.4 µm; the 3.61 µm figure is
adder/COMPLEX1 at 30 T. Per-cell numbers are re-measured at gate time in §4.)
Regenerating the 5 adder cells serially took **~57 min** (AUDIT §5.37) ≈
11 min/cell average, dominated by SA placement and the compaction solves; the
1.5 h figure is the big-cell placement alone (double SA rounds, §1.3).
**Implications**: (a) ~95 % of wall-clock is SA + LP, not GDS export — a
Python engine that replaces SA with something cheaper wins immediately;
(b) quality is not luck — it comes from diffusion sharing (wGaps), gate
alignment (mismatchesGate), ~13 M1 tracks of routing resource, and the ILP
compactor squeezing the result; any replacement must model all four;
(c) ASTRAN's floor on irregular 14–22 T cells is 2.09–5.51 µm, and the SMT
scorer already showed exact packing can beat it (multiplier/COMPLEX0: 3.99
vs 5.51 µm, −27.6 %, AUDIT §5.37) — there is headroom, not just parity to
chase.

---

## 2. Proposed architecture

New package `flow/bigcell_engine/`, sibling of `flow/smt_engine/`, same
contract style: deterministic, Qt-free, unit-tested, GDS on the ASTRAN layer
map consumable by `flow/layout_sanity.py` and `flow/pin_accessibility.py`.
One cell per invocation (called from the same queue that drives ASTRAN —
`flow/astran_queue.py` gets an engine field in its manifest, keeping the
per-cell-cwd discipline and the `.sp`-mtime cache contract, invariant 7).

```
flow/bigcell_engine/
  netlist_ext.py     # extensions over smt_engine.netlist (folding, row seeds)
  place_sa.py        # SA/PSO×SA placement (primary path)
  place_euler.py     # deterministic Euler-chain constructive placement
  place_windows.py   # CP-SAT window decomposition (evaluation + polish)
  route_grid.py      # negotiated-congestion router (Pathfinder port, 3-layer)
  route_exact.py     # thin wrapper: smt_engine.route_model as window fixer
  geometry.py        # ordering -> placed geometry (tracks, diffusions, poly)
  compact_client.py  # stage-1 JSON model request + solve + repair ladder
  gds.py             # reuse/extend flow/smt_engine/gds.py for irregular cells
  engine.py          # orchestration: ladder + fallback + logging
```

### 2.1 Netlist handling — reuse `flow/smt_engine/netlist.py`

Keep `CellNetlist`, `find_series_chains` (degree-2 pure internal nodes — the
gate-sharing trap is already handled, netlist.py:86-96),
`find_parallel_groups` (same (type, drain, source) pair, netlist.py:131-146)
and `build_diffusion_blocks` (chain/group/single with net-pair alternating
orientation, netlist.py:205-267) as the **only** structural model. Extensions
needed for big/irregular cells (`netlist_ext.py`):

1. **Deterministic folding** mirroring ASTRAN's two transforms
   (cellnetlst.cpp:254-286): width folding of any device whose
   `ceil(W/0.19)` footprint exceeds the per-row diffusion height budget, and
   series-stack folding when a chain's total width overflows one row half.
   Folding multiplies devices, so it must run *before* block building and be
   repricable (`name#legK`) for traceability. (The exact engine folds inside
   CP-SAT via `k`/`legw` variables, layout_model.py:99-114; a heuristic engine
   needs the fold decided up front.)
2. **Row seeds**: a function that proposes, per polarity, an initial linear
   order of diffusion blocks (used by both the Euler constructor and SA init).
   Deterministic: sort blocks by (−size, first-device-name), i.e. the same
   discipline as `build_diffusion_blocks`.
3. **Mixed-structure blocks**: today a "chain" is strictly linear. Irregular
   cells (adder/COMPLEX10) have nodes of degree > 2 that neither chains nor
   parallel groups capture; they fall out as singles, losing sharing. Add a
   **tree/branch block** type: a connected component over pure internal
   degree-2/3 nodes, flattened left-to-right by a DFS from its lowest-net
   leaf (deterministic tie-break by device name), placed as one unit whose
   internal branch points get access columns like shared edges. This is the
   minimal extension that makes `build_diffusion_blocks` total (every device
   in exactly one block) on all 15 benchmark cells; verify with a property
   test over `flow/outputs/*/*.sp`.

Port order / orientation stays exactly `BlockMember.left_net/right_net`
(netlist.py:154-203); the SA move set then operates on the same
representation ASTRAN uses (block sequence + per-block orientation + GAP
padding), so cost terms are directly comparable.

### 2.2 Placement — three candidates, evaluated, then composed

All three produce the same artifact: `(orderingP, orderingN)` of blocks with
orientations, legalized on the 0.19 µm grid at H = 2.47 µm
(invariants 1/2/10 — width in grid columns, height fixed, wells at H/2).

**A. CP-SAT window decomposition** (reuse `layout_model.build_layout_model`,
flow/smt_engine/layout_model.py:68-300). Split the block set into windows of
W blocks (start W=8), solve each window exactly with a fixed left boundary
(seam), concatenate. Pros: reuses the proven constraints (breaks, exclusivity,
gate alignment) verbatim. Cons: seams forfeit cross-window sharing; the model
is quadratic in block count — the break disjunctions are O(B²)
(layout_model.py:154-177) and access-column exclusivity is O(spots²)
(layout_model.py:224-263) — fine at B≈8–12 per window, and global width
`width_ub` is estimated from block sizes (layout_model.py:87-94) so window
models stay small. **Verdict: evaluate as (i) standalone on 14–22 T cells to
quantify the seam penalty and (ii) as a final polish pass on the outermost
window.** Not the primary big-cell path: irregular cells hit the same
routing-infeasibility wall that killed the joint engine (§2.4), and a
placement-only CP-SAT at 36 T with 40+ blocks is already minutes per window.

**B. SA / PSO×SA hybrid — the primary path** (roadmap P2-13,
doc/RESEARCH_AND_OPTIMIZATION.md:173; CFET-HMF template, :69-70). Port
ASTRAN's representation and move set *faithfully* (dual-row block ordering,
shift/mirror moves with P/N/both at ¼/¼/½, GAP padding) so ASTRAN's cost
function transfers term-for-term: width, diffusion breaks (block
left/right-net comparison — cheaper than ASTRAN's per-slot check because
blocks precompute their edge nets), gate mismatches (per-column gate-net
comparison), routing span and bounding-box congestion (identical formulas,
cellnetlst.cpp:364-460). Two upgrades over ASTRAN:
  - **Incremental cost evaluation.** ASTRAN recomputes the full cost per move
    (O(nets)); cache per-column net-edge/gate arrays and update only the moved
    segment's affected columns, exactly like the delta the move already
    isolates. This is what makes Python competitive (target: ≥100k moves/s;
    full recompute only at iteration boundaries to assert equality with the
    incremental sum in tests).
  - **PSO outer loop** over SA runs: each particle is an ordering; the swarm
    update proposes which segment to move (velocity = similarity to personal/
    global best orderings), SA refines. All randomness from the seeded
    per-cell RNG (§3); iteration budgets only (§3); swarm/particle counts
    fixed constants. The fitness may add the P0-4/P2-13 routability proxy:
    a cheap track-occupancy estimate from the bounding-box congestion term is
    already in the cost; the `pin_accessibility` on-track/blocked/crowd
    metrics are the second-stage (expensive) filter applied to the top-K
    placements only, never inside the loop.

**C. Graph-based Euler-chain construction** (deterministic initializer for B,
and the fallback when SA regresses). Reference: ASTRAN's dead
`eulerpath()`/`visit` (cellnetlst.cpp:36-193) — a joint P/N trail that pairs
same-gate P/N devices and tolerates up to `trans.size()/2` gaps — recast at
**block granularity** on the diffusion-block graph: nodes = block end-nets,
edges = blocks; find two trails (one per polarity) maximizing (a) same-gate
column pairing between the rows and (b) zero-gap adjacencies, with a bounded
gap budget (breaks) exactly like `visit(nDifs)`. Deterministic backtracking
with a hard node-expansion budget (e.g. 200k expansions) and lexicographic
tie-breaks; on budget exhaustion return the greedy row seeds (§2.1.2). This
constructs in milliseconds what SA needs thousands of moves to find, and is
the natural way to exploit tree/branch blocks.

**Composition** (what actually ships): C seeds → B refines (SA first, PSO×SA
only if the SA result misses the §4 stage-A threshold) → A polishes only when
the cell is small enough that the window model solves in <60 s. ASTRAN's
speculate loop (place → trial route → keep best, autocell2.cpp:187-216) is
kept: the top-K distinct orderings from B get a fast `route_grid` trial and
the best routing cost wins — this is the single highest-value feedback loop
in ASTRAN and it is cheap once the router exists.

### 2.3 Diffusion sharing representation

Inherited verbatim from the block model, which is already ASTRAN-equivalent:
- parallel blocks alternate orientation so every shared edge is same-net
  (netlist.py:247-260) — the §5.37 fix;
- block ends carry `left_net`/`right_net`; two abutting blocks share diffusion
  iff right == left, else a one-column break gap is mandatory
  (layout_model.py:154-177 is the exact constraint; in the SA representation
  this is just the `wGaps` cost term, and the final geometry emitter inserts
  the gap column);
- shared *internal* edges of a block are access columns only for nets exposed
  elsewhere (netlist.py:270-283, `exposed_net_set`) — pure internal nodes need
  no contact;
- gate alignment: a same-gate P/N column pair shares one straight poly stripe
  (gds.py:131-142 already emits merged stripes; the SA `mismatchesGate` term
  rewards producing them).

### 2.4 Routing — a ladder, with the exact encoding's wall stated precisely

**Rung 1 — exact (exists, in flight): `smt_engine.route_model` + M2.**
The 7-track model (route_model.py:74-92) with poly jumps (§5.36) and the M2
escape + via encoding (route_model.py:331-341, 627-658) closes NAND3–NAND6
(6–12 T, regular) with 0 verify violations, M1-only. **Where it dies —
precisely:** model size is O(N²·T·W) from the crossing-safety constraints
(one per net-pair × track × column-gap × 2 sides, route_model.py:537-550)
plus O(N²·W) dual-column rules (route_model.py:489-495) and O(N·W·T²) join
literals (route_model.py:714-835). For a 36 T cell (N≈25 signal nets,
W≈40 columns) that is ≈25·25·7·39·2 ≈ **341k crossing constraints** plus
~42k join groups — far beyond single-worker CP-SAT at a 60 s budget, and the
19-column 14 T COMPLEX0 was already **INFEASIBLE by resources** (every conflict
column carries active diffusion, no legal poly/M1 route; §5.35, §5.36 —
"布局 OPTIMAL 19 列仍不可布"). Numbers to re-measure and pin as the boundary:
rung 1 is *attempted* only when `W ≤ 14` **and** `N ≤ 12` and is given 60 s;
beyond that it is skipped without burning the budget. Its role in stage 3
narrows to **window fixer**: after `route_grid` fails on a local region,
re-run the exact model on a ≤12-column sub-window with stripes outside the
window fixed as blockages.

**Rung 2 — negotiated congestion (new, the workhorse): `route_grid.py`.**
A faithful port of the GraphRouter scheme onto a richer grid, merging
AutoCell::route's per-column element graph (autocell2.cpp:243-474) with
GridRouter's 3-layer structure (M1 horizontal tracks / via1 / M2 vertical-ish
escapes — gridrouter.cpp:33-47 cost triples). Concretely:
- **Grid**: columns = 0.19 µm placement grid (x = column edges, I/O stripes
  and contacts land on track x-positions like the real router's `inoutCnt`
  hub); y = the ~13 M1 tracks from `calcArea`'s rule-derived `trackPos` list
  plus the two supply rails; z ∈ {M1, V1, M2}.
- **Nodes/arcs**: per (column, track): an M1 node with horizontal arcs to its
  x-neighbours (cost 4 in-field / 16 over-diffusion, autocell2.cpp:28-33), a
  poly node per gate column wired across each device's diffusion span (cost 6;
  poly-to-M1 contact arcs cost 20 over diffusion, 500 at I/O hubs,
  autocell2.cpp:41-62), diffusion access nodes per block end (arc 20 to the
  tracks over its span), supply rail nodes, and via arcs M1↔M2. I/O pin
  hubs: a 0-cost `inoutCnt` node per column wired to every track so a pin can
  attach on any track (autocell2.cpp:58-62, 303-309).
- **Solver**: negotiated congestion exactly as `GraphRouter::routeNets`
  (graphrouter.cpp:92-184): route all nets permitting overlap, `history +=
  contested`, cost = arc + history·(users+1), rip-up conflicted nets, ≤8000
  attempts; then ≤2 Steiner sweeps (graphrouter.cpp:185-282). Deterministic
  variants: nets iterated in sorted order; the priority queue breaks cost ties
  by (node id, insertion counter) so equal-cost paths are stable; attempt cap
  fixed (§3).
- **Two-layer honesty**: the port must produce geometry the *existing
  checkers* can consume. `smt_engine/gds.py` already emits M2 + via1 on the
  ASTRAN stream map (gds.py:32-35, 168-182); `route_grid` reuses those
  emitters, so `verify.py`'s BFS (`verify.py:346-452`) — extended with the
  same M1/M2/poly node kinds it already models — remains the structural gate.

**Rung 3 — geometry realization + compaction (reuse stage 1).**
`geometry.py` turns (ordering, route) into the box list: diffusions per block
per row, poly stripes at leg centres, M1/M2/poly wires, contacts, supply
rails drawn inside the cell (invariant 2), pins on grid. `compact_client.py`
serializes the stage-1 JSON model request (boxes + rule families: min-width,
spacing pairs, enclosure, width-grid) and drives the escalation ladder
**unchanged**: strict solve → repair passes to 0 violations (big-M
`RELAXATION` device, final M must be 0 — `tests/unit/test_gds_quality.py`)
→ option-3 drop only on proved INFEASIBLE → conservative retry = give the
router one more track and redo rungs 2–3 (this mirrors autoFlow's
`conservative` loop but the retry *widens* the cell instead of shrinking the
diffusion, fixing the landmine that made ASTRAN's retry counterproductive).
Big cells need exactly this ladder — the 36 T LP already exists at
11.5k-constraint scale and solves better on CP-SAT than CBC (§1.5), so no new
compaction research is required in stage 3.

---

## 3. Determinism strategy (invariant 9)

1. **One seeded RNG per cell, derived from content.** `rng =
   random.Random(hashlib.sha256(f"{spice_text}|{engine_version}").hexdigest())`
   — content-derived (cache contract, invariant 7), version-bumped only when
   the algorithm changes, never `hash()` (PYTHONHASHSEED), never the global
   `random` module. ASTRAN gets its determinism accidentally (unseeded C
   `rand()`); we make it explicit.
2. **Iteration budgets, never wall-clock.** ASTRAN's SA has a 17,500 s
   time-based break (thresholdaccept.h:194) and the adapter a 300 s solve
   cap; a Python engine must not port either into result-affecting code
   paths. All loops terminate on fixed counts: SA iterations (budget scaled
   from `problemSize`, like `num_repetitions`, thresholdaccept.h:94), PSO
   generations, Pathfinder attempts (8000), Steiner sweeps (2), repair
   passes (8), solver `max_time_in_seconds` only as a *safety net whose
   normal-path timeout never binds* — and if it ever binds, the result is
   treated as a failure and the ladder falls back (never "best so far"),
   because a time-limited incumbent is not reproducible across machines.
   CP-SAT keeps `num_search_workers = 1` (layout_model.py:314,
   route_model.py:871 and §5.36(4) document why).
3. **Sorted iteration everywhere.** Every `set`/`dict` crossing into model
   construction, tie-breaking, cost accumulation order, or output emission is
   `sorted()` (the §5.36(4) class of bug). Tie-breaks in every "pick best"
   are `(cost, canonical key)` with canonical keys derived from device/net
   names, never insertion order.
4. **Solver-layer contracts carried over**: FEASIBLE counts as success
   (invariant 4); all-zero solutions are failures, never shipped (0 × 0
   discipline); expression-naming constraints of the LP are a stage-1
   concern but stage 3 asserts its JSON request never emits expression-valued
   column names (invariant 3).
5. **Enforcement**: `tests/unit/test_determinism.py` gains a bigcell case —
   two full runs of a 22 T and a 36 T cell in one process with different
   `PYTHONHASHSEED` must produce byte-identical ordering, route, and GDS.

---

## 4. Quality gates and acceptance thresholds

**Fixed benchmark set** (never re-picked after gate definition):
- `flow/original_astran_cells` — the 20-cell GSCL45 ASTRAN baseline
  (invariant 10's matched-geometry baseline);
- `flow/outputs/{adder,ctrl,max,multiplier}/COMPLEX*` — 15 cells, 6–36 T;
  the **big-cell subset** is the 12 cells ≥ 14 T (§1.6 table).

**Measurement protocol** (one script, committed):
1. Regenerate every cell three times with the engine under test (fresh
   process each time); assert byte-identical outputs across runs (§3.5).
2. **Width** = the engine's reported width in grid columns × 0.19 µm for the
   candidate, and the `.Astranlog`-recorded width for ASTRAN — same
   row height 2.47 µm on both sides (invariants 1/10; the SMT batch table in
   §5.37 is the template, including its transistor-count freshness check).
3. **DRC/structure**: `layout_sanity.check_layout` must pass (0 violations,
   height ≈ 2.47 ± 5 %, width on grid, VCC/GND labels); the compaction
   repair ladder must end at 0 spacing violations (`test_gds_quality`
   semantics); `smt_engine.verify.verify_cell` (extended for M2/poly as in
   §2.4) must report 0 violations — it is the LVS-flavoured gate that caught
   §5.36's shipped-grade defect.
4. **Pin accessibility**: `flow/pin_accessibility.py` score per cell
   (on-track/blocked/crowd). Reference band: ASTRAN snapshots score
   0.325–0.536 (AUDIT §5.38); the engine must beat, not match, this weak
   band on average.

**Acceptance thresholds** (ladder stages; a stage passes only with 100 % of
cells routed, verified, DRC-clean — a single 0 × 0 or verify violation fails
the stage):

| Stage | Width vs ASTRAN (big-cell subset) | Pin access | Exit criteria |
|---|---|---|---|
| **A — parity** | median ≤ +25 %; worst cell ≤ +50 % | ≥ ASTRAN per-cell − 0.1 | engine trustworthy enough to shadow-run in reports |
| **B — competitive** | median ≤ +10 %; ≥ 50 % of cells ≤ ASTRAN (win or tie); worst ≤ +25 % | ≥ ASTRAN median | engine eligible as `auto` middle rung with ASTRAN fallback |
| **C — retire** | median ≤ ASTRAN; worst ≤ +15 %; ≥ 60 % wins | ≥ ASTRAN median | ASTRAN demoted to archived baseline generator |

Gate A additionally requires the small/regular cells (NAND2–NAND6 via
`smt`, and the 6–12 T COMPLEX cells) to keep closing through the existing
path — stage 3 must not regress rung 1's territory.

---

## 5. Migration plan

Tied to stage 2's per-cell flag (`--engine auto|smt|astran`); stage 3 adds
`bigcell` and defines `auto` as the ladder **smt → bigcell → astran**:

1. **Shadow mode (report-only).** `regenerate_cells.py`/`verilog2cells.py`
   gain `--engine-report bigcell`: run the bigcell engine beside ASTRAN,
   emit a comparison table (widths, pin access, verify status, wall-clock)
   into the run report. No snapshot changes. Exit: gate A data collected on
   all 15 COMPLEX cells.
2. **`--engine bigcell` explicit.** Opt-in per cell; outputs land in the
   normal `outputs/<bench>/COMPLEX*` slots with a manifest field recording
   the engine (the queue manifest already records per-cell provenance,
   `flow/astran_queue.py`). Snapshot regeneration stays a single coherent
   commit per AGENTS.md ("result set is tracked"). Exit: gate B met on the
   big-cell subset; adder benchmark fully regenerated through
   `auto` with zero ASTRAN fallbacks.
3. **`auto` flips the ladder order for >12 T cells.** Selection rule in
   `auto`: ≤12 T and regular → `smt`; >12 T or irregular → `bigcell`;
   `astran` only on explicit request or explicit fallback trigger
   (bigcell stage failure: layout UNKNOWN, route failure after ladder
   exhaustion, verify/sanity violation — same loud-failure semantics as the
   0 × 0 detection, never silent). ASTRAN remains installed and CI-exercised
   (`pytest -m slow`) throughout — it is the baseline generator for §4 and
   the fallback, not dead code.
4. **Default flip** (gate C met): `auto`'s final fallback becomes a warning,
   ASTRAN runs move behind an env flag for reproducibility archaeology, and
   `tools/astran` is archived (kept vendored, no longer on the critical
   path). The GUI's ASTRAN-failure messaging (`flow_core._popen_astran`,
   360 Total Security guidance) becomes legacy-path-only.

Rollout order minimizes risk: shadow → opt-in → auto-middle → default, each
step reversible by config, each step's evidence appended to
`doc/AUDIT_REPORT.md` (the engineering-log requirement).

---

## 6. Effort estimates and top risks

**Person-weeks** (1 pw = one engineer-week; assumes stage-1 compaction JSON
exists before item 5 starts):

| Component | Estimate | Notes |
|---|---|---|
| `netlist_ext.py` (folding, tree blocks, row seeds) | 1.5–2 | property tests over all 15 `.sp` |
| `place_euler.py` (block-granularity Euler chains) | 2 | bounded-backtracking; reference cellnetlst.cpp:36-193 |
| `place_sa.py` (SA + incremental cost, then PSO×SA) | 3–4 | incremental evaluator is the hard, test-heavy part |
| `place_windows.py` (CP-SAT evaluation + polish) | 1.5–2 | mostly plumbing around `layout_model` |
| `route_grid.py` (Pathfinder port, 3-layer grid) | 4–5 | largest single item; port of graphrouter + autocell2 graph builder |
| `route_exact.py` (window fixer) | 0.5–1 | thin wrapper over `route_model` |
| `geometry.py` + `gds.py` extension | 2 | reuse `smt_engine/gds.py`; irregular cells need tree-block emission |
| `compact_client.py` + repair-ladder glue | 1–2 | depends on stage-1 landing |
| verification/gates (verify extension, threshold script) | 1.5–2 | extends `verify.py` + batch table tooling |
| migration tooling (flag, report mode, manifest) | 1 | |
| **Total** | **≈ 18–22 pw** | +30 % contingency → 24–29 pw |

**Top risks and mitigations:**

1. **Python SA throughput** (the 36 T cell needs ~10⁶–10⁷ cost evaluations
   to match ASTRAN's budget). *Mitigation:* incremental cost evaluation with
   a full-recompute assertion in tests; the Euler constructor (C) supplies
   ASTRAN-unachievable starting points so fewer moves are needed; iteration
   budgets are set by *measured convergence* on the benchmark, not by
   copying ASTRAN's 150× problemSize constant. If still short, restrict PSO
   to ≤22 T cells and rely on CP-SAT windows for the tail.
2. **Routing quality parity** — ASTRAN's negotiated router is tuned (arc
   costs 4/16/6/20/495, 8000 attempts, Steiner sweeps) and the exact model's
   infeasibility boundary (§2.4) means the heuristic router has no safety
   net on big irregular cells. *Mitigation:* port the cost table verbatim
   first, tune only with benchmark evidence; keep the exact window fixer as
   the targeted net; fall back to ASTRAN per cell (the ladder exists for
   exactly this).
3. **Hidden semantic traps in the geometry layer** — the project history
   (§5.35–5.38) shows the model/checker gap, not the solver, is where
   shipped-grade defects lived (P/N half-cell disconnection, floating gate
   contacts, foreign-gate poly shorts). *Mitigation:* no geometry is emitted
   without `verify.py` + `layout_sanity` + the repair-ladder-zero rule;
   every new trap found becomes a regression test (the established
   `doc/AUDIT_REPORT.md` discipline).

---

## 7. Open questions

1. **Track budget for `route_grid`**: ASTRAN derives ~13 M1 tracks from
   `.rul` rules (`calcArea`). Should the Python engine re-derive from
   `tech_freePDK45.rul` (single source of truth) or fix the track list as
   engine constants? (Recommending: re-derive, with a parity test against
   ASTRAN's `trackPos` on one cell.)
2. **I/O pin placement policy**: ASTRAN puts pins on any track via the
   `inoutCnt` hub and aligns them to the grid at export
   (autocell2.cpp:639-645). The exact engine instead pins stripes
   (gds.py:244-280). Which pin convention does the big-cell engine adopt for
   `pin_accessibility` on-track scoring — and does the P1-9 port-order
   variability (±100 % width swings) justify a port-variant loop here?
3. **Tree/branch block granularity**: is one DFS-flattened block per branchy
   component enough, or do we need the Euler trail to cut branches at access
   columns (i.e., a block that is a *path cover* of the component)? Decide
   with the adder/COMPLEX10 and multiplier/COMPLEX7 netlists before writing
   `place_euler.py`.
4. **PSO necessity**: if plain SA + Euler seeds passes gate B on all 12
   big cells, ship without the swarm (one less stochastic layer to pin
   down). The PSO×SA template stays in the roadmap (P2-13) as the reserve.
5. **Compaction budget for big cells**: the 36 T LP already needs minutes
   under CBC and the adapter caps at 300 s; does stage 3 need the CP-SAT
   backend promoted to default for bigcell runs only (evidence: COMPLEX1
   CBC collapse, §1.5), or does python-mip with the same 2 % gap suffice?
6. **Multi-row-height variants**: P1-11 (double-height cells for >20 T)
   could fold into the bigcell engine almost free (row count is a
   parameter). In scope or explicitly deferred? (Recommending: defer; keep
   H = 2.47 invariant until gate C, then evaluate.)
