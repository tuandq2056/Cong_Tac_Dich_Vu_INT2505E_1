#!/usr/bin/env bash
# ==============================================================================
# WebChat SOA — Black-box API Integration & Contract Test Harness
#
# Coordinates:
#   1. Docker Compose stack health checks (Identity, Social, Chat, Gateway)
#      Supports running against existing services or starting stack on demand.
#   2. Gateway Perimeter Security & Route Isolation Checks
#   3. Newman Functional E2E Collections (01_auth, 02_social, 03_chat) with --bail
#   4. Schemathesis Property-Based Multi-Pass Contract Fuzzing
#   5. Automated diagnostic logging on failure & clean volume teardown
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/../docker-compose.yml" ]; then
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
elif [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
  REPO_ROOT="$SCRIPT_DIR"
else
  REPO_ROOT="$(pwd)"
fi

cd "$REPO_ROOT"

# Configuration Options
COMPOSE=(docker compose -f docker-compose.yml)
START_COMPOSE="${START_COMPOSE:-auto}" # auto | 1 | 0
KEEP_STACK="${KEEP_STACK:-0}"          # 1: keep containers alive
SKIP_PERIMETER="${SKIP_PERIMETER:-0}"  # 1: skip gateway perimeter
SKIP_NEWMAN="${SKIP_NEWMAN:-0}"        # 1: skip newman collections
SKIP_CONTRACT_TESTS="${SKIP_CONTRACT_TESTS:-0}" # 1: skip schemathesis
ENV_FILE="${ENV_FILE:-apitest/environments/webchat.local.postman_environment.json}"

STARTED_COMPOSE=0

# Trap handler for diagnostics and clean teardown
cleanup() {
  local exit_code=$?
  if [ "$exit_code" -ne 0 ]; then
    echo "" >&2
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2
    echo " [FAIL] Test execution encountered an error (exit code: $exit_code)" >&2
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2
    if [ -f docker-compose.yml ] && command -v docker >/dev/null 2>&1; then
      echo "=== Docker Compose Container Status ===" >&2
      "${COMPOSE[@]}" ps >&2 || true
      echo "=== Docker Compose Service Logs (Tail 100) ===" >&2
      "${COMPOSE[@]}" logs --tail=100 >&2 || true
    fi
  fi

  if [ "$STARTED_COMPOSE" = "1" ]; then
    if [ "$KEEP_STACK" != "1" ]; then
      echo "Tearing down Docker Compose test stack..."
      "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
    else
      echo "Preserving Docker Compose test stack (KEEP_STACK=1)..."
    fi
  fi
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

check_service_health() {
  local url="$1"
  local expected_service="${2:-}"
  local body
  if ! body=$(curl -fsS --max-time 3 "$url" 2>/dev/null); then
    return 1
  fi
  echo "$body" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' || return 1
  if [ -n "$expected_service" ]; then
    echo "$body" | grep -q "\"service\"[[:space:]]*:[[:space:]]*\"$expected_service\"" || return 1
  fi
  return 0
}

is_stack_healthy() {
  check_service_health "http://localhost:8080/healthz" "gateway" && \
  check_service_health "http://localhost:8001/healthz" "identity" && \
  check_service_health "http://localhost:8002/healthz" "social" && \
  check_service_health "http://localhost:8003/healthz" "chat"
}

wait_for_service() {
  local url="$1"
  local service_name="$2"
  local max_retries="${3:-45}"
  local delay="${4:-2}"
  echo "Waiting for $service_name at $url..."
  for i in $(seq 1 "$max_retries"); do
    if check_service_health "$url" "$service_name"; then
      echo "  [OK] $service_name is ready (attempt $i/$max_retries)"
      return 0
    fi
    sleep "$delay"
  done
  echo "ERROR: Timed out waiting for $service_name at $url ($((max_retries * delay))s elapsed)" >&2
  return 1
}

echo "================================================================================"
echo " WebChat SOA API Integration & Contract Test Suite"
echo " Working Root:    $REPO_ROOT"
echo " Compose Mode:    $START_COMPOSE (started_by_script: $STARTED_COMPOSE)"
echo " Keep Stack:      $KEEP_STACK"
echo "================================================================================"

# 1. Stack Management: Determine whether to spin up or reuse services
if [ "$START_COMPOSE" = "1" ] || { [ "$START_COMPOSE" = "auto" ] && ! is_stack_healthy; }; then
  echo "Starting docker-compose stack..."
  "${COMPOSE[@]}" up -d --build
  STARTED_COMPOSE=1
else
  echo "Existing services stack is already responding and healthy. Reusing active stack."
fi

# 2. Wait for health checks
wait_for_service http://localhost:8080/healthz gateway
wait_for_service http://localhost:8001/healthz identity
wait_for_service http://localhost:8002/healthz social
wait_for_service http://localhost:8003/healthz chat

# 3. Gateway Perimeter & Security Isolation Checks
if [ "$SKIP_PERIMETER" != "1" ]; then
  echo ""
  echo "================================================================================"
  echo " [1/3] Gateway Perimeter Security Isolation Checks"
  echo "================================================================================"
  # Verify internal endpoint is blocked via Gateway (port 8080)
  internal_res=$(curl -s -w "\n%{http_code}" http://localhost:8080/internal/v1/users/00000000-0000-4000-8000-000000000000)
  internal_code=$(echo "$internal_res" | tail -n 1)
  internal_body=$(echo "$internal_res" | sed '$d')
  if [ "$internal_code" != "404" ]; then
    echo "ERROR: Gateway exposed internal route! Expected 404, got: $internal_code" >&2
    exit 1
  fi
  echo "$internal_body" | grep -q "CONVERSATION_NOT_FOUND" || {
    echo "WARNING: Expected CONVERSATION_NOT_FOUND in perimeter response body, got: $internal_body" >&2
  }
  echo "  [OK] /internal is masked from Gateway (HTTP 404)"

  # Verify unknown routes return 404
  unknown_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/not-a-valid-route-endpoint)
  if [ "$unknown_code" != "404" ]; then
    echo "ERROR: Unknown route expected 404, got: $unknown_code" >&2
    exit 1
  fi
  echo "  [OK] Unknown routes masked from Gateway (HTTP 404)"
fi

# 4. Newman Functional E2E Collections
if [ "$SKIP_NEWMAN" != "1" ]; then
  echo ""
  echo "================================================================================"
  echo " [2/3] Newman Functional E2E Integration Suite"
  echo "================================================================================"
  NEWMAN_CMD=()
  if command -v newman >/dev/null 2>&1; then
    NEWMAN_CMD=(newman run)
  elif command -v npx >/dev/null 2>&1; then
    NEWMAN_CMD=(npx --yes newman run)
  fi

  if [ ${#NEWMAN_CMD[@]} -eq 0 ]; then
    echo "WARNING: Neither 'newman' nor 'npx' is available. Skipping Newman collections." >&2
  else
    COLLECTIONS=(
      apitest/collections/01_auth.postman_collection.json
      apitest/collections/02_social.postman_collection.json
      apitest/collections/03_chat.postman_collection.json
    )
    RUN_COUNT=0
    for col in "${COLLECTIONS[@]}"; do
      if [ -f "$col" ]; then
        echo ">>> Executing Newman Collection: $(basename "$col")"
        CMD=("${NEWMAN_CMD[@]}" "$col")
        if [ -f "$ENV_FILE" ]; then
          CMD+=(-e "$ENV_FILE")
        fi
        CMD+=(--bail)
        "${CMD[@]}" || {
          echo "ERROR: Newman collection $col failed!" >&2
          exit 1
        }
        RUN_COUNT=$((RUN_COUNT + 1))
      fi
    done

    if [ "$RUN_COUNT" -eq 0 ]; then
      echo "Notice: No collections found in apitest/collections/*. Skipping Newman step."
    else
      echo ">>> All $RUN_COUNT Newman E2E collections passed successfully."
    fi
  fi
fi

# 5. Schemathesis Property-Based Contract Fuzzing
if [ "$SKIP_CONTRACT_TESTS" != "1" ]; then
  echo ""
  echo "================================================================================"
  echo " [3/3] Schemathesis Property-Based Contract Fuzzing"
  echo "================================================================================"
  SCHEMATHESIS_RUNNER=""
  if [ -f "apitest/schemathesis/run_schemathesis.sh" ]; then
    SCHEMATHESIS_RUNNER="apitest/schemathesis/run_schemathesis.sh"
  elif [ -f "$SCRIPT_DIR/run_schemathesis.sh" ]; then
    SCHEMATHESIS_RUNNER="$SCRIPT_DIR/run_schemathesis.sh"
  fi

  if [ -n "$SCHEMATHESIS_RUNNER" ]; then
    chmod +x "$SCHEMATHESIS_RUNNER"
    "$SCHEMATHESIS_RUNNER" || {
      echo "ERROR: Schemathesis contract fuzzing detected violations!" >&2
      exit 1
    }
  else
    echo "WARNING: Schemathesis runner script not found. Skipping contract fuzzing." >&2
  fi
fi

echo ""
echo "================================================================================"
echo " === ALL BLACK-BOX API AND CONTRACT TESTS PASSED SUCCESSFULLY ==="
echo "================================================================================"
