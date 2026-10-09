#!/usr/bin/env bash
# Shared helpers for the dev scripts. Source it; do not execute it.
# shellcheck shell=bash
# Variables below are consumed by the scripts that source this file.
# shellcheck disable=SC2034

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export REPO_ROOT

CLUSTER_NAME="${CLUSTER_NAME:-clear-helper}"
KUBE_CONTEXT="k3d-${CLUSTER_NAME}"
APP_NAMESPACE="clear-helper"
ARGOCD_NAMESPACE="argocd"
SEALED_SECRETS_NAMESPACE="kube-system"
SEALED_SECRETS_CONTROLLER="sealed-secrets-controller"

# Images are pushed from the host to the k3d registry and pulled in-cluster as
# k3d-registry.localhost:5000 (see infra/k3d/cluster.yaml).
REGISTRY_PUSH="${REGISTRY_PUSH:-localhost:5000}"
IMAGE_TAG="${IMAGE_TAG:-dev}"

# Argo CD chart (argo/argo-cd). Checked 2026-10-09.
ARGOCD_CHART_VERSION="${ARGOCD_CHART_VERSION:-10.10.1}"
ARGOCD_HELM_REPO="https://argoproj.github.io/argo-helm"

K3D_CONFIG="${REPO_ROOT}/infra/k3d/cluster.yaml"
ROOT_APP="${REPO_ROOT}/infra/argocd/root.yaml"
APPS_VALUES="${REPO_ROOT}/infra/argocd/apps/values.yaml"
DEV_SECRETS_DIR="${REPO_ROOT}/infra/secrets/dev"

if [[ -t 1 ]]; then
  _c_info=$'\033[1;34m'; _c_ok=$'\033[1;32m'; _c_warn=$'\033[1;33m'; _c_err=$'\033[1;31m'; _c_off=$'\033[0m'
else
  _c_info=""; _c_ok=""; _c_warn=""; _c_err=""; _c_off=""
fi

log()  { printf '%s==>%s %s\n' "${_c_info}" "${_c_off}" "$*"; }
ok()   { printf '%s[ok]%s %s\n' "${_c_ok}" "${_c_off}" "$*"; }
warn() { printf '%s[aviso]%s %s\n' "${_c_warn}" "${_c_off}" "$*" >&2; }
die()  { printf '%s[erro]%s %s\n' "${_c_err}" "${_c_off}" "$*" >&2; exit 1; }

require_cmd() {
  local cmd
  for cmd in "$@"; do
    command -v "${cmd}" >/dev/null 2>&1 || die "'${cmd}' não encontrado. Rode scripts/setup-dev.sh."
  done
}

# Repository URL: single source of truth is infra/argocd/root.yaml (spec.source.repoURL).
repo_url() {
  awk '/^[[:space:]]*repoURL:[[:space:]]/ { print $2; exit }' "${ROOT_APP}"
}

# Pinned chart version of a component in infra/argocd/apps/values.yaml.
component_version() {
  local component="$1"
  awk -v c="  ${component}:" '
    $0 == c { found = 1; next }
    found && /^  [^ ]/ { exit }
    found && /^[[:space:]]+version:/ { print $2; exit }
  ' "${APPS_VALUES}"
}

kubectl_ctx() { kubectl --context "${KUBE_CONTEXT}" "$@"; }
helm_ctx()    { helm --kube-context "${KUBE_CONTEXT}" "$@"; }

cluster_exists() {
  k3d cluster get "${CLUSTER_NAME}" >/dev/null 2>&1
}

# Random lowercase hex string with N bytes of entropy (2N characters).
rand_hex() {
  local bytes="$1"
  head -c "${bytes}" /dev/urandom | od -An -tx1 -v | tr -d ' \n'
}
