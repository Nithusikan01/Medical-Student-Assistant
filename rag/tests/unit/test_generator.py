from unittest.mock import Mock

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
    mock_client.models.generate_content.assert_called_once_with(
        model="gemini-test",
        contents="test prompt",
    )


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
