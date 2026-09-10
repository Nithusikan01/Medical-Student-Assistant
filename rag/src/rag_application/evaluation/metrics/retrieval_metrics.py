from __future__ import annotations

from typing import Sequence


class RetrievalMetrics:
    """
    Retrieval evaluation metrics.

    Assumptions:
        - expected_ids contains the relevant chunk IDs.
        - retrieved_ids is ordered by retrieval rank.
    """

    @staticmethod
    def recall_at_k(
        expected_ids: Sequence[str],
        retrieved_ids: Sequence[str],
    ) -> float:
        """
        Recall@K

        Relevant retrieved / Total relevant
        """

        expected = set(expected_ids)

        if not expected:
            return 0.0

        retrieved = set(retrieved_ids)

        return len(expected & retrieved) / len(expected)

    @staticmethod
    def precision_at_k(
        expected_ids: Sequence[str],
        retrieved_ids: Sequence[str],
    ) -> float:
        """
        Precision@K

        Relevant retrieved / Retrieved
        """

        if not retrieved_ids:
            return 0.0

        expected = set(expected_ids)
        retrieved = set(retrieved_ids)

        return len(expected & retrieved) / len(retrieved_ids)

    @staticmethod
    def hit_rate(
        expected_ids: Sequence[str],
        retrieved_ids: Sequence[str],
    ) -> float:
        """
        Hit Rate

        1 if at least one relevant chunk is retrieved.
        """

        expected = set(expected_ids)

        for chunk_id in retrieved_ids:
            if chunk_id in expected:
                return 1.0

        return 0.0

    @staticmethod
    def mrr(
        expected_ids: Sequence[str],
        retrieved_ids: Sequence[str],
    ) -> float:
        """
        Mean Reciprocal Rank (single-query value).

        Returns:
            1/rank of first relevant result.
        """

        expected = set(expected_ids)

        for rank, chunk_id in enumerate(retrieved_ids, start=1):
            if chunk_id in expected:
                return 1.0 / rank

        return 0.0

    @staticmethod
    def ndcg(
        expected_ids: Sequence[str],
        retrieved_ids: Sequence[str],
    ) -> float:
        """
        Normalized Discounted Cumulative Gain.

        Binary relevance.
        """

        if not expected_ids:
            return 0.0

        expected = set(expected_ids)

        dcg = 0.0

        for rank, chunk_id in enumerate(retrieved_ids, start=1):
            if chunk_id in expected:
                dcg += 1.0 / __import__("math").log2(rank + 1)

        ideal = min(len(expected), len(retrieved_ids))

        idcg = sum(
            1.0 / __import__("math").log2(i + 1)
            for i in range(2, ideal + 2)
        )

        if idcg == 0:
            return 0.0

        return dcg / idcg