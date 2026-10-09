"""Routability metrics for generated cells (roadmap P0-4).

Width alone says nothing about how hard a cell is to route: a narrow
cell whose pins and in-cell wires saturate every track loses its area
win in detailed routing (Routability Booster, ISPD'24; Cell-Flex,
ISPD'25).  ASTRAN's own router already emits the signals we need, so
the metric is parsed from the cell's .Astranlog -- no extra tool run:

    -> Routing finished in 35 attempts after 0.542 s
    -> Final cost: Width=33; Gate Mismatches=4; WL=64; Rt. Density=5; Nr. Gaps=4

``rt_density`` is the placer's worst-track congestion estimate (the
"Rt. Density" cost component), ``routing_attempts`` the number of
Pathfinder rip-up/reroute rounds the final route needed.  Both grow
with routing difficulty; the score combines them with the structural
warnings (gate mismatches, diffusion gaps).
"""

import os
import re

_FINAL_COST_RE = re.compile(
    r"->\s*Final cost:\s*Width=(\d+);\s*Gate Mismatches=(\d+);\s*WL=(\d+);"
    r"\s*Rt\. Density=(\d+);\s*Nr\. Gaps=(\d+)")
_ROUTING_RE = re.compile(r"->\s*Routing finished in (\d+) attempts")


class RoutabilityMetrics(object):
    def __init__(self, width_tracks, gate_mismatches, wirelength,
                 rt_density, gaps, routing_attempts):
        self.width_tracks = width_tracks
        self.gate_mismatches = gate_mismatches
        self.wirelength = wirelength
        self.rt_density = rt_density
        self.gaps = gaps
        self.routing_attempts = routing_attempts

    def score(self):
        """Scalar routing-difficulty proxy (higher = harder to route).

        The worst-track density dominates; structural defects (mismatched
        gates, diffusion gaps) add friction; long rip-up chains are the
        tie-breaker.  Weights are deliberately simple and documented so
        the number stays explainable.
        """
        return (self.rt_density
                + 0.5 * self.gate_mismatches
                + 0.25 * self.gaps
                + 0.05 * self.routing_attempts)

    def as_dict(self):
        return {
            "width_tracks": self.width_tracks,
            "gate_mismatches": self.gate_mismatches,
            "wirelength": self.wirelength,
            "rt_density": self.rt_density,
            "gaps": self.gaps,
            "routing_attempts": self.routing_attempts,
            "score": self.score(),
        }


def parse_astran_log_routability(log_path):
    """Parse routability metrics from an ASTRAN log; None when absent."""
    if (not os.path.exists(log_path)):
        return None
    final_cost = None
    attempts = []
    with open(log_path, 'r', errors="ignore") as f:
        for line in f:
            m = _FINAL_COST_RE.search(line)
            if (m):
                # keep the LAST Final cost line: the accepted track count's
                final_cost = tuple(int(g) for g in m.groups())
            m = _ROUTING_RE.search(line)
            if (m):
                attempts.append(int(m.group(1)))
    if (final_cost is None):
        return None
    width_tracks, gate_mismatches, wirelength, rt_density, gaps = final_cost
    return RoutabilityMetrics(
        width_tracks, gate_mismatches, wirelength, rt_density, gaps,
        max(attempts) if attempts else 0)


def load_cell_routability(gds_path, cell_name):
    """Convenience wrapper: metrics for <gds_path>/<cell_name>.Astranlog."""
    return parse_astran_log_routability(
        os.path.join(gds_path, cell_name + ".Astranlog"))
