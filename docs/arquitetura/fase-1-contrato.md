# Fase 1: Contrato de integração (Baseline RAG + Avaliação)

Complementa o [contrato da Fase 0](fase-0-contrato.md), que continua valendo.
O objetivo e o critério de pronto estão em `constitution/roadmap.md`, Fase 1.

> **Baseline proposital:** extração de texto simples, chunking de tamanho fixo e embedding dense.
> Ela existe para ser a régua das Fases 2 a 5. Não antecipe parsing estrutural, chunking semântico,
> busca híbrida, rerank nem enriquecimento.

## Decisões validadas

| Tema | Decisão |
|------|---------|
| LLM (dev) | `qwen3.5:2b` via Ollama local (CPU; o 4b não cabe na memória do WSL junto com o cluster), exposto no LiteLLM como `qwen3`. Requer Ollama ≥ versão que suporte Qwen3.5 2B |
| Embedding (dev) | `bge-m3` via Ollama (dense, 1024 dimensões), exposto no LiteLLM como `bge-m3` |
| Golden set v1 | Normas públicas (LGPD 13.709/2018, Licitações 14.133/2021 e LAI 12.527/2011); perguntas geradas por LLM e revisadas por humano |
| Histórico de conversa | **Só na sessão** (navegador). O cliente envia o histórico a cada pergunta e nada é persistido no servidor |

## Modelo de dados

`documents` (herda `TenantScoped`):

| Coluna | Tipo | Observação |
|--------|------|------------|
| `id` | uuid pk | |
| `tenant_id` | uuid fk → tenants, indexado | |
| `filename` | text | nome original |
| `content_type` | text | |
| `size_bytes` | bigint | |
| `sha256` | text | único por (`tenant_id`, `sha256`): reenviar o mesmo arquivo devolve 409 com o id existente |
| `s3_key` | text | `tenants/{tenant_id}/documents/{id}/original` |
| `status` | enum | `uploaded` → `processing` → `indexed` \| `failed` |
| `error` | text null | mensagem curta quando `failed` |
| `page_count` | int null | |
| `chunk_count` | int null | |
| `pipeline_version` | text null | ex.: `baseline-v1` |
| `created_at`, `updated_at` | timestamptz | |

## Formatos e limites (Fase 1)

- Aceitos: PDF (`pypdf`, texto nativo e sem OCR), DOCX (`python-docx`), TXT, Markdown e HTML (texto visível).
- Tamanho máximo: `CH_UPLOAD_MAX_MB` (padrão 50). Acima disso, 413. Tipo não suportado, 415.
- PDF sem texto extraível (escaneado) termina em `failed` com o erro `"Documento sem texto extraível (OCR chega na Fase 2)"`.

## Pipeline de ingestão baseline (`pipeline_version = baseline-v1`)

1. A API grava o arquivo no S3, cria o documento com status `uploaded` e enfileira `ingest_document(document_id, tenant_id)` no arq.
2. O worker:
   - muda o status para `processing`;
   - extrai o texto **por página** (no PDF, a página real; nos demais formatos, a página é sempre 1);
   - divide em **chunks de tamanho fixo**: `CH_CHUNK_SIZE` caracteres (padrão 1000) com `CH_CHUNK_OVERLAP` de sobreposição (padrão 200), sem atravessar páginas;
   - gera os embeddings via LiteLLM (`/v1/embeddings`, modelo `CH_EMBEDDING_MODEL`=`bge-m3`) em lotes;
   - faz upsert no Qdrant;
   - muda o status para `indexed`, gravando `chunk_count` e `page_count`.
3. Qualquer erro deixa o status em `failed` com o campo `error` preenchido. Reprocessar é idempotente: os pontos antigos do documento são apagados antes do novo upsert.

## Qdrant

- Coleção: `CH_QDRANT_COLLECTION` (padrão `chunks_baseline_v1`), vetor nomeado `dense` com 1024 dimensões e distância Cosine. A API cria a coleção no startup se ela não existir.
- O nome da coleção identifica a versão da estratégia: trocar o modelo de embedding ou o chunking significa usar uma coleção nova (regra de reindexação da constituição).
- Índices de payload: `tenant_id` (keyword, `is_tenant=true`) e `document_id` (keyword).
- Payload de cada ponto: `tenant_id`, `document_id`, `filename`, `page`, `chunk_index`, `text`, `char_start`, `char_end`, `pipeline_version`, `embedding_model`.
- **Toda busca filtra por `tenant_id`.** Não existe busca sem esse filtro.

## Novas variáveis de ambiente

