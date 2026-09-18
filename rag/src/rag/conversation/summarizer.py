from rag.conversation.memory import ConversationMemory
from rag.llm.protocol import TextGenerator
from rag.observability import Stage, Tracer, generation_metadata


class ConversationSummarizer:

    def __init__(self, generator: TextGenerator, *, tracer: Tracer | None = None):
        self.generator = generator
        self.tracer = tracer if tracer is not None else Tracer()

    def summarize(self, memory: ConversationMemory) -> str:

        messages = memory.get_recent_messages()

        conversation_text = "\n".join(f"{m.role}: {m.content}" for m in messages)

        prompt = f"""
You are a conversation summarizer.

Your job is to maintain a compact memory of the conversation.

Existing summary:
{memory.summary}

Recent conversation:
{conversation_text}

Rules:
- Preserve important entities (names, projects, facts)
- Remove repetition
- Keep it concise but informative

Return ONLY the updated summary.
"""

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
