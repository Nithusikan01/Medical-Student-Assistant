import { useCallback, useState } from "react";

import { askQuestion } from "../api/client";
import type { SourceChunk } from "../types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceChunk[];
}

export function useConversation() {
  const [conversationId, setConversationId] = useState(() =>
    crypto.randomUUID(),
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = useCallback(
    async (question: string, topK: number) => {
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

  const reset = useCallback(() => {
    setConversationId(crypto.randomUUID());
    setMessages([]);
    setError(null);
  }, []);

  return { conversationId, messages, pending, error, ask, reset };
}
