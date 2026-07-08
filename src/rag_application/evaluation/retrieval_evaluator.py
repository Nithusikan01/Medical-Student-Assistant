from __future__ import annotations

from typing import List

from rag_application.evaluation.schemas import (
    EvaluationSample,
    RetrievalEvaluationResult,
)
from rag_application.evaluation.metrics.retrieval_metrics import (
    RetrievalMetrics,
)
from rag_application.retrieval.query_service import QueryService


class RetrievalEvaluator:
    """
    Evaluates only the retrieval stage.

    Metrics:
        - Recall@K
        - Precision@K
        - MRR
        - Hit Rate
    """

    def __init__(
        self,
        query_service: QueryService,
    ):
        self.query_service = query_service

    def evaluate_sample(
        self,
        sample: EvaluationSample,
        top_k: int = 5,
    ) -> RetrievalEvaluationResult:

        retrieved_chunks = self.query_service.search(
            query=sample.question,
            top_k=top_k,
        )

        retrieved_ids = [
            chunk.id
            for chunk in retrieved_chunks
        ]

        expected_ids = sample.expected_chunk_ids

        recall = RetrievalMetrics.recall_at_k(
            expected_ids,
            retrieved_ids,
        )

        precision = RetrievalMetrics.precision_at_k(
            expected_ids,
            retrieved_ids,
        )

        mrr = RetrievalMetrics.mrr(
            expected_ids,
            retrieved_ids,
        )

        hit_rate = RetrievalMetrics.hit_rate(
            expected_ids,
            retrieved_ids,
        )

        return RetrievalEvaluationResult(
            question_id=sample.id,
            question=sample.question,
            retrieved_chunk_ids=retrieved_ids,
            expected_chunk_ids=expected_ids,
            recall_at_k=recall,
            precision_at_k=precision,
            mrr=mrr,
            hit_rate=hit_rate,
        )

    def evaluate_dataset(
        self,
        dataset: List[EvaluationSample],
        top_k: int = 5,
    ) -> List[RetrievalEvaluationResult]:

        results = []

        for sample in dataset:
            results.append(
                self.evaluate_sample(
                    sample,
                    top_k,
                )
            )

        return results