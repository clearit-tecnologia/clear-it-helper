# clear-helper — backend

API (FastAPI) e worker (arq) do clear-helper. A mesma imagem atende API, worker, migrações e bootstrap; só o comando muda. O contrato de integração da Fase 0 (variáveis `CH_*`, rotas e modelo de dados) está em [`../docs/arquitetura/fase-0-contrato.md`](../docs/arquitetura/fase-0-contrato.md).

## Requisitos

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

## Desenvolvimento

```bash
uv lock                      # gera o uv.lock (versionar no Git)
uv sync                      # cria .venv com dependências de runtime + dev
cp .env.example .env         # preencha CH_JWT_SECRET e demais valores

uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
```

Os testes usam SQLite em memória (aiosqlite) e não precisam de serviços externos.

## Comandos

| Comando | Uso |
|---------|-----|
| `uvicorn clear_helper.main:app --host 0.0.0.0 --port 8000` | API |
| `python -m clear_helper.worker` | worker (arq); na Fase 0 só tem a task `ping` |
| `alembic upgrade head` | migrações (executar no diretório `backend/`) |
| `python -m clear_helper.cli bootstrap` | cria, de forma idempotente, o tenant e o admin a partir de `CH_BOOTSTRAP_*` |

O bootstrap deriva o `slug` do tenant a partir de `CH_BOOTSTRAP_TENANT` (ex.: `ClearIT` → `clearit`). Se o admin já existir, ele não é alterado (a senha não é sobrescrita).

## Rotas (Fase 0)

- `GET /health/live`: processo vivo.
- `GET /health/ready`: verifica postgres, redis, qdrant, s3 e litellm em paralelo, com timeout por serviço (`CH_HEALTH_TIMEOUT_SECONDS`, padrão 2 s). Retorna 503 apenas se o PostgreSQL falhar; os demais serviços com erro deixam o status como `degraded`.
- `POST /auth/login` e `GET /auth/me`: autenticação JWT local (HS256, claims `sub`, `tid`, `role`, `exp`, `iat`).

A documentação OpenAPI (`/docs`) só fica ativa com `CH_ENV=dev`.

## Imagem

```bash
docker build -t clear-helper-backend .   # requer uv.lock
```

Runtime em `python:3.12-slim`, usuário não-root (UID 10001), porta 8000.

## Regras

- Toda entidade de negócio herda `TenantScoped` (`tenant_id` obrigatório e indexado).
- Repositórios recebem `tenant_id` explícito. A única exceção é a busca de usuário por e-mail no login, que acontece antes de o tenant ser conhecido (o e-mail é único globalmente).
- Logs em JSON no stdout, sem senhas, tokens ou e-mails.
