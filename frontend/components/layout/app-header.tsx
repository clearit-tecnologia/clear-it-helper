"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import type { CurrentUser } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const ROLE_LABELS: Record<CurrentUser["role"], string> = {
  admin: "Administrador",
  member: "Membro",
};

export const NAV_ITEMS = [
  { href: "/", label: "Chat" },
  { href: "/documentos", label: "Documentos" },
  { href: "/status", label: "Status" },
] as const;

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

interface AppHeaderProps {
  user: CurrentUser;
  onLogout: () => void;
}

export function AppHeader({ user, onLogout }: AppHeaderProps) {
  const pathname = usePathname() ?? "/";
  return (
    <header className="border-b bg-card">
      <div className="container flex flex-col gap-3 py-4 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-6">
          <p className="text-lg font-semibold">Clear Helper</p>
          <nav aria-label="Principal">
            <ul className="flex flex-wrap gap-1">
              {NAV_ITEMS.map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "inline-flex h-9 items-center rounded-md px-3 text-sm font-medium transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                        active && "bg-secondary text-primary underline underline-offset-4",
                      )}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </div>
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
