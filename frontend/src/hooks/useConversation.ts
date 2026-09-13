import { useCallback, useEffect, useState } from "react";

import { askQuestion, getConversation } from "../api/conversations";
import type { SourceChunk } from "../types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceChunk[];
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
    async (question: string, topK: number) => {
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
        });

        setMessages((previous) => [
          ...previous,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: response.answer,
            sources: response.sources,
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

  return { messages, pending, loading, error, ask };
}
