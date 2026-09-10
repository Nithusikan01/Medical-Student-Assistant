import { useEffect, useRef, useState } from "react";

import type { ChatMessage } from "../hooks/useConversation";
import { SourceList } from "./SourceList";

interface ChatPanelProps {
  messages: ChatMessage[];
  pending: boolean;
  error: string | null;
  topK: number;
  onTopKChange: (value: number) => void;
  onSend: (question: string) => void;
}

export function ChatPanel({
  messages,
  pending,
  error,
  topK,
  onTopKChange,
  onSend,
}: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, pending]);

  const submit = () => {
    const question = draft.trim();

    if (question.length === 0 || pending) {
      return;
    }

    onSend(question);
    setDraft("");
  };

  return (
    <section className="chat">
      <div className="messages">
        {messages.length === 0 && !pending && (
          <div className="empty">
            <h2>Ask about your documents</h2>
            <p>
              Upload a PDF, then ask a question. Every answer is grounded in the
              retrieved chunks listed beneath it.
            </p>
          </div>
        )}

        {messages.map((message) => (
          <article key={message.id} className={`message message-${message.role}`}>
            <div className="message-role">
              {message.role === "user" ? "You" : "Assistant"}
            </div>

            <div className="message-body">{message.content}</div>

            {message.sources && <SourceList sources={message.sources} />}
          </article>
        ))}

        {pending && (
          <article className="message message-assistant">
            <div className="message-role">Assistant</div>
            <div className="message-body thinking">Retrieving and generating…</div>
          </article>
        )}

        {error && <div className="error">{error}</div>}

        <div ref={endRef} />
      </div>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <textarea
          value={draft}
          rows={3}
          placeholder="Ask a question about the ingested documents…"
          disabled={pending}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />

        <div className="composer-actions">
          <label className="top-k">
            Sources
            <input
              type="number"
              min={1}
              max={20}
              value={topK}
              onChange={(event) => onTopKChange(Number(event.target.value))}
            />
          </label>

          <button type="submit" disabled={pending || draft.trim().length === 0}>
            {pending ? "Asking…" : "Ask"}
          </button>
        </div>
      </form>
    </section>
  );
}
