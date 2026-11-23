# One image definition for the three services; the compose file passes SERVICE.
# Build context is the repository root:
#   docker build -f services/Dockerfile --build-arg SERVICE=identity .
FROM python:3.12-slim

# Remediate known base image vulnerabilities (e.g. zlib1g CVE-2026-85091)
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

ARG SERVICE=identity
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY services/${SERVICE}/pyproject.toml ./
COPY services/${SERVICE}/app ./app

RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 webchat

USER webchat

EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
