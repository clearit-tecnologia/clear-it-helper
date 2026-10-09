"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { DocumentList, documentElementId } from "@/components/documents/document-list";
import { DocumentUpload } from "@/components/documents/document-upload";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { isPending, useDocuments } from "@/hooks/use-documents";
import type { DocumentItem } from "@/lib/api/types";

export function DocumentsScreen() {
  const { documents, isLoading, error, isUploading, refresh, upload, remove, reprocess } = useDocuments();
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<DocumentItem | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [focusListTitle, setFocusListTitle] = useState(false);
  const listTitleRef = useRef<HTMLHeadingElement>(null);

  const showDocument = useCallback(
    (id: string) => {
      setHighlightedId(id);
      if (!documents.some((d) => d.id === id)) void refresh();
    },
    [documents, refresh],
  );

  // Moves focus to the highlighted document once it is in the list.
  useEffect(() => {
    if (!highlightedId) return;
    const element = document.getElementById(documentElementId(highlightedId));
    if (!element) return;
    element.focus();
    if (typeof element.scrollIntoView === "function") element.scrollIntoView({ block: "center" });
  }, [highlightedId, documents]);

  // The deleted item's button is gone, so focus goes to the list title instead of <body>.
  // Runs after the dialog's own focus restoration (child effects run first).
  useEffect(() => {
    if (!focusListTitle || pendingDelete) return;
    listTitleRef.current?.focus();
    setFocusListTitle(false);
  }, [focusListTitle, pendingDelete]);

  async function confirmDelete() {
    if (!pendingDelete) return;
    const doc = pendingDelete;
    setBusyId(doc.id);
    setActionError(null);
    try {
      await remove(doc.id);
      setNotice(`Documento “${doc.filename}” excluído.`);
      setFocusListTitle(true);
      if (highlightedId === doc.id) setHighlightedId(null);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Não foi possível excluir o documento.");
    } finally {
      setBusyId(null);
      setPendingDelete(null);
    }
  }

  async function handleReprocess(doc: DocumentItem) {
    setBusyId(doc.id);
    setActionError(null);
    try {
      await reprocess(doc.id);
      setNotice(`Reprocessamento de “${doc.filename}” iniciado.`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Não foi possível reprocessar o documento.");
    } finally {
      setBusyId(null);
    }
  }

  const hasPending = documents.some(isPending);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Documentos</h1>

      <DocumentUpload isUploading={isUploading} onUpload={upload} onShowDocument={showDocument} />

      <section aria-labelledby="documents-title" aria-busy={isLoading}>
        <Card>
          <CardHeader className="sm:flex-row sm:items-start sm:justify-between sm:gap-4">
            <div className="flex flex-col gap-1.5">
              <CardTitle id="documents-title" ref={listTitleRef} tabIndex={-1} className="focus-visible:outline-none">
                Seus documentos
              </CardTitle>
              <CardDescription>
                {hasPending
                  ? "A lista é atualizada automaticamente enquanto houver documentos em processamento."
                  : "Somente documentos indexados são usados nas respostas do chat."}
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={() => void refresh()} className="mt-2 sm:mt-0">
              Atualizar lista
            </Button>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <p role="status" aria-live="polite" className="text-sm empty:hidden">
              {notice}
            </p>
            {actionError && (
              <p role="alert" className="text-sm text-destructive">
                {actionError}
              </p>
            )}

            {isLoading ? (
              <p className="text-sm text-muted-foreground">Carregando documentos…</p>
            ) : error && documents.length === 0 ? (
              <div className="flex flex-col items-start gap-3">
                <p role="alert" className="text-sm text-destructive">
                  {error}
                </p>
                <Button variant="outline" onClick={() => void refresh()}>
                  Tentar novamente
                </Button>
              </div>
            ) : documents.length === 0 ? (
              <p className="rounded-md border border-dashed border-input bg-muted p-6 text-center text-sm text-muted-foreground">
                Nenhum documento enviado ainda. Envie o primeiro arquivo acima para começar a fazer perguntas no chat.
              </p>
            ) : (
              <>
                {error && (
                  <p role="alert" className="text-sm text-destructive">
                    {error} Exibindo a última lista obtida.
                  </p>
                )}
                <DocumentList
                  documents={documents}
                  highlightedId={highlightedId}
                  busyId={busyId}
                  onDelete={setPendingDelete}
                  onReprocess={(doc) => void handleReprocess(doc)}
                />
              </>
            )}
          </CardContent>
        </Card>
      </section>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Excluir documento?"
        description={
          <p>
            O documento <strong className="break-all text-foreground">{pendingDelete?.filename}</strong> e todos os
            seus trechos indexados serão removidos. Esta ação não pode ser desfeita.
          </p>
        }
        confirmLabel="Excluir"
        destructive
        isConfirming={pendingDelete !== null && busyId === pendingDelete.id}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
