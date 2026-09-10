import json
from unittest.mock import Mock

from rag_application.ingestion.pipeline import IngestionPipeline
from tests.unit.helpers import (
    make_chunk,
    make_embedded_chunk,
    make_loaded_document,
    make_vector_record,
)


def test_ingestion_pipeline_runs_all_steps(tmp_path):
    document = make_loaded_document()
    chunks = [make_chunk(0, "chunk text")]
    embedded_chunks = [make_embedded_chunk(0, "chunk text")]
    vector_records = [make_vector_record()]

    loader = Mock()
    chunker = Mock()
    embedder = Mock()
    processor = Mock()
    vector_store = Mock()

    loader.load.return_value = document
    chunker.chunk_batches.return_value = [chunks]
    embedder.embed_batch.return_value = embedded_chunks
    processor.prepare.return_value = vector_records

    pipeline = IngestionPipeline(
        loader=loader,
        chunker=chunker,
        embedder=embedder,
        processor=processor,
        vector_store=vector_store,
        batch_size=32,
        bm25_corpus_path=tmp_path / "bm25_corpus.json",
    )

    summary = pipeline.ingest("cv.pdf")

    loader.load.assert_called_once_with("cv.pdf", document_id=None, filename=None)
    chunker.chunk_batches.assert_called_once_with(
        document=document,
        batch_size=32,
    )
    embedder.embed_batch.assert_called_once_with(chunks)
    processor.prepare.assert_called_once_with(embedded_chunks)
    vector_store.upsert.assert_called_once_with(vector_records)
    assert summary == {
        "document_id": "doc",
        "filename": "doc.pdf",
        "pages": 1,
        "chunks": 1,
        "vectors": 1,
    }


def test_ingestion_pipeline_writes_bm25_corpus(tmp_path):
    chunks = [
        make_chunk(0, "lexical search corpus text"),
    ]
    pipeline = IngestionPipeline(
        loader=Mock(load=Mock(return_value=make_loaded_document())),
        chunker=Mock(chunk_batches=Mock(return_value=[chunks])),
        embedder=Mock(embed_batch=Mock(return_value=[])),
        processor=Mock(prepare=Mock(return_value=[])),
        vector_store=Mock(upsert=Mock(return_value=0)),
        batch_size=5,
        bm25_corpus_path=tmp_path / "storage" / "bm25_corpus.json",
    )

    pipeline.ingest("doc.pdf")

    corpus_path = tmp_path / "storage" / "bm25_corpus.json"
    rows = json.loads(corpus_path.read_text(encoding="utf-8"))
    assert rows[0]["text"] == "lexical search corpus text"
    assert rows[0]["metadata"]["filename"] == "doc.pdf"
