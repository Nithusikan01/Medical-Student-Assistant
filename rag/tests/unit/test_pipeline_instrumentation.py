"""
The spans a real query produces.

This wires the actual pipeline - retrievers, fusion, reranker, query
service, rewriter, summariser and the RAG service - with only the external
calls stubbed, then asserts the shape and content of the resulting trace.
A unit test of each component in isolation would not catch the thing that
matters most here: that the spans nest correctly, which is what makes the
trace explorer readable.
"""

import pytest

from rag.conversation.memory import ConversationMemory
from rag.conversation.query_rewriter import QueryRewriter
from rag.conversation.summarizer import ConversationSummarizer
from rag.indexes.bm25_index import BM25Index
from rag.llm.schemas import LLMResponse, TokenUsage
from rag.observability import SpanRecord, SpanStatus, Tracer, TraceRecord
from rag.rerankers.base import BaseReranker
from rag.rerankers.fallback_reranker import FallbackReranker
from rag.retrieval.bm25_retriever import BM25Retriever
from rag.retrieval.dense_retriever import DenseRetriever
from rag.retrieval.hybrid_retriever import HybridRetriever
from rag.retrieval.query_service import QueryService
from rag.services.history_aware_rag_service import HistoryAwareRAGService
from tests.unit.helpers import make_chunk, make_search_result


class RecordingRecorder:
    def __init__(self) -> None:
        self.spans: list[SpanRecord] = []
        self.traces: list[TraceRecord] = []

    def record_span(self, span: SpanRecord) -> None:
        self.spans.append(span)

    def record_trace(self, trace: TraceRecord) -> None:
        self.traces.append(trace)

    def by_stage(self) -> dict[str, SpanRecord]:
        return {span.stage: span for span in self.spans}


# ----------------------------------------------------------------------
# Stubs for everything that would otherwise be a network call
# ----------------------------------------------------------------------


class StubEmbedder:
    model_name = "stub-embed-v1"

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]


class StubVectorStore:
    def __init__(self, results=None) -> None:
        self.results = results

    def query(self, embedding, top_k=5, filters=None):
        if self.results is not None:
            return self.results

        return [
            make_search_result(chunk_id="doc_chunk_0", score=0.95),
            make_search_result(chunk_id="doc_chunk_1", score=0.80),
            make_search_result(chunk_id="doc_chunk_2", score=0.65),
        ]


class StubGenerator:
    """Reports usage, latency and an attempt count, as both real ones do."""

    def __init__(self, text: str = "Generated answer") -> None:
        self.text = text

    def generate(self, prompt: str) -> LLMResponse:
        return LLMResponse(
            text=self.text,
            model="stub-model",
            latency=0.25,
            metadata={"provider": "stub", "attempt": 2},
            usage=TokenUsage(
                prompt_tokens=120,
                completion_tokens=30,
                total_tokens=150,
            ),
        )


class ReversingReranker(BaseReranker):
    """Deterministically changes the order, so rank change is observable."""

    def rerank(self, query, candidates, top_k=5):
        reversed_candidates = list(reversed(candidates))[:top_k]

        return [
            chunk.with_rerank_score(score=1.0 - (rank * 0.1), rank=rank)
            for rank, chunk in enumerate(reversed_candidates, start=1)
        ]


class BrokenReranker(BaseReranker):
    def rerank(self, query, candidates, top_k=5):
        raise RuntimeError("reranker is unavailable")


class StubSessionManager:
    def __init__(self, memory: ConversationMemory) -> None:
        self.memory = memory

    def get_memory(self, conversation_id: str) -> ConversationMemory:
        return self.memory


# ----------------------------------------------------------------------
# Assembly
# ----------------------------------------------------------------------


REWRITTEN_QUERY = "paracetamol dose adults"


def build_service(
    tracer: Tracer,
    *,
    reranker: BaseReranker | None = None,
    vector_results=None,
    bm25_documents=None,
) -> HistoryAwareRAGService:
    generator = StubGenerator()

    # A separate stub for rewriting: retrieval runs on the rewritten query,
    # so if this echoed the answer text the BM25 half of the pipeline would
    # match nothing and the fusion numbers would be meaningless.
    rewrite_generator = StubGenerator(text=REWRITTEN_QUERY)

    dense_retriever = DenseRetriever(
        vector_store=StubVectorStore(vector_results),
        embedding_model=StubEmbedder(),
        tracer=tracer,
    )

    if bm25_documents is None:
        # Two documents match the rewritten query and overlap the dense
        # results on doc_chunk_0 only, so the fusion span has something
        # non-trivial to report.
        #
        # The three that match nothing are not padding: BM25 IDF collapses
        # to zero for a term present in every document, and the index drops
        # non-positive scores - so a corpus where everything matches
        # returns nothing at all.
        bm25_documents = [
            make_chunk(index=0, text="paracetamol dose for adults"),
            make_chunk(index=7, text="paracetamol contraindications in pregnancy"),
            make_chunk(index=1, text="ibuprofen dosing guidance"),
            make_chunk(index=2, text="amoxicillin course length"),
            make_chunk(index=3, text="warfarin monitoring schedule"),
        ]

    bm25_retriever = BM25Retriever(
        bm25_index=BM25Index(documents=bm25_documents),
        tracer=tracer,
    )

    query_service = QueryService(
        retriever=HybridRetriever(
            dense_retriever=dense_retriever,
            bm25_retriever=bm25_retriever,
            tracer=tracer,
        ),
        reranker=reranker if reranker is not None else ReversingReranker(),
        tracer=tracer,
    )

    return HistoryAwareRAGService(
        query_service=query_service,
        generator=generator,
        session_manager=StubSessionManager(ConversationMemory()),
        query_rewriter=QueryRewriter(rewrite_generator, tracer=tracer),
        summarizer=ConversationSummarizer(generator, tracer=tracer),
        tracer=tracer,
    )


