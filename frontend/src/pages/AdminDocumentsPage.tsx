import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  deleteDocument,
  listDocuments,
  uploadDocument,
} from "../api/documents";
import { deleteUser, listUsers, updateUserRole } from "../api/users";
import { useAuth } from "../auth/useAuth";
import {
  ArrowLeft,
  Document,
  Spinner,
  Trash,
  Upload,
  Users,
} from "../components/Icons";
import { ThemeToggle } from "../components/ThemeToggle";
import type { AdminUserSummary, DocumentSummary } from "../types";

function formatSize(bytes: number | null): string {
  if (bytes === null) {
    return "—";
  }

  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function AdminDocumentsPage() {
  const { user: currentUser } = useAuth();

  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [uploading, setUploading] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [usersError, setUsersError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDocuments(await listDocuments());
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not load documents.",
      );
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    listUsers()
      .then(setUsers)
      .catch((caught) => {
        setUsersError(
          caught instanceof Error ? caught.message : "Could not load users.",
        );
      });
  }, []);

  const upload = async (file: File) => {
    setError(null);
    setMessage(null);
    setUploading(file.name);

    try {
      const response = await uploadDocument(file);
      setMessage(`${response.filename} added to the library.`);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed.");
    } finally {
      setUploading(null);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    }
  };

  const remove = async (document: DocumentSummary) => {
    const confirmed = window.confirm(
      `Delete "${document.filename}"? Its passages will be removed and it ` +
        `will stop appearing in answers.`,
    );

    if (!confirmed) {
      return;
    }

    setError(null);
    setMessage(null);

    try {
      await deleteDocument(document.id);
      setMessage(`${document.filename} deleted.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Delete failed.");
    } finally {
      await refresh();
    }
  };

  const removeUser = async (target: AdminUserSummary) => {
    setUsersError(null);

    // Deleting an admin needs a stronger confirmation than a plain OK/Cancel
    // - typing the email back proves intent rather than a reflex click.
    if (target.role === "admin") {
      const typed = window.prompt(
        `This permanently deletes the admin account "${target.email}", ` +
          `including their conversations. This cannot be undone.\n\n` +
          `Type their email to confirm.`,
      );

      if (typed === null) {
        return;
      }

      if (typed.trim().toLowerCase() !== target.email.toLowerCase()) {
        setUsersError("Email did not match - nothing was deleted.");
        return;
      }
    } else if (
      !window.confirm(
        `Delete ${target.email}? Their conversations go with them. This cannot be undone.`,
      )
    ) {
      return;
    }

    try {
      await deleteUser(target.id, { confirm: target.role === "admin" });
      setUsers((previous) => previous.filter((row) => row.id !== target.id));
    } catch (caught) {
      setUsersError(
        caught instanceof Error ? caught.message : "Could not delete user.",
      );
    }
  };

  const toggleRole = async (target: AdminUserSummary) => {
    setUsersError(null);
    const nextRole = target.role === "admin" ? "user" : "admin";

    const confirmed = window.confirm(
      nextRole === "admin"
        ? `Make ${target.email} an admin? They will be able to manage the ` +
            `document library and every user, including deleting them.`
        : `Remove admin access from ${target.email}?`,
    );

    if (!confirmed) {
      return;
    }

    try {
      const updated = await updateUserRole(target.id, nextRole);
      setUsers((previous) =>
        previous.map((row) => (row.id === updated.id ? updated : row)),
      );
    } catch (caught) {
      setUsersError(
        caught instanceof Error ? caught.message : "Could not update role.",
      );
    }
  };

  return (
    <div className="admin-shell">
      <div className="admin-bar">
        <Link to="/" className="back-link">
          <ArrowLeft />
          Back to chat
        </Link>
        <ThemeToggle compact />
      </div>

      <div className="admin-body">
        <div className="admin-inner">
          <div>
            <h1>Library</h1>
            <p className="tagline">
              Everyone queries these documents. Only admins can change them.
            </p>
          </div>

          <div className="dropzone">
            <span className="dropzone-icon">
              <Upload size={20} strokeWidth={1.7} />
            </span>

            <div className="dropzone-copy">
              <strong>Add a PDF to the library</strong>
              <span>
                Text-based PDFs only. A long textbook can take several minutes
                to process.
              </span>
            </div>

            <input
              ref={inputRef}
              id="document-upload"
              type="file"
              accept="application/pdf,.pdf"
              disabled={uploading !== null}
              style={{ display: "none" }}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  void upload(file);
                }
              }}
            />

            <button
              type="button"
              className="btn"
              disabled={uploading !== null}
              onClick={() => inputRef.current?.click()}
            >
              <Upload />
              {uploading ? "Ingesting…" : "Choose file"}
            </button>
          </div>

          {uploading && (
            <p className="upload-status">
              <Spinner />
              Ingesting {uploading}…
            </p>
          )}
          {message && (
            <p className="upload-status upload-ok">{message}</p>
          )}
          {error && <p className="upload-status upload-error">{error}</p>}

          {documents.length === 0 ? (
            <div className="empty-state">
              <span className="empty-state-icon">
                <Document size={24} strokeWidth={1.5} />
              </span>
              <div>
                <strong>The library is empty</strong>
                <p>
                  Until a PDF is added, every question comes back with “I
                  couldn't find relevant information in the documents.”
                </p>
              </div>
            </div>
          ) : (
            <div className="table-card">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Status</th>
                    <th className="numeric">Pages</th>
                    <th className="numeric">Chunks</th>
                    <th className="numeric">Size</th>
                    <th>Added by</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {documents.map((document) => (
                    <tr key={document.id}>
                      <td>
                        <span className="file-cell">
                          <Document />
                          {document.filename}
                        </span>
                        {document.error && (
                          <span className="row-error" title={document.error}>
                            {document.error}
                          </span>
                        )}
                      </td>
                      <td>
                        <span className={`badge badge-${document.status}`}>
                          {document.status === "processing" ||
                          document.status === "deleting" ? (
                            <Spinner size={11} />
                          ) : (
                            <span className="badge-dot" />
                          )}
                          {document.status}
                        </span>
                      </td>
                      <td className="numeric">
                        {document.page_count ?? <span className="dim">—</span>}
                      </td>
                      <td className="numeric">{document.chunk_count}</td>
                      <td className="numeric dim">
                        {formatSize(document.size_bytes)}
                      </td>
                      <td className="dim">
                        {document.uploaded_by_email ?? "—"}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <button
                          type="button"
                          className="btn btn-danger btn-small"
                          onClick={() => void remove(document)}
                        >
                          <Trash size={13} />
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="admin-section">
            <h2>Users</h2>
            <p className="tagline">
              Everyone who has registered, newest first.
            </p>

            {usersError && (
              <p className="upload-status upload-error">{usersError}</p>
            )}

            {users.length === 0 ? (
              !usersError && (
                <div className="empty-state">
                  <span className="empty-state-icon">
                    <Users size={24} strokeWidth={1.5} />
                  </span>
                  <div>
                    <strong>No one has joined yet</strong>
                    <p>Registered users will show up here.</p>
                  </div>
                </div>
              )
            ) : (
              <div className="table-card">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Role</th>
                      <th>Status</th>
                      <th>Joined</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((user) => {
                      const isSelf = user.id === currentUser?.id;

                      return (
                        <tr key={user.id}>
                          <td>
                            <span className="file-cell">
                              <Users />
                              {user.full_name ?? user.email}
                            </span>
                            {user.full_name && (
                              <span className="cell-sub">{user.email}</span>
                            )}
                          </td>
                          <td>
                            <span
                              className={`badge ${
                                user.role === "admin"
                                  ? "badge-processing"
                                  : "badge-ready"
                              }`}
                            >
                              <span className="badge-dot" />
                              {user.role}
                            </span>
                          </td>
                          <td className="dim">
                            {user.is_active ? "Active" : "Inactive"}
                          </td>
                          <td className="dim">{formatDate(user.created_at)}</td>
                          <td>
                            <span className="row-actions">
                              <button
                                type="button"
                                className="btn btn-secondary btn-small"
                                onClick={() => void toggleRole(user)}
                              >
                                {user.role === "admin"
                                  ? "Remove admin"
                                  : "Make admin"}
                              </button>

                              <button
                                type="button"
                                className="btn btn-danger btn-small"
                                disabled={isSelf}
                                title={
                                  isSelf
                                    ? "You cannot delete your own account."
                                    : undefined
                                }
                                onClick={() => void removeUser(user)}
                              >
                                <Trash size={13} />
                                Delete
                              </button>
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
