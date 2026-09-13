from rag.conversation.memory import ConversationMemory


class SessionManager:
    def __init__(self):
        self.sessions: dict[str, ConversationMemory] = {}

    def get_memory(self, conversation_id: str):
        if conversation_id not in self.sessions:
            self.sessions[conversation_id] = ConversationMemory()
        return self.sessions[conversation_id]
