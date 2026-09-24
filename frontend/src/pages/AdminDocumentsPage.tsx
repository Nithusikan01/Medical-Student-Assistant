import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  deleteDocument,
  listDocuments,
  uploadDocument,
} from "../api/documents";
import { formatSize } from "../components/admin/Primitives";
import {
  ArrowLeft,
  Document,
  Spinner,
  Trash,
  Upload,
} from "../components/Icons";
import { ThemeToggle } from "../components/ThemeToggle";
import type { DocumentSummary } from "../types";


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
            {/* Named for the card that leads here and for the route, not
                for the word the body copy uses. "Library" reads better in
                a sentence; it reads as a different page in a heading. */}
            <h1>Documents</h1>
            <p className="tagline">
              Everyone queries these documents. Only admins can change them.
            </p>
            <p className="mon-links">
              <Link to="/admin/monitoring">&larr; Admin dashboard</Link>
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
            <div className="table-card table-card-stack">
              <table className="data-table cards-on-phone doc-table">
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
                      <td className="doc-name">
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
                      <td className="doc-status">
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
                      {/* data-label names each figure once the header row
                          is hidden and the row becomes a card on a phone. */}
                      <td className="numeric doc-pages" data-label="Pages">
                        {document.page_count ?? <span className="dim">—</span>}
                      </td>
                      <td className="numeric doc-chunks" data-label="Chunks">
                        {document.chunk_count}
                      </td>
                      <td className="numeric dim doc-size" data-label="Size">
                        {formatSize(document.size_bytes)}
                      </td>
                      <td className="dim doc-by">
                        {document.uploaded_by_email ?? "—"}
                      </td>
                      <td className="doc-actions" style={{ textAlign: "right" }}>
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

        </div>
      </div>
    </div>
  );
}
