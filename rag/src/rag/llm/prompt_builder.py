from textwrap import dedent

from rag.conversation.schemas import ChatMessage
from rag.retrieval.schemas import RetrievedChunk


class PromptBuilder:
    """
    Builds the prompt supplied to the LLM.
    """

    @staticmethod
    def build_prompt(
        question: str,
        chunks: list[RetrievedChunk],
        summary: str | None = None,
        recent_messages: list[ChatMessage] | None = None,
    ) -> str:

        context = PromptBuilder._format_context(chunks)
        conversation = PromptBuilder._format_conversation(recent_messages)

        prompt = dedent(
            f"""
            You are a retrieval-grounded answer generator.

            Rules:
            - Answer ONLY using the supplied context.
            - Never use outside knowledge.
            - If the answer is not explicitly supported by the context, reply exactly:
              I don't know based on the provided document.
            - Prefer the exact wording from the context for:
              - names
              - roles
              - organizations
              - dates
              - numbers
              - certifications
              - titles
            - Keep the answer concise.
            - Do not explain your reasoning.
            - Do not output markdown.
            - Do not output bullet points unless explicitly requested.
            - Output only the final answer.

            Conversation Summary:
            {summary or "No summary available."}

            Recent Conversation:
            {conversation}

            Retrieved Context:
            {context}

            Question:
            {question}

            Answer:
            """
        )

        return prompt.strip()

    @staticmethod
    def _format_context(
        chunks: list[RetrievedChunk],
    ) -> str:

        if not chunks:
            return "No retrieved context."

        blocks = []

        for index, chunk in enumerate(chunks, start=1):

            metadata = chunk.metadata

            lines = [
                f"[Context {index}]",
                f"Document: {metadata.filename}",
                f"Chunk: {metadata.chunk_index}",
            ]

            if metadata.page_number is not None:
                lines.append(f"Page: {metadata.page_number}")

            if metadata.section_title:
                lines.append(f"Section: {metadata.section_title}")

            lines.extend(
                [
                    "Content:",
                    chunk.text,
                ]
            )

            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    @staticmethod
    def _format_conversation(
        messages: list[ChatMessage] | None,
    ) -> str:

        if not messages:
            return "No recent conversation."

        return "\n".join(f"{message.role}: {message.content}" for message in messages)
