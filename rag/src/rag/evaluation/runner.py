"""
Running an evaluation set against a retriever.

Offline, and only offline. This never runs inside a request, never
appears in the operational dashboard, and reports nothing that the
production tables could have produced on their own - those are three
statements of the same rule, which is that measured behaviour and
measured quality are different claims with different evidence behind
them.

What it needs is a retriever and a labelled set. It does not need an
LLM: every metric here is about which passages came back, not about what
was written with them. Answer-level quality is a separate problem that
needs either a human or a judge model, and conflating the two would let
a retrieval regression hide behind a well-written wrong answer.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from rag.evaluation.metrics import (
    average_precision,
    mean,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from rag.evaluation.schemas import (
    EvaluationDataset,
    EvaluationExample,
    EvaluationReport,
    ExampleResult,
)

logger = logging.getLogger(__name__)

DEFAULT_K_VALUES = (1, 3, 5, 10)


class Retriever(Protocol):
    """
    What the runner needs, which is far less than BaseRetriever.

    A Protocol rather than the base class so an evaluation can be run
    against anything that ranks chunks - a stub, a recorded ranking, a
    competing implementation - without either side importing the other.
    """

    def retrieve(self, query: str, top_k: int | None = None) -> Sequence[Any]: ...


def _ids(chunks: Sequence[Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    chunk_ids: list[str] = []
    document_ids: list[str] = []

    for chunk in chunks:
        chunk_id = getattr(chunk, "id", None)

        if chunk_id is not None:
            chunk_ids.append(str(chunk_id))

        metadata = getattr(chunk, "metadata", None)
        document_id = getattr(metadata, "document_id", None)

        if document_id is not None:
            document_ids.append(str(document_id))

    return tuple(chunk_ids), tuple(document_ids)


def score_example(
    example: EvaluationExample,
    chunk_ids: Sequence[str],
    document_ids: Sequence[str],
    *,
    k_values: Sequence[int] = DEFAULT_K_VALUES,
) -> dict[str, float | None]:
    """
    Every metric for one example.

    Chunk-level and document-level scores are kept apart rather than
    merged. They are different questions - "did it find the right
    passage" and "did it find the right book" - and averaging them
    together would produce a number that answers neither.
    """

    scores: dict[str, float | None] = {}

    if example.relevant_chunk_ids:
        truth = example.relevant_chunk_ids

        for k in k_values:
            scores[f"recall@{k}"] = recall_at_k(chunk_ids, truth, k)
            scores[f"precision@{k}"] = precision_at_k(chunk_ids, truth, k)
            scores[f"ndcg@{k}"] = ndcg_at_k(chunk_ids, truth, k)

        scores["mrr"] = reciprocal_rank(chunk_ids, truth)
        scores["map"] = average_precision(chunk_ids, truth)

    if example.relevant_document_ids:
        truth = example.relevant_document_ids

        # Deduplicated, preserving order: several chunks of one document
        # are one document found, not several.
        seen: list[str] = []

        for document_id in document_ids:
            if document_id not in seen:
                seen.append(document_id)

        for k in k_values:
            scores[f"document_recall@{k}"] = recall_at_k(seen, truth, k)

        scores["document_mrr"] = reciprocal_rank(seen, truth)

    return scores


def evaluate(
    retriever: Retriever,
    dataset: EvaluationDataset,
    *,
    top_k: int = 10,
    k_values: Sequence[int] = DEFAULT_K_VALUES,
    config: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> EvaluationReport:
    """
    Run every labelled example and summarise.

    Unlabelled examples are skipped and counted, never scored as zero.
    A question nobody has labelled is missing evidence, not a failure of
    retrieval, and averaging it in as a miss would make the set report a
    worse system the larger it grows.

    An example whose retrieval raises is recorded with its error and left
    out of the averages, for the same reason.
    """

    results: list[ExampleResult] = []
    failed = 0

    for example in dataset.labelled_examples:
        try:
            chunks = retriever.retrieve(example.question, top_k=top_k)
            chunk_ids, document_ids = _ids(chunks)

            results.append(
                ExampleResult(
                    example_id=example.id,
                    question=example.question,
                    retrieved_chunk_ids=chunk_ids,
                    retrieved_document_ids=document_ids,
                    scores=score_example(
                        example,
                        chunk_ids,
                        document_ids,
                        k_values=k_values,
                    ),
                )
            )
        except Exception as error:
            failed += 1

            logger.exception("Evaluation failed on example '%s'.", example.id)

            results.append(
                ExampleResult(
                    example_id=example.id,
                    question=example.question,
                    retrieved_chunk_ids=(),
                    retrieved_document_ids=(),
                    # The type, not the message: a provider exception can
                    # carry a key, and this report gets committed.
                    error=type(error).__name__,
                )
            )

    return EvaluationReport(
        dataset=dataset.name,
        ran_at=now or datetime.now(UTC),
        examples=tuple(results),
        summary=summarize(results),
        config={"top_k": top_k, "k_values": list(k_values), **(config or {})},
        skipped_unlabelled=dataset.unlabelled_count,
        failed=failed,
    )


def summarize(results: Sequence[ExampleResult]) -> dict[str, float | None]:
    """
    Mean of each metric over the examples that produced one.

    A metric absent from an example - because it was labelled at document
    level only, say - is skipped rather than counted as zero.
    """

    names: list[str] = []

    for result in results:
        for name in result.scores:
            if name not in names:
                names.append(name)

    return {name: mean(result.scores.get(name) for result in results) for name in names}
