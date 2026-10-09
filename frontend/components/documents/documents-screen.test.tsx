import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentsScreen } from "@/components/documents/documents-screen";
import { DOCUMENTS_POLL_INTERVAL_MS } from "@/hooks/use-documents";
import type { DocumentItem } from "@/lib/api/types";
import { saveSession } from "@/lib/auth/session";
import { axeViolations } from "@/lib/test-utils/axe";
import { jsonResponse, makeDocument } from "@/lib/test-utils/fixtures";

const indexed = makeDocument({
  id: "doc-1",
  filename: "lei-13709.pdf",
  status: "indexed",
  page_count: 12,
  chunk_count: 48,
  created_at: "2026-10-09T13:00:00Z",
});
const failed = makeDocument({
  id: "doc-2",
  filename: "escaneado.pdf",
  status: "failed",
  error: "Documento sem texto extraível (OCR chega na Fase 2)",
});

function uploadInput(): HTMLInputElement {
  return screen.getByTestId("upload-input") as HTMLInputElement;
}

describe("DocumentsScreen", () => {
  const fetchMock = vi.fn<typeof fetch>();
  let documents: DocumentItem[];
  let uploadResponse: () => Response;

  beforeEach(() => {
    saveSession("tok", 3600);
    documents = [indexed, failed];
    uploadResponse = () => jsonResponse(makeDocument({ id: "novo", filename: "novo.pdf" }), 202);
    fetchMock.mockReset();
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/documents" && method === "GET") return jsonResponse({ items: documents });
      if (url === "/api/documents" && method === "POST") return uploadResponse();
      if (method === "DELETE") {
        documents = documents.filter((d) => !url.endsWith(d.id));
        return new Response(null, { status: 204 });
      }
      if (url.endsWith("/reprocess")) return new Response(null, { status: 202 });
      return jsonResponse({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("lista documentos com status, páginas, trechos, data e erro", async () => {
    render(<DocumentsScreen />);
    const item = within(await screen.findByTestId("document-doc-1"));
    expect(item.getByRole("heading", { name: "lei-13709.pdf" })).toBeInTheDocument();
    expect(item.getByText("Indexado")).toBeInTheDocument();
    expect(item.getByText("12")).toBeInTheDocument();
    expect(item.getByText("48")).toBeInTheDocument();
    expect(item.getByText(/^09\/10\/2026/)).toBeInTheDocument();

    const bad = within(screen.getByTestId("document-doc-2"));
    expect(bad.getByText("Falhou")).toBeInTheDocument();
    expect(bad.getByText("Documento sem texto extraível (OCR chega na Fase 2)")).toBeInTheDocument();
  });

  it("informa formatos, limite de 50 MB e que PDF escaneado ainda não é suportado", async () => {
    render(<DocumentsScreen />);
    expect(screen.getByText(/Formatos aceitos: PDF, DOCX, TXT, MD ou HTML\. Tamanho máximo: 50 MB/)).toBeInTheDocument();
    expect(screen.getByText("PDFs escaneados ainda não são suportados.")).toBeInTheDocument();
    await screen.findByTestId("document-doc-1");
  });

  it("mostra estado vazio", async () => {
    documents = [];
    render(<DocumentsScreen />);
    expect(await screen.findByText(/Nenhum documento enviado ainda/)).toBeInTheDocument();
  });

  it("mostra erro de carregamento com opção de tentar novamente", async () => {
    fetchMock.mockImplementationOnce(async () => jsonResponse({}, 500));
    render(<DocumentsScreen />);
    expect(await screen.findByRole("alert")).toHaveTextContent("O servidor está indisponível");
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByTestId("document-doc-1")).toBeInTheDocument();
  });

  it("consulta a cada 3 s enquanto houver documento em processamento e para ao indexar", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    documents = [makeDocument({ id: "p", status: "processing" })];
    render(<DocumentsScreen />);
    await screen.findByText("Processando");
    const listCalls = () => fetchMock.mock.calls.filter(([u, i]) => u === "/api/documents" && (i?.method ?? "GET") === "GET").length;
    expect(listCalls()).toBe(1);

    documents = [makeDocument({ id: "p", status: "indexed", chunk_count: 3 })];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DOCUMENTS_POLL_INTERVAL_MS);
    });
    expect(listCalls()).toBe(2);
    expect(await screen.findByText("Indexado")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(DOCUMENTS_POLL_INTERVAL_MS * 3);
    });
    expect(listCalls()).toBe(2);
  });

  it("envia arquivo pelo botão e anuncia o resultado", async () => {
    const user = userEvent.setup();
    render(<DocumentsScreen />);
    await screen.findByTestId("document-doc-1");
    await user.upload(uploadInput(), new File(["%PDF"], "novo.pdf", { type: "application/pdf" }));

    expect(await screen.findByText("1 arquivo enviado.")).toBeInTheDocument();
    expect(screen.getByText("Enviado. O processamento começou.")).toBeInTheDocument();
  });

  it("aceita arquivos soltos na área de arrastar", async () => {
    render(<DocumentsScreen />);
    await screen.findByTestId("document-doc-1");
    const file = new File(["texto"], "notas.txt", { type: "text/plain" });
    fireEvent.drop(screen.getByTestId("upload-dropzone"), { dataTransfer: { files: [file] } });
    expect(await screen.findByText("1 arquivo enviado.")).toBeInTheDocument();
  });

  it("409: informa duplicado e realça o documento existente", async () => {
    uploadResponse = () => jsonResponse({ detail: "Duplicate", document_id: "doc-1" }, 409);
    const user = userEvent.setup();
    render(<DocumentsScreen />);
    await screen.findByTestId("document-doc-1");
    await user.upload(uploadInput(), new File(["%PDF"], "lei-13709.pdf", { type: "application/pdf" }));

    expect(await screen.findByText("Este arquivo já foi enviado anteriormente.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ver documento existente" }));
    const existing = screen.getByTestId("document-doc-1");
    expect(existing).toHaveFocus();
    expect(existing).toHaveTextContent("(arquivo já enviado)");
  });

  it.each([
    [413, "O arquivo excede o limite de 50 MB."],
    [415, "Formato não suportado. Envie arquivos PDF, DOCX, TXT, MD ou HTML."],
  ])("%i: mostra mensagem em pt-BR", async (status, message) => {
    uploadResponse = () => jsonResponse({ detail: "x" }, status);
    const user = userEvent.setup();
    render(<DocumentsScreen />);
    await screen.findByTestId("document-doc-1");
    await user.upload(uploadInput(), new File(["%PDF"], "arquivo.pdf", { type: "application/pdf" }));
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByText("1 com erro.")).toBeInTheDocument();
  });

  it("recusa localmente formato não suportado sem chamar a API", async () => {
    const user = userEvent.setup({ applyAccept: false });
    render(<DocumentsScreen />);
    await screen.findByTestId("document-doc-1");
    await user.upload(uploadInput(), new File(["x"], "planilha.xlsx"));
    expect(await screen.findByText(/Formato não suportado/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === "POST")).toBe(false);
  });

  it("exclui somente após confirmação no diálogo", async () => {
    const user = userEvent.setup();
    render(<DocumentsScreen />);
    await screen.findByTestId("document-doc-1");

    await user.click(screen.getByRole("button", { name: "Excluir lei-13709.pdf" }));
    const dialog = screen.getByRole("alertdialog", { name: "Excluir documento?" });
    expect(dialog).toHaveAccessibleDescription(/lei-13709\.pdf.*não pode ser desfeita/);
    expect(within(dialog).getByRole("button", { name: "Cancelar" })).toHaveFocus();

    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === "DELETE")).toBe(false);

    await user.click(screen.getByRole("button", { name: "Excluir lei-13709.pdf" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Excluir" }));

    await waitFor(() => expect(screen.queryByTestId("document-doc-1")).not.toBeInTheDocument());
    expect(screen.getByText("Documento “lei-13709.pdf” excluído.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.find(([, i]) => i?.method === "DELETE")?.[0]).toBe("/api/documents/doc-1");
    expect(screen.getByRole("heading", { name: "Seus documentos" })).toHaveFocus();
  });

  it("reprocessa documento com falha", async () => {
    const user = userEvent.setup();
    render(<DocumentsScreen />);
    await screen.findByTestId("document-doc-2");
    await user.click(screen.getByRole("button", { name: "Reprocessar escaneado.pdf" }));
    expect(await screen.findByText("Reprocessamento de “escaneado.pdf” iniciado.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => u === "/api/documents/doc-2/reprocess")).toBe(true);
  });

  it("não tem violações de acessibilidade (axe, WCAG 2.1 AA), inclusive com o diálogo aberto", async () => {
    const user = userEvent.setup();
    const { container } = render(<DocumentsScreen />);
    await screen.findByTestId("document-doc-1");
    expect(await axeViolations(container)).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Excluir lei-13709.pdf" }));
    expect(await axeViolations(container)).toEqual([]);
  });
});
