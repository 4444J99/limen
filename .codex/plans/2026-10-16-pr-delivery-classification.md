# Classify explicit delivery submissions before merge assessment

Owner: Limen merge submission workflow. Trigger: Domus PR #446 was otherwise deliverable but its explicit submission stopped at LIFECYCLE-UNKNOWN because no lifecycle label existed.

1. Treat the existing one-PR, exact-head submission command as delivery intent. Read current state, draft flag, head and labels before adding the existing delivery label to an untyped open PR.
2. Preserve every existing lifecycle hold, conflicting or unknown lifecycle label, and preservation marker. Do not classify drafts, closed PRs, mismatched heads, dependency-review routes, or unreadable state. Unattended scans never create delivery intent.
3. Verify the label mutation with fresh exact-head state, then retain the existing CI, conflict, stale-base and merge-policy checks. Failed or pending checks may defer readiness without losing delivery intent. No polling or automatic retry is added.
4. Add behavior regressions for successful classification and ordering, idempotency, holds, draft/head drift, API failures, and post-write races. Run the implicated verification batch, publish and merge through the governed rail.

Isolation: /Volumes/Archive4T/limen-pr-delivery-20261016, branch fix/pr-delivery-classification-20261016, base 24da5bffeefb855f1968e0c830c1ca5445a291cf. Target-volume storage admission passed with more than 200 GiB available. Existing internal-volume and other agents' checkouts are untouched. Retain this checkout until published validation and merge acceptance; retire only through the existing custody-verifying reclaimer.

Implementation receipt: explicit submission now materializes and rereads delivery classification before assessment. The guarded additive label write is hash-registered; the lifecycle literal ratchet shrank by one. The stale root-manifest row for the already-absent `.staged-heal` entry was removed to restore exact tracked-root parity.

Validation: all 53 focused merge-drain tests and all 18 cheap scoped gates passed. The full CLI regression gate reached 99% with no assertion failures reported before its 300-second deadline expired; this is incomplete verification, not a pass. The runner stopped before the API gate. The finite local verification allowance prevents another full-suite retry in this attempt. Gitvs owns the outstanding verification through this branch's draft PR; keep it draft until both heavy gates pass, then use the existing exact-head merge rail. The shared primary checkout has unrelated modifications and divergent history and has not been reset or patched in place.
