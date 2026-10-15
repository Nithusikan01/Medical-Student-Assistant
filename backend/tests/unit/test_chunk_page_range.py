"""
A chunk's page range and offsets survive the database round trip.

Chunks are cut from a document's whole text, so one can start on one page
and end on the next. The BM25 corpus is rebuilt from document_chunks, so
anything the sink does not store, lexical retrieval cannot cite.
"""

import uuid

from rag.ingestion.schemas import ChunkMetadata, DocumentChunk

from backend.db.models import STATUS_READY, Document, DocumentChunkRecord
from backend.services.postgres_chunk_sink import PostgresChunkSink
from backend.wiring.bm25_loader import load_bm25_documents


def test_page_range_and_offsets_are_stored_and_reloaded(db, session_factory):
    document_id = uuid.uuid4()
    db.add(Document(id=document_id, filename="notes.pdf", status=STATUS_READY))
    db.commit()

    chunk = DocumentChunk(
        id=f"{document_id}_chunk_0",
        chunk_index=0,
        text="dysregulated host\nresponse to infection",
        metadata=ChunkMetadata(
            document_id=str(document_id),
            filename="notes.pdf",
            source_path="/srv/uploads/x.pdf",
            page_number=4,
            end_page_number=5,
            start_char=120,
            end_char=159,
            chunk_size=39,
            overlap_size=50,
        ),
    )

    with PostgresChunkSink(session_factory, document_id) as sink:
        sink.add_batch([chunk])

    (loaded,) = load_bm25_documents(session_factory)

    assert loaded.metadata.page_number == 4
    assert loaded.metadata.end_page_number == 5
    assert (loaded.metadata.start_char, loaded.metadata.end_char) == (120, 159)


def test_chunks_from_before_the_page_range_load_with_none(db, session_factory):
    document_id = uuid.uuid4()
    db.add(Document(id=document_id, filename="old.pdf", status=STATUS_READY))
    db.add(
        DocumentChunkRecord(
            id=f"{document_id}_chunk_0",
            document_id=document_id,
            chunk_index=0,
            text="ingested before chunks could span pages",
            page_number=7,
        )
    )
    db.commit()

    (loaded,) = load_bm25_documents(session_factory)

    assert loaded.metadata.page_number == 7
    assert loaded.metadata.end_page_number is None
