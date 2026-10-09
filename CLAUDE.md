# CLAUDE.md

Chatbot RAG on-premises da ClearIT focado em **embedding inteligente** de documentos enviados pelo usuário.

## Leia primeiro
- `constitution/mission.md`: princípios inegociáveis.
- `constitution/tech-stack.md`: stack aprovada. Não introduza tecnologia fora dela sem validar com o usuário.
- `constitution/roadmap.md`: fases e critérios de pronto. Trabalhe só no escopo da fase atual.
- `docs/arquitetura/fase-0-contrato.md`: nomes de serviços, env vars `CH_*` e rotas da API. Mudou o contrato? Atualize backend, frontend e infra juntos.

## Regras do projeto
- **100% on-premises:** nunca configure provedor de LLM em nuvem nem envie dados para fora.
- **Tenant em tudo:** toda entidade herda `TenantScoped`; toda consulta (SQL e Qdrant) filtra por `tenant_id`.
- **Eval antes de merge:** mudanças em parsing, chunking, embedding ou recuperação exigem comparação no golden set (`eval/`).
- **Kubernetes em todos os ambientes** (k3d no dev), deploy via Helm + Argo CD. Não crie docker-compose.
- **Secrets:** nunca em claro no Git; use Sealed Secrets.
- Código e comentários em inglês; documentação em pt-BR.
- Decisões que não estão na constituição devem ser validadas com o usuário (AskUserQuestion) antes de implementar.

## Estrutura
- `backend/`: FastAPI + worker arq (Python 3.12, uv, ruff, mypy, pytest).
- `frontend/`: Next.js 15 (pnpm, ESLint, Vitest).
- `infra/`: k3d, Helm chart, Argo CD e values por ambiente.
- `scripts/`: setup e subida do ambiente dev.
- `eval/`: golden set e resultados de avaliação.
