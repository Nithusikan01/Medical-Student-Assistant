import type { DocumentSummary, IngestResponse } from "../types";
import { request } from "./client";

export function listDocuments(): Promise<DocumentSummary[]> {
  return request<DocumentSummary[]>("/api/documents");
}

export function uploadDocument(file: File): Promise<IngestResponse> {
  const form = new FormData();
  form.append("file", file);

  return request<IngestResponse>("/api/ingest", {
    method: "POST",
    formData: form,
  });
}

export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/api/documents/${id}`, { method: "DELETE" });
}
