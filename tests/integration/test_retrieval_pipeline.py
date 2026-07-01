import os
from pathlib import Path

import pytest

from rag_application.config.settings import load_settings
from rag_application.ingestion.document_loader import DocumentLoader
from rag_application.ingestion.chunker import TextChunker
from rag_application.ingestion.processor import VectorDataProcessor
from rag_application.ingestion.embedder import Embedder
from rag_application.ingestion.pipeline import IngestionPipeline
from rag_application.retrieval.query_service import QueryService
from rag_application.retrieval.retriever import Retriever
from rag_application.vectorstore.pinecone_store import VectorStore


def test_retrieval_pipeline():
    pdf_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "cv.pdf"

    if not pdf_path.exists():
        pytest.skip("CV PDF is not available.")

    if not os.getenv("PINECONE_API_KEY") or not os.getenv("PINECONE_INDEX_NAME"):
        pytest.skip("Pinecone credentials are not configured.")

    settings = load_settings()

    document_loader = DocumentLoader()

    
    chunker = TextChunker(
        config=settings.chunking_config()
    )

    embedder = Embedder(
        config=settings.embedding_config()
    )
    dimension = len(embedder.model.encode("test"))

    vector_data_processor = VectorDataProcessor()

    vector_store = VectorStore(
        settings=settings,
        dimension=dimension
    )

    ingestion_pipeline = IngestionPipeline(
        document_loader=document_loader,
        chunker=chunker,
        embedder=embedder,
        vector_data_processor=vector_data_processor,
        vector_store=vector_store
    )
    ingestion_pipeline.run(str(pdf_path))

    retriever = Retriever(
        vector_store=vector_store,
        embedding_model=embedder.model
    )
    query_service = QueryService(retriever)

    results = query_service.search("Who is Nithusikan?")

    assert len(results) > 0
