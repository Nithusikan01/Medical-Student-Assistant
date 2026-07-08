from textwrap import dedent
from typing import List, Optional
from rag_application.conversation.schemas import ChatMessage
from rag_application.retrieval.schemas import RetrievedChunk


class PromptBuilder:

    @staticmethod
    def build_prompt(
        question: str,
        chunks: List[RetrievedChunk],
        summary: Optional[str] = None,
        recent_messages: Optional[List[ChatMessage]] = None
    ) -> str:

        # -------------------------
        # 1. Structured context blocks
        # -------------------------
        context_blocks = []

        for i, c in enumerate(chunks, start=1):

            context_blocks.append(
                f"""
[Context {i}]
Source ID: {c.id}
Content:
{c.text}
"""
            )

        context = "\n".join(context_blocks)

        # -------------------------
        # 2. Recent messages formatting
        # -------------------------
        if recent_messages:
            recent_messages_str = "\n".join(
                f"{m.role}: {m.content}"
                for m in recent_messages
            )
        else:
            recent_messages_str = "No recent messages available."

        # -------------------------
        # 3. Build prompt
        # -------------------------
        prompt = dedent(
            f"""
            You are a retrieval-grounded answer generator.

            Rules:
            - Use only the provided context.
            - Return the shortest answer that fully answers the question.
            - For names, titles, roles, dates, numbers, certifications, and list items, prefer the exact wording from the context.
            - Normalize obvious punctuation differences when it keeps the meaning identical, such as using "and" instead of "&" in titles.
            - Do not paraphrase if the context already contains a precise phrase.
            - If the answer is not explicitly supported by the context, return exactly: I don't know based on the provided document.
            - Do not guess, expand, summarize, or add extra explanation.
            - Output only the final answer text.
            - Do not include labels such as Answer:, Evidence:, Final Answer:, bullets, or markdown.

            If the question asks for a role/title/organization label, copy that phrase as a short noun phrase and do not add surrounding words.
            If the context says "Research Manager & Team Lead of the DAP Team", respond with the short title phrase "Research Manager and Team Lead of the DAP Team".

            Conversation summary:
            {summary if summary else "No summary available."}

            Recent messages:
            {recent_messages_str}

            Context:
            {context}

            Question:
            {question}

            Answer:
            """
        )

        return prompt.strip()