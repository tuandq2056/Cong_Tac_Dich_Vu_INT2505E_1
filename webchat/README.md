# WebChat

Chat service for the SOA course: accounts, friendships, direct and group conversations, real-time
messages over WebSocket, attachments and audio, read-state, on-demand unread summaries, and browser
text-to-speech.

Backend: FastAPI + PostgreSQL. Frontend: React + TypeScript. Three services, one contract.

## Services

| Service | Owns | Public surface |
|---|---|---|
| Identity | accounts, usernames, password and Google login, tokens | `/api/v1/auth`, `/api/v1/users` |
| Social | friend requests, friendships, conversations, members, permissions | `/api/v1/friend-requests`, `/friends`, `/conversations`, internal permissions |
| Chat | messages, `seq`, attachments, read-state, summaries, WebSocket | `/api/v1/conversations/{id}/...`, `/ws/v1/chat` |
| Web | the screens that drive the flows | browser |

`/internal/v1` is service-to-service only. The browser never calls it.

## Layout

| Path | What lives there |
|---|---|
| `docs/spec/webchat-api-spec.md` | The API specification, converted from the source DOCX. |
| `contracts/` | `openapi.yaml` (REST) and `asyncapi.yaml` (WebSocket), derived from the spec and under review. |
| `docs/adr/` | Architecture decisions. Decisions, not suggestions. |
| `docs/phase2/problem-register.md` | Every known problem and the milestone plan. |
| `docs/agents/` | Issue workflow, labels, benchmark protocol. |
| `services/` | The three FastAPI applications. |
| `web/` | React + TypeScript client. |
| `apitest/` | Black-box REST and WebSocket tests against the running stack. |
| `loadtest/` | Dataset, profiles and the CI smoke test. |

## Before you write code

Read `docs/phase2/problem-register.md` for the current milestone, the ADRs in `docs/adr/`, and the
spec. If the prose and a contract file disagree, the contract wins for the wire format and the prose
wins for behaviour; open an issue instead of guessing.

## Commands

```bash
make verify        # backend tests + web lint/test/build + contract lint
make up            # docker compose up
make down          # stop and remove the stack
```

`make verify` fails with an instruction while a component does not exist yet. A green run always means
something actually ran.

## Working on a change

1. Pick an issue from the register; it has an ID (`IDN1`, `SOC3`, `CHT7`, …).
2. One issue, one branch: `feat/<issue>-<slug>` from an up-to-date `main`.
3. Failing test first, then the smallest change that passes it.
4. Open a PR with `Closes #<issue>` and the verification output. A person merges it.

See [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md) and
[docs/agents/triage-labels.md](docs/agents/triage-labels.md).

## Non-negotiables

- A successful `message.ack` means the message is committed.
- `seq` is per conversation, allocated in the insert transaction, and never reused.
- `UNIQUE (conversation_id, seq)` and `UNIQUE (conversation_id, sender_id, client_message_id)` stay.
- A browser token is never accepted on `/internal/v1`; a service token is never accepted on `/api/v1`.
- Errors use `ErrorResponse` with `request_id` and a stable `error.code`.
- Pagination is cursor-based; an empty page is `200`, not `404`.
