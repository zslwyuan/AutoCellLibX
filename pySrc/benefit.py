"""Benefit estimation for pattern growth (roadmap P0-3).

Growth used to merge the single most frequent neighbour class and learn
only *after* a 5-10 minute ASTRAN run whether the grown shape pays off
(COMPLEX10 on adder came out wider than the sum of its parts: 5.89 vs
4.94 um, -56.05 um^2 across 59 occurrences).

The estimator here predicts a branch's benefit before any layout run:

    est_benefit = occurrences * orig_width * (1 - est_shrink(new_size))

where ``orig_width`` is the sum of the member cells' ASTRAN baseline
widths plus the candidate neighbour's width, and ``est_shrink`` comes
from a ShrinkModel that is calibrated *online*: every finished layout
contributes an observed shrink factor (new_width / baseline_width) for
its cell count, and estimates use the worst (max) factor observed at
that size -- a deliberately conservative rule, since a wrong veto costs
a pattern while a wrong pass costs another ASTRAN run.  Unseen sizes
fall back to ``prior``.

Empirical anchors from outputs/adder (baseline sum -> generated width):
3 cells (COMPLEX1)  4.37 -> 4.37  shrink 1.00
4 cells (COMPLEX9)  3.99 -> 3.61  shrink 0.905
5 cells (COMPLEX10) 4.94 -> 5.89  shrink 1.19  <- would be pruned after
                                                    one observation
"""


class ShrinkModel(object):
    """Size-dependent width-shrink factor, calibrated online per run."""

    def __init__(self, prior=0.95):
        self.prior = prior
        self.samples = {}            # size -> [new_width / baseline_width]

    def observe(self, size, baselineWidth, newWidth):
        if (baselineWidth > 0 and newWidth > 0):
            self.samples.setdefault(size, []).append(
                newWidth / baselineWidth)

    def estimateShrink(self, size):
        observed = self.samples.get(size)
        if (observed):
            # Conservative: assume the worst layout we have seen at this
            # size, not the average.
            return max(observed)
        return self.prior

    def estimateBenefit(self, memberWidths, addedWidth, newSize,
                        occurrences):
        """Estimated total width saved by growing ``occurrences`` clusters
        of ``memberWidths`` + one ``addedWidth`` neighbour."""
        origWidth = sum(memberWidths) + addedWidth
        return occurrences * (origWidth
                              - self.estimateShrink(newSize) * origWidth)


def makeGrowthBenefitEstimator(stdType2AstranArea, shrinkModel):
    """Closure with the call signature grow_sequence_of_clusters expects."""
    def estimate(memberTypeNames, neighborTypeName, newSize, occurrences):
        try:
            memberWidths = [stdType2AstranArea[t] for t in memberTypeNames]
            addedWidth = stdType2AstranArea[neighborTypeName]
        except KeyError:
            # Unknown width -> no opinion; do not veto the branch.
            return float("inf")
        return shrinkModel.estimateBenefit(
            memberWidths, addedWidth, newSize, occurrences)
    return estimate
