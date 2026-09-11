import os
from dataclasses import dataclass
from pathlib import Path

from rag.config.component_configs import (
    ChunkingConfig,
    EmbeddingConfig,
    GenerationConfig,
    PineconeConfig,
    PineconeEmbeddingConfig,
    PineconeRerankConfig,
    RetrievalConfig,
)


@dataclass(frozen=True)
class Settings:
    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------
    pinecone_api_key: str
    pinecone_index_name: str
    gemini_api_key: str

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    storage_path: Path = Path("storage")
    bm25_corpus_path: Path = Path("storage") / "bm25_corpus.json"

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------
    chunk_size: int = 500
    chunk_overlap: int = 50

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_batch_size: int = 32

    # ------------------------------------------------------------------
    # Hosted inference (Pinecone)
    #
    # When enabled, embedding and reranking run through Pinecone's API and
    # no model weights are downloaded. The embedding dimension is fixed by
    # the hosted model, so the index must be created to match it.
    # ------------------------------------------------------------------
    use_hosted_inference: bool = True
    hosted_embedding_model: str = "llama-text-embed-v2"
    hosted_embedding_dimension: int = 1024
    hosted_rerank_model: str = "bge-reranker-v2-m3"

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    candidate_k: int = 20
    dense_top_k: int = 20
    reranking_k: int = 8
    final_context_k: int = 5
    similarity_threshold: float = 0.7

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    generation_model_name: str = "gemini-3.1-flash-lite"

    # ------------------------------------------------------------------
    # Component Configurations
    # ------------------------------------------------------------------
    def pinecone_config(self) -> PineconeConfig:
        return PineconeConfig(
            api_key=self.pinecone_api_key,
            index_name=self.pinecone_index_name,
        )

    def embedding_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            model_name=self.embedding_model_name,
            batch_size=self.embedding_batch_size,
        )

    def hosted_embedding_config(self) -> PineconeEmbeddingConfig:
        return PineconeEmbeddingConfig(
            api_key=self.pinecone_api_key,
            model_name=self.hosted_embedding_model,
            dimension=self.hosted_embedding_dimension,
        )

    def hosted_rerank_config(self) -> PineconeRerankConfig:
        return PineconeRerankConfig(
            api_key=self.pinecone_api_key,
            model_name=self.hosted_rerank_model,
        )

    def generation_config(self) -> GenerationConfig:
        return GenerationConfig(
            model_name=self.generation_model_name,
            api_key=self.gemini_api_key,
        )

    def chunking_config(self) -> ChunkingConfig:
        return ChunkingConfig(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

    def retrieval_config(self) -> RetrievalConfig:
        return RetrievalConfig(
            candidate_k=self.candidate_k,
            dense_top_k=self.dense_top_k,
            reranking_k=self.reranking_k,
            final_context_k=self.final_context_k,
            similarity_threshold=self.similarity_threshold,
        )


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)

    if raw is None:
        return default

    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    pinecone_index_name = os.getenv("PINECONE_INDEX_NAME")
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not pinecone_api_key:
        raise ValueError("PINECONE_API_KEY environment variable is not set.")

    if not pinecone_index_name:
        raise ValueError("PINECONE_INDEX_NAME environment variable is not set.")

    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    storage_path = Path(os.getenv("STORAGE_PATH", "storage"))

    return Settings(
        pinecone_api_key=pinecone_api_key,
        pinecone_index_name=pinecone_index_name,
        gemini_api_key=gemini_api_key,
        storage_path=storage_path,
        bm25_corpus_path=storage_path / "bm25_corpus.json",
        chunk_size=int(os.getenv("CHUNK_SIZE", "500")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "50")),
        embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "32")),
        candidate_k=int(os.getenv("CANDIDATE_K", "20")),
        dense_top_k=int(os.getenv("DENSE_TOP_K", "20")),
        reranking_k=int(os.getenv("RERANKING_K", "8")),
        final_context_k=int(os.getenv("FINAL_CONTEXT_K", "5")),
        similarity_threshold=float(os.getenv("SIMILARITY_THRESHOLD", "0.7")),
        embedding_model_name=os.getenv(
            "EMBEDDING_MODEL_NAME",
            "sentence-transformers/all-MiniLM-L6-v2",
        ),
        generation_model_name=os.getenv(
            "GENERATION_MODEL_NAME",
            "gemini-3.1-flash-lite",
        ),
        use_hosted_inference=_env_bool("USE_HOSTED_INFERENCE", True),
        hosted_embedding_model=os.getenv(
            "HOSTED_EMBEDDING_MODEL",
            "llama-text-embed-v2",
        ),
        hosted_embedding_dimension=int(os.getenv("HOSTED_EMBEDDING_DIMENSION", "1024")),
        hosted_rerank_model=os.getenv(
            "HOSTED_RERANK_MODEL",
            "bge-reranker-v2-m3",
        ),
    )
