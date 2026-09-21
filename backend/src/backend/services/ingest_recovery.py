"""
Recovering documents whose ingestion stopped without saying so.

DocumentService marks a document `failed` when ingestion raises. That
covers every failure the process survives - a bad PDF, a Pinecone outage,
a dropped connection - and none of the failures where the process itself
goes away.

A killed process raises nothing. The `documents` row is created as
`processing` before ingestion starts, deliberately, so a crash leaves a
visible row rather than orphan vectors; but nothing ever moved it on. The
row stayed `processing` for good, and because the lexical index is built
only from `ready` documents, its chunks became permanently invisible to
BM25 while its vectors stayed live in Pinecone. Hybrid retrieval quietly
degraded to dense-only, with no error anywhere to say so.

That is not hypothetical: it is how a real document ended up stuck, after
the host killed uvicorn for memory partway through an upload. On ECS the
same thing happens on any task restart during an upload.

The sweep runs at startup, which is exactly when the replacement process
for a killed one comes up.

Documents are marked `failed`, not repaired. Their chunk rows are partial
by definition - ingestion writes them batch by batch - and silently
promoting a partial corpus to `ready` would be a worse outcome than an
honest failure, because nothing downstream could tell it was incomplete.
An admin can then delete and re-upload, which is the existing path for a
failed ingest.
"""

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import STATUS_FAILED, STATUS_PROCESSING, Document

logger = logging.getLogger(__name__)

# Generous on purpose. The cost of waiting is a row that reads "processing"
# for a while longer; the cost of being hasty is failing an ingest that was
# still working, which on a long textbook is a real possibility. The
# heartbeat is what lets this be minutes rather than hours.
DEFAULT_STALL_MINUTES = 15

STALL_MESSAGE = (
    "Ingestion stopped unexpectedly and did not finish. The server was most "
    "likely restarted mid-upload. Delete this document and upload it again."
)


def stall_threshold() -> timedelta:
    raw = os.getenv("INGEST_STALL_MINUTES")

    if raw is None:
        return timedelta(minutes=DEFAULT_STALL_MINUTES)

    try:
        return timedelta(minutes=max(int(raw), 1))
    except ValueError:
        logger.warning(
            "INGEST_STALL_MINUTES is not an integer; using %d.",
            DEFAULT_STALL_MINUTES,
        )
        return timedelta(minutes=DEFAULT_STALL_MINUTES)


def reconcile_stalled_ingestions(
    session_factory: sessionmaker[Session],
    *,
    threshold: timedelta | None = None,
    now: datetime | None = None,
) -> list[uuid.UUID]:
    """
    Mark long-silent `processing` documents as failed.

    Returns the ids it changed, so a caller can log or report them.

    Staleness is measured from the last batch to land, falling back to when
    the row was created for a document that never got that far. A document
    actively being ingested has a recent heartbeat and is left alone, which
    is what makes this safe to run while another task is mid-upload.
    """

    moment = now or datetime.now(UTC)
    cutoff = moment - (threshold or stall_threshold())

    with session_factory() as session:
        stalled = list(
            session.scalars(
                sa.select(Document).where(
                    sa.and_(
                        Document.status == STATUS_PROCESSING,
                        sa.func.coalesce(
                            Document.heartbeat_at,
                            Document.created_at,
                        )
                        < cutoff,
                    )
                )
            ).all()
        )

        if not stalled:
            return []

        for document in stalled:
            document.status = STATUS_FAILED
            document.error = STALL_MESSAGE

            logger.warning(
                "Document '%s' (%s) was left mid-ingestion and has been "
                "marked failed.",
                document.filename,
                document.id,
            )

        session.commit()

        return [document.id for document in stalled]


def recover_on_startup(session_factory: sessionmaker[Session]) -> None:
    """
    Guarded wrapper for the lifespan.

    A problem reconciling old rows must not stop the application starting -
    the same rule the telemetry layer follows.
    """

    try:
        recovered = reconcile_stalled_ingestions(session_factory)

        if recovered:
            logger.warning(
                "Marked %d stalled ingestion(s) as failed on startup.",
                len(recovered),
            )
    except Exception:
        logger.exception("Could not reconcile stalled ingestions.")
