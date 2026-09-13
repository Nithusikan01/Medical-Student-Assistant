"""
Document lifecycle.

Deletion has to satisfy an ordering constraint that is invisible from the
outside: lexical retrieval must stop seeing the document *before* its vectors
are removed, so a document is never "delisted but still retrievable". The
tests below record the order the collaborators are called in, because that
order is the actual contract.
"""

import uuid

import pytest
import sqlalchemy as sa

from backend.db.models import (
    STATUS_DELETING,
    STATUS_FAILED,
    STATUS_READY,
    Document,
    DocumentChunkRecord,
)
from backend.services.document_service import (
    DocumentDeletionError,
    DocumentService,
    DuplicateDocumentError,
)


class RecordingVectorStore:
    """Records calls against a shared log so ordering can be asserted."""

    def __init__(self, log: list[str], *, ids: list[str] | None = None) -> None:
        self._log = log
        self.deleted: list[str] = []
        self.listed: list[str] = ids or []
        self.delete_error: Exception | None = None
        self.supports_listing = True

    def delete(self, ids):
        self._log.append("delete_vectors")

        if self.delete_error is not None:
            raise self.delete_error

        self.deleted.extend(ids)

    def list_ids(self, prefix):
        if not self.supports_listing:
            raise NotImplementedError

        return [i for i in self.listed if i.startswith(prefix)]


class RecordingPipeline:
    def __init__(self, summary=None, error: Exception | None = None) -> None:
        self.summary = summary or {"pages": 3, "chunks": 7}
        self.error = error
        self.calls: list[dict] = []

    def ingest(self, file_path, *, document_id, chunk_sink, filename):
        self.calls.append(
            {
                "file_path": file_path,
                "document_id": document_id,
                "filename": filename,
            }
        )

        if self.error is not None:
            raise self.error

        return self.summary


@pytest.fixture
def call_log() -> list[str]:
    return []


@pytest.fixture
def vector_store(call_log) -> RecordingVectorStore:
    return RecordingVectorStore(call_log)


@pytest.fixture
def pipeline() -> RecordingPipeline:
    return RecordingPipeline()


@pytest.fixture
def service(session_factory, pipeline, vector_store, call_log) -> DocumentService:
    def refresh():
        call_log.append("refresh_bm25")

    return DocumentService(
        session_factory=session_factory,
        pipeline=pipeline,
        vector_store=vector_store,
        refresh_lexical_index=refresh,
    )


@pytest.fixture
def stored_document(session_factory):
    def _store(*, status=STATUS_READY, chunks=3, content_hash="hash-1"):
        document_id = uuid.uuid4()

        with session_factory() as session:
            session.add(
                Document(
                    id=document_id,
                    filename="pharmacology.pdf",
                    status=status,
                    content_hash=content_hash,
                )
            )
            session.add_all(
                DocumentChunkRecord(
                    id=f"{document_id}_chunk_{index}",
                    document_id=document_id,
                    chunk_index=index,
                    text=f"chunk {index}",
                )
                for index in range(chunks)
            )
            session.commit()

        return document_id

    return _store


# ----------------------------------------------------------------------
# Deletion
# ----------------------------------------------------------------------


def test_delete_refreshes_lexical_retrieval_before_removing_vectors(
    service, stored_document, call_log
):
    service.delete(stored_document())

    assert call_log == ["refresh_bm25", "delete_vectors"], (
        "removing vectors first would leave a window where the document is "
        "still lexically retrievable but its text is gone"
    )


def test_delete_removes_exactly_the_documents_vectors(
    service, stored_document, vector_store, db
):
    document_id = stored_document(chunks=3)
    other_id = stored_document(chunks=2, content_hash="hash-2")

    service.delete(document_id)

    assert sorted(vector_store.deleted) == sorted(
        f"{document_id}_chunk_{i}" for i in range(3)
    )
    assert db.get(Document, other_id) is not None


def test_delete_removes_the_registry_row_and_cascades_its_chunks(
    service, stored_document, db
):
    document_id = stored_document()

    service.delete(document_id)

    db.expire_all()

    assert db.get(Document, document_id) is None
    assert (
        db.scalars(
            sa.select(DocumentChunkRecord).where(
                DocumentChunkRecord.document_id == document_id
            )
        ).all()
        == []
    )


def test_delete_marks_the_document_before_touching_the_vector_store(
    session_factory, stored_document, pipeline, call_log
):
    """
    The status flip has to be committed first: if the vector delete fails,
    the row must already show that a deletion is in progress.
    """

    document_id = stored_document()
    seen_status: list[str] = []

    class StatusProbingStore(RecordingVectorStore):
        def delete(self, ids):
            with session_factory() as session:
                seen_status.append(session.get(Document, document_id).status)

            return super().delete(ids)

    service = DocumentService(
        session_factory=session_factory,
        pipeline=pipeline,
        vector_store=StatusProbingStore(call_log),
        refresh_lexical_index=lambda: call_log.append("refresh_bm25"),
    )

    service.delete(document_id)

    assert seen_status == [STATUS_DELETING]


def test_a_failed_vector_delete_leaves_the_document_recoverable(
    service, stored_document, vector_store, db
):
    document_id = stored_document()
    vector_store.delete_error = RuntimeError("pinecone is down")

    with pytest.raises(DocumentDeletionError):
        service.delete(document_id)

    db.expire_all()
    document = db.get(Document, document_id)

    assert document is not None, "the row must survive so an admin can retry"
    assert document.status == STATUS_DELETING


def test_the_deletion_error_does_not_leak_the_underlying_message(
    service, stored_document, vector_store
):
    vector_store.delete_error = RuntimeError("pinecone rejected key pcsk_secret_value")

    with pytest.raises(DocumentDeletionError) as raised:
        service.delete(stored_document())

    assert "pcsk_secret_value" not in str(raised.value)


