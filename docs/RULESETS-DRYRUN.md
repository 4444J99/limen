# setup-rulesets.py — live merge-gate contract

**Updated:** 2026-08-26 · **Status:** SOURCE CONTRACT — `--apply` installs and verifies the declared
state; the live read-back, not this document, is the operational receipt.

## Limen's concurrency rail

`4444J99/limen` uses a queue-free proven-at-submission rail. Its zero-approval `pull_request` rule
blocks every direct default-branch write, requires every review thread to be resolved, and has no
bypass actors. Concurrent agents prove immutable PR heads without repeatedly rewriting them against
a moving `main`.

The ruleset targets `~DEFAULT_BRANCH` and contains exactly one rule:

- `pull_request` with `squash` as the only allowed merge method, zero required approvals, no
  code-owner or last-push approval, mandatory review-thread resolution, and no bypass actors.

Classic default-branch protection owns the registry-declared always-on check:

- context: `pr-gate`
- `strict:false`
- `enforce_admins:true`
- no human-review requirement

The ruleset's `pull_request` edge is the remote enforcement surface. Tabularius publishes only to
`tabularius/board-projection`, opens an exact-head PR, and leaves the local board dirty so later
tickets coalesce while that PR is in flight. There is no direct-push exception.

## Queue CI contract

`.github/workflows/pr-gate.yml` remains the always-on scoped orchestration check. The three
path-filtered `ci.yml` jobs are additive exact-head receipts when implicated; making them global
required contexts would strand content-only and Tabularius board PRs in `expected` forever.

- On `pull_request`, `scripts/verify.py --changed` requires a resolvable base and retains
  `--skip-ci-covered pr-gate.yml:pr-gate`. The PR's full CI children remain independently owned
  exact-head receipts.
- The `merge_group` event remains a fail-closed compatibility path if a future live queue is
  deliberately installed; the active ruleset does not install a queue rule.

## What setup-rulesets.py changes

The script is dry-run by default. For every selected repository it reports the planned classic
protection and repository settings. `--apply` is the only mutation switch.

For `4444J99/limen`, apply performs these idempotent operations:

1. Enable and read-back verify the repository switch that permits explicitly authorized Actions
   workflows to create pull requests.
2. Create or update the historically named `limen-default-merge-queue` ruleset, then read-back
   verify the exact active, squash-only, thread-resolved, no-bypass `pull_request` rule. A failure stops here before any
   weaker setting is touched.
3. Enable and read-back verify auto-merge while preserving source branches
   (`delete_branch_on_merge=false`).
4. Write and read-back verify classic protection with the always-on check declared by the conductor
   class in `institutio/github/estate.yaml`, `strict:false`, `enforce_admins:true`, no required
   review, and no actor restriction.

The source branches remain after merge so removal stays with receipt-backed reaping. The queue ruleset
prohibits direct default-branch writes, including admin and automation writers.

Every selected repository derives its checks from the first matching estate class. Fact-qualified
classes use live repository facts; explicit repository overrides win. Other repositories do not
receive Limen's PR-only ruleset.

## Commands

Read-only targeted preview:

```bash
cd ~/Workspace/limen
python3 scripts/setup-rulesets.py --repo 4444J99/limen
```

Explicit targeted apply:

```bash
cd ~/Workspace/limen
python3 scripts/setup-rulesets.py --apply --repo 4444J99/limen
```

Re-running the apply updates the named ruleset rather than creating a duplicate. The script makes no
remote mutation without the exact `--apply` token.

## Reversibility

- PR-only ruleset:
  `gh api -X DELETE /repos/4444J99/limen/rulesets/<ruleset-id>`
- Classic branch protection:
  `gh api -X DELETE /repos/4444J99/limen/branches/main/protection`
- Auto-merge:
  `gh api -X PATCH /repos/4444J99/limen -F allow_auto_merge=false`

Ruleset `19147990` retains its historical name so external receipts remain stable. The native queue
rule was removed on 2026-08-06; the active contract is direct squash only after the always-on scoped
gate passes and every review thread is resolved. Conditional CI children remain additional evidence.
