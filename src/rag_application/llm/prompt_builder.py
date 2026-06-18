from typing import List
from rag_application.retrieval.schemas import RetrievedChunk


class PromptBuilder:

    @staticmethod
    def build_prompt(
        question: str,
        chunks: List[RetrievedChunk]
    ) -> str:

        context = "\n\n".join(
            [
                f"[Score: {c.score:.2f}]\n{c.text}"
                for c in chunks
            ]
        )


        prompt = f"""
You are an intelligent assistant. Use the context below to answer the question.

RULES:
- If the answer is not in the context, say "I don't know based on the provided document."
- Be concise and accurate.
- Do not hallucinate.

CONTEXT:
{context}

QUESTION:
{question}

ANSWER:
"""

        return prompt.strip()