# Agent surface census and safe containment handoff

Owner: [Limen #2848](https://github.com/4444J99/limen/issues/2848).
Architecture reconciliation: [existing PR #3026](https://github.com/4444J99/limen/pull/3026).

Read [revision 4](../../plans/2026-10-18-codex-census-safe-containment-v4.md) for the
provider mapping, exact source surfaces, staged commands and acceptance predicates.

- inventory.py scans metadata at unlimited depth; verify checks retained hashes and counts.
- stage-rollback.py prepares and verifies a fresh candidate while preserving current history.
- check-tools.py exercises deep enumeration, aliases, failure preservation and replay refusal.
- coverage.json records measured counts and gaps without private directory names.
- session-evidence.json binds verification and private publication readback.
- session-closeout.json records the exact native session and retained ownership.

Private path ledgers belong to the private Domus census owner; their remote publication is
bound in the evidence. A complete traversal, a published handoff, and a released session are
separate states. No runtime cutover or retirement is authorized by these artifacts.
