
bypass_types = ["DFF", "bool"]

# Beam width of the pattern-growth loop (P0-3): how many queue heads are
# grown per round.  1 reproduces the legacy single-head behaviour.
grow_beam_width = 2

# Routability gate (P0-4): a candidate whose worst-track routing density
# (ASTRAN's own "Rt. Density" cost) exceeds this is excluded from the
# savings.  None disables the gate (metrics are still computed and
# reported) -- measure first, gate deliberately.
routability_density_gate = None

# Layout sanity gate (P2 phase 0): structurally broken layouts (degenerate,
# wrong row height, off-grid, missing layers/supply labels) are excluded
# from the savings.  These are unambiguous failures, so the gate defaults
# to on.
layout_sanity_gate = True

# Width proxy for growth pruning (P2 phase 1): replace the ShrinkModel
# estimator with the learned width proxy.  Off by default -- LOO MAPE is
# ~16% on the current 12-sample corpus and it overestimates compact
# shapes (would have vetoed COMPLEX9), so it is report-only until more
# training layouts exist.
use_width_proxy_for_growth = False

# Synthesis-reuse gate (AUDIT 5.25): when set, only single-output patterns
# with simple common functions (support<=4, depth<=2) are accepted -- the
# only class abc's cone-driven mapping can ever pick up.  Off by default:
# it would exclude every current adder pattern (all multi-output).
require_reuse_eligible = False

