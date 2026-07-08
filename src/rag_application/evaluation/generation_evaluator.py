from __future__ import annotations

from typing import List

from rag_application.evaluation.schemas import (
    EvaluationSample,
    GenerationEvaluationResult,
)
from rag_application.evaluation.metrics.generation_metrics import (
    GenerationMetrics,
)
from rag_application.services.history_aware_rag_service import (
    HistoryAwareRAGService,
)


class GenerationEvaluator:
    """
    Evaluates the generation stage of the RAG pipeline.

    Metrics:
        - Exact Match
        - F1
        - ROUGE-L
        - BLEU
        - Semantic Similarity
    """

    def __init__(
        self,
        rag_service: HistoryAwareRAGService,
    ):
        self.rag_service = rag_service

    def evaluate_sample(
        self,
        sample: EvaluationSample,
    ) -> GenerationEvaluationResult:

        generated_answer = self.rag_service.answer(
            conversation_id=f"evaluation-{sample.id}",
            question=sample.question,
        )

        expected_answer = sample.expected_answer

        exact_match = GenerationMetrics.exact_match(
            expected_answer,
            generated_answer,
        )

        f1 = GenerationMetrics.f1(
            expected_answer,
            generated_answer,
        )

        rouge = GenerationMetrics.rouge_l(
            expected_answer,
            generated_answer,
        )

        bleu = GenerationMetrics.bleu(
            expected_answer,
            generated_answer,
        )

        semantic_similarity = GenerationMetrics.semantic_similarity(
            expected_answer,
            generated_answer,
        )

        return GenerationEvaluationResult(
            question_id=sample.id,
            question=sample.question,
            expected_answer=expected_answer,
            generated_answer=generated_answer,
            exact_match=exact_match,
            f1=f1,
            rouge_l=rouge,
            bleu=bleu,
            semantic_similarity=semantic_similarity,
        )

    def evaluate_dataset(
        self,
        dataset: List[EvaluationSample],
    ) -> List[GenerationEvaluationResult]:

        results = []

        for sample in dataset:
            results.append(
                self.evaluate_sample(sample)
            )

        return results
