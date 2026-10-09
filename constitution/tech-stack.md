# Tech Stack

> Stack do MVP enxuto da ClearIT AI Platform (ver `../../DiagramArchitecture.mermaid`), com execução **100% on-premises**.
> Componentes marcados como _(fase posterior)_ fazem parte da arquitetura-alvo, mas não entram no MVP.

## Visão geral

```
Next.js ──► FastAPI (API) ──► Fila ──► Worker de ingestão
               │                         │ Docling + OCR → chunking semântico
               │                         │ → contexto/enriquecimento (LLM) → BGE-M3
               │                         ▼
               ├──► Qdrant (dense + sparse, filtro por tenant_id)
               ├──► PostgreSQL (metadados, tenants, conversas)
               ├──► Object storage S3 (arquivos originais)
               └──► LiteLLM ──► vLLM (Qwen3)
                         └──► Serviço de embeddings/rerank (BGE-M3 + bge-reranker-v2-m3)
Observabilidade: Langfuse (traces) · Prometheus/Grafana (infra + GPU)

Tudo acima roda no Kubernetes, exceto vLLM e o serviço de embeddings/rerank, que no MVP
ficam em servidor GPU dedicado fora do cluster, acessados via LiteLLM.
```

## Aplicação

| Camada | Escolha | Motivo |
|--------|---------|--------|
| Backend / API | **Python 3.12 + FastAPI** | O ecossistema de IA é nativo em Python; API assíncrona com streaming via SSE. |
| Validação / config | Pydantic v2, pydantic-settings | Contratos tipados entre as camadas. |
| ORM / migrações | SQLAlchemy 2.x + Alembic | Padrão de mercado, com suporte assíncrono. |
| Fila / workers | Redis + worker assíncrono (ex.: arq) | A ingestão é lenta (OCR e LLM) e precisa rodar fora do ciclo da requisição. _Dagster na fase posterior._ |
| Frontend | **Next.js (App Router) + TypeScript** | Alinhado à arquitetura-alvo. |
| UI | Tailwind CSS + shadcn/ui | Produtividade e consistência visual. |
| Autenticação | JWT local com `tenant_id` no token (MVP) | _Keycloak OIDC na fase posterior, sem mudar o modelo de dados._ |

## Pipeline de embedding inteligente

| Pilar | Ferramenta | Observação |
|-------|-----------|------------|
| 1. Parsing estrutural | **Docling** (+ OCR integrado: EasyOCR/Tesseract; Surya como alternativa) | Exporta a estrutura do documento (seções, tabelas, listas) em DoclingDocument. |
| 2. Chunking semântico | Docling HybridChunker (hierárquico, respeita limite de tokens) | Chunks que respeitam seções e tabelas. |
| 2. Contextual retrieval | LLM local (Qwen3) gera de 1 a 2 frases de contexto por chunk | O contexto é prefixado ao chunk antes de gerar o embedding e indexado também no sparse. |
| 3. Embeddings | **BGE-M3** (via FlagEmbedding) | Multilíngue, forte em pt-BR, gera vetores dense e sparse com um único modelo. |
| 3. Rerank | **bge-reranker-v2-m3** | Cross-encoder multilíngue, aplicado sobre o top-k da busca híbrida. |
| 3. Busca híbrida | Qdrant Query API (dense + sparse, fusão RRF) | Fusão nativa, sem código extra. |
| 4. Enriquecimento | Qwen3 com saída estruturada (JSON) | Resumo, palavras-chave, perguntas hipotéticas e classificação, gravados no payload do Qdrant. |

## Modelos e inferência (on-premises)

| Função | Modelo padrão | Servidor |
|--------|---------------|----------|
| Geração (chat, contexto, enriquecimento) | **Qwen3**, com tamanho definido pela GPU disponível (ex.: 8B, 14B ou 32B) | **vLLM** (API compatível com OpenAI) |
| Embedding | BGE-M3 | Serviço Python dedicado (FlagEmbedding) |
| Rerank | bge-reranker-v2-m3 | Mesmo serviço de embeddings |
| Hospedagem (MVP) | — | vLLM e embeddings rodam em **servidor GPU dedicado fora do cluster**; entram no Kubernetes com NVIDIA GPU Operator na Fase 6. |
| Gateway | **LiteLLM Proxy** | Ponto único de acesso aos modelos, com chaves, quotas e custo por tenant. |

