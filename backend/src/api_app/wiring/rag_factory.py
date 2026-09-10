import json
import logging
from functools import lru_cache
from pathlib import Path

from rag_application.config.settings import load_settings
from rag_application.conversation.query_rewriter import QueryRewriter
from rag_application.conversation.summarizer import ConversationSummarizer
from rag_application.indexes.bm25_index import BM25Index
from rag_application.ingestion.embedder import Embedder
from rag_application.ingestion.schemas import (
    ChunkMetadata,
    DocumentChunk,
)
from rag_application.llm.generator import GeminiGenerator
from rag_application.retrieval.bm25_retriever import BM25Retriever
from rag_application.retrieval.dense_retriever import DenseRetriever
from rag_application.retrieval.hybrid_retriever import HybridRetriever
from rag_application.retrieval.query_service import QueryService
from rag_application.retrieval.reranker import Reranker
from rag_application.services.history_aware_rag_service import (
    HistoryAwareRAGService,
)
from rag_application.vectorstore.pinecone_store import PineconeVectorStore

from api_app.db.session import get_session_factory
from api_app.services.conversation_store import PersistentConversationStore
from api_app.wiring.bm25_loader import load_bm25_documents

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
def build_embedder() -> Embedder:
    """
    One embedding model for the whole process.

    Ingestion and querying previously each built their own, loading two
    copies of the same weights into memory.
    """

    return Embedder(load_settings().embedding_config())


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

    settings = load_settings()

    #
    # Embedding Model and Vector Store (shared with the ingestion path)
    #
    embedder = build_embedder()

    #
    # Dense Retriever
    #
    dense_retriever = DenseRetriever(
        vector_store=build_vector_store(),
        embedding_model=embedder.model,
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
    reranker = Reranker(
        model_name=DEFAULT_RERANKER_MODEL,
    )

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
    llm = GeminiGenerator(
        settings.generation_config(),
    )

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
