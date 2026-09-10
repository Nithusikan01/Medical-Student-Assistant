import type {
  ConversationDetail,
  ConversationSummary,
  QueryResponse,
} from "../types";
import { request } from "./client";

export function listConversations(): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>("/api/conversations");
}

export function getConversation(id: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/api/conversations/${id}`);
}

export function createConversation(
  title?: string,
): Promise<ConversationDetail> {
  return request<ConversationDetail>("/api/conversations", {
    method: "POST",
    body: { title: title ?? null },
  });
}

export function renameConversation(
  id: string,
  title: string,
): Promise<ConversationSummary> {
  return request<ConversationSummary>(`/api/conversations/${id}`, {
    method: "PATCH",
    body: { title },
  });
}

export function deleteConversation(id: string): Promise<void> {
  return request<void>(`/api/conversations/${id}`, { method: "DELETE" });
}

export function askQuestion(params: {
  conversationId: string;
  question: string;
  topK: number;
}): Promise<QueryResponse> {
  return request<QueryResponse>("/api/query", {
    method: "POST",
    body: {
      conversation_id: params.conversationId,
      question: params.question,
      top_k: params.topK,
    },
  });
}
