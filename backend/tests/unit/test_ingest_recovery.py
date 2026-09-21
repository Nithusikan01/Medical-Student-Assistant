"""
Recovering documents whose ingestion stopped without saying so.

The bug these tests exist to prevent is one that actually happened: the
host killed uvicorn partway through an upload, nothing raised, and the
document sat in `processing` for good - its chunks invisible to the
lexical index, its vectors live in Pinecone, and no error anywhere.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from backend.db.models import (
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_READY,
    Document,
    DocumentChunkRecord,
)
from backend.services.ingest_recovery import (
    DEFAULT_STALL_MINUTES,
    STALL_MESSAGE,
    reconcile_stalled_ingestions,
    recover_on_startup,
    stall_threshold,
)
from backend.services.postgres_chunk_sink import PostgresChunkSink

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def add_document(
    db,
    *,
    status: str = STATUS_PROCESSING,
    created_minutes_ago: float = 60.0,
    heartbeat_minutes_ago: float | None = None,
    filename: str = "book.pdf",
) -> uuid.UUID:
    document_id = uuid.uuid4()

    db.add(
        Document(
            id=document_id,
            filename=filename,
            status=status,
            created_at=NOW - timedelta(minutes=created_minutes_ago),
            updated_at=NOW - timedelta(minutes=created_minutes_ago),
            heartbeat_at=(
                None
                if heartbeat_minutes_ago is None
                else NOW - timedelta(minutes=heartbeat_minutes_ago)
            ),
        )
    )
    db.commit()

    return document_id


# ----------------------------------------------------------------------
# What gets reconciled
# ----------------------------------------------------------------------


def test_a_document_left_mid_ingestion_is_failed(db, session_factory):
    """The exact shape of the real incident: old row, no heartbeat."""

    document_id = add_document(db, created_minutes_ago=4000)

    recovered = reconcile_stalled_ingestions(session_factory, now=NOW)

    assert recovered == [document_id]

    db.expire_all()
    document = db.get(Document, document_id)

    assert document.status == STATUS_FAILED
    assert "restarted mid-upload" in document.error


def test_a_stale_heartbeat_is_reconciled(db, session_factory):
    document_id = add_document(
        db,
        created_minutes_ago=90,
        heartbeat_minutes_ago=45,
    )

    assert reconcile_stalled_ingestions(session_factory, now=NOW) == [document_id]


# ----------------------------------------------------------------------
# What must be left alone
# ----------------------------------------------------------------------


def test_an_ingestion_still_beating_is_left_alone(db, session_factory):
    """
    The property that makes this safe to run while another task is mid
    upload: a live ingest has a recent heartbeat, however long it has been
    running overall.
    """

    add_document(db, created_minutes_ago=240, heartbeat_minutes_ago=1)

    assert reconcile_stalled_ingestions(session_factory, now=NOW) == []


def test_a_young_ingestion_is_left_alone(db, session_factory):
    """No batch has landed yet, but the upload only just started."""

    add_document(db, created_minutes_ago=2)

    assert reconcile_stalled_ingestions(session_factory, now=NOW) == []


@pytest.mark.parametrize("status", [STATUS_READY, STATUS_FAILED, "deleting"])
def test_only_processing_documents_are_touched(db, session_factory, status):
    add_document(db, status=status, created_minutes_ago=4000)

    assert reconcile_stalled_ingestions(session_factory, now=NOW) == []


def test_nothing_to_do_is_not_an_error(db, session_factory):
    assert reconcile_stalled_ingestions(session_factory, now=NOW) == []


# ----------------------------------------------------------------------
# What it deliberately does not do
# ----------------------------------------------------------------------


def test_partial_chunks_are_left_in_place(db, session_factory):
    """
    Marked failed, not repaired, and not cleaned up either.

    The chunk rows are partial by definition - ingestion writes them batch
    by batch - so promoting them to `ready` would ship an incomplete corpus
    that nothing downstream could detect. Deleting them here would also
    take the decision away from the admin, who may want to inspect first;
    the existing delete path already removes them.
    """

    document_id = add_document(db, created_minutes_ago=4000)

    db.add(
        DocumentChunkRecord(
            id=f"{document_id}_chunk_0",
            document_id=document_id,
            chunk_index=0,
            text="a partially ingested chunk",
        )
    )
    db.commit()

    reconcile_stalled_ingestions(session_factory, now=NOW)

    db.expire_all()

    assert db.get(Document, document_id).status == STATUS_FAILED
    assert db.get(DocumentChunkRecord, f"{document_id}_chunk_0") is not None


def test_a_reconciled_document_is_not_lexically_retrievable(db, session_factory):
    """
    The consequence that made this bug invisible, pinned in a test: the
    lexical index is built from `ready` documents only, so a stuck one was
    silently absent from half of hybrid retrieval.
    """

    from backend.wiring.bm25_loader import load_bm25_documents

    document_id = add_document(db, created_minutes_ago=4000)

    db.add(
        DocumentChunkRecord(
            id=f"{document_id}_chunk_0",
            document_id=document_id,
            chunk_index=0,
            text="paracetamol dosing",
        )
    )
    db.commit()

    # Stuck in processing: invisible before reconciliation too. Failing it
    # does not change retrieval - it makes the state honest so an admin can
    # act on it.
    assert load_bm25_documents(session_factory) == []

    reconcile_stalled_ingestions(session_factory, now=NOW)

    assert load_bm25_documents(session_factory) == []


# ----------------------------------------------------------------------
# The heartbeat itself
# ----------------------------------------------------------------------


def test_writing_a_batch_beats(db, session_factory):
    from rag.ingestion.schemas import ChunkMetadata, DocumentChunk

    document_id = add_document(db, created_minutes_ago=5)

    assert db.get(Document, document_id).heartbeat_at is None

    sink = PostgresChunkSink(session_factory, document_id)

    with sink:
        sink.add_batch(
            [
                DocumentChunk(
                    id=f"{document_id}_chunk_0",
                    chunk_index=0,
                    text="a chunk",
                    metadata=ChunkMetadata(
                        document_id=str(document_id),
                        filename="book.pdf",
                        source_path="",
                        chunk_size=7,
                    ),
                )
            ]
        )

    db.expire_all()

    assert db.get(Document, document_id).heartbeat_at is not None


def test_an_empty_batch_does_not_beat(db, session_factory):
    """A batch with nothing in it is not a sign of progress."""

    document_id = add_document(db, created_minutes_ago=5)

    sink = PostgresChunkSink(session_factory, document_id)
    sink.add_batch([])

    db.expire_all()

    assert db.get(Document, document_id).heartbeat_at is None


# ----------------------------------------------------------------------
# Configuration and guarding
# ----------------------------------------------------------------------


def test_the_threshold_is_configurable(monkeypatch):
    monkeypatch.setenv("INGEST_STALL_MINUTES", "45")

    assert stall_threshold() == timedelta(minutes=45)


def test_an_unparseable_threshold_falls_back(monkeypatch):
    monkeypatch.setenv("INGEST_STALL_MINUTES", "soon")

    assert stall_threshold() == timedelta(minutes=DEFAULT_STALL_MINUTES)


def test_startup_recovery_never_stops_the_application():
    """
    The same rule the telemetry layer follows: a problem reconciling old
    rows must not prevent the application starting.
    """

    def broken_session_factory():
        raise RuntimeError("database is gone")

    recover_on_startup(broken_session_factory)


def test_the_stall_message_tells_an_admin_what_to_do():
    assert "upload it again" in STALL_MESSAGE
