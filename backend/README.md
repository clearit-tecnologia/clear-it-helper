# clear-helper — backend

API (FastAPI) e worker (arq) do clear-helper. A mesma imagem atende API, worker, migrações e bootstrap; só o comando muda. Os contratos de integração (variáveis `CH_*`, rotas e modelo de dados) estão em [`../docs/arquitetura/fase-0-contrato.md`](../docs/arquitetura/fase-0-contrato.md) e [`../docs/arquitetura/fase-1-contrato.md`](../docs/arquitetura/fase-1-contrato.md).

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

Os testes usam SQLite em memória (aiosqlite) e fakes em memória para S3, Qdrant, LiteLLM (via `httpx.MockTransport`) e fila arq (`tests/fakes.py`); não precisam de serviços externos. PDFs e DOCX de teste são gerados no próprio teste (`tests/documents_factory.py`).

## Comandos

| Comando | Uso |
|---------|-----|
| `uvicorn clear_helper.main:app --host 0.0.0.0 --port 8000` | API |
| `python -m clear_helper.worker` | worker (arq): tasks `ping` e `ingest_document` |
| `alembic upgrade head` | migrações (executar no diretório `backend/`) |
| `python -m clear_helper.cli bootstrap` | cria, de forma idempotente, o tenant e o admin a partir de `CH_BOOTSTRAP_*` |
| `python -m clear_helper.cli create-user --tenant <nome> --email <e> --password-env <VAR> [--role admin\|member]` | cria, de forma idempotente, o tenant (se não existir) e um usuário nele (padrão `member`); a senha é lida da variável de ambiente indicada, nunca de argumento. Usado para o tenant dedicado do eval |

O bootstrap e o `create-user` derivam o `slug` do tenant a partir do nome (ex.: `ClearIT` → `clearit`). Se o usuário já existir no tenant, ele não é alterado (senha e papel não são sobrescritos); se o e-mail pertencer a outro tenant, o comando falha.

## Rotas (Fase 0)

- `GET /health/live`: processo vivo.
- `GET /health/ready`: verifica postgres, redis, qdrant, s3 e litellm em paralelo, com timeout por serviço (`CH_HEALTH_TIMEOUT_SECONDS`, padrão 2 s). Retorna 503 apenas se o PostgreSQL falhar; os demais serviços com erro deixam o status como `degraded`.
- `POST /auth/login` e `GET /auth/me`: autenticação JWT local (HS256, claims `sub`, `tid`, `role`, `exp`, `iat`).

A documentação OpenAPI (`/docs`) só fica ativa com `CH_ENV=dev`.

## Rotas (Fase 1: baseline RAG)

Todas exigem `Authorization: Bearer <jwt>` e operam somente no tenant do token (documento de outro tenant responde 404).

| Rota | Comportamento |
|------|---------------|
| `POST /documents` (multipart, campo `file`) | 202 + `Document`; 409 `{"detail","document_id"}` se o mesmo arquivo (sha256) já existe no tenant; 413 acima de `CH_UPLOAD_MAX_MB`; 415 para formato não suportado; 400 para arquivo vazio; 503 se o S3 estiver indisponível |
| `GET /documents` | `{"items":[Document]}`, mais recentes primeiro |
| `GET /documents/{id}` | `Document` |
| `GET /documents/{id}/file` | arquivo original em stream (`Content-Disposition: inline`, `Content-Security-Policy: sandbox`, `X-Content-Type-Options: nosniff`) |
| `DELETE /documents/{id}` | 204; remove pontos do Qdrant, objeto do S3 e a linha (nessa ordem; se Qdrant/S3 falharem, responde 503 e mantém a linha) |
| `POST /documents/{id}/reprocess` | 202; volta o status para `uploaded` e reenfileira |
| `POST /search` | `{"query","top_k"?}` → `{"results":[Source]}`, sem LLM |
| `POST /chat` | SSE com os eventos `sources`, `token`, `done` e `error` |

### Ingestão (`pipeline_version = baseline-v1`)

1. A API valida tamanho e formato (extensão + assinatura do arquivo), calcula o sha256, grava em `tenants/{tenant_id}/documents/{id}/original` no S3, cria a linha com status `uploaded` e enfileira `ingest_document(document_id, tenant_id)`.
2. O worker muda para `processing`, extrai o texto por página (`extraction.py`: pypdf, python-docx, BeautifulSoup com `html.parser`, TXT/Markdown com detecção de encoding), divide em chunks fixos de `CH_CHUNK_SIZE` caracteres com `CH_CHUNK_OVERLAP` de sobreposição sem atravessar páginas (`chunking.py`), gera embeddings no LiteLLM em lotes de 16 e grava no Qdrant (`vectorstore.py`).
3. Termina em `indexed` (com `page_count`, `chunk_count` e `pipeline_version`) ou `failed` (com `error` curto em pt-BR). PDF sem texto termina com `"Documento sem texto extraível (OCR chega na Fase 2)"`.

Reprocessar é idempotente: os pontos do documento são apagados antes do upsert e o id de cada ponto é determinístico (`uuid5(document_id:chunk_index)`). `char_start`/`char_end` no payload são posições dentro do texto extraído da página.

### Qdrant

A coleção `CH_QDRANT_COLLECTION` (vetor nomeado `dense`, `CH_EMBEDDING_DIM` dimensões, Cosine) e os índices de payload `tenant_id` (keyword, `is_tenant=true`) e `document_id` são criados no startup da API e do worker. Se o Qdrant estiver fora no startup, a criação é tentada de novo no primeiro uso. Se a coleção existir com outra dimensão, a operação falha: trocar modelo de embedding ou chunking exige coleção nova. Toda busca e toda remoção filtram por `tenant_id`.

### Chat

- Busca: embedding da pergunta atual (o histórico não entra na busca) e top `CH_RETRIEVAL_TOP_K` trechos com score ≥ `CH_RETRIEVAL_MIN_SCORE`. O `/search` usa os mesmos parâmetros (`top_k` do corpo substitui o padrão, de 1 a 50).
- Sem trechos acima do limiar, o LLM **não é chamado**: a resposta é `"Não encontrei essa informação nos documentos enviados."` com `refused=true`.
- O prompt de sistema (pt-BR, em `rag.py`) exige resposta só com base nos trechos, citação `[n]` e a frase de recusa quando os trechos não respondem. `refused` também fica `true` quando o modelo responde com essa frase.
- Blocos `<think>…</think>` são removidos do stream mesmo quando as tags chegam divididas entre tokens.
- Respostas SSE usam `Cache-Control: no-cache` e `X-Accel-Buffering: no`. O timeout de geração é `CH_LLM_TIMEOUT_SECONDS`.

## Imagem

```bash
docker build -t clear-helper-backend .   # requer uv.lock
```

Runtime em `python:3.12-slim`, usuário não-root (UID 10001), porta 8000.

## Regras

- Toda entidade de negócio herda `TenantScoped` (`tenant_id` obrigatório e indexado).
- Repositórios recebem `tenant_id` explícito. A única exceção é a busca de usuário por e-mail no login, que acontece antes de o tenant ser conhecido (o e-mail é único globalmente).
- Logs em JSON no stdout, sem senhas, tokens ou e-mails. Logs de ingestão e chat registram ids, contagens e latência, nunca o conteúdo dos documentos ou das perguntas.
- Toda consulta ao Qdrant filtra por `tenant_id` (`vectorstore.tenant_filter`).
