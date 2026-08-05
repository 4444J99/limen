# Pre-Build Excavation Predicate

Generated: `manual-contract`

## Canonical Decision

- Before building substantive work in a shared fleet repo, check the PR and commit stream first.
- This predicate prevents rebuilding work that already shipped, is in flight, or was already rejected.
- It is read-only and does not mutate repos, branches, issues, tasks, or remotes.
- A `CLEAR` result is not authority to skip reading the printed stream; it only means supplied keywords did not match.

## Command

```bash
scripts/pre-build-excavate.sh <owner/repo> [keyword ...]
```

Example:

```bash
scripts/pre-build-excavate.sh organvm/a-i-chat--exporter moneta checkout licence
```

## Result States

| Exit | State | Meaning |
|---:|---|---|
| 0 | `CLEAR` | Repo stream was reachable and no supplied keyword matched existing PR/commit titles. |
| 2 | `DEGRADED` | Repo stream was not trustworthy because `gh`, auth, network, or repo lookup failed. |
| 3 | `LIKELY-DUP` | A supplied keyword matched open/closed/merged PRs or recent commit subjects. |

## Contract

- This receipt records the predicate as a durable prior-excavation surface.
- Per-repo runs belong in the owner repo, PR, issue, or task packet that needed the check.
- Do not store raw private prompt bodies or credentials in predicate output.
