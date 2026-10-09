import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SourcePanel } from "@/components/chat/source-panel";
import { ApiError } from "@/lib/api/client";
import { makeSource, sampleSource } from "@/lib/test-utils/fixtures";
import { axeViolations } from "@/lib/test-utils/axe";

describe("SourcePanel", () => {
  it("mostra trecho, arquivo, página e score em um diálogo", () => {
    render(<SourcePanel source={sampleSource} onClose={vi.fn()} onOpenDocument={vi.fn()} />);
    const dialog = screen.getByRole("dialog", { name: "Fonte [1]" });
    expect(dialog).toHaveTextContent("lei-13709.pdf");
    expect(dialog).toHaveTextContent("Página3");
    expect(dialog).toHaveTextContent("0,812");
    expect(dialog).toHaveTextContent(sampleSource.text);
    expect(screen.getByRole("button", { name: /Fechar/ })).toHaveFocus();
  });

  it("abre o documento na página citada", async () => {
    const open = vi.fn().mockResolvedValue(undefined);
    render(<SourcePanel source={sampleSource} onClose={vi.fn()} onOpenDocument={open} />);
    await userEvent.click(screen.getByRole("button", { name: "Abrir documento (abre em nova aba)" }));
    expect(open).toHaveBeenCalledWith({ documentId: "doc-1", filename: "lei-13709.pdf", page: 3 });
  });

  it("oferece download para DOCX e mostra erro acessível", async () => {
    const open = vi.fn().mockRejectedValue(new ApiError(404, "O recurso não foi encontrado."));
    render(<SourcePanel source={makeSource({ filename: "ata.docx" })} onClose={vi.fn()} onOpenDocument={open} />);
    await userEvent.click(screen.getByRole("button", { name: "Baixar documento" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("O recurso não foi encontrado.");
  });

  it("fecha pelo botão", async () => {
    const onClose = vi.fn();
    render(<SourcePanel source={sampleSource} onClose={onClose} onOpenDocument={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /Fechar/ }));
    expect(onClose).toHaveBeenCalled();
  });

  it("não tem violações de acessibilidade (axe, WCAG 2.1 AA)", async () => {
    const { container } = render(<SourcePanel source={sampleSource} onClose={vi.fn()} onOpenDocument={vi.fn()} />);
    expect(await axeViolations(container)).toEqual([]);
  });
});
