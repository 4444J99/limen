# ARCA escrow recovery predicate

Owner: continuity; permanent lever L-ARCA-KEY-ESCROW; issue #719.

Implement a read-only executable check using the canonical Private-vault escrow,
one bounded committed ciphertext archive, and memory-only tar inspection. Keep
passwords off argv, environment, logs, and disk. Reject malformed, oversized,
missing, or truncated evidence. Emit only counts and an explicit bounded scope.

Verify hermetic boundary tests and the existing ARCA generation gate. Run the
live predicate separately: unit fixtures cannot establish actual escrow access.
Full estate restoration, fresh-device recovery, and permanent lever closure are
separate obligations; this predicate proves only its stated recovery scope.

## Live verification

`python3 scripts/check-arca-escrow.py` returned exit 0 on September 16, 2026:
accepted=true, ciphertext_bytes=4128, regular_files=1, plaintext_bytes=1759,
scope=one-bounded-committed-archive. The source was read at a pinned local Git
commit; this does not assert remote custody or full restoration. Six hermetic
boundary tests also passed. No plaintext was extracted or key rotated.
