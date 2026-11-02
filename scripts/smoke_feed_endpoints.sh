#!/usr/bin/env bash
# Smoke test gzip feed artifacts. Run in Terminal.app:
#   bash scripts/smoke_feed_endpoints.sh
#   FULL=1 bash scripts/smoke_feed_endpoints.sh   # also count <job> (slow on large gzip)
set -euo pipefail
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

check() {
  local path="$1"
  local expect_min="${2:-0}"
  local out
  out="$(mktemp)"
  echo "======== /wrapping/${path} ========"
  curl -sS -D - -o "$out" --max-time 120 -w "time_total=%{time_total}s http=%{http_code} size=%{size_download}\n" \
    "https://lw.joinrs.com/wrapping/${path}" | head -20
  local magic
  magic="$(xxd -p -l 2 "$out" 2>/dev/null || true)"
  if [[ "$magic" == "1f8b" ]]; then
    echo "body=gzip bytes=$(wc -c <"$out" | tr -d ' ') (expect_jobs>=${expect_min})"
    if [[ "${FULL:-0}" == "1" ]]; then
      local jobs
      jobs="$(gzip -dc "$out" | grep -c '<job>' || true)"
      echo "jobs≈${jobs}"
    fi
  else
    echo "FAIL body not gzip magic=${magic}"
  fi
  rm -f "$out"
  echo
}

for platform in jooble talent adzuna; do
  check "${platform}" 1
  check "${platform}/it" 1
  check "${platform}/it5" 1
  check "${platform}/es" 1
  for s in 1 2 3 4 5; do
    check "${platform}/us/${s}" 1
  done
  check "${platform}/uk" 1
  check "${platform}/fr" 1
  check "${platform}/de" 1
  check "${platform}/eu" 1
  check "${platform}/americas" 1
  check "${platform}/asia" 1
  check "${platform}/row" 1
done
echo "DONE"
