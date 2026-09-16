from unittest.mock import Mock

from rag.config.component_configs import GenerationConfig
from rag.llm.groq_generator import GroqGenerator
from rag.llm.schemas import LLMResponse


def test_generate_success():
    config = GenerationConfig(
        api_key="test",
        model_name="openai/gpt-oss-120b",
    )
    mock_client = Mock()
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="Hello AI"))]
    mock_response.usage = None
    mock_client.chat.completions.create.return_value = mock_response

    generator = GroqGenerator(
        config=config,
        client=mock_client,
        max_retries=1,
    )

    result = generator.generate("test prompt")

    assert isinstance(result, LLMResponse)
    assert result.text == "Hello AI"
    assert result.usage is None
    mock_client.chat.completions.create.assert_called_once_with(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": "test prompt"}],
    )


def test_generate_captures_token_usage():
    config = GenerationConfig(
        api_key="test",
        model_name="openai/gpt-oss-120b",
    )
    mock_client = Mock()
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="Hello AI"))]
    mock_response.usage = Mock(
        prompt_tokens=80,
        completion_tokens=20,
        total_tokens=100,
    )
    mock_client.chat.completions.create.return_value = mock_response

    generator = GroqGenerator(
        config=config,
        client=mock_client,
        max_retries=1,
    )

    result = generator.generate("test prompt")

    assert result.usage is not None
    assert result.usage.prompt_tokens == 80
    assert result.usage.completion_tokens == 20
    assert result.usage.total_tokens == 100
