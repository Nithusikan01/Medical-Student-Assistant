import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from backend.db.models import (
    STATUS_PROCESSING,
    STATUS_READY,
    Document,
    DocumentChunkRecord,
)


def get(session: Session, document_id: uuid.UUID) -> Document | None:
    return session.get(Document, document_id)


def list_all(session: Session) -> list[Document]:
    return list(
        session.scalars(sa.select(Document).order_by(Document.created_at.desc()))
    )


def find_ready_by_hash(
    session: Session,
    content_hash: str,
) -> Document | None:
    return session.scalar(
        sa.select(Document).where(
            Document.content_hash == content_hash,
            Document.status == STATUS_READY,
        )
    )


def create(
    session: Session,
    *,
    document_id: uuid.UUID,
    filename: str,
    status: str,
    content_hash: str | None = None,
    size_bytes: int | None = None,
    uploaded_by: uuid.UUID | None = None,
) -> Document:
    document = Document(
        id=document_id,
        filename=filename,
        status=status,
        content_hash=content_hash,
        size_bytes=size_bytes,
        uploaded_by=uploaded_by,
    )

    session.add(document)
    session.flush()

    return document


def chunk_ids(session: Session, document_id: uuid.UUID) -> list[str]:
    """
    The authoritative list of Pinecone vector ids for a document.
    """

    return list(
        session.scalars(
            sa.select(DocumentChunkRecord.id)
            .where(DocumentChunkRecord.document_id == document_id)
            .order_by(DocumentChunkRecord.chunk_index)
        )
    )


# ----------------------------------------------------------------------
# Knowledge-base state, for the monitoring API
# ----------------------------------------------------------------------


def status_counts(session: Session) -> dict[str, int]:
    """How many documents sit in each lifecycle state."""

    return {
        status: int(count)
        for status, count in session.execute(
            sa.select(Document.status, sa.func.count()).group_by(Document.status)
        )
    }


def chunk_totals(session: Session) -> tuple[int, int]:
    """
    (chunks stored, chunks a lexical search can actually reach).

    The two differ whenever a document is not `ready`, because the BM25
    loader selects on that status. The gap is the exact shape of the stuck
    ingestion incident - rows present, vectors live, lexically invisible -
    so it is worth reporting as a number rather than leaving to be
    inferred.
    """

    stored = int(
        session.scalar(sa.select(sa.func.count()).select_from(DocumentChunkRecord)) or 0
    )

    retrievable = int(
        session.scalar(
            sa.select(sa.func.count())
            .select_from(DocumentChunkRecord)
            .join(Document, Document.id == DocumentChunkRecord.document_id)
            .where(Document.status == STATUS_READY)
        )
        or 0
    )

    return stored, retrievable


def last_ingested_at(session: Session):
    """When the most recent document became ready, or None if none has."""

    return session.scalar(
        sa.select(sa.func.max(Document.updated_at)).where(
            Document.status == STATUS_READY
        )
    )


def count_processing_since(session: Session, cutoff) -> int:
    """
    Documents that have been ingesting, silently, since before `cutoff`.

    Measured from the ingestion heartbeat, falling back to creation for a
    document that never got a batch written - the same rule the recovery
    sweep uses, so the panel and the sweep never disagree.
    """

    return int(
        session.scalar(
            sa.select(sa.func.count())
            .select_from(Document)
            .where(
                sa.and_(
                    Document.status == STATUS_PROCESSING,
                    sa.func.coalesce(Document.heartbeat_at, Document.created_at)
                    < cutoff,
                )
            )
        )
        or 0
    )


def uploader_emails(
    session: Session,
    documents: list[Document],
) -> dict[uuid.UUID, str]:
    from backend.db.models import User

    ids = {doc.uploaded_by for doc in documents if doc.uploaded_by}

    if not ids:
        return {}

    return {
        user_id: email
        for user_id, email in session.execute(
            sa.select(User.id, User.email).where(User.id.in_(ids))
        )
    }
