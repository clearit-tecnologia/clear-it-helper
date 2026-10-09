import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppHeader } from "@/components/layout/app-header";
import type { CurrentUser } from "@/lib/api/types";
import { axeViolations } from "@/lib/test-utils/axe";

vi.mock("next/navigation", () => ({ usePathname: () => "/documentos" }));

const user: CurrentUser = {
  id: "1",
  email: "admin@orgao.gov.br",
  role: "admin",
  tenant: { id: "t", name: "Órgão", slug: "orgao" },
};

describe("AppHeader", () => {
  it("navega entre Chat, Documentos e Status marcando a página atual", () => {
    render(<AppHeader user={user} onLogout={vi.fn()} />);
    const nav = within(screen.getByRole("navigation", { name: "Principal" }));
    expect(nav.getByRole("link", { name: "Chat" })).toHaveAttribute("href", "/");
    expect(nav.getByRole("link", { name: "Chat" })).not.toHaveAttribute("aria-current");
    expect(nav.getByRole("link", { name: "Documentos" })).toHaveAttribute("aria-current", "page");
    expect(nav.getByRole("link", { name: "Status" })).toHaveAttribute("href", "/status");
  });

  it("não tem violações de acessibilidade (axe, WCAG 2.1 AA)", async () => {
    const { container } = render(<AppHeader user={user} onLogout={vi.fn()} />);
    expect(await axeViolations(container)).toEqual([]);
  });
});
