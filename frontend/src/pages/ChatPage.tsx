import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { checkHealth } from "../api/client";
import {
  createConversation,
  deleteConversation,
  listConversations,
  renameConversation,
} from "../api/conversations";
import { useAuth } from "../auth/useAuth";
import { ChatPanel } from "../components/ChatPanel";
import { ConversationSidebar } from "../components/ConversationSidebar";
import { BookMark, Gauge, SignOut } from "../components/Icons";
import { ThemeToggle } from "../components/ThemeToggle";
import { useConversation } from "../hooks/useConversation";
import { useGenerationModels } from "../hooks/useGenerationModels";
import type { ConversationSummary } from "../types";

export function ChatPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { conversationId = null } = useParams<{ conversationId: string }>();

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [topK, setTopK] = useState(5);
  const [online, setOnline] = useState<boolean | null>(null);

  const { messages, pending, loading, error, ask, rate } =
    useConversation(conversationId);
  const { models, selectedModel, selectModel } = useGenerationModels();

  const refreshConversations = useCallback(async () => {
    const rows = await listConversations().catch(() => []);
    setConversations(rows);
    return rows;
  }, []);

  useEffect(() => {
    void checkHealth().then(setOnline);
  }, []);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations, messages.length]);

  // Land on a usable conversation: the newest one, or a fresh one.
  useEffect(() => {
    if (conversationId) {
      return;
    }

    let cancelled = false;

    const pick = async () => {
      const rows = await refreshConversations();

      if (cancelled) {
        return;
      }

      if (rows.length > 0) {
        navigate(`/c/${rows[0].id}`, { replace: true });
      } else {
        const created = await createConversation();
        if (!cancelled) {
          navigate(`/c/${created.id}`, { replace: true });
        }
      }
    };

    void pick();

    return () => {
      cancelled = true;
    };
  }, [conversationId, navigate, refreshConversations]);

  const startNew = async () => {
    const created = await createConversation();
    await refreshConversations();
    navigate(`/c/${created.id}`);
  };

  const rename = async (id: string, title: string) => {
    await renameConversation(id, title);
    await refreshConversations();
  };

  const remove = async (id: string) => {
    await deleteConversation(id);
    const rows = await refreshConversations();

    if (id === conversationId) {
      navigate(rows.length > 0 ? `/c/${rows[0].id}` : "/", { replace: true });
    }
  };

  const active = conversations.find(
    (conversation) => conversation.id === conversationId,
  );

  return (
    <div className="app">
      <aside className="sidebar">
        <span className="wordmark">
          <BookMark />
          Anamnesis
        </span>

        <div className="status">
          <span
            className={`dot ${
              online === null
                ? ""
                : online
                  ? "dot-online"
                  : "dot-offline"
            }`}
          />
          {online === null
            ? "Checking…"
            : online
              ? "Connected"
              : "API unreachable"}
        </div>

        <ConversationSidebar
          conversations={conversations}
          activeId={conversationId}
          onNew={() => void startNew()}
          onRename={(id, title) => void rename(id, title)}
          onDelete={(id) => void remove(id)}
        />

        <div className="account">
          <div className="account-row">
            <span className="avatar">
              {(user?.email ?? "?").charAt(0).toUpperCase()}
            </span>
            <span className="account-email" title={user?.email}>
              {user?.email}
            </span>
          </div>

          {/* Points at the dashboard rather than the library: the page that
              says whether anything is broken should not be one click deeper
              than the page that does not. The dashboard links onward to the
              library, users and the trace explorer. */}
          {user?.role === "admin" && (
            <Link to="/admin/monitoring" className="admin-link">
              <Gauge />
              Admin dashboard
            </Link>
          )}

          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => void logout()}
          >
            <SignOut />
            Sign out
          </button>
        </div>
      </aside>

      <div className="chat">
        <div className="chat-head">
          <span className="chat-title">
            {active?.title ?? "New conversation"}
          </span>
          <ThemeToggle compact />
        </div>

        <ChatPanel
          onRate={rate}
          messages={messages}
          pending={pending}
          loading={loading}
          error={error}
          topK={topK}
          onTopKChange={(value) =>
            setTopK(
              Number.isFinite(value) ? Math.min(20, Math.max(1, value)) : 5,
            )
          }
          showTopK={user?.role === "admin"}
          models={models}
          selectedModel={selectedModel}
          onModelChange={selectModel}
          onSend={(question) => void ask(question, topK, selectedModel)}
        />
      </div>
    </div>
  );
}
