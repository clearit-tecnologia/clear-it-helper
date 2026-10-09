import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, getCurrentUser, getReadiness, login } from "@/lib/api/client";
import { getAccessToken, saveSession } from "@/lib/auth/session";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const readyBody = {
  status: "degraded",
  checks: {
    postgres: { status: "error", latency_ms: 1.2, detail: "connection refused" },
    redis: { status: "ok", latency_ms: 0.5, detail: null },
  },
};

describe("cliente de API", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("faz login via caminho relativo /api/auth/login com JSON", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ access_token: "tok", token_type: "bearer", expires_in: 3600 }));

    const result = await login({ email: "a@b.gov.br", password: "x" });

    expect(result.access_token).toBe("tok");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/auth/login");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ email: "a@b.gov.br", password: "x" });
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("traduz 401 do login para mensagem em pt-BR", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "invalid" }, 401));

    await expect(login({ email: "a@b.gov.br", password: "x" })).rejects.toMatchObject({
      status: 401,
      message: "E-mail ou senha incorretos.",
    });
  });

  it("converte falha de rede em ApiError com status 0", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    const error = await login({ email: "a@b.gov.br", password: "x" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
  });

  it("envia o Bearer token em /api/auth/me", async () => {
    saveSession("meu-token", 3600);
    const user = { id: "1", email: "a@b.gov.br", role: "admin", tenant: { id: "t", name: "Órgão", slug: "orgao" } };
    fetchMock.mockResolvedValue(jsonResponse(user));

    await expect(getCurrentUser()).resolves.toEqual(user);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/auth/me");
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer meu-token");
  });

  it("não chama a API sem token e responde 401", async () => {
    await expect(getCurrentUser()).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("limpa a sessão quando /auth/me responde 401", async () => {
    saveSession("expirado", 3600);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "expired" }, 401));

    await expect(getCurrentUser()).rejects.toMatchObject({ status: 401 });
    expect(getAccessToken()).toBeNull();
  });

  it("aceita 503 em /api/health/ready e devolve o corpo", async () => {
    fetchMock.mockResolvedValue(jsonResponse(readyBody, 503));

    const result = await getReadiness();
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/health/ready");
    expect(result.status).toBe("degraded");
    expect(result.checks.postgres?.status).toBe("error");
  });

  it("rejeita 503 sem corpo JSON válido (ex.: ingress sem backend)", async () => {
    fetchMock.mockResolvedValue(new Response("Service Unavailable", { status: 503 }));

    await expect(getReadiness()).rejects.toBeInstanceOf(ApiError);
  });

  it("rejeita outros erros HTTP em /health/ready", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, 500));

    await expect(getReadiness()).rejects.toMatchObject({ status: 500 });
  });
});
