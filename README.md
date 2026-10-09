# clear-helper

Chatbot RAG **100% on-premises** da ClearIT, focado em **embedding inteligente** dos documentos enviados pelo usuário: parsing estrutural, chunking semântico com contexto, busca híbrida com rerank e enriquecimento por LLM.

- Missão, princípios, stack e fases: [`constitution/`](constitution/)
- Contrato entre backend, frontend e infra: [`docs/arquitetura/fase-0-contrato.md`](docs/arquitetura/fase-0-contrato.md)

**Fase atual: 0 (Fundação).**

## Estrutura

| Pasta | Conteúdo |
|-------|----------|
| [`backend/`](backend/) | FastAPI (API) + worker arq · Python 3.12 · uv |
| [`frontend/`](frontend/) | Next.js 15 · TypeScript · Tailwind · pnpm |
| [`infra/`](infra/) | k3d, Helm chart, Argo CD (app-of-apps) e values `dev`/`mvp` |
| [`scripts/`](scripts/) | Verificação de pré-requisitos e subida/descida do ambiente dev |
| [`eval/`](eval/) | Golden set e resultados de avaliação (a partir da Fase 1) |
| [`.github/workflows/`](.github/workflows/) | CI: lint, testes, `helm lint`/kubeconform, build de imagens |

## Começando (dev)

1. Verifique os pré-requisitos. O script lista o que falta e como instalar:
   ```bash
   ./scripts/setup-dev.sh
   ```
   São eles: Docker acessível no WSL (integração do Docker Desktop), k3d, kubectl, helm, kubeseal, uv, pnpm e Node ≥ 20.
2. Gere o lockfile do backend (uma vez) e configure a URL do repositório GitHub em `infra/argocd/root.yaml`.
3. Suba o ambiente (cluster k3d + Argo CD + Sealed Secrets + imagens + app):
   ```bash
   ./scripts/dev-up.sh
   ```
4. Acesse http://clear-helper.localhost e entre com o admin de bootstrap (as credenciais são impressas pelo `dev-up.sh`).

Para derrubar: `./scripts/dev-down.sh` (`--purge` remove também o registry).

Detalhes em [`infra/README.md`](infra/README.md), [`backend/README.md`](backend/README.md) e [`frontend/README.md`](frontend/README.md).

## Regras do projeto

Resumo das regras de [`CLAUDE.md`](CLAUDE.md) e da constituição:

- Nenhum dado nem chamada de modelo sai do ambiente on-premises.
- Toda entidade e toda consulta são isoladas por `tenant_id`.
- Mudanças no pipeline RAG só entram com comparação de métricas no golden set.
- Secrets nunca ficam em claro no Git (Sealed Secrets).
