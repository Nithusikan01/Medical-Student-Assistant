import hashlib
import re

from rag.cache.schemas import CacheScope

_WHITESPACE = re.compile(r"\s+")

# Stripped from both ends only. Punctuation *inside* a question can change
# its meaning, so this deliberately does not remove it everywhere.
_TRIMMED = " \t\r\n.?!,;:\"'`-"


def normalize_question(text: str) -> str:
    """
    Reduce a question to the form the exact tier compares.

    Only differences that cannot change the answer are erased: casing,
    runs of whitespace, and trailing punctuation. "What is the dose?" and
    "what is the dose" are the same question; "what is the dose" and "what
    is not the dose" are not, and nothing here is clever enough to think
    otherwise.
    """

    collapsed = _WHITESPACE.sub(" ", text.casefold())

    return collapsed.strip(_TRIMMED)


def question_hash(text: str) -> str:
    return hashlib.sha256(normalize_question(text).encode("utf-8")).hexdigest()


def scope_for(*, query: str, top_k: int, model_id: str) -> CacheScope:
    return CacheScope(
        query_hash=question_hash(query),
        top_k=top_k,
        model_id=model_id,
    )
