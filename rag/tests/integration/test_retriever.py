import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[3] / "backend" / ".env")

if os.getenv("RUN_REAL_RAG_TESTS") != "1":
    pytest.skip(
        "Set RUN_REAL_RAG_TESTS=1 to run live Pinecone integration tests.",
        allow_module_level=True,
    )

pytest.importorskip("sentence_transformers")

from rag.config.settings import load_settings
from rag.embeddings.local_embedder import Embedder
from rag.ingestion.chunker import TextChunker
from rag.ingestion.document_loader import DocumentLoader
from rag.ingestion.processor import VectorDataProcessor
from rag.ingestion.schemas import EmbeddedChunk
from rag.retrieval.dense_retriever import DenseRetriever
from rag.vectorstore.pinecone_store import PineconeVectorStore


def test_retriever_returns_chunks():
    file_path = Path(__file__).resolve().parents[1] / "fixtures" / "cv.pdf"

    if not file_path.exists():
        pytest.skip("CV PDF fixture is not available.")

    settings = load_settings()
    document = DocumentLoader().load(file_path)
    chunks = TextChunker(config=settings.chunking_config()).chunk(document)
    embedder = Embedder(config=settings.embedding_config())
    vectors = embedder.embed_documents([chunk.text for chunk in chunks])
    embedded_chunks = [
        EmbeddedChunk(
            id=chunk.id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            metadata=chunk.metadata,
            embedding=vector,
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    vector_data = VectorDataProcessor().prepare(embedded_chunks)

    vector_store = PineconeVectorStore(
        config=settings.pinecone_config(),
        dimension=embedder.dimension,
    )
    vector_store.ensure_index()
    vector_store.upsert(vector_data)

    retriever = DenseRetriever(
        vector_store=vector_store,
        embedding_model=embedder,
    )

    retrieved_chunks = retriever.retrieve(
        query="Who is Dr.Isuru Nawinne",
        top_k=7,
    )

    assert retrieved_chunks
