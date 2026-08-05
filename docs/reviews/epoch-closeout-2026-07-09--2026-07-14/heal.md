# Heal

Already merged in this closeout wave:

- #1026: hold Jules claims when the remote catalog is incomplete.
- #1027: gate dispatch and handoff on live runtime/mount requirements.
- #1028: type optional Omega sensor timeouts.
- #1037/#1043/#1044: make chronic fleet debt ownership-truthful and beat-wired.
- #1040: self-bootstrap the daemon's pinned interpreter and protect it from reclaim.
- #1042: parse Jules remote rows by header-anchored tail offsets.
- #1045/#1047: make pulled levers dischargeable and owner-linked.

Durable owner packets at the cutoff:

- #1029, #1031, #1032, #1035, and #1036 are green owner PRs awaiting serial policy review.
- #1030, #1033, and #1034 are conflict/staleness packets; their bodies and reviews name the exact
  reconciliation conditions. They must not be mechanically merged.
- #1049 fixes the mutating `usage-telemetry.py --help` behavior. Exact head `0c270b45` is clean and
  all six CI/PR-gate checks are green.
- #1050 preserves exact local checkout-guard commit `95b47a63`; it is preservation-only.
- #1051 owns the continuation-capsule standard, protocol propagation, epoch report, and regression
  tests. Its remote exact-head checks are the fixed-point proof for this closeout change.
- The old handoff-runtime root at `2b434e2e` is patch-identical to merged #1027 head `b33c013b`
  (`git patch-id --stable` = `b44cd270aaf069e519f5bd4297711ce6183adf44`).

Runtime reset state:

- External volumes were cleanly unmounted/ejected and are an unavailable-resource gate.
- `com.limen.overnight-watch` is unloaded after twice ignoring the pause marker and consuming
  87-95% CPU.
- `logs/AUTONOMY_PAUSED` names PR #1036 and its live fast-exit proof as the release condition.
- The user-led Claude process remains separately owned and must not be killed, edited, approved, or
  harvested by this closeout.

Closeout verification receipts:

- Online and forced-offline `scripts/no-tasks-on-me.sh` both pass.
- TABVLARIVS reports an empty inbox.
- The handoff is fresh and warm, with its unavailable-substrate task filtered from dispatchable next.
- The seven-day ask gate reports `205` intake-window tasks, `205` PASS/ADVISE, and `0` SPLIT.
- The accepted branch reaper reached a fixed point after removing only one clean, merged, idle,
  grant-covered branch.
- The live board remained byte-identical across the stability probe. SHA-256:
  `84d57f348ec22b9124b83a712635a5dfe7c8305ad818d18fc229b767eadeba58`.
