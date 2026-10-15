from textwrap import dedent

from rag.conversation.memory import ConversationMemory
from rag.llm.protocol import TextGenerator
from rag.observability import Stage, Tracer, generation_metadata

_PROMPT = dedent(
    """
    You maintain a compact running summary of a study conversation.

    Existing summary:
    {summary}

    New conversation turns:
    {conversation}

    Rules:
    - Merge the new turns into the existing summary.
    - Keep the topics, terms, definitions and facts the student asked
      about, and anything later questions are likely to refer back to.
    - Copy numbers, doses, units and names exactly.
    - Drop greetings, repetition and anything already covered.
    - Keep it concise.

    Return ONLY the updated summary.
    """
).strip()


class ConversationSummarizer:

    def __init__(self, generator: TextGenerator, *, tracer: Tracer | None = None):
        self.generator = generator
        self.tracer = tracer if tracer is not None else Tracer()

    def summarize(self, memory: ConversationMemory) -> str:

        # Every turn since the last summary, not the recent-message window:
        # the trigger fires after `summary_trigger` pending turns, and the
        # window holds fewer, so summarising the window silently dropped
        # the oldest turns of every cycle from the conversation's memory.
        messages = list(memory.messages)

        conversation_text = "\n".join(f"{m.role}: {m.content}" for m in messages)

        prompt = _PROMPT.format(
            summary=memory.summary or "No summary yet.",
            conversation=conversation_text,
        )

        with self.tracer.span(
            Stage.SUMMARIZATION,
            message_count=len(messages),
            previous_summary_length=len(memory.summary or ""),
        ) as span:

            response = self.generator.generate(prompt)
            summary = response.text.strip()

            span.set(
                summary_length=len(summary),
                **generation_metadata(response),
            )

            return summary
