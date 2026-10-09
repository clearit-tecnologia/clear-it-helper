const encoder = new TextEncoder();

/** Serializes one SSE event as sent by the API (`event:` + JSON `data:`). */
export function sseEvent(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** Response whose body emits each string as a separate network chunk. */
export function sseResponse(chunks: string[], init: ResponseInit = {}): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
    ...init,
  });
}

/**
 * Stream controlled by the test: push chunks over time and honour the abort signal
 * like a real `fetch` would.
 */
export function controlledSseResponse(signal?: AbortSignal | null) {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  signal?.addEventListener("abort", () => {
    try {
      controller.error(new DOMException("Aborted", "AbortError"));
    } catch {
      // already closed
    }
  });
  return {
    response: new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    push: (text: string) => controller.enqueue(encoder.encode(text)),
    close: () => controller.close(),
  };
}
