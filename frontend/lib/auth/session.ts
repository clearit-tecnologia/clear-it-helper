// Armazenamento do token de acesso.
//
// TODO(Fase 6): substituir por cookie HttpOnly/Secure/SameSite emitido pelo
// backend (ou sessão OIDC via Keycloak). sessionStorage é aceito só na Fase 0:
// fica acessível a JavaScript e, portanto, exposto a XSS.

const TOKEN_KEY = "clear-helper.access_token";
const EXPIRES_KEY = "clear-helper.access_token_expires_at";

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function saveSession(accessToken: string, expiresInSeconds: number, now: number = Date.now()): void {
  const s = storage();
  if (!s) return;
  s.setItem(TOKEN_KEY, accessToken);
  s.setItem(EXPIRES_KEY, String(now + expiresInSeconds * 1000));
}

export function getAccessToken(now: number = Date.now()): string | null {
  const s = storage();
  if (!s) return null;
  const token = s.getItem(TOKEN_KEY);
  const expiresAt = Number(s.getItem(EXPIRES_KEY));
  if (!token) return null;
  if (Number.isFinite(expiresAt) && expiresAt > 0 && expiresAt <= now) {
    clearSession();
    return null;
  }
  return token;
}

export function clearSession(): void {
  const s = storage();
  if (!s) return;
  s.removeItem(TOKEN_KEY);
  s.removeItem(EXPIRES_KEY);
}
