# Avaliação (eval)

Régua de qualidade do clear-helper a partir da **Fase 1** (ver `constitution/roadmap.md` e
`docs/arquitetura/fase-1-contrato.md`, seção "Avaliação").

> **Regra da constituição (princípio 3, "Qualidade medida, não presumida"):** nenhuma mudança de
> parsing, chunking, embedding ou recuperação é aceita sem comparar as métricas do golden set antes
> e depois. A baseline da Fase 1 fica registrada em `results/` e é a referência das Fases 2 a 5,
> inclusive o orçamento de latência p95 do `/chat` usado na Fase 4.

## Estrutura

| Caminho | Conteúdo |
|---------|----------|
| `corpus/sources.yaml` | Fontes oficiais, licença, formato e sha256 de cada norma |
| `corpus/fetch_corpus.py` | Baixa as normas e as converte para TXT limpo |
| `corpus/files/` | Arquivos baixados e convertidos (**não versionado**, ver `.gitignore`) |
| `golden-set/v1.jsonl` | 60 perguntas em pt-BR (uma por linha) |
| `scripts/validate_golden_set.py` | Valida o schema, os quotes literais e a distribuição de tipos |
| `run_eval.py` | Roda a avaliação contra a API e grava `results/` |
| `ch_eval/` | Código compartilhado: normalização, conversor HTML, métricas, parser SSE |
| `tests/` | Testes pytest (métricas, normalização, SSE, conversor, validador, cliente) |
| `results/` | Métricas oficiais por fase (versionado) |

## Pré-requisitos

```bash
cd eval
uv sync            # projeto uv separado do backend, Python 3.12
```

## 1. Corpus

O corpus v1 tem três normas federais públicas:

| id | Norma | Fonte oficial | Arquivo convertido |
|----|-------|---------------|--------------------|
| `lgpd` | Lei 13.709/2018 (LGPD) | planalto.gov.br | `lei-13709-2018-lgpd.txt` |
| `licitacoes` | Lei 14.133/2021 (Licitações e Contratos) | planalto.gov.br | `lei-14133-2021-licitacoes.txt` |
| `lai` | Lei 12.527/2011 (LAI) | planalto.gov.br | `lei-12527-2011-lai.txt` |

**Licença:** textos de lei são de domínio público. A Lei 9.610/1998, art. 8º, IV, exclui da proteção
autoral os textos de leis e demais atos oficiais.

```bash
uv run python corpus/fetch_corpus.py                  # baixa, converte e confere o sha256
uv run python corpus/fetch_corpus.py --offline        # reconverte a partir de files/raw/
uv run python corpus/fetch_corpus.py --update-lock    # grava o novo sha256 no sources.yaml
uv run python corpus/fetch_corpus.py --strict         # falha (código 2) se o sha256 divergir
```

### Formato e versão do texto

- **Formato escolhido: TXT UTF-8**, um dispositivo (artigo, parágrafo, inciso ou alínea) por linha,
  sem menus, scripts nem estilos. A baseline aceita TXT (página sempre 1), a conversão é
  determinística e o mesmo arquivo serve para validar os quotes literais. A primeira linha
  identifica a norma e a URL de origem.
- **Texto compilado vigente:** a página do Planalto é o texto compilado, ou seja, já incorpora as
  alterações posteriores (inclusive as de 2026, como as Leis 15.352 e 15.452 na LGPD). A redação
  antiga continua na página, riscada (`<strike>` ou `text-decoration: line-through`). O conversor
  **remove a redação riscada** e **mantém as notas de alteração**, como
  "(Redação dada pela Lei nº 13.853, de 2019)" e "(Incluído pela ...)". O HTML original completo,
  com a redação histórica, fica em `corpus/files/raw/` para auditoria.
- **Encoding:** as páginas do Planalto não declaram charset e usam windows-1252. O conversor tenta
  UTF-8 e cai para cp1252 (bytes indefinidos passam como latin-1).
- **sha256:** o `sources.yaml` guarda o hash do **TXT convertido**, que é o arquivo enviado à API.
  O hash do HTML bruto não serve como trava porque o WAF do Planalto injeta um `<script>` aleatório
  a cada download. Ele fica registrado só em `corpus/files/manifest.json`, junto com a data e o
  `Last-Modified`.
- **Se o Planalto publicar nova redação**, o sha256 muda e o fetcher avisa. Nesse caso, rode o
  validador do golden set, corrija os quotes que deixaram de existir, revise as respostas de
  referência afetadas e só então rode `--update-lock`. Mudar o corpus invalida a comparação com
  resultados antigos.

### Segurança dos downloads

