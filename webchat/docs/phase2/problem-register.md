# Problem register

Every known problem, ordered by priority. Each row becomes one GitHub issue (see
`docs/agents/issue-tracker.md`). IDs are stable: `<AREA><n>`. The issue title starts with the ID so
saved searches and branch names can match on it.

Source of truth for behaviour: `docs/spec/webchat-api-spec.md`. Wire contract: `contracts/`.

## Severity

| Level | Meaning | Response |
|---|---|---|
| `S0` | Data loss, security hole, or the service cannot start | Stop and fix now |
| `S1` | A user-visible rule is wrong, or the contract is broken | Next change |
| `S2` | Performance, reliability or developer experience | Planned |
| `S3` | Cosmetic or nice to have | Backlog |

## Milestones

| Milestone | Goal | Exit criterion |
|---|---|---|
| M0 Foundation | repo, contracts, compose, CI | `make verify` runs; five CI jobs exist |
| M1 Identity | register, login, me, lookup | flow step 1 passes over HTTP |
| M2 Social | friends, conversations, permissions | flow steps 2–4 pass over HTTP |
| M3 Chat REST | history, search, attachments, read-state | steps 6–7 pass over HTTP |
| M4 Chat realtime | WebSocket, ACK, broadcast, reconnect | two browsers exchange a message |
| M5 Web | the screens that drive M1–M4 | E2E happy path in a browser |
| M6 Extras | summary, Google, TTS | acceptance cases in the spec |
| M7 Load | dataset and the three load profiles | p95 targets recorded in the ledger |

## Register

| ID | Sev | Area | Problem | Evidence | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| `FOUND1` | `S1` | infra | `openapi.yaml` and `asyncapi.yaml` were not supplied; the spec defers every path and body to them | spec, "Hai tệp kỹ thuật đi kèm" | both files exist under `contracts/`, lint clean, shared schemas checked, reviewed by the service owners | in-review |
| `FOUND2` | `S1` | infra | No runnable stack: three services, databases and web client | — | `docker compose up` serves `/api/v1` and `/ws/v1/chat`; health checks pass | open |
| `FOUND3` | `S1` | infra | Five CI jobs must gate every push | `.github/workflows/phase2-checks.yml` | verify, secrets, vulnerabilities, api and load-smoke are required checks | open |
| `IDN1` | `S1` | identity | Register, login, `users/me`, `by-username` are not implemented | spec, "Identity · tài khoản" | the four endpoints match the contract; wrong credentials share one 401 code | open |
| `IDN2` | `S1` | identity | Username case-folding race can create two accounts | spec, "Ví dụ tra cứu" | concurrent `Binh`/`binh` yields one account and one 409 | open |
| `IDN3` | `S3` | identity | Google OAuth is optional but must return 501 when disabled | spec, "Identity · đăng nhập Google" | both endpoints return 501 when off; state reuse returns 400 when on | open |
| `SOC1` | `S1` | social | Friend requests: create, list, decide, with one pending per pair | spec, "Social · bạn bè và lời mời" | duplicate and reverse requests return the documented 200/409; two decisions race to one transition | open |
| `SOC2` | `S2` | social | Friends list and unfriend keep history | spec, "Social · bạn bè và lời mời" | unfriend is idempotent 204; direct history still readable; new sends blocked | open |
| `SOC3` | `S1` | social | Direct conversation must be unique regardless of request order | spec, "Social · hội thoại" | concurrent A→B and B→A return one id; non-friends get 403 | open |
| `SOC4` | `S1` | social | Group creation is atomic and idempotent | spec, "Social · hội thoại" | 3–50 members, all-or-nothing, `Idempotency-Key` replay 200, changed payload 409 | open |
| `SOC5` | `S2` | social | Conversation list, detail and members paginate by cursor | spec, "Social · hội thoại" | no duplicate or skipped id between pages; outsider and missing id both 404 | open |
| `SOC6` | `S1` | social | Chat needs `can_read`/`can_send` from Social | spec, "Kiểm tra quyền giữa các dịch vụ" | internal endpoint verifies service audience; outsider 404; Social down maps to 503 | open |
| `CHT1` | `S2` | chat | Attachment upload and download with pending TTL | spec, "Chat · tệp đính kèm" | kind/size/MIME enforced; pending file readable only by uploader; 24 h expiry | open |
| `CHT2` | `S1` | chat | History pagination with `before_seq`/`after_seq`/`through_seq` | spec, "Chat · lịch sử" | newest page desc, backfill asc, no repeated id, `has_more` correct | open |
| `CHT3` | `S2` | chat | Substring search with NFC and diacritics | spec, "Chat · lịch sử" | `BÁO CÁO` matches, `bao cao` does not, scoped to one conversation | open |
| `CHT4` | `S1` | chat | Read-state must be monotonic under concurrent tabs | spec, "Chat · mốc đọc" | 45 then 40 ends at 45; ahead of latest returns 422 | open |
| `CHT5` | `S2` | chat | Unread summary must use a fixed snapshot and text only | spec, "Chat · mốc đọc và tóm tắt" | 104 eligible → 100 sent, `omitted_count=4`; audio/file-only never calls the LLM | open |
| `CHT6` | `S1` | chat | WebSocket session, subscribe and snapshot handshake | spec, "WebSocket · phiên và sự kiện" | auth within 5 s, close 4408/4401, `latest_seq` returned after registration | open |
| `CHT7` | `S0` | chat | `message.send`: commit → ACK → broadcast, with replay | spec, "WebSocket · gửi và xác nhận" | no ACK before commit; same `client_message_id` replays one message; crash loses none | open |
| `WEB1` | `S2` | web | Login, friend list and conversation list screens | spec, "Từ kết bạn đến đọc lại tin" | steps 1–4 usable without dev tools | open |
| `WEB2` | `S1` | web | Reconnect merges buffer and backfill by `message.id` | spec, "Mất kết nối" | after a forced disconnect the timeline has no duplicate and no gap | open |
| `WEB3` | `S2` | web | Audio/file playback and client-side TTS | spec, "Text-to-Speech" | new text is spoken once; replay and own messages are not; leaving stops audio | open |
| `TST1` | `S1` | test | Contract tests against both YAML files | spec, "Kiểm thử và nghiệm thu" | every request/response and frame validated; 401/403/404/409/422/503 covered | open |
| `TST2` | `S1` | test | Integration and E2E cases | spec, "Kiểm thử và nghiệm thu" | two-browser flow, outsider denial, unfriend behaviour, summary boundaries | open |
| `TST3` | `S2` | test | Load profiles and dataset | spec, "Giới hạn và hiệu năng" | 100 conversations × 10 000 messages; three profiles; p95 recorded in the ledger | open |
| `INF1` | `S2` | infra | Every response and log line carries `request_id` | spec, "Quy ước tích hợp" | error body and server log can be joined by `request_id` | open |

## Adding a row

- Copy the evidence, do not paraphrase it. A spec section, a failing test or a log excerpt is better
  than "it is slow".
- Acceptance criteria are checkboxes a reviewer can verify without reading the diff.
- If the problem contradicts an ADR, add the ADR reference and say whether it must be amended.
- Move the status to `fixed` only when the PR that closes the issue is merged.
