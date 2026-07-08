from __future__ import annotations

from dataclasses import asdict
from statistics import mean
from typing import List

from rag_application.evaluation.schemas import (
    EvaluationSample,
)

from rag_application.evaluation.retrieval_evaluator import (
    RetrievalEvaluator,
)

from rag_application.evaluation.generation_evaluator import (
    GenerationEvaluator,
)


class RAGEvaluator:
    """
    Runs the complete RAG evaluation pipeline.

    1. Retrieval evaluation
    2. Generation evaluation
    3. Aggregate metrics
    """

    def __init__(
        self,
        retrieval_evaluator: RetrievalEvaluator,
        generation_evaluator: GenerationEvaluator,
    ):
        self.retrieval_evaluator = retrieval_evaluator
        self.generation_evaluator = generation_evaluator

    def evaluate(
        self,
        dataset: List[EvaluationSample],
        top_k: int = 5,
    ) -> dict:

        retrieval_results = self.retrieval_evaluator.evaluate_dataset(
            dataset=dataset,
            top_k=top_k,
        )

        generation_results = self.generation_evaluator.evaluate_dataset(
            dataset=dataset,
        )

        summary = {
            "retrieval": {
                "Recall@K": mean(
                    r.recall_at_k for r in retrieval_results
                ),
                "Precision@K": mean(
                    r.precision_at_k for r in retrieval_results
                ),
                "MRR": mean(
                    r.mrr for r in retrieval_results
                ),
                "HitRate": mean(
                    r.hit_rate for r in retrieval_results
                ),
            },
            "generation": {
                "ExactMatch": mean(
                    r.exact_match for r in generation_results
                ),
                "F1": mean(
                    r.f1 for r in generation_results
                ),
                "ROUGE-L": mean(
                    r.rouge_l for r in generation_results
                ),
                "BLEU": mean(
                    r.bleu for r in generation_results
                ),
                "SemanticSimilarity": mean(
                    r.semantic_similarity
                    for r in generation_results
                ),
            },
            "retrieval_results": [
                asdict(r)
                for r in retrieval_results
            ],
            "generation_results": [
                asdict(r)
                for r in generation_results
            ],
        }

        return summary
