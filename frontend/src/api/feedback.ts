import type { FeedbackRating, FeedbackResponseBody } from "../types";
import { request } from "./client";

export function rateAnswer(
  messageId: number,
  rating: FeedbackRating,
  comment?: string,
): Promise<FeedbackResponseBody> {
  return request<FeedbackResponseBody>("/api/feedback", {
    method: "POST",
    body: {
      message_id: messageId,
      rating,
      comment: comment ?? null,
    },
  });
}

export function withdrawRating(messageId: number): Promise<void> {
  return request<void>(`/api/feedback/${messageId}`, { method: "DELETE" });
}