@pytest.fixture
def recorder() -> RecordingRecorder:
    return RecordingRecorder()


@pytest.fixture
def tracer(recorder: RecordingRecorder) -> Tracer:
    return Tracer(recorder)


def answer_once(service: HistoryAwareRAGService, tracer: Tracer, question="dose?"):
    with tracer.trace():
        return service.answer_with_sources(
            conversation_id="conversation-1",
            question=question,
        )


# ----------------------------------------------------------------------
# The shape of a trace
# ----------------------------------------------------------------------


def test_a_query_emits_every_stage_that_ran(tracer, recorder):
    answer_once(build_service(tracer), tracer)

    assert {span.stage for span in recorder.spans} == {
        "memory_load",
        "memory_write",
        "query_rewrite",
        "retrieval",
        "query_embedding",
        "dense_retrieval",
        "bm25_retrieval",
        "fusion",
        "reranking",
        "context_build",
        "generation",
    }


def test_retrieval_stages_nest_under_the_retrieval_span(tracer, recorder):
    answer_once(build_service(tracer), tracer)

    stages = recorder.by_stage()

    retrieval = stages["retrieval"]

    # Top-level stages hang off the trace, not off each other.
    assert retrieval.parent_span_id is None
    assert stages["query_rewrite"].parent_span_id is None
    assert stages["generation"].parent_span_id is None

    assert stages["dense_retrieval"].parent_span_id == retrieval.span_id
    assert stages["bm25_retrieval"].parent_span_id == retrieval.span_id
    assert stages["fusion"].parent_span_id == retrieval.span_id
    assert stages["reranking"].parent_span_id == retrieval.span_id

    # Embedding the query is part of dense retrieval, so it nests inside it.
    assert stages["query_embedding"].parent_span_id == stages["dense_retrieval"].span_id


def test_every_span_belongs_to_the_one_trace(tracer, recorder):
    answer_once(build_service(tracer), tracer)

    assert len({span.trace_id for span in recorder.spans}) == 1
    assert recorder.spans[0].trace_id == recorder.traces[0].trace_id


# ----------------------------------------------------------------------
# What each stage records
# ----------------------------------------------------------------------


def test_dense_retrieval_records_counts_and_scores(tracer, recorder):
    answer_once(build_service(tracer), tracer)

    dense = recorder.by_stage()["dense_retrieval"].metadata

    assert dense["result_count"] == 3
    assert dense["top_score"] == pytest.approx(0.95)
    assert dense["min_score"] == pytest.approx(0.65)
    assert dense["average_score"] == pytest.approx(0.80)


def test_query_embedding_records_the_model_and_dimension(tracer, recorder):
    answer_once(build_service(tracer), tracer)

    embedding = recorder.by_stage()["query_embedding"].metadata

    assert embedding["model"] == "stub-embed-v1"
    assert embedding["dimension"] == 4


def test_bm25_records_the_corpus_it_searched(tracer, recorder):
    answer_once(build_service(tracer), tracer, question="paracetamol")

    bm25 = recorder.by_stage()["bm25_retrieval"].metadata

    assert bm25["corpus_size"] == 5


def test_fusion_records_the_overlap_between_retrievers(tracer, recorder):
    answer_once(build_service(tracer), tracer, question="paracetamol")

    fusion = recorder.by_stage()["fusion"].metadata

    assert fusion["method"] == "rrf"
    assert fusion["dense_count"] == 3
    assert fusion["bm25_count"] == 2

    # doc_chunk_0 is in both; the rest belong to one side or the other.
    assert fusion["overlap_count"] == 1
    assert fusion["dense_only_count"] == 2
    assert fusion["bm25_only_count"] == 1
    assert fusion["unique_count"] == 4


def test_reranking_records_that_it_changed_the_selection(tracer, recorder):
    answer_once(build_service(tracer), tracer)

    reranking = recorder.by_stage()["reranking"].metadata

    assert reranking["reranker"] == "ReversingReranker"
    assert reranking["candidate_count"] >= reranking["final_count"]

    # The stub reverses the order, so every position holds a different chunk.
    assert reranking["reordered_count"] > 0
    assert reranking["top_score"] == pytest.approx(0.9)


