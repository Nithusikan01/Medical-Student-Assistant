import { useState } from "react";
import { NavLink } from "react-router-dom";

import type { ConversationSummary } from "../types";

interface ConversationSidebarProps {
  conversations: ConversationSummary[];
  activeId: string | null;
  onNew: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}

export function ConversationSidebar({
  conversations,
  activeId,
  onNew,
  onRename,
  onDelete,
}: ConversationSidebarProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");

  const startRename = (conversation: ConversationSummary) => {
    setEditingId(conversation.id);
    setDraftTitle(conversation.title ?? "");
  };

  const commitRename = (id: string) => {
    const title = draftTitle.trim();

    if (title) {
      onRename(id, title);
    }

    setEditingId(null);
  };

  return (
    <div className="conversations">
      <div className="conversations-head">
        <h3>Chats</h3>
        <button type="button" className="secondary small" onClick={onNew}>
          New
        </button>
      </div>

      {conversations.length === 0 && (
        <p className="hint">No conversations yet.</p>
      )}

      <ul className="conversation-list">
        {conversations.map((conversation) => (
          <li
            key={conversation.id}
            className={conversation.id === activeId ? "active" : undefined}
          >
            {editingId === conversation.id ? (
              <input
                className="rename-input"
                value={draftTitle}
                autoFocus
                onChange={(event) => setDraftTitle(event.target.value)}
                onBlur={() => commitRename(conversation.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    commitRename(conversation.id);
                  }
                  if (event.key === "Escape") {
                    setEditingId(null);
                  }
                }}
              />
            ) : (
              <>
                <NavLink to={`/c/${conversation.id}`} className="conversation-link">
                  <span className="conversation-title">
                    {conversation.title ?? "Untitled"}
                  </span>
                  <span className="conversation-meta">
                    {conversation.message_count} message
                    {conversation.message_count === 1 ? "" : "s"}
                  </span>
                </NavLink>

                <span className="conversation-actions">
                  <button
                    type="button"
                    title="Rename"
                    onClick={() => startRename(conversation)}
                  >
                    ✎
                  </button>
                  <button
                    type="button"
                    title="Delete"
                    onClick={() => onDelete(conversation.id)}
                  >
                    ✕
                  </button>
                </span>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
