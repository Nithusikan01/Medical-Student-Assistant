import os
from dotenv import load_dotenv

from sentence_transformers import SentenceTransformer

from rag_application.config.settings import load_settings
from rag_application.vectorstore.pinecone_store import VectorStore
from rag_application.retrieval.retriever import Retriever
from rag_application.llm.generator import GeminiGenerator
from rag_application.services.rag_service import RAGService


def test_full_rag_pipeline():

    # -----------------------------------
    # Load environment + settings
    # -----------------------------------
    load_dotenv()
    settings = load_settings()

    # -----------------------------------
    # Embedding model (same as production)
    # -----------------------------------
    embedding_model = SentenceTransformer(
        settings.embedding_model_name
    )

    # -----------------------------------
    # Vector store (REAL Pinecone)
    # -----------------------------------
    vector_store = VectorStore(
        settings=settings,
        dimension=len(
            embedding_model.encode("test")
        )
    )

    # -----------------------------------
    # Retriever
    # -----------------------------------
    retriever = Retriever(
        vector_store=vector_store,
        embedding_model=embedding_model
    )

    # -----------------------------------
    # LLM (REAL Gemini API call)
    # -----------------------------------
    generator = GeminiGenerator(
        settings=settings
    )

    # -----------------------------------
    # RAG Service
    # -----------------------------------
    rag = RAGService(
        retriever=retriever,
        generator=generator
    )

    # -----------------------------------
    # Test query (your CV-based question)
    # -----------------------------------
    question = "Who is Nithusikan?"

    answer = rag.answer(question)

    # -----------------------------------
    # Assertions (lightweight, stable)
    # -----------------------------------
    assert answer is not None
    assert isinstance(answer, str)
    assert len(answer) > 0

    # Optional debug print
    print("\n🔥 RAG ANSWER:\n")
    print(answer)