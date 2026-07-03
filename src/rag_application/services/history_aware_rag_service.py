import logging
from typing import List, Tuple

from rag_application.retrieval.schemas import RetrievedChunk

from rag_application.llm.generator import GeminiGenerator
from rag_application.llm.prompt_builder import PromptBuilder

from rag_application.conversation.session_manager import SessionManager
from rag_application.conversation.query_rewriter import QueryRewriter
from rag_application.conversation.summarizer import ConversationSummarizer

from rag_application.retrieval.query_service import QueryService

logger = logging.getLogger(__name__)


class HistoryAwareRAGService:

    SUMMARY_TRIGGER = 12

    def __init__(
        self,
        query_service: QueryService,
        generator: GeminiGenerator,
        session_manager: SessionManager,
        query_rewriter: QueryRewriter,
        summarizer: ConversationSummarizer,
    ):
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
    ) -> Tuple[str, List[RetrievedChunk]]:

        # -------------------------
        # 1. MEMORY
        # -------------------------
        memory = self.session_manager.get_memory(conversation_id)
        memory.add_message("user", question)

        # -------------------------
        # 2. QUERY REWRITE
        # -------------------------
        rewritten_query = self.query_rewriter.rewrite(
            query=question,
            summary=memory.get_summary(),
            recent_messages=memory.get_recent_messages()
        )

        logger.info("Rewritten query: %s", rewritten_query)

        # -------------------------
        # 3. RETRIEVAL (HYBRID + RERANK)
        # -------------------------
        chunks = self.query_service.search(
            query=rewritten_query,
            top_k=top_k,
            candidate_k=candidate_k,
            use_reranker=True
        )

        if not chunks:
            answer = "I couldn't find relevant information in the documents."
            memory.add_message("assistant", answer)
            return answer, []

        # -------------------------
        # 4. PROMPT BUILDING
        # -------------------------
        prompt = PromptBuilder.build_prompt(
            question=question,
            chunks=chunks,
            summary=memory.get_summary(),
            recent_messages=memory.get_recent_messages()
        )

        # -------------------------
        # 5. GENERATION
        # -------------------------
        response = self.generator.generate(prompt)

        if not response.text:
            raise ValueError("LLM returned empty response")

        answer = response.text

        # -------------------------
        # 6. MEMORY UPDATE
        # -------------------------
        memory.add_message("assistant", answer)

        # -------------------------
        # 7. SUMMARY UPDATE
        # -------------------------
        if len(memory.messages) >= self.SUMMARY_TRIGGER:
            updated_summary = self.summarizer.summarize(memory)
            memory.update_summary(updated_summary)

        return answer, chunks

    def answer(self, conversation_id: str, question: str, top_k: int = 5) -> str:
        answer, _ = self.answer_with_sources(conversation_id, question, top_k)
        return answer