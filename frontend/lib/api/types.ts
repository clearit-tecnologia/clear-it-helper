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

// Phase 1 types (docs/arquitetura/fase-1-contrato.md).

export type DocumentStatus = "uploaded" | "processing" | "indexed" | "failed";

export interface DocumentItem {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: DocumentStatus;
  error: string | null;
  page_count: number | null;
  chunk_count: number | null;
  pipeline_version: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentItem[];
}

/** Retrieved chunk. `ref` is the number used in the `[n]` citation. */
export interface Source {
  ref: number;
  document_id: string;
  filename: string;
  page: number;
  chunk_index: number;
  score: number;
  text: string;
}

export interface SearchResponse {
  results: Source[];
}

export type ChatRole = "user" | "assistant";

export interface ChatHistoryEntry {
  role: ChatRole;
  content: string;
}

export interface ChatRequest {
  question: string;
  history: ChatHistoryEntry[];
}

export interface ChatDoneEvent {
  answer: string;
  refused: boolean;
  usage: Record<string, unknown> | null;
  latency_ms: number;
}
