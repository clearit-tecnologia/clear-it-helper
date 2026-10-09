#!/usr/bin/env bash
# Deletes the k3d dev cluster (and its registry). All cluster data is lost.
#   --purge  also removes the registry volume and the local sealed dev secrets
#   --yes    do not ask for confirmation
set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

PURGE=false
ASSUME_YES=false
for arg in "$@"; do
  case "${arg}" in
    --purge) PURGE=true ;;
    --yes|-y) ASSUME_YES=true ;;
    -h|--help)
      echo "Uso: $0 [--purge] [--yes]"
      exit 0
      ;;
    *) die "argumento desconhecido: ${arg}" ;;
  esac
done

require_cmd k3d

if ! cluster_exists; then
  warn "cluster ${CLUSTER_NAME} não existe"
else
  if [[ "${ASSUME_YES}" != true ]]; then
    read -r -p "Remover o cluster k3d '${CLUSTER_NAME}' e todos os dados dele? [s/N] " answer
    [[ "${answer}" =~ ^[sSyY]$ ]] || { echo "Cancelado."; exit 0; }
  fi
  log "Removendo cluster ${CLUSTER_NAME}"
  k3d cluster delete "${CLUSTER_NAME}"
  ok "cluster removido"
fi

# Registries created from the cluster config are normally removed with the cluster;
# make sure no leftover remains.
for registry in k3d-registry.localhost registry.localhost; do
  if k3d registry list 2>/dev/null | awk 'NR > 1 { print $1 }' | grep -x "${registry}" >/dev/null; then
    k3d registry delete "${registry}" >/dev/null && ok "registry ${registry} removido"
  fi
done

if [[ "${PURGE}" == true ]]; then
  if command -v docker >/dev/null 2>&1 && docker volume inspect clear-helper-registry >/dev/null 2>&1; then
    docker volume rm clear-helper-registry >/dev/null && ok "volume clear-helper-registry removido"
  fi
  # Sealed with the deleted cluster's key: useless now.
  rm -f "${DEV_SECRETS_DIR}"/*.sealed.yaml
  ok "secrets selados de dev removidos"
fi
