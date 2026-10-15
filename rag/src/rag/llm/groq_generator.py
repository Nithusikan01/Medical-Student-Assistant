import logging
import time

from groq import Groq

from rag.config.component_configs import GenerationConfig
from rag.llm.retry import EmptyResponseError, retry_delay, should_retry
from rag.llm.schemas import LLMResponse, TokenUsage
from rag.observability import classify

logger = logging.getLogger(__name__)


def _extract_usage(response) -> TokenUsage | None:
    usage = getattr(response, "usage", None)

    if usage is None:
        return None

    return TokenUsage(
        prompt_tokens=usage.prompt_tokens or 0,
        completion_tokens=usage.completion_tokens or 0,
        total_tokens=usage.total_tokens or 0,
    )


class GroqGenerator:
    """
    Wrapper around Groq's OpenAI-compatible chat completions API.

    Mirrors GeminiGenerator's shape (retry, latency, structured response) so
    the two are interchangeable behind the TextGenerator protocol.
    """

    def __init__(
        self,
        config: GenerationConfig,
        *,
        client: Groq | None = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ) -> None:

        if not config.api_key:
            raise ValueError("Groq API key is missing.")

        if not config.model_name:
            raise ValueError("Groq model name is missing.")

        self.client = client if client is not None else Groq(api_key=config.api_key)

        self.model_name = config.model_name

        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def generate(
        self,
        prompt: str,
    ) -> LLMResponse:
        """
        Generate a response from Groq.
        """

        logger.debug("Generating response with Groq.")

        start_time = time.perf_counter()

        last_error: Exception | None = None

        for attempt in range(
            1,
            self.max_retries + 2,
        ):

            try:

                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                )

                text = response.choices[0].message.content

                if not text:
                    raise EmptyResponseError("Groq returned an empty response.")

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
                        "provider": "groq",
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

        raise RuntimeError("Groq generation failed.") from last_error
