import { useRef, useState } from "react";

import { ingestDocument } from "../api/client";

type UploadState =
  | { kind: "idle" }
  | { kind: "uploading"; filename: string }
  | { kind: "done"; message: string }
  | { kind: "error"; message: string };

interface UploadPanelProps {
  onIngested: () => void;
}

export function UploadPanel({ onIngested }: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<UploadState>({ kind: "idle" });

  const upload = async (file: File) => {
    setState({ kind: "uploading", filename: file.name });

    try {
      const response = await ingestDocument(file);

      setState({ kind: "done", message: `${response.filename} ingested.` });
      onIngested();
    } catch (caught) {
      setState({
        kind: "error",
        message: caught instanceof Error ? caught.message : "Upload failed.",
      });
    } finally {
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    }
  };

  return (
    <div className="upload">
      <h3>Documents</h3>

      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        disabled={state.kind === "uploading"}
        onChange={(event) => {
          const file = event.target.files?.[0];

          if (file) {
            void upload(file);
          }
        }}
      />

      {state.kind === "uploading" && (
        <p className="upload-status">Ingesting {state.filename}…</p>
      )}

      {state.kind === "done" && (
        <p className="upload-status upload-ok">{state.message}</p>
      )}

      {state.kind === "error" && (
        <p className="upload-status upload-error">{state.message}</p>
      )}

      <p className="hint">
        Ingestion embeds the PDF, upserts it to Pinecone, and rebuilds the query
        service, so it can take a while on the first run.
      </p>
    </div>
  );
}
