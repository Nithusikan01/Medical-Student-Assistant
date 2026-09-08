from unittest.mock import Mock

from rag_application.config.component_configs import GenerationConfig
from rag_application.llm.generator import GeminiGenerator
from rag_application.llm.schemas import LLMResponse


def test_generate_success():
    config = GenerationConfig(
        api_key="test",
        model_name="gemini-test",
    )
    mock_client = Mock()
    mock_response = Mock()
    mock_response.text = "Hello AI"
    mock_client.models.generate_content.return_value = mock_response

    generator = GeminiGenerator(
        config=config,
        client=mock_client,
        max_retries=1,
    )

    result = generator.generate("test prompt")

    assert isinstance(result, LLMResponse)
    assert result.text == "Hello AI"
    mock_client.models.generate_content.assert_called_once_with(
        model="gemini-test",
        contents="test prompt",
    )
