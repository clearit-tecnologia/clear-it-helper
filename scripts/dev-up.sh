#!/usr/bin/env bash
# Brings up the full dev environment on k3d:
#   1. k3d cluster "clear-helper" (+ registry, Traefik, port 80)
#   2. Sealed Secrets controller (kube-system) and Argo CD (argocd)
#   3. build + push of the backend/frontend images to the k3d registry (tag "dev")
#   4. random dev secrets, sealed and applied (scripts/seal-dev-secrets.sh)
#   5. root Application (app-of-apps) -> Argo CD syncs everything else from Git
#
# Idempotent: re-running it rebuilds/pushes the images and restarts the app Deployments.
# Env vars: SKIP_BUILD=1, SKIP_ROOT=1, REGISTRY_PUSH (default localhost:5000), IMAGE_TAG.
set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

SCRIPTS_DIR="${REPO_ROOT}/scripts"

log "Verificando pré-requisitos"
"${SCRIPTS_DIR}/setup-dev.sh" >/dev/null || "${SCRIPTS_DIR}/setup-dev.sh"

# ---------------------------------------------------------------------------
# 1. Cluster
# ---------------------------------------------------------------------------
if cluster_exists; then
  ok "cluster k3d ${CLUSTER_NAME} já existe"
  k3d cluster start "${CLUSTER_NAME}" >/dev/null 2>&1 || true
else
  log "Criando cluster k3d ${CLUSTER_NAME} (${K3D_CONFIG#"${REPO_ROOT}"/})"
  k3d cluster create --config "${K3D_CONFIG}"
fi
kubectl config use-context "${KUBE_CONTEXT}" >/dev/null
kubectl_ctx wait --for=condition=Ready nodes --all --timeout=180s >/dev/null
ok "cluster pronto (contexto ${KUBE_CONTEXT})"

# ---------------------------------------------------------------------------
# 2. Sealed Secrets + Argo CD (bootstrap; Argo CD takes over sealed-secrets afterwards)
# ---------------------------------------------------------------------------
SEALED_SECRETS_VERSION="$(component_version sealed-secrets)"
[[ -n "${SEALED_SECRETS_VERSION}" ]] || die "versão do sealed-secrets não encontrada em ${APPS_VALUES}"

# Bootstrap only: once the root app exists, Argo CD owns Sealed Secrets and a second
# Helm (server-side apply) upgrade would conflict with the fields Argo CD manages.
if kubectl_ctx -n "${SEALED_SECRETS_NAMESPACE}" get deployment "${SEALED_SECRETS_CONTROLLER}" >/dev/null 2>&1; then
  ok "Sealed Secrets já instalado (gerenciado pelo Argo CD)"
else
  log "Instalando Sealed Secrets ${SEALED_SECRETS_VERSION} em ${SEALED_SECRETS_NAMESPACE}"
  helm_ctx upgrade --install sealed-secrets sealed-secrets \
    --repo https://bitnami.github.io/sealed-secrets \
    --version "${SEALED_SECRETS_VERSION}" \
    --namespace "${SEALED_SECRETS_NAMESPACE}" \
    -f "${REPO_ROOT}/infra/values/common/sealed-secrets.yaml" \
    --wait --timeout 5m >/dev/null
  ok "Sealed Secrets instalado"
fi

log "Instalando Argo CD (chart ${ARGOCD_CHART_VERSION}) em ${ARGOCD_NAMESPACE}"
helm_ctx upgrade --install argocd argo-cd \
  --repo "${ARGOCD_HELM_REPO}" \
  --version "${ARGOCD_CHART_VERSION}" \
  --namespace "${ARGOCD_NAMESPACE}" --create-namespace \
  -f "${REPO_ROOT}/infra/argocd/install/argocd-values.yaml" \
  --wait --timeout 10m >/dev/null
ok "Argo CD instalado"

