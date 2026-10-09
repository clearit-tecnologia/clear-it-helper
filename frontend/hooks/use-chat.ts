"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { isAbortError } from "@/lib/api/client";
import { streamChat } from "@/lib/api/chat";
import {
  buildHistory,
  clearChatHistory,
  createMessageId,
  loadChatHistory,
  saveChatHistory,
  type ChatMessage,
} from "@/lib/chat/history";

export interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  /** Text for the polite live region: set when an answer finishes, never per token. */
  announcement: string;
  send: (question: string) => Promise<void>;
  stop: () => void;
  clear: () => void;
}

export function useChat(): ChatState {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const controllerRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  messagesRef.current = messages;

  // Loaded after mount so server and client renders match.
  useEffect(() => {
    setMessages(loadChatHistory());
    setHydrated(true);
    return () => controllerRef.current?.abort();
  }, []);

  // Persisted when no answer is in flight (avoids a write per token).
  useEffect(() => {
    if (hydrated && !isStreaming) saveChatHistory(messages);
  }, [messages, hydrated, isStreaming]);

  const update = useCallback((id: string, patch: (m: ChatMessage) => Partial<ChatMessage>) => {
    setMessages((current) => current.map((m) => (m.id === id ? { ...m, ...patch(m) } : m)));
  }, []);

  const send = useCallback(
    async (rawQuestion: string) => {
      const question = rawQuestion.trim();
      if (!question || controllerRef.current) return;

      const history = buildHistory(messagesRef.current);
      const userMessage: ChatMessage = { id: createMessageId(), role: "user", content: question, status: "done" };
      const answerId = createMessageId();
      const answer: ChatMessage = { id: answerId, role: "assistant", content: "", status: "streaming", sources: [] };

      const controller = new AbortController();
      controllerRef.current = controller;
      setMessages((current) => [...current, userMessage, answer]);
      setIsStreaming(true);
      setAnnouncement("Gerando resposta…");

      try {
        const done = await streamChat(
          { question, history },
          {
            onSources: (sources) => update(answerId, () => ({ sources })),
            onToken: (text) => update(answerId, (m) => ({ content: m.content + text })),
          },
          controller.signal,
        );
        update(answerId, (m) => ({
          // `answer` is authoritative (reasoning blocks already stripped by the API).
          content: done.answer || m.content,
          status: "done",
          refused: done.refused,
          latencyMs: done.latency_ms,
        }));
        setAnnouncement(
          done.refused ? `Resposta sem evidência nos documentos: ${done.answer}` : `Resposta concluída: ${done.answer}`,
        );
      } catch (error) {
        if (isAbortError(error) || controller.signal.aborted) {
          update(answerId, () => ({ status: "stopped" }));
          setAnnouncement("Geração da resposta interrompida.");
        } else {
          const message = error instanceof Error ? error.message : "Não foi possível gerar a resposta.";
          update(answerId, () => ({ status: "error", error: message }));
          // Errors are announced by the message itself (role="alert").
          setAnnouncement("");
        }
      } finally {
        if (controllerRef.current === controller) controllerRef.current = null;
        setIsStreaming(false);
      }
    },
    [update],
  );

  const stop = useCallback(() => {
    controllerRef.current?.abort();
  }, []);

  const clear = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setMessages([]);
    clearChatHistory();
    setAnnouncement("Conversa apagada.");
  }, []);

  return { messages, isStreaming, announcement, send, stop, clear };
}
