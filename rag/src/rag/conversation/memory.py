from rag.conversation.schemas import ChatMessage


class ConversationMemory:
    """
    One conversation's history, as the RAG service sees it.

    Two views, deliberately separate:

    - `messages` holds only the turns since the last summary. It is what
      the service counts against its summary trigger, and what the
      summariser folds into the next summary - so every turn reaches the
      summary exactly once.
    - `get_recent_messages()` is a fixed-size window over the *whole*
      history, unaffected by summarising. It is what goes into prompts, so
      a summary never leaves the model without the last few turns.

    `update_summary` empties `messages`. If it did not, the trigger would
    stay true from the trigger length onwards and summarise on every turn.

    Subclasses that persist history (the backend's database-backed memory)
    keep these semantics and add storage around them.
    """

    def __init__(self, max_recent_messages: int = 6):
        self.messages: list[ChatMessage] = []
        self.summary: str = ""
        self.max_recent_messages = max_recent_messages
        self._recent: list[ChatMessage] = []

    def add_message(self, role: str, content: str) -> None:
        message = ChatMessage(role=role, content=content)

        self.messages.append(message)
        self._recent = (self._recent + [message])[-self.max_recent_messages :]

    def get_recent_messages(self) -> list[ChatMessage]:
        return list(self._recent)

    def get_summary(self) -> str:
        return self.summary

    def update_summary(self, summary: str) -> None:
        self.summary = summary

        # Everything pending is now represented by the summary.
        self.messages = []
