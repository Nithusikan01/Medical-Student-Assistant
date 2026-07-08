from __future__ import annotations

import re
from typing import cast

import numpy as np
from nltk.translate.bleu_score import sentence_bleu
from rouge_score import rouge_scorer

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


class GenerationMetrics:
    """
    Metrics for evaluating generated answers.
    """

    _embedding_model = SentenceTransformer(
        "sentence-transformers/all-MiniLM-L6-v2"
    )

    @staticmethod
    def normalize(text: str) -> str:
        """
        Lowercase, remove punctuation,
        normalize whitespace.
        """

        text = text.lower()

        text = re.sub(r"[^\w\s]", "", text)

        text = " ".join(text.split())

        return text

    @classmethod
    def exact_match(
        cls,
        expected: str,
        generated: str,
    ) -> float:

        return float(
            cls.normalize(expected)
            == cls.normalize(generated)
        )

    @classmethod
    def f1(
        cls,
        expected: str,
        generated: str,
    ) -> float:

        expected_tokens = cls.normalize(expected).split()
        generated_tokens = cls.normalize(generated).split()

        if not expected_tokens or not generated_tokens:
            return 0.0

        common = set(expected_tokens) & set(generated_tokens)

        if not common:
            return 0.0

        precision = len(common) / len(generated_tokens)

        recall = len(common) / len(expected_tokens)

        return float(
            2 * precision * recall
            / (precision + recall)
        )

    @staticmethod
    def bleu(
        expected: str,
        generated: str,
    ) -> float:

        score = sentence_bleu(
            [expected.split()],
            generated.split(),
        )

        return cast(float, score)

    @staticmethod
    def rouge_l(
        expected: str,
        generated: str,
    ) -> float:

        scorer = rouge_scorer.RougeScorer(
            ["rougeL"],
            use_stemmer=True,
        )

        scores = scorer.score(
            expected,
            generated,
        )

        return float(
            scores["rougeL"].fmeasure
        )

    @classmethod
    def semantic_similarity(
        cls,
        expected: str,
        generated: str,
    ) -> float:

        embeddings = cls._embedding_model.encode(
            [expected, generated],
            convert_to_numpy=True,
        )

        embeddings = cast(
            np.ndarray,
            embeddings,
        )

        similarity = cosine_similarity(
            embeddings[0].reshape(1, -1),
            embeddings[1].reshape(1, -1),
        )

        return float(similarity[0][0])