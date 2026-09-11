import logging
import time

from google import genai

from rag.config.component_configs import GenerationConfig
from rag.llm.schemas import LLMResponse

logger = logging.getLogger(__name__)


class GeminiGenerator:
    """
    Wrapper around the Gemini API.

    Features:
        - retry mechanism
        - latency measurement
        - structured response
        - dependency injection for testing
    """

    def __init__(
        self,
        config: GenerationConfig,
        *,
        client: genai.Client | None = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ) -> None:

        if not config.api_key:
            raise ValueError("Gemini API key is missing.")

        if not config.model_name:
            raise ValueError("Gemini model name is missing.")

        self.client = (
            client if client is not None else genai.Client(api_key=config.api_key)
        )

        self.model_name = config.model_name

        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def generate(
        self,
        prompt: str,
    ) -> LLMResponse:
        """
        Generate a response from Gemini.
        """

        logger.debug("Generating response with Gemini.")

        start_time = time.perf_counter()

        last_error: Exception | None = None

        for attempt in range(
            1,
            self.max_retries + 2,
        ):

            try:

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )

                text = getattr(
                    response,
                    "text",
                    None,
                )

                if not text:
                    raise RuntimeError("Gemini returned an empty response.")

                latency = time.perf_counter() - start_time

                logger.debug(
                    "Generation completed in %.3f seconds.",
                    latency,
                )

                return LLMResponse(
                    text=text.strip(),
                    model=self.model_name,
                    latency=latency,
                    metadata={
                        "attempt": attempt,
                        "provider": "gemini",
                    },
                )

            # Deliberately broad: this is a retry wrapper around a third-party
            # client, and any failure it raises - transport, quota, or an
            # empty response - is worth one more attempt. Narrowing this would
            # let an unlisted error escape the retry entirely.
            except Exception as exc:  # noqa: BLE001

                last_error = exc

                logger.warning(
                    "Generation attempt %d/%d failed: %s",
                    attempt,
                    self.max_retries + 1,
                    exc,
                )

                if attempt <= self.max_retries:
                    time.sleep(self.retry_delay)

        raise RuntimeError("Gemini generation failed.") from last_error
