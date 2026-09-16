from rag.llm.generator import GeminiGenerator
from rag.observability import Stage, Tracer, generation_metadata


class QueryRewriter:

    def __init__(self, generator: GeminiGenerator, *, tracer: Tracer | None = None):
        self.generator = generator
        self.tracer = tracer if tracer is not None else Tracer()

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

        with self.tracer.span(
            Stage.QUERY_REWRITE,
            original_length=len(query),
            recent_message_count=len(recent_messages),
            has_summary=bool(summary),
        ) as span:

            response = self.generator.generate(prompt)
            rewritten = response.text.strip()

            span.set(
                rewritten_length=len(rewritten),
                # Whether the rewrite did anything at all. A conversational
                # follow-up that comes back unchanged is the first thing to
                # check when retrieval looks wrong.
                changed=rewritten != query.strip(),
                **generation_metadata(response),
            )

            return rewritten
