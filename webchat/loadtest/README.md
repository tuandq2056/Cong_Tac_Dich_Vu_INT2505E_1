# Load tests

Target dataset: 100 conversations, 10 000 messages each, a fixed keyword set with common and rare
terms. Ramp for 2 minutes, hold for 10 minutes. Record CPU, RAM, database version and cache state with
every result.

| Profile | Load | Target while holding |
|---|---|---|
| Realtime | 200 WebSocket sessions in 20 groups, 20 text messages/s total | send→ACK p95 ≤ 500 ms, send→recipient p95 ≤ 800 ms, no ACKed message missing from history |
| History | 20 history requests/s, 30 messages/page, deep pagination | p95 ≤ 300 ms, no repeated id across adjacent pages |
| Search | 10 searches/s on the same dataset | p95 ≤ 600 ms, correct conversation, system-error rate < 1% |

`run-smoke.sh` is the short CI version: one connection per scenario, a handful of messages, and a
correctness gate (no duplicate `seq`, no missing ACKed message). It must finish in under two minutes.

Results go to `loadtest/results/` (ignored by git) and one summary row to the local ledger.
