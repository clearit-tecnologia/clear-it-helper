# Infra do clear-helper (Fase 0)

Kubernetes em todos os ambientes: **k3d** no dev e **k3s/RKE2** on-prem (mvp). O deploy usa
**Helm + Argo CD** (GitOps, padrão app-of-apps), e os segredos ficam em **Sealed Secrets**.
Os nomes de serviços, portas e variáveis seguem `docs/arquitetura/fase-0-contrato.md`.

## Estrutura

```
infra/
├── k3d/cluster.yaml              # cluster dev: registry, porta 80 -> Traefik
├── helm/clear-helper/            # chart da aplicação (camadas "data" e "app")
├── argocd/
│   ├── root.yaml                 # Application raiz (app-of-apps); ÚNICO lugar com a URL do repo
│   ├── apps/                     # chart que gera as Applications de cada componente
│   └── install/argocd-values.yaml# values da instalação do próprio Argo CD
├── values/
│   ├── common/                   # values comuns dos charts de terceiros
│   ├── dev/                      # overrides do dev (k3d)
│   └── mvp/                      # overrides do mvp (on-prem)
└── secrets/
    ├── dev/                      # gerado pelo seal-dev-secrets.sh (fora do Git)
    └── mvp/                      # SealedSecrets do mvp (versionados)
```

## Fluxo de desenvolvimento

1. **Pré-requisitos.** O script apenas verifica o ambiente e mostra como instalar o que faltar:

   ```bash
   scripts/setup-dev.sh
   ```

   Ele verifica docker (com daemon acessível no WSL), k3d, kubectl, helm, kubeseal, uv, pnpm e
   node >= 20. Deixe pelo menos 8 GiB de memória para o Docker/WSL.

2. **Modelos locais (opcional, para o chat responder).** O Ollama roda na máquina host, fora do
   cluster, e precisa escutar em todas as interfaces:

   ```bash
   OLLAMA_HOST=0.0.0.0:11434 ollama serve
   ollama pull qwen3:4b && ollama pull bge-m3
   ```

   O LiteLLM do cluster acessa o Ollama por `http://host.k3d.internal:11434` (`infra/values/dev/litellm.yaml`).

3. **Subir o ambiente:**

   ```bash
   scripts/dev-up.sh
   ```

   O script executa, em ordem:
   - cria o cluster k3d `clear-helper` com registry `registry.localhost:5000` e Traefik;
   - instala o Sealed Secrets (`kube-system`) e o Argo CD (`argocd`);
   - gera `backend/uv.lock`, se ainda não existir, e faz build e push das imagens
     `clear-helper-backend:dev` e `clear-helper-frontend:dev` no registry do k3d;
   - gera os secrets de dev com valores aleatórios, sela e aplica no cluster (`scripts/seal-dev-secrets.sh`);
   - aplica a `root.yaml`. A partir daí o Argo CD sincroniza tudo a partir do Git.

   Pode rodar de novo quando quiser: o script recompila e publica as imagens e reinicia os Deployments.
   Variáveis aceitas: `SKIP_BUILD=1`, `SKIP_ROOT=1`, `REGISTRY_PUSH`, `IMAGE_TAG`.

4. **Acessar:**
   - App: <http://clear-helper.localhost>
   - API: <http://clear-helper.localhost/api/health/ready>
   - Login: `admin@clearit.com.br`. A senha é gerada pelo script; para consultar:

     ```bash
     kubectl -n clear-helper get secret clear-helper-app \
       -o jsonpath='{.data.bootstrap-admin-password}' | base64 -d; echo
     ```

   - Argo CD: `kubectl -n argocd port-forward svc/argocd-server 8080:80` e abra <http://localhost:8080>
     (usuário `admin`, senha no secret `argocd-initial-admin-secret`).

   Dentro do WSL, `*.localhost` pode não resolver (no navegador do Windows resolve). Nesse caso,
   use `curl -H "Host: clear-helper.localhost" http://127.0.0.1/api/health/live` ou adicione a
   entrada no `/etc/hosts`.

5. **Derrubar o ambiente:**

   ```bash
   scripts/dev-down.sh            # pede confirmação
   scripts/dev-down.sh --purge    # também remove o volume do registry e os secrets selados de dev
   ```

