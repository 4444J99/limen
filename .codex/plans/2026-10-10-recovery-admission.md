# Remove recovery admission bottlenecks

User source: October 9 implementation plan supplied in the direct session.

Implement additive policy reconciliation against the deployed fingerprint, preserve
all existing priorities and limits, approve only the exact ops6-coordinate-20261009
work key after owner readback, and keep unrestricted dispatch disabled. Use the
existing fanout manifest for three serial preparation roles; no reservation or
native launch before approval. A's production custody remains separate and temporal;
B needs A's authoritative receipt/release; C is activation-window-bound. Hosted
idempotency and incident acceptance remain separate.

Implement capacity-identity storage latches, APFS sharing, missing-mount rejection,
internal legacy restriction, one bounded repair writer, 256 MiB maximum allocation,
budget plus 10 GiB floor, inherited 30-minute attempt/10-minute verification limits.
Expose Domus quota observation and warnings, deduplicate maintenance through the
existing keeper intake toward 70%. Preserve history restoration/replica gates and
SQLite/sidecars. Use scoped tests and owners for publication/application.

Checkpoints and deployment blockers belong to
docs/receipts/recovery-admission-20261010/README.md and the resulting PRs. No
new scheduler, policy budget reset, history deletion or paid upgrade is authorized.
