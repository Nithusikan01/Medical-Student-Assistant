from unittest.mock import Mock

from rag_application.ingestion.pipeline import IngestionPipeline
from rag_application.ingestion.schemas import DocumentChunk


def test_ingestion_pipeline_runs_all_steps(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    document_loader = Mock()
    chunker = Mock()
    embedder = Mock()
    vector_data_processor = Mock()
    vector_store = Mock()

    chunks = [
        DocumentChunk(
            id="cv.pdf_chunk_0",
            text="chunk text",
            source="cv.pdf",
            chunk_index=0,
        )
    ]
    vectors = [[0.1, 0.2]]
    vector_data = [
        {
            "id": "cv.pdf_chunk_0",
            "vector": [0.1, 0.2],
            "metadata": {"original_text": "chunk text"},
        }
    ]

    document_loader.load.return_value = ["page text"]
    chunker.chunk.return_value = chunks
    embedder.embed.return_value = vectors
    vector_data_processor.prepare.return_value = vector_data

    pipeline = IngestionPipeline(
        document_loader=document_loader,
        chunker=chunker,
        embedder=embedder,
        vector_data_processor=vector_data_processor,
        vector_store=vector_store,
    )

    pipeline.run("cv.pdf")

    document_loader.load.assert_called_once_with("cv.pdf")
    chunker.chunk.assert_called_once_with(
        pages=["page text"],
        source="cv.pdf",
    )
    embedder.embed.assert_called_once_with(chunks)
    vector_data_processor.prepare.assert_called_once_with(
        vectors=vectors,
        chunks=chunks,
    )
    vector_store.store_vectors.assert_called_once_with(vector_data)


def test_ingestion_pipeline_writes_bm25_corpus(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    chunks = [
        DocumentChunk(
            id="doc_chunk_0",
            text="lexical search corpus text",
            source="doc.pdf",
            chunk_index=0,
        )
    ]

    pipeline = IngestionPipeline(
        document_loader=Mock(load=Mock(return_value=["page"])),
        chunker=Mock(chunk=Mock(return_value=chunks)),
        embedder=Mock(embed=Mock(return_value=[[0.1]])),
        vector_data_processor=Mock(prepare=Mock(return_value=[])),
        vector_store=Mock(),
    )

    pipeline.run("doc.pdf")

    corpus_path = tmp_path / "storage" / "bm25_corpus.json"
    assert corpus_path.exists()
    assert "lexical search corpus text" in corpus_path.read_text()
