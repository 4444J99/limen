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
