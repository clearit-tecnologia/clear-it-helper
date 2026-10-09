import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatStreamError, streamChat } from "@/lib/api/chat";
import type { Source } from "@/lib/api/types";
import { saveSession } from "@/lib/auth/session";
import { controlledSseResponse, sseEvent, sseResponse } from "@/lib/test-utils/sse";

const source: Source = {
  ref: 1,
  document_id: "doc-1",
  filename: "lei.pdf",
  page: 3,
  chunk_index: 0,
  score: 0.82,
  text: "Art. 1º ...",
};

describe("streamChat", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    saveSession("tok", 3600);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("faz POST com Bearer, limita o histórico a 10 e entrega os eventos em ordem", async () => {
    const raw =
      sseEvent("sources", { sources: [source] }) +
      sseEvent("token", { text: "Prazo de " }) +
      sseEvent("token", { text: "20 dias, prorrogáveis por mais 10 (atenção à regulação) [1]." }) +
      sseEvent("done", { answer: "Prazo de 20 dias [1].", refused: false, usage: null, latency_ms: 1200 });
    // Network chunks cut in arbitrary places, including inside a multi-byte "ç".
    const bytes = new TextEncoder().encode(raw);
    const chunks: Uint8Array[] = [];
    for (let i = 0; i < bytes.length; i += 7) chunks.push(bytes.slice(i, i + 7));
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        chunks.forEach((chunk) => c.enqueue(chunk));
        c.close();
      },
    });
    fetchMock.mockResolvedValue(new Response(stream, { headers: { "Content-Type": "text/event-stream" } }));

    const onSources = vi.fn();
    const tokens: string[] = [];
    const history = Array.from({ length: 14 }, (_, i) => ({
      role: (i % 2 === 0 ? "user" : "assistant") as "user" | "assistant",
      content: `m${i}`,
    }));
    const done = await streamChat({ question: "Qual o prazo?", history }, { onSources, onToken: (t) => tokens.push(t) });

    expect(done).toEqual({ answer: "Prazo de 20 dias [1].", refused: false, usage: null, latency_ms: 1200 });
    expect(onSources).toHaveBeenCalledWith([source]);
    expect(tokens.join("")).toBe("Prazo de 20 dias, prorrogáveis por mais 10 (atenção à regulação) [1].");

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/chat");
    expect(init?.method).toBe("POST");
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer tok");
    expect(headers.Accept).toBe("text/event-stream");
    const body = JSON.parse(init?.body as string) as { question: string; history: unknown[] };
    expect(body.question).toBe("Qual o prazo?");
    expect(body.history).toHaveLength(10);
    expect(body.history[0]).toEqual({ role: "user", content: "m4" });
  });

  it("rejeita com a mensagem do evento error", async () => {
    fetchMock.mockResolvedValue(
      sseResponse([sseEvent("sources", { sources: [] }), sseEvent("error", { detail: "LLM indisponível" })]),
    );
    const error = await streamChat({ question: "x", history: [] }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ChatStreamError);
    expect((error as Error).message).toContain("LLM indisponível");
  });

  it("rejeita quando o stream termina sem done", async () => {
    fetchMock.mockResolvedValue(sseResponse([sseEvent("token", { text: "meia" })]));
    await expect(streamChat({ question: "x", history: [] })).rejects.toMatchObject({
      message: expect.stringContaining("interrompida"),
    });
  });

  it("traduz erros HTTP antes do stream", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 503 }));
    await expect(streamChat({ question: "x", history: [] })).rejects.toMatchObject({ status: 503 });
  });

  it("propaga AbortError quando o usuário para a resposta", async () => {
    const controller = new AbortController();
    fetchMock.mockImplementation(async (_url, init) => {
      const sse = controlledSseResponse(init?.signal);
      sse.push(sseEvent("sources", { sources: [] }));
      return sse.response;
    });
    const promise = streamChat({ question: "x", history: [] }, {}, controller.signal);
    await new Promise((r) => setTimeout(r, 0));
    controller.abort();
    await expect(promise).rejects.toMatchObject({ name: "AbortError" });
  });
});
