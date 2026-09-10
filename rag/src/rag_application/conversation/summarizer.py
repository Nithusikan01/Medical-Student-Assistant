from rag_application.llm.generator import GeminiGenerator
from rag_application.conversation.memory import ConversationMemory


class ConversationSummarizer:

    def __init__(self, generator: GeminiGenerator):
        self.generator = generator

    def summarize(self, memory: ConversationMemory) -> str:

        messages = memory.get_recent_messages()

        conversation_text = "\n".join(
            f"{m.role}: {m.content}"
            for m in messages
        )

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

        response = self.generator.generate(prompt)
        return response.text.strip()