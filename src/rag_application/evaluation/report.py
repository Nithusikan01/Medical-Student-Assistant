from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from statistics import mean
from typing import Any

from rag_application.evaluation.schemas import (
    RetrievalEvaluationResult,
    GenerationEvaluationResult,
    LLMJudgeResult,
)


class EvaluationReport:
    """
    Creates a complete evaluation report from retrieval,
    generation and optional LLM-judge results.
    """

    def __init__(
        self,
        retrieval_results: list[RetrievalEvaluationResult],
        generation_results: list[GenerationEvaluationResult],
        llm_results: list[LLMJudgeResult] | None = None,
    ):
        self.retrieval_results = retrieval_results
        self.generation_results = generation_results
        self.llm_results = llm_results or []

    def build(self) -> dict[str, Any]:

        report = {
            "created_at": datetime.now().isoformat(),
            "num_questions": max(
                len(self.retrieval_results),
                len(self.generation_results),
            ),

            "retrieval_summary": self._retrieval_summary(),

            "generation_summary": self._generation_summary(),

            "llm_summary": self._llm_summary(),

            "retrieval_results": [
                asdict(r)
                for r in self.retrieval_results
            ],

            "generation_results": [
                asdict(r)
                for r in self.generation_results
            ],

            "llm_results": [
                asdict(r)
                for r in self.llm_results
            ]
        }

        return report

    def _retrieval_summary(self):

        if not self.retrieval_results:
            return {}

        return {
            "Recall@K": mean(
                r.recall_at_k
                for r in self.retrieval_results
            ),

            "Precision@K": mean(
                r.precision_at_k
                for r in self.retrieval_results
            ),

            "MRR": mean(
                r.mrr
                for r in self.retrieval_results
            ),

            "HitRate": mean(
                r.hit_rate
                for r in self.retrieval_results
            ),
        }

    def _generation_summary(self):

        if not self.generation_results:
            return {}

        return {

            "ExactMatch": mean(
                r.exact_match
                for r in self.generation_results
            ),

            "F1": mean(
                r.f1
                for r in self.generation_results
            ),

            "ROUGE-L": mean(
                r.rouge_l
                for r in self.generation_results
            ),

            "BLEU": mean(
                r.bleu
                for r in self.generation_results
            ),

            "SemanticSimilarity": mean(
                r.semantic_similarity
                for r in self.generation_results
            ),
        }

    def _llm_summary(self):

        if not self.llm_results:
            return {}

        return {

            "Faithfulness": mean(
                r.faithfulness
                for r in self.llm_results
            ),

            "Correctness": mean(
                r.correctness
                for r in self.llm_results
            ),

            "Completeness": mean(
                r.completeness
                for r in self.llm_results
            ),

            "Groundedness": mean(
                r.groundedness
                for r in self.llm_results
            ),
        }
