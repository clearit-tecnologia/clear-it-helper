#!/usr/bin/env bash
# Checks the dev prerequisites (WSL2/Linux). It only CHECKS and prints how to install
# what is missing; it never installs anything.
set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

missing=0
optional_missing=0

# version_ge <actual> <minimum>  (dotted versions)
version_ge() {
  [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" == "$2" ]]
}

extract_version() {
  grep -Eo '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n1
}

check() {
  # check <name> <min_version|-> <version command> <install hint>
  local name="$1" min="$2" version_cmd="$3" hint="$4" version=""
  if ! command -v "${name}" >/dev/null 2>&1; then
    warn "${name}: NÃO encontrado"
    printf '      como instalar: %s\n' "${hint}"
    missing=$((missing + 1))
    return 0
  fi
  version="$(bash -c "${version_cmd}" 2>/dev/null | extract_version || true)"
  if [[ "${min}" != "-" && -n "${version}" ]] && ! version_ge "${version}" "${min}"; then
    warn "${name}: versão ${version} encontrada, mínimo ${min}"
    printf '      como atualizar: %s\n' "${hint}"
    missing=$((missing + 1))
    return 0
  fi
  ok "${name} ${version:-(versão não identificada)}"
}

log "Verificando pré-requisitos do ambiente dev (nada será instalado)"

# Docker: CLI present AND daemon reachable from WSL.
if ! command -v docker >/dev/null 2>&1; then
  warn "docker: NÃO encontrado"
  printf '      como instalar: Docker Desktop no Windows com "Use the WSL 2 based engine" e a\n'
  printf '      integração com esta distro ativada (Settings > Resources > WSL integration),\n'
  printf '      ou Docker Engine nativo no WSL: https://docs.docker.com/engine/install/ubuntu/\n'
  missing=$((missing + 1))
elif ! docker info >/dev/null 2>&1; then
  warn "docker: CLI encontrado, mas o daemon não está acessível a partir do WSL"
  printf '      verifique se o Docker Desktop está rodando e se a integração WSL está ativa\n'
  # shellcheck disable=SC2016  # literal $USER for the user to copy
  printf '      para esta distro; no Docker Engine nativo: sudo usermod -aG docker "$USER"\n'
  missing=$((missing + 1))
else
  ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?') (daemon acessível)"
  mem_bytes="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)"
  if [[ "${mem_bytes}" =~ ^[0-9]+$ ]] && (( mem_bytes > 0 && mem_bytes < 8 * 1024 * 1024 * 1024 )); then
    warn "docker tem $((mem_bytes / 1024 / 1024)) MiB de memória; recomendado >= 8 GiB (.wslconfig: memory=8GB ou mais)"
  fi
fi

check k3d 5.6 "k3d version" \
  "curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash  (https://k3d.io)"
check kubectl 1.30 "kubectl version --client" \
  "https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/"
check helm 3.15 "helm version --short" \
  "https://helm.sh/docs/intro/install/  (v3.15+ ou v4)"
check kubeseal 0.27 "kubeseal --version" \
  "baixe o binário em https://github.com/bitnami/sealed-secrets/releases (kubeseal-<versão>-linux-amd64.tar.gz) e coloque em ~/.local/bin"
check uv 0.5 "uv --version" \
  "curl -LsSf https://astral.sh/uv/install.sh | sh  (https://docs.astral.sh/uv/)"
check node 20.0 "node --version" \
  "use nvm/fnm: 'fnm install 22' ou https://nodejs.org (LTS >= 20)"
check pnpm 9.0 "pnpm --version" \
  "corepack enable && corepack prepare pnpm@latest --activate  (ou npm i -g pnpm)"

# Optional tools.
for tool in argocd shellcheck; do
  if command -v "${tool}" >/dev/null 2>&1; then
    ok "${tool} (opcional)"
  else
    printf '      [opcional] %s não encontrado' "${tool}"
    case "${tool}" in
      argocd) printf ' (CLI do Argo CD: https://argo-cd.readthedocs.io/en/stable/cli_installation/)\n' ;;
      shellcheck) printf ' (lint de scripts: sudo apt-get install shellcheck)\n' ;;
    esac
    optional_missing=$((optional_missing + 1))
  fi
done

# *.localhost resolution inside WSL (browsers on Windows resolve it natively).
if command -v getent >/dev/null 2>&1 && ! getent hosts clear-helper.localhost >/dev/null 2>&1; then
  printf '      [dica] clear-helper.localhost não resolve dentro do WSL (no navegador do Windows funciona).\n'
  printf '      Para usar curl no WSL: curl -H "Host: clear-helper.localhost" http://127.0.0.1/api/health/live\n'
  printf '      ou adicione "127.0.0.1 clear-helper.localhost" ao /etc/hosts.\n'
fi

echo
if (( missing > 0 )); then
  die "${missing} pré-requisito(s) ausente(s) ou desatualizado(s). Instale-os e rode novamente."
fi
ok "Todos os pré-requisitos obrigatórios estão presentes. Próximo passo: scripts/dev-up.sh"
