#!/usr/bin/env python3
"""AST linter to enforce Hexagonal Architecture Domain purity (ADR 0001, CLAUDE.md Rule 2).

Rule 2: Framework-free core.
Business rules live in a domain/ module that imports only the standard library
and itself — no FastAPI, Pydantic, SQLAlchemy, HTTP types or cross-service code.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Disallowed third-party frameworks and cross-service packages
FORBIDDEN_PACKAGES = {
    "fastapi",
    "pydantic",
    "pydantic_settings",
    "sqlalchemy",
    "alembic",
    "httpx",
    "requests",
    "starlette",
    "jwt",
    "uvicorn",
}

DISALLOWED_SERVICE_CROSS_IMPORTS = {
    "identity": {"social", "chat"},
    "social": {"identity", "chat"},
    "chat": {"identity", "social"},
}


def check_file(file_path: Path, service_name: str) -> list[str]:
    violations: list[str] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, OSError) as exc:
        return [f"{file_path}: Failed to parse AST: {exc}"]

    cross_services = DISALLOWED_SERVICE_CROSS_IMPORTS.get(service_name, set())

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_pkg = alias.name.split(".")[0]
                if top_pkg in FORBIDDEN_PACKAGES:
                    violations.append(
                        f"{file_path}:{node.lineno}: Domain layer must not import '{top_pkg}'"
                    )
                if top_pkg in cross_services:
                    violations.append(
                        f"{file_path}:{node.lineno}: Cross-service import of '{top_pkg}' is forbidden"
                    )
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_pkg = node.module.split(".")[0]
            if top_pkg in FORBIDDEN_PACKAGES:
                violations.append(
                    f"{file_path}:{node.lineno}: Domain layer must not import from '{top_pkg}'"
                )
            if top_pkg in cross_services:
                violations.append(
                    f"{file_path}:{node.lineno}: Cross-service import from '{top_pkg}' is forbidden"
                )
            # Check absolute app imports (e.g., from app.api or app.adapters)
            if top_pkg == "app":
                sub_pkg = node.module.split(".")[1] if len(node.module.split(".")) > 1 else ""
                if sub_pkg in {"api", "adapters"}:
                    violations.append(
                        f"{file_path}:{node.lineno}: Domain layer must not import from outer layer 'app.{sub_pkg}'"
                    )

    return violations


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    services_dir = repo_root / "services"

    if not services_dir.exists():
        print(f"Error: Services directory not found at {services_dir}", file=sys.stderr)
        return 1

    all_violations: list[str] = []
    checked_files = 0

    for service in ("identity", "social", "chat"):
        domain_dir = services_dir / service / "app" / "domain"
        if not domain_dir.exists():
            continue

        for py_file in domain_dir.glob("*.py"):
            checked_files += 1
            violations = check_file(py_file, service)
            all_violations.extend(violations)

    print(f"Checked {checked_files} domain files across services for ADR 0001 compliance.")

    if all_violations:
        print("\nDomain architecture violations found:", file=sys.stderr)
        for v in all_violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print("SUCCESS: All domain layers are strictly framework-free and decoupled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
