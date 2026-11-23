# 0004: Commit, then ACK and broadcast; reconnect reconciles by `seq`

- Status: accepted
- Date: 2026-11-21
- Deciders: team

## Context

A browser can lose its connection at any moment. The contract requires: no successful ACK before the
message is durable, no duplicate message in the UI, and a gap-free history after reconnect. The socket
also carries delivery to every member, including the sender's other tabs.

## Decision

- One JSON object per text frame, maximum 32 KiB. The first frame must be `session.authenticate` within
  5 seconds; otherwise close with `4408`. Close with `4401` when the token is no longer valid.
- **Write path:** authenticate → check `can_send` through Social → in one transaction allocate `seq`,
  insert the message, bind the attachment and insert an outbox row → commit → send `message.ack` to the
  sender and `message.created` to every subscribed socket of the conversation, including the sender.
- **Durability:** the outbox row is written in the same transaction as the message. A dispatcher reads
  committed rows and fans out. Delivery is at-least-once; the client deduplicates by `message.id`. A
  crash after commit and before fan-out loses no message: the outbox row is still there.
- **Subscribe:** register the socket first, then read `latest_seq`, then send
  `conversation.subscribed`. The client buffers `message.created` from the moment it sends
  `conversation.subscribe`, fetches `after_seq=<synced>&through_seq=<latest_seq>`, then merges buffered
  and fetched frames by `message.id` and sorts by `seq`.
- **Replay:** resending `message.send` with the same `conversation_id`, sender and `client_message_id`
  returns the stored message with `replayed=true`. The uniqueness rule is in ADR 0005.
- **Fan-out scope:** v1 assumes one Chat instance. The outbox is the seam for a future shared bus
  (Postgres `LISTEN/NOTIFY` or Redis); until then, in-memory socket registries are single-instance only
  (rule 8 in `CLAUDE.md`).

## Consequences

- An ACK always means "committed", never "probably committed".
- At-least-once delivery means the client must deduplicate; the E2E test asserts one visible message
  after a forced reconnect and replay.
- The sender receives its own `message.created`; the UI merges ACK and event by id.
- A slow subscriber must not block the transaction. Fan-out happens after commit, never inside it.

## Alternatives considered

| Alternative | Why not |
|---|---|
| ACK before commit | Loses messages on a crash and breaks history/ACK agreement. |
| Exactly-once delivery | Requires coordination the spec does not ask for; idempotent client merge is cheaper. |
| Client pulls only | Cannot meet the 800 ms delivery target. |
