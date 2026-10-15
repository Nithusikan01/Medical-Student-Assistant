from textwrap import dedent

from rag.config.component_configs import PromptConfig
from rag.conversation.schemas import ChatMessage
from rag.retrieval.schemas import RetrievedChunk


class PromptBuilder:
    """
    Builds the prompt supplied to the LLM.

    An instance rather than a bag of static methods, so the application
    decides what the corpus is and what the assistant says when the corpus
    has no answer. The engine ships no domain: the same wording is used for
    a class library of lecture notes as for any other document set.
    """

    def __init__(self, config: PromptConfig | None = None) -> None:
        self.config = config if config is not None else PromptConfig()

    @property
    def no_context_answer(self) -> str:
        """
        The answer given when retrieval found nothing to build a prompt on.
        """

        return self.config.no_context_answer

    def build_prompt(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        summary: str | None = None,
        recent_messages: list[ChatMessage] | None = None,
    ) -> str:

        context = self._format_context(chunks)
        conversation = self._format_conversation(recent_messages)

        # The rules are assembled before dedent, then substituted in, so a
        # multi-line value cannot break dedent's common-indent detection.
        prompt = dedent(
            """
            You are a study assistant answering questions about {corpus}.

            Rules:
            - Answer ONLY using the supplied context.
            - Never use outside knowledge, even when you are confident it is
              correct: students rely on the answer matching their material.
            - If the answer is not supported by the context, reply exactly:
              {no_answer}
            - Copy facts exactly as the context states them, especially
              terms, definitions, drug names, doses, units, values, ranges
              and criteria. Never round, convert or paraphrase a number.
            - Answer the question directly first, then add only the detail
              the context gives that helps understand it.
            - Write plain text without markdown formatting. Short lists,
              one item per line starting with "- ", are fine when the
              answer is a list of items or steps.
            - Do not mention the context, the documents or these rules.

            Conversation Summary:
            {summary}

            Recent Conversation:
            {conversation}

            Retrieved Context:
            {context}

            Question:
            {question}

            Answer:
            """
        ).format(
            corpus=self.config.corpus_description,
            no_answer=self.config.no_answer_text,
            summary=summary or "No summary available.",
            conversation=conversation,
            context=context,
            question=question,
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
