"""
Token accounting for every LLM call.

The bug these tests exist to prevent is the one they were written after: the
application recorded tokens for the final answer only, so the usage table -
and the admin dashboard on top of it - understated real spend by everything
query rewriting, summarisation and the rerank fallback consumed.
"""

import pytest

from rag.conversation.memory import ConversationMemory
from rag.conversation.query_rewriter import QueryRewriter
from rag.conversation.summarizer import ConversationSummarizer
from rag.llm.metering import (
    UNATTRIBUTED_STAGE,
    MeteredGenerator,
    collect_usage,
    current_collector,
)
from rag.llm.schemas import LLMResponse, TokenUsage
from rag.observability import Stage, Tracer


class StubGenerator:
    def __init__(self, text="answer", usage=None, provider="stub") -> None:
        self.text = text
        self.calls = 0
        self._usage = (
            usage
            if usage is not None
            else TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120)
        )
        self._provider = provider

    def generate(self, prompt: str) -> LLMResponse:
        self.calls += 1

        return LLMResponse(
            text=self.text,
            model="stub-model",
            metadata={"provider": self._provider, "attempt": 1},
            usage=self._usage,
        )


class UsagelessGenerator:
    """Some providers report no usage; that must not become a zero row."""

    def generate(self, prompt: str) -> LLMResponse:
        return LLMResponse(text="answer", model="stub-model")


class BrokenGenerator:
    def generate(self, prompt: str) -> LLMResponse:
        raise RuntimeError("provider is down")


# ----------------------------------------------------------------------
# The wrapper
# ----------------------------------------------------------------------


def test_a_metered_call_is_collected():
    generator = MeteredGenerator(StubGenerator())

    with collect_usage() as usage:
        response = generator.generate("hello")

    assert response.text == "answer"
    assert usage.total_tokens == 120
    assert usage.events[0].model == "stub-model"
    assert usage.events[0].provider == "stub"


def test_the_response_is_returned_unchanged():
    inner = StubGenerator(text="the real answer")

    with collect_usage():
        response = MeteredGenerator(inner).generate("hello")

    assert response.text == "the real answer"
    assert inner.calls == 1


def test_calls_outside_a_collector_still_work():
    """A script or a test has no collector; generation must not care."""

    response = MeteredGenerator(StubGenerator()).generate("hello")

    assert response.text == "answer"
    assert current_collector() is None


def test_a_provider_reporting_no_usage_records_nothing():
    """
    Absent usage is not zero usage - a zero row would claim the call was
    free, which is a different and wrong statement.
    """

    with collect_usage() as usage:
        MeteredGenerator(UsagelessGenerator()).generate("hello")

    assert usage.events == []


def test_a_generation_failure_propagates():
    with pytest.raises(RuntimeError), collect_usage():
        MeteredGenerator(BrokenGenerator()).generate("hello")


def test_the_wrapper_is_transparent_for_other_attributes():
    inner = StubGenerator()
    inner.model_name = "gemini-3.1-flash-lite"

    assert MeteredGenerator(inner).model_name == "gemini-3.1-flash-lite"


def test_collectors_do_not_leak_between_blocks():
    generator = MeteredGenerator(StubGenerator())

    with collect_usage() as first:
        generator.generate("one")

    with collect_usage() as second:
        generator.generate("two")

    assert first.total_tokens == 120
    assert second.total_tokens == 120
    assert current_collector() is None


# ----------------------------------------------------------------------
# Attribution
# ----------------------------------------------------------------------


def test_spend_is_attributed_to_the_open_stage():
    tracer = Tracer()
    generator = MeteredGenerator(StubGenerator())

    with collect_usage() as usage, tracer.trace():
        with tracer.span(Stage.QUERY_REWRITE):
            generator.generate("rewrite this")

        with tracer.span(Stage.GENERATION):
            generator.generate("answer this")

    assert usage.by_stage() == {"query_rewrite": 120, "generation": 120}


def test_attribution_does_not_depend_on_sampling():
    """
    The load-bearing property. Billing must not change because a request
    happened not to be sampled for telemetry.
    """

    tracer = Tracer(sample_rate=0.0)
    generator = MeteredGenerator(StubGenerator())

    with collect_usage() as usage, tracer.trace(), tracer.span(Stage.SUMMARIZATION):
        generator.generate("summarise")

    assert usage.by_stage() == {"summarization": 120}


def test_spend_outside_any_stage_is_recorded_as_unattributed():
    with collect_usage() as usage:
        MeteredGenerator(StubGenerator()).generate("hello")

    assert usage.by_stage() == {UNATTRIBUTED_STAGE: 120}


# ----------------------------------------------------------------------
# The call sites that were previously invisible
# ----------------------------------------------------------------------


def test_query_rewriting_is_counted():
    tracer = Tracer()
    rewriter = QueryRewriter(MeteredGenerator(StubGenerator()), tracer=tracer)

    with collect_usage() as usage, tracer.trace():
        rewriter.rewrite(query="and him?", summary="", recent_messages=[])

    assert usage.by_stage() == {"query_rewrite": 120}


def test_summarization_is_counted():
    tracer = Tracer()
    summarizer = ConversationSummarizer(
        MeteredGenerator(StubGenerator()),
        tracer=tracer,
    )

    with collect_usage() as usage, tracer.trace():
        summarizer.summarize(ConversationMemory())

    assert usage.by_stage() == {"summarization": 120}


def test_a_whole_request_counts_more_than_generation_alone():
    """
    The regression in one test: rewriting plus generating costs more than
    generating, and the total has to say so.
    """

    tracer = Tracer()
    generator = MeteredGenerator(StubGenerator())
    rewriter = QueryRewriter(generator, tracer=tracer)

    with collect_usage() as usage, tracer.trace():
        rewriter.rewrite(query="and him?", summary="", recent_messages=[])

        with tracer.span(Stage.GENERATION):
            generator.generate("answer")

    assert usage.total_tokens == 240
    assert len(usage.events) == 2
