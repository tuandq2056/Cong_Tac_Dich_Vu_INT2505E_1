# Tracking work with GitHub Issues

Every change starts as an issue. The issue is the contract: if it is not in the issue, it is not in
the pull request.

## Issue body

Use the template in `.github/ISSUE_TEMPLATE/task.md`. A useful issue has, in this order:

1. **Problem** — one paragraph, plus evidence: a command, a log line, a failing test or a number.
2. **Acceptance criteria** — checkboxes that a reviewer can verify without reading the diff.
3. **Affected decisions** — links to the ADRs the change touches.
4. **Out of scope** — what this issue deliberately does not fix.

An issue without testable acceptance criteria is not ready. Mark it `status:needs-info`.

## Labels

The label set is defined in [triage-labels.md](triage-labels.md). Every issue carries one `tier:*`,
one `area:*` and one `type:*`; `status:*` is optional but recommended.

## Command line

```bash
gh issue list --state open --limit 100
gh issue view <n> --comments
gh issue create --title "..." --body-file /tmp/issue.md --label tier:2,area:api,type:bug
gh issue edit <n> --add-label status:ready
gh issue close <n> --comment "Done in #<pr>"
```

Use `--json` and `--jq` when the output feeds another command. Do not create a duplicate: search
`gh issue list --state all` by title prefix first.

## Branches and pull requests

- One issue, one branch: `feat/<issue>-<slug>`, `fix/<issue>-<slug>`, `perf/<issue>-<slug>`, cut from
  an up-to-date `main`.
- Conventional Commits, one tested increment per commit.
- The PR body contains `Closes #<issue>`, the failing-test output, the verification command and its
  result, and a benchmark row when the change claims a performance win.
- A pull request is merged by a person. Authors do not merge their own PRs and do not push to `main`.
