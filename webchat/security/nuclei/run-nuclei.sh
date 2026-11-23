#!/usr/bin/env bash
# run-nuclei.sh - Nuclei DAST Security Scanner Runner for WebChat SOA
# Usage: ./security/nuclei/run-nuclei.sh [TARGET_URL] [WS_TARGET_URL]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# 1. Target URL & Protocol Configuration (HTTP & WebSocket)
TARGET_URL="${1:-${TARGET_URL:-http://localhost:8080}}"
WS_TARGET_URL="${2:-${WS_TARGET_URL:-}}"

# If WS_TARGET_URL is not explicitly specified, derive it from TARGET_URL
if [ -z "${WS_TARGET_URL}" ]; then
  if [[ "${TARGET_URL}" =~ ^http:// ]]; then
    WS_TARGET_URL="ws://${TARGET_URL#http://}"
  elif [[ "${TARGET_URL}" =~ ^https:// ]]; then
    WS_TARGET_URL="wss://${TARGET_URL#https://}"
  elif [[ "${TARGET_URL}" =~ ^ws:// ]]; then
    WS_TARGET_URL="${TARGET_URL}"
    TARGET_URL="http://${TARGET_URL#ws://}"
  elif [[ "${TARGET_URL}" =~ ^wss:// ]]; then
    WS_TARGET_URL="${TARGET_URL}"
    TARGET_URL="https://${TARGET_URL#wss://}"
  else
    WS_TARGET_URL="ws://${TARGET_URL}"
    TARGET_URL="http://${TARGET_URL}"
  fi
fi

TEMPLATES_DIR="${TEMPLATES_DIR:-${SCRIPT_DIR}}"
FAIL_ON_SEVERITY="${FAIL_ON_SEVERITY:-critical,high}"
STRICT_HEALTH="${STRICT_HEALTH:-0}"

# Create temporary report files in host /tmp for Docker volume compatibility
REPORT_JSON="$(mktemp /tmp/nuclei-report-XXXXXX.jsonl)"
REPORT_TXT="$(mktemp /tmp/nuclei-report-XXXXXX.txt)"
REPORT_JSON_HTTP="$(mktemp /tmp/nuclei-http-XXXXXX.jsonl)"
REPORT_TXT_HTTP="$(mktemp /tmp/nuclei-http-XXXXXX.txt)"
REPORT_JSON_WS="$(mktemp /tmp/nuclei-ws-XXXXXX.jsonl)"
REPORT_TXT_WS="$(mktemp /tmp/nuclei-ws-XXXXXX.txt)"

cleanup() {
  rm -f "${REPORT_JSON}" "${REPORT_TXT}" \
        "${REPORT_JSON_HTTP}" "${REPORT_TXT_HTTP}" \
        "${REPORT_JSON_WS}" "${REPORT_TXT_WS}"
}
trap cleanup EXIT

echo "=========================================================="
echo "  WebChat SOA: Nuclei DAST Security Scanner"
echo "=========================================================="
echo "HTTP Target URL:  ${TARGET_URL}"
echo "WS Target URL:    ${WS_TARGET_URL}"
echo "Templates Dir:    ${TEMPLATES_DIR}"
echo "Fail Threshold:   ${FAIL_ON_SEVERITY}"
echo "----------------------------------------------------------"

# Step 1: Health pre-check
echo "[1/4] Probing gateway health at ${TARGET_URL}/healthz..."
if ! curl -fsS -m 5 "${TARGET_URL}/healthz" >/dev/null 2>&1; then
  echo "[-] WARNING: Target ${TARGET_URL} is not responding at /healthz."
  echo "    Ensure docker compose stack is running ('make up' or 'docker compose up -d')."
  if [ "${STRICT_HEALTH}" = "1" ]; then
    echo "[-] ERROR: STRICT_HEALTH is enabled and gateway health check failed. Aborting." >&2
    exit 1
  fi
  echo "    Proceeding with scan anyway..."
else
  echo "[+] Gateway health check passed."
fi

# Step 2: Determine execution engine (local binary vs docker) & configure volume mapping
echo "[2/4] Detecting Nuclei execution engine and volume mapping..."
NUCLEI_CMD=()
CONTAINER_TEMPLATES_DIR=""

if command -v nuclei >/dev/null 2>&1; then
  NUCLEI_CMD=(nuclei)
  CONTAINER_TEMPLATES_DIR="${TEMPLATES_DIR}"
  echo "[+] Using local Nuclei binary: $(nuclei -version 2>&1 | head -n 1)"
elif command -v docker >/dev/null 2>&1; then
  if [ -d "${TEMPLATES_DIR}" ]; then
    DOCKER_VOLUMES=(-v "${TEMPLATES_DIR}:/templates:ro" -v /tmp:/tmp)
    CONTAINER_TEMPLATES_DIR="/templates"
  else
    TEMPLATE_BASENAME="$(basename "${TEMPLATES_DIR}")"
    DOCKER_VOLUMES=(-v "${TEMPLATES_DIR}:/templates/${TEMPLATE_BASENAME}:ro" -v /tmp:/tmp)
    CONTAINER_TEMPLATES_DIR="/templates/${TEMPLATE_BASENAME}"
  fi
  NUCLEI_CMD=(docker run --rm --network host "${DOCKER_VOLUMES[@]}" projectdiscovery/nuclei:v3.11.1)
  echo "[+] Using Dockerized Nuclei image: projectdiscovery/nuclei:v3.11.1"
  echo "    Mounted templates: ${TEMPLATES_DIR} -> ${CONTAINER_TEMPLATES_DIR}"
  echo "    Mounted reports:   /tmp -> /tmp"
else
  echo "[-] ERROR: Neither local 'nuclei' nor 'docker' is available." >&2
  exit 1
fi

# Detect template types present
HAS_HTTP_TEMPLATES=0
HAS_WS_TEMPLATES=0

if [ -f "${TEMPLATES_DIR}" ]; then
  if grep -q -E "^[[:space:]]*http:" "${TEMPLATES_DIR}" 2>/dev/null; then HAS_HTTP_TEMPLATES=1; fi
  if grep -q -E "^[[:space:]]*websocket:" "${TEMPLATES_DIR}" 2>/dev/null; then HAS_WS_TEMPLATES=1; fi
elif [ -d "${TEMPLATES_DIR}" ]; then
  if grep -rq -E "^[[:space:]]*http:" "${TEMPLATES_DIR}" 2>/dev/null; then HAS_HTTP_TEMPLATES=1; fi
  if grep -rq -E "^[[:space:]]*websocket:" "${TEMPLATES_DIR}" 2>/dev/null; then HAS_WS_TEMPLATES=1; fi
fi

if [ "${HAS_HTTP_TEMPLATES}" -eq 0 ] && [ "${HAS_WS_TEMPLATES}" -eq 0 ]; then
  echo "[-] ERROR: No HTTP or WebSocket templates found in ${TEMPLATES_DIR}." >&2
  exit 1
fi

# Step 3: Execute Nuclei scan across protocols and track SCAN_STATUS
echo "[3/4] Running Nuclei DAST scan..."
SCAN_STATUS=0

if [ "${HAS_HTTP_TEMPLATES}" -eq 1 ]; then
  echo "  - Running HTTP templates against ${TARGET_URL}..."
  set +e
  "${NUCLEI_CMD[@]}" \
    -u "${TARGET_URL}" \
    -type http \
    -t "${CONTAINER_TEMPLATES_DIR}" \
    -silent \
    -no-color \
    -jsonl-export "${REPORT_JSON_HTTP}" \
    -output "${REPORT_TXT_HTTP}"
  HTTP_STATUS=$?
  set -e
  if [ "${HTTP_STATUS}" -ne 0 ]; then
    echo "[-] ERROR: Nuclei HTTP scan exited with fatal status ${HTTP_STATUS}." >&2
    SCAN_STATUS="${HTTP_STATUS}"
  fi
fi

if [ "${HAS_WS_TEMPLATES}" -eq 1 ]; then
  echo "  - Running WebSocket templates against ${WS_TARGET_URL}..."
  set +e
  "${NUCLEI_CMD[@]}" \
    -u "${WS_TARGET_URL}" \
    -type websocket \
    -t "${CONTAINER_TEMPLATES_DIR}" \
    -silent \
    -no-color \
    -jsonl-export "${REPORT_JSON_WS}" \
    -output "${REPORT_TXT_WS}"
  WS_STATUS=$?
  set -e
  if [ "${WS_STATUS}" -ne 0 ]; then
    echo "[-] ERROR: Nuclei WebSocket scan exited with fatal status ${WS_STATUS}." >&2
    SCAN_STATUS="${WS_STATUS}"
  fi
fi

# Abort immediately if engine experienced a crash or fatal execution error
if [ "${SCAN_STATUS}" -ne 0 ]; then
  echo "[-] ERROR: Nuclei scanner engine failed (fatal exit status ${SCAN_STATUS}). Aborting." >&2
  exit "${SCAN_STATUS}"
fi

# Consolidate reports across protocols
if [ -s "${REPORT_JSON_HTTP}" ]; then cat "${REPORT_JSON_HTTP}" >> "${REPORT_JSON}"; fi
if [ -s "${REPORT_JSON_WS}" ]; then cat "${REPORT_JSON_WS}" >> "${REPORT_JSON}"; fi
if [ -s "${REPORT_TXT_HTTP}" ]; then cat "${REPORT_TXT_HTTP}" >> "${REPORT_TXT}"; fi
if [ -s "${REPORT_TXT_WS}" ]; then cat "${REPORT_TXT_WS}" >> "${REPORT_TXT}"; fi

# Step 4: Analyze results and handle exit codes
echo "[4/4] Analyzing scan results..."
TOTAL_FINDINGS=0
CRITICAL_COUNT=0
HIGH_COUNT=0
MEDIUM_COUNT=0
LOW_COUNT=0
INFO_COUNT=0

if [ -s "${REPORT_JSON}" ]; then
  TOTAL_FINDINGS=$(wc -l < "${REPORT_JSON}" | tr -d " ")
  CRITICAL_COUNT=$(grep -c '"severity":"critical"' "${REPORT_JSON}" || true)
  HIGH_COUNT=$(grep -c '"severity":"high"' "${REPORT_JSON}" || true)
  MEDIUM_COUNT=$(grep -c '"severity":"medium"' "${REPORT_JSON}" || true)
  LOW_COUNT=$(grep -c '"severity":"low"' "${REPORT_JSON}" || true)
  INFO_COUNT=$(grep -c '"severity":"info"' "${REPORT_JSON}" || true)
fi

echo "----------------------------------------------------------"
echo "  DAST Scan Summary:"
echo "    Total findings:    ${TOTAL_FINDINGS}"
echo "    - CRITICAL:        ${CRITICAL_COUNT}"
echo "    - HIGH:            ${HIGH_COUNT}"
echo "    - MEDIUM:          ${MEDIUM_COUNT}"
echo "    - LOW:             ${LOW_COUNT}"
echo "    - INFO:            ${INFO_COUNT}"
echo "----------------------------------------------------------"

if [ "${TOTAL_FINDINGS}" -gt 0 ]; then
  echo "Findings Details:"
  cat "${REPORT_TXT}"
  echo "----------------------------------------------------------"
fi

# Evaluate failure condition with robust whitespace trimming and full severity branches
SHOULD_FAIL=0
IFS=',' read -ra SEVS <<< "${FAIL_ON_SEVERITY}"
for sev in "${SEVS[@]}"; do
  sev_clean="$(echo "${sev}" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
  case "${sev_clean}" in
    critical)
      if [ "${CRITICAL_COUNT}" -gt 0 ]; then SHOULD_FAIL=1; fi
      ;;
    high)
      if [ "${HIGH_COUNT}" -gt 0 ]; then SHOULD_FAIL=1; fi
      ;;
    medium)
      if [ "${MEDIUM_COUNT}" -gt 0 ]; then SHOULD_FAIL=1; fi
      ;;
    low)
      if [ "${LOW_COUNT}" -gt 0 ]; then SHOULD_FAIL=1; fi
      ;;
    info)
      if [ "${INFO_COUNT}" -gt 0 ]; then SHOULD_FAIL=1; fi
      ;;
    "")
      # Ignore empty tokens from trailing or doubled commas
      ;;
    *)
      echo "[-] WARNING: Unknown severity threshold '${sev_clean}' ignored." >&2
      ;;
  esac
done

if [ "${SHOULD_FAIL}" -eq 1 ]; then
  echo "[-] DAST FAILURE: Vulnerabilities found exceeding threshold (${FAIL_ON_SEVERITY})." >&2
  exit 1
fi

echo "[+] DAST SUCCESS: No blocking vulnerabilities detected."
exit 0
