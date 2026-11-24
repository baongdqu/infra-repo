#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_DIR="${HOME}/.sealed-secrets-backup"
KEY_FILE="${BACKUP_DIR}/master-key.yaml"
ENV_FILE="${SCRIPT_DIR}/.env.secrets"

usage() {
  echo "Usage: $0 {backup-key|restore-key|seal}"
  exit 1
}

backup_key() {
  mkdir -p "${BACKUP_DIR}"
  echo "[+] Sao luu Sealed Secrets master key ra ${KEY_FILE} ..."
  kubectl get secret -n sealed-secrets -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml > "${KEY_FILE}"
  chmod 600 "${KEY_FILE}"
  echo "[OK] Da sao luu master key (giu ngoai Git)."
}

restore_key() {
  if [[ ! -f "${KEY_FILE}" ]]; then
    echo "[ERROR] Khong tim thay ${KEY_FILE}. Hay chay backup-key truoc khi destroy cluster!"
    exit 1
  fi
  echo "[+] Khoi phuc master key TRUOC KHI apply argocd/root-app.yaml ..."
  kubectl create namespace sealed-secrets --dry-run=client -o yaml | kubectl apply -f -
  kubectl apply -f "${KEY_FILE}"
  if kubectl get deployment sealed-secrets -n sealed-secrets >/dev/null 2>&1; then
    kubectl rollout restart deployment/sealed-secrets -n sealed-secrets
    kubectl rollout status deployment/sealed-secrets -n sealed-secrets --timeout=90s
  fi
  echo "[OK] Master key da san sang trong namespace sealed-secrets."
}

seal_all() {
  command -v kubeseal >/dev/null 2>&1 || { echo "[ERROR] Chua cai kubeseal CLI."; exit 1; }
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[ERROR] Khong tim thay ${ENV_FILE}. Hay copy tu .env.secrets.example."
    exit 1
  fi
  # shellcheck disable=SC1090
  source "${ENV_FILE}"

  seal_env "dev" "${DEV_POSTGRES_USER}" "${DEV_POSTGRES_PASSWORD}" "${DEV_POSTGRES_DB}" "${REPO_ROOT}/k8s/overlays/dev/sealed-secret.yaml"
  seal_env "production" "${PROD_POSTGRES_USER}" "${PROD_POSTGRES_PASSWORD}" "${PROD_POSTGRES_DB}" "${REPO_ROOT}/k8s/overlays/production/sealed-secret.yaml"
  echo "[OK] Hoan tat! Nho bo comment '- sealed-secret.yaml' trong kustomization.yaml cua dev va production."
}

seal_env() {
  local ns="$1" user="$2" pass="$3" db="$4" out="$5"
  local url="postgresql://${user}:${pass}@postgres:5432/${db}"
  echo "[+] Ma hoa app-secrets cho namespace '${ns}' -> ${out} ..."
  kubectl create secret generic app-secrets \
    --namespace "${ns}" \
    --from-literal=POSTGRES_USER="${user}" \
    --from-literal=POSTGRES_PASSWORD="${pass}" \
    --from-literal=POSTGRES_DB="${db}" \
    --from-literal=DATABASE_URL="${url}" \
    --dry-run=client -o yaml | \
  kubeseal --controller-name=sealed-secrets --controller-namespace=sealed-secrets --format yaml > "${out}"
}

case "${ACTION}" in
  backup-key)  backup_key ;;
  restore-key) restore_key ;;
  seal)        seal_all ;;
  *)           usage ;;
esac
