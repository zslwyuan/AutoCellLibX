
bypassTypes = ["DFF", "bool"]

# Beam width of the pattern-growth loop (P0-3): how many queue heads are
# grown per round.  1 reproduces the legacy single-head behaviour.
growBeamWidth = 2

# Routability gate (P0-4): a candidate whose worst-track routing density
# (ASTRAN's own "Rt. Density" cost) exceeds this is excluded from the
# savings.  None disables the gate (metrics are still computed and
# reported) -- measure first, gate deliberately.
routabilityDensityGate = None

# Layout sanity gate (P2 phase 0): structurally broken layouts (degenerate,
# wrong row height, off-grid, missing layers/supply labels) are excluded
# from the savings.  These are unambiguous failures, so the gate defaults
# to on.
layoutSanityGate = True

