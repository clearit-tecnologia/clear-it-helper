import { AnswerContent, CitationButton, describeSource } from "@/components/chat/citation-button";
import type { Source } from "@/lib/api/types";
import type { ChatMessage } from "@/lib/chat/history";
import { cn } from "@/lib/utils";

export interface ChatMessageItemProps {
  message: ChatMessage;
  onOpenSource: (source: Source) => void;
}

export function ChatMessageItem({ message, onOpenSource }: ChatMessageItemProps) {
  if (message.role === "user") {
    return (
      <li className="flex flex-col items-end" data-testid="chat-message-user">
        <h3 className="sr-only">Você perguntou</h3>
        <p className="max-w-prose whitespace-pre-wrap break-words rounded-lg bg-primary px-4 py-3 text-primary-foreground">
          {message.content}
        </p>
      </li>
    );
  }

  const sources = message.sources ?? [];
  const isStreaming = message.status === "streaming";
  const refused = message.status === "done" && message.refused === true;

  return (
    <li className="flex flex-col items-start" data-testid="chat-message-assistant">
      <h3 className="sr-only">{refused ? "Resposta do assistente: sem evidência" : "Resposta do assistente"}</h3>
      <div
        data-refused={refused || undefined}
        className={cn(
          "flex w-full max-w-prose flex-col gap-3 rounded-lg border bg-card px-4 py-3",
          refused && "border-dashed border-input bg-muted",
          message.status === "error" && "border-destructive",
        )}
      >
        {refused && (
          <p className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
            <span aria-hidden="true">!</span>
            Sem evidência nos documentos
          </p>
        )}

        {message.content ? (
          <AnswerContent text={message.content} sources={sources} onOpenSource={onOpenSource} />
        ) : isStreaming ? (
          <p className="text-muted-foreground">
            {sources.length > 0 ? "Gerando resposta…" : "Buscando nos documentos…"}
          </p>
        ) : null}

        {isStreaming && message.content && (
          <p className="text-xs text-muted-foreground">
            <span aria-hidden="true">▍</span> Gerando resposta…
          </p>
        )}

        {message.status === "stopped" && (
          <p className="text-xs font-medium text-muted-foreground">Resposta interrompida.</p>
        )}

        {message.status === "error" && (
          <p role="alert" className="text-sm text-destructive">
            {message.error ?? "Não foi possível gerar a resposta."}
          </p>
        )}

        {sources.length > 0 && !refused && (
          <div className="border-t pt-3">
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Fontes</h4>
            <ul className="flex flex-col gap-1 text-sm">
              {sources.map((source) => (
                <li key={source.ref} className="flex flex-wrap items-baseline gap-1">
                  <CitationButton source={source} onOpen={onOpenSource} />
                  <span aria-hidden="true" className="break-all text-muted-foreground">
                    {describeSource(source)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </li>
  );
}
