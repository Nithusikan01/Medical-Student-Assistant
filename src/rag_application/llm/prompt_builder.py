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

        context = "\n\n".join(
            [
                f"[Score: {c.score:.2f}]\n{c.text}"
                for c in chunks
            ]
        )

        recent_messages_str = "\n".join(
            f"{msg.role}: {msg.content}"
            for msg in recent_messages
        ) if recent_messages else "No recent messages available."


        prompt = f"""
You are an intelligent assistant. Use the context below to answer the question.

RULES:
- If the answer is not in the context, say "I don't know based on the provided document."
- Be concise and accurate.
- Do not hallucinate.

CONTEXT:
{context}

SUMMARY:
{summary if summary else "No summary available."}

RECENT MESSAGES:
{recent_messages_str}

QUESTION:
{question}

ANSWER:
"""

        return prompt.strip()