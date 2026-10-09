import { clearSession, getAccessToken } from "@/lib/auth/session";
import type { CurrentUser, LoginRequest, LoginResponse, ReadinessResponse } from "@/lib/api/types";

/**
 * Prefixo fixo e relativo: em produção o ingress encaminha `/api/*` para a API
 * removendo o prefixo; no `next dev`, o rewrite de next.config.ts faz o mesmo.
 */
export const API_BASE = "/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  /** Envia `Authorization: Bearer <token>` com o token da sessão. */
  auth?: boolean;
  /** Status HTTP não-2xx cujo corpo JSON deve ser devolvido normalmente. */
  acceptStatus?: readonly number[];
  signal?: AbortSignal;
}

const NETWORK_ERROR = "Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente.";

function defaultMessage(status: number): string {
  if (status === 401) return "Sua sessão expirou ou as credenciais são inválidas.";
  if (status === 403) return "Você não tem permissão para acessar este recurso.";
  if (status >= 500) return "O servidor está indisponível no momento. Tente novamente em instantes.";
  return "Não foi possível concluir a solicitação.";
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = false, acceptStatus = [], signal } = options;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  if (auth) {
    const token = getAccessToken();
    if (!token) throw new ApiError(401, defaultMessage(401));
    headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, NETWORK_ERROR);
  }

  if (!response.ok && !acceptStatus.includes(response.status)) {
    if (response.status === 401 && auth) clearSession();
    throw new ApiError(response.status, defaultMessage(response.status));
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(response.status, "Resposta inesperada do servidor.");
  }
}

export function login(credentials: LoginRequest, signal?: AbortSignal): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/auth/login", { method: "POST", body: credentials, signal }).catch(
    (error: unknown) => {
      if (error instanceof ApiError && error.status === 401) {
        throw new ApiError(401, "E-mail ou senha incorretos.");
      }
      throw error;
    },
  );
}

export function getCurrentUser(signal?: AbortSignal): Promise<CurrentUser> {
  return apiRequest<CurrentUser>("/auth/me", { auth: true, signal });
}

/** A API responde 503 (com o mesmo corpo) quando o PostgreSQL está fora. */
export async function getReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  const data = await apiRequest<ReadinessResponse>("/health/ready", { acceptStatus: [503], signal });
  if (!data || typeof data !== "object" || typeof data.checks !== "object" || data.checks === null) {
    throw new ApiError(502, "Resposta inesperada do servidor.");
  }
  return data;
}
