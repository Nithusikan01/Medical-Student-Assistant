import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"
STATUS_DELETING = "deleting"

DOCUMENT_STATUSES = (
    STATUS_PROCESSING,
    STATUS_READY,
    STATUS_FAILED,
    STATUS_DELETING,
)


class Document(Base):
    __tablename__ = "documents"

    # Matches LoadedDocument.document_id, so chunk ids stay derivable.
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True)

    filename: Mapped[str] = mapped_column(sa.String(512), nullable=False)

    content_hash: Mapped[str | None] = mapped_column(sa.String(64))

    status: Mapped[str] = mapped_column(
        sa.String(16),
        nullable=False,
        default=STATUS_PROCESSING,
        server_default=STATUS_PROCESSING,
    )

    error: Mapped[str | None] = mapped_column(sa.Text)

    page_count: Mapped[int | None] = mapped_column(sa.Integer)

    chunk_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    size_bytes: Mapped[int | None] = mapped_column(sa.BigInteger)

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid,
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    # Touched as each batch of chunks lands, so a stalled ingestion can be
    # told from a slow one.
    #
    # Without it there is no way to distinguish the two: `updated_at` is set
    # when the row changes, and ingestion writes to document_chunks rather
    # than to this table, so a healthy twenty-minute ingest and one that died
    # ten seconds in look identical.
    #
    # Null means no batch has landed yet - either the ingest is very young,
    # or it died before its first batch. The sweep falls back to created_at
    # for those.
    heartbeat_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    chunks: Mapped[list["DocumentChunkRecord"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('processing', 'ready', 'failed', 'deleting')",
            name="status_valid",
        ),
        sa.Index("ix_documents_status", "status"),
        # The stalled-ingestion sweep: processing rows, oldest heartbeat first.
        sa.Index("ix_documents_status_heartbeat_at", "status", "heartbeat_at"),
        # Partial, so a failed or deleted upload does not block re-uploading
        # the same file, while two live copies cannot coexist.
        sa.Index(
            "ux_documents_content_hash_ready",
            "content_hash",
            unique=True,
            postgresql_where=sa.text("status = 'ready'"),
            sqlite_where=sa.text("status = 'ready'"),
        ),
    )


class DocumentChunkRecord(Base):
    """
    One stored chunk.

    Named ...Record to stay distinct from the engine's DocumentChunk
    dataclass. This table is the authoritative list of Pinecone vector ids
    for a document, and the source text for the BM25 index.
    """

    __tablename__ = "document_chunks"

    # Exactly the Pinecone vector id: {document_id}_chunk_{index}.
    id: Mapped[str] = mapped_column(sa.String(320), primary_key=True)

    document_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    chunk_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    text: Mapped[str] = mapped_column(sa.Text, nullable=False)

    page_number: Mapped[int | None] = mapped_column(sa.Integer)
    section_title: Mapped[str | None] = mapped_column(sa.String(512))
    heading_level: Mapped[int | None] = mapped_column(sa.Integer)
    start_char: Mapped[int | None] = mapped_column(sa.Integer)
    end_char: Mapped[int | None] = mapped_column(sa.Integer)
    chunk_size: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    overlap_size: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    language: Mapped[str] = mapped_column(
        sa.String(16),
        nullable=False,
        default="en",
        server_default="en",
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")

    __table_args__ = (
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_id_chunk_index",
        ),
        sa.Index("ix_document_chunks_document_id", "document_id"),
    )
