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
        prompt = f"""
You are a highly accurate retrieval-based assistant.

You MUST follow these rules:

- Answer ONLY using the provided context
- If the answer is not in the context, say:
  "I don't know based on the provided document."
- Do NOT guess or hallucinate
- Prefer exact names, titles, and entities from context
- Be concise and precise

========================
CONVERSATION SUMMARY
========================
{summary if summary else "No summary available."}

========================
RECENT MESSAGES
========================
{recent_messages_str}

========================
CONTEXT
========================
{context}

========================
QUESTION
========================
{question}

========================
ANSWER
Answer:
Evidence:
- Context 1
- Context 3
Final Answer:
========================
"""

        return prompt.strip()