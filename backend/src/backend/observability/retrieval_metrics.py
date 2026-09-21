"""
What retrieval is doing, aggregated across requests.

Everything here is an **online operational metric** in the sense of section
54: measured from real traffic, no ground truth needed. None of it says
whether retrieval was *good*.

That distinction is the whole reason this module does not compute Recall@K,
Precision@K, MRR or nDCG. Those need a set of questions with known-correct
documents, which production logs do not contain - a chunk's similarity score
says how close it was in embedding space, not whether it answered anything.
Section 20 is explicit that production retrieval logs alone cannot produce
them, and manufacturing a number called "Recall@5" from this data would be
inventing a metric the data cannot support.

What these numbers *can* answer:

- has one half of hybrid retrieval quietly stopped contributing?
- how often does reranking fall back, or give up entirely?
- does reranking actually change the selection it costs a second to produce?
- are similarity scores drifting?
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from backend.observability.aggregation import percentile

# The stages this module reads. Anything else in a trace is irrelevant here.
RETRIEVAL_STAGES = (
    "retrieval",
    "dense_retrieval",
    "bm25_retrieval",
    "fusion",
    "reranking",
)

RETRIEVER_STAGES = ("dense_retrieval", "bm25_retrieval")

# Read on its own rather than added to RETRIEVAL_STAGES: the cache sits in
# front of retrieval and its spans are the record of retrieval that did
# *not* happen, which is the opposite of what the report above measures.
CACHE_STAGE = "cache_lookup"


@dataclass(frozen=True, slots=True)
class Distribution:
    """A numeric field summarised across calls."""

    count: int = 0
    mean: float | None = None
    p50: float | None = None
    p95: float | None = None
    minimum: float | None = None
    maximum: float | None = None


def summarize(values: Iterable[Any]) -> Distribution:
    """
    Distribution of one metadata field.

    Non-numeric and missing values are skipped rather than coerced: a span
    that did not record a field must not contribute a zero, which would drag
    every average toward it.
    """

    numbers = sorted(
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    )

    if not numbers:
        return Distribution()

    return Distribution(
        count=len(numbers),
        mean=sum(numbers) / len(numbers),
        p50=percentile(numbers, 0.5),
        p95=percentile(numbers, 0.95),
        minimum=numbers[0],
        maximum=numbers[-1],
    )


@dataclass(frozen=True, slots=True)
class RetrieverSummary:
    stage: str
    calls: int

    # How often this retriever came back with nothing. The single most
    # useful number here: a BM25 half that has silently stopped matching
    # shows up as an empty rate climbing toward 1, while every other
    # retrieval metric still looks healthy.
    empty_calls: int
    empty_rate: float

    result_count: Distribution
    top_score: Distribution
    average_score: Distribution


@dataclass(frozen=True, slots=True)
class FusionSummary:
    calls: int

    # Section 19's breakdown: of the chunks entering fusion, what share came
    # from one retriever only, and what share both agreed on.
    dense_only_share: float | None
    bm25_only_share: float | None
    overlap_share: float | None

    # Calls where one retriever contributed nothing at all - hybrid
    # retrieval degraded to a single retriever without anything failing.
    single_retriever_calls: int
    single_retriever_rate: float

    overlap_count: Distribution
    unique_count: Distribution


@dataclass(frozen=True, slots=True)
class RerankingSummary:
    calls: int

    # Which implementation actually answered, and how often. Populated by
    # FallbackReranker annotating its span.
    reranker_usage: dict[str, int] = field(default_factory=dict)

    degraded_calls: int = 0
    degraded_rate: float = 0.0

    # Whether reranking changed the selection it costs latency to produce.
    # Not a quality claim - a change is not necessarily an improvement, and
    # only an evaluation set can say which.
    changed_calls: int = 0
    change_rate: float = 0.0

    candidate_count: Distribution = field(default_factory=Distribution)
    final_count: Distribution = field(default_factory=Distribution)
    introduced_count: Distribution = field(default_factory=Distribution)
    reordered_count: Distribution = field(default_factory=Distribution)
    top_score: Distribution = field(default_factory=Distribution)

    # How deep into the candidate pool reranking actually reached.
    #
    # The tuning signal for candidate_k. Retrieval fetches candidate_k
    # chunks and reranking scores all of them; if max_promoted_rank sits
    # far below candidate_k across a window, the remainder were retrieved
    # and scored for nothing, and the pool can shrink. If it presses
    # against candidate_k, good chunks are being cut off before the
    # reranker sees them and the pool should grow.
    max_promoted_rank: Distribution = field(default_factory=Distribution)
    mean_promoted_rank: Distribution = field(default_factory=Distribution)
    unused_candidate_depth: Distribution = field(default_factory=Distribution)


@dataclass(frozen=True, slots=True)
class CacheSummary:
    """
    How often the response cache saved the work.

    `hit_rate` is None when nothing was looked up, never 0.0: a share of
    nothing is undefined, and 0% would read as "the cache never worked"
    rather than "nobody asked it anything".
    """

    calls: int = 0
    hits: int = 0
    hit_rate: float | None = None

    # Split because the two say different things: exact hits mean the same
    # question is being asked again, semantic hits mean it is being asked
    # in different words. A collapse in the semantic share is the sign the
    # threshold has been set too high.
    exact_hits: int = 0
    semantic_hits: int = 0

    similarity: Distribution = field(default_factory=Distribution)
    entry_count: Distribution = field(default_factory=Distribution)


def summarize_cache(rows: Sequence[dict]) -> CacheSummary | None:
    if not rows:
        return None

    hits = [row for row in rows if row.get("hit") is True]

    return CacheSummary(
        calls=len(rows),
        hits=len(hits),
        hit_rate=len(hits) / len(rows),
        exact_hits=sum(1 for row in hits if row.get("match") == "exact"),
        semantic_hits=sum(1 for row in hits if row.get("match") == "semantic"),
        # Only hits carry one, so a miss must not drag the distribution
        # toward zero.
        similarity=summarize(_field(hits, "similarity")),
        entry_count=summarize(_field(rows, "entry_count")),
    )


@dataclass(frozen=True, slots=True)
class RetrievalReport:
    retrievers: list[RetrieverSummary]
    fusion: FusionSummary | None
    reranking: RerankingSummary | None
    cache: CacheSummary | None = None


# ----------------------------------------------------------------------


def _field(rows: Sequence[dict], name: str) -> list[Any]:
    return [row.get(name) for row in rows if name in row]


def _by_stage(spans: Sequence[tuple[str, dict]]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}

    for stage, meta in spans:
        grouped.setdefault(stage, []).append(meta or {})

    return grouped


def summarize_retriever(stage: str, rows: Sequence[dict]) -> RetrieverSummary:
    counts = _field(rows, "result_count")

    empty = sum(1 for value in counts if value == 0)

    return RetrieverSummary(
        stage=stage,
        calls=len(rows),
        empty_calls=empty,
        empty_rate=empty / len(rows) if rows else 0.0,
        result_count=summarize(counts),
        top_score=summarize(_field(rows, "top_score")),
        average_score=summarize(_field(rows, "average_score")),
    )


def summarize_fusion(rows: Sequence[dict]) -> FusionSummary | None:
    if not rows:
        return None

    dense_only = sum(row.get("dense_only_count", 0) or 0 for row in rows)
    bm25_only = sum(row.get("bm25_only_count", 0) or 0 for row in rows)
    overlap = sum(row.get("overlap_count", 0) or 0 for row in rows)

    total = dense_only + bm25_only + overlap

    single = sum(
        1
        for row in rows
        if (row.get("dense_count", 0) or 0) == 0 or (row.get("bm25_count", 0) or 0) == 0
    )

    return FusionSummary(
        calls=len(rows),
        # None rather than zero when nothing was retrieved at all: a share of
        # nothing is undefined, not 0%.
        dense_only_share=(dense_only / total) if total else None,
        bm25_only_share=(bm25_only / total) if total else None,
        overlap_share=(overlap / total) if total else None,
        single_retriever_calls=single,
        single_retriever_rate=single / len(rows),
        overlap_count=summarize(_field(rows, "overlap_count")),
        unique_count=summarize(_field(rows, "unique_count")),
    )


def summarize_reranking(rows: Sequence[dict]) -> RerankingSummary | None:
    if not rows:
        return None

    usage: dict[str, int] = {}

    for row in rows:
        used = row.get("reranker_used")

        if used:
            usage[str(used)] = usage.get(str(used), 0) + 1

    degraded = sum(1 for row in rows if row.get("reranker_degraded") is True)

    changed = sum(
        1
        for row in rows
        if (row.get("introduced_count", 0) or 0) > 0
        or (row.get("reordered_count", 0) or 0) > 0
    )

    return RerankingSummary(
        calls=len(rows),
        reranker_usage=dict(
            sorted(usage.items(), key=lambda item: item[1], reverse=True)
        ),
        degraded_calls=degraded,
        degraded_rate=degraded / len(rows),
        changed_calls=changed,
        change_rate=changed / len(rows),
        candidate_count=summarize(_field(rows, "candidate_count")),
        final_count=summarize(_field(rows, "final_count")),
        introduced_count=summarize(_field(rows, "introduced_count")),
        reordered_count=summarize(_field(rows, "reordered_count")),
        top_score=summarize(_field(rows, "top_score")),
        max_promoted_rank=summarize(_field(rows, "max_promoted_rank")),
        mean_promoted_rank=summarize(_field(rows, "mean_promoted_rank")),
        unused_candidate_depth=summarize(_field(rows, "unused_candidate_depth")),
    )


def build_report(spans: Sequence[tuple[str, dict]]) -> RetrievalReport:
    """
    Summarise every retrieval stage present in a window.

    A stage with no spans is absent rather than reported as zeroes - "this
    did not run" and "this ran and found nothing" are different findings.
    """

    grouped = _by_stage(spans)

    return RetrievalReport(
        retrievers=[
            summarize_retriever(stage, grouped[stage])
            for stage in RETRIEVER_STAGES
            if stage in grouped
        ],
        fusion=summarize_fusion(grouped.get("fusion", [])),
        reranking=summarize_reranking(grouped.get("reranking", [])),
        cache=summarize_cache(grouped.get(CACHE_STAGE, [])),
    )
