"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ChatComposer } from "@/components/chat/chat-composer";
import { ChatMessageItem } from "@/components/chat/chat-message";
import { SourcePanel } from "@/components/chat/source-panel";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/use-chat";
import { useDocumentAvailability, type DocumentAvailability } from "@/hooks/use-document-availability";
import type { Source } from "@/lib/api/types";
import type { openDocument } from "@/lib/documents/open-document";

function AvailabilityNotice({ availability }: { availability: DocumentAvailability }) {
  if (availability !== "none" && availability !== "pending") return null;
  return (
    <Alert className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
      <p>
        {availability === "none" ? (
          <>
            <strong className="font-semibold">Você ainda não enviou documentos.</strong> O assistente só responde com
            base nos seus arquivos: envie-os primeiro na página Documentos.
          </>
        ) : (
          <>
            <strong className="font-semibold">Seus documentos ainda estão sendo processados.</strong> As respostas
            ficam disponíveis assim que algum deles estiver indexado.
          </>
        )}
      </p>
      <Button asChild variant={availability === "none" ? "default" : "outline"} size="sm">
        <Link href="/documentos">{availability === "none" ? "Enviar documentos" : "Ver documentos"}</Link>
      </Button>
    </Alert>
  );
}

export interface ChatScreenProps {
  /** Injectable for tests. */
  onOpenDocument?: typeof openDocument;
}

export function ChatScreen({ onOpenDocument }: ChatScreenProps) {
  const { messages, isStreaming, announcement, send, stop, clear } = useChat();
  const availability = useDocumentAvailability();
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  // Keeps the newest message in view when a question is sent and when it finishes.
  const lastId = messages[messages.length - 1]?.id;
  useEffect(() => {
    const el = endRef.current;
    if (el && typeof el.scrollIntoView === "function") el.scrollIntoView({ block: "end" });
  }, [lastId, isStreaming]);

  function handleClear() {
    clear();
    composerRef.current?.focus();
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Chat com seus documentos</h1>
        {messages.length > 0 && (
          <Button variant="outline" size="sm" onClick={handleClear}>
            Limpar conversa
          </Button>
        )}
      </div>

      <AvailabilityNotice availability={availability} />

      {/* Announces the finished answer once; the message list itself is not live. */}
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      <section aria-labelledby="conversation-title" aria-busy={isStreaming} className="flex flex-col gap-4">
        <h2 id="conversation-title" className="sr-only">
          Conversa
        </h2>
        {messages.length === 0 ? (
          <p className="rounded-md border border-dashed border-input bg-muted p-6 text-sm text-muted-foreground">
            Faça uma pergunta sobre os seus documentos. Cada resposta cita os trechos usados, como [1]: selecione a
            citação para ver o trecho e abrir o documento. A conversa fica só nesta aba do navegador e é apagada ao
            sair.
          </p>
        ) : (
          <ol className="flex flex-col gap-4" aria-label="Mensagens da conversa">
            {messages.map((message) => (
              <ChatMessageItem key={message.id} message={message} onOpenSource={setSelectedSource} />
            ))}
          </ol>
        )}
        <div ref={endRef} />
      </section>

      <section aria-label="Nova pergunta" className="rounded-lg border bg-card p-4 shadow-sm">
        <ChatComposer ref={composerRef} isStreaming={isStreaming} onSend={(q) => void send(q)} onStop={stop} />
      </section>

      <SourcePanel source={selectedSource} onClose={() => setSelectedSource(null)} onOpenDocument={onOpenDocument} />
    </div>
  );
}
