"""
Retrieval metrics, aggregated across requests.

These are online operational metrics only. The tests at the bottom pin the
boundary this module must not cross: nothing here claims retrieval was
*good*, because production logs contain no ground truth to judge that
against.
"""

import pytest

from backend.observability.retrieval_metrics import (
    RETRIEVAL_STAGES,
    build_report,
    summarize,
    summarize_fusion,
    summarize_reranking,
    summarize_retriever,
)


def spans(*pairs) -> list[tuple[str, dict]]:
    return list(pairs)


# ----------------------------------------------------------------------
# Distributions
# ----------------------------------------------------------------------


def test_a_distribution_skips_missing_values_rather_than_zeroing_them():
    """
    A span that never recorded a field must not contribute a zero - that
    would drag every average toward it and understate real scores.
    """

    summary = summarize([0.9, None, 0.7, None])

    assert summary.count == 2
    assert summary.mean == pytest.approx(0.8)


def test_booleans_are_not_numbers():
    """True is an int in Python; counting it as 1.0 would be nonsense here."""

    assert summarize([True, False]).count == 0


def test_an_empty_distribution_reports_nothing_rather_than_zero():
    summary = summarize([])

    assert summary.count == 0
    assert summary.mean is None
    assert summary.p95 is None


# ----------------------------------------------------------------------
# Retrievers
# ----------------------------------------------------------------------


def test_a_retriever_that_returns_nothing_is_counted():
    """
    The most useful number in this module: a lexical half that has silently
    stopped matching shows up here while every other metric looks healthy.
    """

    summary = summarize_retriever(
        "bm25_retrieval",
        [
            {"result_count": 0},
            {"result_count": 0},
            {"result_count": 5, "top_score": 2.1},
            {"result_count": 3, "top_score": 1.4},
        ],
    )

    assert summary.calls == 4
    assert summary.empty_calls == 2
    assert summary.empty_rate == pytest.approx(0.5)
    assert summary.top_score.count == 2


def test_score_distributions_are_summarised():
    summary = summarize_retriever(
        "dense_retrieval",
        [
            {"result_count": 30, "top_score": 0.95, "average_score": 0.80},
            {"result_count": 30, "top_score": 0.55, "average_score": 0.40},
        ],
    )

    assert summary.result_count.mean == pytest.approx(30.0)
    assert summary.top_score.minimum == pytest.approx(0.55)
    assert summary.top_score.maximum == pytest.approx(0.95)


# ----------------------------------------------------------------------
# Fusion
# ----------------------------------------------------------------------


def test_fusion_reports_where_results_came_from():
    """Section 19's breakdown: vector only, lexical only, or both."""

    summary = summarize_fusion(
        [
            {
                "dense_count": 3,
                "bm25_count": 2,
                "dense_only_count": 2,
                "bm25_only_count": 1,
                "overlap_count": 1,
                "unique_count": 4,
            }
        ]
    )

    assert summary.dense_only_share == pytest.approx(0.5)
    assert summary.bm25_only_share == pytest.approx(0.25)
    assert summary.overlap_share == pytest.approx(0.25)


def test_a_retriever_contributing_nothing_is_flagged_as_single_retriever():
    """
    Hybrid retrieval degrading to one retriever, with nothing having failed
    and no error anywhere. Exactly what was observed locally when the chunk
    table was empty but Pinecone still answered.
    """

    summary = summarize_fusion(
        [
            {"dense_count": 30, "bm25_count": 0, "dense_only_count": 30},
            {"dense_count": 30, "bm25_count": 4, "overlap_count": 2},
        ]
    )

    assert summary.single_retriever_calls == 1
    assert summary.single_retriever_rate == pytest.approx(0.5)


def test_shares_are_undefined_rather_than_zero_when_nothing_was_retrieved():
    summary = summarize_fusion([{"dense_count": 0, "bm25_count": 0}])

    assert summary.overlap_share is None
    assert summary.dense_only_share is None


def test_no_fusion_spans_means_no_summary():
    assert summarize_fusion([]) is None


# ----------------------------------------------------------------------
# Reranking
# ----------------------------------------------------------------------


def test_reranker_degradation_is_counted():
    """
    Falling back to the Gemini reranker, or giving up entirely, used to be
    only a log line. This is the number that makes it visible.
    """

    summary = summarize_reranking(
        [
            {"reranker_used": "PineconeReranker", "reranker_degraded": False},
            {"reranker_used": "GeminiReranker", "reranker_degraded": True},
            {"reranker_used": "none", "reranker_degraded": True},
            {"reranker_used": "PineconeReranker", "reranker_degraded": False},
        ]
    )

    assert summary.degraded_calls == 2
    assert summary.degraded_rate == pytest.approx(0.5)
    assert summary.reranker_usage["PineconeReranker"] == 2
    assert summary.reranker_usage["none"] == 1


