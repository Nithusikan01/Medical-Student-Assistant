import logging

from rag_application.config.component_configs import PineconeRerankConfig
from rag_application.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class PineconeReranker:
    """
    Cross-encoder reranking through Pinecone's hosted inference API.

    Same contract as the local Reranker, so the query service is unaware of
    which one it holds - but with no model weights to download and a
    stronger model than the local default.
    """

    def __init__(self, config: PineconeRerankConfig) -> None:
        from pinecone import Pinecone

        self._client = Pinecone(api_key=config.api_key)
        self.model_name = config.model_name

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        if not candidates:
            logger.warning("No candidates provided to reranker.")
            return []

        try:
            response = self._client.inference.rerank(
                model=self.model_name,
                query=query,
                documents=[{"text": chunk.text} for chunk in candidates],
                top_n=min(top_k, len(candidates)),
                return_documents=False,
            )
        except Exception:
            # Reranking is a refinement, not a requirement: falling back to
            # the fused order keeps the question answerable when the hosted
            # model is unreachable or the quota is spent.
            logger.exception("Reranking failed; falling back to the retrieval order.")
            return candidates[:top_k]

        results = [
            candidates[item.index].with_rerank_score(
                score=float(item.score),
                rank=rank,
            )
            for rank, item in enumerate(response.data, start=1)
        ]

        logger.debug(
            "Reranker reduced %d candidates to %d.",
            len(candidates),
            len(results),
        )

        return results
