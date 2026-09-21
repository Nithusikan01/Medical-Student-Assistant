"""
Comparing two evaluation runs.

This is what makes the rest of the package worth having. A single report
says almost nothing on its own - Recall@5 of 0.71 is neither good nor
bad without something to hold it against. Two reports say whether a
change helped, which is the only question anybody actually asks.

The same machinery covers both remaining jobs:

  - **Experiment tracking.** Same dataset, two configurations. Did
    raising candidate_k help, or just cost more?
  - **Drift.** Same dataset, same configuration, two points in time. If
    the numbers moved and the configuration did not, the corpus did -
    documents were added, removed, or re-chunked.

Those are distinguished by what changed, not by different code, which is
why this module reports configuration differences alongside metric
differences rather than leaving them for a reader to notice.
"""

from dataclasses import dataclass, field
from typing import Any

from rag.evaluation.schemas import EvaluationReport

# Below this, a difference is noise. Retrieval over a small labelled set
# moves by a percent or two between runs for reasons that have nothing to
# do with the change being tested, and calling that an improvement is how
# a tuning session convinces itself of things that are not true.
DEFAULT_SIGNIFICANCE = 0.01


@dataclass(frozen=True, slots=True)
class MetricDelta:
    metric: str

    baseline: float | None
    candidate: float | None

    @property
    def delta(self) -> float | None:
        """None when either side is missing - not zero."""

        if self.baseline is None or self.candidate is None:
            return None

        return self.candidate - self.baseline

    def direction(self, significance: float = DEFAULT_SIGNIFICANCE) -> str:
        change = self.delta

        if change is None:
            return "unknown"

        if abs(change) < significance:
            return "unchanged"

        return "better" if change > 0 else "worse"


@dataclass(frozen=True, slots=True)
class Comparison:
    dataset: str

    metrics: tuple[MetricDelta, ...]
    config_changes: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    comparable: bool = True
    note: str = ""

    def improved(self, significance: float = DEFAULT_SIGNIFICANCE) -> list[MetricDelta]:
        return [
            metric
            for metric in self.metrics
            if metric.direction(significance) == "better"
        ]

    def regressed(
        self, significance: float = DEFAULT_SIGNIFICANCE
    ) -> list[MetricDelta]:
        return [
            metric
            for metric in self.metrics
            if metric.direction(significance) == "worse"
        ]

    @property
    def looks_like_drift(self) -> bool:
        """
        Metrics moved while the configuration stayed put.

        Which means the corpus changed underneath: documents added,
        removed, or re-chunked. Worth naming, because the instinct on
        seeing a regression is to look at the code that was not touched.
        """

        return bool(self.regressed()) and not self.config_changes


def compare(
    baseline: EvaluationReport,
    candidate: EvaluationReport,
    *,
    significance: float = DEFAULT_SIGNIFICANCE,
) -> Comparison:
    """
    What changed between two runs.

    Comparing reports from different datasets is refused rather than
    computed. The arithmetic would work and the answer would be
    meaningless, which is the more dangerous kind of wrong.
    """

    if baseline.dataset != candidate.dataset:
        return Comparison(
            dataset=candidate.dataset,
            metrics=(),
            comparable=False,
            note=(
                f"Reports are from different datasets ('{baseline.dataset}' "
                f"and '{candidate.dataset}'); the comparison would be "
                "arithmetic without meaning."
            ),
        )

    names: list[str] = list(baseline.summary)

    for name in candidate.summary:
        if name not in names:
            names.append(name)

    metrics = tuple(
        MetricDelta(
            metric=name,
            baseline=baseline.summary.get(name),
            candidate=candidate.summary.get(name),
        )
        for name in names
    )

    changes: dict[str, tuple[Any, Any]] = {}

    for key in set(baseline.config) | set(candidate.config):
        before = baseline.config.get(key)
        after = candidate.config.get(key)

        if before != after:
            changes[key] = (before, after)

    return Comparison(
        dataset=candidate.dataset,
        metrics=metrics,
        config_changes=changes,
    )