def test_deleting_an_unknown_document_is_a_no_op(service, call_log):
    assert service.delete(uuid.uuid4()) is None
    assert call_log == []


# ----------------------------------------------------------------------
# Purge
# ----------------------------------------------------------------------


def test_purge_sweeps_up_vectors_the_registry_does_not_know_about(
    session_factory, stored_document, pipeline, call_log
):
    """
    A crash mid-ingest can leave vectors in Pinecone with no matching chunk
    row. Purge is the admin-triggered reconciliation for exactly that.
    """

    document_id = stored_document(chunks=2)

    store = RecordingVectorStore(
        call_log,
        ids=[
            f"{document_id}_chunk_0",
            f"{document_id}_chunk_1",
            f"{document_id}_chunk_9",  # orphan
            "some-other-document_chunk_0",
        ],
    )

    service = DocumentService(
        session_factory=session_factory,
        pipeline=pipeline,
        vector_store=store,
        refresh_lexical_index=lambda: call_log.append("refresh_bm25"),
    )

    removed = service.purge(document_id)

    assert removed == 3
    assert f"{document_id}_chunk_9" in store.deleted
    assert "some-other-document_chunk_0" not in store.deleted


def test_purge_still_works_when_the_store_cannot_list(
    session_factory, stored_document, pipeline, vector_store, call_log, db
):
    document_id = stored_document(chunks=2)
    vector_store.supports_listing = False

    service = DocumentService(
        session_factory=session_factory,
        pipeline=pipeline,
        vector_store=vector_store,
        refresh_lexical_index=lambda: call_log.append("refresh_bm25"),
    )

    assert service.purge(document_id) == 2

    db.expire_all()

    assert db.get(Document, document_id) is None


# ----------------------------------------------------------------------
# Ingestion
# ----------------------------------------------------------------------


def test_ingest_records_the_document_and_marks_it_ready(
    service, session_factory, tmp_path, admin, db
):
    path = tmp_path / "upload.pdf"
    path.write_bytes(b"%PDF-1.4")

    document = service.ingest(
        file_path=path,
        filename="Pharmacology Notes.pdf",
        content_hash="hash-xyz",
        size_bytes=8,
        uploaded_by=admin.id,
    )

    assert document.status == STATUS_READY
    assert document.filename == "Pharmacology Notes.pdf"
    assert document.page_count == 3
    assert document.chunk_count == 7
    assert document.uploaded_by == admin.id


def test_ingest_passes_the_real_filename_not_the_temp_path(
    service, pipeline, tmp_path, admin
):
    """
    Uploads are saved under a generated name; without threading the real
    filename through, every citation would read like '9b0f2c....pdf'.
    """

    path = tmp_path / "9b0f2c4a-temp.pdf"
    path.write_bytes(b"%PDF-1.4")

    service.ingest(
        file_path=path,
        filename="Pharmacology Notes.pdf",
        content_hash="hash-xyz",
        size_bytes=8,
        uploaded_by=admin.id,
    )

    assert pipeline.calls[0]["filename"] == "Pharmacology Notes.pdf"


def test_ingesting_the_same_content_twice_is_refused(
    service, stored_document, tmp_path, admin
):
    stored_document(status=STATUS_READY, content_hash="hash-dupe")

    path = tmp_path / "upload.pdf"
    path.write_bytes(b"%PDF-1.4")

    with pytest.raises(DuplicateDocumentError):
        service.ingest(
            file_path=path,
            filename="again.pdf",
            content_hash="hash-dupe",
            size_bytes=8,
            uploaded_by=admin.id,
        )


def test_the_same_content_may_be_re_uploaded_after_a_failure(
    service, stored_document, tmp_path, admin
):
    """
    The duplicate guard only looks at ready documents, so a failed upload
    does not permanently block the file.
    """

    stored_document(status=STATUS_FAILED, content_hash="hash-retry")

    path = tmp_path / "upload.pdf"
    path.write_bytes(b"%PDF-1.4")

    assert service.ingest(
        file_path=path,
        filename="retry.pdf",
        content_hash="hash-retry",
        size_bytes=8,
        uploaded_by=admin.id,
    )


def test_a_failed_ingestion_leaves_a_visible_failed_row(
    session_factory, vector_store, tmp_path, admin, db, call_log
):
    """
    Recorded before ingestion starts so a crash leaves a deletable row
    rather than orphan vectors nobody can find.
    """

    service = DocumentService(
        session_factory=session_factory,
        pipeline=RecordingPipeline(error=RuntimeError("pdf is corrupt")),
        vector_store=vector_store,
        refresh_lexical_index=lambda: call_log.append("refresh_bm25"),
    )

    path = tmp_path / "upload.pdf"
    path.write_bytes(b"not really a pdf")

    with pytest.raises(RuntimeError):
        service.ingest(
            file_path=path,
            filename="broken.pdf",
            content_hash="hash-broken",
            size_bytes=16,
            uploaded_by=admin.id,
        )

    db.expire_all()
    document = db.scalar(sa.select(Document))

    assert document.status == STATUS_FAILED
    assert "pdf is corrupt" in document.error


def test_ingest_refreshes_lexical_retrieval_once_ready(
    service, tmp_path, admin, call_log
):
    path = tmp_path / "upload.pdf"
    path.write_bytes(b"%PDF-1.4")

    service.ingest(
        file_path=path,
        filename="notes.pdf",
        content_hash="hash-new",
        size_bytes=8,
        uploaded_by=admin.id,
    )

    assert call_log == ["refresh_bm25"]
