import logging
from unittest.mock import Mock

from google import genai
from google.genai.models import Models

from rag.config.component_configs import GenerationConfig
from rag.llm.generator import GeminiGenerator
from rag.llm.schemas import LLMResponse


def test_generate_success():
    config = GenerationConfig(
        api_key="test",
        model_name="gemini-test",
    )
    mock_client = Mock()
    mock_response = Mock()
    mock_response.text = "Hello AI"
    mock_response.usage_metadata = None
    mock_client.models.generate_content.return_value = mock_response

    generator = GeminiGenerator(
        config=config,
        client=mock_client,
        max_retries=1,
    )

    result = generator.generate("test prompt")

    assert isinstance(result, LLMResponse)
    assert result.text == "Hello AI"
    assert result.usage is None
    mock_client.models.generate_content.assert_called_once()
    kwargs = mock_client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-test"
    assert kwargs["contents"] == "test prompt"
    assert kwargs["config"].automatic_function_calling.disable is True


def test_generate_skips_the_sdk_afc_loop_and_its_warning(monkeypatch, caplog):
    # Runs the real SDK client, stopping only at the network call, so this
    # fails if a future google-genai release stops honouring `disable`.
    sent_response = Mock(text="Hello AI", usage_metadata=None)
    monkeypatch.setattr(Models, "_logged_afc_warning", False)
    monkeypatch.setattr(Models, "_generate_content", Mock(return_value=sent_response))
    generator = GeminiGenerator(
        config=GenerationConfig(api_key="test", model_name="gemini-test"),
        client=genai.Client(api_key="test"),
        max_retries=0,
    )

    with caplog.at_level(logging.INFO, logger="google_genai"):
        result = generator.generate("test prompt")

    assert result.text == "Hello AI"
    assert Models._generate_content.call_count == 1
    assert not [r for r in caplog.records if "function calling" in r.getMessage()]


def test_generate_captures_token_usage():
    config = GenerationConfig(
        api_key="test",
        model_name="gemini-test",
    )
    mock_client = Mock()
    mock_response = Mock()
    mock_response.text = "Hello AI"
    mock_response.usage_metadata = Mock(
        prompt_token_count=120,
        candidates_token_count=30,
        total_token_count=150,
    )
    mock_client.models.generate_content.return_value = mock_response

    generator = GeminiGenerator(
        config=config,
        client=mock_client,
        max_retries=1,
    )

    result = generator.generate("test prompt")

    assert result.usage is not None
    assert result.usage.prompt_tokens == 120
    assert result.usage.completion_tokens == 30
    assert result.usage.total_tokens == 150
