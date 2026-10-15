from dataclasses import dataclass


@dataclass(frozen=True)
class PineconeConfig:
    api_key: str
    index_name: str
    # Where a missing index is created. Only read by ensure_index().
    cloud: str = "aws"
    region: str = "us-east-1"


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str
    batch_size: int = 32


@dataclass(frozen=True)
class PineconeEmbeddingConfig:
    api_key: str
    model_name: str
    # Fixed by the hosted model; the Pinecone index must be created to match.
    dimension: int


@dataclass(frozen=True)
class PineconeRerankConfig:
    api_key: str
    model_name: str


@dataclass(frozen=True)
class GenerationConfig:
    model_name: str
    api_key: str


@dataclass(frozen=True)
class ChunkingConfig:
    chunk_size: int
    chunk_overlap: int


@dataclass(frozen=True)
class RetrievalConfig:
    """
    How wide retrieval casts its net before reranking narrows it.

    The final number of sources is not here: it is `top_k` on each request,
    because the caller chooses it.
    """

    # Chunks each retriever returns, and the pool the reranker scores.
    candidate_k: int = 30
    # Reciprocal Rank Fusion constant used by HybridRetriever.
    rrf_k: int = 60


@dataclass(frozen=True)
class ConversationConfig:
    # Pending turns (since the last summary) that trigger a new summary.
    summary_trigger: int = 12
    # Most recent turns included verbatim in prompts.
    max_recent_messages: int = 6


@dataclass(frozen=True)
class CacheConfig:
    """
    Bounds for the response cache.

    `store_context_free_only` is the correctness control rather than a
    tuning knob: an answer generated with conversation history in its
    prompt can refer back to that conversation, and serving it to someone
    else would be wrong. Left on, only answers generated with no history
    are ever stored, and every entry is safe to serve to anyone.
    """

    enabled: bool = True
    semantic_enabled: bool = True
    max_entries: int = 512
    ttl_seconds: int = 86_400
    # Deliberately high. Serving the answer to a *nearly* identical
    # question is worse than missing, and this corpus is study material.
    similarity_threshold: float = 0.95
    store_context_free_only: bool = True


@dataclass(frozen=True)
class SmallTalkConfig:
    """
    How the assistant introduces itself when there is nothing to retrieve.

    `enabled` turns the whole short-circuit off, which sends greetings
    back down the retrieval path - the behaviour it exists to replace,
    kept reachable because it is the strictly grounded one.
    """

    enabled: bool = True
    assistant_name: str = "Anamnesis"
    # What the assistant is, as a noun phrase completing "I'm <name>, your
    # ...". Deployment-specific: another class uploads other material.
    corpus_description: str = "study assistant for the class library"
    # Who it helps and with what, as one sentence. Said right after the
    # name in every self-introduction, and in the scope guard's reply.
    purpose: str = "I help you study and revise."
    # What the greeting invites questions about, completing "Ask me
    # anything about ... from the class library", and examples of such
    # questions. The application names its subject so the greeting and the
    # scope guard's reply describe the same thing.
    topics: str = "the course material"
    examples: str = (
        "a definition, a concept you'd like explained, what a guideline says"
    )


@dataclass(frozen=True)
class PromptConfig:
    """
    The deployment-specific wording of the answer prompt.

    The engine knows nothing about what its documents are; the application
    says so here, and every prompt that needs it reads it from one place.
    """

    # Completes "questions about ...", so a noun phrase.
    corpus_description: str = "the course material in the class library"

    # What the model is told to reply, verbatim, when the context does not
    # support an answer.
    no_answer_text: str = "I don't know based on the provided documents."

    # What the service answers, without calling the model, when retrieval
    # returned nothing at all.
    no_context_answer: str = "I couldn't find relevant information in the documents."


@dataclass(frozen=True)
class ScopeConfig:
    """
    What the assistant is for, and what it says to a question that is not.

    The defaults describe no particular subject; the application names its
    own (see Settings, SCOPE_SUBJECT and friends). `enabled=False` answers
    every question, off-topic ones included, as before.
    """

    enabled: bool = True

    # Completes "a study assistant for ..." and "questions about ...".
    subject: str = "the subjects of the course material"

    # Optional "including ..." list, so a narrow subject name does not make
    # the classifier decline a neighbouring field the course covers.
    in_scope_examples: str = ""

    refusal_text: str = (
        "That question is outside what I can help with. I'm here for the "
        "subjects in your course material, so try asking about a topic "
        "from your studies."
    )
