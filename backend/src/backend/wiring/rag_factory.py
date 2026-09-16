import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rag.config.component_configs import GenerationConfig
from rag.config.settings import load_settings
from rag.conversation.query_rewriter import QueryRewriter
from rag.conversation.summarizer import ConversationSummarizer
from rag.embeddings.pinecone_embedder import PineconeEmbedder
from rag.indexes.bm25_index import BM25Index
from rag.ingestion.schemas import (
    ChunkMetadata,
    DocumentChunk,
)
from rag.llm.generator import GeminiGenerator
from rag.llm.groq_generator import GroqGenerator
from rag.llm.protocol import TextGenerator
from rag.rerankers.fallback_reranker import FallbackReranker
from rag.rerankers.gemini_reranker import GeminiReranker
from rag.rerankers.pinecone_reranker import PineconeReranker
from rag.retrieval.bm25_retriever import BM25Retriever
from rag.retrieval.dense_retriever import DenseRetriever
from rag.retrieval.hybrid_retriever import HybridRetriever
from rag.retrieval.query_service import QueryService
from rag.services.history_aware_rag_service import (
    HistoryAwareRAGService,
)
from rag.vectorstore.pinecone_store import PineconeVectorStore

from backend.db.session import get_session_factory
from backend.services.conversation_store import PersistentConversationStore
from backend.wiring.bm25_loader import load_bm25_documents

logger = logging.getLogger(__name__)

DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-base"


def _parse_chunk_index(
    chunk_id: str,
    fallback: int,
) -> int:
    marker = "_chunk_"

    if marker not in chunk_id:
        return fallback

    try:
        return int(chunk_id.rsplit(marker, 1)[1])
    except ValueError:
        return fallback


def _parse_document_id(
    chunk_id: str,
) -> str:
    marker = "_chunk_"

    if marker not in chunk_id:
        return chunk_id

    return chunk_id.split(marker, 1)[0]


def load_bm25_corpus(
    corpus_path: Path,
) -> list[DocumentChunk]:
    if not corpus_path.exists():
        logger.warning(
            "BM25 corpus not found at %s.",
            corpus_path,
        )

        return []

    with corpus_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        rows = json.load(file)

    chunks: list[DocumentChunk] = []

    for index, row in enumerate(rows):
        chunk_id = row["id"]
        metadata_row = row.get("metadata", row)

        metadata = ChunkMetadata(
            document_id=metadata_row.get(
                "document_id",
                _parse_document_id(chunk_id),
            ),
            filename=metadata_row.get(
                "filename",
                _parse_document_id(chunk_id),
            ),
            source_path=metadata_row.get(
                "source_path",
                metadata_row.get("source", ""),
            ),
            page_number=metadata_row.get("page_number"),
            section_title=metadata_row.get("section_title"),
            heading_level=metadata_row.get("heading_level"),
            start_char=metadata_row.get("start_char"),
            end_char=metadata_row.get("end_char"),
            chunk_size=metadata_row.get("chunk_size", 0),
            overlap_size=metadata_row.get("overlap_size", 0),
            element_id=metadata_row.get("element_id"),
            element_type=metadata_row.get("element_type"),
            language=metadata_row.get("language", "en"),
            tags=metadata_row.get("tags", []),
        )

        chunks.append(
            DocumentChunk(
                id=chunk_id,
                chunk_index=metadata_row.get(
                    "chunk_index",
                    _parse_chunk_index(
                        chunk_id,
                        index,
                    ),
                ),
                text=row["text"],
                metadata=metadata,
            )
        )

    logger.info(
        "Loaded %d BM25 chunks from %s",
        len(chunks),
        corpus_path,
    )

    return chunks


