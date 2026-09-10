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
import { useConversation } from "../hooks/useConversation";
import type { ConversationSummary } from "../types";

export function ChatPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { conversationId = null } = useParams<{ conversationId: string }>();

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [topK, setTopK] = useState(5);
  const [online, setOnline] = useState<boolean | null>(null);

  const { messages, pending, loading, error, ask } =
    useConversation(conversationId);

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

  return (
    <div className="app">
      <aside className="sidebar">
        <header className="brand">
          <h1>Medical Student Assistant</h1>
          <p className="tagline">Retrieval-grounded answers over the library</p>
        </header>

        <div className="status">
          <span
            className={`dot ${
              online === null
                ? "dot-unknown"
                : online
                  ? "dot-online"
                  : "dot-offline"
            }`}
          />
          {online === null
            ? "Checking API…"
            : online
              ? "API connected"
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
          <h3>Account</h3>
          <p className="account-email" title={user?.email}>
            {user?.email}
          </p>
          {user?.role === "admin" && (
            <Link to="/admin/documents" className="admin-link">
              Manage documents
            </Link>
          )}
          <button
            type="button"
            className="secondary"
            onClick={() => void logout()}
          >
            Sign out
          </button>
        </div>
      </aside>

      <ChatPanel
        messages={messages}
        pending={pending}
        loading={loading}
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
