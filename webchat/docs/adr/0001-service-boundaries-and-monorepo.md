# 0001: Three services in one monorepo, talking only through contracts

- Status: accepted
- Date: 2026-11-21
- Deciders: team

## Context

The spec splits the backend into Identity, Social and Chat, each with a named owner. The services have
different data (accounts, relationships, messages) and different failure modes. The team is small and
ships from one repository, but the exercise is about service boundaries, not about one deployable.

## Decision

One repository with three independently runnable FastAPI applications and one React client:

```
services/identity/   services/social/   services/chat/   web/
```

- Each service owns its data and exposes only its published REST/WebSocket contract.
- Services never import each other's Python code and never read each other's tables. Cross-service
  reads go through `/internal/v1` with a service token.
- `contracts/openapi.yaml` and `contracts/asyncapi.yaml` are the only shared artefacts.
- A local `docker compose` starts all three services, their databases and the web client. Production
  packaging is out of scope for v1.

## Consequences

- One CI run can verify the whole system; one PR can change a contract and its consumers together.
- A shared library would be convenient, but it would quietly recreate a monolith. Only generated
  contract types may be shared.
- Any cross-service feature must name the internal endpoint it depends on and what it does when that
  endpoint is down (the spec answers this with `503 SOCIAL_UNAVAILABLE`).

## Alternatives considered

| Alternative | Why not |
|---|---|
| One FastAPI app with three modules | Cheaper, but it cannot demonstrate the permission call or the failure isolation the spec requires. |
| Three repositories | Correct for independent teams, too heavy for one course team and one CI pipeline. |
