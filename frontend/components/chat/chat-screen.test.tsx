import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatScreen } from "@/components/chat/chat-screen";
import type { ChatRequest, DocumentItem } from "@/lib/api/types";
import { saveSession } from "@/lib/auth/session";
import { axeViolations } from "@/lib/test-utils/axe";
import { jsonResponse, makeDocument, sampleSource } from "@/lib/test-utils/fixtures";
import { controlledSseResponse, sseEvent, sseResponse } from "@/lib/test-utils/sse";

const ANSWER = "O titular pode solicitar acesso aos dados [1].";

function answerStream(answer = ANSWER, refused = false, sources = [sampleSource]) {
  return sseResponse([
    sseEvent("sources", { sources }),
    sseEvent("token", { text: answer.slice(0, 10) }),
    // Two events in one chunk and an event split across chunks.
    sseEvent("token", { text: answer.slice(10, 20) }) + "event: tok",
    `en\ndata: ${JSON.stringify({ text: answer.slice(20) })}\n\n`,
    sseEvent("done", { answer, refused, usage: null, latency_ms: 900 }),
  ]);
}

describe("ChatScreen", () => {
  const fetchMock = vi.fn<typeof fetch>();
  let documents: DocumentItem[];
  let chatHandler: (init: RequestInit | undefined) => Response | Promise<Response>;

  beforeEach(() => {
    saveSession("tok", 3600);
    documents = [makeDocument({ status: "indexed", page_count: 10, chunk_count: 30 })];
    chatHandler = () => answerStream();
    fetchMock.mockReset();
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/api/documents") return jsonResponse({ items: documents });
      if (url === "/api/chat") return chatHandler(init);
      return jsonResponse({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  function chatBodies(): ChatRequest[] {
    return fetchMock.mock.calls
      .filter(([url]) => String(url) === "/api/chat")
      .map(([, init]) => JSON.parse(init?.body as string) as ChatRequest);
  }

  it("envia a pergunta, mostra a resposta com citação e abre a fonte", async () => {
    const user = userEvent.setup();
    render(<ChatScreen onOpenDocument={vi.fn()} />);

    await user.type(screen.getByLabelText("Sua pergunta"), "Quais são os direitos do titular?{Enter}");

    const log = screen.getByRole("list", { name: "Mensagens da conversa" });
    expect(await within(log).findByText("Quais são os direitos do titular?")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("status", { name: "" })).toHaveTextContent(`Resposta concluída: ${ANSWER}`));
    expect(within(log).getByText(/O titular pode solicitar acesso aos dados/)).toBeInTheDocument();
    expect(screen.getByLabelText("Sua pergunta")).toHaveValue("");

    const citations = within(log).getAllByRole("button", { name: /^\[1\] ver fonte/ });
    expect(citations.length).toBeGreaterThanOrEqual(1);
    await user.click(citations[0]!);
    const dialog = screen.getByRole("dialog", { name: "Fonte [1]" });
    expect(dialog).toHaveTextContent(sampleSource.text);
    expect(dialog).toHaveTextContent("Página3");

    expect(chatBodies()[0]).toEqual({ question: "Quais são os direitos do titular?", history: [] });
  });

  it("envia o histórico da sessão na pergunta seguinte e o persiste no sessionStorage", async () => {
    const user = userEvent.setup();
    render(<ChatScreen onOpenDocument={vi.fn()} />);

    await user.type(screen.getByLabelText("Sua pergunta"), "Primeira{Enter}");
    await screen.findByText("Resposta concluída", { exact: false });
    await user.type(screen.getByLabelText("Sua pergunta"), "E a segunda?{Enter}");
    await waitFor(() => expect(chatBodies()).toHaveLength(2));

    expect(chatBodies()[1]?.history).toEqual([
      { role: "user", content: "Primeira" },
      { role: "assistant", content: ANSWER },
    ]);
    await waitFor(() => expect(screen.getByLabelText("Sua pergunta")).not.toHaveAttribute("aria-invalid"));
    await waitFor(() => expect(sessionStorage.getItem("clear-helper.chat.v1")).toContain("E a segunda?"));
  });

  it("restaura a conversa da sessão e permite limpá-la", async () => {
    sessionStorage.setItem(
      "clear-helper.chat.v1",
      JSON.stringify([{ id: "a", role: "user", content: "Pergunta antiga", status: "done" }]),
    );
    const user = userEvent.setup();
    render(<ChatScreen onOpenDocument={vi.fn()} />);
    expect(await screen.findByText("Pergunta antiga")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Limpar conversa" }));
    expect(screen.queryByText("Pergunta antiga")).not.toBeInTheDocument();
    expect(sessionStorage.getItem("clear-helper.chat.v1")).toBeNull();
    expect(screen.getByLabelText("Sua pergunta")).toHaveFocus();
  });

  it("destaca a resposta recusada (sem evidência)", async () => {
    chatHandler = () => answerStream("Não encontrei essa informação nos documentos enviados.", true, []);
    const user = userEvent.setup();
    render(<ChatScreen onOpenDocument={vi.fn()} />);

    await user.type(screen.getByLabelText("Sua pergunta"), "Qual a capital da França?{Enter}");
    expect(await screen.findByText("Sem evidência nos documentos")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Resposta do assistente: sem evidência" })).toBeInTheDocument();
    expect(document.querySelector("[data-refused]")).toHaveTextContent("Não encontrei essa informação");
  });

  it("não anuncia token a token e permite parar a resposta", async () => {
    let push: (text: string) => void = () => undefined;
    chatHandler = (init) => {
      const sse = controlledSseResponse(init?.signal);
      push = sse.push;
      sse.push(sseEvent("sources", { sources: [sampleSource] }));
      return sse.response;
    };
    const user = userEvent.setup();
    render(<ChatScreen onOpenDocument={vi.fn()} />);

    await user.type(screen.getByLabelText("Sua pergunta"), "Pergunta longa{Enter}");
    push(sseEvent("token", { text: "Resposta parcial" }));
    expect(await screen.findByText("Resposta parcial")).toBeInTheDocument();

    const live = screen.getByText("Gerando resposta…", { selector: "[role=status]" });
    expect(live).not.toHaveTextContent("Resposta parcial");
    expect(screen.getByRole("region", { name: "Conversa" })).toHaveAttribute("aria-busy", "true");

    await user.click(screen.getByRole("button", { name: "Parar resposta" }));
    expect(await screen.findByText("Resposta interrompida.")).toBeInTheDocument();
    expect(screen.getByText("Resposta parcial")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enviar pergunta" })).toBeInTheDocument();
    expect(live).toHaveTextContent("Geração da resposta interrompida.");
  });

  it("mostra o erro do stream de forma acessível", async () => {
    chatHandler = () => sseResponse([sseEvent("sources", { sources: [] }), sseEvent("error", { detail: "timeout" })]);
    const user = userEvent.setup();
    render(<ChatScreen onOpenDocument={vi.fn()} />);

    await user.type(screen.getByLabelText("Sua pergunta"), "Teste{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível gerar a resposta: timeout");
  });

  it("valida pergunta vazia", async () => {
    const user = userEvent.setup();
    render(<ChatScreen onOpenDocument={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Enviar pergunta" }));
    expect(screen.getByLabelText("Sua pergunta")).toHaveAccessibleDescription(
      "Enter envia; Shift+Enter quebra a linha. Digite uma pergunta antes de enviar.",
    );
    expect(chatBodies()).toHaveLength(0);
  });

  it("orienta a enviar documentos quando não há nenhum", async () => {
    documents = [];
    render(<ChatScreen onOpenDocument={vi.fn()} />);
    expect(await screen.findByText("Você ainda não enviou documentos.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Enviar documentos" })).toHaveAttribute("href", "/documentos");
  });

  it("avisa quando os documentos ainda estão em processamento", async () => {
    documents = [makeDocument({ status: "processing" })];
    render(<ChatScreen onOpenDocument={vi.fn()} />);
    expect(await screen.findByText("Seus documentos ainda estão sendo processados.")).toBeInTheDocument();
  });

  it("não tem violações de acessibilidade com uma resposta citada (axe, WCAG 2.1 AA)", async () => {
    const user = userEvent.setup();
    const { container } = render(<ChatScreen onOpenDocument={vi.fn()} />);
    await user.type(screen.getByLabelText("Sua pergunta"), "Pergunta{Enter}");
    await screen.findByText("Resposta concluída", { exact: false });
    expect(await axeViolations(container)).toEqual([]);
  });
});
