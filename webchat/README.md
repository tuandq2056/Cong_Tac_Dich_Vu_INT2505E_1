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

## Implementation Status & Team Collaboration

- **Hạ tầng CI/CD chung ([`.github/workflows/webchat-checks.yml`](../.github/workflows/webchat-checks.yml))**: Hoàn tất 100% tự động hóa kiểm tra: Gitleaks, Trivy, Load Smoke (200 req/20 workers), Kiểm tra kiến trúc ADR 0001, Sinh unit test tự động, Lint ruff, Redocly, AsyncAPI và Schemathesis/Newman API contract test.
- **Microservice Identity ([`services/identity`](services/identity/)) - Production Ready**: Hoàn thiện thực tế kết nối PostgreSQL, mã hóa mật khẩu PBKDF2-HMAC-SHA256 (100k vòng, salt), cấp phát JWT token (aud=webchat) và kiểm tra service token nội bộ (aud=identity-internal), 34/34 unit test PASS.
- **Microservices Social & Chat ([`services/social`](services/social/), [`services/chat`](services/chat/)) - Baseline Mocks**: Đang hoạt động ở chế độ mock/baseline tuân thủ nghiêm ngặt hợp đồng OpenAPI 3.1 & AsyncAPI 3.0 để toàn bộ luồng CI/CD và Gateway chạy thông suốt.
- **Hướng dẫn cho thành viên phát triển module mới**:
  1. Khi bắt đầu phát triển Social hoặc Chat thật, chỉ cần vào thư mục `services/social` hoặc `services/chat`.
  2. Giữ nguyên wire schema trong `app/api/schemas.py` và các hợp đồng endpoint đã định nghĩa.
  3. Thay thế/mở rộng logic nghiệp vụ và repository tương ứng với database của module.
  4. Chạy `make verify` và `make test-api` tại local để đảm bảo module mới thay thế mock không làm hỏng hợp đồng chung.

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
