from collections.abc import Mapping
from dataclasses import dataclass

from rag.config.component_configs import (
    CacheConfig,
    ChunkingConfig,
    ConversationConfig,
    EmbeddingConfig,
    GenerationConfig,
    PineconeConfig,
    PineconeEmbeddingConfig,
    PineconeRerankConfig,
    PromptConfig,
    RetrievalConfig,
    ScopeConfig,
    SmallTalkConfig,
)


@dataclass(frozen=True)
class Settings:
    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------
    pinecone_api_key: str
    pinecone_index_name: str
    gemini_api_key: str
    # Optional: enables the Groq-backed generation models. Left empty, those
    # models are simply not offered rather than the app failing to start.
    groq_api_key: str = ""

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------
    chunk_size: int = 500
    chunk_overlap: int = 50

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_batch_size: int = 32

    # ------------------------------------------------------------------
    # Hosted inference (Pinecone)
    #
    # When enabled, embedding and reranking run through Pinecone's API and
    # no model weights are downloaded. The embedding dimension is fixed by
    # the hosted model, so the index must be created to match it.
    # ------------------------------------------------------------------
    use_hosted_inference: bool = True
    hosted_embedding_model: str = "llama-text-embed-v2"
    hosted_embedding_dimension: int = 1024
    hosted_rerank_model: str = "bge-reranker-v2-m3"

    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    candidate_k: int = 30
    rrf_k: int = 60

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------
    summary_trigger: int = 12
    max_recent_messages: int = 6

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    generation_model_name: str = "gemini-3.1-flash-lite"

    # ------------------------------------------------------------------
    # Response cache
    #
    # Answers already given, keyed on the standalone form of the question,
    # so a class asking the same things does not pay for retrieval and
    # generation every time. Invalidated whenever the corpus changes.
    # ------------------------------------------------------------------
    response_cache_enabled: bool = True
    response_cache_semantic_enabled: bool = True
    response_cache_max_entries: int = 512
    response_cache_ttl_seconds: int = 86_400
    response_cache_similarity_threshold: float = 0.95
    response_cache_store_context_free_only: bool = True

    # ------------------------------------------------------------------
    # Small talk
    #
    # Greetings and thank-yous answered without retrieval, so the
    # grounding rule in the prompt never fires on a turn that was not
    # asking the corpus anything.
    # ------------------------------------------------------------------
    small_talk_enabled: bool = True
    assistant_name: str = "Anamnesis"
    # "I'm <name>, your <description>. <purpose>" - every self-introduction
    # (greetings, "who are you", the scope guard's reply) is built from these.
    assistant_description: str = "medical study assistant"
    assistant_purpose: str = (
        "I help medical students learn their course material and prepare " "for exams."
    )

    # ------------------------------------------------------------------
    # Prompt
    #
    # What the documents are, as a noun phrase completing "questions
    # about ...". The engine itself is domain-free.
    # ------------------------------------------------------------------
    corpus_description: str = "the course material in the class library"

    # ------------------------------------------------------------------
    # Scope
    #
    # Questions clearly unrelated to the subject are declined before any
    # retrieval, with a reply saying what the assistant is for.
    # ------------------------------------------------------------------
    scope_guard_enabled: bool = True
    scope_subject: str = "medicine and the health sciences"
    scope_examples: str = (
        "anatomy, physiology, biochemistry, pathology, microbiology, "
        "pharmacology, clinical medicine and surgery, public health, "
        "medical ethics and research methods"
    )
    # Empty means composed from the assistant's name, description and
    # purpose (see scope_config), so it introduces the assistant the same
    # way the greeting does.
    scope_refusal: str = ""

    # ------------------------------------------------------------------
    # Component Configurations
    # ------------------------------------------------------------------
    def pinecone_config(self) -> PineconeConfig:
        return PineconeConfig(
            api_key=self.pinecone_api_key,
            index_name=self.pinecone_index_name,
            cloud=self.pinecone_cloud,
            region=self.pinecone_region,
        )

    def embedding_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            model_name=self.embedding_model_name,
            batch_size=self.embedding_batch_size,
        )

    def hosted_embedding_config(self) -> PineconeEmbeddingConfig:
        return PineconeEmbeddingConfig(
            api_key=self.pinecone_api_key,
            model_name=self.hosted_embedding_model,
            dimension=self.hosted_embedding_dimension,
        )

    def hosted_rerank_config(self) -> PineconeRerankConfig:
        return PineconeRerankConfig(
            api_key=self.pinecone_api_key,
            model_name=self.hosted_rerank_model,
        )

    def generation_config(self) -> GenerationConfig:
        return GenerationConfig(
            model_name=self.generation_model_name,
            api_key=self.gemini_api_key,
        )

    def chunking_config(self) -> ChunkingConfig:
        return ChunkingConfig(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

    def cache_config(self) -> CacheConfig:
        return CacheConfig(
            enabled=self.response_cache_enabled,
            semantic_enabled=self.response_cache_semantic_enabled,
            max_entries=self.response_cache_max_entries,
            ttl_seconds=self.response_cache_ttl_seconds,
            similarity_threshold=self.response_cache_similarity_threshold,
            store_context_free_only=self.response_cache_store_context_free_only,
        )

    def small_talk_config(self) -> SmallTalkConfig:
        return SmallTalkConfig(
            enabled=self.small_talk_enabled,
            assistant_name=self.assistant_name,
            corpus_description=self.assistant_description,
            purpose=self.assistant_purpose,
            # The same subject the scope guard answers, so the greeting
            # never invites a question the guard would then decline.
            topics=self.scope_subject,
            examples=(
                "a condition, a drug, a mechanism, a guideline or a topic "
                "for a medical exam"
            ),
        )

    def prompt_config(self) -> PromptConfig:
        return PromptConfig(corpus_description=self.corpus_description)

    def scope_config(self) -> ScopeConfig:
        return ScopeConfig(
            enabled=self.scope_guard_enabled,
            subject=self.scope_subject,
            in_scope_examples=self.scope_examples,
            refusal_text=self.scope_refusal or self._default_scope_refusal(),
        )

    def _default_scope_refusal(self) -> str:
        return (
            # Opens with an apology: this is the one reply that turns a
            # student's request down.
            "Apologies for the inconvenience - I'm not able to help with that "
            f"question. I'm {self.assistant_name}, your "
            f"{self.assistant_description}. "
            # Names the subject outright rather than "your course": the app
            # is open to anyone who registers, and a student of another
            # field would read "your course" as their own.
            f"{self.assistant_purpose} I can only answer questions about "
            f"{self.scope_subject}. Please feel free to ask a medical question "
            "instead - for example about a condition, a drug, a mechanism or "
            "a medical exam topic - and I'll gladly answer it from the class "
            "library."
        )

    def retrieval_config(self) -> RetrievalConfig:
        return RetrievalConfig(
            candidate_k=self.candidate_k,
            rrf_k=self.rrf_k,
        )

    def conversation_config(self) -> ConversationConfig:
        return ConversationConfig(
            summary_trigger=self.summary_trigger,
            max_recent_messages=self.max_recent_messages,
        )


def _bool(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)

    if raw is None:
        return default

    return raw.strip().lower() in {"1", "true", "yes", "on"}


def settings_from_mapping(values: Mapping[str, str]) -> Settings:
    """
    Build Settings from a mapping of configuration names to strings.

    The engine never reads the process environment itself: where
    configuration comes from is the application's decision. The backend
    passes os.environ; a test passes a dict.
    """

    pinecone_api_key = values.get("PINECONE_API_KEY")
    pinecone_index_name = values.get("PINECONE_INDEX_NAME")
    gemini_api_key = values.get("GEMINI_API_KEY")
    groq_api_key = values.get("GROQ_API_KEY", "")

    if not pinecone_api_key:
        raise ValueError("PINECONE_API_KEY is not set.")

    if not pinecone_index_name:
        raise ValueError("PINECONE_INDEX_NAME is not set.")

    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not set.")

    return Settings(
        pinecone_api_key=pinecone_api_key,
        pinecone_index_name=pinecone_index_name,
        gemini_api_key=gemini_api_key,
        groq_api_key=groq_api_key,
        chunk_size=int(values.get("CHUNK_SIZE", "500")),
        chunk_overlap=int(values.get("CHUNK_OVERLAP", "50")),
        embedding_batch_size=int(values.get("EMBEDDING_BATCH_SIZE", "32")),
        pinecone_cloud=values.get("PINECONE_CLOUD", "aws"),
        pinecone_region=values.get("PINECONE_REGION", "us-east-1"),
        candidate_k=int(values.get("CANDIDATE_K", "30")),
        rrf_k=int(values.get("RRF_K", "60")),
        summary_trigger=int(values.get("SUMMARY_TRIGGER", "12")),
        max_recent_messages=int(values.get("MAX_RECENT_MESSAGES", "6")),
        embedding_model_name=values.get(
            "EMBEDDING_MODEL_NAME",
            "sentence-transformers/all-MiniLM-L6-v2",
        ),
        generation_model_name=values.get(
            "GENERATION_MODEL_NAME",
            "gemini-3.1-flash-lite",
        ),
        use_hosted_inference=_bool(values, "USE_HOSTED_INFERENCE", True),
        hosted_embedding_model=values.get(
            "HOSTED_EMBEDDING_MODEL",
            "llama-text-embed-v2",
        ),
        hosted_embedding_dimension=int(
            values.get("HOSTED_EMBEDDING_DIMENSION", "1024")
        ),
        hosted_rerank_model=values.get(
            "HOSTED_RERANK_MODEL",
            "bge-reranker-v2-m3",
        ),
        response_cache_enabled=_bool(values, "RESPONSE_CACHE_ENABLED", True),
        response_cache_semantic_enabled=_bool(
            values,
            "RESPONSE_CACHE_SEMANTIC_ENABLED",
            True,
        ),
        response_cache_max_entries=int(values.get("RESPONSE_CACHE_MAX_ENTRIES", "512")),
        response_cache_ttl_seconds=int(
            values.get("RESPONSE_CACHE_TTL_SECONDS", "86400")
        ),
        response_cache_similarity_threshold=float(
            values.get("RESPONSE_CACHE_SIMILARITY_THRESHOLD", "0.95")
        ),
        response_cache_store_context_free_only=_bool(
            values,
            "RESPONSE_CACHE_STORE_CONTEXT_FREE_ONLY",
            True,
        ),
        small_talk_enabled=_bool(values, "SMALL_TALK_ENABLED", True),
        assistant_name=values.get("ASSISTANT_NAME", "Anamnesis"),
        assistant_description=values.get(
            "ASSISTANT_DESCRIPTION", Settings.assistant_description
        ),
        assistant_purpose=values.get("ASSISTANT_PURPOSE", Settings.assistant_purpose),
        corpus_description=values.get(
            "CORPUS_DESCRIPTION",
            "the course material in the class library",
        ),
        scope_guard_enabled=_bool(values, "SCOPE_GUARD_ENABLED", True),
        scope_subject=values.get("SCOPE_SUBJECT", Settings.scope_subject),
        scope_examples=values.get("SCOPE_EXAMPLES", Settings.scope_examples),
        scope_refusal=values.get("SCOPE_REFUSAL", Settings.scope_refusal),
    )
