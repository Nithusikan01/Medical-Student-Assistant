from dataclasses import dataclass


@dataclass(frozen=True)
class PineconeConfig:
    api_key: str
    index_name: str


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str
    batch_size: int = 32


@dataclass(frozen=True)
class PineconeEmbeddingConfig:
    api_key: str
    model_name: str
    # Fixed by the hosted model; the Pinecone index must be created to match.
    dimension: int


@dataclass(frozen=True)
class PineconeRerankConfig:
    api_key: str
    model_name: str


@dataclass(frozen=True)
class GenerationConfig:
    model_name: str
    api_key: str


@dataclass(frozen=True)
class ChunkingConfig:
    chunk_size: int
    chunk_overlap: int


@dataclass(frozen=True)
class RetrievalConfig:
    candidate_k: int = 20
    dense_top_k: int = 20
    reranking_k: int = 8
    final_context_k: int = 5
    similarity_threshold: float = 0.7
