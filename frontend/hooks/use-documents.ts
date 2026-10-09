"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, isAbortError } from "@/lib/api/client";
import {
  deleteDocument,
  DuplicateDocumentError,
  listDocuments,
  reprocessDocument,
  uploadDocument,
  validateUploadFile,
} from "@/lib/api/documents";
import type { DocumentItem } from "@/lib/api/types";

/** Poll interval while any document is `uploaded` or `processing`. */
export const DOCUMENTS_POLL_INTERVAL_MS = 3_000;

export type UploadOutcome =
  | { filename: string; kind: "success"; document: DocumentItem }
  | { filename: string; kind: "duplicate"; documentId: string | null }
  | { filename: string; kind: "error"; message: string };

export function isPending(doc: DocumentItem): boolean {
  return doc.status === "uploaded" || doc.status === "processing";
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export interface DocumentsState {
  documents: DocumentItem[];
  isLoading: boolean;
  error: string | null;
  isUploading: boolean;
  refresh: () => Promise<void>;
  upload: (files: File[]) => Promise<UploadOutcome[]>;
  remove: (id: string) => Promise<void>;
  reprocess: (id: string) => Promise<void>;
}

export function useDocuments(pollIntervalMs: number = DOCUMENTS_POLL_INTERVAL_MS): DocumentsState {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      const items = await listDocuments(controller.signal);
      setDocuments(items);
      setError(null);
    } catch (err) {
      if (controller.signal.aborted || isAbortError(err)) return;
      setError(errorMessage(err, "Não foi possível carregar os documentos."));
    } finally {
      if (!controller.signal.aborted) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => controllerRef.current?.abort();
  }, [load]);

  const hasPending = documents.some(isPending);

  // Polls only while ingestion is in progress and the tab is visible.
  useEffect(() => {
    if (!hasPending) return;
    const id = window.setInterval(() => {
      if (document.visibilityState !== "hidden") void load();
    }, pollIntervalMs);
    return () => window.clearInterval(id);
  }, [hasPending, load, pollIntervalMs]);

  const upload = useCallback(
    async (files: File[]): Promise<UploadOutcome[]> => {
      const outcomes: UploadOutcome[] = [];
      setIsUploading(true);
      try {
        // Sequential on purpose: keeps server load predictable and results ordered.
        for (const file of files) {
          const invalid = validateUploadFile(file);
          if (invalid) {
            outcomes.push({ filename: file.name, kind: "error", message: invalid });
            continue;
          }
          try {
            const created = await uploadDocument(file);
            outcomes.push({ filename: file.name, kind: "success", document: created });
          } catch (err) {
            if (err instanceof DuplicateDocumentError) {
              outcomes.push({ filename: file.name, kind: "duplicate", documentId: err.documentId });
            } else {
              outcomes.push({ filename: file.name, kind: "error", message: errorMessage(err, "Falha no envio.") });
            }
          }
        }
      } finally {
        setIsUploading(false);
      }
      await load();
      return outcomes;
    },
    [load],
  );

  const remove = useCallback(
    async (id: string) => {
      try {
        await deleteDocument(id);
      } catch (err) {
        // Already gone: just resync the list.
        if (!(err instanceof ApiError && err.status === 404)) throw err;
      }
      setDocuments((current) => current.filter((d) => d.id !== id));
      await load();
    },
    [load],
  );

  const reprocess = useCallback(
    async (id: string) => {
      await reprocessDocument(id);
      // Optimistic: shows "Enviado" right away so polling starts.
      setDocuments((current) =>
        current.map((d) => (d.id === id ? { ...d, status: "uploaded", error: null } : d)),
      );
      await load();
    },
    [load],
  );

  return { documents, isLoading, error, isUploading, refresh: load, upload, remove, reprocess };
}
