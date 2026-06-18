from unittest.mock import Mock

from rag_application.llm.generator import GeminiGenerator
from rag_application.config.settings import Settings
from rag_application.llm.schemas import LLMResponse


def test_generate_success():

    settings = Settings(
        pinecone_api_key="x",
        pinecone_index_name="x",
        gemini_api_key="test",
        generation_model_name="gemini-test"
    )

    mock_client = Mock()
    mock_response = Mock()
    mock_response.text = "Hello AI"

    mock_client.models.generate_content.return_value = mock_response

    generator = GeminiGenerator(
        settings=settings,
        client=mock_client,
        max_retries=1
    )

    result = generator.generate("test prompt")

    assert isinstance(result, LLMResponse)
    assert result.text  == "Hello AI"