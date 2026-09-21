import { useCallback, useEffect, useState } from "react";

import { askQuestion, getConversation } from "../api/conversations";
import { rateAnswer, withdrawRating } from "../api/feedback";
import type { FeedbackRating, SourceChunk } from "../types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceChunk[];
  // Only set for answers generated this session - conversation history
  // loaded from the server doesn't carry which model answered.
  model?: string;
  // The stored id of an answer. Absent on questions, and on an answer the
  // server could not identify - in which case it cannot be rated.
  messageId?: number;
  feedback?: FeedbackRating | null;
}

export function useConversation(conversationId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Hydrate from the server whenever the route's conversation changes, so
  // history survives a reload and is shared across devices.
  useEffect(() => {
    let cancelled = false;

    if (!conversationId) {
      setMessages([]);
      return;
    }

    setLoading(true);
    setError(null);

    getConversation(conversationId)
      .then((detail) => {
        if (cancelled) {
          return;
        }

        setMessages(
          detail.messages.map((message) => ({
            id: String(message.id),
            role: message.role,
            content: message.content,
            sources: message.sources ?? undefined,
            messageId: message.id,
            feedback: message.feedback,
          })),
        );
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Could not load this conversation.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const ask = useCallback(
    async (question: string, topK: number, model?: string | null) => {
      if (!conversationId) {
        return;
      }

      setError(null);
      setPending(true);

      setMessages((previous) => [
        ...previous,
        { id: crypto.randomUUID(), role: "user", content: question },
      ]);

      try {
        const response = await askQuestion({
          conversationId,
          question,
          topK,
          model,
        });

        setMessages((previous) => [
          ...previous,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: response.answer,
            sources: response.sources,
            model: response.model,
            messageId: response.message_id ?? undefined,
            feedback: null,
          },
        ]);
      } catch (caught) {
        setError(
          caught instanceof Error ? caught.message : "Unexpected error.",
        );
      } finally {
        setPending(false);
      }
    },
    [conversationId],
  );

  /**
   * Rate an answer, or take the rating back by pressing the same thumb.
   *
   * Optimistic: the thumb fills immediately and reverts if the request
   * fails. A rating is not worth making someone wait for, and a failed
   * one that silently looked successful would be worse than a visible
   * revert.
   */
  const rate = useCallback(
    async (messageId: number, rating: FeedbackRating) => {
      let previous: FeedbackRating | null | undefined;

      setMessages((messages) =>
        messages.map((message) => {
          if (message.messageId !== messageId) {
            return message;
          }

          previous = message.feedback;

          return {
            ...message,
            feedback: message.feedback === rating ? null : rating,
          };
        }),
      );

      const next = previous === rating ? null : rating;

      try {
        if (next === null) {
          await withdrawRating(messageId);
        } else {
          await rateAnswer(messageId, next);
        }
      } catch {
        setMessages((messages) =>
          messages.map((message) =>
            message.messageId === messageId
              ? { ...message, feedback: previous ?? null }
              : message,
          ),
        );
      }
    },
    [],
  );

  return { messages, pending, loading, error, ask, rate };
}
