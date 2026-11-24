# 0005: Idempotency by a stored key, not by hope

- Status: accepted
- Date: 2026-11-21
- Deciders: team

## Context

The client retries after a timeout without knowing whether the first attempt committed. Three
operations must survive that: sending a message (WebSocket), creating a group (`Idempotency-Key`), and
accepting a friend request (two decisions race). A duplicate message or a duplicate group is a
user-visible bug; `client_message_id` alone is not enough if the payload can change.

## Decision

- **Message:** `UNIQUE (sender_id, client_message_id)` on `message`. On conflict,
  compare the conversation and message content:
  - same conversation and content → return the stored message with `replayed=true`;
  - different conversation or content → `CLIENT_MESSAGE_ID_CONFLICT`, no new message.
- **Group creation:** require `Idempotency-Key` (UUID). Table `idempotency_key` keyed by
  `(user_id, key)` stores `request_hash`, `response_status`, `response_body`, `created_at`, expires
  after 24 hours. Same key + same hash → replay the stored response (`200`). Same key + different hash
  → `409 IDEMPOTENCY_CONFLICT`. The row is inserted in the same transaction as the group and its
  members.
- **Friend request decision:** `UPDATE friend_request SET status = :new WHERE id = :id AND status =
  'pending'` decides the winner. The loser reads the row: same decision by the right actor → `200`,
  different decision → `409 REQUEST_CLOSED`.
- **Direct conversation:** canonical pair `(user_low, user_high)` with a unique constraint, so A→B and
  B→A create one row even under concurrency. The loser reads and returns it with `200`.

## Consequences

- Every retryable write names its key and its conflict behaviour in the contract.
- Stored responses contain ids only the service can produce; never store secrets in that table.
- A cleanup job deletes idempotency rows older than 24 hours; the table is not a permanent audit log.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Client-generated UUID as primary key only | A changed payload under the same key silently wins. |
| No key, dedupe by content | Two legitimate identical messages would collapse into one. |
