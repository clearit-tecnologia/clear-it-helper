#!/usr/bin/env bash
# Generates random dev secrets, seals them with the cluster's Sealed Secrets key and
# applies the SealedSecrets to the k3d cluster.
#
# - Idempotent: a Secret that already exists in the cluster is kept (rotating the
#   bootstrap password or the Garage keys after the first boot would break login/S3).
#   Use --force to regenerate everything (then recreate the cluster data, or the admin
#   password will not match the user already created by the bootstrap).
# - Sealed files are written to infra/secrets/dev/ (gitignored: they are only valid for
#   this local cluster's key).
# - Plain values never touch the repository nor the command line (temp dir, mode 700).
set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

FORCE=false
for arg in "$@"; do
  case "${arg}" in
    --force) FORCE=true ;;
    -h|--help)
      echo "Uso: $0 [--force]"
      exit 0
      ;;
    *) die "argumento desconhecido: ${arg}" ;;
  esac
done

require_cmd kubectl kubeseal

kubectl_ctx get namespace >/dev/null 2>&1 \
  || die "contexto ${KUBE_CONTEXT} indisponível. Rode scripts/dev-up.sh primeiro."

log "Aguardando o controller do Sealed Secrets"
kubectl_ctx -n "${SEALED_SECRETS_NAMESPACE}" rollout status \
  "deployment/${SEALED_SECRETS_CONTROLLER}" --timeout=180s >/dev/null

kubectl_ctx create namespace "${APP_NAMESPACE}" --dry-run=client -o yaml | kubectl_ctx apply -f - >/dev/null

mkdir -p "${DEV_SECRETS_DIR}"
WORK_DIR="$(mktemp -d)"
chmod 700 "${WORK_DIR}"
trap 'rm -rf "${WORK_DIR}"' EXIT

# seal_secret <name> <key=value>...
seal_secret() {
  local name="$1"
  shift
  if [[ "${FORCE}" != true ]] && kubectl_ctx -n "${APP_NAMESPACE}" get secret "${name}" >/dev/null 2>&1; then
    ok "${name}: já existe no cluster (mantido; use --force para regenerar)"
    return 0
  fi

  local secret_dir="${WORK_DIR}/${name}" kv key value
  local -a from_file=()
  mkdir -p "${secret_dir}"
  for kv in "$@"; do
    key="${kv%%=*}"
    value="${kv#*=}"
    printf '%s' "${value}" > "${secret_dir}/${key}"
    from_file+=("--from-file=${key}=${secret_dir}/${key}")
  done

  kubectl create secret generic "${name}" \
    --namespace "${APP_NAMESPACE}" "${from_file[@]}" \
    --dry-run=client -o yaml \
    | kubeseal --context "${KUBE_CONTEXT}" \
        --controller-namespace "${SEALED_SECRETS_NAMESPACE}" \
        --controller-name "${SEALED_SECRETS_CONTROLLER}" \
        --format yaml \
    > "${DEV_SECRETS_DIR}/${name}.sealed.yaml"

  kubectl_ctx apply -f "${DEV_SECRETS_DIR}/${name}.sealed.yaml" >/dev/null
  ok "${name}: gerado, selado e aplicado (${DEV_SECRETS_DIR#"${REPO_ROOT}"/}/${name}.sealed.yaml)"
}

log "Gerando e selando secrets de dev no namespace ${APP_NAMESPACE}"

# Backend: JWT (>= 32 chars) and bootstrap admin password.
seal_secret clear-helper-app \
  "jwt-secret=$(rand_hex 32)" \
  "bootstrap-admin-password=$(rand_hex 12)"

# Garage: rpc_secret must be 32 bytes hex; access keys follow Garage's format
# (GK + 24 hex chars / 64 hex chars) because they are imported by the bootstrap Job.
seal_secret clear-helper-garage \
  "rpc-secret=$(rand_hex 32)" \
  "admin-token=$(rand_hex 32)" \
  "access-key-id=GK$(rand_hex 12)" \
  "secret-access-key=$(rand_hex 32)" \
  "langfuse-access-key-id=GK$(rand_hex 12)" \
  "langfuse-secret-access-key=$(rand_hex 32)"

# LiteLLM master key (must start with "sk-"); also used by the backend (CH_LITELLM_API_KEY).
seal_secret litellm-masterkey \
  "masterkey=sk-$(rand_hex 24)"

# Langfuse (only consumed when langfuse.enabled=true, generated anyway so it can be
# toggled on without re-running this script).
seal_secret langfuse-secrets \
  "salt=$(rand_hex 32)" \
  "encryption-key=$(rand_hex 32)" \
  "nextauth-secret=$(rand_hex 32)" \
  "clickhouse-password=$(rand_hex 24)" \
  "public-key=pk-lf-$(rand_hex 16)" \
  "secret-key=sk-lf-$(rand_hex 16)" \
  "admin-email=admin@clearit.com.br" \
  "admin-password=$(rand_hex 12)"

log "Aguardando o controller decifrar os secrets"
for name in clear-helper-app clear-helper-garage litellm-masterkey langfuse-secrets; do
  for _ in $(seq 1 30); do
    kubectl_ctx -n "${APP_NAMESPACE}" get secret "${name}" >/dev/null 2>&1 && break
    sleep 2
  done
  kubectl_ctx -n "${APP_NAMESPACE}" get secret "${name}" >/dev/null 2>&1 \
    || die "Secret ${name} não foi criado pelo controller (veja: kubectl -n kube-system logs deploy/${SEALED_SECRETS_CONTROLLER})"
done
ok "Secrets disponíveis em ${APP_NAMESPACE}"

cat <<EOF

Credenciais do admin inicial (login na UI):
  e-mail: admin@clearit.com.br   (infra/values/dev/clear-helper.yaml -> config.bootstrap.adminEmail)
  senha:  kubectl --context ${KUBE_CONTEXT} -n ${APP_NAMESPACE} get secret clear-helper-app \\
            -o jsonpath='{.data.bootstrap-admin-password}' | base64 -d; echo
EOF
