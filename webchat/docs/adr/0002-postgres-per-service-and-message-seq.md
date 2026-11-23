# 0002: One PostgreSQL schema per service; `seq` allocated inside the insert transaction

- Status: accepted
- Date: 2026-11-21
- Deciders: team

## Context

The contract requires a per-conversation `seq` that increases in commit order, is dense enough to
paginate with open bounds (`before_seq`, `after_seq`, `through_seq`), and never repeats. It also
requires that a message is visible in history exactly when it was ACKed, and that concurrent sends to
the same conversation produce one order.

The three services have separate ownership. Cross-service joins are forbidden.

## Decision

- PostgreSQL 16 in development and tests; the same major version in CI.
- One logical database per service (`identity`, `social`, `chat`) in one cluster locally. Social owns
  memberships; Chat owns messages, attachments and read-state.
- Chat allocates `seq` with a single statement inside the message transaction:

  ```sql
  UPDATE conversation_counter
     SET last_seq = last_seq + 1
   WHERE conversation_id = :id
  RETURNING last_seq;
  ```

  The unique constraint `UNIQUE (conversation_id, seq)` is the last line of defence. The counter row is
  the single writer per conversation; a missing row is created with `INSERT … ON CONFLICT DO NOTHING`
  before the update.

- Message insert, counter update, attachment binding and the outbox row for broadcast commit in one
  transaction. The ACK and `message.created` are emitted only after commit.
- Migrations are Alembic, one history per service. A published revision is never edited.

## Consequences

- Pagination is stable and gap-free per conversation, at the cost of serialising sends within one
  conversation. That is the intended bottleneck; different conversations do not block each other.
- A conversation with a hot counter can become a lock hotspot. Measure it before choosing a more
  complex allocator; the spec's target is 20 messages/second across 20 groups.
- Read-state and summaries never allocate `seq` and never touch the counter.

## Alternatives considered

| Alternative | Why not |
|---|---|
| `BIGSERIAL` global sequence | Gaps and cross-conversation ordering; pagination by `seq` becomes sparse. |
| Timestamp ordering | Ties and clock skew; cannot guarantee a total order. |
| Client-assigned sequence | Collision and trust problems. |
