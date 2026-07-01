from functools import lru_cache

from fastapi import APIRouter, HTTPException

from rag_application.api.schemas import (
    QueryRequest,
    QueryResponse
)
from rag_application.config.settings import load_settings
from rag_application.ingestion.embedder import Embedder
from rag_application.llm.generator import GeminiGenerator
from rag_application.retrieval.retriever import Retriever
from rag_application.services.rag_service import RAGService
from rag_application.services.history_aware_rag_service import HistoryAwareRAGService 
from rag_application.vectorstore.pinecone_store import (
    PineconeVectorStore as VectorStore,
)
from rag_application.conversation.query_rewriter import QueryRewriter
from rag_application.conversation.session_manager import SessionManager
from rag_application.conversation.summarizer import ConversationSummarizer

router = APIRouter()


@lru_cache()
def get_rag_service() -> RAGService:
    settings = load_settings()

    embedder = Embedder(settings.embedding_config())
    sample_embedding = embedder.model.encode("dimension_check")
    dimension = len(sample_embedding)

    vector_store = VectorStore(
        settings=settings,
        dimension=dimension,
    )

    retriever = Retriever(
        vector_store=vector_store,
        embedding_model=embedder.model,
    )

    generator = GeminiGenerator(settings.generation_config())

    return RAGService(
        retriever=retriever,
        generator=generator,
    )

@lru_cache()
def get_history_aware_rag_service() -> HistoryAwareRAGService:
    settings = load_settings()

    embedder = Embedder(settings.embedding_config())
    sample_embedding = embedder.model.encode("dimension_check")
    dimension = len(sample_embedding)

    vector_store = VectorStore(
        settings=settings,
        dimension=dimension,
    )

    retriever = Retriever(
        vector_store=vector_store,
        embedding_model=embedder.model,
    )

    # This generator is used for final answer generation, will have the most powerful model and settings
    generator = GeminiGenerator(settings.generation_config()) 

    # This generator is used for query rewriting, will have a smaller model and settings to reduce cost and latency
    query_generator = GeminiGenerator(settings.generation_config())

    # This generator is used for conversation summarization, will have a smaller model and settings to reduce cost and latency
    summary_generator = GeminiGenerator(settings.generation_config())

    session_manager = SessionManager()

    query_rewriter = QueryRewriter(
        generator=query_generator
    )

    summarizer = ConversationSummarizer(
        generator=summary_generator
    )

    return HistoryAwareRAGService(
        retriever=retriever,
        generator=generator,
        session_manager=session_manager,
        query_rewriter=query_rewriter,
        summarizer=summarizer
    )


@router.post("/query", response_model=QueryResponse)
def query_documents(request: QueryRequest) -> QueryResponse:
    settings = load_settings()
    try:
        rag_service = get_history_aware_rag_service()

        answer, chunks = rag_service.answer_with_sources(
            conversation_id=request.conversation_id,
            question=request.question,
            top_k=settings.retrieval_top_k,
        )

        return QueryResponse(
            question=request.question,
            answer=answer,
            source_documents=[chunk.text for chunk in chunks] or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
