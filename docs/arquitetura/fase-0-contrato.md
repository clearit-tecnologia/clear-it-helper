# Fase 0: Contrato de integração

Este documento é a fonte da verdade compartilhada entre backend, frontend e infra na Fase 0.
Qualquer mudança aqui deve ser refletida nas três partes.

## Estrutura do monorepo

```
clear-helper/
├── constitution/          # mission, tech-stack, roadmap
├── docs/                  # arquitetura, ADRs, guias
├── backend/               # FastAPI (API) + worker (mesma imagem, comandos diferentes)
├── frontend/              # Next.js 15 (App Router, TS, Tailwind, shadcn/ui)
├── eval/                  # golden set e scripts de avaliação (preenchido na Fase 1)
├── infra/
│   ├── k3d/               # definição do cluster local + registry
│   ├── helm/clear-helper/ # chart da aplicação
│   ├── argocd/            # app-of-apps e Applications por componente
│   └── values/{dev,mvp}/  # values por ambiente
├── scripts/               # setup e bootstrap
└── .github/workflows/     # CI
```

## Kubernetes

| Item | Valor |
|------|-------|
| Namespace da aplicação | `clear-helper` |
| Cluster dev | k3d, cluster `clear-helper`, registry `registry.localhost:5000` (mesmo nome no host e dentro do cluster, via mirror do k3s) |
| Ingress | Traefik (padrão do k3s), host `clear-helper.localhost` |
| Rotas | `/api/*` → `clear-helper-api:8000` (prefixo `/api` removido via middleware); `/` → `clear-helper-frontend:3000` |
| Secrets | Sealed Secrets (controller em `kube-system`); no dev, um script gera e sela os secrets |
| GitOps | Argo CD em `argocd`, padrão app-of-apps (`infra/argocd/root.yaml`) |

## Serviços e endereços internos

| Serviço | Endereço no cluster | Origem |
|---------|--------------------|--------|
| API | `http://clear-helper-api:8000` | chart próprio |
| Frontend | `http://clear-helper-frontend:3000` | chart próprio |
| Worker | — (consome fila Redis) | chart próprio |
| PostgreSQL | `clear-helper-pg-rw:5432`, db `clearhelper` | CloudNativePG (`Cluster` `clear-helper-pg`; secret `clear-helper-pg-app`, chave `uri`) |
| Redis | `redis://clear-helper-redis:6379/0` | chart próprio (imagem `valkey/valkey`; evita charts Bitnami) |
| Qdrant | `http://qdrant:6333` | chart oficial `qdrant/qdrant` |
| S3 (Garage) | `http://clear-helper-garage:3900`, bucket `clear-helper-docs` | chart próprio + Job de bootstrap (layout, chave, bucket) |
| LiteLLM | `http://litellm:4000` | chart oficial `oci://ghcr.io/berriai/litellm-helm` |
| Langfuse | `http://langfuse-web:3000` | chart oficial `langfuse/langfuse` (desativável no dev) |
| vLLM / embeddings | **fora do cluster**, configurado só no LiteLLM | servidor GPU dedicado (dev: Ollama local) |

## Variáveis de ambiente do backend (prefixo `CH_`)

| Variável | Exemplo | Uso |
|----------|---------|-----|
| `CH_ENV` | `dev` | ambiente |
| `CH_DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL (o backend converte `postgresql://` para `postgresql+asyncpg://`) |
| `CH_REDIS_URL` | `redis://clear-helper-redis:6379/0` | fila e cache |
| `CH_QDRANT_URL` | `http://qdrant:6333` | banco vetorial |
| `CH_S3_ENDPOINT` / `CH_S3_ACCESS_KEY` / `CH_S3_SECRET_KEY` / `CH_S3_BUCKET` / `CH_S3_REGION` | `garage` como região | object storage |
| `CH_LITELLM_URL` / `CH_LITELLM_API_KEY` | `http://litellm:4000` | gateway de modelos |
| `CH_LANGFUSE_HOST` / `CH_LANGFUSE_PUBLIC_KEY` / `CH_LANGFUSE_SECRET_KEY` | opcionais | traces |
| `CH_JWT_SECRET` / `CH_JWT_EXPIRES_MINUTES` | `60` | autenticação |
| `CH_BOOTSTRAP_TENANT` / `CH_BOOTSTRAP_ADMIN_EMAIL` / `CH_BOOTSTRAP_ADMIN_PASSWORD` | — | seed idempotente do tenant e admin iniciais |
| `CH_CORS_ORIGINS` | `http://clear-helper.localhost` | CORS |
| `CH_LOG_LEVEL` | `INFO` | nível de log (JSON) |
| `CH_HEALTH_TIMEOUT_SECONDS` | `2` | timeout de cada check do `/health/ready` |

## API (Fase 0)

Todas as respostas são JSON. A autenticação usa `Authorization: Bearer <jwt>`.

| Método e rota | Auth | Resposta |
|---------------|------|----------|
| `GET /health/live` | não | `{"status":"ok"}` |
| `GET /health/ready` | não | `{"status":"ok"\|"degraded","checks":{"postgres":{"status":"ok"\|"error","latency_ms":n,"detail":str\|null},"redis":…,"qdrant":…,"s3":…,"litellm":…}}`; HTTP 200 se postgres está ok, senão 503 |
| `POST /auth/login` | não | body `{"email","password"}` → `{"access_token","token_type":"bearer","expires_in"}`; 401 se inválido |
| `GET /auth/me` | sim | `{"id","email","role","tenant":{"id","name","slug"}}` |

JWT claims: `sub` (user id), `tid` (tenant id), `role`, `exp`, `iat`.

## Modelo de dados (Fase 0)

- `tenants`: `id` uuid pk, `name`, `slug` único, `created_at`.
- `users`: `id` uuid pk, `tenant_id` fk → tenants (indexado), `email` único, `password_hash` (argon2), `role` (`admin` \| `member`), `is_active`, `created_at`.
- Regra: toda entidade de negócio futura herda o mixin `TenantScoped` (`tenant_id` obrigatório e indexado). Os repositórios recebem `tenant_id` explícito; não existe consulta sem filtro de tenant.

## Comandos do backend

| Comando | Uso |
|---------|-----|
| `uvicorn clear_helper.main:app --host 0.0.0.0 --port 8000 --root-path /api` | API (atrás do ingress com strip-prefix `/api`) |
| `python -m clear_helper.worker` | worker (arq) |
| `alembic upgrade head` (workdir `/app`) | migrações (Job Helm `pre-install,pre-upgrade` / Argo CD `PreSync`) |
| `python -m clear_helper.cli bootstrap` | seed idempotente do tenant e admin a partir de `CH_BOOTSTRAP_*` (executado após as migrações) |
