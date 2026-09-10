from dataclasses import dataclass, replace
from enum import Enum


class RetrievalMethod(str, Enum):
    """
    Indicates which retrieval stage produced the current ranking.
    """

    DENSE = "dense"
    BM25 = "bm25"
    HYBRID = "hybrid"
    RERANKED = "reranked"


@dataclass(frozen=True, slots=True)
class RetrievedChunkMetadata:
    """
    Metadata associated with a retrieved chunk.
    """

    document_id: str
    filename: str
    source_path: str

    chunk_index: int

    page_number: int | None = None
    section_title: str | None = None
    heading_level: int | None = None


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """
    Represents a retrieved chunk throughout the retrieval pipeline.

    The `score` field always represents the score currently used for
    ranking. Stage-specific scores are preserved for debugging,
    evaluation, and explainability.
    """

    id: str
    text: str
    metadata: RetrievedChunkMetadata

    #
    # Current ranking score.
    #
    score: float

    #
    # Scores produced by each retrieval stage.
    #
    dense_score: float | None = None
    bm25_score: float | None = None
    hybrid_score: float | None = None
    rerank_score: float | None = None

    #
    # Current rank after the latest stage.
    #
    rank: int | None = None

    #
    # Which stage produced the current ranking.
    #
    retrieval_method: RetrievalMethod = RetrievalMethod.DENSE

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def with_dense_score(
        self,
        score: float,
        rank: int | None = None,
    ) -> "RetrievedChunk":
        return replace(
            self,
            score=score,
            dense_score=score,
            rank=rank,
            retrieval_method=RetrievalMethod.DENSE,
        )

    def with_bm25_score(
        self,
        score: float,
        rank: int | None = None,
    ) -> "RetrievedChunk":
        return replace(
            self,
            score=score,
            bm25_score=score,
            rank=rank,
            retrieval_method=RetrievalMethod.BM25,
        )

    def with_hybrid_score(
        self,
        score: float,
        rank: int | None = None,
    ) -> "RetrievedChunk":
        return replace(
            self,
            score=score,
            hybrid_score=score,
            rank=rank,
            retrieval_method=RetrievalMethod.HYBRID,
        )

    def with_rerank_score(
        self,
        score: float,
        rank: int | None = None,
    ) -> "RetrievedChunk":
        return replace(
            self,
            score=score,
            rerank_score=score,
            rank=rank,
            retrieval_method=RetrievalMethod.RERANKED,
        )