# ---------------------------------------------------------------------------
# 3. Images
# ---------------------------------------------------------------------------
build_and_push() {
  local name="$1" context="$2"
  local image="${REGISTRY_PUSH}/${name}:${IMAGE_TAG}"
  if [[ ! -f "${context}/Dockerfile" ]]; then
    warn "${context#"${REPO_ROOT}"/}/Dockerfile não existe; imagem ${name} não foi construída"
    return 0
  fi
  log "Build ${image}"
  DOCKER_BUILDKIT=1 docker build -t "${image}" "${context}"
  log "Push ${image}"
  docker push "${image}" >/dev/null
  ok "${name}:${IMAGE_TAG} publicado no registry do k3d"
}

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  # backend/Dockerfile requires uv.lock (commit it after generating).
  if [[ -f "${REPO_ROOT}/backend/pyproject.toml" && ! -f "${REPO_ROOT}/backend/uv.lock" ]]; then
    warn "backend/uv.lock não existe; gerando com 'uv lock' (faça commit do arquivo)"
    (cd "${REPO_ROOT}/backend" && uv lock)
  fi
  build_and_push clear-helper-backend "${REPO_ROOT}/backend"
  build_and_push clear-helper-frontend "${REPO_ROOT}/frontend"
else
  warn "SKIP_BUILD=1: imagens não foram construídas"
fi

# ---------------------------------------------------------------------------
# 4. Secrets
# ---------------------------------------------------------------------------
"${SCRIPTS_DIR}/seal-dev-secrets.sh"

# ---------------------------------------------------------------------------
# 5. Root Application
# ---------------------------------------------------------------------------
REPO_URL="$(repo_url)"
if [[ "${SKIP_ROOT:-0}" == "1" ]]; then
  warn "SKIP_ROOT=1: root Application não aplicada"
elif [[ "${REPO_URL}" == *CHANGE-ME* ]]; then
  warn "A URL do repositório ainda é o placeholder (${REPO_URL})."
  warn "Troque spec.source.repoURL em infra/argocd/root.yaml, faça push e rode:"
  warn "  kubectl --context ${KUBE_CONTEXT} apply -n ${ARGOCD_NAMESPACE} -f infra/argocd/root.yaml"
else
  log "Aplicando root Application (${REPO_URL})"
  kubectl_ctx apply -n "${ARGOCD_NAMESPACE}" -f "${ROOT_APP}" >/dev/null
  ok "root Application aplicada; o Argo CD vai sincronizar operadores -> dados -> app"
fi

# Re-run the PreSync hooks (migrations/bootstrap) with the freshly pushed ":dev" image.
# Argo CD may have auto-synced a new commit before the build finished, running the
# migration Job with the previous image.
if kubectl_ctx -n "${ARGOCD_NAMESPACE}" get application clear-helper >/dev/null 2>&1; then
  kubectl_ctx -n "${ARGOCD_NAMESPACE}" patch application clear-helper --type merge \
    -p '{"operation":{"initiatedBy":{"username":"dev-up"},"sync":{"syncStrategy":{"hook":{}}}}}' >/dev/null
  ok "sync do clear-helper disparado (migrações com a imagem nova)"
fi

# Pick up freshly pushed ":dev" images (pullPolicy Always) when the app already exists.
for deploy in clear-helper-api clear-helper-worker clear-helper-frontend; do
  if kubectl_ctx -n "${APP_NAMESPACE}" get deployment "${deploy}" >/dev/null 2>&1; then
    kubectl_ctx -n "${APP_NAMESPACE}" rollout restart "deployment/${deploy}" >/dev/null
    ok "rollout restart ${deploy}"
  fi
done

cat <<EOF

Ambiente dev:
  App:      http://clear-helper.localhost
  API:      http://clear-helper.localhost/api/health/ready
  Argo CD:  kubectl --context ${KUBE_CONTEXT} -n ${ARGOCD_NAMESPACE} port-forward svc/argocd-server 8080:80
            -> http://localhost:8080  (usuário admin; senha:
            kubectl --context ${KUBE_CONTEXT} -n ${ARGOCD_NAMESPACE} get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo)
  Status:   kubectl --context ${KUBE_CONTEXT} -n ${ARGOCD_NAMESPACE} get applications

A primeira sincronização completa leva alguns minutos (download de imagens e charts).
EOF
