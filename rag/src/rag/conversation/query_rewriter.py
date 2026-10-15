from textwrap import dedent

from rag.llm.protocol import TextGenerator
from rag.observability import Stage, Tracer, generation_metadata

# Formatted rather than an f-string inside dedent: substituting multi-line
# conversation text first leaves lines at column zero, dedent then finds no
# common indent, and the model receives the whole prompt indented.
_PROMPT = dedent(
    """
    You rewrite a follow-up question into a standalone search query for a
    document search engine.

    Use the conversation to resolve:
    - pronouns (it, they, this, that, these)
    - references to something discussed earlier ("the second one",
      "that condition", "the drug you mentioned")
    - terms the question leaves out but clearly means

    Conversation summary:
    {summary}

    Recent messages:
    {recent}

    Follow-up question:
    {query}

    Rules:
    - Output ONLY the rewritten query, on one line.
    - Keep every technical term, name, abbreviation and number exactly as
      written.
    - If the question is already standalone, output it unchanged.
    - Do NOT answer the question and do NOT explain.
    """
).strip()


class QueryRewriter:

    def __init__(self, generator: TextGenerator, *, tracer: Tracer | None = None):
        self.generator = generator
        self.tracer = tracer if tracer is not None else Tracer()

    def rewrite(self, query: str, summary: str, recent_messages: list) -> str:

        recent_text = "\n".join(f"{m.role}: {m.content}" for m in recent_messages)

        prompt = _PROMPT.format(
            summary=summary or "No summary available.",
            recent=recent_text or "No recent conversation.",
            query=query,
        )

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
