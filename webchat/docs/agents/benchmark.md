# Benchmark protocol

A performance claim is evidence, not an opinion. This file defines the evidence the project accepts.

## Rules

1. **One environment.** Record machine, CPU, memory, database version, instance count and commit for
   every run. Numbers from different environments are not comparable.
2. **Warm up, then discard the warm-up.** Cold caches and a cold runtime can double latency.
3. **A → B → A.** Baseline, change, baseline, on the same database. Keep both baselines. A result is
   real only if it is outside both and larger than the noise floor (default 10%).
4. **One scenario per block.** Do not mix a write-heavy scenario with a read scenario. Reset state
   between blocks and say how.
5. **Gate before metric.** Run the correctness gate (no duplicate writes, no lost updates, no failed
   requests). A failed gate invalidates the run whatever the latency says.
6. **Keep the raw output.** Store it under `loadtest/results/` (ignored by git) and one summary row in
   the local ledger.

## Ledger row

```md
| date | label | scenario @ rate | baseline p50/p95 | change p50/p95 | Δ p95 | gate | verdict | commit |
```

Add the top SQL statements before and after when the database is the bottleneck. Statement counts and
rows examined survive JIT noise; latency alone does not.

## Verdict

- **KEEP** — outside both baselines, above the noise floor, gate passed.
- **DROP** — inside the noise, regresses another scenario beyond the floor, or fails the gate.
- **RERUN** — the two baselines disagree by more than the floor. Fix the environment first.
