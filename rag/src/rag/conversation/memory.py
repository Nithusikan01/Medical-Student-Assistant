from rag.conversation.schemas import ChatMessage


class ConversationMemory:
    """
    Two views of one conversation, kept apart on purpose.

    `messages` holds the turns since the last summary. It is what
    HistoryAwareRAGService counts against SUMMARY_TRIGGER, and what the
    summarizer folds into the summary; `update_summary` empties it, because
    those turns are now represented by the summary.

    The recent window holds the last `max_recent_messages` turns of the
    whole conversation, and is what goes into prompts. It survives a
    summary, so the turn just before the checkpoint is still context for
    the next question.

    The two used to be one list. Summarising then saw only the window - the
    last 6 of the 12 turns that triggered it - and the other 6 never reached
    the summary; and because nothing emptied the list, every turn after the
    twelfth summarised again.
    """

    def __init__(self, max_recent_messages: int = 6):
        self.messages: list[ChatMessage] = []
        self.summary: str = ""
        self.max_recent_messages = max_recent_messages
        self._recent: list[ChatMessage] = []

    def add_message(self, role: str, content: str):
        message = ChatMessage(role=role, content=content)

        self.messages.append(message)
        self._recent = self._window(self._recent + [message])

    def get_recent_messages(self) -> list[ChatMessage]:
        return list(self._recent)

    def get_summary(self):
        return self.summary

    def update_summary(self, summary: str):
        self.summary = summary
        self.messages = []

    def _window(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        # A slice of [-0:] is the whole list, not an empty one.
        if self.max_recent_messages <= 0:
            return []

        return messages[-self.max_recent_messages :]