> **Importante:** o Argo CD sincroniza a partir do repositório **remoto**. Mudanças no chart ou nos
> values só chegam ao cluster depois do push para a branch configurada em `root.yaml` (`main`).
> As imagens de dev vêm do registry local, então não dependem de push.

## Como trocar a URL do repositório

A URL aparece **somente** em `infra/argocd/root.yaml`, no campo `spec.source.repoURL`. A URL
atual é `https://github.com/clearit-tecnologia/clear-it-helper.git` (repositório público, então o Argo CD lê via HTTPS sem credencial).

1. Edite `spec.source.repoURL` (e `targetRevision`, se não for `main`).
2. Faça commit e push.
3. Aplique de novo: `kubectl apply -n argocd -f infra/argocd/root.yaml`, ou rode `scripts/dev-up.sh`.

As Applications filhas recebem a URL e a revisão automaticamente, pelas variáveis de build do Argo CD
(`$ARGOCD_APP_SOURCE_REPO_URL` e `$ARGOCD_APP_SOURCE_TARGET_REVISION`). Os scripts leem a URL do
mesmo arquivo. Enquanto a URL for o placeholder, o `dev-up.sh` não aplica a `root.yaml` e mostra um aviso.

**Repositório privado:** cadastre a credencial no Argo CD uma vez por cluster, sem commitar o token:

```bash
argocd repo add https://github.com/<org>/clear-helper.git --username <user> --password <token-somente-leitura>
```

Outra opção é criar um Secret com o label `argocd.argoproj.io/secret-type: repository`, selado.

## Ordem de sincronização (sync-waves)

| Wave | Applications | Conteúdo |
|------|--------------|----------|
| -1 | (recursos da root) | `AppProject clear-helper` e repositórios OCI (`ghcr.io/berriai`, `ghcr.io/clickhouse`) |
| 0 | `sealed-secrets`, `cnpg-operator`, `clickhouse-operator`* | operadores e CRDs |
| 1 | `clear-helper-secrets`** | SealedSecrets versionados em `infra/secrets/mvp` |
| 2 | `clear-helper-data`, `qdrant` | CNPG `clear-helper-pg` (e `langfuse-pg`*), Valkey, Garage + Job de bootstrap (PostSync), Qdrant |
| 3 | `litellm`, `langfuse`* | gateway de modelos e observabilidade |
| 4 | `clear-helper` | API, worker, frontend, Jobs PreSync (migração e depois bootstrap) e IngressRoute |

\* só com `langfuse.enabled: true`. \*\* só no mvp (`secretsApp.enabled`).

O chart `clear-helper` é aplicado duas vezes (`clear-helper-data` e `clear-helper`), com os toggles
`components.data.enabled` e `components.app.enabled`. Assim, o Job PreSync de migração só roda quando o
PostgreSQL já existe. Para as waves esperarem a wave anterior ficar saudável, o Argo CD precisa do
health check de `Application`, que já está configurado em `infra/argocd/install/argocd-values.yaml`.

## Versões fixadas

| Componente | Chart | Versão | App |
|-----------|-------|--------|-----|
| Argo CD | `argo/argo-cd` | 10.10.1 | v3.5.4 |
| Sealed Secrets | `https://bitnami.github.io/sealed-secrets` `sealed-secrets` | 2.20.0 | 0.40.0 |
| CloudNativePG | `cnpg/cloudnative-pg` | 0.29.1 | 1.30.1 |
| ClickHouse operator | `oci://ghcr.io/clickhouse/clickhouse-operator-helm` | 0.0.8 | v0.0.8 |
| Qdrant | `qdrant/qdrant` | 1.19.2 | v1.19.2 |
| LiteLLM | `oci://ghcr.io/berriai/litellm-helm` | 1.104.2 | 1.104.2 |
| Langfuse | `langfuse/langfuse` | 2.1.4 | 4.50.0 |
| k3s (k3d) | `rancher/k3s` | v1.36.5-k3s1 | — |
| PostgreSQL | `ghcr.io/cloudnative-pg/postgresql` | 16.15-standard-trixie | — |
| Valkey | `valkey/valkey` | 9.1.2-alpine | — |
| Garage | `dxflrs/garage` | v2.4.1 | — |

As versões dos charts ficam em `infra/argocd/apps/values.yaml`. A versão do Argo CD fica em
`scripts/lib/common.sh`.

