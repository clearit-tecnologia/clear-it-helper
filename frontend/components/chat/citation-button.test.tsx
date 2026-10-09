import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AnswerContent, CitationButton, splitCitations } from "@/components/chat/citation-button";
import { makeSource, sampleSource } from "@/lib/test-utils/fixtures";
import { axeViolations } from "@/lib/test-utils/axe";

const second = makeSource({ ref: 2, filename: "lei-14133.pdf", page: 10 });

describe("citações", () => {
  it("separa texto e citações, incluindo [1, 2], e ignora refs sem fonte", () => {
    const segments = splitCitations("Sim [1]. Também [1, 2]. Fora [9].", [sampleSource, second]);
    expect(segments.map((s) => (s.kind === "text" ? s.text : s.sources.map((x) => x.ref).join("+")))).toEqual([
      "Sim ",
      "1",
      ". Também ",
      "1+2",
      ". Fora [9].",
    ]);
  });

  it("botão tem nome acessível que começa pelo texto visível e abre a fonte", async () => {
    const onOpen = vi.fn();
    render(<CitationButton source={sampleSource} onOpen={onOpen} />);
    const button = screen.getByRole("button", { name: "[1] ver fonte: lei-13709.pdf, página 3" });
    await userEvent.click(button);
    expect(onOpen).toHaveBeenCalledWith(sampleSource);
  });

  it("renderiza a resposta como texto com citações clicáveis por teclado", async () => {
    const onOpen = vi.fn();
    render(
      <AnswerContent text={"<b>não é HTML</b> conforme [2]."} sources={[sampleSource, second]} onOpenSource={onOpen} />,
    );
    expect(screen.getByText("<b>não é HTML</b> conforme", { exact: false })).toBeInTheDocument();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: /^\[2\]/ })).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(onOpen).toHaveBeenCalledWith(second);
  });

  it("não tem violações de acessibilidade (axe, WCAG 2.1 AA)", async () => {
    const { container } = render(
      <AnswerContent text="Resposta [1] e [2]." sources={[sampleSource, second]} onOpenSource={vi.fn()} />,
    );
    expect(await axeViolations(container)).toEqual([]);
  });
});
