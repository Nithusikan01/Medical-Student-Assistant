import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from api_app.db.models import (
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


def uploader_emails(
    session: Session,
    documents: list[Document],
) -> dict[uuid.UUID, str]:
    from api_app.db.models import User

    ids = {doc.uploaded_by for doc in documents if doc.uploaded_by}

    if not ids:
        return {}

    return {
        user_id: email
        for user_id, email in session.execute(
            sa.select(User.id, User.email).where(User.id.in_(ids))
        )
    }