@lru_cache
def build_embedder():
    """
    One embedder for the whole process, shared by ingestion and querying.

    Hosted inference is the default: it downloads no weights, so the service
    starts in seconds and the deployed image needs neither PyTorch nor
    sentence-transformers. Set USE_HOSTED_INFERENCE=false to run the local
    model instead, which requires the rag package's "local-models" extra.
    """

    settings = load_settings()

    if settings.use_hosted_inference:
        return PineconeEmbedder(settings.hosted_embedding_config())

    # Imported lazily so the module loads without torch installed.
    from rag.ingestion.embedder import Embedder

    return Embedder(settings.embedding_config())


@lru_cache
def build_generator() -> GeminiGenerator:
    """
    One Gemini client for the whole process, shared by generation, query
    rewriting, summarization, and the reranker fallback.
    """

    return GeminiGenerator(load_settings().generation_config())


DEFAULT_GENERATION_MODEL_ID = "gemini-flash"

# id -> (label, provider, model_name). model_name is None for the Gemini
# entry, which generates through the shared build_generator() singleton
# (settings.generation_model_name) rather than a fixed string here.
_GENERATION_MODEL_SPECS: dict[str, tuple[str, str, str | None]] = {
    DEFAULT_GENERATION_MODEL_ID: ("Gemini (default)", "gemini", None),
    "groq-gpt-oss-120b": ("GPT-OSS 120B (Groq)", "groq", "openai/gpt-oss-120b"),
    "groq-gpt-oss-20b": ("GPT-OSS 20B (Groq)", "groq", "openai/gpt-oss-20b"),
    "groq-qwen3.8-27b": ("Qwen3.8 27B (Groq)", "groq", "qwen/qwen3.8-27b"),
}

# Daily token quotas for the admin usage dashboard. Gemini is billed, not
# quota-limited on our plan, so it has no ceiling here. The Groq numbers are
# Groq's free-tier per-model daily token limits (console.groq.com/docs/rate-
# limits) at the time this was written - Groq can and does change these, and
# "qwen3.8-27b" in particular is a newer catalog entry whose published limit
# is less certain than the gpt-oss pair's, so treat these as a starting point
# to verify against the console rather than a guarantee. There is
# deliberately no env var override: change the constant here if a limit
# turns out to be wrong.
_DAILY_TOKEN_LIMITS: dict[str, int | None] = {
    DEFAULT_GENERATION_MODEL_ID: None,
    "groq-gpt-oss-120b": 200_000,
    "groq-gpt-oss-20b": 200_000,
    "groq-qwen3.8-27b": 200_000,
}


@dataclass(frozen=True)
class GenerationModelOption:
    id: str
    label: str
    provider: str


class UnknownGenerationModelError(ValueError):
    """Raised for a model id that isn't currently offered."""


def available_generation_models() -> list[GenerationModelOption]:
    """
    Models the UI may offer right now.

    Groq entries are omitted entirely when GROQ_API_KEY isn't configured,
    rather than being listed and failing on first use.
    """

    settings = load_settings()

    models = []

    for model_id, (label, provider, _) in _GENERATION_MODEL_SPECS.items():
        if provider == "groq" and not settings.groq_api_key:
            continue

        models.append(
            GenerationModelOption(id=model_id, label=label, provider=provider)
        )

    return models


def all_generation_models() -> list[GenerationModelOption]:
    """
    Every model in the catalog, regardless of whether it is currently
    configured.

    Unlike available_generation_models(), this doesn't call load_settings()
    or filter on GROQ_API_KEY - it's for the admin usage dashboard, where a
    Groq model's historical usage should stay visible even if the key is
    later removed, and it needs no credentials to answer.
    """

    return [
        GenerationModelOption(id=model_id, label=label, provider=provider)
        for model_id, (label, provider, _) in _GENERATION_MODEL_SPECS.items()
    ]


def daily_token_limit(model_id: str) -> int | None:
    """None means no configured limit (usage is still tracked, just not capped)."""

    return _DAILY_TOKEN_LIMITS.get(model_id)


@lru_cache
def _build_groq_generator(model_name: str) -> GroqGenerator:
    settings = load_settings()

    return GroqGenerator(
        GenerationConfig(
            model_name=model_name,
            api_key=settings.groq_api_key,
        )
    )


