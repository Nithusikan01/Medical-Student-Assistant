import logging

from rag_application.config.settings import load_settings

from rag_application.ingestion.embedder import Embedder
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
    # 5. BBM25 Index + Retriever
    # -----------------------------
    # NOTE:
    # You MUST populate this from ingestion pipeline later.
    # For now, we initialize empty index safely.
    bm25_index = BM25Index(documents=[])    # placeholder corpus

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
