import type { IngestResponse, QueryResponse } from "../types";

async function readError(response: Response): Promise<string> {
  const fallback = `Request failed (${response.status})`;

  const body = await response.json().catch(() => null);

  if (!body) {
    return fallback;
  }

  if (typeof body.detail === "string") {
    return body.detail;
  }

  if (Array.isArray(body.detail)) {
    return body.detail
      .map((item: { msg?: string }) => item.msg ?? fallback)
      .join("; ");
  }

  return fallback;
}

export async function askQuestion(params: {
  conversationId: string;
  question: string;
  topK: number;
  signal?: AbortSignal;
}): Promise<QueryResponse> {
  const response = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation_id: params.conversationId,
      question: params.question,
      top_k: params.topK,
    }),
    signal: params.signal,
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  return response.json();
}

export async function ingestDocument(file: File): Promise<IngestResponse> {
  const form = new FormData();
  form.append("file", file);

  const response = await fetch("/api/ingest", {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  return response.json();
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch("/health/health");
    return response.ok;
  } catch {
    return false;
  }
}
