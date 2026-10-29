#!/usr/bin/env bash
# Trigger a one-shot job-feed pipeline Job from the CronJob (runs in-cluster → RDS).
# Usage:
#   ./scripts/trigger_job_feed_k8s.sh [namespace]
# Env:
#   NAMESPACE (default: lw)
#   DEADLINE_SECONDS (default: 86400)
set -euo pipefail

NAMESPACE="${1:-${NAMESPACE:-lw}}"
DEADLINE_SECONDS="${DEADLINE_SECONDS:-86400}"
CRONJOB="linkedin-jooble-job-feed-pipeline"
JOB_NAME="job-feed-manual-$(date +%Y%m%d-%H%M%S)"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl non trovato. Installa kubectl e configura il contesto EKS (namespace ${NAMESPACE})." >&2
  exit 1
fi

echo "Patching CronJob ${CRONJOB} activeDeadlineSeconds=${DEADLINE_SECONDS} (ns=${NAMESPACE})…"
kubectl patch cronjob "${CRONJOB}" -n "${NAMESPACE}" --type=merge \
  -p "{\"spec\":{\"jobTemplate\":{\"spec\":{\"activeDeadlineSeconds\":${DEADLINE_SECONDS}}}}}"

echo "Creating Job ${JOB_NAME} from CronJob…"
kubectl create job --from="cronjob/${CRONJOB}" "${JOB_NAME}" -n "${NAMESPACE}"

echo
echo "Watch status:"
echo "  kubectl get job ${JOB_NAME} -n ${NAMESPACE} -w"
echo "  kubectl logs -f job/${JOB_NAME} -n ${NAMESPACE}"
echo
echo "Row counts (from laptop, needs VPN/.env):"
echo "  python scripts/watch_job_feed_progress.py"
echo
kubectl get job "${JOB_NAME}" -n "${NAMESPACE}"
kubectl get pods -n "${NAMESPACE}" -l "job-name=${JOB_NAME}" -o wide 2>/dev/null || \
  kubectl get pods -n "${NAMESPACE}" | grep "${JOB_NAME}" || true
