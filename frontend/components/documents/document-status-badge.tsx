import type { DocumentStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const DOCUMENT_STATUS_LABELS: Record<DocumentStatus, string> = {
  uploaded: "Enviado",
  processing: "Processando",
  indexed: "Indexado",
  failed: "Falhou",
};

const STATUS_STYLES: Record<DocumentStatus, { symbol: string; className: string }> = {
  uploaded: { symbol: "↑", className: "border border-input text-foreground" },
  processing: { symbol: "…", className: "border border-primary text-primary" },
  indexed: { symbol: "✓", className: "bg-success text-success-foreground" },
  failed: { symbol: "✕", className: "bg-destructive text-destructive-foreground" },
};

/** Status shown with text and symbol, not color alone (WCAG 1.4.1). */
export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.uploaded;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        style.className,
      )}
    >
      <span aria-hidden="true">{style.symbol}</span>
      {DOCUMENT_STATUS_LABELS[status] ?? status}
    </span>
  );
}
