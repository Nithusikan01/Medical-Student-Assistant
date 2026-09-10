import { useCallback, useEffect, useState } from "react";

import { checkHealth } from "./api/client";
import { ChatPanel } from "./components/ChatPanel";
import { UploadPanel } from "./components/UploadPanel";
import { useConversation } from "./hooks/useConversation";

export default function App() {
  const { conversationId, messages, pending, error, ask, reset } =
    useConversation();

  const [topK, setTopK] = useState(5);
  const [online, setOnline] = useState<boolean | null>(null);

  const refreshHealth = useCallback(() => {
    void checkHealth().then(setOnline);
  }, []);

  useEffect(() => {
    refreshHealth();
  }, [refreshHealth]);

  return (
    <div className="app">
      <aside className="sidebar">
        <header className="brand">
          <h1>Medical Student Assistant</h1>
          <p className="tagline">Retrieval-grounded answers over your PDFs</p>
        </header>

        <div className="status">
          <span
            className={`dot ${online === null ? "dot-unknown" : online ? "dot-online" : "dot-offline"}`}
          />
          {online === null
            ? "Checking API…"
            : online
              ? "API connected"
              : "API unreachable"}
        </div>

        <UploadPanel onIngested={refreshHealth} />

        <div className="conversation">
          <h3>Conversation</h3>
          <p className="conversation-id" title={conversationId}>
            {conversationId.slice(0, 8)}
          </p>
          <button type="button" className="secondary" onClick={reset}>
            New conversation
          </button>
          <p className="hint">
            Follow-up questions reuse this id, so the backend rewrites them into
            standalone queries using the conversation history.
          </p>
        </div>
      </aside>

      <ChatPanel
        messages={messages}
        pending={pending}
        error={error}
        topK={topK}
        onTopKChange={(value) =>
          setTopK(Number.isFinite(value) ? Math.min(20, Math.max(1, value)) : 5)
        }
        onSend={(question) => void ask(question, topK)}
      />
    </div>
  );
}
