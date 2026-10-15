from unittest.mock import Mock

import pytest

from rag.config.component_configs import GenerationConfig
from rag.llm import generator as gemini_module
from rag.llm.generator import GeminiGenerator
from rag.llm.retry import MAX_RETRY_DELAY_SECONDS, EmptyResponseError, retry_delay
from rag.observability import ErrorCategory, classify, is_transient
from rag.utils.exceptions import VectorStoreError


class ProviderError(Exception):
    def __init__(self, status_code, retry_after=None):
        super().__init__(f"status {status_code} for key sk-secret")
        self.status_code = status_code
        if retry_after is not None:
            self.retry_after = retry_after


def wrapped(error: Exception) -> Exception:
    try:
        raise VectorStoreError("Failed to query Pinecone.") from error
    except VectorStoreError as outer:
        return outer


def test_classification_sees_through_an_engine_wrapper():
    """
    Every provider failure is re-raised as an engine exception so its
    message never reaches a response; classifying only the wrapper filed
    every one of them as internal.
    """

    assert classify(wrapped(ProviderError(429))) is ErrorCategory.RATE_LIMIT
    assert classify(wrapped(TimeoutError())) is ErrorCategory.TIMEOUT
    assert classify(VectorStoreError("no cause")) is ErrorCategory.INTERNAL


def test_only_failures_a_retry_can_fix_are_transient():
    assert is_transient(ProviderError(503))
    assert is_transient(ProviderError(429))
    assert not is_transient(ProviderError(401))
    assert not is_transient(ProviderError(400))
    assert not is_transient(ValueError("bug"))


def test_retry_delay_honours_retry_after_but_caps_it():
    assert retry_delay(ProviderError(429, retry_after=3), 1, 1.0) == 3.0
    assert retry_delay(ProviderError(429, retry_after=600), 1, 1.0) == (
        MAX_RETRY_DELAY_SECONDS
    )
    assert retry_delay(ProviderError(503), 3, 1.0) == 4.0


def build_gemini(side_effect, monkeypatch):
    monkeypatch.setattr(gemini_module.time, "sleep", Mock())
    client = Mock()
    client.models.generate_content.side_effect = side_effect

    return (
        GeminiGenerator(
            GenerationConfig(api_key="k", model_name="m"),
            client=client,
            max_retries=2,
        ),
        client,
    )


def ok(text="answer"):
    return Mock(text=text, usage_metadata=None)


def test_an_auth_failure_is_not_retried(monkeypatch):
    generator, client = build_gemini([ProviderError(401)], monkeypatch)

    with pytest.raises(RuntimeError) as raised:
        generator.generate("p")

    assert client.models.generate_content.call_count == 1
    assert classify(raised.value) is ErrorCategory.AUTH


def test_a_rate_limit_is_retried_and_can_recover(monkeypatch):
    generator, client = build_gemini([ProviderError(429), ok()], monkeypatch)

    assert generator.generate("p").text == "answer"
    assert client.models.generate_content.call_count == 2


def test_an_empty_completion_is_retried(monkeypatch):
    generator, _ = build_gemini([ok(text=""), ok()], monkeypatch)

    assert generator.generate("p").metadata["attempt"] == 2


def test_the_retry_log_line_carries_no_provider_message(monkeypatch, caplog):
    generator, _ = build_gemini([ProviderError(401)], monkeypatch)

    with pytest.raises(RuntimeError):
        generator.generate("p")

    assert "sk-secret" not in caplog.text


def test_pinecone_query_retries_transient_failures_only(monkeypatch):
    from rag.vectorstore import pinecone_store
    from rag.vectorstore.pinecone_store import PineconeVectorStore

    monkeypatch.setattr(pinecone_store.time, "sleep", Mock())

    store = PineconeVectorStore.__new__(PineconeVectorStore)
    store.index = Mock()
    store.index.query.side_effect = [TimeoutError(), Mock(matches=[])]

    assert store.query([0.1], top_k=1) == []
    assert store.index.query.call_count == 2

    store.index = Mock()
    store.index.query.side_effect = [ProviderError(400)]

    with pytest.raises(VectorStoreError):
        store.query([0.1], top_k=1)

    assert store.index.query.call_count == 1


def test_empty_response_error_is_a_runtime_error():
    # Callers that caught RuntimeError for an empty completion still do.
    assert issubclass(EmptyResponseError, RuntimeError)
