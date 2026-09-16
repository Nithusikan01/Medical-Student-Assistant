"""
Small derivations used by instrumented stages.

Kept here rather than in the retrieval package because they exist purely to
describe a stage to telemetry - no retrieval decision is made from them.
"""

from collections.abc import Iterable, Sequence
from typing import Any


def summarize_scores(scores: Iterable[float]) -> dict[str, float]:
    """
    Top, mean and minimum of a stage's scores.

    Returns an empty dict for no scores, so a caller can splat it into
    `span.set(**summarize_scores(...))` and simply record nothing when a
    retriever came back empty - rather than storing three zeros that would
    later read as "scored zero" instead of "found nothing".
    """

    values = [float(score) for score in scores if score is not None]

    if not values:
        return {}

    return {
        "top_score": max(values),
        "average_score": sum(values) / len(values),
        "min_score": min(values),
    }


def rank_change(before: Sequence[str], after: Sequence[str]) -> dict[str, int]:
    """
    How much a reranking stage actually changed the selection.

    `introduced_count` is how many of the final chunks the previous stage
    would not have chosen at all; `reordered_count` is how many positions
    hold a different chunk than before. Together they answer the question
    reranking is supposed to justify - did it change anything? - without
    assuming the change was an improvement, which only an evaluation set
    can establish.
    """

    previous = list(before)
    current = list(after)
    previous_set = set(previous)

    return {
        "introduced_count": sum(1 for item in current if item not in previous_set),
        "reordered_count": sum(
            1
            for position, item in enumerate(current)
            if position >= len(previous) or previous[position] != item
        ),
    }


def generation_metadata(response: Any) -> dict[str, Any]:
    """
    Model, provider, attempt count, latency and tokens from an LLM response.

    Duck-typed rather than importing LLMResponse, so this package keeps no
    dependency on the llm package and any generator satisfying the
    TextGenerator protocol is describable.

    The provider latency and the attempt count were already being measured
    by both generators and then thrown away at the call site; this is where
    they finally reach storage. Note that provider_latency_ms covers every
    attempt including retries and their backoff, which is what makes it
    differ from the span's own duration.
    """

    metadata = getattr(response, "metadata", None) or {}
    usage = getattr(response, "usage", None)
    latency = getattr(response, "latency", None)

    fields: dict[str, Any] = {
        "model": getattr(response, "model", None),
        "provider": metadata.get("provider"),
        "attempts": metadata.get("attempt"),
    }

    if latency is not None:
        fields["provider_latency_ms"] = float(latency) * 1000.0

    if usage is not None:
        fields["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
        fields["completion_tokens"] = getattr(usage, "completion_tokens", None)
        fields["total_tokens"] = getattr(usage, "total_tokens", None)

    return {name: value for name, value in fields.items() if value is not None}
