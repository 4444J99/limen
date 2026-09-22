# UCC local credential delivery

Authority: user requested implementation of the full UCC restoration, explicitly authorizing the existing CLAVIS cache and GitHub administrator identity. Continue autonomous bounded packets with published checkpoints. Never expose mock business data in the application.

Scope: add a local path to the existing delivery utility; pin the existing account/repository/principal; consume only the private sanctioned cache; use stdin for the exact repository secret; verify metadata. Preserve hosted App and accepted-source checks. No permission expansion or new credentials.

Implementation and evidence: local cache refuses symlinks, permissive modes, oversized/nonregular files and duplicate assignments; no shell evaluation. Local path refuses CI, verifies account plus D1 reads, principal identity, repository identity and admin permission. Only the specified secret can be written. Errors remain sanitized. Tests cover these boundaries and the unchanged hosted path (86 passed); lint and formatting passed.

Observed 2026-09-17 UTC: read-only account/repository/principal preflight passed. The authorized local apply returned success and read back the exact secret metadata. This is credential delivery evidence, not Cloudflare write/deployment acceptance. Credential value stays in existing custody and GitHub Actions secrets.

Remaining owning work: UCC deployment must verify actual resource writes and accepted revision; CLAVIS provisioning must reconcile stale Personal source references without losing provenance. UCC PR514 has a clean eight-check harness receipt but its one merge submission was deferred with dependency-policy exception unusual-dependency-files. Mixed package and implementation changes require owning review-route reconciliation, not repeated submissions or bypass.

Retain this isolated checkout until its delivery repair lands. Retain both UCC restoration checkouts for ongoing authorized work.

Staging workflow dispatched on accepted main: https://github.com/organvm-iii-ergon/public-record-data-scrapper/actions/runs/35171069185 . The old acceptance implementation is not sufficient proof; inspect actual step/artifact outcomes. Existing provisioning apply currently delegates to its read-only check and reports stale Personal references. Promptless inventory confirmed no Cloudflare item in Limen-Automation; no source items were moved or deleted. This requires a bounded provenance-preserving provisioning implementation.
