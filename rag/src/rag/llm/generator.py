import logging
import time

from google import genai
from google.genai import types

from rag.config.component_configs import GenerationConfig
from rag.llm.retry import EmptyResponseError, retry_delay, should_retry
from rag.llm.schemas import LLMResponse, TokenUsage
from rag.observability import classify

logger = logging.getLogger(__name__)

# Gemini is never given tools here, so automatic function calling has nothing
# to call. Left at the SDK default (on), every request still goes through the
# SDK's AFC loop, which logs a warning recommending Chat.send_message on the
# first call. Disabling it sends the request straight to the model.
_REQUEST_CONFIG = types.GenerateContentConfig(
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)


def _extract_usage(response) -> TokenUsage | None:
    usage_metadata = getattr(response, "usage_metadata", None)

    if usage_metadata is None:
        return None

    return TokenUsage(
        prompt_tokens=usage_metadata.prompt_token_count or 0,
        completion_tokens=usage_metadata.candidates_token_count or 0,
        total_tokens=usage_metadata.total_token_count or 0,
    )


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
                    config=_REQUEST_CONFIG,
                )

                text = getattr(
                    response,
                    "text",
                    None,
                )

                if not text:
                    raise EmptyResponseError("Gemini returned an empty response.")

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
                    usage=_extract_usage(response),
                )

            # Broad on purpose: any failure is caught so it can be
            # classified. Whether it is retried is should_retry's decision -
            # a rejected key or an invalid request fails the same way every
            # time, so only transient failures get another attempt.
            except Exception as exc:  # noqa: BLE001

                last_error = exc

                # The category and type, never the message: provider
                # messages can echo the key or endpoint the call was sent to.
                logger.warning(
                    "Generation attempt %d/%d failed (%s, %s).",
                    attempt,
                    self.max_retries + 1,
                    type(exc).__name__,
                    classify(exc).value,
                )

                if attempt > self.max_retries or not should_retry(exc):
                    break

                time.sleep(retry_delay(exc, attempt, self.retry_delay))

        raise RuntimeError("Gemini generation failed.") from last_error
