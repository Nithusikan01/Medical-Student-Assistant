import logging
import uuid
from pathlib import Path

import sqlalchemy as sa
from rag.ingestion.pipeline import IngestionPipeline
from rag.vectorstore.base import VectorStoreInterface
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import (
    STATUS_DELETING,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_READY,
    Document,
)
from backend.db.repositories import documents
from backend.services.postgres_chunk_sink import PostgresChunkSink

logger = logging.getLogger(__name__)


class DuplicateDocumentError(Exception):
    pass


class DocumentDeletionError(Exception):
    """Vectors could not be removed; the document is left mid-delete."""


class DocumentService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        pipeline: IngestionPipeline,
        vector_store: VectorStoreInterface,
        on_corpus_change,
    ) -> None:
        self._session_factory = session_factory
        self._pipeline = pipeline
        self._vector_store = vector_store
        # Called after any change to the set of documents that can be
        # retrieved. Rebuilds the lexical index and empties the response
        # cache - a callable rather than either of those, so this service
        # keeps knowing nothing about what is derived from the corpus.
        self._on_corpus_change = on_corpus_change

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest(
        self,
        *,
        file_path: Path,
        filename: str,
        content_hash: str,
        size_bytes: int,
        uploaded_by: uuid.UUID | None,
    ) -> Document:
        with self._session_factory() as session:
            existing = documents.find_ready_by_hash(session, content_hash)

            if existing is not None:
                raise DuplicateDocumentError(
                    f"'{existing.filename}' has already been ingested."
                )

            document_id = uuid.uuid4()

            # Recorded before ingestion starts so a crash leaves a visible,
            # deletable row rather than orphan vectors nobody can find.
            documents.create(
                session,
                document_id=document_id,
                filename=filename,
                status=STATUS_PROCESSING,
                content_hash=content_hash,
                size_bytes=size_bytes,
                uploaded_by=uploaded_by,
            )
            session.commit()

        sink = PostgresChunkSink(self._session_factory, document_id)

        try:
            summary = self._pipeline.ingest(
                file_path,
                document_id=str(document_id),
                chunk_sink=sink,
                # The file on disk is a generated temporary name; without
                # this every citation would show that instead of the real
                # document name.
                filename=filename,
            )
        except Exception as exc:
            with self._session_factory() as session:
                session.execute(
                    sa.update(Document)
                    .where(Document.id == document_id)
                    .values(status=STATUS_FAILED, error=str(exc)[:2000])
                )
                session.commit()

            logger.exception("Ingestion failed for '%s'.", filename)
            raise

        with self._session_factory() as session:
            session.execute(
                sa.update(Document)
                .where(Document.id == document_id)
                .values(
                    status=STATUS_READY,
                    error=None,
                    page_count=summary.get("pages"),
                    chunk_count=summary.get("chunks", 0),
                )
            )
            session.commit()

            document = documents.get(session, document_id)

        self._on_corpus_change()

        return document

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete(self, document_id: uuid.UUID) -> None:
        """
        Remove a document from both retrieval paths, then the registry.

        BM25 is refreshed before the vectors are removed so the document is
        never "delisted but still lexically retrievable"; the loader only
        includes ready documents, so flipping the status is enough. The
        response cache is emptied at the same point and for the same
        reason, and stays empty even if the vector delete below fails -
        the safe direction for a cache.
        """

        with self._session_factory() as session:
            document = documents.get(session, document_id)

            if document is None:
                return

            session.execute(
                sa.update(Document)
                .where(Document.id == document_id)
                .values(status=STATUS_DELETING)
            )
            session.commit()

            vector_ids = documents.chunk_ids(session, document_id)

        self._on_corpus_change()

        try:
            self._vector_store.delete(vector_ids)
        except Exception as exc:
            # The row stays in 'deleting' so an admin can retry the purge
            # rather than losing track of the orphaned vectors.
            logger.exception("Failed to delete vectors for document %s.", document_id)
            raise DocumentDeletionError(
                "The document's vectors could not be removed. "
                "It is marked for deletion and can be purged again."
            ) from exc

        with self._session_factory() as session:
            session.execute(sa.delete(Document).where(Document.id == document_id))
            session.commit()

    def purge(self, document_id: uuid.UUID) -> int:
        """
        Retry deletion and sweep up stray vectors sharing the id prefix.

        Prefix listing is eventually consistent, so it is only used here, as
        an admin-triggered reconciliation, never as the primary delete path.
        """

        with self._session_factory() as session:
            known = documents.chunk_ids(session, document_id)

        stray: list[str] = []

        try:
            stray = [
                vector_id
                for vector_id in self._vector_store.list_ids(f"{document_id}_chunk_")
                if vector_id not in set(known)
            ]
        except NotImplementedError:
            logger.info("Vector store cannot list ids; skipping the sweep.")

        self._vector_store.delete(known + stray)

        with self._session_factory() as session:
            session.execute(sa.delete(Document).where(Document.id == document_id))
            session.commit()

        self._on_corpus_change()

        return len(known) + len(stray)
