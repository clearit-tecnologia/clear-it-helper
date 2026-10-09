import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import {
  deleteDocument,
  DuplicateDocumentError,
  fetchDocumentFile,
  listDocuments,
  reprocessDocument,
  UPLOAD_MAX_BYTES,
  uploadDocument,
  validateUploadFile,
} from "@/lib/api/documents";
import { getAccessToken, saveSession } from "@/lib/auth/session";
import { sampleDocument } from "@/lib/test-utils/fixtures";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}


describe("cliente de documentos", () => {
  const fetchMock = vi.fn<typeof fetch>();
  const file = new File(["%PDF-1.4"], "lei.pdf", { type: "application/pdf" });

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    saveSession("tok", 3600);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("envia multipart no campo file, com Bearer e sem Content-Type manual", async () => {
    fetchMock.mockResolvedValue(jsonResponse(sampleDocument, 202));

    await expect(uploadDocument(file)).resolves.toEqual(sampleDocument);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/documents");
    expect(init?.method).toBe("POST");
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer tok");
    expect(headers["Content-Type"]).toBeUndefined();
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("409 vira DuplicateDocumentError com o id do documento existente", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Duplicate", document_id: "doc-antigo" }, 409));

    const error = await uploadDocument(file).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(DuplicateDocumentError);
    expect((error as DuplicateDocumentError).documentId).toBe("doc-antigo");
    expect((error as DuplicateDocumentError).status).toBe(409);
  });

  it("409 sem document_id ainda é tratado como duplicado", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Duplicate" }, 409));
    const error = await uploadDocument(file).catch((e: unknown) => e);
    expect((error as DuplicateDocumentError).documentId).toBeNull();
  });

  it("413 informa o limite de tamanho em pt-BR", async () => {
    fetchMock.mockResolvedValue(new Response("Request Entity Too Large", { status: 413 }));
    await expect(uploadDocument(file)).rejects.toMatchObject({
      status: 413,
      message: "O arquivo excede o limite de 50 MB.",
    });
  });

  it("415 informa os formatos aceitos", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Unsupported" }, 415));
    await expect(uploadDocument(file)).rejects.toMatchObject({
      status: 415,
      message: expect.stringContaining("PDF, DOCX, TXT, MD ou HTML"),
    });
  });

  it("lista documentos e valida o formato da resposta", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [sampleDocument] }));
    await expect(listDocuments()).resolves.toEqual([sampleDocument]);
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/documents");

    fetchMock.mockResolvedValueOnce(jsonResponse({ unexpected: true }));
    await expect(listDocuments()).rejects.toBeInstanceOf(ApiError);
  });

  it("exclui (204) e reprocessa (202 sem corpo)", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(deleteDocument("doc 1")).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/documents/doc%201");
    expect(fetchMock.mock.calls[0]![1]?.method).toBe("DELETE");

    fetchMock.mockResolvedValueOnce(new Response(null, { status: 202 }));
    await expect(reprocessDocument("doc-1")).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[1]![0]).toBe("/api/documents/doc-1/reprocess");
    expect(fetchMock.mock.calls[1]![1]?.method).toBe("POST");
  });

  it("baixa o arquivo com Bearer e devolve o blob e o tipo", async () => {
    fetchMock.mockResolvedValue(new Response("conteúdo", { status: 200, headers: { "Content-Type": "application/pdf" } }));
    const result = await fetchDocumentFile("doc-1");
    expect(result.contentType).toBe("application/pdf");
    expect(await result.blob.text()).toBe("conteúdo");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/documents/doc-1/file");
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("401 no download limpa a sessão", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "expired" }, 401));
    await expect(fetchDocumentFile("doc-1")).rejects.toMatchObject({ status: 401 });
    expect(getAccessToken()).toBeNull();
  });

  it("valida extensão, tamanho e arquivo vazio antes do envio", () => {
    expect(validateUploadFile(file)).toBeNull();
    expect(validateUploadFile(new File(["x"], "NOTAS.MD"))).toBeNull();
    expect(validateUploadFile(new File(["x"], "planilha.xlsx"))).toMatch(/Formato não suportado/);
    expect(validateUploadFile(new File([], "vazio.txt"))).toBe("O arquivo está vazio.");
    const big = new File(["x"], "grande.pdf");
    Object.defineProperty(big, "size", { value: UPLOAD_MAX_BYTES + 1 });
    expect(validateUploadFile(big)).toMatch(/50 MB/);
  });
});