Os downloads são tratados como dados não confiáveis: só HTTPS em `*.gov.br` ou `*.leg.br` (também
após redirecionamentos), limite de 20 MB, gravação em `corpus/files/` (diretório próprio, fora do
Git) e leitura apenas pelo parser HTML da biblioteca padrão. Nada do que é baixado é executado.

## 2. Golden set

Uma pergunta por linha em `golden-set/v1.jsonl`, no schema do contrato:

```json
{"id": "lai-001", "question": "...", "type": "factual|multi_hop|unanswerable",
 "reference_answer": "...",
 "evidence": [{"document": "lei-12527-2011-lai.txt", "quote": "...", "locator": "Lei 12.527/2011, art. 11, § 1º"}],
 "reviewed": false}
```

Distribuição da v1 (60 perguntas, geradas por LLM e **pendentes de revisão humana**):

| Tipo | Qtd. | % | Observação |
|------|------|---|------------|
| `factual` | 42 | 70% | 12 LAI, 14 LGPD, 16 Lei 14.133 |
| `multi_hop` | 12 | 20% | 9 cruzam duas leis (6 LGPD×LAI, 3 LAI×14.133) e 3 combinam dispositivos da mesma lei |
| `unanswerable` | 6 | 10% | Temas plausíveis que não estão nas leis (algumas são "pegadinhas" próximas do texto, como o prazo de comunicação de incidente à ANPD) |

Regras:

- `evidence.quote` é um trecho **literal** de 30 a 200 caracteres do arquivo convertido. Na
  comparação, os dois lados passam por NFKC, minúsculas e colapso de espaços. Com isso, quebras de
  linha no meio do quote não atrapalham.
- Um chunk recuperado é **relevante** quando contém o quote normalizado e pertence ao mesmo
  documento (`Source.filename == evidence.document`). O critério não depende da estratégia de
  chunking: como os quotes têm até 200 caracteres e a sobreposição da baseline é de 200, todo quote
  cabe inteiro em pelo menos um chunk.
- `factual` exige pelo menos 1 evidência e `multi_hop` pelo menos 2. Em `unanswerable`, `evidence`
  fica vazio e a resposta de referência é a recusa.
- As perguntas não copiam o texto da lei. O validador avisa quando há 8 ou mais palavras seguidas
  iguais a um quote.

### Validar

```bash
uv run python scripts/validate_golden_set.py            # erros → código 1
uv run python scripts/validate_golden_set.py --strict   # avisos também reprovam
```

O validador confere o schema, os ids únicos, o tamanho dos quotes, a **presença literal de cada
quote no corpus convertido**, os quotes ambíguos (que aparecem mais de uma vez), o mínimo de 50
perguntas e as faixas de distribuição (factual 60–80%, multi_hop 15–25%, unanswerable 5–15%).

### Como revisar as perguntas (revisão humana)

Para cada linha com `"reviewed": false`:

1. Abra o arquivo convertido em `corpus/files/` e localize o quote (busca literal).
2. Confira se o `locator` (lei, artigo, parágrafo, inciso ou alínea) aponta o dispositivo certo.
3. Confira se a `reference_answer` está correta, completa e **só** usa o que está nas evidências.
   Valores sujeitos a atualização por decreto (dispensa de licitação, grande vulto) devem citar o
   valor da lei e mencionar a atualização.
4. Confira se a pergunta soa como a de um servidor público, sem copiar o texto da lei, e se tem uma
   única leitura razoável.
5. Em `multi_hop`, confira se a resposta precisa mesmo de todas as evidências.
6. Em `unanswerable`, procure no corpus (`grep -i`) e confirme que a resposta **não** está lá.
7. Corrija o que for preciso, mude para `"reviewed": true` e rode o validador.

Corrija tudo **antes** de registrar a baseline. Depois que houver resultado oficial em `results/`,
qualquer mudança de significado no golden set cria uma nova versão (`v2.jsonl`) e exige rodar a
baseline de novo, para que as comparações continuem válidas.

## 3. Rodar a avaliação

Pré-requisitos: backend da Fase 1 implantado (`http://clear-helper.localhost/api`) e um usuário
num **tenant dedicado ao eval**. Outros documentos no tenant entram na busca e distorcem as
métricas, e o script avisa quando isso acontece.

```bash
export EVAL_EMAIL=eval@clearit.local EVAL_PASSWORD='...'
uv run python run_eval.py                      # corpus + /search + /chat
uv run python run_eval.py --skip-chat          # só recuperação (rápido, sem LLM)
uv run python run_eval.py --limit 5            # rodada parcial (sufixo -limit5 no arquivo)
```

