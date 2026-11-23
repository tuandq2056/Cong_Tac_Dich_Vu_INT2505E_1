#!/usr/bin/env bash
# CI smoke: start the stack, run concurrent requests until every service answers reliably, then stop.
# Replace the target with the realtime/history/search profiles once those harnesses exist.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
COMPOSE=(docker compose -f docker-compose.yml)
PYTHON=${PYTHON:-python3}

cleanup() {
  if [ "${KEEP_STACK:-0}" != "1" ]; then
    "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

"${COMPOSE[@]}" up -d --build
for _ in $(seq 1 90); do
  if curl -fsS http://localhost:8080/healthz >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -fsS http://localhost:8080/healthz >/dev/null || {
  echo "gateway did not become healthy" >&2
  "${COMPOSE[@]}" ps >&2
  exit 1
}

"$PYTHON" loadtest/smoke.py --url http://localhost:8080/healthz --requests 200 --workers 20

echo "Load smoke passed: 200 requests, 20 workers, zero failures."
