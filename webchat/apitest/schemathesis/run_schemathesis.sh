#!/usr/bin/env bash
# ==============================================================================
# WebChat Schemathesis Contract Fuzzing Runner
# 
# Executes property-based contract testing against contracts/openapi.yaml
# using a multi-pass fuzzing strategy:
#   - Pass 1: Unauthenticated public fuzzing against Gateway (port 8080)
#   - Pass 2: Authenticated user fuzzing against Gateway (Bearer token, aud=webchat)
#   - Pass 3: Service-level fuzzing against internal endpoints (Identity & Social)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/../../contracts/openapi.yaml" ]; then
  REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
elif [ -f "$SCRIPT_DIR/contracts/openapi.yaml" ]; then
  REPO_ROOT="$SCRIPT_DIR"
else
  REPO_ROOT="$(pwd)"
fi

cd "$REPO_ROOT"

# Configuration parameters with sensible defaults
OPENAPI_SPEC="${OPENAPI_SPEC:-contracts/openapi.yaml}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8080}"
IDENTITY_URL="${IDENTITY_URL:-http://localhost:8001}"
SOCIAL_URL="${SOCIAL_URL:-http://localhost:8002}"
CHAT_URL="${CHAT_URL:-http://localhost:8003}"

WEBCHAT_JWT_SECRET="${WEBCHAT_JWT_SECRET:-dev-only-change-me}"
SERVICE_JWT_SECRET="${SERVICE_JWT_SECRET:-dev-only-service-secret}"

WORKERS="${WORKERS:-2}"
MAX_RESPONSE_TIME="${MAX_RESPONSE_TIME:-3000}"
MAX_EXAMPLES="${MAX_EXAMPLES:-50}"
SUPPRESS_HEALTH_CHECK="${SUPPRESS_HEALTH_CHECK:-too_slow}"
PASS="${PASS:-all}" # options: 1, 2, 3, 3a, 3b, all

# Verify schema exists
if [ ! -f "$OPENAPI_SPEC" ]; then
  echo "ERROR: OpenAPI specification not found at: $OPENAPI_SPEC" >&2
  exit 1
fi

# Locate Schemathesis binary
if command -v schemathesis >/dev/null 2>&1; then
  SCHEMATHESIS=(schemathesis)
elif [ -x "$REPO_ROOT/.venv/bin/schemathesis" ]; then
  SCHEMATHESIS=("$REPO_ROOT/.venv/bin/schemathesis")
elif python3 -m schemathesis --version >/dev/null 2>&1; then
  SCHEMATHESIS=(python3 -m schemathesis)
else
  echo "ERROR: Schemathesis is not installed or not in PATH." >&2
  echo "Please install dependencies via: pip install schemathesis>=3.35 pyjwt>=2.8" >&2
  echo "Or run: make install-dev" >&2
  exit 1
fi

# Locate or inline token generator
TOKEN_GEN=""
if [ -f "$SCRIPT_DIR/generate_token.py" ]; then
  TOKEN_GEN="$SCRIPT_DIR/generate_token.py"
elif [ -f "$REPO_ROOT/apitest/schemathesis/generate_token.py" ]; then
  TOKEN_GEN="$REPO_ROOT/apitest/schemathesis/generate_token.py"
fi

get_token() {
  local token_type="$1"
  local secret="$2"
  if [ -n "$TOKEN_GEN" ]; then
    python3 "$TOKEN_GEN" --type "$token_type" --secret "$secret"
  else
    python3 -c "
import base64, hashlib, hmac, json, time
def b64url(d): return base64.urlsafe_b64encode(d).rstrip(b'=').decode('ascii')
now = int(time.time())
claims = {'iat': now, 'exp': now + 86400}
if '$token_type' == 'user':
    claims.update({'sub': '11111111-1111-4111-8111-111111111111', 'username': 'fuzz_user', 'aud': 'webchat', 'iss': 'webchat-identity'})
elif '$token_type' == 'identity-service':
    claims.update({'sub': 'social', 'aud': 'identity-internal', 'iss': 'webchat-social'})
elif '$token_type' == 'social-service':
    claims.update({'sub': 'chat', 'aud': 'social-internal', 'iss': 'webchat-chat'})
hdr = b64url(json.dumps({'alg': 'HS256', 'typ': 'JWT'}, separators=(',', ':')).encode('utf-8'))
pld = b64url(json.dumps(claims, separators=(',', ':')).encode('utf-8'))
sig = b64url(hmac.new('$secret'.encode('utf-8'), f'{hdr}.{pld}'.encode('ascii'), hashlib.sha256).digest())
print(f'{hdr}.{pld}.{sig}')
"
  fi
}

USER_TOKEN=$(get_token "user" "$WEBCHAT_JWT_SECRET")
IDENTITY_SERVICE_TOKEN=$(get_token "identity-service" "$SERVICE_JWT_SECRET")
SOCIAL_SERVICE_TOKEN=$(get_token "social-service" "$SERVICE_JWT_SECRET")

# Dynamically detect Schemathesis major version
SCHEMATHESIS_VER=$("${SCHEMATHESIS[@]}" --version 2>&1 | grep -oE '[0-9]+' | head -n 1 || echo "4")

