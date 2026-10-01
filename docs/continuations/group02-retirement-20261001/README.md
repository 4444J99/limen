# Group 02 restored ignored-payload retirement

Owners: Domus #397, PORTVS #14, Limen #2740. The user explicitly expanded
the stream allowlist on 2026-10-01 to permit required shared-dependency work.

The ordinary worktree lifecycle refuses all ignored payload, including an
expired continuation capsule and test caches whose complete encrypted snapshots
have already been restored. `scripts/retire-restored-ignored-payload.py` bridges
that custody evidence without changing or bypassing the reclaimer.

The adapter accepts only G02-05 and G02-09 from the merged diagnostics receipt
at `b97e9eabd50881fbe2ad1dd47a2d65fbb4309be3`. It authenticates the private
release, checks ciphertext and snapshot hashes, restores every captured entry,
compares the live complete tree, and removes only exclusively ignored
directories. It uses the existing descriptor-safe custody purge with inode,
content and process rechecks. Tracked files, Git stores, refs and worktree
registrations are untouched. Protection, age, lock and process gates remain
mandatory; any changed or uncaptured byte retains the payload.

Afterward the installed `reclaim-worktrees.py` must separately admit and detach
the clean worktree. An ignored-payload purge is not checkout retirement.

Native state cutover remains subject to protected-client drain. The current
host explicitly selects the legacy agent root inside Limen. The existing
source-independent adapter correctly refuses to silently create an empty
replacement. Do not move active databases, restart protected sessions, or
change that root declaration until consistent capture, restoration, native
canary and rollback receipts exist. Source checkout retention remains explicit.

Validation: four negative/control tests cover byte/mode/new-entry drift,
archive traversal/link denial, and exclusion of tracked parents. Both target
snapshots passed authenticated download/decryption, full restoration and live
tree comparison in dry-run before apply. Execution receipts are appended here
after the owning lifecycle completes.

## Execution on 2026-10-01

- G02-05: one ignored continuation directory purged after fresh restoration
  and full live-tree comparison. The descriptor-safe receipt is completed.
- G02-09: six exclusively ignored cache directories purged through the same
  custody protocol. All six descriptor-safe receipts are completed.
- G02-03: diagnostics clone physically retired by the installed clone reaper.
  The remote belt proved every local object remained recoverable from origin.
  Its own remote-check SSH multiplexer was gracefully drained; the final check
  used nonpersistent SSH and retained all normal credential and hook controls.
  Native deletion receipt: 2,051,460 logical bytes; pre-removal allocation:
  2,844 KiB. The directory is absent. Concurrent host writes reduced observed
  free space, so no positive APFS free-space gain is attributed to this deletion.
- All ten other original roots remain. The five linked views have zero native
  reclaim candidates: four are under the unchanged 24-hour idle gate and the
  host-repair view is dirty. Removing ignored directories updated the parent
  timestamps; this adapter does not backdate those directories to force removal.
  The existing beat-wired reclaimer discovers repo-local roots and owns later
  age-qualified retirement; no new scheduled process was activated.
- Native state cutover: six existing Codex SQLite databases are open by four
  live consumers. Chezmoi still selects the protected, dirty Domus source.
  No protected client, state database or source branch was moved or restarted.
  The source-detachment implementation checkout created by this attempt was
  unused and clean; it was removed using non-forced Git worktree removal.

The user override removed the shared-dependency scope blocker. It did not erase
native-client drain, custody, active-source or idle-age predicates. E3 cutover
is still incomplete; source integration and encrypted preservation are credited
only to their measured acceptance. See `execution.json` for redacted receipts.
