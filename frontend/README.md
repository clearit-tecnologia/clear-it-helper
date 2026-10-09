# clear-helper — frontend

Interface web do clear-helper (Fase 1 — Baseline RAG): login, chat com streaming e
citações, gestão de documentos e painel **Status do ambiente**.

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
| `/` | Chat: `POST /api/chat` (SSE lido com `fetch` + `ReadableStream`), citações `[n]` com painel lateral da fonte, botão parar e histórico só na sessão |
| `/documentos` | Upload (arrastar/soltar ou botão), lista com status, excluir e reprocessar; atualização a cada 3 s enquanto houver documento em processamento |
| `/status` | Status do ambiente (`GET /api/health/ready`, a cada 15 s) |
| `/healthz` | Probe do Kubernetes (200 `{"status":"ok"}`) |

As rotas autenticadas ficam no grupo `app/(app)/`, cujo layout (`AppShell`) resolve o
usuário uma única vez e mostra o cabeçalho com a navegação Chat, Documentos e Status.

### Decisões de UI (Fase 1)

- **Histórico da conversa:** em memória + `sessionStorage` (`clear-helper.chat.v1`), apagado ao
  sair e ao fechar a aba. Cada pergunta envia no máximo as 10 últimas mensagens concluídas.
- **Acessibilidade do streaming:** a lista de mensagens não é região viva; uma região
  `role="status"` anuncia a resposta só ao concluir (ou a interrupção). Erros usam `role="alert"`.
- **Abrir documento:** o arquivo é baixado com o Bearer e aberto via blob URL. PDF abre em nova
  aba com `#page=N`; TXT/MD/HTML abrem como **texto puro** (um blob URL tem a origem da
  aplicação, e renderizar HTML enviado executaria scripts com acesso ao token); DOCX é baixado.
- **Diálogos:** `<dialog>` nativo com `showModal()` (foco preso, Esc fecha), sem nova dependência.

## Imagem

```bash
docker build -t registry.localhost:5000/clear-helper-frontend:dev .
```

Imagem multi-stage (`node:22-alpine`), usuário não-root (UID 1001), porta 3000.

## Pendências conhecidas

- Token em `sessionStorage` (aceito só na Fase 0). Na Fase 6 passa para cookie
  HttpOnly / sessão OIDC (Keycloak).
