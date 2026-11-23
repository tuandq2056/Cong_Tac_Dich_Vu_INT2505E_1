# Contracts

The wire contract is the source of truth for every service and the web client.

| File | Spec | Direction |
|---|---|---|
| `openapi.yaml` | OpenAPI 3.1.1 | REST `/api/v1` and `/internal/v1` |
| `asyncapi.yaml` | AsyncAPI 3.0.0 | WebSocket `/ws/v1/chat`, from the Chat service's point of view |

> **Derived, under review.** The source document (`docs/spec/webchat-api-spec.md`) defers every path,
> parameter, request body and response body to these two files, but neither file was present next to
> the DOCX. Both files here were derived from the prose and pass their linters plus
> `check_shared.py`. They still need a line-by-line review against the DOCX by the service owners;
> open an issue for every difference rather than editing a contract silently.

## Rules

- `snake_case` field names, UUID identifiers, RFC 3339 UTC timestamps.
- Errors always use `ErrorResponse`: `request_id` plus `error { code, message, fields?, related_id? }`.
- `Message` and `TextContent` are one schema shared by REST and WebSocket. Do not fork them.
- Two internal endpoints (`/internal/v1/...`) are service-to-service only; they are not part of the
  browser contract.
- A change to a published contract needs an ADR, a version note and a contract test that fails first.

## Checks

```bash
npx @redocly/cli lint contracts/openapi.yaml
npx @asyncapi/cli validate contracts/asyncapi.yaml
```

Both are wired into the `api` job of `.github/workflows/phase2-checks.yml`.
