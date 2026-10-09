# Roadmap

> Fases organizadas por dependência. Cada fase tem objetivo, entregáveis e **critério de pronto**.
> Sem datas fixas: uma fase só começa quando a anterior cumpre o critério de pronto.
> A partir da Fase 1, toda fase que mexe no pipeline precisa mostrar o ganho de métricas sobre a fase anterior.

## Fase 0 — Fundação

**Objetivo:** criar um esqueleto executável com isolamento por tenant desde o primeiro commit.

Entregáveis:
- Monorepo (`backend/`, `frontend/`, `eval/`, `infra/`) com tooling configurado (uv, ruff, mypy, pytest, pnpm).
- Cluster local com k3d e Helm chart da aplicação (FastAPI, Next.js e worker) + charts de PostgreSQL (CloudNativePG), Qdrant, Redis, Garage, LiteLLM e Langfuse.
- Argo CD sincronizando o cluster a partir do repositório (GitOps), com ambientes `dev` e `mvp` como values separados.
- vLLM com Qwen3 e o serviço de embeddings/rerank (BGE-M3) em servidor GPU dedicado fora do cluster, acessíveis via LiteLLM.
- Modelo de dados com `tenant_id` em todas as entidades, autenticação JWT local e migrações Alembic.
- Pipeline de CI com lint e testes.

**Pronto quando:** um cluster k3d novo, com Argo CD apontado para o repositório, sobe o ambiente completo sem passos manuais, um usuário faz login e o health check responde para todos os serviços.

## Fase 1 — Baseline RAG + Avaliação

**Objetivo:** ter um RAG ponta a ponta simples e uma régua para medir todo o resto.

Entregáveis:
- Upload de documentos, armazenamento no S3 e ingestão assíncrona com status visível na UI.
- Baseline proposital: extração de texto simples, chunking de tamanho fixo e embedding dense com BGE-M3.
- Chat com streaming via SSE, citações clicáveis (documento e página/trecho) e recusa quando não há evidência.
- **Golden set v1** em pt-BR (≥ 50 perguntas sobre documentos reais ou representativos do setor público).
- Script de avaliação (Recall@k, MRR, RAGAS) e traces no Langfuse.

**Pronto quando:** o fluxo upload → pergunta → resposta citada funciona, e as métricas da baseline estão registradas em `eval/results/`.

## Fase 2 — Pilar 1: Parsing estrutural

**Objetivo:** fazer o sistema entender o documento antes de fragmentá-lo.

Entregáveis:
- Docling para PDF, DOCX, XLSX e PPTX, preservando seções, tabelas e listas.
- OCR para documentos escaneados, com detecção automática da necessidade.
- Persistência do documento estruturado (DoclingDocument) no S3, para reprocessar sem novo parsing.
- Citações com página e caminho de seção (ex.: "Art. 5º › §2º").

**Pronto quando:** as tabelas e os PDFs escaneados do golden set são recuperáveis e as métricas superam a baseline.

## Fase 3 — Pilar 2: Chunking semântico + Contextual Retrieval

**Objetivo:** criar chunks que respeitam o sentido e carregam o contexto do documento.

Entregáveis:
- HybridChunker do Docling, sem cortar seção ou tabela no meio e respeitando o limite de tokens do BGE-M3.
- Geração de contexto por chunk com Qwen3, prefixado antes do embedding.
- Versionamento de estratégia de chunking por coleção, com reindexação controlada.

**Pronto quando:** há ganho mensurável de Recall@k e de faithfulness sobre a Fase 2, e o custo de ingestão (tempo e GPU por página) está documentado.

## Fase 4 — Pilar 3: Busca híbrida + Rerank

**Objetivo:** encontrar o trecho certo, inclusive quando a pergunta usa termos exatos (números de lei, siglas, códigos).

Entregáveis:
- Vetores sparse do BGE-M3 indexados junto aos dense, com fusão RRF via Qdrant Query API.
- Reranking com bge-reranker-v2-m3 sobre o top-k.
- Parâmetros (k, limiar de score, pesos) configuráveis e ajustados pelo golden set.

**Pronto quando:** há ganho em MRR e nDCG sobre a Fase 3, com a latência p95 do chat dentro do orçamento definido na Fase 1.

## Fase 5 — Pilar 4: Enriquecimento por LLM

**Objetivo:** dar a cada chunk metadados que ampliem os caminhos de recuperação.

Entregáveis:
- Extração estruturada por chunk: resumo, palavras-chave, perguntas hipotéticas e classificação/tipo.
- Indexação das perguntas hipotéticas como vetores adicionais e dos metadados como filtros.
- Filtros na UI (por documento, tipo e data).
- Ingestão incremental: só reprocessa o que mudou.

**Pronto quando:** há ganho mensurável sobre a Fase 4 que justifique o custo extra de GPU. Se não houver ganho, o pilar fica desativável por configuração.

## Fase 6 — Endurecimento para produção

**Objetivo:** levar o MVP à arquitetura-alvo da ClearIT AI Platform.

Entregáveis:
- Keycloak OIDC (Organizations), substituindo o JWT local.
- Presidio (redação de PII/LGPD) e NeMo Guardrails.
- Dagster na orquestração da ingestão.
- vLLM e embeddings migrados para dentro do Kubernetes com NVIDIA GPU Operator, em cluster k3s/RKE2 on-prem.
- Prometheus/Grafana (DCGM), alertas e auditoria WORM.
- Feedback do usuário (👍/👎) alimentando o golden set.

**Pronto quando:** o sistema passa por revisão de segurança e por teste de carga, com isolamento entre tenants comprovado por testes automatizados.

## Futuro (fora do escopo atual)

- Canais adicionais (WhatsApp corporativo, APIs externas).
- Agentes com LangGraph + Temporal e integrações via MCP.
- Pool SGLang com prefix cache e verificação de extração com Vision-LLM.
