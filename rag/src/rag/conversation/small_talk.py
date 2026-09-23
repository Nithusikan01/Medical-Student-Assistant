"""
Turns that carry no information need, answered without retrieval.

A greeting is not a retrieval failure, but a retrieval-grounded pipeline
cannot tell the two apart: "hi" retrieves whichever chunks happen to sit
nearest in the index, the prompt's grounding rule fires on them, and the
first message a user ever sends is answered with "I don't know based on
the provided document." No amount of prompt tuning fixes that - the
pipeline is behaving correctly on a question it should never have been
asked.

So the small, closed set of turns that ask nothing of the corpus is
recognised *before* the query rewriter runs and answered from a canned
reply: no rewrite call, no retrieval, no generation, no cache entry.

Deliberately pattern matching rather than an LLM classifier. The set is
small and closed, an exact match against a normalised *whole* message is
predictable enough to unit test, and a canned reply cannot promise a
capability the application does not have. Anything that is not a whole
message match falls through to the ordinary RAG path untouched - "hi,
what is the pathophysiology of sepsis?" included - which is the safe
direction for this to fail in: a missed greeting costs one clumsy
answer, while a swallowed question costs a real one.
"""

import re
from dataclasses import dataclass
from enum import Enum

from rag.config.component_configs import SmallTalkConfig


class SmallTalkIntent(str, Enum):
    """
    What a non-question turn is doing.

    Separate intents rather than one "small talk" bucket because the
    right reply differs: a greeting should offer help, a thank-you should
    not re-introduce the assistant, and a farewell should say that the
    conversation is kept.
    """

    GREETING = "greeting"
    CHECK_IN = "check_in"
    IDENTITY = "identity"
    THANKS = "thanks"
    ACKNOWLEDGEMENT = "acknowledgement"
    FAREWELL = "farewell"


@dataclass(frozen=True, slots=True)
class SmallTalkReply:
    """
    A recognised turn, and the answer to give for it.
    """

    intent: SmallTalkIntent
    text: str


# ----------------------------------------------------------------------
# Normalisation
# ----------------------------------------------------------------------

# Dropped outright rather than replaced with a space, so "what's" folds
# to "whats" instead of splitting into two tokens.
_APOSTROPHES = re.compile(r"['’`ʼ]")

# Everything else non-alphanumeric becomes a space, which is what makes
# "Hi!!!", "hi...", "hi :)" and "Hi." all the same string.
_PUNCTUATION = re.compile(r"[^a-z0-9\s]+")

_WHITESPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """
    Fold a message to the form the patterns below are written against.
    """

    folded = _APOSTROPHES.sub("", text.casefold())

    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", folded)).strip()


# ----------------------------------------------------------------------
# Patterns
#
# Every one is anchored at both ends and matched against the normalised
# whole message, so the length cap that would otherwise be needed to keep
# real questions out is implicit in the grammar.
# ----------------------------------------------------------------------

_HELLO = (
    r"(?:hi+|hey+|hello+|helo|hiya|yo|howdy|greetings|"
    r"good (?:morning|afternoon|evening|day))"
)

# Who the greeting is aimed at. Harmless on its own, and letting it trail
# a greeting is what makes "hey there" and "hi anamnesis" match.
_ADDRESS = (
    r"(?:there|again|bot|assistant|anamnesis|everyone|all|"
    r"guys|team|mate|doc|sir|maam|madam)"
)

_FILLER = r"(?:ok(?:ay)?|alright|all right)"

_THANKS = (
    r"(?:thanks|thank you|thank u|thankyou|thx|tysm|ty|"
    r"many thanks|much appreciated|appreciate it|appreciated)"
)

_PLEASED = r"(?:great|perfect|cool|nice|awesome|brilliant|excellent|super|lovely)"

