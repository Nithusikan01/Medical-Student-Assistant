from typing import Protocol

from rag.llm.schemas import LLMResponse


class TextGenerator(Protocol):
    """
    Structural contract for anything that can turn a prompt into text.

    GeminiGenerator and GroqGenerator both satisfy this without inheriting
    from it, the same protocol seam used elsewhere in the engine
    (ConversationStore, ChunkSink) to keep call sites swappable.
    """

    def generate(self, prompt: str) -> LLMResponse: ...
