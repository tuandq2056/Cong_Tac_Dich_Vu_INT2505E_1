# 0006: Monotonic read-state; summary reads one fixed snapshot

- Status: accepted
- Date: 2026-11-21
- Deciders: team

## Context

Two tabs can update read-state out of order. A summary must describe a stable range even while new
messages arrive, must include only text from other people, and must never move the read marker. The
contract exposes `last_read_seq`, `snapshot_seq`, `source_from_seq`, `source_to_seq`,
`source_count` and `omitted_count`.

## Decision

- **Read-state:** one row per `(conversation_id, user_id)`, initialised to `0`. Update with a single
  statement, `last_read_seq = GREATEST(last_read_seq, :through_seq)`, and reject `through_seq` greater
  than the current `latest_seq` with `422 READ_AHEAD`. Concurrent updates 45 then 40 end at 45.
- **Summary:** in one `REPEATABLE READ` transaction, read `last_read_seq` and `latest_seq` and fix
  `snapshot_seq = latest_seq`. Select messages where:
  - `seq > last_read_seq AND seq <= snapshot_seq`,
  - `sender_id <> :user_id`,
  - `content_type = 'text'`.

  Order by `seq` ascending, take the newest 100. `omitted_count` is the number of eligible rows older
  than the cut. The LLM receives only `text`, in ascending `seq` order. If no eligible row exists,
  return `status=empty`, `summary=null`, `source_count=0`, two null source bounds and do not call the
  LLM.
- **Isolation of failure:** an LLM error or timeout returns `503 SUMMARY_UNAVAILABLE` and leaves
  read-state untouched. The summary is not persisted in v1; it is a read-only projection.
- **Read vs sync:** the client keeps a device sync marker separate from the user's read marker. Fetching
  history or searching never advances either.

## Consequences

- Summaries are reproducible for a given `snapshot_seq`, which makes the 104-message test deterministic.
- A summary can include a message the user read in another tab a second ago; that is acceptable because
  the snapshot is defined at request time.
- No summary cache means repeated requests pay the LLM cost again; measure before adding one.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Move read-state when summarising | The spec forbids it; a summary is not a read. |
| Select first 100 by `seq` | Drops the newest messages, which are the useful ones. |
| Include file names or audio transcripts | The spec limits the LLM input to text content. |
