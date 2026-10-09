import { describe, expect, it } from "vitest";

import { clearSession, getAccessToken, saveSession } from "@/lib/auth/session";

describe("sessão", () => {
  it("salva e lê o token", () => {
    saveSession("abc", 60, 1_000);
    expect(getAccessToken(1_000)).toBe("abc");
  });

  it("descarta token expirado", () => {
    saveSession("abc", 60, 1_000);
    expect(getAccessToken(1_000 + 61_000)).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });

  it("limpa a sessão", () => {
    saveSession("abc", 60);
    clearSession();
    expect(getAccessToken()).toBeNull();
  });
});
