import { API_BASE, ApiError, authHeaders, defaultMessage, isAbortError, NETWORK_ERROR } from "@/lib/api/client";
import { clearSession } from "@/lib/auth/session";
import type { ChatDoneEvent, ChatRequest, Source } from "@/lib/api/types";
import { SseParser, type SseEvent } from "@/lib/sse";

/** Contract limit: at most 10 history messages per question. */
export const MAX_HISTORY_MESSAGES = 10;

export interface ChatStreamHandlers {
  onSources?: (sources: Source[]) => void;
  onToken?: (text: string) => void;
}

/** `error` event sent by the server in the middle of the stream. */
export class ChatStreamError extends Error {
  constructor(detail: string) {
    super(detail ? `Não foi possível gerar a resposta: ${detail}` : "Não foi possível gerar a resposta.");
    this.name = "ChatStreamError";
  }
}

const INCOMPLETE_STREAM = "A resposta foi interrompida antes de terminar. Tente novamente.";
const UNEXPECTED_RESPONSE = "Resposta inesperada do servidor.";

function parseData<T>(event: SseEvent): T {
  try {
    return JSON.parse(event.data) as T;
  } catch {
    throw new ApiError(502, UNEXPECTED_RESPONSE);
  }
}

/**
 * POST /api/chat and consumes the SSE stream (`sources` → `token`* → `done` | `error`).
 * Resolves with the `done` payload; rejects with `AbortError` when `signal` aborts.
 */
export async function streamChat(
  request: ChatRequest,
  handlers: ChatStreamHandlers = {},
  signal?: AbortSignal,
): Promise<ChatDoneEvent> {
  const body: ChatRequest = {
    question: request.question,
    history: request.history.slice(-MAX_HISTORY_MESSAGES),
  };

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError(0, NETWORK_ERROR);
  }

  if (!response.ok) {
    if (response.status === 401) clearSession();
    throw new ApiError(response.status, defaultMessage(response.status));
  }
  if (!response.body) throw new ApiError(502, UNEXPECTED_RESPONSE);

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  const parser = new SseParser();
  // Holder object: TS does not track assignments made inside the `handle` closure.
  const result: { done: ChatDoneEvent | null } = { done: null };

  const handle = (event: SseEvent): void => {
    switch (event.event) {
      case "sources": {
        const data = parseData<{ sources?: Source[] }>(event);
        handlers.onSources?.(Array.isArray(data.sources) ? data.sources : []);
        break;
      }
      case "token": {
        const data = parseData<{ text?: string }>(event);
        if (typeof data.text === "string" && data.text) handlers.onToken?.(data.text);
        break;
      }
      case "done":
        result.done = parseData<ChatDoneEvent>(event);
        break;
      case "error": {
        const data = parseData<{ detail?: string }>(event);
        throw new ChatStreamError(typeof data.detail === "string" ? data.detail : "");
      }
      default:
        break;
    }
  };

  try {
    for (;;) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch (error) {
        if (isAbortError(error) || signal?.aborted) throw new DOMException("Aborted", "AbortError");
        throw new ApiError(0, INCOMPLETE_STREAM);
      }
      if (chunk.done) break;
      // `stream: true` keeps multi-byte UTF-8 characters split across chunks intact.
      for (const event of parser.push(decoder.decode(chunk.value, { stream: true }))) handle(event);
      if (result.done) break;
    }
    if (!result.done) {
      for (const event of parser.push(decoder.decode())) handle(event);
      for (const event of parser.flush()) handle(event);
    }
  } finally {
    // Releases the connection on `done`, server `error` or abort; harmless if already closed.
    reader.cancel().catch(() => undefined);
  }

  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  if (!result.done) throw new ApiError(0, INCOMPLETE_STREAM);
  return result.done;
}
