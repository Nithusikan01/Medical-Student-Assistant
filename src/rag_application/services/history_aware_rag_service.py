import logging
from typing import List, Tuple

from rag_application.conversation.query_rewriter import QueryRewriter
from rag_application.conversation.summarizer import ConversationSummarizer
from rag_application.conversation.session_manager import SessionManager

from rag_application.llm.generator import GeminiGenerator
from rag_application.llm.prompt_builder import PromptBuilder

from rag_application.retrieval.retriever import Retriever
from rag_application.retrieval.schemas import RetrievedChunk


logger = logging.getLogger(__name__)


class HistoryAwareRAGService:

    SUMMARY_TRIGGER = 12

    def __init__(
        self,
        retriever: Retriever,
        generator: GeminiGenerator,
        session_manager: SessionManager,
        query_rewriter: QueryRewriter,
        summarizer: ConversationSummarizer,
    ):
        self.retriever = retriever
        self.generator = generator

        self.session_manager = session_manager
        self.query_rewriter = query_rewriter
        self.summarizer = summarizer

    def answer(
        self,
        conversation_id: str,
        question: str,
        top_k: int = 5,
    ) -> str:
        answer, _ = self.answer_with_sources(
            conversation_id=conversation_id,
            question=question,
            top_k=top_k,
        )
        return answer

    def answer_with_sources(
        self,
        conversation_id: str,
        question: str,
        top_k: int = 5,
    ) -> Tuple[str, List[RetrievedChunk]]:

        memory = self.session_manager.get_memory(
            conversation_id
        )

        # -------------------------
        # Store user message
        # -------------------------

        memory.add_message(
            role="user",
            content=question
        )

        # -------------------------
        # Rewrite query using history
        # -------------------------

        rewritten_query = self.query_rewriter.rewrite(
            query=question,
            summary=memory.get_summary(),
            recent_messages=memory.get_recent_messages()
        )

        logger.info(
            "Original query: %s",
            question
        )

        logger.info(
            "Rewritten query: %s",
            rewritten_query
        )

        # -------------------------
        # Retrieval
        # -------------------------

        chunks = self.retriever.retrieve(
            query=rewritten_query,
            top_k=top_k
        )

        if not chunks:
            answer = (
                "I don't know based on the provided documents."
            )

            memory.add_message(
                role="assistant",
                content=answer
            )

            return answer, []

        # -------------------------
        # Prompt construction
        # -------------------------

        prompt = PromptBuilder.build_prompt(
            question=question,
            chunks=chunks,
            summary=memory.get_summary(),
            recent_messages=memory.get_recent_messages()
        )

        # -------------------------
        # Generation
        # -------------------------

        response = self.generator.generate(
            prompt
        )

        if not response.text:
            raise ValueError(
                "Gemini returned empty response"
            )

        answer = response.text

        # -------------------------
        # Store assistant response
        # -------------------------

        memory.add_message(
            role="assistant",
            content=answer
        )

        # -------------------------
        # Summarization trigger
        # -------------------------

        if (
            len(memory.messages)
            >= self.SUMMARY_TRIGGER
        ):

            logger.info(
                "Conversation summary update triggered"
            )

            updated_summary = (
                self.summarizer.summarize(memory)
            )

            memory.update_summary(
                updated_summary
            )

        return answer, chunks
