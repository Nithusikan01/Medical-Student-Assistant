import logging
from typing import Any

from rag.cache.protocol import ResponseCache
from rag.cache.schemas import CacheLookup
from rag.cache.semantic_cache import NullResponseCache
from rag.conversation.query_rewriter import QueryRewriter
from rag.conversation.small_talk import SmallTalkResponder
from rag.conversation.store import ConversationStore
from rag.conversation.summarizer import ConversationSummarizer
from rag.llm.prompt_builder import PromptBuilder
from rag.llm.protocol import TextGenerator
from rag.observability import Stage, Tracer, generation_metadata
from rag.retrieval.query_service import QueryService
from rag.retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)

# What the cache scopes an answer to when the caller names no model. The
# service is handed a generator, not an id, and two different models must
# never share an entry - so an unnamed one gets a bucket of its own rather
# than being lumped in with a named default.
DEFAULT_CACHE_MODEL_ID = "default"


class HistoryAwareRAGService:
    """
    End-to-end conversational RAG pipeline.

        User Question
              │
              ▼
        Conversation Memory
              │
              ├────► Small Talk ──────────────────┐
              ▼      (greeting, thanks, farewell) │
         Query Rewriting                          │
              │                                   │
              ▼                                   │
      Retrieval (+ Reranking)                     │
              │                                   │
              ▼                                   │
        Prompt Construction                       │
              │                                   │
              ▼                                   │
         LLM Generation                           │
              │                                   │
              ▼                                   │
        Memory / Summary Update  ◄────────────────┘
    """

    SUMMARY_TRIGGER = 12

    def __init__(
        self,
        query_service: QueryService,
        generator: TextGenerator,
        session_manager: ConversationStore,
        query_rewriter: QueryRewriter,
        summarizer: ConversationSummarizer,
        *,
        response_cache: ResponseCache | None = None,
        small_talk: SmallTalkResponder | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.query_service = query_service
        self.generator = generator

        self.session_manager = session_manager
        self.query_rewriter = query_rewriter
        self.summarizer = summarizer

        # Keyword-only and defaulted to a cache that remembers nothing, so
        # every existing caller keeps the behaviour it had.
        self.response_cache: ResponseCache = (
            response_cache if response_cache is not None else NullResponseCache()
        )
        self._caching = response_cache is not None

        # Unlike the cache, this defaults to *on*: a pipeline that answers
        # "hello" with "I don't know based on the provided document" is
        # not a configuration choice anyone would make deliberately. Pass
        # a responder built with `SmallTalkConfig(enabled=False)` to get
        # the strictly-retrieval behaviour back.
        self.small_talk = small_talk if small_talk is not None else SmallTalkResponder()

        # The stages this service owns directly. Retrieval, reranking,
        # rewriting and summarisation are instrumented by the components
        # that perform them, and nest under whatever trace is open.
        self.tracer = tracer if tracer is not None else Tracer()

    def answer_with_sources(
        self,
        conversation_id: str,
        question: str,
        top_k: int = 5,
        candidate_k: int = 30,
        generator: TextGenerator | None = None,
        model_id: str | None = None,
    ) -> tuple[str, list[RetrievedChunk]]:
        """
        Generate an answer together with the retrieved supporting chunks.

        `generator` overrides the service's default LLM for this call only
        (e.g. a user-selected model), leaving query rewriting and
        summarization on the default. `model_id` names that model for the
        response cache, which must not serve one model's answer as
        another's; the service is handed a generator object and has no
        other way to know which one it is.

        Token accounting is deliberately not a parameter here. It used to be
        an `on_usage` callback, which could only ever report this one call -
        the rewriter, the summariser and the rerank fallback spend tokens
        this service never sees. Wrapping the generators in
        rag.llm.metering.MeteredGenerator reports all of them, so the caller
        opens a `collect_usage()` block instead.
        """

        logger.info(
            "Processing question for conversation '%s'.",
            conversation_id,
        )

        #
        # 1. Conversation memory
        #
        with self.tracer.span(Stage.MEMORY_LOAD) as span:

            memory = self.session_manager.get_memory(conversation_id)

            # Read before the question is written, so this means "this
            # conversation had turns before this one", not "this
            # conversation has turns". Both the rewrite and the decision to
            # cache the answer hang on that distinction.
            has_context = bool(memory.get_summary()) or bool(
                memory.get_recent_messages()
            )

            span.set(
                # Turns since the last summary checkpoint - this is what
                # SUMMARY_TRIGGER counts, not the whole history.
                pending_message_count=len(memory.messages),
                recent_message_count=len(memory.get_recent_messages()),
                has_summary=bool(memory.get_summary()),
            )

        with self.tracer.span(Stage.MEMORY_WRITE, role="user"):

            memory.add_message(
                role="user",
                content=question,
            )

        #
        # 1b. A turn that is not asking the corpus anything
        #
        # Checked on the raw question rather than the rewritten one, and
        # before the rewriter runs: "hi" has nothing to fold conversation
        # history into, and rewriting it would spend an LLM call to
        # produce a query for a search that should never happen.
        #
        # Answered but never cached. There is nothing to save - no
        # retrieval, no generation - and an entry keyed on "hi" would sit
        # in a cache sized for real questions.
        small_talk = self.small_talk.reply_to(question)

        if small_talk is not None:

            logger.info(
                "Answering conversation '%s' as small talk (%s).",
                conversation_id,
                small_talk.intent.value,
            )

            # A span rather than nothing at all, because "answered without
            # retrieving" is exactly the thing an operator wants to be
            # able to separate from "retrieved and found nothing": both
            # produce a trace with no generation span and no sources.
            with self.tracer.span(Stage.SMALL_TALK) as span:

                answer = small_talk.text

                span.set(
                    intent=small_talk.intent.value,
                    answer_chars=len(answer),
                )

            return self._finish(
                memory=memory,
                answer=answer,
                chunks=[],
            )

        #
        # 2. Rewrite query
        #
        # On the opening turn there is nothing to fold in: no summary, no
        # earlier turns, nothing for a pronoun to refer back to. The
        # rewriter could only reword the question, at the price of an LLM
        # call, so it is not asked. No span is emitted either - an absent
        # stage means the work did not happen, which is the truth here.
        if has_context:

            standalone_query = self.query_rewriter.rewrite(
                query=question,
                summary=memory.get_summary(),
                recent_messages=memory.get_recent_messages(),
            )

            logger.info(
                "Rewritten query: %s",
                standalone_query,
            )

        else:

            standalone_query = question

        cache_model_id = model_id or DEFAULT_CACHE_MODEL_ID

        #
        # 2b. An answer this question already has
        #
        # Keyed on the standalone query and never on the raw question: the
        # rewritten form is context-free by construction, and that is the
        # whole reason one conversation's answer can be handed to another.
        lookup = self._lookup(
            query=standalone_query,
            top_k=top_k,
            model_id=cache_model_id,
        )

        if lookup.entry is not None:

            logger.info(
                "Answering conversation '%s' from cache (%s).",
                conversation_id,
                lookup.match,
            )

            # Retrieval, reranking and generation are all skipped; the
            # memory write and the summary check below are not. Skipping
            # those would leave the stored conversation disagreeing with
            # what the user was shown.
            return self._finish(
                memory=memory,
                answer=lookup.entry.answer,
                chunks=lookup.entry.chunks,
            )

        #
        # 3. Retrieve supporting chunks
        #
        chunks = self.query_service.search(
            query=standalone_query,
            top_k=top_k,
            candidate_k=candidate_k,
            use_reranker=True,
            # Spent already, by the semantic tier above. Passing it saves
            # dense retrieval embedding the same text a second time.
            query_embedding=lookup.query_embedding,
        )

        if not chunks:

            answer = "I couldn't find relevant information " "in the documents."

            # Cached like any other answer. It can only go stale when the
            # corpus gains the document that would have answered it, and
            # ingesting one empties the cache.
            self._remember(
                query=standalone_query,
                top_k=top_k,
                model_id=cache_model_id,
                answer=answer,
                chunks=[],
                lookup=lookup,
                has_context=has_context,
            )

            # No generation span is emitted here, deliberately: the absence
            # of one, next to the trace's source_count of 0, is precisely
            # the record that retrieval short-circuited the LLM call.
            return self._finish(memory=memory, answer=answer, chunks=[])

        logger.debug(
            "Retrieved %d supporting chunks.",
            len(chunks),
        )

        #
        # 4. Build prompt
        #
        with self.tracer.span(Stage.CONTEXT_BUILD) as span:

            prompt = PromptBuilder.build_prompt(
                question=question,
                chunks=chunks,
                summary=memory.get_summary(),
                recent_messages=memory.get_recent_messages(),
            )

            # The funnel the spec asks to be able to follow: how many
            # chunks retrieval and reranking settled on, how much text that
            # is, and how much prompt it turned into once the summary and
            # recent turns were added around it.
            span.set(
                chunk_count=len(chunks),
                context_chars=sum(len(chunk.text) for chunk in chunks),
                prompt_chars=len(prompt),
                document_count=len({chunk.metadata.document_id for chunk in chunks}),
            )

        #
        # 5. Generate answer
        #
        with self.tracer.span(Stage.GENERATION) as span:

            response = (generator or self.generator).generate(prompt)

            if not response.text:
                raise ValueError("LLM returned an empty response.")

            answer = response.text

            span.set(
                answer_chars=len(answer),
                **generation_metadata(response),
            )

        #
        # 5b. Remember it
        #
        self._remember(
            query=standalone_query,
            top_k=top_k,
            model_id=cache_model_id,
            answer=answer,
            chunks=chunks,
            lookup=lookup,
            has_context=has_context,
        )

        return self._finish(memory=memory, answer=answer, chunks=chunks)

    def answer(
        self,
        conversation_id: str,
        question: str,
        top_k: int = 5,
        generator: TextGenerator | None = None,
        model_id: str | None = None,
    ) -> str:
        """
        Generate an answer without returning the retrieved chunks.
        """

        answer, _ = self.answer_with_sources(
            conversation_id=conversation_id,
            question=question,
            top_k=top_k,
            generator=generator,
            model_id=model_id,
        )

        return answer

    # ------------------------------------------------------------------
    # Steps 6 and 7, which run whether or not the answer was generated
    # ------------------------------------------------------------------

    def _finish(
        self,
        *,
        memory: Any,
        answer: str,
        chunks: list[RetrievedChunk],
    ) -> tuple[str, list[RetrievedChunk]]:
        """
        Write the assistant turn, and summarise if it is time.
        """

        #
        # 6. Update conversation memory
        #
        with self.tracer.span(Stage.MEMORY_WRITE, role="assistant"):

            memory.add_message(
                role="assistant",
                content=answer,
            )

        #
        # 7. Update conversation summary
        #
        if len(memory.messages) >= self.SUMMARY_TRIGGER:

            logger.debug("Updating conversation summary.")

            summary = self.summarizer.summarize(memory)

            memory.update_summary(summary)

        return answer, chunks

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def _lookup(
        self,
        *,
        query: str,
        top_k: int,
        model_id: str,
    ) -> CacheLookup:
        """
        Consult the cache, recording what it said.

        Returns an empty lookup when no cache is wired up, and emits no
        span for it: nothing ran, so there is nothing to time.
        """

        if not self._caching:
            return CacheLookup()

        with self.tracer.span(
            Stage.CACHE_LOOKUP,
            top_k=top_k,
            model=model_id,
        ) as span:

            lookup = self.response_cache.lookup(
                query=query,
                top_k=top_k,
                model_id=model_id,
            )

            # No query text: span metadata carries numbers and names, and
            # storing questions here would make the telemetry tables a
            # second copy of what the conversation already holds.
            recorded: dict[str, Any] = {
                "hit": lookup.hit,
                "match": lookup.match,
                "entry_count": lookup.entry_count,
            }

            if lookup.similarity is not None:
                recorded["similarity"] = lookup.similarity

            span.set(**recorded)

            return lookup

    def _remember(
        self,
        *,
        query: str,
        top_k: int,
        model_id: str,
        answer: str,
        chunks: list[RetrievedChunk],
        lookup: CacheLookup,
        has_context: bool,
    ) -> None:
        """
        Offer a freshly generated answer to the cache.

        Whether it is kept is the cache's decision rather than this
        service's: `context_free` is the fact it needs, and the policy
        that acts on it sits next to the configuration that sets it.
        """

        if not self._caching:
            return

        self.response_cache.store(
            query=query,
            top_k=top_k,
            model_id=model_id,
            answer=answer,
            chunks=chunks,
            query_embedding=lookup.query_embedding,
            context_free=not has_context,
        )
