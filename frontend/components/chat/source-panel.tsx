"use client";

import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import type { Source } from "@/lib/api/types";
import { openDocument, openModeFor } from "@/lib/documents/open-document";
import { formatScore } from "@/lib/format";

export interface SourcePanelProps {
  source: Source | null;
  onClose: () => void;
  /** Injectable for tests. */
  onOpenDocument?: typeof openDocument;
}

/** Side panel (drawer on small screens) with the cited chunk and its origin. */
export function SourcePanel({ source, onClose, onOpenDocument = openDocument }: SourcePanelProps) {
  const id = useId();
  const [isOpening, setIsOpening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    setIsOpening(false);
  }, [source]);

  async function handleOpen() {
    if (!source) return;
    setIsOpening(true);
    setError(null);
    try {
      await onOpenDocument({ documentId: source.document_id, filename: source.filename, page: source.page });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível abrir o documento.");
    } finally {
      setIsOpening(false);
    }
  }

  const downloads = source ? openModeFor(source.filename) === "download" : false;

  return (
    <Dialog open={source !== null} onClose={onClose} labelledBy={`${id}-title`} variant="sheet">
      {source && (
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between gap-4 border-b p-4">
            <h2 id={`${id}-title`} className="text-lg font-semibold">
              Fonte [{source.ref}]
            </h2>
            <Button variant="outline" size="sm" onClick={onClose} data-autofocus>
              Fechar<span className="sr-only"> painel da fonte</span>
            </Button>
          </div>

          <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Arquivo</dt>
              <dd className="break-all font-medium">{source.filename}</dd>
              <dt className="text-muted-foreground">Página</dt>
              <dd>{source.page}</dd>
              <dt className="text-muted-foreground">Similaridade</dt>
              <dd>{formatScore(source.score)}</dd>
            </dl>

            <figure className="flex flex-col gap-2">
              <figcaption className="text-sm font-semibold">Trecho usado na resposta</figcaption>
              <blockquote className="whitespace-pre-wrap break-words rounded-md border-l-4 border-primary bg-muted p-3 text-sm leading-relaxed">
                {source.text}
              </blockquote>
            </figure>

            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </div>

          <div className="border-t p-4">
            <Button onClick={() => void handleOpen()} disabled={isOpening} className="w-full sm:w-auto">
              {isOpening ? "Abrindo…" : downloads ? "Baixar documento" : "Abrir documento"}
              {!isOpening && !downloads && <span className="sr-only"> (abre em nova aba)</span>}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
