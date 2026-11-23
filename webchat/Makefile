# One entry point for every check. Uses .venv when it exists, so `cd services/x && ...` still works.
VENV_PY := $(shell test -x $(CURDIR)/.venv/bin/python && echo $(CURDIR)/.venv/bin/python || (test -x $(CURDIR)/../.venv/bin/python && echo $(CURDIR)/../.venv/bin/python || echo python3))
PYTHON ?= $(VENV_PY)
NPM ?= npm

.PHONY: verify verify-backend verify-web contracts install-dev up down \
	security security-secrets security-vuln security-dast \
	test-contract test-api test test-arch generate-tests test-unit

verify: test-arch verify-backend verify-web contracts

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

verify-backend:
	@found=0; \
	for dir in services/*/; do \
		if [ -f "$${dir}pyproject.toml" ]; then \
			found=1; echo "== $${dir}"; \
			(cd "$${dir}" && $(PYTHON) -m pytest -q) || exit 1; \
		fi; \
	done; \
	if [ "$$found" = 0 ]; then \
		echo "No backend yet: add services/*/pyproject.toml (see services/README.md)." >&2; exit 1; \
	fi

verify-web:
	@if [ -f web/package.json ]; then \
		cd web && $(NPM) ci --no-audit --no-fund && $(NPM) run lint && $(NPM) test -- --run && $(NPM) run build; \
	else \
		echo "No web client yet: add web/package.json (see web/README.md)." >&2; exit 1; \
	fi

contracts:
	@python3 contracts/check_shared.py
	@if [ -f contracts/openapi.yaml ]; then \
		npx --yes @redocly/cli@latest lint contracts/openapi.yaml; \
	else echo "No contracts/openapi.yaml yet: see contracts/README.md." >&2; fi
	@if [ -f contracts/asyncapi.yaml ]; then \
		npx --yes @asyncapi/cli@latest validate contracts/asyncapi.yaml; \
	else echo "No contracts/asyncapi.yaml yet: see contracts/README.md." >&2; fi

security-secrets:
	@if command -v gitleaks >/dev/null 2>&1; then \
		gitleaks detect --redact --verbose; \
	else \
		docker run --rm --user "$$(id -u):$$(id -g)" -v "$$(pwd)":/repo zricethezav/gitleaks:v8.30.0 git /repo --config=/repo/.gitleaks.toml --redact --no-banner; \
	fi

security-vuln:
	@if command -v trivy >/dev/null 2>&1; then \
		trivy fs --quiet --scanners vuln,misconfig,secret --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1 .; \
	else \
		docker run --rm -v "$$(pwd)":/src -w /src aquasec/trivy:0.69.3 fs --quiet --scanners vuln,misconfig,secret --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1 /src; \
	fi

security-dast:
	@chmod +x ./security/nuclei/run-nuclei.sh
	@./security/nuclei/run-nuclei.sh $(TARGET_URL) $(WS_TARGET_URL)

security: security-secrets security-vuln

up:
	docker compose up -d --build

down:
	docker compose down -v

test-contract:
	@chmod +x apitest/schemathesis/run_schemathesis.sh
	@WORKERS="$(WORKERS)" MAX_EXAMPLES="$(MAX_EXAMPLES)" ./apitest/schemathesis/run_schemathesis.sh

test-api:
	@chmod +x apitest/run.sh
	@./apitest/run.sh

test-arch:
	@$(PYTHON) scripts/check_domain_rules.py

generate-tests:
	@$(PYTHON) tools/testgen/cli.py

test-unit: generate-tests verify-backend

test: verify test-api

