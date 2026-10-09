import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { formatLatency, HealthStatusPanel, type HealthStatusPanelProps } from "@/components/health/health-status-panel";
import type { ReadinessResponse } from "@/lib/api/types";
import { axeViolations } from "@/lib/test-utils/axe";

const degraded: ReadinessResponse = {
  status: "degraded",
  checks: {
    postgres: { status: "ok", latency_ms: 2.345, detail: null },
    redis: { status: "ok", latency_ms: 0.8, detail: null },
    qdrant: { status: "error", latency_ms: 1500, detail: "timeout" },
    s3: { status: "ok", latency_ms: 12, detail: null },
    litellm: { status: "error", latency_ms: null, detail: "connection refused" },
  },
};

function renderPanel(overrides: Partial<HealthStatusPanelProps> = {}) {
  const props: HealthStatusPanelProps = {
    data: degraded,
    error: null,
    isLoading: false,
    isRefreshing: false,
    lastUpdated: new Date("2026-10-09T13:45:10Z"),
    onRefresh: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<HealthStatusPanel {...props} />) };
}

describe("HealthStatusPanel", () => {
  it("mostra um item por dependência com status, latência e detalhe", () => {
    renderPanel();

    for (const name of ["postgres", "redis", "qdrant", "s3", "litellm"]) {
      expect(screen.getByTestId(`dependency-${name}`)).toBeInTheDocument();
    }
    const qdrant = within(screen.getByTestId("dependency-qdrant"));
    expect(qdrant.getByRole("heading", { name: "Qdrant" })).toBeInTheDocument();
    expect(qdrant.getByText("Com erro")).toBeInTheDocument();
    expect(qdrant.getByText("1.500 ms")).toBeInTheDocument();
    expect(qdrant.getByText("timeout")).toBeInTheDocument();

    const postgres = within(screen.getByTestId("dependency-postgres"));
    expect(postgres.getByText("Operacional")).toBeInTheDocument();
    expect(postgres.getByText("2,3 ms")).toBeInTheDocument();

    expect(within(screen.getByTestId("dependency-litellm")).getAllByText("—")).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("Ambiente degradado");
  });

  it("indica dependência ausente na resposta como não informada", () => {
    renderPanel({ data: { status: "ok", checks: { postgres: { status: "ok", latency_ms: 1, detail: null } } } });

    expect(within(screen.getByTestId("dependency-redis")).getByText("Não informado")).toBeInTheDocument();
  });

  it("exibe estado de carregamento", () => {
    renderPanel({ data: null, isLoading: true, lastUpdated: null });

    expect(screen.getByRole("status")).toHaveTextContent("Verificando o ambiente");
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("exibe erro de forma acessível quando não há dados", () => {
    renderPanel({ data: null, error: "O servidor está indisponível no momento." });

    expect(screen.getByRole("alert")).toHaveTextContent("O servidor está indisponível");
    expect(screen.getByRole("status")).toHaveTextContent("Não foi possível verificar o ambiente.");
  });

  it("mantém o último resultado quando uma atualização falha", () => {
    renderPanel({ error: "Falha de rede." });

    expect(screen.getByRole("alert")).toHaveTextContent("Exibindo o último resultado obtido.");
    expect(screen.getByTestId("dependency-postgres")).toBeInTheDocument();
  });

  it("aciona a atualização manual pelo botão", async () => {
    const { props } = renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "Atualizar agora" }));
    expect(props.onRefresh).toHaveBeenCalledTimes(1);
  });

  it("não tem violações de acessibilidade (axe, WCAG 2.1 AA)", async () => {
    const { container } = renderPanel();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("formata latência em pt-BR", () => {
    expect(formatLatency(1234.56)).toBe("1.234,6 ms");
    expect(formatLatency(null)).toBe("—");
  });
});