Regras:
- **Nenhum provedor em nuvem** é configurado no LiteLLM em ambientes com dados reais.
- Trocar de modelo exige rodar o golden set de avaliação. Se o modelo de embedding mudar, todo o acervo precisa ser reindexado, então cada coleção registra o modelo e a versão usados.
- Para desenvolvimento sem GPU, é permitido usar Ollama com modelos menores na máquina local (fora do cluster), sempre atrás do mesmo LiteLLM.

## Dados

| Função | Escolha |
|--------|---------|
| Banco vetorial | **Qdrant**: coleção com vetores nomeados `dense` e `sparse`, payload com `tenant_id`, `document_id` e metadados, e índice de payload em `tenant_id`. |
| Relacional | **PostgreSQL 16** (operador CloudNativePG no cluster): tenants, usuários, documentos, status de ingestão, conversas e feedback. |
| Object storage | S3 compatível on-premises (**Garage**; Ceph em produção de larga escala), para arquivos originais e artefatos de parsing. |
| Cache / fila | Redis. |

## Qualidade e avaliação

| Item | Ferramenta |
|------|-----------|
| Golden set | Conjunto versionado no repositório: perguntas em pt-BR, respostas esperadas e documentos/trechos de referência. |
| Métricas de recuperação | Recall@k, MRR, nDCG (script próprio). |
| Métricas de geração | **RAGAS** (faithfulness, answer relevancy, context precision), com o LLM juiz também local. |
| Rastreamento | **Langfuse** self-hosted: traces de ingestão e de chat, versões de prompt e scores de avaliação. Depende de **ClickHouse** (via ClickHouse operator), reutilizando o PostgreSQL (CNPG), o Redis e o Garage do projeto. Ligado no `mvp`, desligado por padrão no `dev` para economizar recursos. |

## Infraestrutura e engenharia

| Item | Escolha |
|------|---------|
| Orquestração | **Kubernetes** em todos os ambientes (sem Docker Compose) |
| Cluster local (dev) | **k3d** (k3s em containers, leve no WSL2) |
| Cluster on-prem (MVP/produção) | **k3s**; **RKE2** para clientes que exigem endurecimento (CIS/FIPS), comum no setor público |
| Empacotamento | **Helm**: chart próprio da aplicação + charts oficiais (Qdrant, Langfuse, LiteLLM, CloudNativePG, Redis) |
| Deploy | **Argo CD (GitOps)** desde o MVP: o estado do cluster é o que está no Git |
| Imagens | Build OCI (Dockerfile) no CI, publicadas em registry on-prem |
| GPU | Fora do cluster no MVP; **NVIDIA GPU Operator** no Kubernetes _(Fase 6)_ |
| Métricas | Prometheus + Grafana (incluindo DCGM para GPU) |
| Python tooling | uv (dependências), ruff (lint/format), mypy (tipos), pytest |
| Frontend tooling | pnpm, ESLint, Prettier, Vitest/Playwright |
| CI | Lint + testes + avaliação de regressão do RAG em PRs que tocam o pipeline |

## Fase posterior (arquitetura-alvo)

- **Keycloak OIDC** (Organizations), para identidade multi-tenant.
- **Presidio**, para redação de PII (LGPD) em prompts e logs.
- **NeMo Guardrails**, para guardrails de entrada e saída.
- **Dagster**, para orquestrar a ingestão com linhagem e reprocessamento.
- **LangGraph + Temporal**, para agentes e fluxos duráveis.
- **SGLang**, como pool de inferência com prefix cache para RAG.
- Verificação da extração com Vision-LLM.
- Auditoria WORM no PostgreSQL (CNPG).
