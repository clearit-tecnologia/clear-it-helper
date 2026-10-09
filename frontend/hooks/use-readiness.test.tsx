import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { READINESS_INTERVAL_MS, useReadiness } from "@/hooks/use-readiness";

const body = { status: "ok", checks: { postgres: { status: "ok", latency_ms: 1, detail: null } } };

describe("useReadiness", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchMock.mockReset();
    fetchMock.mockImplementation(async () => new Response(JSON.stringify(body), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("consulta ao montar e repete a cada 15 segundos", async () => {
    expect(READINESS_INTERVAL_MS).toBe(15_000);
    const { result } = renderHook(() => useReadiness());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.status).toBe("ok");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(READINESS_INTERVAL_MS);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("expõe a mensagem de erro quando a API falha", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const { result } = renderHook(() => useReadiness());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toMatch(/Não foi possível conectar/);
    expect(result.current.data).toBeNull();
  });
});
