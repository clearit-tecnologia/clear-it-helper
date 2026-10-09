"use client";

import { Button } from "@/components/ui/button";
import type { CurrentUser } from "@/lib/api/types";

const ROLE_LABELS: Record<CurrentUser["role"], string> = {
  admin: "Administrador",
  member: "Membro",
};

interface AppHeaderProps {
  user: CurrentUser;
  onLogout: () => void;
}

export function AppHeader({ user, onLogout }: AppHeaderProps) {
  return (
    <header className="border-b bg-card">
      <div className="container flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-lg font-semibold">Clear Helper</p>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
          <dl className="grid grid-cols-[auto_1fr] gap-x-2 text-sm sm:text-right">
            <dt className="sr-only">Usuário</dt>
            <dd className="col-span-2 font-medium">{user.email}</dd>
            <dt className="text-muted-foreground">Organização:</dt>
            <dd>{user.tenant.name}</dd>
            <dt className="text-muted-foreground">Perfil:</dt>
            <dd>{ROLE_LABELS[user.role] ?? user.role}</dd>
          </dl>
          <Button variant="outline" onClick={onLogout}>
            Sair
          </Button>
        </div>
      </div>
    </header>
  );
}
