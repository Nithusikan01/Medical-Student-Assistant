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
from rag_application.ingestion.pipeline import IngestionPipeline
from rag_application.ingestion.processor import VectorDataProcessor
from rag_application.retrieval.dense_retriever import DenseRetriever
from rag_application.retrieval.query_service import QueryService
from rag_application.vectorstore.pinecone_store import PineconeVectorStore


def test_retrieval_pipeline():
    pdf_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "cv.pdf"

    if not pdf_path.exists():
        pytest.skip("CV PDF is not available.")

    settings = load_settings()
    embedder = Embedder(config=settings.embedding_config())
    vector_store = PineconeVectorStore(
        settings=settings,
        dimension=embedder.dimension,
    )
    ingestion_pipeline = IngestionPipeline(
        loader=DocumentLoader(),
        chunker=TextChunker(config=settings.chunking_config()),
        embedder=embedder,
        processor=VectorDataProcessor(),
        vector_store=vector_store,
        batch_size=settings.embedding_batch_size,
        bm25_corpus_path=settings.bm25_corpus_path,
    )
    ingestion_pipeline.ingest(str(pdf_path))

    retriever = DenseRetriever(
        vector_store=vector_store,
        embedding_model=embedder.model,
    )
    query_service = QueryService(retriever)

    results = query_service.search("Who is Nithusikan?")

    assert len(results) > 0
