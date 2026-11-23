# Triage labels

One label from each of `tier:*`, `area:*` and `type:*`. `status:*` is optional and changes as the
issue moves. Names are lowercase, `scope:value`, and stable: tooling and saved searches match on them.

## Priority

| Label | Meaning |
|---|---|
| `tier:0` | Production is broken or data is at risk. Drop everything. |
| `tier:1` | Correctness, security or a blocked release. Next. |
| `tier:2` | Performance, reliability or developer experience. Planned. |
| `tier:3` | Nice to have. Only when the higher tiers are empty. |

## Area

| Label | Meaning |
|---|---|
| `area:api` | HTTP contract, validation, error mapping |
| `area:domain` | Business rules, use cases, invariants |
| `area:data` | Schema, migrations, queries, indexes |
| `area:infra` | Build, containers, deployment, observability |
| `area:test` | Test harness, fixtures, load tests |
| `area:docs` | Documentation and decisions |

Add an area only when it is genuinely new; update this file in the same PR.

## Type

| Label | Meaning |
|---|---|
| `type:bug` | Wrong behaviour. Include a reproduction. |
| `type:perf` | Same behaviour, better numbers. Include a baseline. |
| `type:feature` | New behaviour. Include acceptance criteria. |
| `type:chore` | Dependencies, tooling, cleanup. No behaviour change. |
| `type:adr` | A decision record, not code. |

## Status

| Label | Meaning |
|---|---|
| `status:ready` | Fully specified; someone can start without asking a question. |
| `status:needs-info` | Missing evidence or acceptance criteria. |
| `status:blocked` | Waiting on another issue, a decision or access. |
| `status:in-review` | A PR is open and waiting for review. |

## Colours

| Group | Colour |
|---|---|
| `tier:0` / `tier:1` | `B60205` |
| `tier:2` | `D93F0B` |
| `tier:3` | `FBCA04` |
| `area:*` | `1D76DB` |
| `type:*` | `5319E7` |
| `status:*` | `0E8A16` |
