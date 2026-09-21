"""
The corpus, as opposed to the traffic against it.

Every other monitoring module summarises requests. A corpus problem never
shows up in those: it makes answers worse without making anything fail, so
it has to be reported directly or not at all.
"""

from datetime import UTC, datetime, timedelta

from backend.db.models import (
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_READY,
    Document,
    DocumentChunkRecord,
)
from backend.db.repositories import documents as document_repo
from backend.observability.knowledge_base import INGESTION_STAGES, build_report

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def add_document(
    db,
    *,
    status: str = STATUS_READY,
    chunks: int = 0,
    filename: str = "book.pdf",
    minutes_ago: float = 10.0,
    heartbeat_minutes_ago: float | None = None,
):
    import uuid

    document_id = uuid.uuid4()

    db.add(
        Document(
            id=document_id,
            filename=filename,
            status=status,
            created_at=NOW - timedelta(minutes=minutes_ago),
            updated_at=NOW - timedelta(minutes=minutes_ago),
            heartbeat_at=(
                None
                if heartbeat_minutes_ago is None
                else NOW - timedelta(minutes=heartbeat_minutes_ago)
            ),
        )
    )

    for index in range(chunks):
        db.add(
            DocumentChunkRecord(
                id=f"{document_id}_chunk_{index}",
                document_id=document_id,
                chunk_index=index,
                text=f"chunk {index}",
            )
        )

    db.commit()

    return document_id


# ----------------------------------------------------------------------
# The reads
# ----------------------------------------------------------------------


def test_documents_are_counted_by_status(db):
    add_document(db, status=STATUS_READY)
    add_document(db, status=STATUS_READY)
    add_document(db, status=STATUS_FAILED)

    assert document_repo.status_counts(db) == {STATUS_READY: 2, STATUS_FAILED: 1}


def test_stored_and_retrievable_chunks_are_counted_separately(db):
    """
    The gap between them is the stuck-ingestion shape: rows present,
    vectors live, invisible to lexical search.
    """

    add_document(db, status=STATUS_READY, chunks=4)
    add_document(db, status=STATUS_PROCESSING, chunks=3)

    assert document_repo.chunk_totals(db) == (7, 4)


def test_the_last_ingest_ignores_documents_that_never_finished(db):
    add_document(db, status=STATUS_READY, minutes_ago=90)
    add_document(db, status=STATUS_PROCESSING, minutes_ago=1)

    assert document_repo.last_ingested_at(db) == NOW - timedelta(minutes=90)


def test_no_ingest_yet_is_none_not_a_date(db):
    assert document_repo.last_ingested_at(db) is None


def test_stalled_documents_use_the_heartbeat(db):
    """
    Same rule as the recovery sweep, so the panel and the sweep can never
    disagree about what "stalled" means.
    """

    add_document(db, status=STATUS_PROCESSING, heartbeat_minutes_ago=1)
    add_document(db, status=STATUS_PROCESSING, heartbeat_minutes_ago=45)
    add_document(db, status=STATUS_PROCESSING, minutes_ago=4000)

    cutoff = NOW - timedelta(minutes=15)

    assert document_repo.count_processing_since(db, cutoff) == 2


# ----------------------------------------------------------------------
# The arithmetic
# ----------------------------------------------------------------------


def test_unreachable_chunks_are_the_difference():
    report = build_report(
        status_counts={STATUS_READY: 1, STATUS_PROCESSING: 1},
        chunks_stored=10,
        chunks_retrievable=6,
        last_ingested_at=NOW,
        stalled_documents=1,
    )

    assert report.chunks_unreachable == 4
    assert report.total_documents == 2
    assert report.ready_documents == 1
    assert report.healthy is False


def test_a_clean_corpus_is_healthy():
    report = build_report(
        status_counts={STATUS_READY: 3},
        chunks_stored=90,
        chunks_retrievable=90,
        last_ingested_at=NOW,
        stalled_documents=0,
    )

    assert report.chunks_unreachable == 0
    assert report.healthy is True


def test_a_negative_difference_is_clamped():
    """
    The two counts are separate queries. An ingest finishing between them
    should read as "nothing unreachable", never as a negative count.
    """

    report = build_report(
        status_counts={STATUS_READY: 1},
        chunks_stored=5,
        chunks_retrievable=7,
        last_ingested_at=None,
        stalled_documents=0,
    )

    assert report.chunks_unreachable == 0


def test_an_empty_corpus_reports_zero_rather_than_failing():
    report = build_report(
        status_counts={},
        chunks_stored=0,
        chunks_retrievable=0,
        last_ingested_at=None,
        stalled_documents=0,
    )

    assert report.total_documents == 0
    assert report.last_ingested_at is None
    assert report.healthy is True


def test_the_charted_stages_are_the_ones_the_pipeline_emits():
    """
    Guards the failure this phase existed to fix: stages declared and never
    emitted. If the pipeline stops emitting one of these, the panel would
    silently chart nothing.
    """

    from rag.observability import Stage

    declared = {
        Stage.INGESTION.value,
        Stage.DOCUMENT_LOAD.value,
        Stage.INGESTION_BATCH.value,
        Stage.DOCUMENT_EMBEDDING.value,
        Stage.VECTOR_UPSERT.value,
    }

    assert set(INGESTION_STAGES) == declared
