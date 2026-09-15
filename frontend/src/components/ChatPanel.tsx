import { useEffect, useRef, useState } from "react";

import type { ChatMessage } from "../hooks/useConversation";
import type { GenerationModelInfo } from "../types";
import { Send, Spinner } from "./Icons";
import { SourceList } from "./SourceList";

interface ChatPanelProps {
  messages: ChatMessage[];
  pending: boolean;
  loading?: boolean;
  error: string | null;
  topK: number;
  onTopKChange: (value: number) => void;
  showTopK: boolean;
  models: GenerationModelInfo[];
  selectedModel: string | null;
  onModelChange: (id: string) => void;
  onSend: (question: string) => void;
}

export function ChatPanel({
  messages,
  pending,
  loading = false,
  error,
  topK,
  onTopKChange,
  showTopK,
  models,
  selectedModel,
  onModelChange,
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
    <>
      <div className="messages">
        {loading && (
          <div className="thinking">
            <Spinner />
            Loading conversation…
          </div>
        )}

        {messages.length === 0 && !pending && !loading && (
          <div className="empty">
            <h2>Ask about the library</h2>
            <p>
              Every answer is grounded in the retrieved passages listed beneath
              it, so you can check the source before you trust it.
            </p>
          </div>
        )}

        {messages.map((message) =>
          message.role === "user" ? (
            <div key={message.id} className="message-user">
              {message.content}
            </div>
          ) : (
            <article key={message.id} className="message-assistant">
              {message.model && (
                <span className="message-model">
                  {models.find((option) => option.id === message.model)
                    ?.label ?? message.model}
                </span>
              )}
              <p className="message-body">{message.content}</p>
              {message.sources && <SourceList sources={message.sources} />}
            </article>
          ),
        )}

        {pending && (
          <article className="message-assistant">
            <div className="thinking">
              <Spinner />
              Retrieving and generating…
            </div>
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
          rows={2}
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
          <label className="model-select">
            Model
            <select
              value={selectedModel ?? ""}
              disabled={models.length === 0}
              onChange={(event) => onModelChange(event.target.value)}
            >
              {models.length === 0 && <option value="">Default</option>}
              {models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.label}
                </option>
              ))}
            </select>
          </label>

          {showTopK && (
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
          )}

          <span className="composer-hint">
            Enter to send · Shift+Enter for a new line
          </span>

          <button
            type="submit"
            className="btn"
            disabled={pending || draft.trim().length === 0}
          >
            <Send />
            {pending ? "Asking…" : "Ask"}
          </button>
        </div>
      </form>
    </>
  );
}
