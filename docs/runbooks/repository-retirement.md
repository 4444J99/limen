# Repository retirement batches

`limen repos retire` replaces separate agent-led inventories with one exact-scope,
resumable executor. It does not create a new allowance, infer admission from an
old issue comment, or approve its own deletion. Existing issue owners remain open.

```sh
limen repos retire --batch /private/path/batch.json
limen repos retire --batch /private/path/batch.json --apply
limen repos accept --resume campaign-id
limen repos retire --resume campaign-id --apply
limen repos status campaign-id
```

The acceptance command runs in the separately reserved reviewer’s native session,
not in the executor. `LIMEN_SESSION_ID` must match the keeper-assigned identity.
The conductor schedules those two roles; no repeated human permission is needed.

## Private manifest

Use JSON with schema `limen.repository_retirement.v1`, `campaign_id`, a timezone-aware
`deadline`, the admitted `run_id` and independent child `review_run_id`, and an exact
`repositories` array. Each entry contains an absolute canonical `path`, authenticated
numeric GitHub `repository_id`, and existing `owner` issue such as `4444J99/limen#2739`.
List all authorized linked paths; unlisted dependent stores are retained.

`custody` contains `inventory`, its SHA-256 `inventory_sha256`, `archive_root`, and
`recovery_root`. These must identify the existing registered Archive4T and T7Recovery
devices. Both mounts must independently pass physical identity and encryption checks.
The command never configures encryption, creates keys, or prints credentials.

The preview prints the immutable `manifest_binding` and exact common-directory
resource claims. The admitted executor packet binds these using
`execution.repository_retirement = {campaign_id, manifest_sha256}`. This hash excludes
the subsequently allocated run IDs, avoiding circular hashing. Its authority includes
`repository-sync`, `repository-custody`, and `repository-retire`, exact path prefixes,
and exclusive `git-common:<digest>` claims. Use an `agent_minutes` spend envelope of
at most 120. The reviewer is a distinct native session in a child run, with the same
binding, `repository-accept` authority, and at most 10 minutes. Use the normal keeper
work-loan and registration contracts; these are not locally manufactured reservations.

## Progress, custody, and recovery

Private journals live under `$XDG_DATA_HOME/limen/repository-retirement` (default
`~/.local/share/limen/repository-retirement`). `status` shows redacted results;
`status --private` includes paths and inventories and must never be published.
Public receipts contain aggregate changes, opaque candidate IDs, owner issues,
reason codes, actual subprocess exits, and distinct allocated/free-space measurements.
Publication uses one issue comment with verified readback and a write-ahead intent.
An ambiguous POST is reconciled rather than blindly repeated.

Full filesystem copies include the Git store, reflogs, stashes, local refs, dirty,
untracked and ignored files, symlinks, modes, ACLs and extended attributes. Two actual
restore probes verify every record. Archived roots and their original paths are in
the private custody receipt. Restore to the recorded original paths through the
owning lifecycle; never overlay a live common store. Git bundles alone are insufficient.

Fast-forwards use live upstream OIDs and ancestry checks. Existing tags, divergent
branches and remote-tracking history are not rewritten. No push, prune, reflog expiry
or force removal occurs. Dirty linked views are prepared only after accepted complete
custody; exact captured paths are journaled before native non-forced detachment.
Common stores remain while any registered worktree depends on them.

Resume checks completed removal journals and live readback before counting absence.
Interrupted checkout preparation or incomplete purge remains retained with its journal
and verified archives; it is not silently repeated. Changed content invalidates only
that candidate's acceptance. A new acceptance reservation is required for a changed
proof; the original review receipt cannot authorize it.

The command stops at the inherited deadline or allowance. Active/open-file ownership,
unassigned ownership, unsupported remote identity mappings, shallow/promisor histories,
external alternates and external nested stores produce one candidate-specific reason.
Other candidates continue. Keeper connection errors stop once without an admission loop.

## Verification

The scoped suite uses real disposable Git repositories and independently injected test
admission/volume probes, never production bypass flags. It covers fast-forward direction,
additive tags, private dirty/history restoration, non-forced linked removal, retained
stores, stale acceptance, corrupt recovery copies, active paths, absent paths, bounded
command exits, CLI registration, distinct campaigns and independent native identities.

```sh
PYTHONPATH=cli/src python3 -m pytest -q cli/tests/test_repository_retirement.py cli/tests/test_worktree_abandonment.py cli/tests/test_personal_custody.py
```
