import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveSession } from "@/lib/auth/session";
import { openDocument, openModeFor } from "@/lib/documents/open-document";

describe("openDocument", () => {
  const fetchMock = vi.fn<typeof fetch>();
  const createObjectURL = vi.fn<(blob: Blob) => string>();
  let tab: { opener: unknown; document: Document; location: { href: string }; close: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    saveSession("tok", 3600);
    fetchMock.mockReset();
    createObjectURL.mockReset().mockReturnValue("blob:http://app/abc");
    tab = { opener: window, document: document.implementation.createHTMLDocument(""), location: { href: "" }, close: vi.fn() };
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("abre PDF em nova aba na página citada, sem opener", async () => {
    fetchMock.mockResolvedValue(new Response("%PDF", { headers: { "Content-Type": "application/pdf" } }));
    await openDocument({ documentId: "doc-1", filename: "lei.pdf", page: 7 });

    expect(window.open).toHaveBeenCalledWith("", "_blank");
    expect(tab.opener).toBeNull();
    expect(tab.location.href).toBe("blob:http://app/abc#page=7");
    expect(createObjectURL.mock.calls[0]![0].type).toBe("application/pdf");
    expect((fetchMock.mock.calls[0]![1]?.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("exibe HTML como texto puro (nunca renderiza HTML enviado na origem da aplicação)", async () => {
    fetchMock.mockResolvedValue(new Response("<script>x</script>", { headers: { "Content-Type": "text/html" } }));
    await openDocument({ documentId: "doc-1", filename: "pagina.html", page: 1 });

    expect(createObjectURL.mock.calls[0]![0].type).toBe("text/plain;charset=utf-8");
    expect(tab.location.href).toBe("blob:http://app/abc");
  });

  it("baixa DOCX com o nome original, sem abrir aba", async () => {
    fetchMock.mockResolvedValue(new Response("PK", { headers: { "Content-Type": "application/octet-stream" } }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    await openDocument({ documentId: "doc-1", filename: "ata.docx" });

    expect(window.open).not.toHaveBeenCalled();
    expect(click).toHaveBeenCalledTimes(1);
    const anchor = click.mock.contexts[0] as HTMLAnchorElement;
    expect(anchor.download).toBe("ata.docx");
  });

  it("fecha a aba e propaga o erro quando o download falha", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 404 }));
    await expect(openDocument({ documentId: "x", filename: "lei.pdf", page: 1 })).rejects.toMatchObject({ status: 404 });
    expect(tab.close).toHaveBeenCalled();
  });

  it("decide o modo por extensão e Content-Type", () => {
    expect(openModeFor("a.PDF")).toBe("pdf");
    expect(openModeFor("a.md")).toBe("text");
    expect(openModeFor("a.docx")).toBe("download");
    expect(openModeFor("sem-extensao", "text/plain")).toBe("text");
  });
});
