# <issue>: <title>

Status: draft | agreed | in progress | done
Branch: `<type>/<issue>-<slug>`

## Problem

What is wrong or missing, with evidence (command output, log line, number). Link the issue.

## Constraints

Which project rules and which ADRs apply. What must not change: contracts, ordering, schema.

## Options

| Option | Change | Cost | Risk | Why not |
|---|---|---|---|---|
| A | | | | |
| B | | | | |

## Decision

The option chosen and what would make us revisit it.

## Tests that must fail first

- [ ] `<test name>` — fails because `<reason>`
- [ ] `<concurrency/randomised test>` — proves `<ordering property>`

## Implementation sketch

Files to touch and the order. Small enough to fit in one pull request.

## Verification

- [ ] Full check green
- [ ] Independent review
- [ ] Benchmark row (or "no performance claim")

## Open questions

- [ ] Q1: <question> — decided at <step>, default if undecided.
