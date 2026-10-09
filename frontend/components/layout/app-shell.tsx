"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/hooks/use-current-user";
import { clearSession } from "@/lib/auth/session";
import { clearChatHistory } from "@/lib/chat/history";

/**
 * Authenticated area: resolves the user once (the layout persists across the
 * Chat, Documentos and Status routes) and renders the header with navigation.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const state = useCurrentUser();

  useEffect(() => {
    if (state.status === "unauthenticated") router.replace("/login");
  }, [state.status, router]);

  function handleLogout() {
    // The conversation lives only in this browser session and goes away on logout.
    clearChatHistory();
    clearSession();
    router.replace("/login");
  }

  if (state.status === "loading" || state.status === "unauthenticated") {
    return (
      <main id="conteudo" className="container py-10">
        <p role="status" aria-live="polite" className="text-muted-foreground">
          Carregando…
        </p>
      </main>
    );
  }

  if (state.status === "error") {
    return (
      <main id="conteudo" className="container flex flex-col items-start gap-4 py-10">
        <h1 className="text-2xl font-semibold">Não foi possível carregar a página</h1>
        <p role="alert" className="text-destructive">
          {state.message}
        </p>
        <div className="flex gap-3">
          <Button onClick={() => window.location.reload()}>Tentar novamente</Button>
          <Button variant="outline" onClick={handleLogout}>
            Sair
          </Button>
        </div>
      </main>
    );
  }

  return (
    <>
      <AppHeader user={state.user} onLogout={handleLogout} />
      <main id="conteudo" className="container py-8">
        {children}
      </main>
    </>
  );
}
