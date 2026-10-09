"use client";

import { useId, useRef, useState, type ChangeEvent, type DragEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { UploadOutcome } from "@/hooks/use-documents";
import { ACCEPTED_EXTENSIONS, ACCEPTED_FORMATS_LABEL, UPLOAD_MAX_MB } from "@/lib/api/documents";
import { cn } from "@/lib/utils";

export interface DocumentUploadProps {
  isUploading: boolean;
  onUpload: (files: File[]) => Promise<UploadOutcome[]>;
  /** Highlights an existing document (409 duplicate). */
  onShowDocument: (documentId: string) => void;
}

function summarize(outcomes: UploadOutcome[]): string {
  const ok = outcomes.filter((o) => o.kind === "success").length;
  const dup = outcomes.filter((o) => o.kind === "duplicate").length;
  const failed = outcomes.filter((o) => o.kind === "error").length;
  const parts: string[] = [];
  if (ok) parts.push(ok === 1 ? "1 arquivo enviado" : `${ok} arquivos enviados`);
  if (dup) parts.push(dup === 1 ? "1 já existente" : `${dup} já existentes`);
  if (failed) parts.push(failed === 1 ? "1 com erro" : `${failed} com erro`);
  return `${parts.join(", ")}.`;
}

export function DocumentUpload({ isUploading, onUpload, onShowDocument }: DocumentUploadProps) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [outcomes, setOutcomes] = useState<UploadOutcome[] | null>(null);

  async function handleFiles(list: FileList | null) {
    const files = list ? Array.from(list) : [];
    if (files.length === 0 || isUploading) return;
    setOutcomes(null);
    setOutcomes(await onUpload(files));
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const { files } = event.target;
    void handleFiles(files).finally(() => {
      // Lets the same file be selected again.
      if (inputRef.current) inputRef.current.value = "";
    });
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    if (!isDragging) setIsDragging(true);
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    setIsDragging(false);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    void handleFiles(event.dataTransfer.files);
  }

  return (
    <section aria-labelledby={`${id}-title`}>
      <Card>
        <CardHeader>
          <CardTitle id={`${id}-title`}>Enviar documentos</CardTitle>
          <CardDescription id={`${id}-hint`}>
            Formatos aceitos: {ACCEPTED_FORMATS_LABEL}. Tamanho máximo: {UPLOAD_MAX_MB} MB por arquivo.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Alert>
            <strong className="font-semibold">PDFs escaneados ainda não são suportados.</strong> O texto do PDF
            precisa ser selecionável; o reconhecimento de texto em imagens (OCR) chega na Fase 2.
          </Alert>

          {/* Drop target only (pointer shortcut); the button below is the keyboard and screen reader path. */}
          {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions -- drag-and-drop has an equivalent native button */}
          <div
            data-testid="upload-dropzone"
            onDragEnter={handleDragOver}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={cn(
              "flex flex-col items-center justify-center gap-3 rounded-md border-2 border-dashed border-input bg-muted p-6 text-center transition-colors",
              isDragging && "border-primary bg-secondary",
            )}
          >
            <p className="text-sm text-muted-foreground">
              {isDragging ? "Solte os arquivos para enviar." : "Arraste arquivos para esta área ou"}
            </p>
            <Button
              onClick={() => inputRef.current?.click()}
              disabled={isUploading}
              aria-describedby={`${id}-hint`}
            >
              {isUploading ? "Enviando…" : "Selecionar arquivos"}
            </Button>
            <input
              ref={inputRef}
              id={`${id}-input`}
              data-testid="upload-input"
              type="file"
              multiple
              hidden
              accept={ACCEPTED_EXTENSIONS.join(",")}
              onChange={handleChange}
            />
          </div>

          <div role="status" aria-live="polite" className="flex flex-col gap-2 text-sm">
            {isUploading && <p>Enviando arquivos…</p>}
            {outcomes && outcomes.length > 0 && (
              <>
                <p className="font-medium">{summarize(outcomes)}</p>
                <ul className="flex flex-col gap-2" aria-label="Resultado do envio">
                  {outcomes.map((outcome, index) => (
                    <li key={`${outcome.filename}-${index}`} className="rounded-md border p-3">
                      <span className="font-medium break-words">{outcome.filename}</span>
                      {outcome.kind === "success" && (
                        <span className="block text-success">Enviado. O processamento começou.</span>
                      )}
                      {outcome.kind === "duplicate" && (
                        <span className="flex flex-wrap items-center gap-x-2">
                          <span>Este arquivo já foi enviado anteriormente.</span>
                          {outcome.documentId && (
                            <Button
                              variant="link"
                              className="h-auto p-0"
                              onClick={() => onShowDocument(outcome.documentId as string)}
                            >
                              Ver documento existente
                            </Button>
                          )}
                        </span>
                      )}
                      {outcome.kind === "error" && (
                        <span className="block text-destructive">{outcome.message}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