def test_whether_reranking_changed_the_selection_is_counted():
    summary = summarize_reranking(
        [
            {"introduced_count": 3, "reordered_count": 5},
            {"introduced_count": 0, "reordered_count": 0},
            {"introduced_count": 0, "reordered_count": 2},
        ]
    )

    assert summary.changed_calls == 2
    assert summary.change_rate == pytest.approx(2 / 3)
    assert summary.introduced_count.mean == pytest.approx(1.0)


def test_the_candidate_to_final_funnel_is_reported():
    summary = summarize_reranking(
        [
            {"candidate_count": 30, "final_count": 5},
            {"candidate_count": 30, "final_count": 5},
        ]
    )

    assert summary.candidate_count.mean == pytest.approx(30.0)
    assert summary.final_count.mean == pytest.approx(5.0)


# ----------------------------------------------------------------------
# The whole report
# ----------------------------------------------------------------------


def test_a_report_covers_every_stage_present():
    report = build_report(
        spans(
            ("dense_retrieval", {"result_count": 30, "top_score": 0.9}),
            ("bm25_retrieval", {"result_count": 0}),
            ("fusion", {"dense_count": 30, "bm25_count": 0, "dense_only_count": 30}),
            ("reranking", {"candidate_count": 30, "final_count": 5}),
        )
    )

    assert [r.stage for r in report.retrievers] == [
        "dense_retrieval",
        "bm25_retrieval",
    ]
    assert report.fusion.single_retriever_calls == 1
    assert report.reranking.calls == 1


def test_a_stage_that_did_not_run_is_absent_rather_than_zeroed():
    """
    "This did not run" and "this ran and found nothing" are different
    findings, and a dashboard must not render them alike.
    """

    report = build_report(spans(("dense_retrieval", {"result_count": 10})))

    assert report.fusion is None
    assert report.reranking is None
    assert [r.stage for r in report.retrievers] == ["dense_retrieval"]


def test_an_empty_window_produces_an_empty_report():
    report = build_report([])

    assert report.retrievers == []
    assert report.fusion is None
    assert report.reranking is None


def test_spans_missing_their_metadata_do_not_break_the_report():
    report = build_report(spans(("dense_retrieval", {}), ("fusion", {})))

    assert report.retrievers[0].calls == 1
    assert report.retrievers[0].result_count.count == 0


# ----------------------------------------------------------------------
# The boundary this module must not cross
# ----------------------------------------------------------------------


def test_no_offline_quality_metric_is_produced():
    """
    Recall@K, Precision@K, MRR and nDCG need a question set with
    known-correct documents. Production logs have none, so this module must
    not grow a field that implies otherwise - a similarity score says how
    close a chunk was in embedding space, not whether it answered anything.
    """

    report = build_report(spans(("dense_retrieval", {"result_count": 5})))

    forbidden = ("recall", "precision", "mrr", "ndcg", "hit_rate", "relevance")
    fields = {field.lower() for field in report.retrievers[0].__slots__}

    assert not any(term in field for field in fields for term in forbidden)


def test_only_retrieval_stages_are_declared():
    assert set(RETRIEVAL_STAGES) == {
        "retrieval",
        "dense_retrieval",
        "bm25_retrieval",
        "fusion",
        "reranking",
    }


# ----------------------------------------------------------------------
# Candidate pool depth
# ----------------------------------------------------------------------


def test_promotion_depth_is_aggregated():
    summary = summarize_reranking(
        [
            {
                "max_promoted_rank": 25,
                "mean_promoted_rank": 9.6,
                "unused_candidate_depth": 5,
            },
            {
                "max_promoted_rank": 4,
                "mean_promoted_rank": 2.0,
                "unused_candidate_depth": 26,
            },
        ]
    )

    assert summary.max_promoted_rank.mean == pytest.approx(14.5)
    assert summary.max_promoted_rank.maximum == pytest.approx(25.0)
    assert summary.unused_candidate_depth.mean == pytest.approx(15.5)


def test_a_consistently_shallow_reranker_shows_high_unused_depth():
    """
    What tuning candidate_k down would look like in the data: reranking
    never reaches past the first few candidates, so most of the pool is
    retrieved and scored for nothing.
    """

    summary = summarize_reranking(
        [{"max_promoted_rank": 3, "unused_candidate_depth": 27} for _ in range(10)]
    )

    assert summary.max_promoted_rank.maximum == pytest.approx(3.0)
    assert summary.unused_candidate_depth.minimum == pytest.approx(27.0)


def test_depth_is_absent_when_no_span_recorded_it():
    """Older spans predate the field; they must not contribute zeroes."""

    summary = summarize_reranking([{"candidate_count": 30, "final_count": 5}])

    assert summary.max_promoted_rank.count == 0
    assert summary.max_promoted_rank.mean is None
