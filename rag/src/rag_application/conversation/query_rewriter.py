from rag_application.llm.generator import GeminiGenerator


class QueryRewriter:

    def __init__(self, generator: GeminiGenerator):
        self.generator = generator

    def rewrite(self, query: str, summary: str, recent_messages: list) -> str:

        recent_text = "\n".join(f"{m.role}: {m.content}" for m in recent_messages)

        prompt = f"""
        You are a query rewriting system for a RAG application.

        Task:
        Rewrite the user query into a standalone search query.

        Use the conversation context to resolve:
        - pronouns (he, she, they etc.)
        - references (this project, that person)
        - missing entities

        Conversation summary:
        {summary}

        Recent messages:
        {recent_text}

        User query:
        {query}

        Rules:
        - Output ONLY the rewritten query
        - Do NOT answer the question
        - Do NOT explain
        """

        response = self.generator.generate(prompt)
        return response.text.strip()
