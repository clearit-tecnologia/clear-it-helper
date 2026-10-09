# clear-helper — frontend

Interface web do clear-helper (Fase 0): login, dados do usuário/tenant e painel
**Status do ambiente**. O chat entra na Fase 1.

Stack: Next.js 15 (App Router, `output: "standalone"`), TypeScript strict,
Tailwind CSS, componentes no estilo shadcn/ui (`components/ui/`), Vitest + Testing Library + axe-core.

## Desenvolvimento

Requisitos: Node.js >= 18.18 e pnpm 9 (via `corepack enable`).

```bash
cp .env.example .env.local   # ajuste API_INTERNAL_URL se a API não estiver em localhost:8000
pnpm install
pnpm dev                     # http://localhost:3000
```

O frontend chama sempre caminhos relativos `/api/...`. No cluster, o ingress
(`clear-helper.localhost`) encaminha `/api/*` para `clear-helper-api:8000` removendo o
prefixo; no `pnpm dev`, um rewrite em `next.config.ts` faz o mesmo papel.

## Qualidade

```bash
pnpm lint        # ESLint (next/core-web-vitals, next/typescript, jsx-a11y strict)
pnpm typecheck   # tsc --noEmit
pnpm test        # Vitest (inclui verificação de acessibilidade com axe-core)
pnpm build
```

## Rotas

| Rota | Descrição |
|------|-----------|
| `/login` | Login por e-mail e senha (`POST /api/auth/login`) |
| `/` | Usuário/tenant (`GET /api/auth/me`), sair, status do ambiente (`GET /api/health/ready`, a cada 15 s) |
| `/healthz` | Probe do Kubernetes (200 `{"status":"ok"}`) |

## Imagem

```bash
docker build -t registry.localhost:5000/clear-helper-frontend:dev .
```

Imagem multi-stage (`node:22-alpine`), usuário não-root (UID 1001), porta 3000.

## Pendências conhecidas

- Token em `sessionStorage` (aceito só na Fase 0). Na Fase 6 passa para cookie
  HttpOnly / sessão OIDC (Keycloak).
