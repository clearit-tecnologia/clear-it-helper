import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/login-form";
import { getAccessToken } from "@/lib/auth/session";
import { axeViolations } from "@/lib/test-utils/axe";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

describe("LoginForm", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    replace.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("valida campos obrigatórios com mensagens associadas", async () => {
    render(<LoginForm />);
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    const email = screen.getByLabelText("E-mail");
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(email).toHaveAccessibleDescription("Informe o e-mail.");
    expect(email).toHaveFocus();
    expect(screen.getByLabelText("Senha")).toHaveAccessibleDescription("Informe a senha.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("autentica, guarda o token e redireciona", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ access_token: "tok", token_type: "bearer", expires_in: 3600 }), { status: 200 }),
    );
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText("E-mail"), "admin@orgao.gov.br");
    await userEvent.type(screen.getByLabelText("Senha"), "segredo");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(getAccessToken()).toBe("tok");
    expect(replace).toHaveBeenCalledWith("/");
  });

  it("anuncia credenciais inválidas e devolve o foco à senha", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "invalid" }), { status: 401 }));
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText("E-mail"), "admin@orgao.gov.br");
    await userEvent.type(screen.getByLabelText("Senha"), "errada");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("E-mail ou senha incorretos.");
    expect(screen.getByLabelText("Senha")).toHaveFocus();
    expect(screen.getByLabelText("Senha")).toHaveValue("");
    expect(replace).not.toHaveBeenCalled();
  });

  it("não tem violações de acessibilidade (axe, WCAG 2.1 AA)", async () => {
    const { container } = render(<LoginForm />);
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await axeViolations(container)).toEqual([]);
  });
});
