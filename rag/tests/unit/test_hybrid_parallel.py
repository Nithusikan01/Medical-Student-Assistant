import threading

import pytest

from rag.observability import Stage, Tracer
from rag.retrieval.hybrid_retriever import HybridRetriever
from tests.unit.helpers import make_retrieved_chunk
from tests.unit.test_observability import RecordingRecorder


class GatedRetriever:
    """Waits for the other retriever to start, so it only finishes if both overlap."""

    def __init__(self, started: threading.Event, wait_for: threading.Event, ids):
        self.started = started
        self.wait_for = wait_for
        self.ids = ids
        self.thread: str | None = None

    def retrieve(self, query, top_k=None):
        self.thread = threading.current_thread().name
        self.started.set()

        if not self.wait_for.wait(timeout=5):
            raise TimeoutError("the other retriever never started")

        return [make_retrieved_chunk(chunk_id=i, text=i) for i in self.ids]


def test_dense_and_bm25_run_at_the_same_time():
    dense_started, bm25_started = threading.Event(), threading.Event()
    dense = GatedRetriever(dense_started, bm25_started, ["d1"])
    bm25 = GatedRetriever(bm25_started, dense_started, ["b1"])

    results = HybridRetriever(dense, bm25).retrieve("q", top_k=5)

    assert {chunk.id for chunk in results} == {"d1", "b1"}
    assert dense.thread != bm25.thread


class ExplodingRetriever:
    def retrieve(self, query, top_k=None):
        raise RuntimeError("pinecone is down")


class StaticRetriever:
    def __init__(self, ids):
        self.ids = ids

    def retrieve(self, query, top_k=None):
        return [make_retrieved_chunk(chunk_id=i, text=i) for i in self.ids]


def test_a_dense_failure_still_reaches_the_caller():
    retriever = HybridRetriever(ExplodingRetriever(), StaticRetriever(["b1"]))

    with pytest.raises(RuntimeError, match="pinecone is down"):
        retriever.retrieve("q", top_k=5)


def test_sequential_mode_gives_the_same_fusion():
    dense, bm25 = StaticRetriever(["a", "b"]), StaticRetriever(["b", "c"])

    parallel = HybridRetriever(dense, bm25).retrieve("q", top_k=5)
    sequential = HybridRetriever(dense, bm25, parallel=False).retrieve("q", top_k=5)

    assert [c.id for c in parallel] == [c.id for c in sequential]


class SpanningRetriever(StaticRetriever):
    def __init__(self, ids, tracer, stage):
        super().__init__(ids)
        self.tracer = tracer
        self.stage = stage

    def retrieve(self, query, top_k=None):
        with self.tracer.span(self.stage):
            return super().retrieve(query, top_k)


def test_worker_thread_spans_nest_under_the_caller_span():
    recorder = RecordingRecorder()
    tracer = Tracer(recorder)

    retriever = HybridRetriever(
        SpanningRetriever(["a"], tracer, Stage.DENSE_RETRIEVAL),
        SpanningRetriever(["b"], tracer, Stage.BM25_RETRIEVAL),
        tracer=tracer,
    )

    with tracer.trace(), tracer.span(Stage.RETRIEVAL):
        retriever.retrieve("q", top_k=5)

    spans = {span.stage: span for span in recorder.spans}

    assert len({span.trace_id for span in recorder.spans}) == 1
    assert spans["dense_retrieval"].parent_span_id == spans["retrieval"].span_id
    assert spans["bm25_retrieval"].parent_span_id == spans["retrieval"].span_id