def resolve_generator(model_id: str | None) -> tuple[TextGenerator, str]:
    """
    Resolve a client-requested model id to a generator for one query call.

    Defaults to DEFAULT_GENERATION_MODEL_ID when no id is given. Raises
    UnknownGenerationModelError for an id that isn't currently offered
    (unknown, or a Groq model with no key configured), so the router can
    turn that into a 400 instead of silently substituting a different model
    than the one the user asked for.
    """

    resolved_id = model_id or DEFAULT_GENERATION_MODEL_ID
    spec = _GENERATION_MODEL_SPECS.get(resolved_id)
    settings = load_settings()

    if spec is None or (spec[1] == "groq" and not settings.groq_api_key):
        raise UnknownGenerationModelError(resolved_id)

    _, provider, model_name = spec

    if provider == "gemini":
        return build_generator(), resolved_id

    return _build_groq_generator(model_name), resolved_id


@lru_cache
def build_reranker():
    """
    Hosted reranking by default, with the shared Gemini model as a fallback
    when the hosted call fails; the local cross-encoder only when hosted
    inference is disabled entirely.
    """

    settings = load_settings()

    if settings.use_hosted_inference:
        primary = PineconeReranker(settings.hosted_rerank_config())
        fallback = GeminiReranker(build_generator())
        return FallbackReranker(primary=primary, fallback=fallback)

    # Imported lazily so the module loads without torch installed.
    from rag.rerankers.local_reranker import Reranker

    return Reranker(model_name=DEFAULT_RERANKER_MODEL)


@lru_cache
def build_vector_store() -> PineconeVectorStore:
    return PineconeVectorStore(
        settings=load_settings(),
        dimension=build_embedder().dimension,
    )


@lru_cache
def build_bm25_index() -> BM25Index:
    """
    The one BM25 index the running service uses.

    Cached so that ingesting or deleting a document can refresh it in place
    with .rebuild(), instead of tearing down the whole RAG service and
    reloading the embedding model and cross-encoder reranker with it.
    """

    return BM25Index(documents=load_bm25_documents(get_session_factory()))


def refresh_bm25_index() -> int:
    """
    Reload the lexical corpus into the live index.

    The running service holds a reference to the same object, so the change
    is visible immediately without a restart.
    """

    documents = load_bm25_documents(get_session_factory())
    build_bm25_index().rebuild(documents)

    return len(documents)


@lru_cache
def build_history_aware_rag_service() -> HistoryAwareRAGService:
    #
    # Embedding Model and Vector Store (shared with the ingestion path)
    #
    embedder = build_embedder()

    #
    # Dense Retriever
    #
    dense_retriever = DenseRetriever(
        vector_store=build_vector_store(),
        embedding_model=embedder,
    )

    #
    # BM25 Retriever
    #
    bm25_retriever = BM25Retriever(
        bm25_index=build_bm25_index(),
    )

    #
    # Hybrid Retriever
    #
    hybrid_retriever = HybridRetriever(
        dense_retriever=dense_retriever,
        bm25_retriever=bm25_retriever,
    )

    #
    # Reranker
    #
    reranker = build_reranker()

    #
    # Query Service
    #
    query_service = QueryService(
        retriever=hybrid_retriever,
        reranker=reranker,
    )

    #
    # LLM
    #
    llm = build_generator()

    #
    # Conversation Components
    #
    session_manager = PersistentConversationStore(get_session_factory())

    query_rewriter = QueryRewriter(llm)

    summarizer = ConversationSummarizer(llm)

    #
    # RAG Service
    #
    rag_service = HistoryAwareRAGService(
        query_service=query_service,
        generator=llm,
        session_manager=session_manager,
        query_rewriter=query_rewriter,
        summarizer=summarizer,
    )

    logger.info("History-aware RAG system initialized successfully.")

    return rag_service
