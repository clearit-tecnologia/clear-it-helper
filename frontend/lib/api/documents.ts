import {
  API_BASE,
  ApiError,
  apiRequest,
  authHeaders,
  defaultMessage,
  isAbortError,
  NETWORK_ERROR,
  readErrorBody,
} from "@/lib/api/client";
import { clearSession } from "@/lib/auth/session";
import type { DocumentItem, DocumentListResponse } from "@/lib/api/types";

/**
 * Contract default (`CH_UPLOAD_MAX_MB`). The server is the authority: if it changes
 * there, 413 is still handled; this only avoids pointless uploads.
 */
export const UPLOAD_MAX_MB = 50;
export const UPLOAD_MAX_BYTES = UPLOAD_MAX_MB * 1024 * 1024;

/** Phase 1 accepted extensions (native-text PDF, DOCX, TXT, Markdown and HTML). */
export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md", ".markdown", ".html", ".htm"] as const;
export const ACCEPTED_FORMATS_LABEL = "PDF, DOCX, TXT, MD ou HTML";

export const UNSUPPORTED_TYPE_MESSAGE = `Formato não suportado. Envie arquivos ${ACCEPTED_FORMATS_LABEL}.`;
export const TOO_LARGE_MESSAGE = `O arquivo excede o limite de ${UPLOAD_MAX_MB} MB.`;

/** Re-upload of a file that already exists in the tenant (409). */
export class DuplicateDocumentError extends ApiError {
  readonly documentId: string | null;

  constructor(documentId: string | null, body: unknown) {
    super(409, "Este arquivo já foi enviado anteriormente.", body);
    this.name = "DuplicateDocumentError";
    this.documentId = documentId;
  }
}

export function fileExtension(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot < 0 ? "" : filename.slice(dot).toLowerCase();
}

/** Client-side validation before upload. Returns the error message or `null`. */
export function validateUploadFile(file: File): string | null {
  if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(fileExtension(file.name))) return UNSUPPORTED_TYPE_MESSAGE;
  if (file.size > UPLOAD_MAX_BYTES) return TOO_LARGE_MESSAGE;
  if (file.size === 0) return "O arquivo está vazio.";
  return null;
}

export async function listDocuments(signal?: AbortSignal): Promise<DocumentItem[]> {
  const data = await apiRequest<DocumentListResponse>("/documents", { auth: true, signal });
  if (!data || !Array.isArray(data.items)) throw new ApiError(502, "Resposta inesperada do servidor.");
  return data.items;
}

export function getDocument(id: string, signal?: AbortSignal): Promise<DocumentItem> {
  return apiRequest<DocumentItem>(`/documents/${encodeURIComponent(id)}`, { auth: true, signal });
}

export async function uploadDocument(file: File, signal?: AbortSignal): Promise<DocumentItem> {
  const form = new FormData();
  form.append("file", file, file.name);
  try {
    return await apiRequest<DocumentItem>("/documents", { method: "POST", body: form, auth: true, signal });
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 409) {
      const body = error.body as { document_id?: unknown } | null;
      const documentId = body && typeof body.document_id === "string" ? body.document_id : null;
      throw new DuplicateDocumentError(documentId, error.body);
    }
    if (error.status === 413) throw new ApiError(413, TOO_LARGE_MESSAGE, error.body);
    if (error.status === 415) throw new ApiError(415, UNSUPPORTED_TYPE_MESSAGE, error.body);
    throw error;
  }
}

export function deleteDocument(id: string, signal?: AbortSignal): Promise<void> {
  return apiRequest<void>(`/documents/${encodeURIComponent(id)}`, { method: "DELETE", auth: true, signal });
}

export function reprocessDocument(id: string, signal?: AbortSignal): Promise<void> {
  return apiRequest<void>(`/documents/${encodeURIComponent(id)}/reprocess`, {
    method: "POST",
    auth: true,
    signal,
    parseJson: false,
  });
}

export interface DocumentFile {
  blob: Blob;
  contentType: string;
}

/** Downloads the original file with the Bearer token (a plain link cannot send it). */
export async function fetchDocumentFile(id: string, signal?: AbortSignal): Promise<DocumentFile> {
  const headers = authHeaders();
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/documents/${encodeURIComponent(id)}/file`, {
      headers,
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError(0, NETWORK_ERROR);
  }
  if (!response.ok) {
    if (response.status === 401) clearSession();
    throw new ApiError(response.status, defaultMessage(response.status), await readErrorBody(response));
  }
  const blob = await response.blob();
  return { blob, contentType: response.headers.get("Content-Type") ?? blob.type };
}
