import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

if os.getenv("RUN_REAL_RAG_TESTS") != "1":
    pytest.skip(
        "Set RUN_REAL_RAG_TESTS=1 to run live Pinecone integration tests.",
        allow_module_level=True,
    )

pytest.importorskip("sentence_transformers")

from rag_application.config.settings import load_settings
from rag_application.ingestion.chunker import TextChunker
from rag_application.ingestion.document_loader import DocumentLoader
from rag_application.ingestion.embedder import Embedder
from rag_application.ingestion.processor import VectorDataProcessor
from rag_application.retrieval.dense_retriever import DenseRetriever
from rag_application.vectorstore.pinecone_store import PineconeVectorStore


def test_retriever_returns_chunks():
    file_path = Path(__file__).resolve().parents[1] / "fixtures" / "cv.pdf"

    if not file_path.exists():
        pytest.skip("CV PDF fixture is not available.")

    settings = load_settings()
    document = DocumentLoader().load(file_path)
    chunks = TextChunker(config=settings.chunking_config()).chunk(document)
    embedder = Embedder(config=settings.embedding_config())
    embedded_chunks = embedder.embed_batch(chunks)
    vector_data = VectorDataProcessor().prepare(embedded_chunks)

    vector_store = PineconeVectorStore(
        settings=settings,
        dimension=embedder.dimension,
    )
    vector_store.upsert(vector_data)

    retriever = DenseRetriever(
        vector_store=vector_store,
        embedding_model=embedder.model,
    )

    retrieved_chunks = retriever.retrieve(
        query="Who is Dr.Isuru Nawinne",
        top_k=7,
    )

    assert retrieved_chunks
