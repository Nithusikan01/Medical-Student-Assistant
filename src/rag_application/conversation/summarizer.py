from rag_application.llm.generator import GeminiGenerator
from rag_application.conversation.memory import ConversationMemory


class ConversationSummarizer:
    def __init__(
            self, 
            generator: GeminiGenerator
        ):
        self.generator = generator

    def summarize(
            self, 
            conversation_memory: ConversationMemory
    ) -> str:
        
        messages = conversation_memory.get_recent_messages()

        conversation_text = "\n".join(
            f"{message.role}: {message.content}"
            for message in messages
        )

        prompt = f"""
    Summarize the following conversation.

    Current summary:
    {conversation_memory.summary}

    Recent messages:
    {conversation_text}

    Return the updated summary of the conversation only.
"""
        response = self.generator.generate(prompt)
        return response.text.strip()