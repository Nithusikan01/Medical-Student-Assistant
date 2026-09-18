import json
import logging
import re

from rag.llm.protocol import TextGenerator
from rag.rerankers.base import BaseReranker
from rag.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)

_MAX_CANDIDATE_CHARS = 500
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class GeminiReranker(BaseReranker):
    """
    Listwise reranking through the same Gemini model used for generation.

    Used as a fallback when the hosted Pinecone reranker is unavailable, so
    it deliberately raises on any failure rather than degrading itself -
    FallbackReranker is what decides the final resort (retrieval order).
    """

    def __init__(self, generator: TextGenerator) -> None:
        self.generator = generator

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        if not candidates:
            logger.warning("No candidates provided to reranker.")
            return []

        prompt = self._build_prompt(query, candidates, top_k)

        response = self.generator.generate(prompt)
        ranking = self._parse_ranking(response.text, len(candidates))

        if not ranking:
            raise ValueError("Gemini reranker returned no usable ranking.")

        results = [
            candidates[index].with_rerank_score(score=score, rank=rank)
            for rank, (index, score) in enumerate(ranking[:top_k], start=1)
        ]

        logger.debug(
            "Gemini reranker reduced %d candidates to %d.",
            len(candidates),
            len(results),
        )

        return results

    @staticmethod
    def _build_prompt(
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int,
    ) -> str:
        documents = "\n".join(
            f"{index}: {chunk.text[:_MAX_CANDIDATE_CHARS]}"
            for index, chunk in enumerate(candidates)
        )

        return f"""
        You are a relevance-ranking system for a RAG application.

        Query:
        {query}

        Candidate documents (index: text):
        {documents}

        Task:
        Return the {min(top_k, len(candidates))} most relevant documents for the query,
        ordered most relevant first.

        Output ONLY a JSON array, no explanation, no markdown fence, in this exact shape:
        [{{"index": 0, "score": 0.93}}, {{"index": 2, "score": 0.71}}]

        Rules:
        - "index" must be one of the candidate indices shown above.
        - "score" is your relevance estimate between 0 and 1.
        - Do not include indices for irrelevant documents.
        """

    @staticmethod
    def _parse_ranking(
        text: str,
        num_candidates: int,
    ) -> list[tuple[int, float]]:
        cleaned = _FENCE_RE.sub("", text.strip())

        try:
            raw = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Gemini reranker returned non-JSON output.")
            return []

        if not isinstance(raw, list):
            logger.warning("Gemini reranker JSON was not a list.")
            return []

        ranking: list[tuple[int, float]] = []
        seen_indices: set[int] = set()

        for item in raw:
            if not isinstance(item, dict):
                continue

            index = item.get("index")
            score = item.get("score")

            if not isinstance(index, int) or isinstance(index, bool):
                continue

            if index < 0 or index >= num_candidates or index in seen_indices:
                continue

            if not isinstance(score, (int, float)) or isinstance(score, bool):
                continue

            seen_indices.add(index)
            ranking.append((index, float(score)))

        return ranking
