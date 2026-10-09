import { fetchDocumentFile, fileExtension } from "@/lib/api/documents";

/** Blob URLs are kept alive long enough for the new tab to load them. */
const REVOKE_AFTER_MS = 60_000;

type OpenMode = "pdf" | "text" | "download";

const TEXT_EXTENSIONS = new Set([".txt", ".md", ".markdown", ".html", ".htm"]);

export function openModeFor(filename: string, contentType = ""): OpenMode {
  const ext = fileExtension(filename);
  if (ext === ".pdf" || contentType.startsWith("application/pdf")) return "pdf";
  if (TEXT_EXTENSIONS.has(ext) || contentType.startsWith("text/")) return "text";
  return "download";
}

export interface OpenDocumentOptions {
  documentId: string;
  filename: string;
  /** 1-based page; appended as `#page=N` for PDFs. */
  page?: number | null;
}

/**
 * Fetches `GET /api/documents/{id}/file` with the Bearer token and shows it:
 * - PDF: new tab with `#page=N`;
 * - TXT/MD/HTML: new tab as **text/plain**. A blob URL shares this app's origin, so
 *   rendering uploaded HTML would run its scripts with access to the session token;
 * - other formats (DOCX): downloaded with the original filename.
 *
 * The tab is opened synchronously (inside the click) so popup blockers allow it,
 * then navigated once the file arrives.
 */
export async function openDocument({ documentId, filename, page }: OpenDocumentOptions): Promise<void> {
  const expected = openModeFor(filename);
  const tab = expected === "download" ? null : window.open("", "_blank");
  if (tab) {
    try {
      tab.opener = null;
      tab.document.title = filename;
      tab.document.body.textContent = "Carregando documento…";
    } catch {
      // Cross-origin or restricted window: navigation below still works.
    }
  }

  try {
    const { blob, contentType } = await fetchDocumentFile(documentId);
    const mode = openModeFor(filename, contentType);
    const typed =
      mode === "pdf"
        ? new Blob([blob], { type: "application/pdf" })
        : mode === "text"
          ? new Blob([blob], { type: "text/plain;charset=utf-8" })
          : blob;
    const url = URL.createObjectURL(typed);
    window.setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS);

    if (mode === "download" || !tab) {
      const link = document.createElement("a");
      link.href = mode === "pdf" && page ? `${url}#page=${page}` : url;
      if (mode === "download") link.download = filename;
      else {
        link.target = "_blank";
        link.rel = "noopener";
      }
      document.body.appendChild(link);
      link.click();
      link.remove();
      tab?.close();
      return;
    }

    tab.location.href = mode === "pdf" && page ? `${url}#page=${page}` : url;
  } catch (error) {
    tab?.close();
    throw error;
  }
}