Principais flags: `--api-url` (padrão `http://clear-helper.localhost/api` ou `EVAL_API_URL`),
`--email`/`--password` (ou `EVAL_EMAIL`/`EVAL_PASSWORD`), `--top-k` (padrão 10), `--limit`,
`--skip-chat`, `--skip-upload`, `--reprocess-failed`, `--index-timeout`, `--chat-timeout`,
`--pipeline-version` e `--output-dir`.

O que o script faz:

1. `POST /auth/login` e `GET /auth/me` (registra o tenant).
2. Upload idempotente dos três TXT (`POST /documents`; 409 = já existe, usa o `document_id`) e
   espera todos ficarem `indexed`. Documento `failed` interrompe a execução, a menos que se use
   `--reprocess-failed`.
3. `POST /search` com `top_k=10` para cada pergunta: Recall@k, Hit@k, MRR e nDCG@k com
   k ∈ {1, 3, 5, 10}. As perguntas `unanswerable` ficam **fora** das métricas de recuperação, mas o
   top score delas é registrado (ajuda a calibrar `CH_RETRIEVAL_MIN_SCORE`).
4. `POST /chat` (SSE, sem histórico), uma pergunta por vez: resposta, recusa, citações `[n]`, TTFT e
   latência total no cliente (p50/p95), além do `done.latency_ms` do servidor.
5. Grava `results/<AAAA-MM-DD>-<pipeline_version>.json` (bruto, com cada resposta e cada chunk
   recuperado) e `.md` (tabela de métricas e detalhes por pergunta).

Definições:

- **Recall@k:** fração das evidências da pergunta cobertas pelos k primeiros chunks.
- **MRR:** 1/posição do primeiro chunk relevante.
- **nDCG@k:** ganho binário só para o chunk que cobre uma evidência **nova**, para que chunks
  sobrepostos com o mesmo quote não inflem o resultado. O ideal é uma evidência nova em cada uma das
  min(k, n) primeiras posições.
- **Recusa:** `done.refused=true` (a API não achou trecho acima do score mínimo) **ou** uma resposta
  do LLM do tipo "não encontrei / os trechos não mencionam…" (regex em `ch_eval/sse.py`).
  - Recusa correta = recusas / perguntas `unanswerable`.
  - Recusa indevida = recusas / perguntas respondíveis.

### RAGAS (opcional)

`--ragas` calcula faithfulness, answer relevancy e context precision (com a resposta de referência)
sobre as respostas não recusadas, usando os trechos que o LLM recebeu (evento `sources`). O juiz
roda **localmente** pelo endpoint OpenAI-compatível do LiteLLM. Nenhum provedor em nuvem é usado e a
telemetria do RAGAS fica desligada (`RAGAS_DO_NOT_TRACK=true`).

```bash
kubectl -n <namespace-da-app> port-forward svc/litellm 4000:4000   # em outro terminal
export EVAL_JUDGE_API_KEY='<master key do LiteLLM>'                 # nunca versionar
uv run python run_eval.py --ragas --judge-base-url http://localhost:4000/v1 \
    --judge-model qwen3 --judge-embedding-model bge-m3
```

Outras flags: `--judge-timeout`, `--judge-workers` (padrão 1, por causa da CPU) e
`--judge-extra-body` (JSON repassado ao modelo, por exemplo para desligar o modo de raciocínio, se o
LiteLLM ou o Ollama suportarem). Falhas do juiz viram `null` por pergunta e entram em `nan_counts`,
sem descartar a execução.

## 4. Testes

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Limitações conhecidas

- **Golden set gerado por LLM e ainda não revisado** (`reviewed: false` em todas as perguntas).
  Nenhum resultado deve ser tratado como oficial antes da revisão humana.
- **RAGAS com juiz 4B em CPU** (`qwen3.5:4b` via Ollama): é lento (cerca de 10 chamadas ao LLM por
  pergunta, o que pode levar horas para 54 perguntas), gera mais falhas de parsing de JSON (NaN) e
  avalia o próprio modelo gerador (viés de autoavaliação). Use o RAGAS como sinal relativo entre
  fases, sempre com o mesmo juiz. Para número absoluto, use um juiz maior em GPU (ambiente `mvp`).
- **Latência medida em CPU:** a p95 da baseline vale como orçamento só no mesmo hardware. Registre
  o hardware junto com o resultado.
- **Detecção de recusa por regex:** respostas parciais ("não há informação sobre X, mas…") podem
  contar como recusa. Confira os casos de fronteira no JSON.
- **Corpus pequeno e homogêneo** (3 leis, só TXT): não exercita PDF escaneado nem tabelas, que são
  o foco da Fase 2. Será preciso ampliar o corpus para medir os ganhos de parsing estrutural.
- Valores atualizados por decreto (dispensa, grande vulto) não estão no corpus. As respostas de
  referência usam o valor do texto da lei.
