"""
Offline retrieval evaluation.

The distinction this package exists to hold: the dashboard measures what
happened, these measure whether it was any good, and the second needs
ground truth the first can never supply.

Most of what is asserted here is about honesty rather than arithmetic.
An unlabelled question must not count as a miss, an unmeasurable metric
must not average in as zero, and two reports from different datasets
must not be compared just because the subtraction would work.
"""

import json
from datetime import UTC, datetime

import pytest

from rag.evaluation import (
    EvaluationDataset,
    EvaluationExample,
    EvaluationReport,
    InvalidDatasetError,
    average_precision,
    compare,
    evaluate,
    load_dataset,
    mean,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


class StubChunk:
    def __init__(self, chunk_id: str, document_id: str = "doc-1") -> None:
        self.id = chunk_id
        self.metadata = type("Metadata", (), {"document_id": document_id})()


class StubRetriever:
    """Returns a fixed ranking, so the metrics are what is under test."""

    def __init__(self, ranking, document_ids=None) -> None:
        self.ranking = ranking
        self.document_ids = document_ids or ["doc-1"] * len(ranking)

    def retrieve(self, query, top_k=None):
        chunks = [
            StubChunk(chunk_id, document_id)
            for chunk_id, document_id in zip(
                self.ranking, self.document_ids, strict=False
            )
        ]

        return chunks[: top_k or len(chunks)]


class ExplodingRetriever:
    def retrieve(self, query, top_k=None):
        raise RuntimeError("pinecone key sk-abcdef123456 was rejected")


def example(**overrides) -> EvaluationExample:
    defaults = {
        "id": "q1",
        "question": "What is the dose?",
        "relevant_chunk_ids": ("a", "b"),
    }

    return EvaluationExample(**{**defaults, **overrides})


def dataset(*examples) -> EvaluationDataset:
    return EvaluationDataset(name="set", examples=tuple(examples))


# ----------------------------------------------------------------------
# The metrics
# ----------------------------------------------------------------------


def test_recall_counts_relevant_items_inside_the_window():
    assert recall_at_k(["a", "x", "b"], ["a", "b"], 3) == 1.0
    assert recall_at_k(["a", "x", "y"], ["a", "b"], 3) == 0.5
    assert recall_at_k(["x", "y", "a"], ["a", "b"], 2) == 0.0


def test_precision_counts_the_window_that_is_relevant():
    assert precision_at_k(["a", "b", "x", "y"], ["a", "b"], 4) == 0.5
    assert precision_at_k(["a", "b"], ["a", "b"], 2) == 1.0


def test_reciprocal_rank_rewards_finding_it_early():
    assert reciprocal_rank(["a", "x"], ["a"]) == 1.0
    assert reciprocal_rank(["x", "a"], ["a"]) == 0.5
    assert reciprocal_rank(["x", "y"], ["a"]) == 0.0


def test_ndcg_is_one_for_a_perfect_ranking():
    assert ndcg_at_k(["a", "b", "x"], ["a", "b"], 3) == pytest.approx(1.0)


def test_ndcg_separates_rankings_recall_cannot():
    """
    The reason it is here. Both rankings contain the relevant chunk in
    the top 3, so Recall@3 is identical; only nDCG says one put it first.
    """

    early = ndcg_at_k(["a", "x", "y"], ["a"], 3)
    late = ndcg_at_k(["x", "y", "a"], ["a"], 3)

    assert recall_at_k(["a", "x", "y"], ["a"], 3) == recall_at_k(
        ["x", "y", "a"], ["a"], 3
    )
    assert early > late


def test_average_precision_rewards_ordering():
    both_early = average_precision(["a", "b", "x", "y"], ["a", "b"])
    both_late = average_precision(["x", "y", "a", "b"], ["a", "b"])

    assert both_early > both_late


# ----------------------------------------------------------------------
# What must not be reported as zero
# ----------------------------------------------------------------------


def test_recall_with_nothing_labelled_is_undefined():
    """
    Returning 0.0 would count an unlabelled question as a total miss and
    quietly drag the average down - which is how an evaluation set
    becomes a lie about the system.
    """

    assert recall_at_k(["a"], [], 3) is None


def test_precision_over_an_empty_ranking_is_undefined():
    assert precision_at_k([], ["a"], 3) is None


def test_reciprocal_rank_of_a_miss_is_genuinely_zero():
    """
    Unlike the others. "No relevant result anywhere in the ranking" is a
    real outcome, not missing data.
    """

    assert reciprocal_rank(["x", "y"], ["a"]) == 0.0


def test_the_mean_skips_absent_values_rather_than_counting_them():
    assert mean([1.0, None, 0.0]) == 0.5
    assert mean([None, None]) is None


# ----------------------------------------------------------------------
# Running a set
# ----------------------------------------------------------------------


def test_a_perfect_retriever_scores_one():
    report = evaluate(
        StubRetriever(["a", "b"]),
        dataset(example()),
        k_values=(2,),
        now=NOW,
    )

    assert report.summary["recall@2"] == 1.0
    assert report.evaluated == 1


def test_unlabelled_examples_are_skipped_not_failed():
    """
    A question nobody has labelled is missing evidence, not a failure of
    retrieval. Averaging it in as a miss would make the set report a
    worse system the larger it grows.
    """

    report = evaluate(
        StubRetriever(["a"]),
        dataset(
            example(),
            EvaluationExample(id="q2", question="Unlabelled?"),
        ),
        k_values=(1,),
        now=NOW,
    )

    assert report.skipped_unlabelled == 1
    assert len(report.examples) == 1


def test_a_retrieval_failure_is_recorded_and_left_out_of_the_average():
    report = evaluate(
        ExplodingRetriever(),
        dataset(example()),
        now=NOW,
    )

    assert report.failed == 1
    assert report.summary == {}


def test_a_failure_records_the_type_not_the_message():
    """
    A provider exception can carry an API key, and this report gets
    written to a file and committed.
    """

    report = evaluate(ExplodingRetriever(), dataset(example()), now=NOW)

    (result,) = report.examples

    assert result.error == "RuntimeError"
    assert "sk-abcdef123456" not in json.dumps(
        {"error": result.error, "question": result.question}
    )


def test_document_level_labels_are_scored_separately():
    """
    "Did it find the right passage" and "did it find the right book" are
    different questions; averaging them together answers neither.
    """

    report = evaluate(
        StubRetriever(["x", "y"], document_ids=["doc-7", "doc-7"]),
        dataset(
            EvaluationExample(
                id="q1",
                question="Which book?",
                relevant_document_ids=("doc-7",),
            )
        ),
        k_values=(1,),
        now=NOW,
    )

    assert report.summary["document_recall@1"] == 1.0
    assert "recall@1" not in report.summary


def test_repeated_chunks_of_one_document_count_once():
    report = evaluate(
        StubRetriever(["a", "b", "c"], document_ids=["doc-1", "doc-1", "doc-9"]),
        dataset(
            EvaluationExample(
                id="q1",
                question="Which book?",
                relevant_document_ids=("doc-9",),
            )
        ),
        k_values=(2,),
        now=NOW,
    )

    # doc-9 is second among distinct documents, so it is inside the top 2.
    assert report.summary["document_recall@2"] == 1.0


def test_the_config_is_recorded_with_the_result():
    """
    Without it a report is a number with no claim attached, and two
    reports cannot be meaningfully compared.
    """

    report = evaluate(
        StubRetriever(["a"]),
        dataset(example()),
        top_k=7,
        now=NOW,
    )

    assert report.config["top_k"] == 7


# ----------------------------------------------------------------------
# Loading a set
# ----------------------------------------------------------------------


def write(tmp_path, payload) -> str:
    path = tmp_path / "set.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    return str(path)


def test_a_set_round_trips(tmp_path):
    path = write(
        tmp_path,
        {
            "name": "cardiology",
            "examples": [
                {"id": "q1", "question": "What dose?", "relevant_chunk_ids": ["a"]}
            ],
        },
    )

    loaded = load_dataset(path)

    assert loaded.name == "cardiology"
    assert loaded.examples[0].relevant_chunk_ids == ("a",)


def test_a_malformed_example_raises_rather_than_being_skipped(tmp_path):
    """
    A set that silently drops half its questions would report a confident
    average over whatever survived.
    """

    path = write(tmp_path, {"examples": [{"question": ""}]})

    with pytest.raises(InvalidDatasetError):
        load_dataset(path)


def test_duplicate_ids_are_rejected(tmp_path):
    path = write(
        tmp_path,
        {
            "examples": [
                {"id": "q1", "question": "a?"},
                {"id": "q1", "question": "b?"},
            ]
        },
    )

    with pytest.raises(InvalidDatasetError):
        load_dataset(path)


def test_an_empty_set_is_rejected(tmp_path):
    path = write(tmp_path, {"examples": []})

    with pytest.raises(InvalidDatasetError):
        load_dataset(path)


def test_a_missing_file_says_so(tmp_path):
    with pytest.raises(InvalidDatasetError):
        load_dataset(tmp_path / "nothing.json")


# ----------------------------------------------------------------------
# Comparing runs
# ----------------------------------------------------------------------


def report_with(summary, config=None, name="set") -> EvaluationReport:
    return EvaluationReport(
        dataset=name,
        ran_at=NOW,
        examples=(),
        summary=summary,
        config=config or {},
    )


def test_an_improvement_is_reported_as_one():
    result = compare(
        report_with({"recall@5": 0.60}),
        report_with({"recall@5": 0.75}),
    )

    assert [metric.metric for metric in result.improved()] == ["recall@5"]


def test_a_regression_is_reported_as_one():
    result = compare(
        report_with({"recall@5": 0.75}),
        report_with({"recall@5": 0.60}),
    )

    assert result.regressed()


def test_noise_is_not_reported_as_a_change():
    """
    Retrieval over a small labelled set moves by a percent between runs
    for reasons unrelated to the change being tested. Calling that an
    improvement is how a tuning session convinces itself of things that
    are not true.
    """

    result = compare(
        report_with({"recall@5": 0.700}),
        report_with({"recall@5": 0.705}),
    )

    assert result.improved() == []
    assert result.regressed() == []


def test_configuration_changes_are_reported_alongside():
    result = compare(
        report_with({"recall@5": 0.6}, {"top_k": 5}),
        report_with({"recall@5": 0.7}, {"top_k": 10}),
    )

    assert result.config_changes["top_k"] == (5, 10)


def test_a_regression_with_no_config_change_reads_as_drift():
    """
    The corpus moved underneath: documents added, removed or re-chunked.
    Worth naming, because the instinct on seeing a regression is to look
    at code that was not touched.
    """

    result = compare(
        report_with({"recall@5": 0.8}, {"top_k": 5}),
        report_with({"recall@5": 0.5}, {"top_k": 5}),
    )

    assert result.looks_like_drift


def test_a_regression_after_a_config_change_is_not_called_drift():
    result = compare(
        report_with({"recall@5": 0.8}, {"top_k": 10}),
        report_with({"recall@5": 0.5}, {"top_k": 3}),
    )

    assert not result.looks_like_drift


def test_different_datasets_are_refused_rather_than_subtracted():
    """
    The arithmetic would work and the answer would be meaningless, which
    is the more dangerous kind of wrong.
    """

    result = compare(
        report_with({"recall@5": 0.6}, name="cardiology"),
        report_with({"recall@5": 0.9}, name="pharmacology"),
    )

    assert result.comparable is False
    assert result.metrics == ()


def test_a_metric_present_on_only_one_side_is_not_comparable():
    result = compare(
        report_with({"recall@5": 0.6}),
        report_with({"recall@5": 0.6, "ndcg@5": 0.7}),
    )

    ndcg = next(metric for metric in result.metrics if metric.metric == "ndcg@5")

    assert ndcg.delta is None
    assert ndcg.direction() == "unknown"
