import { useState } from "react";
import { NavLink } from "react-router-dom";

import type { ConversationSummary } from "../types";
import { Pencil, Plus, Trash } from "./Icons";

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
    <>
      <button type="button" className="btn btn-secondary" onClick={onNew}>
        <Plus />
        New chat
      </button>

      <div className="conversations">
        <span className="eyebrow" style={{ padding: "0 4px" }}>
          Recent
        </span>

        {conversations.length === 0 && (
          <p className="field-hint" style={{ padding: "0 4px" }}>
            No conversations yet.
          </p>
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
                  <NavLink
                    to={`/c/${conversation.id}`}
                    className="conversation-link"
                  >
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
                      className="icon-button"
                      title="Rename"
                      aria-label="Rename conversation"
                      onClick={() => startRename(conversation)}
                    >
                      <Pencil />
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      title="Delete"
                      aria-label="Delete conversation"
                      onClick={() => onDelete(conversation.id)}
                    >
                      <Trash />
                    </button>
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
