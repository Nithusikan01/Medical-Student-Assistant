"""
Retrieval quality metrics.

These are the numbers the operational dashboard deliberately does not
report, and cannot: Recall@K, Precision@K, MRR and nDCG all compare what
was retrieved against what *should* have been retrieved, and production
logs contain only the first half. No amount of traffic turns one into
the other.

So everything here takes two arguments - a ranking and a set of known
relevant ids - and nothing here can be computed from a trace.

Relevance is binary. Graded relevance would be more expressive and much
harder to label consistently, and a labelling scheme nobody applies the
same way twice produces numbers that move for reasons unrelated to the
system. If graded labels ever exist, nDCG is the one function here that
would need more than a threshold change.
"""

import math
from collections.abc import Iterable, Sequence


def _top(ranking: Sequence[str], k: int) -> list[str]:
    if k <= 0:
        return []

    return list(ranking[:k])


def recall_at_k(
    ranking: Sequence[str],
    relevant: Iterable[str],
    k: int,
) -> float | None:
    """
    The share of known-relevant items that appear in the top k.

    None when nothing is labelled relevant, because a share of nothing is
    undefined. Returning 0.0 there would count an unlabelled example as a
    complete miss and quietly drag the average down - which is how an
    evaluation set silently becomes a lie about the system.
    """

    truth = set(relevant)

    if not truth:
        return None

    found = truth.intersection(_top(ranking, k))

    return len(found) / len(truth)


def precision_at_k(
    ranking: Sequence[str],
    relevant: Iterable[str],
    k: int,
) -> float | None:
    """
    The share of the top k that is relevant.

    None when k is zero or nothing was retrieved: there is no denominator.
    Note that this is capped by how many relevant items exist - with two
    labelled chunks, Precision@5 cannot exceed 0.4, which is a property of
    the metric and not a finding about retrieval.
    """

    truth = set(relevant)
    top = _top(ranking, k)

    if not top:
        return None

    return len(truth.intersection(top)) / len(top)


def reciprocal_rank(ranking: Sequence[str], relevant: Iterable[str]) -> float:
    """
    1/rank of the first relevant item, or 0 when none was retrieved.

    Zero is correct here rather than None: "no relevant result anywhere in
    the ranking" is a real, meaningful outcome, not missing data.
    """

    truth = set(relevant)

    for position, chunk_id in enumerate(ranking, start=1):
        if chunk_id in truth:
            return 1.0 / position

    return 0.0


def average_precision(ranking: Sequence[str], relevant: Iterable[str]) -> float | None:
    """
    Mean of the precisions at each rank where a relevant item was found.

    Rewards putting relevant items early, unlike Recall@K which only asks
    whether they are inside the window at all.
    """

    truth = set(relevant)

    if not truth:
        return None

    hits = 0
    total = 0.0

    for position, chunk_id in enumerate(ranking, start=1):
        if chunk_id in truth:
            hits += 1
            total += hits / position

    return total / len(truth)


def ndcg_at_k(
    ranking: Sequence[str],
    relevant: Iterable[str],
    k: int,
) -> float | None:
    """
    Discounted cumulative gain at k, normalised against the ideal ranking.

    The one metric here that is rank-aware *and* bounded, which makes it
    the fairest single number for comparing two retrieval configurations -
    Recall@K cannot tell a relevant chunk at position 1 from one at
    position 10.
    """

    truth = set(relevant)

    if not truth or k <= 0:
        return None

    gain = sum(
        1.0 / math.log2(position + 1)
        for position, chunk_id in enumerate(_top(ranking, k), start=1)
        if chunk_id in truth
    )

    ideal = sum(
        1.0 / math.log2(position + 1) for position in range(1, min(len(truth), k) + 1)
    )

    return gain / ideal if ideal else None


def mean(values: Iterable[float | None]) -> float | None:
    """
    Average of the values that exist, ignoring the ones that do not.

    None in, skipped - never counted as zero. That distinction is the
    whole reason the functions above return None rather than 0.0.
    """

    present = [value for value in values if value is not None]

    return sum(present) / len(present) if present else None
