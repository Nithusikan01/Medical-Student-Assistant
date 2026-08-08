import json
import logging
from functools import lru_cache
from pathlib import Path

from rag_application.config.settings import load_settings

from rag_application.ingestion.embedder import Embedder
from rag_application.ingestion.schemas import (
    ChunkMetadata,
    DocumentChunk,
)

from rag_application.vectorstore.pinecone_store import PineconeVectorStore

from rag_application.indexes.bm25_index import BM25Index

from rag_application.retrieval.dense_retriever import DenseRetriever
from rag_application.retrieval.bm25_retriever import BM25Retriever
from rag_application.retrieval.hybrid_retriever import HybridRetriever
from rag_application.retrieval.reranker import Reranker
from rag_application.retrieval.query_service import QueryService

from rag_application.llm.generator import GeminiGenerator

from rag_application.conversation.query_rewriter import QueryRewriter
from rag_application.conversation.session_manager import SessionManager
from rag_application.conversation.summarizer import ConversationSummarizer

from rag_application.services.history_aware_rag_service import (
    HistoryAwareRAGService,
)

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

        metadata = ChunkMetadata(
            document_id=row.get(
                "document_id",
                _parse_document_id(chunk_id),
            ),
            filename=row.get(
                "filename",
                _parse_document_id(chunk_id),
            ),
            source_path=row.get(
                "source_path",
                "",
            ),
            page_number=row.get("page_number"),
            section_title=row.get("section_title"),
            heading_level=row.get("heading_level"),
            start_char=row.get("start_char"),
            end_char=row.get("end_char"),
            chunk_size=row.get("chunk_size", 0),
            overlap_size=row.get("overlap_size", 0),
            element_id=row.get("element_id"),
            element_type=row.get("element_type"),
            language=row.get("language", "en"),
            tags=row.get("tags", []),
        )

        chunks.append(
            DocumentChunk(
                id=chunk_id,
                chunk_index=row.get(
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


@lru_cache()
def build_history_aware_rag_service() -> HistoryAwareRAGService:

    settings = load_settings()

    #
    # Embedding Model
    #
    embedder = Embedder(
        settings.embedding_config()
    )

    #
    # Vector Store
    #
    vector_store = PineconeVectorStore(
        settings=settings,
        dimension=embedder.dimension
    )

    #
    # Dense Retriever
    #
    dense_retriever = DenseRetriever(
        vector_store=vector_store,
        embedding_model=embedder.model,
    )

    #
    # BM25 Retriever
    #
    bm25_documents = load_bm25_corpus(
        corpus_path=settings.bm25_corpus_path
    )

    bm25_index = BM25Index(
        documents=bm25_documents,
    )

    bm25_retriever = BM25Retriever(
        bm25_index=bm25_index,
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
    session_manager = SessionManager()

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

    logger.info(
        "History-aware RAG system initialized successfully."
    )

    return rag_service