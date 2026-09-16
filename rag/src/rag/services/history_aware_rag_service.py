import logging
from collections.abc import Callable

from rag.conversation.query_rewriter import QueryRewriter
from rag.conversation.store import ConversationStore
from rag.conversation.summarizer import ConversationSummarizer
from rag.llm.prompt_builder import PromptBuilder
from rag.llm.protocol import TextGenerator
from rag.llm.schemas import TokenUsage
from rag.retrieval.query_service import QueryService
from rag.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class HistoryAwareRAGService:
    """
    End-to-end conversational RAG pipeline.

        User Question
              │
              ▼
        Conversation Memory
              │
              ▼
         Query Rewriting
              │
              ▼
      Retrieval (+ Reranking)
              │
              ▼
        Prompt Construction
              │
              ▼
         LLM Generation
              │
              ▼
        Memory / Summary Update
    """

    SUMMARY_TRIGGER = 12

    def __init__(
        self,
        query_service: QueryService,
        generator: TextGenerator,
        session_manager: ConversationStore,
        query_rewriter: QueryRewriter,
        summarizer: ConversationSummarizer,
    ) -> None:
        self.query_service = query_service
        self.generator = generator

        self.session_manager = session_manager
        self.query_rewriter = query_rewriter
        self.summarizer = summarizer

    def answer_with_sources(
        self,
        conversation_id: str,
        question: str,
        top_k: int = 5,
        candidate_k: int = 30,
        generator: TextGenerator | None = None,
        on_usage: Callable[[TokenUsage], None] | None = None,
    ) -> tuple[str, list[RetrievedChunk]]:
        """
        Generate an answer together with the retrieved supporting chunks.

        `generator` overrides the service's default LLM for this call only
        (e.g. a user-selected model), leaving query rewriting and
        summarization on the default. `on_usage`, if given, is called once
        with the generation call's token usage - it is the caller's hook for
        persisting/metering usage, since this service has no storage of its
        own; it is not called when the retrieval short-circuit below skips
        generation entirely, or when the provider reports no usage data.
        """

        logger.info(
            "Processing question for conversation '%s'.",
            conversation_id,
        )

        #
        # 1. Conversation memory
        #
        memory = self.session_manager.get_memory(conversation_id)

        memory.add_message(
            role="user",
            content=question,
        )

        #
        # 2. Rewrite query
        #
        rewritten_query = self.query_rewriter.rewrite(
            query=question,
            summary=memory.get_summary(),
            recent_messages=memory.get_recent_messages(),
        )

        logger.info(
            "Rewritten query: %s",
            rewritten_query,
        )

        #
        # 3. Retrieve supporting chunks
        #
        chunks = self.query_service.search(
            query=rewritten_query,
            top_k=top_k,
            candidate_k=candidate_k,
            use_reranker=True,
        )

        if not chunks:

            answer = "I couldn't find relevant information " "in the documents."

            memory.add_message(
                role="assistant",
                content=answer,
            )

            return answer, []

        logger.debug(
            "Retrieved %d supporting chunks.",
            len(chunks),
        )

        #
        # 4. Build prompt
        #
        prompt = PromptBuilder.build_prompt(
            question=question,
            chunks=chunks,
            summary=memory.get_summary(),
            recent_messages=memory.get_recent_messages(),
        )

        #
        # 5. Generate answer
        #
        response = (generator or self.generator).generate(prompt)

        if not response.text:
            raise ValueError("LLM returned an empty response.")

        answer = response.text

        if on_usage is not None and response.usage is not None:
            on_usage(response.usage)

        #
        # 6. Update conversation memory
        #
        memory.add_message(
            role="assistant",
            content=answer,
        )

        #
        # 7. Update conversation summary
        #
        if len(memory.messages) >= self.SUMMARY_TRIGGER:

            logger.debug("Updating conversation summary.")

            summary = self.summarizer.summarize(memory)

            memory.update_summary(summary)

        return answer, chunks

    def answer(
        self,
        conversation_id: str,
        question: str,
        top_k: int = 5,
        generator: TextGenerator | None = None,
        on_usage: Callable[[TokenUsage], None] | None = None,
    ) -> str:
        """
        Generate an answer without returning the retrieved chunks.
        """

        answer, _ = self.answer_with_sources(
            conversation_id=conversation_id,
            question=question,
            top_k=top_k,
            generator=generator,
            on_usage=on_usage,
        )

        return answer
