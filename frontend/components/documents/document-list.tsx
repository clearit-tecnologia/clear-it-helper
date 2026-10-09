import { DocumentStatusBadge } from "@/components/documents/document-status-badge";
import { Button } from "@/components/ui/button";
import { isPending } from "@/hooks/use-documents";
import type { DocumentItem } from "@/lib/api/types";
import { formatCount, formatDateTime, formatFileSize } from "@/lib/format";
import { cn } from "@/lib/utils";

export function documentElementId(id: string): string {
  return `documento-${id}`;
}

export interface DocumentListProps {
  documents: DocumentItem[];
  highlightedId: string | null;
  busyId: string | null;
  onDelete: (doc: DocumentItem) => void;
  onReprocess: (doc: DocumentItem) => void;
}

export function DocumentList({ documents, highlightedId, busyId, onDelete, onReprocess }: DocumentListProps) {
  return (
    <ul className="flex flex-col gap-3" aria-label="Documentos enviados">
      {documents.map((doc) => {
        const highlighted = doc.id === highlightedId;
        const busy = doc.id === busyId;
        return (
          <li
            key={doc.id}
            id={documentElementId(doc.id)}
            // Focus target for "Ver documento existente" (not in the tab order).
            tabIndex={-1}
            data-testid={`document-${doc.id}`}
            className={cn(
              "flex flex-col gap-3 rounded-md border p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              highlighted && "border-primary bg-secondary ring-2 ring-primary",
            )}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h3 className="break-all text-base font-semibold">
                {doc.filename}
                {highlighted && (
                  <span className="ml-2 align-middle text-xs font-medium text-primary">(arquivo já enviado)</span>
                )}
              </h3>
              <DocumentStatusBadge status={doc.status} />
            </div>

            {doc.status === "failed" && (
              <p className="text-sm text-destructive">
                <span className="font-medium">Erro: </span>
                {doc.error ?? "Falha no processamento."}
              </p>
            )}

            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm sm:grid-cols-4 sm:gap-x-6">
              <div className="contents sm:flex sm:flex-col">
                <dt className="text-muted-foreground">Páginas</dt>
                <dd>{formatCount(doc.page_count)}</dd>
              </div>
              <div className="contents sm:flex sm:flex-col">
                <dt className="text-muted-foreground">Trechos</dt>
                <dd>{formatCount(doc.chunk_count)}</dd>
              </div>
              <div className="contents sm:flex sm:flex-col">
                <dt className="text-muted-foreground">Tamanho</dt>
                <dd>{formatFileSize(doc.size_bytes)}</dd>
              </div>
              <div className="contents sm:flex sm:flex-col">
                <dt className="text-muted-foreground">Enviado em</dt>
                <dd>
                  <time dateTime={doc.created_at}>{formatDateTime(doc.created_at)}</time>
                </dd>
              </div>
            </dl>

            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => onReprocess(doc)}
                disabled={busy || isPending(doc)}
              >
                Reprocessar<span className="sr-only"> {doc.filename}</span>
              </Button>
              <Button variant="outline" size="sm" className="text-destructive" onClick={() => onDelete(doc)} disabled={busy}>
                Excluir<span className="sr-only"> {doc.filename}</span>
              </Button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
