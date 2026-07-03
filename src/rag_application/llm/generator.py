import time
import logging
from typing import Optional

from google import genai

from rag_application.llm.schemas import LLMResponse
from rag_application.config.component_configs import GenerationConfig

logger = logging.getLogger(__name__)


class GeminiGenerator:
    """
    Production-ready Gemini LLM wrapper.

    Features:
    - Retry mechanism
    - Latency tracking
    - Safe response parsing
    - Future-ready metadata support
    """

    def __init__(
        self,
        config: Optional[GenerationConfig] = None,
        *,
        settings=None,
        client: Optional[genai.Client] = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ):

        config = config or settings

        if config is None:
            raise ValueError("Generation configuration is required")

        api_key = getattr(config, "api_key", None) or getattr(config, "gemini_api_key", None)
        model_name = getattr(config, "model_name", None) or getattr(config, "generation_model_name", None)

        if not api_key:
            raise ValueError("API key is required")

        if not model_name:
            raise ValueError("Model name is required")

        self.client = client or genai.Client(api_key=api_key)
        self.model_name = model_name

        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def generate(self, prompt: str) -> LLMResponse:
        """
        Generate response from Gemini with retries and telemetry.
        """

        last_error = None
        start_time = time.time()

        for attempt in range(self.max_retries + 1):

            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )

                text = getattr(response, "text", None)

                if not text:
                    raise RuntimeError("Gemini returned empty response")

                latency = time.time() - start_time

                return LLMResponse(
                    text=text.strip(),
                    model=self.model_name,
                    latency=latency,
                    metadata={
                        "attempt": attempt + 1,
                        "success": True
                    }
                )

            except Exception as e:
                last_error = e

                logger.warning(
                    "Gemini attempt %d failed: %s",
                    attempt + 1,
                    str(e)
                )

                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                    continue

                break

        raise RuntimeError(
            f"Gemini generation failed after {self.max_retries + 1} attempts: {last_error}"
        )