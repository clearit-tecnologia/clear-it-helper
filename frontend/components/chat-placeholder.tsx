import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** Reserva o espaço do chat, que será implementado na Fase 1. */
export function ChatPlaceholder() {
  return (
    <section aria-labelledby="chat-title">
    <Card>
      <CardHeader>
        <CardTitle id="chat-title">Chat com seus documentos</CardTitle>
        <CardDescription>Em breve: disponível a partir da Fase 1.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex min-h-48 items-center justify-center rounded-md border border-dashed border-input bg-muted p-6 text-center text-sm text-muted-foreground">
          Aqui você poderá enviar documentos e fazer perguntas com respostas citadas.
        </div>
      </CardContent>
    </Card>
    </section>
  );
}