if [ "$SCHEMATHESIS_VER" -ge 4 ]; then
  URL_FLAG="--url"
  SUPPRESS_HEALTH_FLAG="--suppress-health-check"
  MAX_EXAMPLES_FLAG="--max-examples"
  # Convert MAX_RESPONSE_TIME from ms to seconds for 4.x (e.g. 3000ms -> 3)
  if [ "$MAX_RESPONSE_TIME" -gt 100 ]; then
    RESPONSE_TIME_VAL="$(( MAX_RESPONSE_TIME / 1000 ))"
    if [ "$RESPONSE_TIME_VAL" -le 0 ]; then RESPONSE_TIME_VAL=3; fi
  else
    RESPONSE_TIME_VAL="$MAX_RESPONSE_TIME"
  fi
  DEADLINE_STR="${RESPONSE_TIME_VAL}s"
else
  URL_FLAG="--base-url"
  SUPPRESS_HEALTH_FLAG="--hypothesis-suppress-health-check"
  MAX_EXAMPLES_FLAG="--hypothesis-max-examples"
  RESPONSE_TIME_VAL="$MAX_RESPONSE_TIME"
  DEADLINE_STR="${RESPONSE_TIME_VAL}ms"
fi

# Base options conforming to requirements
CHECKS="not_a_server_error,status_code_conformance,content_type_conformance,response_schema_conformance"

COMMON_ARGS=(
  --checks "$CHECKS"
  "$SUPPRESS_HEALTH_FLAG=$SUPPRESS_HEALTH_CHECK"
  --max-response-time="$RESPONSE_TIME_VAL"
  "$MAX_EXAMPLES_FLAG=$MAX_EXAMPLES"
  --workers="$WORKERS"
)

echo "================================================================================"
echo " Starting Schemathesis Multi-Pass Contract Fuzzing"
echo " Spec:              $OPENAPI_SPEC"
echo " Gateway URL:       $GATEWAY_URL"
echo " Identity URL:      $IDENTITY_URL"
echo " Social URL:        $SOCIAL_URL"
echo " Checks:            $CHECKS"
echo " Workers:           $WORKERS | Max Examples: $MAX_EXAMPLES | Deadline: $DEADLINE_STR"
echo "================================================================================"

# Pass 1: Unauthenticated public fuzzing against Gateway
if [ "$PASS" = "all" ] || [ "$PASS" = "1" ]; then
  echo ""
  echo ">>> [Pass 1/3] Unauthenticated public fuzzing against Gateway ($GATEWAY_URL)"
  echo "    Targets: /api/v1/ (public auth endpoints & unauthenticated checks on protected routes)"
  "${SCHEMATHESIS[@]}" run "$OPENAPI_SPEC" \
    "$URL_FLAG=$GATEWAY_URL" \
    --exclude-path-regex="^/internal/" \
    "${COMMON_ARGS[@]}" \
    ${SCHEMATHESIS_EXTRA_ARGS:-}
  echo ">>> [Pass 1/3] OK"
fi

# Pass 2: Authenticated user fuzzing against Gateway
if [ "$PASS" = "all" ] || [ "$PASS" = "2" ]; then
  echo ""
  echo ">>> [Pass 2/3] Authenticated user fuzzing against Gateway ($GATEWAY_URL)"
  echo "    Targets: /api/v1/ with Bearer token (aud=webchat)"
  "${SCHEMATHESIS[@]}" run "$OPENAPI_SPEC" \
    "$URL_FLAG=$GATEWAY_URL" \
    --exclude-path-regex="^/internal/" \
    --header="Authorization: Bearer $USER_TOKEN" \
    "${COMMON_ARGS[@]}" \
    ${SCHEMATHESIS_EXTRA_ARGS:-}
  echo ">>> [Pass 2/3] OK"
fi

# Pass 3: Service-level fuzzing against internal endpoints
if [ "$PASS" = "all" ] || [ "$PASS" = "3" ] || [ "$PASS" = "3a" ]; then
  echo ""
  echo ">>> [Pass 3a/3] Identity internal endpoint fuzzing ($IDENTITY_URL)"
  echo "    Targets: /internal/v1/users/{user_id} with Service token (aud=identity-internal, sub=social)"
  "${SCHEMATHESIS[@]}" run "$OPENAPI_SPEC" \
    "$URL_FLAG=$IDENTITY_URL" \
    --include-path-regex="^/internal/v1/users/" \
    --header="Authorization: Bearer $IDENTITY_SERVICE_TOKEN" \
    "${COMMON_ARGS[@]}" \
    ${SCHEMATHESIS_EXTRA_ARGS:-}
  echo ">>> [Pass 3a/3] OK"
fi

if [ "$PASS" = "all" ] || [ "$PASS" = "3" ] || [ "$PASS" = "3b" ]; then
  echo ""
  echo ">>> [Pass 3b/3] Social internal endpoint fuzzing ($SOCIAL_URL)"
  echo "    Targets: /internal/v1/conversations/{id}/members/{user_id}/permissions with Service token (aud=social-internal, sub=chat)"
  "${SCHEMATHESIS[@]}" run "$OPENAPI_SPEC" \
    "$URL_FLAG=$SOCIAL_URL" \
    --include-path-regex="^/internal/v1/conversations/" \
    --header="Authorization: Bearer $SOCIAL_SERVICE_TOKEN" \
    "${COMMON_ARGS[@]}" \
    ${SCHEMATHESIS_EXTRA_ARGS:-}
  echo ">>> [Pass 3b/3] OK"
fi

echo ""
echo "================================================================================"
echo " === ALL SCHEMATHESIS CONTRACT FUZZING PASSES PASSED SUCCESSFULLY ==="
echo "================================================================================"
