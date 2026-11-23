# 0003: Two JWT audiences — browser tokens and service tokens

- Status: accepted
- Date: 2026-11-21
- Deciders: team

## Context

Identity issues the browser token. Social and Chat must verify it without calling Identity on every
request. Chat must also call Social's internal endpoint, and Social must call Identity's internal
endpoint, without impersonating a user.

The spec fixes the browser token claims: `aud=webchat`, `sub` = user UUID, `username`, `exp`.

## Decision

- **Browser token:** JWT signed by Identity, `aud=webchat`, `sub` = user UUID, `username`, `exp`,
  `iss=webchat-identity`. Every service verifies signature, `iss`, `aud` and `exp` before use.
- **Service token:** separate signing key and `aud` per callee (`identity-internal`,
  `social-internal`), `sub` = caller service name (`social`, `chat`). The callee checks that `sub` is
  allowed to call that endpoint. A browser token presented to an internal endpoint is rejected with
  `401`; a valid service token for the wrong audience is rejected too.
- Algorithm HS256 for v1, keys from environment, never in the repository. The verification code is
  written so a switch to RS256/JWKS changes configuration, not call sites.
- Passwords: Argon2id. Username lookup is case-insensitive through a normalized column with a unique
  constraint, not through `LOWER()` at query time only.
- Google login is behind `GOOGLE_ENABLED`; when false both endpoints return `501 GOOGLE_DISABLED`.

## Consequences

- A leaked browser key does not mint service tokens, and vice versa.
- Key rotation requires a short overlap window (accept old and new `kid`). v1 ships one key; the code
  reads `kid` so rotation does not need a schema change.
- Every service needs the verification key. That is acceptable for three services; a real deployment
  would use JWKS.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Opaque tokens + introspection | Correct, but adds a network hop and a new failure mode to every request. |
| One shared secret and audience | A browser token could be replayed to an internal endpoint. |
