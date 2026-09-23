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


@dataclass(frozen=True)
class CacheConfig:
    """
    Bounds for the response cache.

    `store_context_free_only` is the correctness control rather than a
    tuning knob: an answer generated with conversation history in its
    prompt can refer back to that conversation, and serving it to someone
    else would be wrong. Left on, only answers generated with no history
    are ever stored, and every entry is safe to serve to anyone.
    """

    enabled: bool = True
    semantic_enabled: bool = True
    max_entries: int = 512
    ttl_seconds: int = 86_400
    # Deliberately high. Serving the answer to a *nearly* identical
    # question is worse than missing, and this corpus is study material.
    similarity_threshold: float = 0.95
    store_context_free_only: bool = True


@dataclass(frozen=True)
class SmallTalkConfig:
    """
    How the assistant introduces itself when there is nothing to retrieve.

    `enabled` turns the whole short-circuit off, which sends greetings
    back down the retrieval path - the behaviour it exists to replace,
    kept reachable because it is the strictly grounded one.
    """

    enabled: bool = True
    assistant_name: str = "Anamnesis"
    # What the corpus is, as a noun phrase completing "I'm <name>, your
    # ...". Deployment-specific: another class uploads other material.
    corpus_description: str = "study assistant for this class's document library"
