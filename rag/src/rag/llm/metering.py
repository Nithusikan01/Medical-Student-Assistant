"""
Token accounting for every LLM call a request makes.

The application already recorded tokens for the final answer. It did not
record the other three call sites - query rewriting, which fires on every
question; conversation summarisation; and the Gemini reranker that stands in
when hosted reranking fails - so the usage table, and the admin dashboard
built on it, understated real spend. A measured example: 1291 tokens
recorded against 1441 actually spent, a 10% shortfall from rewriting alone.

The fix is a wrapper rather than a callback threaded through each component.
`MeteredGenerator` satisfies the same `TextGenerator` protocol as the thing
it wraps, so wrapping once at the composition root meters every caller -
including ones added later - with no signature changes to QueryRewriter,
ConversationSummarizer or GeminiReranker, and no chance of a new call site
being forgotten.

Attribution comes from the ambient stage bound by `Tracer.span`, which is
set whether or not the trace is being recorded. That matters: what a request
costs must not depend on whether it happened to be sampled.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from rag.llm.protocol import TextGenerator
from rag.llm.schemas import LLMResponse, TokenUsage
from rag.observability.context import current_stage

logger = logging.getLogger(__name__)

# Used when a generation happens outside any instrumented stage - a script,
# a test, or a call site that has not been given a span. Recorded rather than
# dropped, because unattributed spend is still spend.
UNATTRIBUTED_STAGE = "unattributed"


@dataclass(frozen=True, slots=True)
class UsageEvent:
    """One LLM call's token spend, attributed to the stage that made it."""

    stage: str
    usage: TokenUsage

    model: str | None = None
    provider: str | None = None


class UsageCollector:
    """
    Gathers the usage events of one request.

    Deliberately not thread-safe and not shared: one collector belongs to one
    request, and the contextvar keeps it there.
    """

    __slots__ = ("events",)

    def __init__(self) -> None:
        self.events: list[UsageEvent] = []

    def record(self, event: UsageEvent) -> None:
        self.events.append(event)

    @property
    def total_tokens(self) -> int:
        return sum(event.usage.total_tokens for event in self.events)

    def by_stage(self) -> dict[str, int]:
        totals: dict[str, int] = {}

        for event in self.events:
            totals[event.stage] = totals.get(event.stage, 0) + event.usage.total_tokens

        return totals


_current_collector: ContextVar[UsageCollector | None] = ContextVar(
    "rag_usage_collector",
    default=None,
)


def current_collector() -> UsageCollector | None:
    return _current_collector.get()


@contextmanager
def collect_usage() -> Iterator[UsageCollector]:
    """
    Collect every LLM call made inside this block.

    The caller decides what to do with the result - this package has no
    storage of its own, the same way the RAG service does not.
    """

    collector = UsageCollector()
    token = _current_collector.set(collector)

    try:
        yield collector
    finally:
        _current_collector.reset(token)


class MeteredGenerator:
    """
    A TextGenerator that reports what each call spent.

    Satisfies the protocol structurally, so it can stand in anywhere a
    generator is expected.
    """

    def __init__(self, generator: TextGenerator) -> None:
        self._generator = generator

    def __getattr__(self, name: str):
        # Transparent for anything the wrapper does not define, so callers
        # that reach for an attribute of the underlying client still work.
        return getattr(self._generator, name)

    def generate(self, prompt: str) -> LLMResponse:
        response = self._generator.generate(prompt)

        self._meter(response)

        return response

    def _meter(self, response: LLMResponse) -> None:
        """
        Never allowed to fail the generation that produced it: an accounting
        problem must not cost the user their answer.
        """

        try:
            collector = current_collector()

            if collector is None or response.usage is None:
                return

            metadata = response.metadata or {}

            collector.record(
                UsageEvent(
                    stage=current_stage() or UNATTRIBUTED_STAGE,
                    usage=response.usage,
                    model=response.model,
                    provider=metadata.get("provider"),
                )
            )
        except Exception:
            logger.exception("Failed to meter an LLM call.")
