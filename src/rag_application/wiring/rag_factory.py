import json
import logging
from pathlib import Path

from rag_application.config.settings import load_settings

from rag_application.ingestion.embedder import Embedder
from rag_application.ingestion.schemas import DocumentChunk
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

from rag_application.services.history_aware_rag_service import HistoryAwareRAGService

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BM25_CORPUS_PATH = PROJECT_ROOT / "storage" / "bm25_corpus.json"


def _parse_chunk_index(chunk_id: str, fallback: int) -> int:
    marker = "_chunk_"
    if marker not in chunk_id:
        return fallback

    try:
        return int(chunk_id.rsplit(marker, 1)[1])
    except ValueError:
        return fallback


def _parse_source(chunk_id: str) -> str:
    marker = "_chunk_"
    if marker not in chunk_id:
        return "bm25_corpus"

    return chunk_id.split(marker, 1)[0]


def load_bm25_documents(
    corpus_path: Path = DEFAULT_BM25_CORPUS_PATH,
) -> list[DocumentChunk]:
    if not corpus_path.exists():
        logger.warning(
            "BM25 corpus not found at %s. BM25 retrieval will be empty.",
            corpus_path,
        )
        return []

    with corpus_path.open("r", encoding="utf-8") as file:
        rows = json.load(file)

    documents = []
    for index, row in enumerate(rows):
        chunk_id = row["id"]
        documents.append(
            DocumentChunk(
                id=chunk_id,
                text=row["text"],
                source=row.get("source", _parse_source(chunk_id)),
                chunk_index=row.get(
                    "chunk_index",
                    _parse_chunk_index(chunk_id, index),
                ),
                page_number=row.get("page_number"),
                timestamp=row.get("timestamp", 0),
            )
        )

    logger.info(
        "Loaded %d BM25 documents from %s",
        len(documents),
        corpus_path,
    )
    return documents


def build_history_aware_rag_service() -> HistoryAwareRAGService:

    # -----------------------------
    # 1. Settings
    # -----------------------------
    settings = load_settings()

    # -----------------------------
    # 2. Embedding model
    # -----------------------------
    embedder = Embedder(settings.embedding_config())

    sample_embedding = embedder.model.encode("dimension_check")
    dimension = len(sample_embedding)

    # -----------------------------
    # 3. Vector store
    # -----------------------------
    vector_store = PineconeVectorStore(
        settings=settings,
        dimension=dimension
    )

    # -----------------------------
    # 4. Dense retriever
    # -----------------------------
    dense_retriever = DenseRetriever(
        vector_store=vector_store,
        embedding_model=embedder.model
    )

    # -----------------------------
    # 5. BM25 Index + Retriever
    # -----------------------------
    bm25_documents = load_bm25_documents()
    bm25_index = BM25Index(documents=bm25_documents)

    bm25_retriever = BM25Retriever(
        bm25_index=bm25_index
    )

    # -----------------------------
    # 6. Hybrid retriever
    # -----------------------------
    hybrid_retriever = HybridRetriever(
        dense_retriever=dense_retriever,
        bm25_retriever=bm25_retriever
    )

    # -----------------------------
    # 7. Reranker Integration
    # -----------------------------
    reranker = Reranker(
        model_name="BAAI/bge-reranker-base"
    )


    query_service = QueryService(
        retriever=hybrid_retriever,
        reranker=reranker
    )




    # -----------------------------
    # 8. LLM (SINGLE INSTANCE)
    # -----------------------------
    llm = GeminiGenerator(settings.generation_config())

    # -----------------------------
    # 9. Conversation layer
    # -----------------------------
    session_manager = SessionManager()

    query_rewriter = QueryRewriter(llm)
    summarizer = ConversationSummarizer(llm)

    # -----------------------------
    # 10. RAG Service
    # -----------------------------
    rag_service = HistoryAwareRAGService(
        query_service=query_service,
        generator=llm,
        session_manager=session_manager,
        query_rewriter=query_rewriter,
        summarizer=summarizer
    )

    logger.info("RAG system successfully initialized")

    return rag_service