# Ordered: the first whole-message match wins, and the two orderings that
# matter are farewell before thanks ("thanks, bye") and thanks before
# acknowledgement ("ok thanks").
_PATTERNS: tuple[tuple[SmallTalkIntent, "re.Pattern[str]"], ...] = (
    (
        SmallTalkIntent.FAREWELL,
        re.compile(
            rf"^(?:(?:{_FILLER}|{_THANKS}|{_PLEASED})\s+)*"
            r"(?:bye+|good ?bye|see you(?:\s+(?:later|soon|tomorrow))?|"
            r"see ya|cya|good ?night|gn|talk to you later|talk later|ttyl|"
            r"catch you later|thats (?:all|it)(?:\s+for now)?|im done|"
            r"that will be all|have a good (?:day|night|one))"
            rf"(?:\s+{_ADDRESS})?$"
        ),
    ),
    (
        SmallTalkIntent.THANKS,
        re.compile(
            rf"^(?:(?:{_FILLER}|{_PLEASED})\s+)*{_THANKS}"
            rf"(?:\s+(?:a lot|so much|a ton|very much|again|{_ADDRESS}))?$"
        ),
    ),
    (
        SmallTalkIntent.IDENTITY,
        re.compile(
            rf"^(?:{_HELLO}\s+)?"
            r"(?:who (?:are|r) (?:you|u)|who is this|what are you|"
            r"what(?: i)?s this|what(?: i)?s anamnesis|"
            r"what(?: i)?s your name|introduce yourself|tell me about yourself|"
            r"what can you do(?:\s+for me)?|what do you do|"
            r"what can you help(?:\s+me)?(?:\s+with)?|"
            r"how can you help(?:\s+me)?(?:\s+with)?|how do you help(?:\s+me)?|"
            r"what can i ask(?:\s+you)?(?:\s+about)?|what should i ask|"
            r"how does this (?:work|app work)|how do i use this|"
            r"help|help me|i need help)$"
        ),
    ),
    (
        SmallTalkIntent.CHECK_IN,
        re.compile(
            rf"^(?:{_HELLO}\s+)?(?:{_ADDRESS}\s+)?"
            r"(?:how (?:are|r) (?:you|u)(?:\s+(?:doing|today|feeling))?|"
            r"hows it going|how is it going|how is everything|"
            r"what(?: i)?s up|wassup|sup|how do you do|"
            r"are you (?:there|ok|okay|alive|working))$"
        ),
    ),
    (
        SmallTalkIntent.GREETING,
        re.compile(rf"^(?:{_FILLER}\s+)?{_HELLO}(?:\s+{_HELLO})?(?:\s+{_ADDRESS})?$"),
    ),
    (
        SmallTalkIntent.ACKNOWLEDGEMENT,
        re.compile(
            rf"^(?:{_FILLER}|{_PLEASED}|k|kk|got it|gotcha|i see|understood|"
            r"makes sense|noted|fine|fair enough|sounds good)$"
        ),
    ),
)

# Echoed back when the user opened with one, so "good evening" is not
# answered with "good morning".
_TIME_OF_DAY = re.compile(r"\bgood (morning|afternoon|evening)\b")


class SmallTalkResponder:
    """
    Recognises conversational turns, and answers them.

    `reply_to` returns None for anything that should be retrieved, which
    is everything this module does not positively recognise.
    """

    def __init__(self, config: SmallTalkConfig | None = None) -> None:
        self.config = config if config is not None else SmallTalkConfig()

    def reply_to(self, message: str) -> SmallTalkReply | None:

        if not self.config.enabled:
            return None

        normalised = normalise(message)

        if not normalised:
            return None

        for intent, pattern in _PATTERNS:

            if pattern.match(normalised):
                return SmallTalkReply(
                    intent=intent,
                    text=self._text(intent, normalised),
                )

        return None

    # ------------------------------------------------------------------
    # Replies
    # ------------------------------------------------------------------

    def _text(self, intent: SmallTalkIntent, normalised: str) -> str:

        if intent is SmallTalkIntent.GREETING:
            return f"{self._salutation(normalised)} {self._introduction()}"

        if intent is SmallTalkIntent.CHECK_IN:
            return f"I'm well, thank you for asking. {self._introduction()}"

        if intent is SmallTalkIntent.IDENTITY:
            return self._who_i_am()

        if intent is SmallTalkIntent.THANKS:
            return (
                "You're very welcome. Ask me anything else from the library "
                "whenever you need it."
            )

        if intent is SmallTalkIntent.FAREWELL:
            return (
                "Goodbye, and good luck with your studies. This conversation "
                "is saved, so you can pick it up again whenever you like."
            )

        return "Of course. Is there anything else you'd like to look up?"

    def _salutation(self, normalised: str) -> str:
        """
        Mirror a time-of-day greeting, or fall back to a neutral one.
        """

        match = _TIME_OF_DAY.search(normalised)

        if match is None:
            return "Hello!"

        return f"Good {match.group(1)}!"

    def _introduction(self) -> str:
        return (
            f"I'm {self.config.assistant_name}, your "
            f"{self.config.corpus_description}. Ask me anything from the "
            "material that has been uploaded - a definition, a concept "
            "you'd like explained, what a guideline says - and I'll answer "
            "from those documents and show you the passages I used.\n\n"
            "What would you like to look up?"
        )

    def _who_i_am(self) -> str:
        return (
            f"I'm {self.config.assistant_name}, your "
            f"{self.config.corpus_description}. I answer from the documents "
            "that have been uploaded here and from nothing else, and every "
            "answer lists the passages it came from so you can check them.\n\n"
            "You can ask me to explain a concept, define a term, summarise a "
            "topic, or find what the material says about something - and you "
            "can keep asking follow-up questions, because I remember the rest "
            "of this conversation.\n\n"
            "If something isn't in the library, I'll tell you so rather than "
            "guess. What are you studying?"
        )