| Variável | Padrão | Uso |
|----------|--------|-----|
| `CH_LLM_MODEL` | `qwen3` | nome do modelo de chat no LiteLLM |
| `CH_EMBEDDING_MODEL` | `bge-m3` | nome do modelo de embedding no LiteLLM |
| `CH_EMBEDDING_DIM` | `1024` | dimensão do vetor dense |
| `CH_QDRANT_COLLECTION` | `chunks_baseline_v1` | coleção da baseline |
| `CH_CHUNK_SIZE` / `CH_CHUNK_OVERLAP` | `1000` / `200` | chunking fixo (caracteres) |
| `CH_RETRIEVAL_TOP_K` | `5` | trechos usados no contexto |
| `CH_RETRIEVAL_MIN_SCORE` | `0.35` | abaixo disso o trecho é descartado; sem trechos, a resposta é recusada |
| `CH_UPLOAD_MAX_MB` | `50` | limite de upload |
| `CH_LLM_TIMEOUT_SECONDS` | `300` | timeout de geração (CPU é lento) |

## API (Fase 1)

Todas as rotas exigem `Authorization: Bearer <jwt>` e operam **somente** no tenant do token.

| Método e rota | Resposta |
|---------------|----------|
| `POST /documents` (multipart, campo `file`) | 202 + `Document`; 409 `{"detail","document_id"}` se for duplicado; 413/415 |
| `GET /documents` | `{"items":[Document]}`, ordenado por `created_at desc` |
| `GET /documents/{id}` | `Document`; 404 se não existir ou for de outro tenant |
| `GET /documents/{id}/file` | o arquivo original (stream, com `Content-Type` e `Content-Disposition: inline`) |
| `DELETE /documents/{id}` | 204; remove do S3, do Qdrant e do PostgreSQL |
| `POST /documents/{id}/reprocess` | 202; reenfileira a ingestão |
| `POST /search` | body `{"query","top_k"?}` → `{"results":[Source]}` (sem LLM; usado pelo eval e para depuração) |
| `POST /chat` | body `{"question","history":[{"role":"user"\|"assistant","content"}]}` (máximo de 10 mensagens) → **SSE** |

`Document`: `{"id","filename","content_type","size_bytes","status","error","page_count","chunk_count","pipeline_version","created_at","updated_at"}`

`Source`: `{"ref":1,"document_id","filename","page","chunk_index","score","text"}`. `ref` é o número usado na citação `[1]`.

### Eventos SSE do `/chat` (`text/event-stream`, `data:` em JSON)

| `event` | `data` |
|---------|--------|
| `sources` | `{"sources":[Source]}`, enviado primeiro (pode vir vazio) |
| `token` | `{"text":"..."}`, repetido durante o stream |
| `done` | `{"answer":"<texto completo>","refused":bool,"usage":{...}\|null,"latency_ms":n}` |
| `error` | `{"detail":"..."}` |

### Regras de resposta (prompt do sistema, em pt-BR)

- Responder **apenas** com base nos trechos fornecidos, citando cada afirmação com `[n]`.
- Sem trechos acima de `CH_RETRIEVAL_MIN_SCORE`, a API **não chama o LLM**: responde com `refused=true` e o texto fixo `"Não encontrei essa informação nos documentos enviados."`.
- Se os trechos não respondem à pergunta, o modelo deve dizer que não encontrou a informação (o eval mede essa recusa).
- O histórico serve só para entender a pergunta atual; a busca usa a pergunta atual.
- Os blocos de raciocínio (`<think>…</think>`) dos modelos Qwen são removidos do stream.

## Avaliação (`eval/`)

- `eval/corpus/`: `sources.yaml` (URL oficial, sha256 e licença de cada norma) e o script `fetch_corpus.py`, que baixa e converte os textos para PDF ou TXT. Os arquivos baixados não são versionados no Git.
- `eval/golden-set/v1.jsonl`, uma pergunta por linha:
  `{"id","question","type":"factual"|"multi_hop"|"unanswerable","reference_answer","evidence":[{"document","quote","locator"}],"reviewed":bool}`
  - `evidence.quote`: trecho literal curto (de 30 a 200 caracteres) do documento. Um chunk recuperado é **relevante** se contém o quote normalizado (minúsculas, espaços colapsados), o que torna o critério independente da estratégia de chunking.
  - Ao menos 50 perguntas: cerca de 70% `factual`, 20% `multi_hop` e 10% `unanswerable` (para medir a recusa).
- `eval/run_eval.py`:
  - faz login na API;
  - garante o corpus no tenant de avaliação (upload idempotente) e espera tudo ficar `indexed`;
  - roda `/search` (para Recall@k, MRR e nDCG@k, com k ∈ {1, 3, 5, 10}) e `/chat` (para resposta, recusa e latência);
  - opcionalmente roda o RAGAS (faithfulness, answer relevancy e context precision) com o juiz local via LiteLLM.
  - Saída: `eval/results/<data>-<pipeline_version>.json` e `.md`, com a latência p50/p95 do `/chat`.
- **Orçamento de latência:** a p95 medida na baseline fica registrada como referência para a Fase 4.
