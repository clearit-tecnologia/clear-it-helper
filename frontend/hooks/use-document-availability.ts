"use client";

import { useEffect, useState } from "react";

import { isAbortError } from "@/lib/api/client";
import { listDocuments } from "@/lib/api/documents";

/**
 * - `none`: no documents at all;
 * - `pending`: documents exist but none is indexed yet;
 * - `unknown`: the list could not be loaded (chat stays usable).
 */
export type DocumentAvailability = "loading" | "none" | "pending" | "ready" | "unknown";

export function useDocumentAvailability(): DocumentAvailability {
  const [state, setState] = useState<DocumentAvailability>("loading");

  useEffect(() => {
    const controller = new AbortController();
    listDocuments(controller.signal)
      .then((items) => {
        if (items.some((d) => d.status === "indexed")) setState("ready");
        else setState(items.length === 0 ? "none" : "pending");
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbortError(error)) return;
        setState("unknown");
      });
    return () => controller.abort();
  }, []);

  return state;
}
