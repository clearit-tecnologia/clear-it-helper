"use client";

import { forwardRef, useId, useState, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export interface ChatComposerProps {
  isStreaming: boolean;
  onSend: (question: string) => void;
  onStop: () => void;
}

export const ChatComposer = forwardRef<HTMLTextAreaElement, ChatComposerProps>(function ChatComposer(
  { isStreaming, onSend, onStop },
  ref,
) {
  const id = useId();
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit() {
    if (isStreaming) return;
    if (!question.trim()) {
      setError("Digite uma pergunta antes de enviar.");
      return;
    }
    setError(null);
    onSend(question);
    setQuestion("");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter breaks the line; ignored while composing (IME).
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  const describedBy = [`${id}-hint`, error ? `${id}-error` : null].filter(Boolean).join(" ");

  return (
    <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-2">
      <Label htmlFor={`${id}-question`}>Sua pergunta</Label>
      <Textarea
        ref={ref}
        id={`${id}-question`}
        name="question"
        rows={3}
        value={question}
        onChange={(e) => {
          setQuestion(e.target.value);
          if (error) setError(null);
        }}
        onKeyDown={handleKeyDown}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        placeholder="Ex.: Qual é o prazo para responder a um pedido de acesso à informação?"
      />
      <p id={`${id}-hint`} className="text-xs text-muted-foreground">
        Enter envia; Shift+Enter quebra a linha.
      </p>
      {error && (
        <p id={`${id}-error`} role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        {isStreaming ? (
          <Button variant="outline" onClick={onStop}>
            Parar resposta
          </Button>
        ) : (
          <Button type="submit">Enviar pergunta</Button>
        )}
      </div>
    </form>
  );
});
