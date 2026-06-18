from functools import lru_cache

from fastapi import APIRouter, HTTPException

from rag_application.api.schemas import (
    QueryRequest,
    QueryResponse
)
from rag_application.config.component_configs import (
    EmbeddingConfig,
    GenerationConfig,
)
from rag_application.config.settings import load_settings
from rag_application.ingestion.embedder import Embedder
from rag_application.llm.generator import GeminiGenerator
from rag_application.llm.prompt_builder import PromptBuilder
from rag_application.retrieval.retriever import Retriever
from rag_application.services.rag_service import RAGService
from rag_application.vectorstore.pinecone_store import (
    PineconeVectorStore as VectorStore,
)

router = APIRouter()


@lru_cache()
def get_rag_service() -> RAGService:
    settings = load_settings()

    embedding_config = EmbeddingConfig(
        model_name=settings.embedding_model_name,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    generation_config = GenerationConfig(
        model_name=settings.generation_model_name,
        api_key=settings.gemini_api_key,
    )

    embedder = Embedder(embedding_config)
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

    generator = GeminiGenerator(generation_config)

    return RAGService(
        retriever=retriever,
        generator=generator,
    )


@router.post("/query", response_model=QueryResponse)
def query_documents(request: QueryRequest) -> QueryResponse:
    try:
        rag_service = get_rag_service()

        chunks = rag_service.retriever.retrieve(
            query=request.question,
            top_k=request.top_k,
        )

        if not chunks:
            return QueryResponse(
                question=request.question,
                answer="I don't know based on the provided document.",
                source_documents=None,
            )

        prompt = PromptBuilder.build_prompt(
            question=request.question,
            chunks=chunks,
        )

        response = rag_service.generator.generate(prompt)

        return QueryResponse(
            question=request.question,
            answer=response.text,
            source_documents=[chunk.text for chunk in chunks],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc