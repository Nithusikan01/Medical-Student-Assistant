"""
Spans on the ingestion path.

Until now the Stage enum declared INGESTION, INGESTION_BATCH,
DOCUMENT_EMBEDDING and VECTOR_UPSERT and nothing emitted any of them - the
enum promised coverage the pipeline did not have. These tests hold the
pipeline to what the enum claims.

The motivating incident: a process killed mid-ingest left a document stuck
in `processing` with no error anywhere, and it was found by inference from
a retrieval metric. A span per batch reports it directly.
"""

from pathlib import Path

import pytest

from rag.ingestion.pipeline import IngestionPipeline
from rag.ingestion.schemas import (
    ChunkMetadata,
    DocumentChunk,
    LoadedDocument,
    LoadedPage,
)
from rag.observability import SpanRecord, Stage, Tracer, TraceRecord


class RecordingRecorder:
    """Keeps what a real recorder would persist."""

    def __init__(self) -> None:
        self.spans: list[SpanRecord] = []
        self.traces: list[TraceRecord] = []

    def record_span(self, span: SpanRecord) -> None:
        self.spans.append(span)

    def record_trace(self, trace: TraceRecord) -> None:
        self.traces.append(trace)

    def stages(self) -> list[str]:
        return [span.stage for span in self.spans]

    def of_stage(self, stage: Stage) -> list[SpanRecord]:
        return [span for span in self.spans if span.stage == stage.value]


class StubLoader:
    def __init__(self, pages: int = 2) -> None:
        self.pages = pages

    def load(self, path, document_id=None, filename=None) -> LoadedDocument:
        return LoadedDocument(
            document_id=document_id or "doc",
            filename=filename or "book.pdf",
            source_path=str(path),
            pages=[
                LoadedPage(page_number=index + 1, text=f"page {index + 1}")
                for index in range(self.pages)
            ],
        )


class StubChunker:
    """Yields fixed batches, the way the real chunker yields lazily."""

    def __init__(self, batches: list[int]) -> None:
        self.batches = batches

    def chunk_batches(self, document, batch_size):
        index = 0

        for size in self.batches:
            batch = []

            for _ in range(size):
                batch.append(
                    DocumentChunk(
                        id=f"{document.document_id}_chunk_{index}",
                        chunk_index=index,
                        text=f"chunk {index}",
                        metadata=ChunkMetadata(
                            document_id=document.document_id,
                            filename=document.filename,
                            source_path=document.source_path,
                            chunk_size=8,
                        ),
                    )
                )
                index += 1

            yield batch


class StubEmbedder:
    def embed_batch(self, chunks):
        return list(chunks)


class StubProcessor:
    def prepare(self, embedded):
        return list(embedded)


class StubVectorStore:
    def __init__(self) -> None:
        self.upserts: list[int] = []

    def upsert(self, records) -> None:
        self.upserts.append(len(records))


class ExplodingVectorStore(StubVectorStore):
    def upsert(self, records) -> None:
        raise RuntimeError("pinecone is unreachable")


def build_pipeline(
    *,
    tracer: Tracer | None = None,
    batches: list[int] | None = None,
    vector_store=None,
    pages: int = 2,
) -> IngestionPipeline:
    return IngestionPipeline(
        loader=StubLoader(pages=pages),
        chunker=StubChunker(batches if batches is not None else [2, 1]),
        embedder=StubEmbedder(),
        processor=StubProcessor(),
        vector_store=vector_store or StubVectorStore(),
        batch_size=2,
        tracer=tracer,
    )


@pytest.fixture
def recorder() -> RecordingRecorder:
    return RecordingRecorder()


@pytest.fixture
def tracer(recorder: RecordingRecorder) -> Tracer:
    return Tracer(recorder)


# ----------------------------------------------------------------------
# What gets emitted
# ----------------------------------------------------------------------


def test_every_declared_ingestion_stage_is_emitted(tracer, recorder):
    with tracer.trace():
        build_pipeline(tracer=tracer).ingest(Path("book.pdf"))

    emitted = set(recorder.stages())

    assert {
        Stage.INGESTION.value,
        Stage.DOCUMENT_LOAD.value,
        Stage.INGESTION_BATCH.value,
        Stage.DOCUMENT_EMBEDDING.value,
        Stage.VECTOR_UPSERT.value,
    } <= emitted


def test_one_batch_span_per_batch(tracer, recorder):
    with tracer.trace():
        build_pipeline(tracer=tracer, batches=[2, 2, 1]).ingest(Path("book.pdf"))

    batches = recorder.of_stage(Stage.INGESTION_BATCH)

    assert [span.metadata["batch"] for span in batches] == [1, 2, 3]
    assert [span.metadata["chunks"] for span in batches] == [2, 2, 1]


def test_the_ingestion_span_carries_the_totals(tracer, recorder):
    with tracer.trace():
        build_pipeline(tracer=tracer, batches=[2, 1], pages=4).ingest(Path("book.pdf"))

    (ingestion,) = recorder.of_stage(Stage.INGESTION)

    assert ingestion.metadata == {
        "pages": 4,
        "chunks": 3,
        "vectors": 3,
        "batches": 2,
    }


def test_the_load_span_reports_pages(tracer, recorder):
    with tracer.trace():
        build_pipeline(tracer=tracer, pages=7).ingest(Path("book.pdf"))

    (load,) = recorder.of_stage(Stage.DOCUMENT_LOAD)

    assert load.metadata["pages"] == 7


def test_batch_spans_nest_under_the_ingestion_span(tracer, recorder):
    with tracer.trace():
        build_pipeline(tracer=tracer, batches=[1]).ingest(Path("book.pdf"))

    (ingestion,) = recorder.of_stage(Stage.INGESTION)
    (batch,) = recorder.of_stage(Stage.INGESTION_BATCH)
    (embedding,) = recorder.of_stage(Stage.DOCUMENT_EMBEDDING)

    assert batch.parent_span_id == ingestion.span_id
    assert embedding.parent_span_id == batch.span_id


def test_spans_are_ordered_by_sequence_not_by_clock(tracer, recorder):
    """
    The waterfall ordering key. Stub work finishes far inside a clock tick,
    so timestamps tie here exactly as they do in production.
    """

    with tracer.trace():
        build_pipeline(tracer=tracer, batches=[1, 1]).ingest(Path("book.pdf"))

    sequences = [span.sequence for span in recorder.spans]

    # Unique, so a waterfall can order by it at all.
    assert len(set(sequences)) == len(sequences)

    # Spans are recorded as they close, so the outermost is recorded last
    # while holding the lowest sequence - which is the whole reason the
    # column exists.
    (ingestion,) = recorder.of_stage(Stage.INGESTION)

    assert ingestion.sequence == min(sequences)
    assert recorder.spans[-1] is ingestion


# ----------------------------------------------------------------------
# Failure
# ----------------------------------------------------------------------


def test_a_failing_upsert_marks_its_span_and_its_parents(tracer, recorder):
    with tracer.trace(), pytest.raises(RuntimeError):
        build_pipeline(
            tracer=tracer,
            batches=[1],
            vector_store=ExplodingVectorStore(),
        ).ingest(Path("book.pdf"))

    failed = {span.stage for span in recorder.spans if span.status.value == "error"}

    assert failed == {
        Stage.VECTOR_UPSERT.value,
        Stage.INGESTION_BATCH.value,
        Stage.INGESTION.value,
    }


def test_a_failing_upsert_records_the_error_type_not_the_message(tracer, recorder):
    """
    A provider exception can carry an API key in its message; the type
    cannot.
    """

    with tracer.trace(), pytest.raises(RuntimeError):
        build_pipeline(
            tracer=tracer,
            batches=[1],
            vector_store=ExplodingVectorStore(),
        ).ingest(Path("book.pdf"))

    (upsert,) = recorder.of_stage(Stage.VECTOR_UPSERT)

    assert upsert.error_type == "RuntimeError"
    assert "pinecone is unreachable" not in str(upsert.metadata)


# ----------------------------------------------------------------------
# The no-telemetry contract
# ----------------------------------------------------------------------


def test_the_pipeline_runs_with_no_tracer_at_all():
    """
    `rag` has to stay usable with no telemetry backend - the same contract
    the query service follows.
    """

    store = StubVectorStore()

    summary = build_pipeline(vector_store=store).ingest(Path("book.pdf"))

    assert summary["chunks"] == 3
    assert store.upserts == [2, 1]


def test_nothing_is_recorded_outside_a_trace(tracer, recorder):
    """A script or a unit test exercising ingestion emits no telemetry."""

    build_pipeline(tracer=tracer).ingest(Path("book.pdf"))

    assert recorder.spans == []


def test_a_document_with_no_extractable_text_reports_zero_batches(tracer, recorder):
    """
    A scanned PDF yields no chunks at all. The ingestion span still has to
    say so rather than fail on an unbound loop variable.
    """

    with tracer.trace():
        summary = build_pipeline(tracer=tracer, batches=[]).ingest(Path("book.pdf"))

    (ingestion,) = recorder.of_stage(Stage.INGESTION)

    assert summary["chunks"] == 0
    assert ingestion.metadata["batches"] == 0
