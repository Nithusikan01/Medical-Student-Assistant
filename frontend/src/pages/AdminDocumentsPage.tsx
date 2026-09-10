import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  deleteDocument,
  listDocuments,
  uploadDocument,
} from "../api/documents";
import type { DocumentSummary } from "../types";

function formatSize(bytes: number | null): string {
  if (bytes === null) {
    return "—";
  }

  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AdminDocumentsPage() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [uploading, setUploading] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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

  const upload = async (file: File) => {
    setError(null);
    setMessage(null);
    setUploading(file.name);

    try {
      const response = await uploadDocument(file);
      setMessage(`${response.filename} ingested.`);
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
      `Delete "${document.filename}"? Its vectors will be removed and it ` +
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
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Delete failed.");
      await refresh();
    }
  };

  return (
    <div className="admin-page">
      <header className="admin-head">
        <div>
          <h1>Documents</h1>
          <p className="tagline">
            Everyone queries this shared library. Only admins can change it.
          </p>
        </div>
        <Link to="/" className="secondary button-like">
          Back to chat
        </Link>
      </header>

      <section className="upload-block">
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          disabled={uploading !== null}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              void upload(file);
            }
          }}
        />

        {uploading && (
          <p className="upload-status">
            Ingesting {uploading}… this can take a while for a long PDF.
          </p>
        )}
        {message && <p className="upload-status upload-ok">{message}</p>}
        {error && <p className="upload-status upload-error">{error}</p>}
      </section>

      <table className="documents">
        <thead>
          <tr>
            <th>File</th>
            <th>Status</th>
            <th>Pages</th>
            <th>Chunks</th>
            <th>Size</th>
            <th>Uploaded by</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {documents.length === 0 && (
            <tr>
              <td colSpan={7} className="empty-row">
                No documents yet. Upload a PDF to get started.
              </td>
            </tr>
          )}

          {documents.map((document) => (
            <tr key={document.id}>
              <td>{document.filename}</td>
              <td>
                <span className={`badge badge-${document.status}`}>
                  {document.status}
                </span>
                {document.error && (
                  <span className="row-error" title={document.error}>
                    {document.error.slice(0, 60)}
                  </span>
                )}
              </td>
              <td>{document.page_count ?? "—"}</td>
              <td>{document.chunk_count}</td>
              <td>{formatSize(document.size_bytes)}</td>
              <td>{document.uploaded_by_email ?? "—"}</td>
              <td>
                <button
                  type="button"
                  className="danger small"
                  onClick={() => void remove(document)}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
