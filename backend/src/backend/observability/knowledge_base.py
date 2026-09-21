"""
The state of the corpus, as opposed to the traffic against it.

Every other monitoring module summarises requests. This one summarises
what there is to retrieve from, which is a different question and fails in
a different way: a corpus problem shows up as answers that are merely
worse, never as an error rate, so nothing else in this dashboard would
report it.

The number that matters most here is the gap between chunks stored and
chunks a lexical search can actually reach. The BM25 index is built from
`ready` documents only, so a document stuck in `processing` keeps its
rows and its vectors while dropping out of half of hybrid retrieval. That
is exactly the incident this application already had, and it was found by
inference from a retrieval metric rather than reported directly. Here it
is a subtraction.

Pure arithmetic, like aggregation.py: no session, no HTTP.
"""

from dataclasses import dataclass
from datetime import datetime

# Every stage the ingestion path emits. Kept here rather than imported from
# the engine's Stage enum so the monitoring layer names what it wants to
# chart, not everything the enum happens to contain.
INGESTION_STAGES = (
    "ingestion",
    "document_load",
    "ingestion_batch",
    "document_embedding",
    "vector_upsert",
)


@dataclass(frozen=True, slots=True)
class KnowledgeBaseReport:
    """What the corpus looks like right now."""

    documents_by_status: dict[str, int]
    total_documents: int
    ready_documents: int

    chunks_stored: int
    chunks_retrievable: int

    # Stored but not reachable by lexical search, because the document
    # they belong to is not ready. Zero is the healthy value.
    chunks_unreachable: int

    last_ingested_at: datetime | None
    stalled_documents: int

    @property
    def healthy(self) -> bool:
        return self.chunks_unreachable == 0 and self.stalled_documents == 0


def build_report(
    *,
    status_counts: dict[str, int],
    chunks_stored: int,
    chunks_retrievable: int,
    last_ingested_at: datetime | None,
    stalled_documents: int,
) -> KnowledgeBaseReport:
    return KnowledgeBaseReport(
        documents_by_status=dict(sorted(status_counts.items())),
        total_documents=sum(status_counts.values()),
        ready_documents=status_counts.get("ready", 0),
        chunks_stored=chunks_stored,
        chunks_retrievable=chunks_retrievable,
        # Clamped at zero rather than trusted to be non-negative: the two
        # counts are separate queries, and an ingest finishing between them
        # should read as "nothing unreachable", not as a negative count.
        chunks_unreachable=max(chunks_stored - chunks_retrievable, 0),
        last_ingested_at=last_ingested_at,
        stalled_documents=stalled_documents,
    )
