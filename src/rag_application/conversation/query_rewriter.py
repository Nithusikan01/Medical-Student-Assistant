from rag_application.llm.generator import GeminiGenerator


class QueryRewriter:
    def __init__(self, generator: GeminiGenerator):
        self.generator = generator

    def rewrite(
            self, 
            query: str, 
            summary: str,
            recent_messages: list
    ) -> str:
        """
        Rewrites the user's query based on the conversation history to make it more contextually relevant.

        :param query: The original user query.
        :param conversation_history: A list of previous conversation turns (e.g., [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]).
        :return: The rewritten query.
        """

        recent_messages_str = "\n".join(
            f"{msg.role}: {msg.content}"
            for msg in recent_messages
        )

        prompt = f"""
        You are a helpful assistant that rewrites user queries to be more contextually relevant standalone queries based on the conversation history.
        
        Conversation summary(Excluding recent messages):
        {summary}
        
        Recent Messages:
        {recent_messages_str}

        Current User Query:
        {query}

        Rewrite the current user query into a standalone search query.

        Return ONLY the rewritten query.
        """

        response = self.generator.generate(prompt)
        return response.text.strip()