## Toggles principais

- `langfuse.enabled` em `infra/values/<env>/apps.yaml`: ativa o Langfuse, o ClickHouse operator, o
  CNPG `langfuse-pg`, o bucket e a chave `langfuse` no Garage e as variáveis `CH_LANGFUSE_*`. Fica
  desligado no dev e ligado no mvp. O chart da app recebe o mesmo valor por parâmetro, então só é
  preciso alterar um lugar.
- `networkPolicy.enabled`, `ingress.type` (`traefik` = IngressRoute, `kubernetes` = Ingress com
  middleware) e as réplicas, recursos e storage: em `infra/values/<env>/clear-helper.yaml`.

## Secrets

Nenhum Secret é criado em claro pelo chart. No dev, todos são gerados pelo `seal-dev-secrets.sh`. No
mvp, devem ser selados com a chave do cluster mvp e versionados em `infra/secrets/mvp/`.

| Secret (ns `clear-helper`) | Chaves | Consumidores |
|---------------------------|--------|--------------|
| `clear-helper-app` | `jwt-secret` (>= 32 caracteres), `bootstrap-admin-password` (>= 8) | API (`CH_JWT_SECRET`) e Job de bootstrap |
| `clear-helper-garage` | `rpc-secret` (64 hex), `admin-token`, `access-key-id` (`GK` + 24 hex), `secret-access-key` (64 hex), `langfuse-access-key-id`, `langfuse-secret-access-key` | Garage, Job de bootstrap do Garage, API/worker (`CH_S3_*`) e Langfuse |
| `litellm-masterkey` | `masterkey` (`sk-...`) | LiteLLM e backend (`CH_LITELLM_API_KEY`) |
| `langfuse-secrets` | `salt`, `encryption-key` (64 hex), `nextauth-secret`, `clickhouse-password`, `public-key` (`pk-lf-...`), `secret-key` (`sk-lf-...`), `admin-email`, `admin-password` | Langfuse (init headless) e backend (`CH_LANGFUSE_*`) |
| `clear-helper-pg-app` | `uri`, ... | criado pelo CloudNativePG (`CH_DATABASE_URL`) |
| `litellm-upstream` (só mvp) | `VLLM_API_KEY`, `EMBEDDINGS_API_KEY` | LiteLLM (servidor GPU externo) |
| `clear-helper-tls`, `langfuse-tls` (só mvp) | `tls.crt`, `tls.key` | IngressRoute e Ingress |

**Credenciais do S3 (Garage).** As chaves não são geradas pelo Garage. Elas vêm do Secret
`clear-helper-garage` e o Job `clear-helper-garage-bootstrap` as importa (`/v2/ImportKey`). O mesmo
Job aplica o layout do nó e cria o bucket `clear-helper-docs` (e `langfuse`) com permissão
read/write/owner. É idempotente e roda em todo sync, como PostSync. Assim, o Secret montado na API é
sempre a fonte da verdade.

## Ambiente mvp (on-prem)

1. Cluster k3s ou RKE2 com Traefik e uma StorageClass padrão.
2. Instale o Sealed Secrets e o Argo CD com os mesmos comandos `helm upgrade --install` do `dev-up.sh`
   (mesmas versões e values).
3. Sele os secrets da tabela acima em `infra/secrets/mvp/` e faça commit.
4. Preencha os `CHANGE-ME` em `infra/values/mvp/`:
   - host do Harbor e tag da imagem;
   - domínios;
   - endpoints do servidor GPU (vLLM e embeddings) no `litellm.yaml`.
5. Em `root.yaml`, troque `../../values/dev/apps.yaml` por `../../values/mvp/apps.yaml` e aplique.

Para ambientes sem internet, espelhe no Harbor as imagens e os charts listados em "Versões fixadas"
e ajuste `repoURL` e `image.repository`.

## Validação local

```bash
helm lint infra/helm/clear-helper -f infra/values/dev/clear-helper.yaml
helm template t infra/helm/clear-helper -f infra/values/mvp/clear-helper.yaml --set langfuse.enabled=true
helm template r infra/argocd/apps -f infra/values/dev/apps.yaml --set repoURL=https://example.invalid/r.git
```

O CI (`.github/workflows/ci.yml`) roda esses comandos e também o kubeconform e o shellcheck.