def test_context_build_records_the_funnel(tracer, recorder):
    answer_once(build_service(tracer), tracer)

    context = recorder.by_stage()["context_build"].metadata

    assert context["chunk_count"] > 0
    assert context["context_chars"] > 0
    assert context["document_count"] >= 1

    # The prompt is the context plus instructions, summary and history.
    assert context["prompt_chars"] > context["context_chars"]


def test_generation_records_tokens_latency_and_attempts(tracer, recorder):
    answer_once(build_service(tracer), tracer)

    generation = recorder.by_stage()["generation"].metadata

    assert generation["model"] == "stub-model"
    assert generation["provider"] == "stub"
    assert generation["prompt_tokens"] == 120
    assert generation["completion_tokens"] == 30
    assert generation["total_tokens"] == 150
    assert generation["answer_chars"] == len("Generated answer")

    # Both were already measured by the generators and previously discarded.
    assert generation["attempts"] == 2
    assert generation["provider_latency_ms"] == pytest.approx(250.0)


def test_query_rewrite_records_whether_it_changed_the_query(tracer, recorder):
    answer_once(build_service(tracer), tracer, question="dose?")

    rewrite = recorder.by_stage()["query_rewrite"].metadata

    assert rewrite["original_length"] == len("dose?")
    assert rewrite["rewritten_length"] == len(REWRITTEN_QUERY)
    assert rewrite["changed"] is True

    # Rewriting spends tokens that the usage table still does not count.
    assert rewrite["total_tokens"] == 150


def test_memory_writes_are_labelled_by_role(tracer, recorder):
    answer_once(build_service(tracer), tracer)

    roles = [
        span.metadata.get("role")
        for span in recorder.spans
        if span.stage == "memory_write"
    ]

    assert roles == ["user", "assistant"]


# ----------------------------------------------------------------------
# Degradation the audit found was invisible
# ----------------------------------------------------------------------


def test_a_reranker_falling_back_is_recorded(tracer, recorder):
    service = build_service(
        tracer,
        reranker=FallbackReranker(
            primary=BrokenReranker(),
            fallback=ReversingReranker(),
            tracer=tracer,
        ),
    )

    answer_once(service, tracer)

    reranking = recorder.by_stage()["reranking"].metadata

    assert reranking["primary_reranker_failed"] is True
    assert reranking["reranker_used"] == "ReversingReranker"
    assert reranking["reranker_degraded"] is True


def test_reranking_giving_up_entirely_is_recorded(tracer, recorder):
    service = build_service(
        tracer,
        reranker=FallbackReranker(
            primary=BrokenReranker(),
            fallback=BrokenReranker(),
            tracer=tracer,
        ),
    )

    answer, chunks = answer_once(service, tracer)

    reranking = recorder.by_stage()["reranking"].metadata

    # Retrieval order was used; the answer still came back.
    assert reranking["reranker_used"] == "none"
    assert reranking["reranker_degraded"] is True
    assert answer == "Generated answer"
    assert chunks


def test_no_retrieval_results_means_no_generation_span(tracer, recorder):
    service = build_service(tracer, vector_results=[], bm25_documents=[])

    answer, chunks = answer_once(service, tracer)

    stages = {span.stage for span in recorder.spans}

    assert "generation" not in stages
    assert "context_build" not in stages
    assert chunks == []
    assert "couldn't find relevant information" in answer


def test_a_failing_stage_marks_only_its_own_span(tracer, recorder):
    service = build_service(tracer)
    service.generator = StubGenerator(text="")

    with pytest.raises(ValueError):
        answer_once(service, tracer)

    stages = recorder.by_stage()

    assert stages["generation"].status is SpanStatus.ERROR
    assert stages["generation"].error_type == "ValueError"

    # Stages that completed before it are untouched.
    assert stages["retrieval"].status is SpanStatus.OK
    assert stages["context_build"].status is SpanStatus.OK


# ----------------------------------------------------------------------
# Regression: the engine still works with no telemetry at all
# ----------------------------------------------------------------------


def test_the_pipeline_runs_untraced(recorder):
    """
    No trace open means no spans - a script or unit test exercising the
    same code path produces no telemetry, and costs nothing for it.
    """

    tracer = Tracer(recorder)

    service = build_service(tracer)

    answer, chunks = service.answer_with_sources(
        conversation_id="conversation-1",
        question="dose?",
    )

    assert answer == "Generated answer"
    assert chunks
    assert recorder.spans == []
    assert recorder.traces == []


def test_components_built_without_a_tracer_still_work():
    """Every tracer argument is keyword-only and defaulted."""

    dense = DenseRetriever(
        vector_store=StubVectorStore(),
        embedding_model=StubEmbedder(),
    )

    assert len(dense.retrieve("dose?", top_k=3)) == 3
