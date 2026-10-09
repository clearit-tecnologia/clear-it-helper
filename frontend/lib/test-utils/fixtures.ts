import type { DocumentItem, Source } from "@/lib/api/types";

export const sampleDocument: DocumentItem = {
  id: "doc-1",
  filename: "lei.pdf",
  content_type: "application/pdf",
  size_bytes: 1024,
  status: "uploaded",
  error: null,
  page_count: null,
  chunk_count: null,
  pipeline_version: null,
  created_at: "2026-10-09T13:00:00Z",
  updated_at: "2026-10-09T13:00:00Z",
};

export function makeDocument(patch: Partial<DocumentItem> = {}): DocumentItem {
  return { ...sampleDocument, ...patch };
}

export const sampleSource: Source = {
  ref: 1,
  document_id: "doc-1",
  filename: "lei-13709.pdf",
  page: 3,
  chunk_index: 4,
  score: 0.8123,
  text: "Art. 18. O titular dos dados pessoais tem direito a obter do controlador...",
};

export function makeSource(patch: Partial<Source> = {}): Source {
  return { ...sampleSource, ...patch };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
