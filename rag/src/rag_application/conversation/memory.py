from typing import List

from rag_application.conversation.schemas import ChatMessage


class ConversationMemory:

    def __init__(self, max_recent_messages: int = 6):
        self.messages: List[ChatMessage] = []
        self.summary: str = ""
        self.max_recent_messages = max_recent_messages

    def add_message(self, role: str, content: str):
        self.messages.append(ChatMessage(role=role, content=content))

    def get_recent_messages(self):
        return self.messages[-self.max_recent_messages:]

    def get_summary(self):
        return self.summary

    def update_summary(self, summary: str):
        self.summary = summary