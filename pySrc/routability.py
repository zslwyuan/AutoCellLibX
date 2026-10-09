"""Routability metrics for generated cells (roadmap P0-4).

Width alone says nothing about how hard a cell is to route: a narrow
cell whose pins and in-cell wires saturate every track loses its area
win in detailed routing (Routability Booster, ISPD'24; Cell-Flex,
ISPD'25).  ASTRAN's own router already emits the signals we need, so
the metric is parsed from the cell's .Astranlog -- no extra tool run:

    -> Routing finished in 35 attempts after 0.542 s
    -> Final cost: Width=33; Gate Mismatches=4; WL=64; Rt. Density=5; Nr. Gaps=4

``rtDensity`` is the placer's worst-track congestion estimate (the
"Rt. Density" cost component), ``routingAttempts`` the number of
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
    def __init__(self, widthTracks, gateMismatches, wirelength,
                 rtDensity, gaps, routingAttempts):
        self.widthTracks = widthTracks
        self.gateMismatches = gateMismatches
        self.wirelength = wirelength
        self.rtDensity = rtDensity
        self.gaps = gaps
        self.routingAttempts = routingAttempts

    def score(self):
        """Scalar routing-difficulty proxy (higher = harder to route).

        The worst-track density dominates; structural defects (mismatched
        gates, diffusion gaps) add friction; long rip-up chains are the
        tie-breaker.  Weights are deliberately simple and documented so
        the number stays explainable.
        """
        return (self.rtDensity
                + 0.5 * self.gateMismatches
                + 0.25 * self.gaps
                + 0.05 * self.routingAttempts)

    def asDict(self):
        return {
            "width_tracks": self.widthTracks,
            "gate_mismatches": self.gateMismatches,
            "wirelength": self.wirelength,
            "rt_density": self.rtDensity,
            "gaps": self.gaps,
            "routing_attempts": self.routingAttempts,
            "score": self.score(),
        }


def parseAstranLogRoutability(logPath):
    """Parse routability metrics from an ASTRAN log; None when absent."""
    if (not os.path.exists(logPath)):
        return None
    finalCost = None
    attempts = []
    with open(logPath, 'r', errors="ignore") as f:
        for line in f:
            m = _FINAL_COST_RE.search(line)
            if (m):
                # keep the LAST Final cost line: the accepted track count's
                finalCost = tuple(int(g) for g in m.groups())
            m = _ROUTING_RE.search(line)
            if (m):
                attempts.append(int(m.group(1)))
    if (finalCost is None):
        return None
    widthTracks, gateMismatches, wirelength, rtDensity, gaps = finalCost
    return RoutabilityMetrics(
        widthTracks, gateMismatches, wirelength, rtDensity, gaps,
        max(attempts) if attempts else 0)


def loadCellRoutability(gdsPath, cellName):
    """Convenience wrapper: metrics for <gdsPath>/<cellName>.Astranlog."""
    return parseAstranLogRoutability(
        os.path.join(gdsPath, cellName + ".Astranlog"))
