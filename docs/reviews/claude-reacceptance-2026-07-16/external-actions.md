# Already-Observed External Actions

This is an inventory, not an authorization to repeat, undo, or validate an action by performing it
again. Details that identify people, private records, accounts, objects, or host paths remain in
their private owner receipts.

| Category | Observed action | Current treatment |
|---|---|---|
| Remote backup configuration | Backblaze XML exclusions were changed | Hold further mutation; reconcile current live XML in Domus before any repair |
| Mail | Four messages and one mail self-test were reported sent | Do not resend; reconcile against private mail receipts and repair authorization binding |
| Calendar | One calendar mutation was reported | Do not replay; reconcile against the calendar owner receipt |
| Media | Media visibility was changed | Preserve current evidence; verify owner policy before any further visibility change |
| Artifact delivery | An artifact was delivered through iCloud | Preserve two-copy custody evidence; do not redeliver |
| Worktree lifecycle | Worktrees were moved or reclaimed | Reconcile each root against remote custody before further movement or deletion |
| Private records | Private ARCA seals were written | Keep private; tracked ledger records only the redacted receipt state |
| Privacy containment | Affected repositories were temporarily changed from public to private on 2026-07-16 | Keep restricted until current-tree and history predicates pass; do not republish by reverting visibility |
| Merge containment | 53 auto-merge requests were canceled; two complete follow-up inventories were empty; branch deletion was disabled across the seven-repository cohort | Keep merge-drain preview-only; four private repositories still read `allow_auto_merge=true` until the account/plan owner can make that setting durable |
| Runtime containment | The live heartbeat inherited `LIMEN_MERGE_DRAIN=0` and `LIMEN_RECLAIM_APPLY=0` while dispatch remained enabled; Domus #308 now tracks the same preview valves | Keep #308 unapplied until its separate supervised apply/readback gate; the live launchd environment override is not durable custody |

No destructive history rewrite, personal-data deletion, credential action, blind host rollback, or
live-storage reversal is authorized by this inventory.
