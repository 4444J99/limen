# setup-rulesets.py — dry-run merge-gate contract

**Updated:** 2026-07-18 · **Status:** TARGET CONTRACT — temporary classic protection is live;
the queue ruleset is applied only after the `merge_group` workflow lands.

## Limen's concurrency rail

`organvm/limen` has one targeted native merge-queue ruleset. It serializes only the final
integration step, and its zero-approval `pull_request` rule blocks every direct default-branch
write with no bypass actors. Concurrent agents keep working and proving their own exact PR heads
without repeatedly merging a moving `main`.

The ruleset targets `~DEFAULT_BRANCH` and contains two rules:

- `pull_request` with `squash` as the only allowed merge method, zero required approvals, no
  code-owner/last-push/thread-resolution requirement, and no bypass actors;
- `merge_queue` with the parameters below.

| Setting | Value |
|---|---:|
| merge method | `SQUASH` |
| grouping strategy | `HEADGREEN` |
| required-check timeout | 60 minutes |
| concurrent queue builds | 4 |
| maximum PRs merged per group | 1 |
| minimum PRs per group | 1 |
| minimum-size wait | 0 minutes |

`HEADGREEN` plus a one-PR merge group proves the head synthetic integration commit. A maximum of
four groups may build concurrently, but GitHub merges them one at a time. This keeps the integration
window serialized without turning the whole agent fleet into one serial lane.

Classic default-branch protection remains the owner of the required check:

- context: `pr-gate`
- `strict:false`
- `enforce_admins:true`
- no human-review requirement

The ruleset's `pull_request` edge is the remote enforcement surface. Tabularius publishes only to
`tabularius/board-projection`, opens an exact-head PR, and leaves the local board dirty so later
tickets coalesce while that PR is in flight. There is no direct-push exception.

## Queue CI contract

`.github/workflows/pr-gate.yml` is the only required workflow triggered by
`merge_group: checks_requested`.

- On `pull_request`, `scripts/verify.py --changed` requires a resolvable base and retains
  `--skip-ci-covered pr-gate.yml:pr-gate`. The PR's full CI children remain independently owned
  exact-head receipts.
- On `merge_group`, `scripts/verify.py --changed --integration` compares the checked-out synthetic
  group commit with `github.event.merge_group.base_sha`. Integration mode fails closed if that base
  cannot resolve, runs every implicated scoped gate, does not use `--skip-ci-covered`, and does not
  restart the whole PR matrix merely because `main` advanced.

GitHub documents `merge_group` as a separate event whose `GITHUB_SHA` is the synthetic group commit;
required checks must explicitly subscribe to it or the queue cannot receive their result.

## What setup-rulesets.py changes

The script is dry-run by default. For every selected repository it reports the planned classic
protection and repository settings. `--apply` is the only mutation switch.

For `organvm/limen`, apply performs these idempotent operations:

1. Enable and read-back verify the repository switch that permits explicitly authorized Actions
   workflows to create pull requests.
2. Create or update `limen-default-merge-queue`, then read-back verify the exact active,
   squash-only, no-bypass `pull_request` and `merge_queue` rules. A failure stops here before any
   weaker setting is touched.
3. Enable and read-back verify auto-merge while preserving source branches
   (`delete_branch_on_merge=false`).
4. Write and read-back verify classic protection with required context `pr-gate`, `strict:false`,
   `enforce_admins:true`, no required review, and no actor restriction.

The source branches remain after merge so removal stays with receipt-backed reaping. The queue ruleset
prohibits direct default-branch writes, including admin and automation writers.

Other repositories retain the existing detected-check behavior and do not receive a merge-queue
ruleset.

## Commands

Read-only targeted preview:

```bash
cd ~/Workspace/limen
python3 scripts/setup-rulesets.py --repo organvm/limen
```

Explicit targeted apply, only after the workflow change is merged and the operator authorizes the
repository-setting mutation:

```bash
cd ~/Workspace/limen
python3 scripts/setup-rulesets.py --apply --repo organvm/limen
```

Re-running the apply updates the named ruleset rather than creating a duplicate. The script makes no
remote mutation without the exact `--apply` token.

## Reversibility

- Queue ruleset:
  `gh api -X DELETE /repos/organvm/limen/rulesets/<ruleset-id>`
- Classic branch protection:
  `gh api -X DELETE /repos/organvm/limen/branches/main/protection`
- Auto-merge:
  `gh api -X PATCH /repos/organvm/limen -F allow_auto_merge=false`

On 2026-07-18, temporary classic `pr-gate` protection with `enforce_admins:true` was applied before
the code rollout to block the still-deployed legacy Contents writers. It must not be weakened before
the target ruleset is installed and read-back verified.
