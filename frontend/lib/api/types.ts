// Tipos espelhando o contrato da Fase 0 (docs/arquitetura/fase-0-contrato.md).

export type CheckStatus = "ok" | "error";

export interface DependencyCheck {
  status: CheckStatus;
  latency_ms: number | null;
  detail: string | null;
}

export const DEPENDENCIES = ["postgres", "redis", "qdrant", "s3", "litellm"] as const;
export type DependencyName = (typeof DEPENDENCIES)[number];

export interface ReadinessResponse {
  status: "ok" | "degraded";
  /** Chaves conhecidas do contrato; dependências extras são aceitas e exibidas. */
  checks: Partial<Record<DependencyName, DependencyCheck>> & Record<string, DependencyCheck | undefined>;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
}

export type UserRole = "admin" | "member";

export interface CurrentUser {
  id: string;
  email: string;
  role: UserRole;
  tenant: Tenant;
}
