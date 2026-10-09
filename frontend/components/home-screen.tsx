"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ChatPlaceholder } from "@/components/chat-placeholder";
import { HealthStatusSection } from "@/components/health/health-status-section";
import { AppHeader } from "@/components/layout/app-header";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/hooks/use-current-user";
import { clearSession } from "@/lib/auth/session";

export function HomeScreen() {
  const router = useRouter();
  const state = useCurrentUser();

  useEffect(() => {
    if (state.status === "unauthenticated") router.replace("/login");
  }, [state.status, router]);

  function handleLogout() {
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
      <main id="conteudo" className="container flex flex-col gap-6 py-8">
        <h1 className="text-2xl font-semibold">Início</h1>
        <ChatPlaceholder />
        <HealthStatusSection />
      </main>
    </>
  );
}
